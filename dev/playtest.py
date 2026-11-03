"""Automated playtest CLI: boot the built ROM in mGBA, act, screenshot, report.

  python dev/playtest.py newgame                     # fresh game via Quickstart, screenshot
  python dev/playtest.py walk "D4 R1 D30"            # new game, then walk; log each leg
  python dev/playtest.py walk "D4 R1" --continue     # continue the test save instead
  python dev/playtest.py walk "..." --realtime       # 60 fps (default is unthrottled)

Runs on a copy of the ROM in dev/out/ so tests never touch your real save.
Screenshots land in dev/out/. Exit code 1 if the overworld is never reached.
"""
import argparse, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED

OUT = os.path.join(REPO, "dev", "out")
DIRS = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}


def prepare_rom(fresh):
    os.makedirs(OUT, exist_ok=True)
    rom = os.path.join(OUT, "test.gba")
    shutil.copyfile(os.path.join(REPO, "pokeemerald.gba"), rom)
    shutil.copyfile(os.path.join(REPO, "pokeemerald.map"), os.path.join(OUT, "test.map"))
    sav = os.path.join(OUT, "test.sav")
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

    rom = prepare_rom(fresh=not a.cont)
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
