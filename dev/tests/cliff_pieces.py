"""Cliff vocabulary tests (no emulator).

1. Shapes: small sketches with levels that must build (with the expected pieces) or must be
   refused (with the expected reason): plateaus with faces 1-3 rows tall, inside corners, stairs
   one and two wide, a ledge running under a wall, a graded road; refused: stairs in a flank or
   three wide, a pinched wall, a wall with low ground on both sides, levels meeting on open
   ground, a cliff touching water.
2. Vanilla agreement: every pair of pieces the resolver puts side by side (in the shapes and on
   CliffLab) is a pair vanilla's 238 General layouts put side by side the same way, and every
   piece's attributes are vanilla's modal ones.
3. Sketch files: the `// level:` lines survive save -> load.
4. Round trip: extract -> compile on CliffLab and Route 202 (cliffs come back as kept '#') leaves
   every block unchanged.

  python dev/tests/cliff_pieces.py [-v]
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import PRIMARY
from mapkit import cliffs, ledges
from mapkit.sketch import Sketch, CHAR_TO_CLASS, assign_tree_quarters

C = cliffs


def sketch(rows, levels):
    """rows: sketch strings; levels: strings of digits (one per row) or None for all 0."""
    return [list(r) for r in rows], ([[int(c) for c in r] for r in levels] if levels
                                     else [[0] * len(rows[0]) for _ in rows])


def build(rows, levels):
    """The pieces the resolver and the level check give a shape, or the errors."""
    chars, lv = sketch(rows, levels)
    w, h = len(chars[0]), len(chars)
    pieces, errors = cliffs.resolve(chars, lv, w, h)
    if errors:
        return pieces, errors
    lp, lerr = ledges.resolve(chars, w, h, cliffs.runs_into(chars, w, h, lambda x, y: not (0 <= x < w and 0 <= y < h)))
    if lerr:
        return pieces, lerr
    cls = [[CHAR_TO_CLASS[ch] for ch in r] for r in chars]
    assign_tree_quarters(cls, w, h)
    return {**pieces, **lp}, cliffs.level_issues(cls, lv, w, h)


PLATEAU = ([".......",
            ".^^^^^.",
            ".^...^.",
            ".^^^^^.",
            "......."],
           ["0000000",
            "0111110",
            "0111110",
            "0111110",
            "0000000"])
FACE2 = ([".......",
          ".^^^^^.",
          ".^...^.",
          ".^^^^^.",
          ".^^^^^.",
          "......."],
         ["0000000",
          "0111110",
          "0111110",
          "0111110",
          "0111110",
          "0000000"])
FACE3 = ([".......",
          ".^^^^^.",
          ".^...^.",
          ".^^^^^.",
          ".^^^^^.",
          ".^^^^^.",
          "......."],
         ["0000000", "0111110", "0111110", "0111110", "0111110", "0111110", "0000000"])
# a three-row face that runs off the map on both sides (no flank to end against)
FACE3_OFF = ([".....", "^^^^^", "^^^^^", "^^^^^", "....."],
             ["11111", "11111", "11111", "11111", "00000"])
# an L: high ground north and west; the low corner in the south-east (face two rows)
INSIDE = ([".........",
           ".........",
           "...^^^^^^",
           "...^^^^^^",
           "...^.....",
           "...^.....",
           "...^....."],
          ["111111111",
           "111111111",
           "111111111",
           "111111111",
           "111100000",
           "111100000",
           "111100000"])
# a plus: the rims' inside corners (0BE, 0BF) and the faces' (089, 074)
PLUS = ([".............",
         "....^^^^^....",
         "....^...^....",
         ".^^^^...^^^^.",
         ".^.........^.",
         ".^^^^...^^^^.",
         "....^...^....",
         "....^^^^^....",
         "............."],
        ["0000000000000",
         "0000111110000",
         "0000111110000",
         "0111111111110",
         "0111111111110",
         "0111111111110",
         "0000111110000",
         "0000111110000",
         "0000000000000"])
STAIRS = (["...........",
           ".^^^^^^^^^.",
           ".^.......^.",
           ".^^%%^^%^^.",
           ".^^%%^^%^^.",
           "..........."],
          ["00000000000",
           "01111111110",
           "01111111110",
           "01111111110",
           "01111111110",
           "00000000000"])
LEDGE = ([".........",
          ".^^^^^^^.",
          ".^.....^.",
          ".^^vvv^^.",
          ".........",
          "........."],
         ["000000000",
          "011111110",
          "011111110",
          "011111110",
          "000000000",
          "000000000"])
# a road down through a cutting in a one-row face: the cut cell takes the lower level, so the
# face ends in its foot corners on both sides
ROAD = (["..=..",
         "^^=^^",
         "..=.."],
        ["11111",
         "11011",
         "00000"])

CASES = [
    ("plateau, one-row face", *PLATEAU,
     {(1, 1): C.RIM_NW, (3, 1): C.RIM, (5, 1): C.RIM_NE, (1, 2): C.FLANK_W, (5, 2): C.FLANK_E,
      (1, 3): C.FOOT_W, (3, 3): C.FACE1, (5, 3): C.FOOT_E}),
    ("two-row face", *FACE2,
     {(1, 3): C.FLANK_W, (2, 3): C.FACE_TOP_W, (3, 3): C.FACE_TOP, (4, 3): C.FACE_TOP_E,
      (5, 3): C.FLANK_E, (1, 4): C.FOOT_W, (3, 4): C.FACE_BOTTOM, (5, 4): C.FOOT_E}),
    ("three-row face off the map", *FACE3_OFF,
     {(0, 1): C.FACE_TOP, (2, 2): C.FACE_MID, (4, 3): C.FACE_BOTTOM}),
    ("three-row face against flanks", *FACE3, "more than two rows"),
    ("two-row face one column wide", [".....", ".^^^.", ".^.^.", ".^^^.", ".^^^.", "....."],
     ["00000", "01110", "01110", "01110", "01110", "00000"], "two columns"),
    ("inside corner under a tall face", *INSIDE,
     {(3, 2): C.FACE_TOP, (3, 3): C.INNER["SE"], (3, 4): C.FLANK_E, (4, 2): C.FACE_TOP,
      (4, 3): C.FACE_BOTTOM}),
    ("plus: rim and face inside corners", *PLUS,
     {(4, 3): C.INNER["NW"], (8, 3): C.INNER["NE"], (4, 5): C.INNER["SW"], (8, 5): C.INNER["SE"],
      (1, 3): C.RIM_NW, (11, 3): C.RIM_NE, (1, 5): C.FOOT_W, (11, 5): C.FOOT_E}),
    ("stairs two and one wide", *STAIRS,
     {(3, 3): C.STAIR_L, (4, 3): C.STAIR_R, (3, 4): C.STAIR_L, (4, 4): C.STAIR_R, (7, 3): C.STAIR_L,
      (7, 4): C.STAIR_L, (2, 3): C.FACE_TOP_W, (6, 3): C.FACE_TOP, (5, 4): C.FACE_BOTTOM}),
    ("a ledge in a face runs under the walls", *LEDGE,
     {(3, 3): ledges.ROW["mid"], (5, 3): ledges.ROW["mid"], (2, 3): C.FACE1, (6, 3): C.FACE1}),
    ("a graded road through a cutting", *ROAD,
     {(1, 1): C.FOOT_E, (3, 1): C.FOOT_W, (0, 1): C.FACE1, (4, 1): C.FACE1}),
    ("stairs in a flank", [".....", ".^^^.", ".%.^.", ".^^^.", "....."],
     ["00000", "01110", "01110", "01110", "00000"], "south face"),
    ("stairs three wide", [".......", ".^^^^^.", ".^...^.", ".%%%^^.", "......."],
     ["0000000", "0111110", "0111110", "0111110", "0000000"], "one or two columns"),
    ("stairs with nothing below", [".....", ".^^^.", ".^.^.", ".^%^.", ".^^^."],
     ["00000", "01110", "01110", "01110", "01110"], "foot of the stairs"),
    ("a wall between low ground", [".....", ".^^^.", "....."], ["00000", "01110", "00000"],
     "both sides"),
    ("levels meet on open ground", ["....", "....", "...."], ["1100", "1100", "0000"], "open ground"),
    ("levels meet across a road and grass", ["..=.", "..=.", "...."], ["1111", "0011", "0000"],
     "open ground"),
    ("a cliff touching water", [".....", ".^^^.", ".^.^.", ".^^^.", ".~~~.", ".~~~."],
     ["00000", "01110", "01110", "01110", "00000", "00000"], "touches water"),
]


def shapes(verbose):
    bad, made = 0, []
    for name, rows, levels, want in CASES:
        pieces, errors = build(rows, levels)
        if isinstance(want, str):
            ok = any(want in m for _, _, m in errors)
            detail = errors[:1] if errors else "built, but should have been refused"
        else:
            ok = not errors and all(pieces.get(xy) == m for xy, m in want.items())
            detail = errors[:2] or {f"{k}": f"{v:03X}" for k, v in pieces.items() if want.get(k, v) != v}
            if not errors:
                made.append((rows, pieces))
        bad += not ok
        if not ok or verbose:
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail if not ok else ''}")
    # a pinched wall (low ground on two diagonals, high all round) can't be drawn without other
    # errors first, so the rule is asked directly
    _, why = cliffs.piece_for({"N": "high", "S": "wall", "W": "wall", "E": "wall"},
                              {"NW": "low", "NE": "high", "SW": "high", "SE": "low"})
    pinched = bool(why) and "pinched" in why
    bad += not pinched
    if not pinched or verbose:
        print(f"  {'ok  ' if pinched else 'FAIL'} a pinched wall: {why}")
    # a graded road climbs one level at a time beside a wall (a cutting); asked directly too
    road = lambda cls, lv: cliffs.level_issues(cls, lv, len(cls[0]), len(cls))
    roads = [("road one level beside a wall", [["CL", "P"], ["CL", "P"]], [[1, 1], [1, 0]], False),
             ("road one level in the open (trees beside it, no wall)", [["T", "P"], ["T", "P"]],
              [[1, 1], [1, 0]], True),
             ("road two levels beside a wall", [["CL", "P"], ["CL", "P"]], [[2, 2], [2, 0]], True)]
    for name, cls, lv, refused in roads:
        good = bool(road(cls, lv)) == refused
        bad += not good
        if not good or verbose:
            print(f"  {'ok  ' if good else 'FAIL'} {name}: {'refused' if road(cls, lv) else 'built'}")
    n = len(CASES) + 1 + len(roads)
    print(f"shapes: {n - bad}/{n} behave as expected")
    return bad == 0, made


def vanilla_agreement(p, made, verbose):
    """Every adjacency between two cliff pieces the resolver produced is one vanilla uses (in the
    same direction), and each piece's attributes are vanilla's modal (collision, elevation)."""
    corpus = Corpus(p)
    tp = p.tileset_pair(PRIMARY, "gTileset_Petalburg")
    cliffs.verify_tileset(p, tp)
    pairs = {}
    for rows, pieces in made:
        for (x, y), m in pieces.items():
            for d, (dx, dy) in C.DIRS.items():
                o = pieces.get((x + dx, y + dy))
                if o is not None and m in C.PIECES and o in C.PIECES:
                    pairs[(m, d, o)] = pairs.get((m, d, o), 0) + 1
    missing = []
    for (m, d, o) in sorted(pairs):
        seen = corpus.neigh.get((PRIMARY, m), {}).get(d, {}).get((PRIMARY, o), 0)
        if verbose:
            print(f"  {m:03X} -{d}-> {o:03X}: vanilla {seen}")
        if seen == 0:
            missing.append(f"{m:03X} -{d}-> {o:03X}")
    attrs_bad = []
    for m in sorted(C.PIECES):
        a = corpus.attrs.get((PRIMARY, m))
        want = C.STAIR_ATTRS if m in C.STAIR_PIECES else C.WALL_ATTRS
        if not a or a.most_common(1)[0][0] != want:
            attrs_bad.append(f"{m:03X}: vanilla {a.most_common(2) if a else 'never'}, ours {want}")
    print(f"vanilla agreement: {len(pairs) - len(missing)}/{len(pairs)} piece adjacencies vanilla uses; "
          f"attributes {len(C.PIECES) - len(attrs_bad)}/{len(C.PIECES)} vanilla's modal"
          + (f"\n  never in vanilla: {', '.join(missing)}" if missing else "")
          + (f"\n  attributes: {'; '.join(attrs_bad)}" if attrs_bad else ""))
    return not missing and not attrs_bad and len(pairs) > 20


def level_lines():
    rows, levels = FACE2
    sk = Sketch("Test", rows, levels=[[int(c) for c in r] for r in levels])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.txt")
        sk.save(path)
        text = open(path, encoding="utf-8").read()
        back = Sketch.load(path)
        flat = Sketch("Flat", ["...", "..."])
        flat.save(path)
        flat_text = open(path, encoding="utf-8").read()
    ok = back.levels == sk.levels and back.rows == sk.rows and "// level:" in text \
        and "// level:" not in flat_text
    print(f"level lines: {'saved and loaded back' if ok else 'WRONG'} (a sketch without levels writes none)")
    return ok


ROUNDTRIP_MAPS = ["CliffLab", "Route202_1"]


def learned(p, _cache={}):
    if not _cache:
        from mapkit.terrain import Vocabulary, learn, vanilla_maps, class_adjacency, forbidden_pairs
        corpus = Corpus(p)
        vocab = Vocabulary(p, corpus)
        entries = vanilla_maps(corpus)
        _cache.update(corpus=corpus, vocab=vocab, rules=learn(p, vocab, entries),
                      forbidden=forbidden_pairs(class_adjacency(p, vocab, entries)))
    return _cache


def built_maps(p):
    """Maps whose design sketch draws cliffs: [(name, sketch)]."""
    out = []
    for name in ROUNDTRIP_MAPS:
        path = p.path("design", "maps", f"{name}.txt")
        if name in p.map_names and os.path.exists(path):
            sk = Sketch.load(path)
            if any(ch in cliffs.CHARS for row in sk.rows for ch in row):
                out.append((name, sk))
    return out


def sketch_agreement(p):
    """Each map built from a sketch with cliffs holds exactly the cliff blocks the resolver gives
    its sketch today (compiled fresh, as mapgen builds it): the committed map is the resolver's
    output, so a change to the resolver that would alter a built cliff shows here. The extract
    round trip below can't show it: extract keeps cliffs as '#'."""
    from mapkit.sketch import compile_sketch
    L = learned(p)
    ok, checked = True, []
    for name, sk in built_maps(p):
        m = p.load_map(name)
        blocks, _ = compile_sketch(p, L["corpus"], L["rules"], sk, m.layout, L["vocab"], L["forbidden"],
                                   fresh=True)
        cells = [i for i, b in enumerate(blocks) if (b & 0x3FF) in C.PIECES]
        differ = sum(1 for i in cells if blocks[i] != m.layout.blocks[i])
        ok &= differ == 0 and bool(cells)
        checked.append(f"{name} {len(cells)} cliff cells, {differ} differ")
    print("sketch agreement: " + ("; ".join(checked) if checked else "NO SKETCH WITH CLIFFS"))
    return ok and bool(checked)


