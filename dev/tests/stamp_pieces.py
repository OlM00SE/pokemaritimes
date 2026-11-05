"""Building stamp tests (no emulator): mapkit/stamps.py, interiors.py, buildings.py.

1. Catalog: every stamp in stamps.toml loads cleanly from its source map (one door, the
   rectangle on the map), and its interior template can be copied (Plan: the floors rewire;
   a Pokémon Center keeps its upstairs and skips the shared link rooms).
2. Vanilla: on the General + Petalburg towns (Littleroot, Oldale, Petalburg) every door with a
   warp is the door of a recognised stamp, and across vanilla at least the doors counted below.
   A recognised stamp's solid cells match block for block; only walk-behind cells may differ.
3. Round trip: extract -> compile on vanilla towns and ours reproduces every stamp cell, and the
   whole map at least as well as keeping those cells as '#' does (the A/B: stamps cost nothing).
4. Refused: a stamp off the map, overlapping, on the wrong tileset, unknown, drawn wrongly or
   uncovered `B`; a door facing a tree or water; a doormat nothing walkable leads onto.
   Accepted: a General stamp on a Rustboro map.
5. Doors (buildings.plan, in memory): an extracted town's doors are all "unchanged"; a building
   moved 2 tiles keeps its warp index and moves it; a new room is planned from the template,
   with a heal location for a Center; refused: two doors naming one room, a room that belongs
   to another map, a two-floor room named without _1F, two Centers, a warp left inside a
   building.
6. Interior scripts: a Center gets the respawn and the nurse, its upstairs the cable club's map
   scripts; a Mart gets the clerk and the stock; a plain room gets the empty stub.

  python dev/tests/stamp_pieces.py [-v]
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, vanilla_maps, learn, class_adjacency, forbidden_pairs
from mapkit.sketch import Sketch, SketchError, extract, compile_sketch
from mapkit.doors import door_tiles, _upstream_maps
from mapkit import stamps, interiors, buildings

TOWNS = ["LittlerootTown", "OldaleTown", "PetalburgCity"]
OURS = ["HomeTown_0", "Woodstock_2"]
MIN_VANILLA_DOORS = 37           # recognised across vanilla's General maps when this was written
FAILS = []


def check(ok, what):
    print(f"  {'PASS' if ok else 'FAIL'}: {what}")
    if not ok:
        FAILS.append(what)
    return ok


def catalog(p):
    print("1. catalog")
    cat = stamps.catalog(p)
    for st in cat.values():
        check(not st.problems and st.door is not None, f"{st.name}: {st.w}x{st.h}, door {st.door}, "
              f"{st.tileset_note()} {st.problems or ''}")
        try:
            pl = interiors.Plan(p, st.interior, "ZzStampTest", st.kind)
            check(True, f"{st.name}: interior {st.interior} copies as {list(pl.names.values())}")
        except interiors.InteriorError as ex:
            check(False, f"{st.name}: interior {st.interior}: {ex}")
    pc = interiors.Plan(p, cat["pokemon_center"].interior, "ZzStampTest", "pokemon_center")
    check(len(pc.names) == 2 and not any("Union" in v or "Trade" in v for v in pc.names),
          f"a Center copies its two floors, not the shared link rooms: {list(pc.names)}")


def vanilla(p):
    print("2. vanilla")
    total = hit = 0
    for n in sorted(_upstream_maps(p.root)):
        if n not in p.map_names:
            continue
        m = p.load_map(n)
        if m.j.get("map_type") not in ("MAP_TYPE_TOWN", "MAP_TYPE_CITY", "MAP_TYPE_ROUTE") or \
                m.layout.primary != "gTileset_General":
            continue
        found = stamps.recognise(p, m.layout)
        warped = {(w["x"], w["y"]) for w in m.events("warp_events")} & set(door_tiles(p, m))
        doors = {st.door_at(x, y) for st, x, y, _ in found}
        total += len(warped)
        hit += len(warped & doors)
        for st, x, y, kept in found:
            solid = [(dx, dy) for (dx, dy), b in st.cells.items() if (b >> 10) & 3]
            if any(m.layout.get(x + dx, y + dy) != st.cells[(dx, dy)] for dx, dy in solid) or \
                    any((st.cells[(c[0] - x, c[1] - y)] >> 10) & 3 for c in kept):
                check(False, f"{n}: {st.name} at ({x},{y}) recognised with a solid cell that differs")
        if n in TOWNS:
            check(warped <= doors, f"{n}: {len(warped & doors)}/{len(warped)} doors are recognised stamps "
                  f"({', '.join(sorted(st.name for st, *_ in found))})")
    check(hit >= MIN_VANILLA_DOORS, f"{hit}/{total} vanilla doors on General maps recognised (>= {MIN_VANILLA_DOORS})")
    for st in stamps.catalog(p).values():
        e = next(e for e in __import__("tomllib").load(open(stamps.CATALOG, "rb"))["stamp"] if e["name"] == st.name)
        got = [(s.name, x, y, k) for s, x, y, k in stamps.recognise(p, p.load_map(st.source).layout)]
        check((st.name, *e["at"], []) in got, f"{st.name} is recognised where it was cut, unchanged")


def round_trip(p, c, v, rules, forb, verbose):
    print("3. round trip")
    for n in TOWNS + OURS:
        m = p.load_map(n)
        L = m.layout
        sk = extract(p, v, n, rules, forb, c)
        blocks, _ = compile_sketch(p, c, rules, sk, L, v, forb)
        cells = set().union(*(stamps.catalog(p)[pl.name].footprint(pl.x, pl.y) for pl in sk.stamps)) \
            if sk.stamps else set()
        same_cells = all(blocks[y * L.width + x] == L.get(x, y) for x, y in cells)
        kept = Sketch(n, ["".join("#" if ch == stamps.CHAR else ch for ch in row) for row in sk.rows])
        kblocks, _ = compile_sketch(p, c, rules, kept, L, v, forb)
        a = sum(x == y for x, y in zip(blocks, L.blocks))
        b = sum(x == y for x, y in zip(kblocks, L.blocks))
        check(same_cells and a >= b, f"{n}: {len(sk.stamps)} stamps, {len(cells)} cells exact; whole map "
              f"{100 * a / len(blocks):.1f}% with stamps vs {100 * b / len(blocks):.1f}% keeping them")
        if verbose:
            print("     " + "\n     ".join(pl.line() for pl in sk.stamps))


def blank(p, name="GroveLab"):
    """An in-memory copy of a layout, all plain grass, to compile test sketches on."""
    L = copy.copy(p.load_map(name).layout)
    L.blocks = [0x3001] * (L.width * L.height)
    return L


def refused(p, c, rules, forb):
    print("4. refusals")
    L = blank(p)
    w, h = L.width, L.height

    def build(rows, placements, layout=L):
        sk = Sketch("X", rows, placements=placements)
        try:
            compile_sketch(p, c, rules, sk, layout, None, forb, fresh=True)
            return None
        except SketchError as ex:
            return ex

    def sketch_with(placements, tweak=None):
        rows = [["."] * w for _ in range(h)]
        for pl in placements:
            st = stamps.catalog(p).get(pl.name)
            for x, y in (st.footprint(pl.x, pl.y) if st else ()):
                if 0 <= x < w and 0 <= y < h:
                    rows[y][x] = stamps.CHAR
        if tweak:
            tweak(rows)
        return ["".join(r) for r in rows]

    P = stamps.Placement
    ok = [P("pokemon_center", 4, 4), P("lab", 12, 4)]
    check(build(sketch_with(ok), ok) is None, "a Center and a lab with doormat on grass build")
    cases = [
        ("off the map", [P("mart", w - 2, 4)], None, "runs off"),
        ("overlapping", [P("mart", 4, 4), P("house_small", 6, 5)], None, "overlaps"),
        ("unknown", [P("castle", 4, 4)], None, "unknown stamp"),
        ("a cell drawn '.'", [P("mart", 4, 4)], lambda r: r[5].__setitem__(5, "."), "drawn as"),
        ("an uncovered B", [P("mart", 4, 4)], lambda r: r[20].__setitem__(20, "B"), "no stamp covers"),
        ("door facing a tree", [P("mart", 4, 4)], lambda r: [r[y].__setitem__(x, "T") for y in (8, 9) for x in (5, 6)],
         "isn't walkable"),
        ("door facing water", [P("mart", 4, 10)],
         lambda r: [r[y].__setitem__(x, "~") for y in range(14, 19) for x in range(1, 12)], "isn't walkable"),
        ("doormat walled in", [P("lab", 12, 4)],                      # door (16,8), mat (16,9)
         lambda r: [r[y].__setitem__(x, "b") for x, y in ((15, 9), (17, 9), (16, 10))], "doormat"),
    ]
    for what, pls, tweak, needle in cases:
        ex = build(sketch_with(pls, tweak), pls)
        msg = str(ex) if ex else ""
        check(ex is not None and (needle is None or needle in msg), f"refused: {what}: {msg.strip()[:110]}")
    R = blank(p, "Fredericton_0")
    rw, rh = R.width, R.height
    rows = lambda pls: ["".join(stamps.CHAR if any((x, y) in stamps.catalog(p)[q.name].footprint(q.x, q.y) for q in pls)
                                else "." for x in range(rw)) for y in range(rh)]
    ex = build(rows([P("house_oldale", 4, 4)]), [P("house_oldale", 4, 4)], R)
    check(ex is not None and "Petalburg" in str(ex), f"refused: a Petalburg stamp on a Rustboro map: {str(ex).strip()[:90]}")
    check(build(rows([P("pokemon_center", 4, 4)]), [P("pokemon_center", 4, 4)], R) is None,
          "a General stamp (the Center) builds on a Rustboro map")
    sk = Sketch("X", ["." * w] * h)
    sk.place(p, "mart", 4, 4)
    for args, needle in (((p, "mart", 5, 5), "overlaps"), ((p, "mart", w - 1, 4), "runs off"), ((p, "spire", 1, 1), "unknown")):
        try:
            sk.place(*args)
            check(False, f"place() refuses {needle}")
        except ValueError as ex:
            check(needle in str(ex), f"place() refuses: {ex}")


def doors(p, c, v, rules, forb):
    print("5. door plans")
    m = p.load_map("HomeTown_0")
    sk = extract(p, v, "HomeTown_0", rules, forb, c)
    dp = buildings.plan(p, m, sk.stamps)
    check(not dp.problems and len(dp.keeps) == len(sk.stamps) and not dp.moves and not dp.creates,
          f"HomeTown's extracted stamps: {len(dp.keeps)} doors unchanged {dp.problems}")
    first = sk.stamps[0]
    moved = [stamps.Placement(first.name, first.x + 2, first.y, first.interior)] + sk.stamps[1:]
    dp = buildings.plan(p, m, moved)
    i = next(i for i, w in enumerate(m.events("warp_events")) if p.const_to_map.get(w["dest_map"]) == first.interior)
    check(len(dp.moves) == 1 and dp.moves[0][0] == i, f"moved 2 tiles: warp {i} moves {dp.moves[:1]}")
    P = stamps.Placement
    dp = buildings.plan(p, m, [P("pokemon_center", 14, 14, "ZzTest_PokemonCenter_1F"), P("mart", 20, 14, "ZzTest_Mart")])
    check(not dp.problems and len(dp.creates) == 2 and len(dp.heals) == 1,
          f"new rooms planned: {[ip.first for _, ip, _ in dp.creates]}, heal at {dp.heals[0][2] if dp.heals else None}")
    for what, pls, needle in (
            ("two doors, one room", [P("mart", 14, 14, "ZzTest_Mart"), P("mart", 20, 14, "ZzTest_Mart")], "both lead"),
            ("another map's room", [P("mart", 14, 14, "Woodstock_Lab")], "no warp on"),
            ("a two-floor room without _1F", [P("pokemon_center", 14, 14, "ZzTest_Center")], "_1F"),
            ("two Centers", [P("pokemon_center", 14, 14, "ZzA_1F"), P("pokemon_center", 20, 14, "ZzB_1F")], "Centers"),
            ("a warp inside a building", [P("house_small", sk.stamps[0].x + 1, sk.stamps[0].y + 4, None)], "inside")):
        dp = buildings.plan(p, m, pls)
        check(any(needle in s for s in dp.problems), f"refused: {what}: {(dp.problems or ['(none)'])[0][:100]}")


def scripts(p):
    print("6. interior scripts")
    cat = stamps.catalog(p)
    pc = interiors.Plan(p, cat["pokemon_center"].interior, "ZzT_PokemonCenter", "pokemon_center")
    one = interiors.scripts_for(p, pc, pc.template, "ZzT_PokemonCenter_1F", "ZzTown", "test")
    two = interiors.scripts_for(p, pc, list(pc.names)[1], "ZzT_PokemonCenter_2F", "ZzTown", "test")
    check("setrespawn(HEAL_LOCATION_ZZ_TOWN)" in one and "Common_EventScript_PkmnCenterNurse" in one
          and "MAP_SCRIPT_ON_RESUME: CableClub_OnResume" in one, "the Center's ground floor: respawn, nurse, resume")
    code = "\n".join(line for line in two.splitlines() if not line.startswith("//"))
    check("MAP_SCRIPT_ON_FRAME_TABLE: CableClub_OnFrame" in code and "OldaleTown" not in code,
          "upstairs: the cable club's shared map scripts, nothing of Oldale's")
    mart = interiors.Plan(p, cat["mart"].interior, "ZzT_Mart", "mart")
    s = interiors.scripts_for(p, mart, mart.template, "ZzT_Mart", "ZzTown", "test")
    check("pokemart(ZzT_Mart_Stock)" in s and all(i in s for i in interiors.MART_STOCK), "the Mart: clerk and stock")
    plain = interiors.Plan(p, cat["house_small"].interior, "ZzT_House", "plain")
    check(interiors.scripts_for(p, plain, plain.template, "ZzT_House", "ZzTown", "test") is None,
          "a plain room: the empty stub")


def main(argv):
    verbose = "-v" in argv
    p = Project()
    c = Corpus(p)
    v = Vocabulary(p, c)
    entries = vanilla_maps(c)
    rules = learn(p, v, entries)
    forb = forbidden_pairs(class_adjacency(p, v, entries))
    catalog(p)
    vanilla(p)
    round_trip(p, c, v, rules, forb, verbose)
    refused(p, c, rules, forb)
    doors(p, c, v, rules, forb)
    scripts(p)
    print(f"RESULT: {'PASS' if not FAILS else f'{len(FAILS)} failures'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
