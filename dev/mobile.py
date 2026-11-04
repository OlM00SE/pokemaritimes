"""Send the latest verified build to your phone, through a private Google Drive folder.

  python dev/mobile.py              # build, verify, publish (nothing to upload if this ROM is there)
  python dev/mobile.py --full       # also run the slice playthrough (tests/playthrough_slice1.py)
  python dev/mobile.py --check      # build and verify only; publish nothing
  python dev/mobile.py --status     # what's on Drive, and whether its phone saves load in this build
  python dev/mobile.py --allow-dirty  # publish a build of uncommitted changes (named ..._dirty-<time>)

The upload is a copy into Google Drive for Desktop's local drive (G:\\My Drive by default), which
syncs it: no API keys or tokens, and nothing about the account is stored in the repo. The folder is
"<My Drive>/PokeMaritimes playtest", created in My Drive's root, so it is private to the account
unless someone shares it by hand. MARITIMES_DRIVE_DIR overrides the folder's path.

  PokeMaritimes_save<N>.zip   the build to play: a ZIP holding PokeMaritimes_save<N>.gba (13 MB,
                              not 32; My Boy! plays a .zip directly, and Android and the Drive app
                              know the type). N is the save layout version: every build with
                              the same N reads the same saves, so replacing the file keeps the
                              phone's save (emulators find the save by the ROM's file name). A
                              save break changes N, so the new build gets a fresh save and the
                              old save stays with the old file.
  README.txt                  this build, what changed, save compatibility, phone instructions,
                              and a direct download link (the Drive app hides its Download item
                              while Android's Data Saver is on; the link opens in Chrome instead,
                              and works only signed in to the owner's account)
  builds/                     every build published, zipped: PokeMaritimes_<date>_<commit>_save<N>.zip
                              (the ROM, named for its save line, and build.txt); index.json lists them
  saves/                      phone saves uploaded by hand (.sav, .srm); each publish checks them
  saves/myboy/                dated copies of My Boy!'s synced saves, made by each publish

My Boy! (Tom's emulator) keeps saves in a private app folder; its "Sync with Google Drive" setting
mirrors them into <My Drive>/MyBoy, which Drive for Desktop shows on this PC. Each publish reads
the files there whose names contain "PokeMaritimes" (never writing there: that would sync back to
the phone), backs up any new content into saves/myboy/, and tests the build against the newest.

"Verified": the exact bytes published boot in mGBA (the dev build the tests use), start a new game,
save, and CONTINUE to the same spot; the newest phone save in saves/ that this build can read
CONTINUEs to the overworld (My Boy!'s synced saves included); with --full, the slice playthrough passes too. Nothing is published
from a tree with uncommitted changes unless --allow-dirty says so: a build is named by its commit.
"""
import argparse, ctypes, datetime, glob, hashlib, io, json, os, shutil, sqlite3, string, struct, subprocess
import sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
import save_layout, savefile

FOLDER_NAME = "PokeMaritimes playtest"
GAME = "PokeMaritimes"
OUT = os.path.join(REPO, "dev", "out", "mobile")
ROM_SRC = os.path.join(REPO, "pokeemerald.gba")
HISTORY_IN_README = 8
SYNC_FOLDERS = ("MyBoy", "MyOldBoy")    # My Boy!'s "Sync with Google Drive" folders, in My Drive
FLASH_SIZE = savefile.NUM_SAVE_SLOTS * savefile.NUM_SECTORS_PER_SLOT * savefile.SECTOR_SIZE \
    + 4 * savefile.SECTOR_SIZE          # both slots, then Hall of Fame and Trainer Hill sectors: 128 KB


# ---------------------------------------------------------------- the build
def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def build_identity(allow_dirty):
    """{commit, short, date, subject, branch, dirty, version}: the build's name comes from HEAD."""
    commit, short, iso, subject = git("log", "-1", "--format=%H%n%h%n%cI%n%s").split("\n", 3)
    dirty = bool(git("status", "--porcelain"))
    if dirty and not allow_dirty:
        sys.exit("the working tree has uncommitted changes (git status): commit them first, so the "
                 "build is named by what it contains, or pass --allow-dirty")
    version = f"{iso[:10]}_{short}"
    if dirty:
        version += f"_dirty-{datetime.datetime.now():%H%M%S}"
    return {"commit": commit, "short": short, "date": iso, "subject": subject, "dirty": dirty,
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "version": version}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def play_zip(rom_name, rom, iso_date):
    """The play file: a ZIP holding only the ROM (My Boy! loads "the first recognized file in the
    archive"), stamped with the commit's date so the same ROM always gives the same bytes."""
    info = zipfile.ZipInfo(rom_name, date_time=tuple(int(x) for x in (
        iso_date[0:4], iso_date[5:7], iso_date[8:10], iso_date[11:13], iso_date[14:16], iso_date[17:19])))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0                  # else it follows the platform: the same bytes everywhere
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(info, rom, compresslevel=9)
    return buf.getvalue()


