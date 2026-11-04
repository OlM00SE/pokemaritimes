"""The corridor plan and its tools (dev/mapkit/geo.py, dev/corridor.py).

  python dev/tests/corridor_plan.py          (no emulator; about a minute: it compiles every
                                              planned map's underlay with mapgen's compiler)

  - projection: km() and lonlat() invert each other; an anchor's world tile is its offset from
    the origin at the plan's scale;
  - connections: a plan built from the game's own map positions derives exactly the game's edge
    connections, offsets included (so the plan's joins mean what map.json means);
  - the plan of record: no errors from `check`; along every join the two maps' underlays (cut
    separately) carry the same river and road across, each run at least 2 wide; cutting a map
    alone gives the same cells as cutting a larger area, so neighbours agree;
  - cleanup: a one-tile tip of water is removed, a one-tile neck widened, a 2-wide river kept;
  - the checker catches: overlapping maps, a map nobody reaches, a map over the engine's size
    limit, a river that stops at a seam;
  - every planned map's underlay compiles with mapgen's compiler.
Exit code 1 on any failure.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit import geo, render
from mapkit.project import Project
import corridor

fails = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


def spec(maps, water=(), road=()):
    return {"projection": {"origin": "Woodstock", "km_per_tile": 0.5},
            "map": maps, "water": list(water), "road": list(road)}


def edge_runs(rows, side):
    col = {"left": [r[0] for r in rows], "right": [r[-1] for r in rows],
           "up": list(rows[0]), "down": list(rows[-1])}[side]
    return col


def main():
    p = Project()
    print("projection:")
    for lon, lat in ((-67.598, 46.152), (-60.194, 46.136), (-64.48, 48.83)):
        lo, la = geo.lonlat(*geo.km(lon, lat))
        check(abs(lo - lon) < 1e-9 and abs(la - lat) < 1e-9, f"lonlat(km({lon}, {lat})) round-trips")
    plan = geo.Plan()
    a = plan.anchors["Fredericton"]
    wx, wy = plan.world(a["lon"], a["lat"])
    kx, ky = geo.km(a["lon"], a["lat"])
    check(abs(wx - (kx - plan.ox) / plan.kpt) < 1e-9 and abs(plan.world(*(
        lambda o: (o["lon"], o["lat"]))(plan.anchors[plan.origin]))[0]) < 1e-9,
          f"the origin ({plan.origin}) is world (0, 0); Fredericton is world ({wx:.1f}, {wy:.1f})")

    print("connections match map.json's meaning:")
    pos, size = render.world_positions(p, "HomeTown_0")
    gplan = geo.Plan(spec=spec([{"name": n, "rect": [x, y, *size[n]]} for n, (x, y) in pos.items()]),
                     geo={"rivers": []})
    derived = {(a, d, b, off) for a, d, b, off, _ in gplan.connections()}
    game = set()
    for n in pos:
        for c in p.load_map(n).connections:
            other = p.const_to_map.get(c["map"])
            if c["direction"] in geo.EDGES and other in pos:
                game.add((n, c["direction"], other, c["offset"]))
    check(derived == game, f"{len(game)} game connections derived exactly from the maps' positions"
          + ("" if derived == game else f": missing {sorted(game - derived)[:3]}, extra {sorted(derived - game)[:3]}"))

    print("the plan of record:")
    errors, warns, _ = corridor.check(plan)
    check(not errors, f"corridor check: {len(errors)} errors {errors[:2]}")
    under = {m["name"]: plan.underlay(m["name"]) for m in plan.maps}
    for a, d, b, off, shared in plan.connections():
        if d not in ("right", "down"):
            continue
        seam = corridor.seam_cells(plan, a, d, b)
        ax, ay, _, _ = plan.rect(plan.by_name[a])
        bx, by, _, _ = plan.rect(plan.by_name[b])
        at = lambda rows, ox, oy, c: rows[c[1] - oy][c[0] - ox]
        for ch, kind in (("~", "water"), ("=", "road")):
            ra = corridor.runs([at(under[a], ax, ay, ca) == ch for _, ca, _ in seam])
            rb = corridor.runs([at(under[b], bx, by, cb) == ch for _, _, cb in seam])
            ok = all(any(r[0] <= o[1] and o[0] <= r[1] for o in rb) for r in ra) and \
                all(any(r[0] <= o[1] and o[0] <= r[1] for o in ra) for r in rb) and \
                all(r[1] - r[0] >= 1 for r in ra + rb)
            check(ok, f"{a}/{b}: {kind} crosses the seam on both sides, 2+ wide ({ra} / {rb})")
    # a map cut alone agrees with a bigger cut around it
    for name in ("Route 202", "Nackawic"):
        x0, y0, w, h = plan.rect(plan.by_name[name])
        alone = plan.clean_water(x0, y0, w, h)
        big = {c for c in plan.clean_water(x0 - 20, y0 - 20, w + 40, h + 40)
               if x0 <= c[0] < x0 + w and y0 <= c[1] < y0 + h}
        check(alone == big, f"{name}: cut alone = cut from a larger area ({len(alone)} water cells)")

    print("cleanup:")
    tip = geo.Plan(spec=spec([{"name": "A", "rect": [0, 0, 20, 12]}],
                             water=[{"name": "w", "world": [[0, 5], [20, 5]], "width": 2}]),
                   geo={"rivers": []})
    base = tip.clean_water(0, 0, 20, 12)
    check(all(sum((x, y) in base for y in range(12)) == 2 for x in range(20)),
          "a straight 2-wide river is left as it is")
    # a one-tile tip below the river, and a one-tile neck in a second river
    tip.water[0]["segs"].append((10.5, 6.5, 10.5, 7.5))
    raw = tip.water_cells(0, 0, 20, 12)
    cleaned = tip.clean_water(0, 0, 20, 12)
    thin = [c for c in cleaned if ((c[0] - 1, c[1]) not in cleaned and (c[0] + 1, c[1]) not in cleaned)
            or ((c[0], c[1] - 1) not in cleaned and (c[0], c[1] + 1) not in cleaned)]
    check((10, 7) in raw and not thin, f"a one-tile tip is cleaned up (thin cells left: {thin[:4]})")
    neck = geo.Plan(spec=spec([{"name": "A", "rect": [0, 0, 20, 12]}],
                              water=[{"name": "w", "world": [[0, 5.5], [20, 5.5]], "width": 1}]),
                    geo={"rivers": []})
    nc = neck.clean_water(0, 0, 20, 12)
    check(all(sum((x, y) in nc for y in range(12)) >= 2 for x in range(20)),
          "a one-tile-wide river is widened to two, all along")

    print("the checker catches:")
    def errs(maps, water=()):
        return corridor.check(geo.Plan(spec=spec(maps, water), geo={"rivers": []}))[0]
    check(any("overlap" in e for e in errs([{"name": "A", "rect": [0, 0, 10, 10]},
                                            {"name": "B", "rect": [5, 5, 10, 10]}])), "overlapping maps")
    check(any("can't be reached" in e for e in errs([{"name": "A", "rect": [0, 0, 10, 10]},
                                                     {"name": "B", "rect": [30, 0, 10, 10]}])),
          "a map nobody reaches")
    check(any("size limit" in e for e in errs([{"name": "A", "rect": [0, 0, 120, 70]}])),
          "a map over the engine's size limit")
    stop = errs([{"name": "A", "rect": [0, 0, 10, 10]}, {"name": "B", "rect": [10, 0, 10, 10]}],
                [{"name": "w", "world": [[0, 5], [9, 5]], "width": 2}])     # ends inside A
    check(any("doesn't continue" in e for e in stop), "a river that stops at a seam")

    print("underlays compile:")
    kit = corridor.build_kit(p)
    for m in plan.maps:
        problems, report = corridor.compile_underlay(plan, m["name"], p, kit)
        check(not problems, f"{m['name']}: builds with mapgen's compiler"
              + (f": {problems[:2]}" if problems else ""))

    print("PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
