"""Automated playtest CLI: boot the built ROM in mGBA, act, screenshot, report.

  python dev/playtest.py newgame                     # fresh game via Quickstart, screenshot
  python dev/playtest.py walk "D4 R1 D30"            # new game, then walk; log each leg
  python dev/playtest.py walk "D4 R1" --continue     # continue the test save instead
  python dev/playtest.py walk "..." --realtime       # 60 fps (default is unthrottled)

Runs on a copy of the ROM in dev/out/ so tests never touch your real save.
Screenshots land in dev/out/. Exit code 1 if the overworld is never reached.
"""
import argparse, atexit, os, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED

OUT = os.path.join(REPO, "dev", "out")
DIRS = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}
_test_dir = None
_test_dirs = []


def _cleanup_test_dirs():
    for directory in _test_dirs:
        directory.cleanup()


atexit.register(_cleanup_test_dirs)


def prepare_rom(fresh, persistent=False):
    """Copy the built ROM into an isolated test slot.

    Automated tests get one temporary slot per process, so parallel tests never replace each
    other's ROM, symbol map or save. The interactive playtest CLI uses the persistent test slot
    to preserve its --continue workflow across commands.
    """
    global _test_dir
    os.makedirs(OUT, exist_ok=True)
    if persistent:
        folder = OUT
    else:
        if fresh or _test_dir is None:
            _test_dir = tempfile.TemporaryDirectory(prefix="emutest-", dir=OUT,
                                                     ignore_cleanup_errors=True)
            _test_dirs.append(_test_dir)
        folder = _test_dir.name
    rom = os.path.join(folder, "test.gba")
    shutil.copyfile(os.path.join(REPO, "pokeemerald.gba"), rom)
    shutil.copyfile(os.path.join(REPO, "pokeemerald.map"), os.path.join(folder, "test.map"))
    sav = os.path.join(folder, "test.sav")
    if fresh and os.path.exists(sav):
        # the previous test's mGBA may still be closing and holding the save (Windows): wait a bit
        for attempt in range(20):
            try:
                os.remove(sav)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.5)
    return rom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["newgame", "walk"])
    ap.add_argument("route", nargs="?", default="", help='legs like "D4 R1 U2"')
    ap.add_argument("--continue", dest="cont", action="store_true", help="continue test save")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--tag", default="pt", help="screenshot filename prefix")
    ap.add_argument("--story", action="store_true",
                    help="play as a real new player (wild battles on, story gates closed); "
                         "default is test mode, which only tests movement")
    a = ap.parse_args()

    rom = prepare_rom(fresh=not a.cont, persistent=True)
    with Emu(rom, extra_args=[] if a.realtime else UNTHROTTLED) as e:
        ok = e.boot_to_overworld() if a.cont else e.boot_new_game()
        if not ok:
            e.shot(os.path.join(OUT, f"{a.tag}_FAILED.png"))
            print("FAIL: never reached the overworld")
            return 1
        if not a.story:
            e.test_mode()
        loc = e.player()
        print(f"start: {e.map_name(loc)} {loc[2:]}")
        e.shot(os.path.join(OUT, f"{a.tag}_00_start.png"))
        for i, leg in enumerate(a.route.split(), 1):
            loc = e.step(DIRS[leg[0].upper()], int(leg[1:] or 1))
            print(f"{leg:>4} -> {e.map_name(loc)} {loc[2:]}")
            e.shot(os.path.join(OUT, f"{a.tag}_{i:02}_{leg}.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
