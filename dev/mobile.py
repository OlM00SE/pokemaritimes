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

  PokeMaritimes_save<N>.gba   the build to play. N is the save layout version: every build with
                              the same N reads the same saves, so replacing the file keeps the
                              phone's save (emulators find the save by the ROM's file name). A
                              save break changes N, so the new build gets a fresh save and the
                              old save stays with the old file.
  README.txt                  this build, what changed, save compatibility, phone instructions
  builds/                     every build published, zipped: PokeMaritimes_<date>_<commit>_save<N>.zip
                              (the ROM, named for its save line, and build.txt); index.json lists them
  saves/                      phone save backups, uploaded from the phone; each publish checks them

"Verified": the exact bytes published boot in mGBA (the dev build the tests use), start a new game,
save, and CONTINUE to the same spot; the newest phone save in saves/ that this build can read
CONTINUEs to the overworld; with --full, the slice playthrough passes too. Nothing is published
from a tree with uncommitted changes unless --allow-dirty says so: a build is named by its commit.
"""
import argparse, ctypes, datetime, glob, hashlib, io, json, os, shutil, sqlite3, string, subprocess
import sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
import save_layout, savefile

FOLDER_NAME = "PokeMaritimes playtest"
GAME = "PokeMaritimes"
OUT = os.path.join(REPO, "dev", "out", "mobile")
ROM_SRC = os.path.join(REPO, "pokeemerald.gba")
HISTORY_IN_README = 8


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


def verify(rom_bytes, phone_save=None, full=False):
    """Boot the exact bytes to publish. Returns (ok, [lines]). The ROM is copied to dev/out/mobile
    with its .map (the bridge reads symbols from it); nothing touches a real save."""
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
    if ok and phone_save:
        name = os.path.basename(phone_save)
        _fresh(sav)
        shutil.copyfile(phone_save, sav)
        with Emu(rom, extra_args=UNTHROTTLED) as e:
            if step(e.boot_to_overworld(), f"the phone save {name} CONTINUEs to the overworld"):
                e.wait_for_control()
                loc = e.player()
                lines[-1] += f" ({e.map_name(loc)} {loc[2:]})"
                e.shot(os.path.join(OUT, "check_phone_save.png"))
        _fresh(sav)     # a copy of Tom's save: don't leave it lying in dev/out
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
    if os.environ.get("MARITIMES_DRIVE_DIR"):
        return os.environ["MARITIMES_DRIVE_DIR"]
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


def uploaded(files, since):
    """Which of {name: (folder name, size)} Google Drive for Desktop has finished uploading, judged
    from its local metadata database (undocumented, so this is best effort; None if it can't be
    read). Measured on Drive for Desktop 133 with a 32 MB file, new and overwritten: while content
    is uploading, the item has a 'local-content-size' property and a pending operation names it,
    and its modified_date (the cloud's) stays as it was; once uploaded both marks are gone and
    modified_date moves. So a file counts as uploaded when its item, in a folder of that name, has
    a cloud id rather than a local one, the size, a modified_date since `since` (epoch seconds),
    neither mark, and isn't trashed."""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS")
    dbs = glob.glob(os.path.join(base, "*", "metadata_sqlite_db"))
    if not dbs:
        return None
    done = set()
    try:
        for db in dbs:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                # a copy with its WAL: reading the live file could block Drive's own writes
                for suffix in ("", "-wal", "-shm"):
                    if os.path.exists(db + suffix):
                        shutil.copyfile(db + suffix, os.path.join(tmp, "m" + suffix))
                con = sqlite3.connect(os.path.join(tmp, "m"))
                try:
                    pending = [r[0] or b"" for r in con.execute("SELECT CAST(proto AS BLOB) FROM operations")]
                    for name, (parent, size) in files.items():
                        row = con.execute(
                            "SELECT 1 FROM items i JOIN stable_parents sp ON sp.item_stable_id = i.stable_id"
                            " JOIN items f ON f.stable_id = sp.parent_stable_id"
                            " WHERE i.local_title = ? AND f.local_title = ? AND i.file_size = ?"
                            " AND i.trashed = 0 AND i.is_tombstone = 0 AND i.modified_date >= ?"
                            " AND i.id NOT LIKE 'local%'"
                            " AND i.stable_id NOT IN (SELECT stable_id FROM local_stable_ids)"
                            " AND NOT EXISTS (SELECT 1 FROM item_properties ip WHERE"
                            " ip.item_stable_id = i.stable_id AND ip.key = 'local-content-size')",
                            (name, parent, size, int((since - 5) * 1000))).fetchone()
                        if row and not any(name.encode() in op for op in pending):
                            done.add(name)
                finally:
                    con.close()
    except (sqlite3.Error, OSError):
        return None
    return done


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
                    if sha256(z.read(e["play"])) == digest:
                        return True
            except (zipfile.BadZipFile, KeyError, OSError):
                pass
    return False


def load_index(folder):
    p = os.path.join(folder, "builds", "index.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def phone_saves(folder, index):
    """[(path, verdict, why)] for saves/*.sav and *.srm (RetroArch, Lemuroid), newest first, judged
    for this build's layout. Both are the 128 KB flash image, maybe with a clock block after it.
    A save this build can't read is tried against the older save lines published (their layouts
    are in the index): verdict 'older', with the play file that reads it."""
    rec = save_layout.recorded()
    older = {}
    for e in index:
        if e.get("layout") and e["layout"]["SAVE_LAYOUT_STAMP"] != rec["SAVE_LAYOUT_STAMP"]:
            older[e["layout"]["SAVE_LAYOUT_STAMP"]] = e
    out = []
    found = [p for ext in ("*.sav", "*.srm") for p in glob.glob(os.path.join(folder, "saves", ext))]
    for p in sorted(found, key=os.path.getmtime, reverse=True):
        verdict, why = savefile.check(p, rec)
        if verdict == "stale":
            for e in older.values():
                if savefile.check(p, e["layout"])[0] in ("ok", "warn"):
                    verdict, why = "older", (f"a save line {e['save_layout_version']} save: it plays in "
                                             f"{e['play']}, not in this build")
                    break
        out.append((p, verdict, why))
    return out


# ---------------------------------------------------------------- the README on Drive
def changes_since(prev_commit):
    if prev_commit and subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", prev_commit,
                                       "HEAD"], capture_output=True).returncode == 0:
        log = git("log", "--first-parent", "--format=%s", f"{prev_commit}..HEAD")
        return log.splitlines()[:30], False
    return git("log", "--first-parent", "--format=%s", "-6").splitlines(), True