def roundtrip(p):
    """extract -> compile leaves every cliff and stair block unchanged (they're kept '#') and
    draws no cliff or stair piece anywhere else (vanilla labels its stairs as grass: the rules
    must never draw them in open ground). A neighbour may differ (observed, not a failure): a
    fresh build reads a wall as grass, an extract keeps it as a solid tile, so e.g. a tree right
    under a wall can take another top variant."""
    from mapkit.sketch import extract, compile_sketch
    L = learned(p)
    corpus, vocab, rules, forbidden = L["corpus"], L["vocab"], L["rules"], L["forbidden"]
    ok, checked = True, []
    for name in (n for n in ROUNDTRIP_MAPS if n in p.map_names):
        m = p.load_map(name)
        cells = [i for i, b in enumerate(m.layout.blocks) if (b & 0x3FF) in C.PIECES]
        if not cells:
            continue
        sk = extract(p, vocab, name, rules, forbidden, corpus)
        blocks, _ = compile_sketch(p, corpus, rules, sk, m.layout, vocab, forbidden)
        cliff_changed = sum(1 for i in cells if blocks[i] != m.layout.blocks[i])
        stray = sum(1 for i, b in enumerate(blocks) if (b & 0x3FF) in C.PIECES and i not in set(cells))
        others = sum(1 for a, b in zip(blocks, m.layout.blocks) if a != b) - cliff_changed
        ok &= cliff_changed == 0 and stray == 0
        checked.append(f"{name} {len(cells)} cliff cells, {cliff_changed} changed, {stray} drawn elsewhere "
                       f"({others} other blocks differ, observed)")
    print("roundtrip: " + ("; ".join(checked) if checked else "NO MAP WITH CLIFFS"))
    return ok and bool(checked)


def main(argv):
    verbose = "-v" in argv
    p = Project()
    ok, made = shapes(verbose)
    # every built map's cliffs (CliffLab, Route 202) join the adjacency check
    for name, _ in built_maps(p):
        L = p.load_map(name).layout
        made.append((None, {(x, y): L.mid(x, y) for y in range(L.height) for x in range(L.width)
                            if L.mid(x, y) in C.PIECES or L.mid(x, y) in ledges.PIECES}))
    ok = vanilla_agreement(p, made, verbose) and ok
    ok = level_lines() and ok
    ok = sketch_agreement(p) and ok
    ok = roundtrip(p) and ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
