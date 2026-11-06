"""Engine-model conformance: does mapkit.engine predict single steps exactly like the game?

For random reachable tiles on each map: warp there (dev mailbox), press a direction, read the
player's tile back from RAM, and compare with World.step()'s prediction (walk/jump/blocked/...).
Tiles within 6 of any object event are skipped (NPCs block steps and trainers start battles).
The game's warp API takes signed 8-bit coordinates; source tiles above 127 cannot be reached by
the test warp and are reported as untestable rather than counted as passing comparisons.

  python dev/tests/conformance.py [--samples 40] [Map ...]
"""
import argparse, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit.engine import World, DIR_NAME

DEFAULT_MAPS = ["HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1", "Fredericton_0",
                "Route203_1", "Route102", "Route104", "Route110", "Route116", "Route117", "Route119",
                "LedgeLab", "ShoreLab", "GroveLab", "CliffLab"]


def samples_for(p, name, n, rng):
    m = p.load_map(name)
    w = World(p, m)
    objs = [(o["x"], o["y"]) for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near_obj = lambda x, y: (x, y) in warps or any(abs(x - ox) + abs(y - oy) <= 6 for ox, oy in objs)
    starts = [w.arrival_state(*w.to_grid(x, y)) for y in range(m.layout.height) for x in range(m.layout.width)
              if m.layout.coll(x, y) == 0 and not near_obj(x, y)
              and not w.surfing(w.arrival_state(*w.to_grid(x, y)))]
    untestable = sum(1 for s in starts if max(w.to_map(s[0], s[1])) > 127)
    starts = [s for s in starts if max(w.to_map(s[0], s[1])) <= 127]
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
    return out, untestable


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("maps", nargs="*")
    args = parser.parse_args(argv)
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    maps = args.maps or DEFAULT_MAPS
    p, rng = Project(), random.Random(1234)
    total = passed = bad = skipped_total = untestable_total = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        for map_index, name in enumerate(maps):
            cases, untestable = samples_for(p, name, args.samples, rng)
            untestable_total += untestable
            mism, executed, attempted, comp_bad = [], 0, 0, 0
            warp_error = False
            if not cases:
                mism.append("    no testable steps were selected")
            for x, y, d, exp, kind in cases:
                attempted += 1
                try:
                    landed = e.warp(name, x, y)[2:]
                except RuntimeError as ex:
                    mism.append(f"    warp to ({x},{y}) failed: {ex}")
                    warp_error = True
                    break
                # Starts come from the model's arrival_state, which says the player stays on the
                # tile; landing elsewhere is a model/game disagreement, not a case to skip.
                if landed != (x, y):
                    mism.append(f"    warp to ({x},{y}) landed at {landed}: comparison not run")
                    continue
                # A tap turns the player if facing elsewhere, or steps if already facing.
                e.press(DIR_NAME[d], 3, 40)
                loc = e.player()
                if (loc[2], loc[3]) == (x, y):
                    e.press(DIR_NAME[d], 3, 50)
                    loc = e.player()
                got = (loc[2], loc[3])
                executed += 1
                total += 1
                if got != exp:
                    comp_bad += 1
                    mism.append(f"    ({x},{y}) {d}: model {kind}->{exp}, game ->{got}")
            failures = len(mism)
            skipped = len(cases) - executed
            passed += executed - comp_bad
            bad += failures
            skipped_total += skipped
            print(f"{name}: {executed - comp_bad}/{executed} "
                  f"executed, {len(cases)} planned, {skipped} skipped, {failures} failed, "
                  f"{untestable} source tiles untestable by signed 8-bit warp"
                  + (" (NOT TESTED)" if not executed else ""))
            for line in mism[:6]:
                print(line)
            if warp_error:
                print(f"Remaining {len(maps) - map_index - 1} maps NOT RUN after emulator warp error; "
                      f"{len(cases) - attempted} planned cases on {name} were not attempted")
                break
    print(f"\nTOTAL: {passed}/{total} executed comparisons; "
          f"{skipped_total} skipped, {bad} failed; "
          f"{untestable_total} source tiles untestable by signed 8-bit warp")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