def zip_rom_digest(path):
    """sha256 of the .gba inside a play ZIP, or None if it isn't one."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".gba")]
            return sha256(z.read(names[0])) if len(names) == 1 else None
    except (zipfile.BadZipFile, OSError, KeyError):
        return None


def check_header(rom):
    """The GBA cartridge header a phone emulator relies on: Emerald's game code (it picks the save
    type, 128 KB flash, and the clock from it), a valid complement check, and a cartridge size."""
    problems = []
    if not 0xC0 <= len(rom) <= 32 << 20:
        problems.append(f"size {len(rom)} bytes")
    else:
        if rom[0xAC:0xB0] != b"BPEE":
            problems.append(f"game code {rom[0xAC:0xB0]!r}, not BPEE")
        if rom[0xBD] != (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF:
            problems.append("header complement check is wrong")
    return problems


# ---------------------------------------------------------------- verification in mGBA
def _fresh(path):
    """Delete a file the previous mGBA may still hold for a moment (Windows)."""
    for attempt in range(20):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.5)


def verify(rom_bytes, phone_save=None, full=False, package=None):
    """Boot the exact bytes to publish. Returns (ok, [lines]). The ROM is copied to dev/out/mobile
    with its .map (the bridge reads symbols from it); nothing touches a real save. `package`, the
    play ZIP's bytes, is booted as it is, as My Boy! opens it."""
    os.makedirs(OUT, exist_ok=True)
    rom, sav = os.path.join(OUT, "check.gba"), os.path.join(OUT, "check.sav")
    _fresh(sav)
    with open(rom, "wb") as f:
        f.write(rom_bytes)
    shutil.copyfile(os.path.join(REPO, "pokeemerald.map"), os.path.join(OUT, "check.map"))
    lines, ok = [], True

    def step(good, what):
        nonlocal ok
        lines.append(f"  {'PASS' if good else 'FAIL'}: {what}")
        print(lines[-1])
        ok &= bool(good)
        return good

    with Emu(rom, extra_args=UNTHROTTLED) as e:
        if step(e.boot_new_game(), "a new game reaches the overworld"):
            e.wait_for_control()
            before = e.player()
            e.shot(os.path.join(OUT, "check_newgame.png"))
            step(e.save_game(), f"the game saves ({e.map_name(before)} {before[2:]})")
    if ok:
        verdict = savefile.check(sav)
        step(verdict[0] == "ok", f"dev/savefile.py reads that save as loadable: {verdict[1]}")
        with Emu(rom, extra_args=UNTHROTTLED) as e:
            if step(e.boot_to_overworld(), "after a power cycle, CONTINUE reaches the overworld"):
                e.wait_for_control()
                after = e.player()
                step(after == before, f"at the same spot ({e.map_name(after)} {after[2:]})")
                e.shot(os.path.join(OUT, "check_continue.png"))
    pkg, pkg_sav = os.path.join(OUT, "package.zip"), os.path.join(OUT, "package.sav")
    if ok and package:      # the file the phone opens, as it is: its save is package.sav
        with open(pkg, "wb") as f:
            f.write(package)
        shutil.copyfile(os.path.join(OUT, "check.map"), os.path.join(OUT, "package.map"))
        _fresh(pkg_sav)
        with Emu(pkg, extra_args=UNTHROTTLED) as e:
            if step(e.boot_new_game(), "the play ZIP itself boots in mGBA and starts a new game"):
                e.wait_for_control()
                here = e.player()
                step(e.save_game(), "the game saves, from the ZIP")
        if ok:
            with Emu(pkg, extra_args=UNTHROTTLED) as e:
                back = e.boot_to_overworld()
                if back:
                    e.wait_for_control()
                step(back and e.player() == here, "after a power cycle, the ZIP CONTINUEs at the same spot")
        _fresh(pkg_sav)
    if ok and phone_save:   # booted from what the phone opens: the ZIP when there is one
        name = os.path.basename(phone_save)
        target, target_sav = (pkg, pkg_sav) if package else (rom, sav)
        _fresh(target_sav)
        shutil.copyfile(phone_save, target_sav)
        with Emu(target, extra_args=UNTHROTTLED) as e:
            if step(e.boot_to_overworld(), f"the phone save {name} CONTINUEs to the overworld"
                                           + (" from the play ZIP" if package else "")):
                e.wait_for_control()
                loc = e.player()
                lines[-1] += f" ({e.map_name(loc)} {loc[2:]})"
                e.shot(os.path.join(OUT, "check_phone_save.png"))
        _fresh(target_sav)  # a copy of Tom's save: don't leave it lying in dev/out
    if ok and full:
        r = subprocess.run([sys.executable, os.path.join(REPO, "dev", "tests", "playthrough_slice1.py")])
        step(r.returncode == 0, "the slice playthrough (tests/playthrough_slice1.py)")
    with open(rom, "rb") as f:
        step(f.read() == rom_bytes, "the ROM file tested is byte for byte the one to publish")
    return ok, lines


