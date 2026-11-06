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


def approach(L, x, y):
    """A walkable neighbour of a step-on warp (stairs, a ladder, the Center's escalator) the
    player can step from onto it, with the key to press: from below if possible (stairs), else
    from a side. The engine lets a step change elevation only through 0 or 15 (transition and
    multi-level tiles), so the escalator (elevation 4) is boarded from its elevation-0 side."""
    ok = lambda a, b: a == b or a in (0, 15) or b in (0, 15)
    for dx, dy, key in ((0, 1, "UP"), (1, 0, "LEFT"), (-1, 0, "RIGHT"), (0, -1, "DOWN")):
        nx, ny = x + dx, y + dy
        if L.inb(nx, ny) and L.coll(nx, ny) == 0 and ok(L.elev(nx, ny), L.elev(x, y)):
            return nx, ny, key
    return x, y + 1, "UP"


def main(maps):
    if not maps:
        print("FAIL: no outdoor maps requested; no doors tested")
        return 1
    p = Project()
    fails = []
    completed = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()
        for outdoor in maps:
            m = p.load_map(outdoor)
            doors = set(door_tiles(p, m))
            selected = tested = 0
            for w in m.events("warp_events"):
                x, y = w["x"], w["y"]
                if (x, y) not in doors:
                    continue
                selected += 1
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
                    ax, ay, key = approach(p.load_map(inside).layout, sw["x"], sw["y"])
                    e.warp(inside, ax, ay)
                    e.press(key, 16, 4)
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
                else:
                    tested += 1
            completed += tested
            print(f"{outdoor}: {tested}/{selected} door round trips completed"
                  + (" (NOT TESTED)" if not selected else ""))
            if not selected:
                fails.append(f"{outdoor}: no door warps were selected; no coverage")
    for f in fails:
        print("FAIL", f)
    print(f"RESULT: {'PASS' if not fails else f'{len(fails)} failures'}; "
          f"{completed} completed door round trips")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
