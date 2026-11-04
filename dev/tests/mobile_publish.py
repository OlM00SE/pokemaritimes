"""dev/mobile.py publishes into a scratch folder (never the real Drive) as the phone needs it.

  python dev/tests/mobile_publish.py

Uses the ROM already built (run dev/fastbuild.py first) and the real mGBA verification:
  1. a first publish: the play file is the ROM byte for byte, named for its save line; the archive
     holds the same ROM under that name plus build.txt; index.json and README.txt describe it;
  2. a save break: with a previous build on another save line in the index, the README says SAVE
     BREAK, the old play file leaves the top level (an archive in builds/ holds it), and a ROM
     the index names but no archive holds is kept; the phone save in saves/ (the game's own, from
     step 1) is reported as loading and CONTINUEd in mGBA; the same save restamped for the older
     line is reported as that line's; a broken one is reported as WON'T LOAD; neither is booted;
     My Boy!'s Google Drive sync folder (MyBoy/, beside the publish folder) is read, never
     written: its PokeMaritimes saves are backed up into saves/myboy/, the newest is the one
     booted, another game's save and a save state are ignored, a file that isn't a flash image
     is "can't check", and a damaged flash image is WON'T LOAD;
  3. publishing the same ROM again uploads no ROM, refreshes a README whose text changed, and
     backs up no save twice; a synced save that changes (same timestamp) gets a second backup
     beside the first, which stays as it was.
"""
import argparse, glob, hashlib, json, os, shutil, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fastbuild, mobile, save_layout, savefile

failed = 0


