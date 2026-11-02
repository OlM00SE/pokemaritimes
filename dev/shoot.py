"""In-game screenshots at chosen spots (what the player actually sees).

  python dev/shoot.py Route203_1 20,12 36,19 [--tag r203]
Writes dev/out/<tag>_<Map>_<x>_<y>.png. Uses a fresh test save and test mode (no battles).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom

args = [a for a in sys.argv[1:] if not a.startswith("--")]
tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "shot"
args = [a for a in args if a != tag]
name, spots = args[0], [tuple(map(int, s.split(","))) for s in args[1:]]
out = os.path.join(REPO, "dev", "out")
with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
    assert e.boot_new_game()
    e.test_mode()
    for x, y in spots:
        pos = e.warp(name, x, y)
        path = os.path.join(out, f"{tag}_{name}_{x}_{y}.png")
        e.shot(path)
        print(path, "player at", pos[2:])
