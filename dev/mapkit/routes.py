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
        states = [world.arrival_state(gx, gy) for gx, gy in touching
                  if world.collision(gx, gy) == 0 and (gx, gy) not in world.obstacles]
        states = [s for s in states if not world.surfing(s)]
        if states:
            out[f"{c['direction']}:{dest}"] = (c["direction"], dest, states)
    return out


def _search(world, starts, grass_first, is_grass):
    """Dijkstra over movement states. Cost = (grass, steps) if grass_first else (steps, grass).
    Returns {state: cost}; states outside the map are reached but not expanded."""
    starts = set(starts)
    best = {s: (0, 0) for s in starts}
    q = [((0, 0), s) for s in starts]
    heapq.heapify(q)
    while q:
        cost, s = heapq.heappop(q)
        if best.get(s) != cost or (not world.in_map(s[0], s[1]) and s not in starts):
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


def forced_trainers(p, m, world, ents):
    """{(a, b): [trainer labels]}: for each crossing, the trainers whose sight it can't avoid
    (each judged alone: the crossing with that trainer's sight tiles closed is impossible).
    Permanent people block, at home (as in route_stats); trainers with a hide flag are left out.
    Returns None if a search is too big (route_stats then reports nothing)."""
    from . import events
    out = {}
    objs = m.events("object_events")
    for i, o in enumerate(objs):
        if not events.is_trainer(o) or events.hidden_by_flag(o):
            continue
        lines = events.sight_lines(world, o, events.sight_others(m, i))
        sight = {t for ts in lines.values() for t in ts}
        if not sight:
            continue
        closed = events.world_with_people(p, m, boxes=False, extra=sight, permanent_only=True)
        for a, (_, _, starts) in ents.items():
            starts = [s for s in starts if (s[0], s[1]) not in closed.obstacles]
            got = _search(closed, starts, False, lambda gx, gy: False)
            if got is None:
                return None
            for b, (db, nb, _) in ents.items():
                if b != a and not any(not closed.in_map(s[0], s[1]) and closed.conn_side.get((s[0], s[1])) == (db, nb)
                                      for s in got if s not in starts):
                    out.setdefault((a, b), []).append(events.label("object_events", i, o))
    return out


def route_stats(p, m):
    """{'crossings': {(a, b): {'steps', 'grass_steps', 'grass_route', 'trainers'}},
    'grass_reachable': n, 'grass_total': n}. Permanent people block the way, at home (a
    wanderer steps aside, an item ball is taken); 'trainers' lists those whose sight the
    crossing can't avoid. Unreachable crossings
    have steps None. Returns None if the search is too big."""
    from .events import world_with_people
    world = world_with_people(p, m, boxes=False, permanent_only=True)
    L = m.layout
    fl = lambda gx, gy: world.flags(gx, gy)
    is_grass = lambda gx, gy: bool(fl(gx, gy) & TILE_FLAG_HAS_ENCOUNTERS) and not fl(gx, gy) & TILE_FLAG_SURFABLE
    ents = _entrances(world, m, p)
    label = {(d, dest): a for a, (d, dest, _) in ents.items()}

    def best_exit(costs):
        """{entrance label: the cheapest cost of stepping out across that entrance's edge}"""
        out = {}
        for s, c in costs.items():
            if not world.in_map(s[0], s[1]):
                b = label.get(world.conn_side.get((s[0], s[1])))
                if b and (b not in out or c < out[b]):
                    out[b] = c
        return out

    crossings, reach = {}, set()
    forced = forced_trainers(p, m, world, ents)
    if forced is None:
        return None
    for a, (da, _, starts) in ents.items():
        fast = _search(world, starts, False, is_grass)
        calm = _search(world, starts, True, is_grass)
        if fast is None or calm is None:
            return None
        reach |= {(s[0], s[1]) for s in fast if world.in_map(s[0], s[1])}
        f, g = best_exit(fast), best_exit(calm)
        for b in ents:
            if a != b:
                crossings[(a, b)] = {"steps": f[b][0] if b in f else None,
                                     "grass_steps": g[b][0] if b in g else None,
                                     "grass_route": g[b][1] if b in g else None,
                                     "trainers": forced.get((a, b), []) if b in f else []}
    total = sum(1 for y in range(L.height) for x in range(L.width) if is_grass(*world.to_grid(x, y)))
    got = sum(1 for gx, gy in reach if is_grass(gx, gy))
    return {"crossings": crossings, "grass_reachable": got, "grass_total": total}


def describe(before, after):
    """Lines comparing two route_stats results (before may be None)."""
    if after is None:
        return ["routes: not measured (search too big)"]
    lines = []
    old = (before or {}).get("crossings", {})
    fmt = lambda r: ("unreachable" if r is None or r["steps"] is None else
                     f"{r['steps']} steps, {r['grass_steps']} in tall grass at least"
                     f" ({r['grass_route']} steps that way)"
                     + (f", can't avoid {', '.join(r['trainers'])}" if r.get("trainers") else ""))
    # a crossing that existed before but not after: an entrance with no walkable tile left
    for a, b in sorted(set(old) | set(after["crossings"])):
        o, r = old.get((a, b)), after["crossings"].get((a, b))
        lost = r is None or (r["steps"] is None and o is not None and o["steps"] is not None)
        lines.append(f"  {a} -> {b}: " + (f"{fmt(o)}  ->  " if before else "") + fmt(r)
                     + ("   <- CROSSING LOST" if lost and o else ""))
    g0 = f"{before['grass_reachable']}/{before['grass_total']} -> " if before else ""
    lines.append(f"  tall grass reachable/total: {g0}{after['grass_reachable']}/{after['grass_total']}")
    return lines
