"""In-game test of the dev warp mailbox: warp to several maps and verify arrival from RAM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom

OUT = os.path.join(REPO, "dev", "out")
targets = [("Route203_1", 10, 10), ("Fredericton_0", 20, 30), ("Route102", 10, 10), ("HomeTown_0", 9, 15)]
ok = True
with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
    assert e.boot_new_game()
    for name, x, y in targets:
        loc = e.warp(name, x, y)
        got = (e.map_name(loc), loc[2], loc[3])
        e.shot(os.path.join(OUT, f"warp_{name}.png"))
        good = got[1:] == (x, y)
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} warp {name} ({x},{y}) -> {got}")
sys.exit(0 if ok else 1)