# ---------------------------------------------------------------- Google Drive (for Desktop)
def volume_label(root):
    buf = ctypes.create_unicode_buffer(261)
    if ctypes.windll.kernel32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0):
        return buf.value
    return ""


def drive_folder():
    """The publish folder: MARITIMES_DRIVE_DIR, or <the Google Drive volume>/My Drive/<FOLDER_NAME>."""
    if os.environ.get("MARITIMES_DRIVE_DIR"):     # My Boy!'s sync folders are looked for beside it
        return os.path.normpath(os.environ["MARITIMES_DRIVE_DIR"])
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(os.path.join(root, "My Drive")) and volume_label(root) == "Google Drive":
            return os.path.join(root, "My Drive", FOLDER_NAME)
    sys.exit("Google Drive for Desktop isn't running (no 'Google Drive' volume with a My Drive folder).\n"
             "Start it from the Start menu and sign in, or set MARITIMES_DRIVE_DIR to the folder to use.")


def drivefs_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq GoogleDriveFS.exe", "/NH"],
                       capture_output=True, text=True)
    return "GoogleDriveFS.exe" in r.stdout


def _drive_dbs():
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS")
    return glob.glob(os.path.join(base, "*", "metadata_sqlite_db"))


def _query_drive(fn):
    """Run fn(connection) on a copy of each Drive for Desktop metadata database (with its WAL:
    reading the live file could block Drive's own writes); a list of the results, or None if
    there's no database or it can't be read."""
    dbs = _drive_dbs()
    if not dbs:
        return None
    results = []
    try:
        for db in dbs:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                for suffix in ("", "-wal", "-shm"):
                    if os.path.exists(db + suffix):
                        shutil.copyfile(db + suffix, os.path.join(tmp, "m" + suffix))
                con = sqlite3.connect(os.path.join(tmp, "m"))
                try:
                    results.append(fn(con))
                finally:
                    con.close()
    except (sqlite3.Error, OSError):
        return None
    return results


ITEM_IN_FOLDER = ("FROM items i JOIN stable_parents sp ON sp.item_stable_id = i.stable_id"
                  " JOIN items f ON f.stable_id = sp.parent_stable_id"
                  " WHERE i.local_title = ? AND f.local_title = ? AND i.trashed = 0 AND i.is_tombstone = 0"
                  " AND f.trashed = 0 AND f.is_tombstone = 0"
                  " AND i.id NOT LIKE 'local%'"
                  " AND i.stable_id NOT IN (SELECT stable_id FROM local_stable_ids)")


def uploaded(files, since):
    """Which of {name: (folder name, size)} Google Drive for Desktop has finished uploading, judged
    from its local metadata database (undocumented, so this is best effort; None if it can't be
    read). Measured on Drive for Desktop 133 with a 32 MB file, new and overwritten: while content
    is uploading, the item has a 'local-content-size' property and a pending operation names it,
    and its modified_date (the cloud's) stays as it was; once uploaded both marks are gone and
    modified_date moves. So a file counts as uploaded when its item, in a folder of that name, has
    a cloud id rather than a local one, the size, a modified_date since `since` (epoch seconds),
    neither mark, and isn't trashed."""
    def done_in(con):
        pending = [r[0] or b"" for r in con.execute("SELECT CAST(proto AS BLOB) FROM operations")]
        done = set()
        for name, (parent, size) in files.items():
            row = con.execute(
                "SELECT 1 " + ITEM_IN_FOLDER + " AND i.file_size = ? AND i.modified_date >= ?"
                " AND NOT EXISTS (SELECT 1 FROM item_properties ip WHERE"
                " ip.item_stable_id = i.stable_id AND ip.key = 'local-content-size')",
                (name, parent, size, int((since - 5) * 1000))).fetchone()
            marker = bytes([len(name.encode())]) + name.encode()     # a protobuf string field
            if row and not any(marker in op for op in pending):
                done.add(name)
        return done
    found = _query_drive(done_in)
    return None if found is None else set().union(*found)


def download_link(folder, name):
    """A direct download link for an uploaded file in the publish folder, from its cloud id:
    it opens in a browser (not the Drive app), and serves the file only to a browser signed in to
    the account that owns it (anyone else gets Google's sign-in page, checked 2026-11-04).
    None until Drive has uploaded the file as it is on this PC (an overwritten file keeps its id,
    so the id alone could serve the previous content)."""
    path = os.path.join(folder, name)
    try:
        size, mtime = os.path.getsize(path), os.path.getmtime(path)
    except OSError:
        return None
    if name not in (uploaded({name: (os.path.basename(folder), size)}, mtime) or set()):
        return None

    def ids(con):
        return [r[0] for r in con.execute("SELECT i.id " + ITEM_IN_FOLDER,
                                          (name, os.path.basename(folder)))]
    found = _query_drive(ids)
    cloud = sorted({i for batch in found or [] for i in batch})
    if len(cloud) != 1:
        return None
    return f"https://drive.usercontent.google.com/download?id={cloud[0]}&export=download"


