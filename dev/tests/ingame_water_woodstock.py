"""In-game confirmation: can the player walk onto Woodstock's river without Surf?
The checker says tiles like (24,14) are surfable water at elevation 3 (walkable).
Walk to the bank at (23,14), press RIGHT, and read the position back from RAM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from autowalk import Walker
from playtest import prepare_rom

OUT = os.path.join(REPO, "dev", "out")
with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
    assert e.boot_new_game()
    wk = Walker(e)
    for m in ("LittlerootTown_MyHouse_1F_0", "HomeTown_0", "Route201_1", "Woodstock_2"):
        assert wk.go_to_map(m), f"could not reach {m}"
    assert wk.go_to_tile(23, 14), f"could not reach the bank, at {wk.here()}"
    e.shot(os.path.join(OUT, "water_before.png"))
    for _ in range(3):
        e.press("RIGHT", 16, 4)
    name, pos = wk.here()
    e.shot(os.path.join(OUT, "water_after.png"))
    print(f"after pressing RIGHT x3 from (23,14): {name} {pos}")
    print("RESULT:", "WALKED ONTO WATER (bug confirmed)" if pos[0] > 23 else "blocked (no bug)")
