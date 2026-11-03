"""In-game screenshots at chosen spots (what the player actually sees).

  python dev/shoot.py Route203_1 20,12 36,19 [--tag r203] [--settle 240]
Writes dev/out/<tag>_<Map>_<x>_<y>.png. Uses a fresh test save and test mode (no battles).
--settle N waits N frames before each shot, so the area-name popup has gone (about 240).
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom


def spot(s):
    try:
        x, y = map(int, s.split(","))
        return x, y
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not a spot (x,y)")


ap = argparse.ArgumentParser(description="In-game screenshots at chosen spots.")
ap.add_argument("map")
ap.add_argument("spots", nargs="+", type=spot, metavar="x,y")
ap.add_argument("--tag", default="shot")
ap.add_argument("--settle", type=int, default=0, metavar="FRAMES")
a = ap.parse_args()                  # bad arguments stop here, before the emulator starts
name, spots, tag, settle = a.map, a.spots, a.tag, a.settle
out = os.path.join(REPO, "dev", "out")
with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
    assert e.boot_new_game()
    e.test_mode()
    for x, y in spots:
        pos = e.warp(name, x, y)
        if settle:
            e.wait(settle)
        path = os.path.join(out, f"{tag}_{name}_{x}_{y}.png")
        e.shot(path)
        print(path, "player at", pos[2:])