def wait_uploaded(files, since, timeout):
    start, last = time.time(), None
    while True:
        done = uploaded(files, since)
        if done is None:
            return "unknown"
        if len(done) == len(files):
            return "uploaded"
        if time.time() - start > timeout:
            return "syncing"
        left = sorted(set(files) - done)
        if left != last:
            print(f"  waiting for Google Drive to upload {', '.join(left)}...")
            last = left
        time.sleep(5)


def write_verified(path, data):
    """Write through a temporary name, then read it back from the Drive volume."""
    tmp = path + ".partial"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    with open(path, "rb") as f:
        if f.read() != data:
            sys.exit(f"read-back mismatch: {path}")


def archived(folder, index, digest):
    """True if an archive in builds/ that the index names holds a ROM with this hash."""
    for e in index:
        path = os.path.join(folder, "builds", e.get("archive", ""))
        if e.get("sha256") == digest and os.path.isfile(path):
            try:
                with zipfile.ZipFile(path) as z:
                    if sha256(z.read(e.get("rom", e["play"]))) == digest:
                        return True
            except (zipfile.BadZipFile, KeyError, OSError):
                pass
    return False


def retire_old_play_files(folder, index, play):
    """Any other play file (an older save line, or a loose .gba from before the ZIPs) leaves the
    top level once an archive in builds/ holds its ROM; on the Drive volume a removal goes to
    Drive's trash."""
    olds = glob.glob(os.path.join(folder, f"{GAME}_save*.gba")) + glob.glob(os.path.join(folder, f"{GAME}_save*.zip"))
    for old in olds:
        if os.path.basename(old) == play:
            continue
        old_digest = zip_rom_digest(old) if old.endswith(".zip") else sha256(open(old, "rb").read())
        if old_digest and archived(folder, index, old_digest):
            os.remove(old)
            print(f"removed {os.path.basename(old)} from the top level (builds/ holds it)")
        else:
            print(f"kept {os.path.basename(old)}: no archive in builds/ holds it")


def load_index(folder):
    p = os.path.join(folder, "builds", "index.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def synced_saves(folder):
    """(saves, ignored): My Boy!'s synced saves for this game, under <My Drive>/MyBoy (or MyOldBoy):
    files whose names contain the game's name and that end in .sav/.srm or are the size of a
    flash image (128 KB, plus up to 1 KB of clock data). Other files with the game's name (save
    states, say) are counted in `ignored`. Only read, never written: a change there would sync
    back to the phone and replace the save My Boy! plays from. A file that vanishes mid-scan (a
    sync in progress) is skipped."""
    root, saves, ignored = os.path.dirname(folder), [], []
    for sync in SYNC_FOLDERS:
        for dirpath, _, names in os.walk(os.path.join(root, sync)):
            for name in names:
                if GAME.lower() not in name.lower():
                    continue
                p = os.path.join(dirpath, name)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if name.lower().endswith((".sav", ".srm")) or FLASH_SIZE <= size <= FLASH_SIZE + 1024:
                    saves.append(p)
                else:
                    ignored.append(p)
    return saves, ignored


def back_up_synced(folder, synced):
    """Copy each synced save whose content differs from its newest backup into saves/myboy/ as
    <its time>_<its name> (never over another backup). Returns the backups written. Only the
    newest backup of each name is read, so the cost doesn't grow with the history."""
    dest = os.path.join(folder, "saves", "myboy")
    written = []
    for p in synced:
        try:
            data, mtime = open(p, "rb").read(), os.path.getmtime(p)
        except OSError:
            continue
        name = os.path.basename(p)
        previous = sorted(glob.glob(os.path.join(dest, "*_" + glob.escape(name))))
        if previous and open(previous[-1], "rb").read() == data:
            continue
        os.makedirs(dest, exist_ok=True)
        stem = os.path.join(dest, f"{datetime.datetime.fromtimestamp(mtime):%Y-%m-%d_%H%M%S}")
        out, k = f"{stem}_{name}", 1
        while os.path.exists(out):
            k += 1
            out = f"{stem}-{k}_{name}"
        write_verified(out, data)
        written.append(out)
    return written


def looks_like_image(path):
    """A flash image as the game writes it: full size, with at least one signed sector. A synced
    file that isn't one may be My Boy!'s own format (undocumented), so it can't be judged."""
    try:
        buf = open(path, "rb").read()
    except OSError:
        return False
    return len(buf) >= FLASH_SIZE and any(
        struct.unpack_from("<I", buf, i * savefile.SECTOR_SIZE + savefile.SIGNATURE_OFF)[0] == savefile.SECTOR_SIGNATURE
        for i in range(savefile.NUM_SECTORS_PER_SLOT * savefile.NUM_SAVE_SLOTS))


def phone_saves(folder, index, synced):
    """[(path, verdict, why)] for My Boy!'s synced saves and for saves/*.sav and *.srm (uploaded by
    hand; .srm is RetroArch's and Lemuroid's), newest first, judged for this build's layout. All
    are the 128 KB flash image, maybe with a clock block after it.
    A save this build can't read is tried against the older save lines published (their layouts
    are in the index): verdict 'older', with the play file that reads it. A synced file that
    isn't a flash image at all is 'unknown' (My Boy!'s sync format isn't documented); one that is,
    but fails its checks, is 'stale' like any other: a damaged save must say so."""
    rec = save_layout.recorded()
    older = {}
    for e in index:
        if e.get("layout") and e["layout"]["SAVE_LAYOUT_STAMP"] != rec["SAVE_LAYOUT_STAMP"]:
            older[e["layout"]["SAVE_LAYOUT_STAMP"]] = e
    found = []
    for p in synced + [p for ext in ("*.sav", "*.srm") for p in glob.glob(os.path.join(folder, "saves", ext))]:
        try:
            found.append((os.path.getmtime(p), p))
        except OSError:
            continue
    out = []
    for _, p in sorted(found, reverse=True):
        if p in synced and not looks_like_image(p):
            out.append((p, "unknown", "not a raw flash image: My Boy!'s sync may store saves another way"))
            continue
        verdict, why = savefile.check(p, rec)
        if verdict == "stale":
            for e in older.values():
                if savefile.check(p, e["layout"])[0] in ("ok", "warn"):
                    verdict, why = "older", (f"a save line {e['save_layout_version']} save: it plays in "
                                             f"{e['play']}, not in this build")
                    break
        out.append((p, verdict, why))
    return out


def shown(p, folder):
    """A save's path as Tom sees it in Drive: relative to My Drive."""
    return os.path.relpath(p, os.path.dirname(folder)).replace("\\", "/")


# ---------------------------------------------------------------- the README on Drive
def has_commit(commit):
    return subprocess.run(["git", "-C", REPO, "cat-file", "-e", f"{commit}^{{commit}}"],
                          capture_output=True).returncode == 0


def changes_since(prev_commit, upto="HEAD"):
    if prev_commit and subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", prev_commit,
                                       upto], capture_output=True).returncode == 0:
        log = git("log", "--first-parent", "--format=%s", f"{prev_commit}..{upto}")
        return log.splitlines()[:30], False
    return git("log", "--first-parent", "--format=%s", "-6", upto).splitlines(), True