def readme(entry, index, saves, changes, first):
    play, n = entry["play"], entry["save_layout_version"]
    prev = index[-2] if len(index) > 1 else None
    L = ["PokeMaritimes: private playtest builds",
         "======================================",
         "For Tom's own play-testing only. Keep this folder private: don't share it or a link to it.",
         "The ROM is built from the Pokemon Emerald decompilation and contains Nintendo / Game Freak",
         "material, so it must never be posted anywhere public.",
         "",
         f"PLAY THIS: {play}",
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
        L += [f"Saves carry over from the previous build ({prev['version']}): same save line.", ""]
    L += ["Recent changes:" if first else "What's new since the last phone build:"]
    L += [f"  - {c}" for c in changes] or ["  - (no new commits: a rebuild of the same code)"]
    L += [""]
    if saves:
        L += ["Phone saves in saves/, checked against this build:"]
        for p, verdict, why in saves[:5]:
            when = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            label = {"ok": "loads", "warn": "loads (one slot damaged)", "none": "empty",
                     "older": "older save line"}.get(verdict, "WON'T LOAD")
            L += [f"  - {os.path.basename(p)} ({when:%Y-%m-%d %H:%M}): {label} ({why})"]
        L += [""]
    L += ["On the phone",
          "------------",
          "First time:",
          f"  1. In the Google Drive app, open '{FOLDER_NAME}', tap the three dots next to",
          f"     {play}, and choose Download.",
          "  2. In the Files app, move it from Download to the folder your emulator reads ROMs from.",
          "  3. Open it in the emulator and start a new game.",
          "",
          "Updating to a newer build (same save line):",
          "  1. Save in-game (START > SAVE), then close the emulator. Don't carry save states",
          "     across builds: a state is a snapshot of the old build's memory and can glitch or",
          "     crash the new one. The in-game save is the one that carries over.",
          f"  2. Download the new {play} and move it over the old one (choose Replace).",
          "     If Android saved it as '... (1).gba', remove the ' (1)' when you rename or move it:",
          "     the emulator finds your save by the ROM's file name.",
          "  3. Open it and choose CONTINUE.",
          "",
          "When the save line changes (a SAVE BREAK, e.g. ..._save2.gba becomes ..._save3.gba):",
          "  the new build can't read the older saves, so it has a new file name and a fresh save.",
          "  Nothing to delete: the old ROM and its save stay as they were.",
          "",
          "Backing up your save (worth doing before each update):",
          "  Upload the emulator's save file (the ROM's name with .sav; .srm in RetroArch and",
          "  Lemuroid) into saves/ here",
          "  (Drive app: + > Upload). The next phone build is tested against the newest one, and",
          "  this file says whether each loads.",
          "",
          "Older builds: builds/ keeps every phone build, zipped, with its build.txt. Unzip one to",
          "play it; the ROM inside is named for its save line, so a save with the same number loads.",
          "",
          "Emulator settings, only if it asks: save type Flash 128K (1 Mbit), real-time clock on.",
          "Most emulators set both from the game code (BPEE).",
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
        files = {e["play"]: (os.path.basename(folder), e["size"])}
        print(f"latest: {e['play']} ({e['version']}), "
              f"{'uploaded' if (uploaded(files, 0) or set()) >= set(files) else 'not confirmed uploaded'}")
    rec = save_layout.recorded()
    print(f"this checkout's save line: {rec['SAVE_LAYOUT_VERSION']}")
    for p, verdict, why in phone_saves(folder, index) if os.path.isdir(folder) else []:
        print(f"  phone save {os.path.basename(p)}: {verdict}: {why}")
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

    folder = None if a.check else drive_folder()
    index = load_index(folder) if folder and os.path.isdir(folder) else []
    saves = phone_saves(folder, index) if folder and os.path.isdir(folder) else []
    # only a clean save is booted: one with a damaged slot shows a message first (the game then
    # loads the other slot), and booting through that would prove little
    loadable = next((p for p, verdict, _ in saves if verdict == "ok"), None)
    for p, verdict, why in saves:
        print(f"phone save {os.path.basename(p)}: {verdict}: {why}")
    print("Verifying in mGBA:")
    ok, lines = verify(rom, loadable, a.full)
    if not ok:
        print("Verification FAILED: nothing published. Screenshots: dev/out/mobile/")
        return 1
    if a.check:
        print("Verified. --check: nothing published.")
        return 0

    play = f"{GAME}_save{n}.gba"
    play_path = os.path.join(folder, play)
    if index and index[-1]["sha256"] == digest and os.path.exists(play_path) \
            and sha256(open(play_path, "rb").read()) == digest:
        print(f"This ROM is already the phone build ({index[-1]['version']}): nothing to upload.")
        if a.wait and drivefs_running():
            print(f"Google Drive: {wait_uploaded({play: (os.path.basename(folder), len(rom))}, 0, a.wait)}")
        return 0

    if not drivefs_running():
        print("warning: Google Drive for Desktop isn't running; the files will upload when it starts")
    for sub in ("builds", "saves"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    since = time.time()
    verified = "boots, starts a new game, saves and CONTINUEs in mGBA"
    if loadable:
        verified += f"; phone save {os.path.basename(loadable)} CONTINUEs"
    if a.full:
        verified += "; the slice playthrough passes"
    entry = {**{k: ident[k] for k in ("version", "commit", "short", "date", "subject", "branch", "dirty")},
             "published": f"{datetime.datetime.now():%Y-%m-%d %H:%M}", "verified": verified,
             "sha256": digest, "size": len(rom), "save_layout_version": n,
             "save_layout_stamp": rec["SAVE_LAYOUT_STAMP"], "layout": rec, "play": play,
             "archive": f"{GAME}_{ident['version']}_save{n}.zip"}
    if any(e["archive"] == entry["archive"] for e in index):      # same commit, other bytes
        entry["archive"] = entry["archive"][:-4] + f"_{digest[:8]}.zip"
    build_txt = (f"{GAME} {entry['version']}\r\ncommit {entry['commit']} ({entry['branch']})\r\n"
                 f"{entry['subject']}\r\nsave line {n} (layout stamp {entry['save_layout_stamp']:#06x})\r\n"
                 f"sha256 {digest}\r\nverified: {verified}\r\n")

    # 1. the archive, first: a later step may remove an older play file only once it's archived
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(play, rom)
        z.writestr("build.txt", build_txt)
    write_verified(os.path.join(folder, "builds", entry["archive"]), buf.getvalue())
    with zipfile.ZipFile(os.path.join(folder, "builds", entry["archive"])) as z:
        if sha256(z.read(play)) != digest:
            sys.exit("the archive's ROM doesn't match after writing it")
    # 2. the play file
    write_verified(play_path, rom)
    # 3. the index and README
    prev = index[-1] if index else None
    index.append(entry)
    write_verified(os.path.join(folder, "builds", "index.json"),
                   (json.dumps(index, indent=1) + "\n").encode("utf-8"))
    changes, first = changes_since(prev["commit"] if prev else None)
    write_verified(os.path.join(folder, "README.txt"),
                   readme(entry, index, saves, changes, first).encode("utf-8"))
    # 4. a play file from an older save line leaves the top level once its archive holds it
    for old in glob.glob(os.path.join(folder, f"{GAME}_save*.gba")):
        if os.path.basename(old) == play:
            continue
        if archived(folder, index, sha256(open(old, "rb").read())):
            os.remove(old)      # on the Drive volume this goes to Drive's trash
            print(f"removed {os.path.basename(old)} from the top level (builds/ holds it)")
        else:
            print(f"kept {os.path.basename(old)}: no archive in builds/ holds it")

    if prev and prev["save_layout_version"] != n:
        print(f"SAVE BREAK: save line {prev['save_layout_version']} -> {n}: the phone build has a new name, "
              f"{play}, and starts with a fresh save")
    files = {play: (os.path.basename(folder), len(rom)), entry["archive"]: ("builds", len(buf.getvalue()))}
    if not drivefs_running():
        state = "waiting for Google Drive for Desktop to start"
    else:
        state = wait_uploaded(files, since, a.wait) if a.wait else "not waited for"
    print(f"\nPublished {entry['version']} to {folder}\n  play file: {play}\n  archive:   builds/{entry['archive']}"
          f"\n  Google Drive: {state}")
    if state == "syncing":
        print("  still uploading: it finishes in the background while Drive for Desktop runs")
    elif state == "unknown":
        print("  couldn't read Drive's sync state: check the Drive icon in the taskbar")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="build and verify; publish nothing")
    ap.add_argument("--status", action="store_true", help="report what's on Drive; build nothing")
    ap.add_argument("--full", action="store_true", help="also run tests/playthrough_slice1.py")
    ap.add_argument("--allow-dirty", action="store_true", help="allow uncommitted changes")
    ap.add_argument("--wait", type=int, default=600, metavar="S",
                    help="seconds to wait for Drive to finish uploading (0: don't wait; default 600)")
    a = ap.parse_args()
    return status() if a.status else publish(a)


if __name__ == "__main__":
    sys.exit(main())
