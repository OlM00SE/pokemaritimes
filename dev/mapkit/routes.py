"""Gameplay numbers for a map's crossings, from the engine model (mapkit/engine.py).

A redesign should keep a route playing the way it did. For every ordered pair of edge
connections (entrances), on foot, ledges included:
  steps:       the fewest moves from one neighbour's edge to the other's (a ledge jump is one move);
  grass_steps: the fewest tall-grass tiles the player must enter on the way (0 = the grass can be
               avoided), and the shortest walk that achieves it (grass_route).
Plus the map's encounter ground: tall-grass tiles a walker can reach.

Crossings are only measured between edge connections; warps (doors, caves) aren't entrances here.
"""
import heapq
from .engine import World
from .project import TILE_FLAG_HAS_ENCOUNTERS, TILE_FLAG_SURFABLE

LIMIT = 200000          # states; beyond this the numbers are not reported


def _entrances(world, m, p):
    """{label: [arrival states]} for each edge connection: the neighbour's cells touching the edge."""
    out = {}
    for c in m.connections:
        if c["direction"] not in ("up", "down", "left", "right"):
            continue
        dest = p.const_to_map.get(c["map"])
        cells = [cell for cell, (d, n) in world.conn_side.items() if d == c["direction"] and n == dest]
        touching = [(gx, gy) for gx, gy in cells
                    if any(world.in_map(gx + dx, gy + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)))]
        states = [world.arrival_state(gx, gy) for gx, gy in touching if world.collision(gx, gy) == 0]
        states = [s for s in states if not world.surfing(s)]
        if states:
            out[f"{c['direction']}:{dest}"] = (c["direction"], dest, states)
    return out


def _search(world, starts, grass_first, is_grass):
    """Dijkstra over movement states. Cost = (grass, steps) if grass_first else (steps, grass).
    Returns {state: cost}; states outside the map are reached but not expanded."""
    best = {s: (0, 0) for s in starts}
    q = [((0, 0), s) for s in starts]
    heapq.heapify(q)
    while q:
        cost, s = heapq.heappop(q)
        if best.get(s) != cost or not world.in_map(s[0], s[1]) and s not in starts:
            continue
        if len(best) > LIMIT:
            return None
        for d in "NSWE":
            ns, kind = world.step(s, d)
            if ns is None or kind == "surf_on":
                continue
            g = 1 if world.in_map(ns[0], ns[1]) and is_grass(ns[0], ns[1]) else 0
            nc = (cost[0] + g, cost[1] + 1) if grass_first else (cost[0] + 1, cost[1] + g)
            if nc < best.get(ns, (1 << 30, 0)):
                best[ns] = nc
                heapq.heappush(q, (nc, ns))
    return best


def route_stats(p, m):
    """{'crossings': {(a, b): {'steps', 'grass_steps', 'grass_route'}}, 'grass_reachable': n,
    'grass_total': n}. Unreachable crossings have steps None. Returns None if the search is
    too big."""
    world = World(p, m)
    L = m.layout
    fl = lambda gx, gy: world.flags(gx, gy)
    is_grass = lambda gx, gy: bool(fl(gx, gy) & TILE_FLAG_HAS_ENCOUNTERS) and not fl(gx, gy) & TILE_FLAG_SURFABLE
    ents = _entrances(world, m, p)
    crossings, reach = {}, set()
    for a, (da, _, starts) in ents.items():
        fast = _search(world, starts, False, is_grass)
        calm = _search(world, starts, True, is_grass)
        if fast is None or calm is None:
            return None
        reach |= {(s[0], s[1]) for s in fast if world.in_map(s[0], s[1])}
        for b, (db, dest, _) in ents.items():
            if a == b:
                continue
            goal = lambda s: not world.in_map(s[0], s[1]) and world.conn_side.get((s[0], s[1])) == (db, dest)
            f = [c for s, c in fast.items() if goal(s)]
            g = [c for s, c in calm.items() if goal(s)]
            crossings[(a, b)] = {"steps": min(f)[0] if f else None,
                                 "grass_steps": min(g)[0] if g else None,
                                 "grass_route": min(g)[1] if g else None}
    total = sum(1 for y in range(L.height) for x in range(L.width) if is_grass(*world.to_grid(x, y)))
    got = sum(1 for gx, gy in reach if is_grass(gx, gy))
    return {"crossings": crossings, "grass_reachable": got, "grass_total": total}


def describe(before, after):
    """Lines comparing two route_stats results (before may be None)."""
    if after is None:
        return ["routes: not measured (search too big)"]
    lines = []
    for (a, b), r in sorted(after["crossings"].items()):
        o = (before or {}).get("crossings", {}).get((a, b))
        fmt = lambda r: ("unreachable" if r["steps"] is None else
                         f"{r['steps']} steps, {r['grass_steps']} in tall grass at least"
                         f" ({r['grass_route']} steps that way)")
        lines.append(f"  {a} -> {b}: " + (f"{fmt(o)}  ->  " if o else "") + fmt(r))
    g0 = f"{before['grass_reachable']}/{before['grass_total']} -> " if before else ""
    lines.append(f"  tall grass reachable/total: {g0}{after['grass_reachable']}/{after['grass_total']}")
    return lines