def refresh_readme(folder, index, saves):
    """Rewrite README.txt for the latest build if its text changed (new instructions, save checks,
    or the direct link once Drive has uploaded the play file); the ROM and the archive stay as
    they are. Returns (rewritten, link)."""
    entry = index[-1]
    link = download_link(folder, entry["play"])
    if not has_commit(entry["commit"]):
        print(f"README.txt kept: commit {entry['short']} isn't in this checkout, so its change list can't be rebuilt")
        return False, link
    prev = index[-2]["commit"] if len(index) > 1 else None
    text = readme(entry, index, saves, *changes_since(prev, entry["commit"]), folder, link).encode("utf-8")
    path = os.path.join(folder, "README.txt")
    if os.path.exists(path) and open(path, "rb").read() == text:
        return False, link
    write_verified(path, text)
    return True, link


def finish(folder, index, saves, files, since, wait):
    """Wait for Drive to upload `files` ({name: (folder name, size)}), then refresh README.txt once
    (with the direct link if the play file is up). Returns (state, link)."""
    if not drivefs_running():
        state = "waiting for Google Drive for Desktop to start"
    else:
        state = wait_uploaded(files, since, wait) if wait else "not waited for"
    rewritten, link = refresh_readme(folder, index, saves)
    if rewritten:
        print("README.txt written" + (" with the direct download link" if link else ""))
    return state, link


