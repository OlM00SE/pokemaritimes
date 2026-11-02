"""In-game ledge test: does the game jump, and refuse to, exactly where the engine model says?

1. Every approach: for every ledge tile on a map (any MB_JUMP_* tile, plus the vocabulary's solid
   corner pieces), warp to each walkable neighbour and press toward it. The model
   (mapkit.engine.World.step) predicts a two-tile jump or no move; the game's resulting tile
   and elevations (current/previous) must match. That covers jumping from the high side, being
   stopped from the low side and at the ends, and the corners being solid.
2. Round trip (maps with an arrival point, e.g. LedgeLab's spawn): walk the model's shortest
   route from the arrival point to the tile farthest away (which takes the ledges down), then
   back again (which must find the way around them), checking the tile after every move.

Tiles in an object event's wander box (+1) are skipped (NPCs block steps); tests run in test
mode (no wild battles, no trainer sight). A map that yields no testable approach fails.

  python dev/tests/ingame_ledges.py [Map ...]    default: LedgeLab Route102 Route103 Route116 Route123
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, UNTHROTTLED
from playtest import prepare_rom, OUT
from mapkit.project import Project
from mapkit.engine import World, DIRS, DIR_NAME, OPPOSITE
from mapkit import ledges
from mapkit.checks import spawn_point

DEFAULT_MAPS = ["LedgeLab", "Route102", "Route103", "Route116", "Route123"]


def elevations(e):
    """(currentElevation, previousElevation) of the player: ObjectEvent byte 0x0B."""
    oid = e.read8(e.sym["gPlayerAvatar"] + 5)
    v = e.read8(e.sym["gObjectEvents"] + oid * 0x24 + 0x0B)
    return v & 0xF, v >> 4


def press_toward(e, d, x, y):
    """A tap turns the player if facing elsewhere, or moves if already facing: tap twice if the
    first tap didn't move. Jumps take longer than steps, hence the generous waits."""
    e.press(DIR_NAME[d], 3, 50)
    loc = e.player()
    if (loc[2], loc[3]) == (x, y):
        e.press(DIR_NAME[d], 3, 60)
        loc = e.player()
    return (loc[2], loc[3])


def cases_for(p, name):
    m = p.load_map(name)
    w = World(p, m)
    L = m.layout
    # NPCs block steps: skip tiles in an object's wander box (its movement range) plus a margin
    boxes = [(o["x"], o["y"], int(o.get("movement_range_x", 0)) + 1, int(o.get("movement_range_y", 0)) + 1)
             for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near = lambda x, y: any(abs(x - ox) <= rx and abs(y - oy) <= ry for ox, oy, rx, ry in boxes) \
        or (x, y) in warps
    jump = set(w.beh_jump)
    is_ledge = lambda x, y: L.inb(x, y) and (L.tiles.behavior(L.mid(x, y)) in jump or
                                             (L.primary == "gTileset_General" and L.mid(x, y) in ledges.PIECES))
    out = []
    for y in range(L.height):
        for x in range(L.width):
            if not is_ledge(x, y):
                continue
            for d, (dx, dy) in DIRS.items():
                sx, sy = x - dx, y - dy                  # stand here, press d toward the ledge
                if not L.inb(sx, sy) or L.coll(sx, sy) or is_ledge(sx, sy) or near(sx, sy):
                    continue
                s = w.arrival_state(*w.to_grid(sx, sy))
                if w.surfing(s):
                    continue
                ns, kind = w.step(s, d)
                exp = (sx, sy) if ns is None else w.to_map(ns[0], ns[1])
                if ns is not None and (not w.in_map(ns[0], ns[1]) or near(*exp)):
                    continue
                elev = None if ns is None else (ns[2], ns[3])
                out.append(((x, y), (sx, sy), d, exp, kind, elev))
    return out


def approaches(e, p, name):
    """Returns the number of failures. A warp that errors, or lands somewhere else, is a
    failure: every case counted as run was really run in the game."""
    cases = cases_for(p, name)
    bad, done, jumps = [], 0, 0
    for ledge, (sx, sy), d, exp, kind, elev in cases:
        try:
            landed = e.warp(name, sx, sy)[2:]
        except RuntimeError as ex:
            print(f"{name}: ABORTED, a warp failed ({ex}) after {done} of {len(cases)} cases")
            for _ in range(30):
                e.press("B", 3, 10)
            return len(bad) + 1
        if landed != (sx, sy):
            bad.append(f"    warp to {(sx, sy)} landed on {landed}: case not run")
            continue
        got = press_toward(e, d, sx, sy)
        done += 1
        jumps += kind == "jump"
        ok = got == exp
        if ok and elev is not None:
            ok = elevations(e) == elev
            got = (got, elevations(e))
            exp = (exp, elev)
        if not ok:
            bad.append(f"    ledge {ledge} from {(sx, sy)} press {d}: model {kind}->{exp}, game ->{got}")
    print(f"{name}: {done - len(bad)}/{done} ledge approaches agree ({jumps} jumps, "
          f"{done - jumps} refusals expected; {len(cases) - done} not run)")
    for line in bad[:8]:
        print(line)
    if not done:
        print(f"{name}: NOTHING TESTED (no ledge with a free approach)")
        return 1
    return len(bad)


def round_trip(e, p, name):
    """Walk the model's route from the arrival point to the farthest tile and back."""
    m = p.load_map(name)
    w = World(p, m)
    spawn = spawn_point(m)
    if not spawn:
        return 0
    spawns = [spawn]
    start = w.arrival_state(*w.to_grid(*spawns[0]))
    seen = w.explore([start])
    depth = {start: 0}                       # BFS order: a state's parent always comes first
    for s, link in seen.items():
        if link:
            depth[s] = depth[link[0]] + 1
    far = max((s for s in seen if w.in_map(s[0], s[1])), key=depth.get)
    there = World.path_to(seen, far)
    back_seen = w.explore([far])
    home = next((s for s in back_seen if s[:2] == start[:2]), None)
    if home is None:
        print(f"{name}: round trip FAILED: the model finds no way back to the spawn")
        return 1
    back = World.path_to(back_seen, home)
    e.warp(name, *spawns[0])
    bad = 0
    for label, route, origin in (("down", there, start), ("back", back, far)):
        jumps = sum(1 for _, k in route if k == "jump")
        s = origin
        for i, (d, kind) in enumerate(route):
            s, _ = w.step(s, d)
            x, y = w.to_map(s[0], s[1])
            px, py = e.player()[2:]
            got = press_toward(e, d, px, py)
            if got != (x, y):
                print(f"{name}: {label} step {i} {d} ({kind}): expected {(x, y)}, game {got}")
                bad += 1
                break
        e.shot(os.path.join(OUT, f"ledges_{name}_{label}.png"))
        print(f"{name}: walked {label} {len(route)} moves ({jumps} ledge jumps) "
              f"{'OK' if not bad else 'FAILED'}")
    return bad


def main(argv):
    maps = argv or DEFAULT_MAPS
    p = Project()
    bad = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()
        for name in maps:
            bad += approaches(e, p, name)
            bad += round_trip(e, p, name)
    print("PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
