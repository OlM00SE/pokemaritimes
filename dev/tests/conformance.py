"""Engine-model conformance: does mapkit.engine predict single steps exactly like the game?

For random reachable tiles on each map: warp there (dev mailbox), press a direction, read the
player's tile back from RAM, and compare with World.step()'s prediction (walk/jump/blocked/...).
Tiles within 6 of any object event are skipped (NPCs block steps and trainers start battles).

  python dev/tests/conformance.py [--samples 40] [Map ...]
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit.engine import World, DIR_NAME

DEFAULT_MAPS = ["HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1", "Fredericton_0",
                "Route203_1", "Route102", "Route104", "Route110", "Route116", "Route117", "Route119",
                "LedgeLab", "ShoreLab"]


def samples_for(p, name, n, rng):
    m = p.load_map(name)
    w = World(p, m)
    objs = [(o["x"], o["y"]) for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near_obj = lambda x, y: (x, y) in warps or any(abs(x - ox) + abs(y - oy) <= 6 for ox, oy in objs)
    starts = [w.arrival_state(*w.to_grid(x, y)) for y in range(m.layout.height) for x in range(m.layout.width)
              if m.layout.coll(x, y) == 0 and not near_obj(x, y)
              and not w.surfing(w.arrival_state(*w.to_grid(x, y)))]
    out = []
    for s in rng.sample(starts, min(n, len(starts))):
        d = rng.choice("NSWE")
        dx, dy = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}[d]
        tx, ty = w.to_map(s[0] + dx, s[1] + dy)
        if (tx, ty) in warps:          # stepping into a door/warp starts a warp: tested elsewhere
            continue
        ns, kind = w.step(s, d)
        if kind in ("surf_on", "unsupported"):     # Surf needs the field move; skip
            continue
        x, y = w.to_map(s[0], s[1])
        exp = (x, y) if ns is None else w.to_map(ns[0], ns[1])
        if ns is not None and not w.in_map(ns[0], ns[1]):
            continue                                # crossing into a neighbour: covered by autowalk
        if near_obj(*exp):
            continue
        out.append((x, y, d, exp, kind))
    return out


def main(argv):
    n = 40
    if "--samples" in argv:
        i = argv.index("--samples"); n = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    maps = argv or DEFAULT_MAPS
    p, rng = Project(), random.Random(1234)
    total = bad = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        for name in maps:
            cases = samples_for(p, name, n, rng)
            mism = []
            skipped = None
            for x, y, d, exp, kind in cases:
                try:
                    if e.warp(name, x, y)[2:] != (x, y):
                        continue                # arrival moved the player (e.g. stepped off a mat)
                except RuntimeError as ex:      # story script took control (unset progress vars)
                    skipped = str(ex)
                    for _ in range(30):         # dismiss whatever is on screen and move on
                        e.press("B", 3, 10)
                    break
                # A tap turns the player if facing elsewhere, or steps if already facing.
                e.press(DIR_NAME[d], 3, 40)
                loc = e.player()
                if (loc[2], loc[3]) == (x, y):
                    e.press(DIR_NAME[d], 3, 50)
                    loc = e.player()
                got = (loc[2], loc[3])
                total += 1
                if got != exp:
                    bad += 1
                    mism.append(f"    ({x},{y}) {d}: model {kind}->{exp}, game ->{got}")
            if skipped:
                print(f"{name}: SKIPPED after a scripted event took control ({skipped})")
                continue
            print(f"{name}: {len(cases) - len(mism)}/{len(cases)} steps agree")
            for line in mism[:6]:
                print(line)
    print(f"\nTOTAL: {total - bad}/{total} single-step predictions match the game")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
