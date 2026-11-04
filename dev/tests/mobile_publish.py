"""dev/mobile.py publishes into a scratch folder (never the real Drive) as the phone needs it.

  python dev/tests/mobile_publish.py

Uses the ROM already built (run dev/fastbuild.py first) and the real mGBA verification:
  1. a first publish: the play file is the ROM byte for byte, named for its save line; the archive
     holds the same ROM under that name plus build.txt; index.json and README.txt describe it;
  2. a save break: with a previous build on another save line in the index, the README says SAVE
     BREAK, the old play file leaves the top level (it's archived), and a stray ROM that isn't
     archived is kept; the phone save in saves/ (the game's own, from step 1) is checked, reported
     as loading, and CONTINUEd in mGBA; a broken one is reported as WON'T LOAD and not booted;
  3. publishing the same ROM again uploads nothing.
"""
import argparse, glob, hashlib, json, os, shutil, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fastbuild, mobile, save_layout

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
        old = b"an older build" * 100
        old_play = f"PokeMaritimes_save{n - 1}.gba"
        open(os.path.join(folder, old_play), "wb").write(old)
        open(os.path.join(folder, "PokeMaritimes_save0.gba"), "wb").write(b"not archived")
        index[0].update(sha256=sha(old), save_layout_version=n - 1, play=old_play)
        json.dump(index, open(os.path.join(folder, "builds", "index.json"), "w", encoding="utf-8"))
        seen.clear()
        check(mobile.publish(args) == 0, "publish succeeds")
        text = open(os.path.join(folder, "README.txt"), encoding="utf-8").read()
        check(f"*** SAVE BREAK: this build can't read saves from save line {n - 1}" in text, "README announces the save break")
        check(not os.path.exists(os.path.join(folder, old_play)), f"the archived {old_play} left the top level")
        check(os.path.exists(os.path.join(folder, "PokeMaritimes_save0.gba")), "a ROM not in the archive is kept")
        check(seen == [os.path.join(folder, "saves", "phone.sav")], "the loadable phone save was booted")
        check("phone.sav" in text and "loads" in text, "README: the phone save loads")
        check("broken.sav" in text and "WON'T LOAD" in text, "README: the broken save won't load")
        check(len(json.load(open(os.path.join(folder, "builds", "index.json"), encoding="utf-8"))) == 2,
              "index.json has both builds")

        print("3. the same ROM again")
        mobile.verify = lambda rom_bytes, phone_save=None, full=False: (True, [])
        before = sorted(os.listdir(os.path.join(folder, "builds")))
        check(mobile.publish(args) == 0, "publish succeeds")
        check(sorted(os.listdir(os.path.join(folder, "builds"))) == before, "nothing new was written")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not failed else f"FAIL: {failed} check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