def readme(entry, index, saves, changes, first, folder, link=None):
    play, n = entry["play"], entry["save_layout_version"]
    size = f"{entry['play_size'] / 2**20:.0f} MB" if entry.get("play_size") else ""
    prev = index[-2] if len(index) > 1 else None
    L = ["PokeMaritimes: private playtest builds",
         "======================================",
         "For Tom's own play-testing only. Keep this folder private: don't share it or a link to it.",
         "The ROM is built from the Pokemon Emerald decompilation and contains Nintendo / Game Freak",
         "material, so it must never be posted anywhere public.",
         "",
         f"PLAY THIS: {play}  {size}",
         f"  direct download (Chrome on your phone, signed in to this Google account):",
         f"  {link or '(appears here once Google Drive has finished uploading the file)'}",
         f"  build       {entry['version']}  ({entry['branch']}, commit {entry['short']}: {entry['subject']})",
         f"  published   {entry['published']}",
         f"  verified    {entry['verified']}",
         f"  save line   {n}   (builds with the same number read the same saves)",
         f"  sha256      {entry['sha256']}",
         ""]
    if prev and prev["save_layout_version"] != n:
        L += [f"*** SAVE BREAK: this build can't read saves from save line {prev['save_layout_version']}. ***",
              f"    Keep your old {prev['play']} if you want to finish that game: its save stays with it.",
              f"    {play} starts with no save: choose NEW GAME.",
              ""]
    elif prev:
        L += [f"SAVES CARRY OVER from the previous build ({prev['version']}): same save line, same file name.", ""]
    L += ["Recent changes:" if first else "What's new since the last phone build:"]
    L += [f"  - {c}" for c in changes] or ["  - (no new commits: a rebuild of the same code)"]
    L += [""]
    if saves:
        L += ["Phone saves found, checked against this build:"]
        for p, verdict, why in saves[:10]:
            when = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            label = {"ok": "loads", "warn": "loads (one slot damaged)", "none": "empty",
                     "older": "older save line", "unknown": "can't check"}.get(verdict, "WON'T LOAD")
            L += [f"  - {shown(p, folder)} ({when:%Y-%m-%d %H:%M}): {label} ({why})"]
        L += [""]
    L += ["On the phone: My Boy!",
          "---------------------",
          "Setup, once:",
          "  a. My Boy! > Settings > Misc: turn OFF 'Quick load on start'. It reloads a save state",
          "     when a game opens; after an update that state is the old build's memory, and saving",
          "     in-game on top of it can write the old build's data into your save. Use the game's",
          "     own save (START > SAVE); don't rely on save states for this game.",
          "  b. In My Boy!'s settings, turn ON 'Sync with Google Drive' (this Google account). My Boy!",
          "     keeps saves in a private folder you can't reach; sync copies them into the MyBoy folder",
          "     of this Drive, and from there every phone build backs them up (saves/myboy/ here,",
          "     dated) and is tested against your newest save before it's published.",
          "  c. Files app: make a folder for the game, Download/PokeMaritimes. In My Boy! choose",
          "     'Add game folder' and pick it.",
          "",
          "Installing a build (the first time, and every update):",
          "  1. If you're playing: save in-game (START > SAVE), then My Boy! MENU > Close.",
          f"  2. Download {play}, either way:",
          f"     - Google Drive app > {FOLDER_NAME} > the three dots next to it > Download.",
          "       No Download in that menu? Google: 'When Data Saver is turned on in your network",
          "       settings, the download option isn't available.' Turn Data Saver off (search",
          "       Android's Settings for 'Data Saver'), or use the next way.",
          "     - Open the direct download link at the top of this file in Chrome. It downloads",
          "       straight to Download/. It's private: without your Google sign-in it shows",
          "       Google's sign-in page, not the file.",
          f"  3. Files app > Downloads: move {play} into Download/PokeMaritimes. On an update, if",
          "     it asks, choose Replace. Don't unzip it: My Boy! plays the ZIP as it is.",
          f"     The name must stay exactly {play}: My Boy! finds your save by the ROM's file",
          f"     name, so a copy named '... (1){os.path.splitext(play)[1]}' would open with no save. If you see '(1)', delete",
          "     the old file and rename the new one.",
          "  4. Open it from My Boy!'s game list (refresh the list if it isn't there).",
          f"     If a loose {entry.get('rom', play)} is in the list too, that's this same save line as a",
          "     .gba from before the ZIPs; delete it once the ZIP plays, so there's one entry per",
          "     save line. (A ROM with another save number is another save line: keep it.)",
          "     The first time: NEW GAME. An update on the same save line: CONTINUE.",
          "     If CONTINUE is missing after an update, don't save: MENU > Close and tell Claude.",
          "     Your save is still there; the new file just isn't being matched to it.",
          "  5. The first time only: save in the game, MENU > Close, open it again and check that",
          "     CONTINUE is there. That proves saving works on your phone.",
          "",
          "When the save line changes (a SAVE BREAK: ..._save2.gba becomes ..._save3.gba):",
          "  The new build can't read the older saves, so it has a new file name and its own fresh",
          "  save in My Boy!. Nothing is overwritten: the old ROM and its save stay in your game list.",
          "  Keep the old one to finish that game, or delete just the old ROM when you're done with it.",
          "",
          "If something goes wrong with a save, stop playing that build (don't save again) and tell",
          "Claude: saves/myboy/ keeps a dated copy of each version of your save that sync uploaded.",
          "If the game ever says the internal battery has run dry, that's the clock, not your save;",
          "report it.",
          "",
          "Fallback: Pizza Boy GBA Pro",
          "  The same file and the same rule: keep the name exactly as published (if it won't open",
          "  the ZIP, extract it in the Files app and play the .gba inside). Its saves are its",
          "  own, separate from My Boy!'s: a game saved in one doesn't appear in the other. Turn off",
          "  any automatic loading of save states there too. To back up a Pizza Boy save, export it",
          "  from Pizza Boy and upload the .sav into saves/ here (Drive app: + > Upload).",
          "",
          "Older builds: builds/ keeps every phone build, zipped, with its build.txt. Unzip one",
          "and play the .gba inside; it's named for its save line, so a save with the same number",
          "loads.",
          "",
          "This is a development build: holding R and pressing START in the overworld opens the",
          "debug menu. Leave it alone for normal play.",
          "",
          "Build history (newest first):"]
    for e in reversed(index[-HISTORY_IN_README:]):
        L += [f"  {e['version']}  save line {e['save_layout_version']}  {e['subject']}"]
    return "\r\n".join(L) + "\r\n"