def check(ok, what):
    global failed
    print(f"  {'PASS' if ok else 'FAIL'}: {what}")
    failed += not ok


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    fastbuild.main = lambda argv: 0          # use the ROM already built
    args = argparse.Namespace(check=False, full=False, allow_dirty=True, wait=0)
    rom = open(mobile.ROM_SRC, "rb").read()
    n = save_layout.recorded()["SAVE_LAYOUT_VERSION"]
    play = f"PokeMaritimes_save{n}.gba"
    real_verify, seen = mobile.verify, []

    def recording_verify(rom_bytes, phone_save=None, full=False):
        seen.append(phone_save)
        return real_verify(rom_bytes, phone_save, full)
    mobile.verify = recording_verify

    tmp = tempfile.mkdtemp(prefix="maritimes_mobile_")
    folder = os.path.join(tmp, "PokeMaritimes playtest")
    os.environ["MARITIMES_DRIVE_DIR"] = folder
    try:
        print("1. first publish")
        check(mobile.publish(args) == 0, "publish succeeds")
        p = os.path.join(folder, play)
        check(os.path.exists(p) and open(p, "rb").read() == rom, f"{play} is the ROM byte for byte")
        index = json.load(open(os.path.join(folder, "builds", "index.json"), encoding="utf-8"))
        check(len(index) == 1 and index[0]["sha256"] == sha(rom) and index[0]["save_layout_version"] == n,
              "index.json records the build, its hash and save line")
        with zipfile.ZipFile(os.path.join(folder, "builds", index[0]["archive"])) as z:
            check(sorted(z.namelist()) == sorted([play, "build.txt"]) and sha(z.read(play)) == sha(rom),
                  f"the archive {index[0]['archive']} holds the same ROM as {play}, and build.txt")
            check(sha(rom) in z.read("build.txt").decode(), "build.txt carries the hash")
        text = open(os.path.join(folder, "README.txt"), encoding="utf-8").read()
        check(f"PLAY THIS: {play}" in text and "*** SAVE BREAK" not in text, "README: what to play, no save break")
        check(os.path.isdir(os.path.join(folder, "saves")), "saves/ exists for phone backups")
        check(seen == [None], "no phone save yet, so none was booted")
        check(not glob.glob(os.path.join(folder, "**", "*.partial"), recursive=True), "no partial files left")

        print("2. a save break, with phone saves")
        game_save = os.path.join(mobile.OUT, "check.sav")      # the verification's own save
        shutil.copyfile(game_save, os.path.join(folder, "saves", "phone.sav"))
        with open(os.path.join(folder, "saves", "broken.sav"), "wb") as f:
            f.write(b"\0" * 1000)
        os.utime(os.path.join(folder, "saves", "broken.sav"), (0, 0))   # older than phone.sav
        # the previous build, on an older save line (same block sizes, another stamp), archived
        old = b"an older build" * 100
        old_play = f"PokeMaritimes_save{n - 1}.gba"
        open(os.path.join(folder, old_play), "wb").write(old)
        older = dict(save_layout.recorded(), SAVE_LAYOUT_VERSION=n - 1)
        older["SAVE_LAYOUT_STAMP"] -= 1
        with zipfile.ZipFile(os.path.join(folder, "builds", "old.zip"), "w") as z:
            z.writestr(old_play, old)
        index[0].update(sha256=sha(old), save_layout_version=n - 1, play=old_play, archive="old.zip",
                        layout=older)
        # a ROM the index names whose archive is gone
        stray = f"PokeMaritimes_save{n + 50}.gba"
        open(os.path.join(folder, stray), "wb").write(b"not archived")
        index.insert(0, {k: v for k, v in index[0].items() if k != "layout"}
                     | dict(sha256=sha(b"not archived"), archive="gone.zip", play=stray, save_layout_version=n + 50))
        json.dump(index, open(os.path.join(folder, "builds", "index.json"), "w", encoding="utf-8"))
        # the game's save, restamped as the older line's
        buf = bytearray(open(game_save, "rb").read())
        for _, o in savefile.sectors_with_id(buf, 0):
            buf[o + savefile.STAMP_OFF:o + savefile.STAMP_OFF + 2] = older["SAVE_LAYOUT_STAMP"].to_bytes(2, "little")
            chk = savefile.sector_checksum(buf, o, savefile.sector_size(0, older))
            buf[o + savefile.CHECKSUM_OFF:o + savefile.CHECKSUM_OFF + 2] = chk.to_bytes(2, "little")
        open(os.path.join(folder, "saves", "older.srm"), "wb").write(buf)
        os.utime(os.path.join(folder, "saves", "older.srm"), (0, 0))
        # My Boy!'s sync folder: the game's save (newest of all), junk, and another game's save
        myboy = os.path.join(tmp, "MyBoy", "save")
        os.makedirs(myboy)
        synced = os.path.join(myboy, f"PokeMaritimes_save{n}.sav")
        shutil.copyfile(game_save, synced)
        os.utime(synced, (time.time() + 60, time.time() + 60))
        open(os.path.join(myboy, "PokeMaritimes_junk.sav"), "wb").write(b"\x55" * 2000)
        os.utime(os.path.join(myboy, "PokeMaritimes_junk.sav"), (0, 0))
        open(os.path.join(myboy, "OtherGame.sav"), "wb").write(b"\x66" * 2000)
        open(os.path.join(myboy, f"PokeMaritimes_save{n}.ss1"), "wb").write(b"\x77" * 300000)
        damaged = bytearray(open(game_save, "rb").read())
        for _, o in savefile.sectors_with_id(damaged, 0):        # SaveBlock2 fails its checksum in both slots
            damaged[o + 0x100] ^= 0xFF
        open(os.path.join(myboy, "PokeMaritimes_damaged.sav"), "wb").write(damaged)
        os.utime(os.path.join(myboy, "PokeMaritimes_damaged.sav"), (1000, 1000))

        def tree(d):
            return {os.path.relpath(os.path.join(r, f), d): (os.path.getmtime(os.path.join(r, f)),
                                                             sha(open(os.path.join(r, f), "rb").read()))
                    for r, _, fs in os.walk(d) for f in fs}
        myboy_before = tree(os.path.join(tmp, "MyBoy"))
        seen.clear()
        check(mobile.publish(args) == 0, "publish succeeds")
        text = open(os.path.join(folder, "README.txt"), encoding="utf-8").read()
        check(f"*** SAVE BREAK: this build can't read saves from save line {n - 1}" in text, "README announces the save break")
        check(not os.path.exists(os.path.join(folder, old_play)), f"the archived {old_play} left the top level")
        check(os.path.exists(os.path.join(folder, stray)), "a ROM whose archive is gone is kept")
        check(seen == [synced], "the newest loadable phone save (My Boy!'s synced one) was booted")
        check(tree(os.path.join(tmp, "MyBoy")) == myboy_before, "My Boy!'s sync folder is untouched")
        backups = {sha(open(q, "rb").read()) for q in glob.glob(os.path.join(folder, "saves", "myboy", "*"))}
        check(backups == {sha(open(synced, "rb").read()), sha(b"\x55" * 2000), sha(bytes(damaged))},
              "saves/myboy/ backs up the PokeMaritimes saves, not the other game's or the save state")
        check(f"MyBoy/save/PokeMaritimes_save{n}.sav" in text, "README: the synced save is listed by its Drive path")
        check("PokeMaritimes_junk.sav" in text and "can't check" in text, "README: an unreadable synced file is 'can't check'")
        check("OtherGame" not in text and ".ss1" not in text, "README: another game's save and the state aren't listed")
        line = next((l for l in text.splitlines() if "PokeMaritimes_damaged.sav" in l), "")
        check("WON'T LOAD" in line, "README: a damaged synced save is WON'T LOAD, not 'can't check'")
        check("phone.sav" in text and "loads" in text, "README: the phone save loads")
        check("broken.sav" in text and "WON'T LOAD" in text, "README: the broken save won't load")
        line = next((l for l in text.splitlines() if "saves/older.srm" in l), "")
        check(f"older save line (a save line {n - 1} save: it plays in {old_play}" in line,
              "README: the restamped save (.srm) belongs to the older save line")
        check(len(json.load(open(os.path.join(folder, "builds", "index.json"), encoding="utf-8"))) == 3,
              "index.json gained the new build")

        print("3. the same ROM again")
        mobile.verify = lambda rom_bytes, phone_save=None, full=False: (True, [])
        before = sorted(os.listdir(os.path.join(folder, "builds")))
        saved = sorted(os.listdir(os.path.join(folder, "saves", "myboy")))
        open(os.path.join(folder, "README.txt"), "w").write("old instructions")
        check(mobile.publish(args) == 0, "publish succeeds")
        text = open(os.path.join(folder, "README.txt"), encoding="utf-8").read()
        check("On the phone: My Boy!" in text and "*** SAVE BREAK" in text,
              "a changed README is refreshed for the same build (still announcing its save break)")
        check(sorted(os.listdir(os.path.join(folder, "builds"))) == before, "nothing new was written")
        check(sorted(os.listdir(os.path.join(folder, "saves", "myboy"))) == saved, "no save backed up twice")
        first = {q: open(os.path.join(folder, "saves", "myboy", q), "rb").read() for q in saved}
        changed = bytearray(open(synced, "rb").read())
        changed[-1] ^= 0xFF
        mtime = os.path.getmtime(synced)
        open(synced, "wb").write(changed)
        os.utime(synced, (mtime, mtime))
        check(mobile.publish(args) == 0, "publish succeeds")
        now = sorted(os.listdir(os.path.join(folder, "saves", "myboy")))
        check(len(now) == len(saved) + 1 and all(open(os.path.join(folder, "saves", "myboy", q), "rb").read() == b
                                                 for q, b in first.items()),
              "a changed synced save (same timestamp) gets a new backup; the first is untouched")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not failed else f"FAIL: {failed} check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
