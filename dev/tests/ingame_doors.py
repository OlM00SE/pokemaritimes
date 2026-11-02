"""In-game: every door warp on the given outdoor maps enters its interior, and the player
can walk back out to the same door. Stairs inside are followed one level too.

  python dev/tests/ingame_doors.py HomeTown_0 Woodstock_2
Screenshots go to dev/out/door_<Map>_<x>_<y>.png. Exit code 1 on any failure.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit.doors import door_tiles

OUT = os.path.join(REPO, "dev", "out")


def name_of(p, const):
    return p.const_to_map.get(const)


def main(maps):
    p = Project()
    fails = []
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()
        for outdoor in maps:
            m = p.load_map(outdoor)
            doors = set(door_tiles(p, m))
            for w in m.events("warp_events"):
                x, y = w["x"], w["y"]
                if (x, y) not in doors:
                    continue
                inside = name_of(p, w["dest_map"])
                label = f"{outdoor} door ({x},{y}) -> {inside}"
                if not inside:
                    fails.append(f"{label}: destination {w['dest_map']} is not a known map"); continue
                e.warp(outdoor, x, y + 1)
                e.press("UP", 16, 4)
                e.wait_for_control()
                where = e.map_name()
                e.shot(os.path.join(OUT, f"door_{outdoor}_{x}_{y}.png"))
                if where != p.load_map(inside).id[4:]:
                    fails.append(f"{label}: pressing UP left the player on {where}"); continue
                # stairs/other step-on warps inside: step onto each from below, check, come back
                for sw in p.load_map(inside).events("warp_events"):
                    up = name_of(p, sw["dest_map"])
                    if not up or sw["dest_map"] == m.id:
                        continue
                    e.warp(inside, sw["x"], sw["y"] + 1)
                    e.press("UP", 16, 4)
                    e.wait_for_control()
                    got = e.map_name()
                    e.shot(os.path.join(OUT, f"door_{up}.png"))
                    want = p.load_map(up).id[4:]
                    print(f"  {inside} ({sw['x']},{sw['y']}) -> {got}", "ok" if got == want else "FAIL")
                    if got != want:
                        fails.append(f"{inside} warp at ({sw['x']},{sw['y']}) went to {got}, not {up}")
                # walk back out through the exit mat
                exit_w = next((sw for sw in p.load_map(inside).events("warp_events") if sw["dest_map"] == m.id), None)
                if exit_w is None:
                    fails.append(f"{label}: {inside} has no warp back to {outdoor}"); continue
                e.warp(inside, exit_w["x"], exit_w["y"] - 1)
                e.press("DOWN", 16, 4)
                e.press("DOWN", 16, 4)
                e.wait_for_control()
                pos = e.player()
                back = e.map_name()
                ok = back == m.id[4:] and (pos[2], pos[3]) == (x, y + 1)
                print(f"{label}: in ok, out -> {back} {pos[2:4]}", "ok" if ok else "FAIL")
                if not ok:
                    fails.append(f"{label}: walking out put the player on {back} {pos[2:4]}, "
                                 f"expected ({x},{y + 1})")
    for f in fails:
        print("FAIL", f)
    print(f"RESULT: {'PASS' if not fails else f'{len(fails)} failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
