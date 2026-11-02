"""In-game ledge test: does the game jump, and refuse to, exactly where the engine model says?

1. Every approach: for every ledge tile on a map (any MB_JUMP_* tile, plus the vocabulary's solid
   corner pieces), warp to each walkable neighbour and press toward it. The model
   (mapkit.engine.World.step) predicts a two-tile jump or no move; the game's resulting tile
   and elevations (current/previous) must match. That covers jumping from the high side, being
   stopped from the low side and at the ends, and the corners being solid.
2. Round trip (maps with an arrival point, e.g. LedgeLab's spawn): walk the model's shortest
   route from the arrival point to the tile farthest away (which takes the ledges down), then
   back again (which must find the way around them), checking the tile after every move.
3. Terrace tour (maps without NPCs): for every ledge group reachable from the entrance (the
   spawn point, else the edge of the first connection), walk to the nearest takeoff, jump, and
   walk back to the entrance, checking every move. Screenshots each landing.

Tiles in an object event's wander box (+1) are skipped (NPCs block steps); tests run in test
mode (no wild battles, no trainer sight). A map that yields no testable approach fails.

  python dev/tests/ingame_ledges.py [Map ...]
      default: LedgeLab Route203_1 Route102 Route103 Route116 Route123
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, UNTHROTTLED
from playtest import prepare_rom, OUT
from mapkit.project import Project
from mapkit.engine import World, DIRS, DIR_NAME, OPPOSITE
from mapkit import ledges
from mapkit.checks import spawn_point

DEFAULT_MAPS = ["LedgeLab", "Route203_1", "Route102", "Route103", "Route116", "Route123"]


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


def entrance(p, m, w):
    """Where a tour starts: the spawn point, else the middle walkable tile along the map edge
    of its first edge connection (where a player walking in from the neighbour arrives)."""
    spawn = spawn_point(m)
    if spawn:
        return spawn
    L = m.layout
    for c in m.connections:
        edge = {"left": [(0, y) for y in range(L.height)], "right": [(L.width - 1, y) for y in range(L.height)],
                "up": [(x, 0) for x in range(L.width)], "down": [(x, L.height - 1) for x in range(L.width)]
                }.get(c["direction"], [])
        ok = [(x, y) for x, y in edge if not L.coll(x, y) and not w.surfing(w.arrival_state(*w.to_grid(x, y)))]
        if ok:
            return ok[len(ok) // 2]
    return None


def walk(e, w, name, route, origin, label):
    """Press each move of a model route; the game must reach every predicted tile."""
    s = origin
    for i, (d, kind) in enumerate(route):
        s, _ = w.step(s, d)
        x, y = w.to_map(s[0], s[1])
        px, py = e.player()[2:]
        got = press_toward(e, d, px, py)
        if got != (x, y):
            print(f"{name}: {label} move {i} {d} ({kind}): expected {(x, y)}, game {got}")
            return False
    return True


def tour(e, p, name):
    """Terrace tour: for every ledge group the player can reach, walk from the entrance to the
    nearest takeoff, jump down, then walk back to the entrance on foot. Proves in the game that
    each terrace can be used and climbed back. Skipped on maps with NPCs (the model doesn't
    route around them). Screenshots each landing: dev/out/ledges_<Map>_tour<N>.png."""
    m = p.load_map(name)
    if m.events("object_events"):
        print(f"{name}: tour skipped (the map has NPCs)")
        return 0
    w = World(p, m)
    L = m.layout
    at = entrance(p, m, w)
    if at is None:
        print(f"{name}: tour FAILED: no entrance to start from")
        return 1
    start = w.arrival_state(*w.to_grid(*at))
    edges = {}
    seen = w.explore([start], edges=edges)
    depth = {start: 0}
    for s, link in seen.items():
        if link:
            depth[s] = depth[link[0]] + 1
    # ledge groups: 4-connected ledge cells
    jump = set(w.beh_jump)
    cells = {(x, y) for y in range(L.height) for x in range(L.width)
             if L.tiles.behavior(L.mid(x, y)) in jump or
             (L.primary == "gTileset_General" and L.mid(x, y) in ledges.PIECES)}
    group, n = {}, 0
    for c in sorted(cells):
        if c in group:
            continue
        n += 1
        stack = [c]
        while stack:
            x, y = stack.pop()
            if (x, y) in group or (x, y) not in cells:
                continue
            group[(x, y)] = n
            stack += [(x + dx, y + dy) for dx, dy in DIRS.values()]
    takeoffs = {}                       # group -> (depth, takeoff state, dir, landing state)
    for s, lst in edges.items():
        for ns, d, kind in lst:
            if kind != "jump":
                continue
            ox, oy = w.to_map(s[0] + DIRS[d][0], s[1] + DIRS[d][1])
            g = group.get((ox, oy))
            if g and (g not in takeoffs or depth[s] < takeoffs[g][0]):
                takeoffs[g] = (depth[s], s, d, ns)
    bad = 0
    print(f"{name}: tour from {at}: {n} ledge groups, {len(takeoffs)} reachable")
    for g in sorted(takeoffs):
        _, s, d, landing = takeoffs[g]
        there = World.path_to(seen, s) + [(d, "jump")]
        back_seen = w.explore([landing])
        home = next((t for t in back_seen if t[:2] == start[:2]), None)
        tx, ty = w.to_map(s[0], s[1]); lx, ly = w.to_map(landing[0], landing[1])
        if home is None:
            print(f"{name}: group {g}: no way back from {(lx, ly)} (a trap)")
            bad += 1
            continue
        e.warp(name, *at)
        ok = walk(e, w, name, there, start, f"group {g} down")
        if ok:
            e.shot(os.path.join(OUT, f"ledges_{name}_tour{g}.png"))
            ok = walk(e, w, name, World.path_to(back_seen, home), landing, f"group {g} back")
        print(f"{name}: group {g}: jump {d} at {(tx, ty)} -> {(lx, ly)}, then back to {at}: "
              f"{'OK' if ok else 'FAILED'}")
        bad += not ok
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
            bad += tour(e, p, name)
    print("PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
