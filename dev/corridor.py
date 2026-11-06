"""The corridor plan of record: check it, draw it over real geography, and cut map underlays.

  python dev/corridor.py check               # the plan's problems, its connections and seams
  python dev/corridor.py render              # dev/out/corridor_plan.png
  python dev/corridor.py underlay "Route 202" [-o file.txt]
                                             # a starter sketch for one planned map: the real
                                             # river ('~') and the road ('=') where the plan has
                                             # them, grass ('.') elsewhere
  python dev/corridor.py compile ["Route 202"]
                                             # does each underlay build with mapgen's compiler?
                                             # (a blank in-memory layout of the planned size;
                                             # nothing is written. A reused folder of another
                                             # size must be resized before building in place:
                                             # `check` lists the sizes.)
  python dev/corridor.py join "Route 201" [--apply]
                                             # make the game's connections between this map and
                                             # its built neighbours the plan's (both sides; a
                                             # direction may change). Refused until each map's
                                             # folder has the plan's size (dev/resize_map.py).

The plan is design/region/corridor.toml (world tiles at one km-per-tile scale, origin on an anchor
place). Connections are derived from the rectangles: two maps join where their edges touch.
check exits 1 on an ERROR:
  - maps that overlap, a map nobody can reach, a map over the engine's size limit
    ((w + 15) * (h + 14) <= 10240, fieldmap.c);
  - a river or road whose runs along a seam don't pair up one to one between the two maps,
    with each pair's ends within a tile (it would stop, split or jump sideways at the seam);
  - water at a seam narrower than 2 tiles (shores need 2), or the road at a seam narrower than 2.
Water and road are judged as the underlays draw them (cleaned water; road only where it isn't
water). WARN: water or road touching the end of a seam (the neighbour's land beyond won't
match), the road meeting a map edge with no neighbour or outside the joined stretch, the road
with no verge from water, the road crossing water (a bridge for the map's design).
With the game (the default) it also lists each reused folder's size against the plan's.
It also lists the joins that differ from the game's current connections: the changes the plan
asks for, made as each map is built.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.geo import Plan, ROOT, EDGES, lonlat

OUT = os.path.join(ROOT, "dev", "out")
MAX_MAP_DATA = 10240                     # include/fieldmap.h; checked as (w + 15) * (h + 14)


def runs(flags):
    """[(start, end)] inclusive runs of True in a list."""
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - 1)); start = None
    return out


def seam_cells(plan, a, d, b):
    """For the join a -d-> b: the world coordinate along the seam for each shared step, and the
    two edge cells (a's last row/column, b's first) at each."""
    ax, ay, aw, ah = plan.rect(plan.by_name[a])
    bx, by, bw, bh = plan.rect(plan.by_name[b])
    if d in ("left", "right"):
        lo, hi = max(ay, by), min(ay + ah, by + bh)
        ea, eb = (ax + aw - 1, bx) if d == "right" else (ax, bx + bw - 1)
        return [(t, (ea, t), (eb, t)) for t in range(lo, hi)]
    lo, hi = max(ax, bx), min(ax + aw, bx + bw)
    ea, eb = (ay + ah - 1, by) if d == "down" else (ay, by + bh - 1)
    return [(t, (t, ea), (t, eb)) for t in range(lo, hi)]


SEAM_SLACK = 1      # tiles: a diagonal river legitimately moves this much between two columns


def seam_mismatches(ra, rb):
    """The two maps' runs (of water or road) along one seam must pair up one to one, each pair's
    ends within SEAM_SLACK tiles: otherwise the river or road jumps sideways at the connection, or
    splits, or stops. Returns problem strings (empty when they match)."""
    out = []
    for mine, other, side in ((ra, rb, "{a}"), (rb, ra, "{b}")):
        for r in mine:
            hits = [o for o in other if r[0] <= o[1] + SEAM_SLACK and o[0] <= r[1] + SEAM_SLACK]
            span = f"steps {r[0]}..{r[1]}"
            if not hits:
                out.append(f"on {side}'s side at {span} doesn't continue across")
            elif len(hits) > 1:
                out.append(f"on {side}'s side at {span} meets {len(hits)} runs on the other side")
            elif abs(hits[0][0] - r[0]) > SEAM_SLACK or abs(hits[0][1] - r[1]) > SEAM_SLACK:
                out.append(f"on {side}'s side at {span} doesn't line up with steps "
                           f"{hits[0][0]}..{hits[0][1]} across the seam")
    return list(dict.fromkeys(out))


def folders(plan):
    """{planned map name: game folder} for the maps that have one."""
    return {m["name"]: m["map"] for m in plan.maps if m.get("map", "new") != "new"}


def edge_joins(project, folder, among):
    """The game's edge connections (not dive/emerge) from `folder` to folders in `among`:
    [(other folder, direction, offset)]."""
    out = []
    for c in project.load_map(folder).connections:
        other = project.const_to_map.get(c["map"])
        if other in among and c["direction"] in EDGES:
            out.append((other, c["direction"], int(c["offset"])))
    return out


def check(plan, project=None):
    """Returns (errors, warnings, report lines)."""
    errors, warns, lines = [], [], []
    for a, b in plan.overlaps():
        errors.append(f"{a} and {b} overlap")
    for m in plan.maps:
        x, y, w, h = plan.rect(m)
        if (w + 15) * (h + 14) > MAX_MAP_DATA:
            errors.append(f"{m['name']} is {w}x{h}: over the engine's map size limit")
    conns = plan.connections()
    graph = {m["name"]: set() for m in plan.maps}
    for a, d, b, off, shared in conns:
        graph[a].add(b)
    seen, stack = {plan.maps[0]["name"]}, [plan.maps[0]["name"]]
    while stack:
        for o in graph[stack.pop()]:
            if o not in seen:
                seen.add(o); stack.append(o)
    for m in plan.maps:
        if m["name"] not in seen:
            errors.append(f"{m['name']} can't be reached from {plan.maps[0]['name']}")

    # cells of every map as its underlay draws them: cleaned water, and the road where it isn't
    # water
    cells = {}
    for m in plan.maps:
        x0, y0, w, h = plan.rect(m)
        cells[m["name"]] = (plan.clean_water(x0, y0, w, h), plan.road_on_land(x0, y0, w, h))
    water = {c for wc, _ in cells.values() for c in wc}
    road = {c for _, rc in cells.values() for c in rc}
    for name, (wc, rc) in cells.items():
        # road against water with no verge: the grammar gives water a grass margin, which would
        # eat the road there
        touch = sorted(c for c in rc if any(
            (c[0] + dx, c[1] + dy) in wc for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
        if touch:
            warns.append(f"{name}: the road touches water with no verge at {len(touch)} cells, "
                         f"e.g. {touch[:3]}")
        # the drawn road crossing water: the map's design must bridge it
        wet = sorted(set(plan.road_cells(*plan.rect(plan.by_name[name]))) & wc)
        if wet:
            warns.append(f"{name}: the road crosses water at {len(wet)} cells, e.g. {wet[:3]} "
                         "(a bridge for the map's design)")

    lines.append("Connections (derived from the rectangles):")
    for a, d, b, off, shared in conns:
        if d not in ("right", "down"):
            continue                     # each join once; the reverse is implied
        seam = seam_cells(plan, a, d, b)
        lines.append(f"  {a} -{d}-> {b}: offset {off}, {shared} tiles shared")
        for kind, layer in (("water", water), ("road", road)):
            ra = runs([ca in layer for _, ca, _ in seam])
            rb = runs([cb in layer for _, _, cb in seam])
            coord = lambda r: f"{seam[r[0]][0]}..{seam[r[1]][0]}"
            if ra or rb:
                lines.append(f"      {kind}: {a} {[coord(r) for r in ra]}, {b} {[coord(r) for r in rb]}")
            for problem in seam_mismatches(ra, rb):
                errors.append(f"{a}/{b} seam: {kind} " + problem.format(a=a, b=b))
            for side, mine in ((a, ra), (b, rb)):
                for r in mine:
                    if r[1] - r[0] + 1 < 2:
                        errors.append(f"{a}/{b} seam: {kind} at {coord(r)} on {side}'s side is "
                                      "1 tile wide (needs 2)")
                    if r[0] == 0 or r[1] == len(seam) - 1:
                        warns.append(f"{a}/{b} seam: {kind} at {coord(r)} touches the end of the "
                                     "seam")
    # the road leaving a map where there's no neighbour
    for m in plan.maps:
        x0, y0, w, h = plan.rect(m)
        rc = cells[m["name"]][1]
        joined = {d for a, d, b, _, _ in conns if a == m["name"]}
        edges = {"up": [(x, y0) for x in range(x0, x0 + w)],
                 "down": [(x, y0 + h - 1) for x in range(x0, x0 + w)],
                 "left": [(x0, y) for y in range(y0, y0 + h)],
                 "right": [(x0 + w - 1, y) for y in range(y0, y0 + h)]}
        for d, edge in edges.items():
            hits = [c for c in edge if c in rc]
            if not hits:
                continue
            if d not in joined:
                warns.append(f"{m['name']}: the road meets the {d} edge at {hits[0]} with no "
                             "neighbour there")
                continue
            # joined on that edge, but is this stretch inside a shared range?
            shared = {cb for a, dd, b, _, _ in conns if a == m["name"] and dd == d
                      for _, cb, _ in seam_cells(plan, a, dd, b)}
            loose = [c for c in hits if c not in shared]
            if loose:
                warns.append(f"{m['name']}: the road meets the {d} edge at {loose[0]}, outside "
                             "the part joined to a neighbour")
    # anchors
    # The river is drawn many times its real width (6-11 tiles = 3-5 km), so a riverside town's
    # real point often falls in the drawn water: reported, not warned. Anchors not fitted (an
    # inset's provisional spot) aren't placed.
    lines.append("Anchor places:")
    for name, a in plan.anchors.items():
        if not a.get("fit", True):
            continue
        wx, wy = plan.world(a["lon"], a["lat"])
        c = (math.floor(wx), math.floor(wy))
        host = [m["name"] for m in plan.maps if not m.get("inset")
                and plan.rect(m)[0] <= c[0] < plan.rect(m)[0] + plan.rect(m)[2]
                and plan.rect(m)[1] <= c[1] < plan.rect(m)[1] + plan.rect(m)[3]]
        if host:
            lines.append(f"  {name:<14} world ({wx:6.1f}, {wy:6.1f}) in {host[0]}"
                         + (", in the drawn water (the design puts it on the bank)"
                            if c in water else ""))
    # against the game as it is
    if project is not None:
        lines.append("Changes to the game's connections the plan asks for:")
        folder = folders(plan)
        planned = {(folder[a], d, folder[b], off) for a, d, b, off, _ in conns
                   if a in folder and b in folder}
        current = {(f, d, other, off) for f in folder.values()
                   for other, d, off in edge_joins(project, f, set(folder.values()))}
        for a, d, b, off in sorted(planned - current):
            lines.append(f"  add    {a} -{d}-> {b} offset {off}")
        for a, d, b, off in sorted(current - planned):
            lines.append(f"  remove {a} -{d}-> {b} offset {off}")
        news = [m["name"] for m in plan.maps if m.get("map", "new") == "new"]
        if news:
            lines.append(f"  new maps: {', '.join(news)} (their joins come when they're created)")
        lines.append("Map sizes (a reused folder is resized to the plan when it's rebuilt):")
        for m in plan.maps:
            if m.get("map", "new") == "new":
                continue
            L = project.load_map(m["map"]).layout
            w, h = plan.rect(m)[2:]
            lines.append(f"  {m['map']:<14} {L.width}x{L.height}"
                         + ("  matches the plan" if (L.width, L.height) == (w, h)
                            else f"  -> {w}x{h} (resize before building the underlay in place)"))
    return errors, warns, lines


def join_plan(plan, name, project):
    """The game's connections between a planned map and the other built maps of the plan, made as
    the plan derives them. Returns (changes, new map.json dicts by folder, problems). Between the
    map and each built planned map, every edge connection is replaced by the plan's join, or
    removed when the plan doesn't put the two side by side (a direction can change, as HomeTown's
    did from down to right); dive/emerge links and connections to maps outside the plan are kept."""
    import json
    from mapkit.geo import OPPOSITE
    folder = folders(plan)
    if name not in folder:
        return [], {}, [f"{name} has no game folder yet"]
    problems, changes, jsons = [], [], {}
    joins = {b: (d, off) for a, d, b, off, _ in plan.connections() if a == name and b in folder}

    def load(f):
        if f not in jsons:
            with open(project.path("data/maps", f, "map.json"), encoding="utf-8") as fh:
                jsons[f] = json.load(fh)
        return jsons[f]

    for n in [name] + list(joins):
        L = project.load_map(folder[n]).layout
        w, h = plan.rect(plan.by_name[n])[2:]
        if (L.width, L.height) != (w, h):
            problems.append(f"{folder[n]} is {L.width}x{L.height}, the plan's {n} is {w}x{h}: "
                            f"resize it first (dev/resize_map.py {folder[n]} {w}x{h})")
    me = folder[name]
    built = set(folder.values())
    linked = {other for other, _, _ in edge_joins(project, me, built)}
    others = [folder[b] for b in joins] + sorted(linked - {folder[b] for b in joins} - {me})
    for fb in others:
        b = next(n for n, f in folder.items() if f == fb)
        want = joins.get(b)                        # None: the plan doesn't join them
        sides = [(me, fb, want)] + [(fb, me, (OPPOSITE[want[0]], -want[1]) if want else None)]
        for f, other, w in sides:
            j = load(f)
            const = project.load_map(other).id
            conns = j.get("connections") or []
            old = [c for c in conns if c["map"] == const and c["direction"] in EDGES]
            if [(c["direction"], int(c["offset"])) for c in old] == ([w] if w else []):
                continue
            at = conns.index(old[0]) if old else len(conns)
            keep = [c for c in conns if c not in old]
            if w:
                keep.insert(min(at, len(keep)), {"map": const, "offset": w[1], "direction": w[0]})
            j["connections"] = keep
            was = ", ".join(f"{c['direction']} {c['offset']}" for c in old) or "none"
            changes.append(f"{f} -> {other}: {was}  =>  " + (f"{w[0]} {w[1]}" if w else "removed"))
    return changes, {f: j for f, j in jsons.items()
                     if any(c.startswith(f + " ->") for c in changes)}, problems


def join_apply(project, jsons):
    from mapkit.mapjson import dump_json
    from mapkit.transaction import edit
    with edit(project, [f"data/maps/{f}/map.json" for f in jsons]):
        for f, j in jsons.items():
            dump_json(project.path("data/maps", f, "map.json"), j)


BLANK_LIKE = "Route201_1"               # a General + Petalburg outdoor layout to compile against


def compile_underlay(plan, name, project, kit=None):
    """Compile the map's underlay with mapgen's compiler on a blank in-memory layout of the
    planned size (nothing is written). Returns (problems, report); problems is [] when it
    builds. kit: (corpus, vocab, rules, forbidden), shared across maps."""
    import copy
    from mapkit.sketch import Sketch, SketchError, compile_sketch
    from mapkit.layout import pack
    corpus, vocab, rules, forbidden = kit or build_kit(project)
    x0, y0, w, h = plan.rect(plan.by_name[name])
    L = copy.copy(project.load_map(BLANK_LIKE).layout)
    L.width, L.height = w, h
    L.blocks = [pack(1, 0, 3)] * (w * h)          # plain grass; only '#' cells would read it
    sk = Sketch(name, plan.underlay(name))
    try:
        _, report = compile_sketch(project, corpus, rules, sk, L, vocab, forbidden, fresh=True)
    except SketchError as ex:
        return [(x0 + x, y0 + y, m) for x, y, m in ex.problems], {}
    return [], report


def build_kit(project):
    from mapkit.corpus import Corpus
    from mapkit.terrain import Vocabulary
    from mapgen import vanilla_maps, learn, forbidden_pairs, class_adjacency
    corpus = Corpus(project)
    vocab = Vocabulary(project, corpus)
    entries = vanilla_maps(corpus)
    return corpus, vocab, learn(project, vocab, entries), \
        forbidden_pairs(class_adjacency(project, vocab, entries))


def render(plan, path):
    from blueprint import Canvas, font
    from mapkit.geo import load_geo
    geo = load_geo()
    xs = [v for m in plan.maps for v in (plan.rect(m)[0], plan.rect(m)[0] + plan.rect(m)[2])]
    ys = [v for m in plan.maps for v in (plan.rect(m)[1], plan.rect(m)[1] + plan.rect(m)[3])]
    (kx0, ky0), (kx1, ky1) = plan.to_km(min(xs) - 6, min(ys) - 6), plan.to_km(max(xs) + 6, max(ys) + 6)
    lon0, lat1 = lonlat(kx0, ky0)
    lon1, lat0 = lonlat(kx1, ky1)
    ppt = 6                                   # pixels per tile
    cv = Canvas((lon0, lat0, lon1, lat1), ppt / plan.kpt, 34)
    cv.geography(geo, 3)
    f, fb = font(13), font(18)
    tile = lambda x, y: (*cv.p(*plan.to_km(x, y)), *cv.p(*plan.to_km(x + 1, y + 1)))
    for m in plan.maps:
        x0, y0, w, h = plan.rect(m)
        p0, p1 = cv.p(*plan.to_km(x0, y0)), cv.p(*plan.to_km(x0 + w, y0 + h))
        box = tuple(int(round(v)) for v in (*p0, *p1))
        cv.d.rectangle(box, fill=(255, 255, 255, 120 if m.get("inset") else 90))
        for c in plan.road_cells(x0, y0, w, h):
            cv.d.rectangle(tile(*c), fill=(196, 160, 96, 255))
        for c in plan.clean_water(x0, y0, w, h):
            cv.d.rectangle(tile(*c), fill=(60, 110, 210, 255))
        if m.get("inset"):
            cv.rect_dashed(box, (120, 60, 160, 255), 2)
        else:
            cv.d.rectangle(box, outline=(30, 30, 30, 255), width=2)
        new = m.get("map", "new") == "new"
        label = f"{m['name']}  {w}x{h}" + ("  (new)" if new else f"  [{m['map']}]") \
            + ("  inset: zoomed in" if m.get("inset") else "")
        cv.text((box[0] + 4, box[1] + 3), label, f, (110, 40, 140) if m.get("inset") else (20, 20, 20))
    for name, a in plan.anchors.items():
        wx, wy = plan.world(a["lon"], a["lat"])
        if a.get("fit", True) and min(xs) - 6 <= wx <= max(xs) + 6 and min(ys) - 6 <= wy <= max(ys) + 6:
            cv.anchor(a, fb, 5)
    cv.text((cv.m, 6), f"Corridor plan: {plan.kpt} km per tile; water from real data (inset water "
                       "drawn by hand), road in tan; the start valley is an inset over the border", fb)
    cv.scale_bar(10, f)
    cv.img.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "render", "underlay", "compile", "join"))
    ap.add_argument("name", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--no-game", action="store_true", help="check: skip the game comparison")
    ap.add_argument("--apply", action="store_true", help="join: write the map.json files")
    a = ap.parse_args()
    plan = Plan()
    os.makedirs(OUT, exist_ok=True)
    if a.cmd == "check":
        project = None
        if not a.no_game:
            from mapkit.project import Project
            project = Project()
        errors, warns, lines = check(plan, project)
        print("\n".join(lines))
        for w in warns:
            print("WARN ", w)
        for e in errors:
            print("ERROR", e)
        print(f"{len(plan.maps)} maps, {len(errors)} errors, {len(warns)} warnings")
        return 1 if errors else 0
    if a.cmd == "render":
        path = a.out or os.path.join(OUT, "corridor_plan.png")
        render(plan, path)
        print("wrote", os.path.relpath(path, ROOT))
        return 0
    if a.name is not None and a.name not in plan.by_name:
        ap.error(f"{a.name!r} isn't a planned map; the plan has: "
                 + ", ".join(f'"{n}"' for n in plan.by_name))
    if a.cmd == "join":
        if a.name is None:
            ap.error('join needs a planned map, e.g. join "Route 201"')
        from mapkit.project import Project
        project = Project()
        changes, jsons, problems = join_plan(plan, a.name, project)
        for c in changes:
            print("  " + c)
        for pr in problems:
            print("  REFUSED: " + pr)
        if problems:
            print("NOT APPLIED")
            return 1
        if not changes:
            print(f"{a.name}: the game's joins already match the plan")
            return 0
        if a.apply:
            join_apply(project, jsons)
            print(f"applied {len(changes)} change(s); rebuild, and re-render the seams")
        else:
            print("dry run; pass --apply to write")
        return 0
    if a.cmd == "compile":
        from mapkit.project import Project
        project = Project()
        kit = build_kit(project)
        names = [a.name] if a.name else list(plan.by_name)
        bad = 0
        for n in names:
            problems, report = compile_underlay(plan, n, project, kit)
            if problems:
                bad += 1
                print(f"{n}: NOT BUILT, {len(problems)} problem(s) (world x, y):")
                for x, y, msg in problems[:12]:
                    print(f"    ({x},{y}) {msg}")
            else:
                print(f"{n}: builds; {report.get('shore_tiles', 0)} shore tiles, "
                      f"{len(report.get('grammar_repairs', {}))} grammar repairs")
        return 1 if bad else 0
    if a.name is None:
        ap.error("underlay needs a planned map: " + ", ".join(f'"{n}"' for n in plan.by_name))
    m = plan.by_name[a.name]
    rows = plan.underlay(a.name)
    path = a.out or os.path.join(OUT, a.name.replace(" ", "") + "_underlay.txt")
    # `// map:` makes the sketch buildable with mapgen, which needs the folder at the planned
    # size; a reused folder that isn't yet is named in a plain comment instead
    header, note = None, None
    w, h = plan.rect(m)[2:]
    if m.get("map", "new") != "new":
        from mapkit.project import Project
        L = Project().load_map(m["map"]).layout
        if (L.width, L.height) == (w, h):
            header = f"// map: {m['map']}"
        else:
            note = (f"// for {m['map']}, which is {L.width}x{L.height}: resize it to {w}x{h} "
                    "before building this in place")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for line in (header, note,
                     f"// underlay of {a.name} from design/region/corridor.toml, world rect {m['rect']}"):
            if line:
                fh.write(line + "\n")
        fh.write("\n".join(rows) + "\n")
    print("\n".join(rows))
    if note:
        print(note[3:])
    print("wrote", os.path.relpath(path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
