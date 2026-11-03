"""In-game screenshots at chosen spots (what the player actually sees).

  python dev/shoot.py Route203_1 20,12 36,19 [--tag r203] [--settle 240]
Writes dev/out/<tag>_<Map>_<x>_<y>.png. Uses a fresh test save and test mode (no battles).
--settle N waits N frames before each shot, so the area-name popup has gone (about 240).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom


def option(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


tag = option("--tag", "shot")
settle = int(option("--settle", 0))
flags = {"--tag", "--settle"}
args = [a for i, a in enumerate(sys.argv[1:], 1) if a not in flags and sys.argv[i - 1] not in flags]
name, spots = args[0], [tuple(map(int, s.split(","))) for s in args[1:]]
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
