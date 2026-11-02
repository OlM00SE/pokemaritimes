"""Reproduce one step with screenshots: python dev/tests/debug_step.py Map x y DIR"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom

name, x, y, d = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
OUT = os.path.join(REPO, "dev", "out")
with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
    assert e.boot_new_game()
    e.test_mode()
    print("arrived:", e.warp(name, x, y), "overworld:", e.in_overworld())
    e.shot(os.path.join(OUT, "dbg_0.png"))
    for i in range(1, 4):
        e.press(d, 3, 40)
        print(f"tap {i}: {e.player()}  cb2_overworld={e.in_overworld()}")
        e.shot(os.path.join(OUT, f"dbg_{i}.png"))
