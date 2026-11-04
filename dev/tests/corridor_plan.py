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
import os, sys
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


def thin_cells(cells):
    """Water cells one tile wide across (land both sides, either axis)."""
    return [c for c in cells if ((c[0] - 1, c[1]) not in cells and (c[0] + 1, c[1]) not in cells)
            or ((c[0], c[1] - 1) not in cells and (c[0], c[1] + 1) not in cells)]


def connected4(cells):
    cells = set(cells)
    if not cells:
        return True
    start = next(iter(cells))
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in cells and n not in seen:
                seen.add(n); stack.append(n)
    return seen == cells


def line_plan(water=(), road=(), rect=(0, 0, 24, 16)):
    return geo.Plan(spec=spec([{"name": "A", "rect": list(rect)}], water, road), geo={"rivers": []})


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
            bad = corridor.seam_mismatches(ra, rb)
            ok = not bad and all(r[1] - r[0] >= 1 for r in ra + rb)
            check(ok, f"{a}/{b}: {kind} pairs up across the seam within a tile, 2+ wide "
                      f"({ra} / {rb}){' ' + str(bad) if bad else ''}")
    # every map cut alone agrees with cuts from larger windows, shifted differently
    for m in plan.maps:
        x0, y0, w, h = plan.rect(m)
        alone = plan.clean_water(x0, y0, w, h)
        same = True
        for dx0, dy0, dx1, dy1 in ((20, 20, 20, 20), (3, 11, 17, 5)):
            big = plan.clean_water(x0 - dx0, y0 - dy0, w + dx0 + dx1, h + dy0 + dy1)
            same &= alone == {c for c in big if x0 <= c[0] < x0 + w and y0 <= c[1] < y0 + h}
        check(same, f"{m['name']}: cut alone = cut from two larger windows ({len(alone)} water cells)")

    print("cleanup:")
    straight = line_plan([{"name": "w", "world": [[0, 5], [24, 5]], "width": 2}])
    base = straight.clean_water(0, 0, 24, 16)
    check(all(sum((x, y) in base for y in range(16)) == 2 for x in range(24)),
          "a straight 2-wide river is left as it is")
    tip = line_plan([{"name": "w", "world": [[0, 5], [24, 5]], "width": 2},
                     {"name": "t", "world": [[10.5, 6.5], [10.5, 7.5]], "width": 1}])
    raw = tip.water_cells(0, 0, 24, 16)
    cleaned = tip.clean_water(0, 0, 24, 16)
    check((10, 7) in raw and not thin_cells(cleaned),
          f"a one-tile spur is made buildable (thin cells left: {thin_cells(cleaned)[:4]})")
    neck = line_plan([{"name": "w", "world": [[0, 5.5], [24, 5.5]], "width": 1}])
    nc = neck.clean_water(0, 0, 24, 16)
    check(all(sum((x, y) in nc for y in range(16)) >= 2 for x in range(24)) and not thin_cells(nc),
          "a one-tile-wide river is widened to two, all along")
    # passing through the map, as rivers do (its own ends are well outside)
    diag = line_plan([{"name": "w", "world": [[-20, -20], [36, 36]], "width": 0.8}], rect=(0, 0, 16, 16))
    draw = diag.water_cells(0, 0, 16, 16)
    dc = diag.clean_water(0, 0, 16, 16)
    around = diag.clean_water(-4, -4, 24, 24)          # judge thinness with the neighbours outside
    thin = [c for c in thin_cells(around) if 0 <= c[0] < 16 and 0 <= c[1] < 16]
    check(len(draw) >= 14 and not connected4(draw) and len(dc) >= len(draw) and connected4(dc)
          and not thin, f"a one-tile diagonal river is kept and joined edge to edge "
                        f"({len(draw)} cells drawn, {len(dc)} after, thin {thin[:3]})")
    guarded = line_plan([{"name": "w", "world": [[0, 5.5], [24, 5.5]], "width": 1}],
                        [{"name": "r", "world": [[0, 4.5], [24, 4.5]], "width": 1},
                         {"name": "r2", "world": [[0, 6.5], [24, 6.5]], "width": 1}])
    gr = guarded.clean_water(0, 0, 24, 16)
    road = set(guarded.road_cells(0, 0, 24, 16))
    check(not (gr & road), "cleanup never turns road into water (a thin river between two roads)")

    print("seam matching:")
    check(bool(corridor.seam_mismatches([(0, 5)], [(5, 10)])), "a river jumping sideways at a seam")
    check(bool(corridor.seam_mismatches([(0, 9)], [(0, 3), (6, 9)])), "a river splitting at a seam")
    check(not corridor.seam_mismatches([(3, 8)], [(4, 9)]), "a diagonal river's 1-tile shift is fine")

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
    plan2 = geo.Plan(spec=spec([{"name": "A", "rect": [0, 0, 10, 12]}, {"name": "B", "rect": [10, 0, 10, 12]}],
                               [{"name": "w", "world": [[5, 0], [5, 12]], "width": 4}],
                               [{"name": "r", "world": [[0, 6], [20, 6]], "width": 2}]),
                     geo={"rivers": []})
    errs2, warns2, _ = corridor.check(plan2)
    check(any("crosses water" in w for w in warns2) and not errs2,
          f"the road crossing water is flagged as a bridge to design ({warns2[:1]}, errors {errs2[:1]})")

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