# ---------------------------------------------------------------- commands
def status():
    folder = drive_folder()
    print(f"Drive folder: {folder}{'' if os.path.isdir(folder) else '  (not created yet)'}")
    print(f"Google Drive for Desktop: {'running' if drivefs_running() else 'NOT RUNNING (nothing syncs)'}")
    index = load_index(folder) if os.path.isdir(folder) else []
    for e in reversed(index[-HISTORY_IN_README:]):
        print(f"  {e['version']}  save line {e['save_layout_version']}  {e['subject']}")
    if index:
        e = index[-1]
        files = {e["play"]: (os.path.basename(folder), e.get("play_size", e["size"]))}
        print(f"latest: {e['play']} ({e['version']}), "
              f"{'uploaded' if (uploaded(files, 0) or set()) >= set(files) else 'not confirmed uploaded'}")
        rewritten, link = refresh_readme(folder, index, phone_saves(folder, index, synced_saves(folder)[0]))
        print(f"direct download: {link or '(not uploaded yet)'}"
              + ("  (README.txt updated)" if rewritten else ""))
    rec = save_layout.recorded()
    print(f"this checkout's save line: {rec['SAVE_LAYOUT_VERSION']}")
    synced, ignored = synced_saves(folder)
    print(f"My Boy! synced saves (My Drive/MyBoy): {len(synced) or 'none (is Sync with Google Drive on?)'}")
    for p in ignored:
        print(f"  ignored (not a save image by name or size): {shown(p, folder)} ({os.path.getsize(p)} bytes)")
    for p, verdict, why in phone_saves(folder, index, synced) if os.path.isdir(folder) else []:
        print(f"  {shown(p, folder)}: {verdict}: {why}")
    return 0


def publish(a):
    ident = build_identity(a.allow_dirty or a.check)     # --check publishes nothing to name
    if ident["branch"] != "develop":
        print(f"note: on branch {ident['branch']}, not develop")
    import fastbuild
    if fastbuild.main([]) != 0:
        print("The build failed: nothing published.")
        return 1
    with open(ROM_SRC, "rb") as f:
        rom = f.read()
    problems = check_header(rom)
    if problems:
        print("The ROM header is wrong: " + "; ".join(problems))
        return 1
    rec = save_layout.recorded()
    n = rec["SAVE_LAYOUT_VERSION"]
    digest = sha256(rom)
    print(f"ROM {ident['version']}: {len(rom) / 2**20:.0f} MiB, save line {n}, sha256 {digest[:16]}...")

    if a.check:     # read the phone saves if Drive is there; write nothing
        try:
            folder = drive_folder()
        except SystemExit:
            folder = None
    else:
        folder = drive_folder()
        for sub in ("builds", "saves"):
            os.makedirs(os.path.join(folder, sub), exist_ok=True)
    synced = synced_saves(folder)[0] if folder else []
    if not a.check:
        for p in back_up_synced(folder, synced):
            print(f"backed up My Boy!'s save: {shown(p, folder)}")
    index = load_index(folder) if folder and os.path.isdir(folder) else []
    saves = phone_saves(folder, index, synced) if folder and os.path.isdir(folder) else []
    # only a clean save is booted: one with a damaged slot shows a message first (the game then
    # loads the other slot), and booting through that would prove little
    loadable = next((p for p, verdict, _ in saves if verdict == "ok"), None)
    for p, verdict, why in saves:
        print(f"phone save {shown(p, folder)}: {verdict}: {why}")
    rom_name, play = f"{GAME}_save{n}.gba", f"{GAME}_save{n}.zip"
    package = play_zip(rom_name, rom, ident["date"])
    print("Verifying in mGBA:")
    ok, lines = verify(rom, loadable, a.full, package)
    if not ok:
        print("Verification FAILED: nothing published. Screenshots: dev/out/mobile/")
        return 1
    if a.check:
        print("Verified. --check: nothing published.")
        return 0

    play_path = os.path.join(folder, play)
    last = index[-1] if index else None
    same_rom = bool(last) and last["sha256"] == digest and archived(folder, [last], digest)
    if same_rom and last["play"] == play and zip_rom_digest(play_path) == digest:
        print(f"This ROM is already the phone build ({last['version']}): nothing to upload.")
        state, link = finish(folder, index, saves, {play: (os.path.basename(folder), len(package))}, 0, a.wait)
        print(f"Google Drive: {state}\ndirect download: {link or '(not uploaded yet)'}")
        return 0
    if same_rom:
        # the same ROM, archived already, published as another play file (the .gba before the
        # ZIPs): only the play file changes; the build keeps its entry and archive
        print(f"Repackaging {last['version']} as {play} (the ROM and its archive stay as they are)")
        since = time.time()
        write_verified(play_path, package)
        if zip_rom_digest(play_path) != digest:
            sys.exit("the play ZIP's ROM doesn't match after writing it")
        last.update(play=play, rom=rom_name, play_size=len(package))
        write_verified(os.path.join(folder, "builds", "index.json"),
                       (json.dumps(index, indent=1) + "\n").encode("utf-8"))
        retire_old_play_files(folder, index, play)
        state, link = finish(folder, index, saves, {play: (os.path.basename(folder), len(package))}, since, a.wait)
        print(f"\nSaves carry over: the same ROM, save line {n}"
              f"\nPlay file: {play} ({len(package) / 2**20:.0f} MB)\n  Google Drive: {state}"
              f"\n  direct download: {link or '(once uploaded: run dev/mobile.py --status)'}")
        return 0

    if not drivefs_running():
        print("warning: Google Drive for Desktop isn't running; the files will upload when it starts")
    since = time.time()
    verified = "boots (as the ZIP too), starts a new game, saves and CONTINUEs in mGBA"
    if loadable:
        verified += f"; your phone save {shown(loadable, folder)} CONTINUEs"
    if a.full:
        verified += "; the slice playthrough passes"
    entry = {**{k: ident[k] for k in ("version", "commit", "short", "date", "subject", "branch", "dirty")},
             "published": f"{datetime.datetime.now():%Y-%m-%d %H:%M}", "verified": verified,
             "sha256": digest, "size": len(rom), "save_layout_version": n,
             "save_layout_stamp": rec["SAVE_LAYOUT_STAMP"], "layout": rec, "play": play,
             "rom": rom_name, "play_size": len(package),
             "archive": f"{GAME}_{ident['version']}_save{n}.zip"}
    if any(e["archive"] == entry["archive"] for e in index):      # same commit, other bytes
        entry["archive"] = entry["archive"][:-4] + f"_{digest[:8]}.zip"
    build_txt = (f"{GAME} {entry['version']}\r\ncommit {entry['commit']} ({entry['branch']})\r\n"
                 f"{entry['subject']}\r\nsave line {n} (layout stamp {entry['save_layout_stamp']:#06x})\r\n"
                 f"sha256 {digest}\r\nverified: {verified}\r\n")

    # 1. the archive, first: a later step may remove an older play file only once it's archived
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(rom_name, rom)
        z.writestr("build.txt", build_txt)
    write_verified(os.path.join(folder, "builds", entry["archive"]), buf.getvalue())
    with zipfile.ZipFile(os.path.join(folder, "builds", entry["archive"])) as z:
        if sha256(z.read(rom_name)) != digest:
            sys.exit("the archive's ROM doesn't match after writing it")
    # 2. the play file: the ZIP that was booted in the verification, byte for byte
    write_verified(play_path, package)
    if zip_rom_digest(play_path) != digest:
        sys.exit("the play ZIP's ROM doesn't match after writing it")
    # 3. the index and README
    prev = index[-1] if index else None
    index.append(entry)
    write_verified(os.path.join(folder, "builds", "index.json"),
                   (json.dumps(index, indent=1) + "\n").encode("utf-8"))
    # (README.txt is written by finish(), once, after the upload)
    # 4. any other play file leaves the top level once an archive holds its ROM
    retire_old_play_files(folder, index, play)

    if prev and prev["save_layout_version"] != n:
        print(f"SAVE BREAK: save line {prev['save_layout_version']} -> {n}: the phone build has a new name, "
              f"{play}, and starts with a fresh save")
    elif prev:
        print(f"Saves carry over: same save line ({n}) and file name as the previous build ({prev['version']})")
    else:
        print(f"The first phone build on save line {n}")
    files = {play: (os.path.basename(folder), len(package)), entry["archive"]: ("builds", len(buf.getvalue()))}
    state, link = finish(folder, index, saves, files, since, a.wait)
    print(f"\nPublished {entry['version']} to {folder}\n  play file: {play} ({len(package) / 2**20:.0f} MB)"
          f"\n  archive:   builds/{entry['archive']}\n  Google Drive: {state}"
          f"\n  direct download: {link or '(once uploaded: run dev/mobile.py --status)'}")
    if state == "syncing":
        print("  still uploading: it finishes in the background while Drive for Desktop runs")
    elif state == "unknown":
        print("  couldn't read Drive's sync state: check the Drive icon in the taskbar")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="build and verify; publish nothing")
    ap.add_argument("--status", action="store_true",
                    help="report what's on Drive, refreshing README.txt's link; build nothing")
    ap.add_argument("--full", action="store_true", help="also run tests/playthrough_slice1.py")
    ap.add_argument("--allow-dirty", action="store_true", help="allow uncommitted changes")
    ap.add_argument("--wait", type=int, default=600, metavar="S",
                    help="seconds to wait for Drive to finish uploading (0: don't wait; default 600)")
    a = ap.parse_args()
    return status() if a.status else publish(a)


if __name__ == "__main__":
    sys.exit(main())
