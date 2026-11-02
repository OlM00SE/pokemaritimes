"""Ledge vocabulary tests (no emulator).

1. Vanilla reconstruction: every ledge in the vanilla gTileset_General maps is reduced to its
   sketch characters (v < >), then rebuilt by mapkit.ledges.resolve(). Each rebuilt piece must
   be vanilla's exact metatile. Groups that use pieces outside the vocabulary (Route 118's cliff
   tiles) are counted separately, as is any vanilla jump tile the vocabulary doesn't cover.
2. Shapes: hand-drawn sketches that must build (with the expected pieces) or must be refused
   (with the expected reason). Covers stacking, junctions, lone tiles, mixed columns, and
   landings on trees, water, kept tiles, and off the map.
3. Round trip: extract -> compile on vanilla routes with ledges (and LedgeLab) leaves every
   ledge block unchanged, attributes included.
4. Traps: the LedgeLab sketch compiles without a trap; sealed off, the checker must report
   the soft-lock (compiled in memory, nothing written).

  python dev/tests/ledge_pieces.py [-v]
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import vanilla_maps, load_blocks, PRIMARY
from mapkit import ledges
from mapkit.sketch import CHAR_TO_CLASS, assign_tree_quarters


def components(cells):
    cells, out = set(cells), []
    while cells:
        stack, comp = [cells.pop()], set()
        while stack:
            x, y = stack.pop()
            comp.add((x, y))
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in cells:
                    cells.remove(n)
                    stack.append(n)
        out.append(comp)
    return out


# Ledge groups the vocabulary doesn't rebuild, per layout. All are ledges meeting cliffs: Route 118's
# mountain terraces, corners whose row side is a cliff wall (Lilycove, Safari Zone North, Battle
# Frontier), and rows running under a primary rock (Routes 119 and 123). Cliffs are future
# vocabulary. The test fails if these counts change in either direction.
KNOWN_UNBUILT = {"LAYOUT_ROUTE118": 11,"LAYOUT_LILYCOVE_CITY": 1, "LAYOUT_SAFARI_ZONE_NORTH": 1,
                 "LAYOUT_ROUTE119": 1, "LAYOUT_ROUTE123": 1, "LAYOUT_BATTLE_FRONTIER_OUTSIDE_EAST": 1}


def vanilla(p, verbose):
    c = Corpus(p)
    tp = p.tileset_pair(PRIMARY, "gTileset_Petalburg")
    ledges.verify_tileset(p, tp)
    jump_names = {"MB_JUMP_SOUTH", "MB_JUMP_WEST", "MB_JUMP_EAST", "MB_JUMP_NORTH"}
    per_piece, groups, outside, uncovered = Counter(), Counter(), [], Counter()
    unbuilt = Counter()
    hits = total = 0
    for e in vanilla_maps(c):
        w, h = e["width"], e["height"]
        b = load_blocks(p, e)
        mid = lambda x, y: b[y * w + x] & 0x3FF
        for y in range(h):
            for x in range(w):
                m = mid(x, y)
                if m not in ledges.PIECES and p.behavior_names.get(tp.behavior(m)) in jump_names:
                    uncovered[m] += 1
        cells = [(x, y) for y in range(h) for x in range(w) if mid(x, y) in ledges.PIECES]
        for comp in components(cells):
            # a group touching a jump tile outside the vocabulary is a different construction
            near = {(x + dx, y + dy) for x, y in comp for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
            if any(0 <= nx < w and 0 <= ny < h and mid(nx, ny) in uncovered for nx, ny in near):
                outside.append((e["id"], min(comp)))
                continue
            # secondary-tileset neighbours are what a sketch would keep as '#' (cliffs, walls)
            rows = [["#" if mid(x, y) >= 512 else "." for x in range(w)] for y in range(h)]
            for x, y in comp:
                rows[y][x] = ledges.piece_char(mid(x, y))
            pieces, errors = ledges.resolve(rows, w, h, ledges.runs_into_kept(rows, w, h, mid))
            ok = not errors and all(pieces.get(xy) == mid(*xy) for xy in comp)
            groups[ok] += 1
            unbuilt[e["id"]] += not ok
            for xy in comp:
                good = pieces.get(xy) == mid(*xy)
                per_piece[(mid(*xy), good)] += 1
                hits += good
                total += 1
            if not ok and verbose:
                print(f"  MISMATCH {e['id']} group at {min(comp)}: {errors[:2]}")
    print(f"vanilla ledges: {hits}/{total} pieces rebuilt exactly; {groups[True]}/{groups[True] + groups[False]} "
          f"groups exact; {len(outside)} groups use cliff pieces outside the vocabulary "
          f"({', '.join(sorted({m.replace('LAYOUT_', '') for m, _ in outside}))})")
    for m in sorted({m for m, _ in per_piece}):
        print(f"  {m:03X} {per_piece[(m, True)]:4}/{per_piece[(m, True)] + per_piece[(m, False)]}", end="")
    print()
    if uncovered:
        print("  vanilla jump tiles outside the vocabulary: "
              + ", ".join(f"{m:03X} x{n}" for m, n in uncovered.most_common()))
    got = {k: v for k, v in unbuilt.items() if v}
    want = {k: v for k, v in KNOWN_UNBUILT.items() if v}
    if got != want:
        print(f"  UNEXPECTED unbuilt groups per layout: {got}\n  expected (KNOWN_UNBUILT): {want}")
        return False
    print(f"  every group outside the {len(want)} known cliff cases rebuilds exactly "
          f"({sum(want.values())} known; {', '.join(k.replace('LAYOUT_', '') for k in want)})")
    return True


# Sketch shapes. Each case: (name, rows, expected) where expected is a list of
# ((x, y), metatile) that must be built, or a substring the refusal must contain.
CASES = [
    ("free row", ["....", ".vv.", "...."], [((1, 1), 0x0D5), ((2, 1), 0x0D6)]),
    ("long row", [".......", ".vvvvv.", "......."], [((1, 1), 0x0D5), ((3, 1), 0x087), ((5, 1), 0x0D6)]),
    ("west column", ["...", ".<.", ".<.", ".<.", "..."],
     [((1, 1), 0x0FE), ((1, 2), 0x085), ((1, 3), 0x106)]),
    ("east column", ["...", ".>.", ".>.", "..."], [((1, 1), 0x0FF), ((1, 2), 0x107)]),
    # Route 116: a plateau's south-west corner
    ("plateau SW corner", ["......", ".<....", ".<....", ".vvvv.", "......"],
     [((1, 1), 0x0FE), ((1, 2), 0x085), ((1, 3), 0x08D), ((2, 3), 0x087), ((4, 3), 0x0D6)]),
    ("plateau SE corner", ["......", "....>.", "....>.", ".vvvv.", "......"],
     [((4, 1), 0x0FF), ((4, 3), 0x08E), ((1, 3), 0x0D5)]),
    # the corner may be drawn with the column's character
    ("corner drawn as <", ["......", ".<....", ".<vvv.", "......"], [((1, 2), 0x08D)]),
    # Route 103: a step down to the east (06F over 08D)
    ("step down east", ["........", ".vvv....", "...vvvv.", "........", "........"],
     [((1, 1), 0x0D5), ((3, 1), 0x06F), ((3, 2), 0x08D), ((6, 2), 0x0D6)]),
    # Route 101: a step down to the west (06E over 08E)
    ("step down west", ["........", "....vvv.", ".vvvv...", "........", "........"],
     [((4, 1), 0x06E), ((4, 2), 0x08E), ((1, 2), 0x0D5), ((6, 1), 0x0D6)]),
    # Route 116: a row stepping down into a west column
    ("row into column", ["......", ".vvv..", "...<..", "...<..", "......"],
     [((3, 1), 0x06F), ((3, 2), 0x085), ((3, 3), 0x106)]),
    ("stacked rows", [".....", ".vvv.", ".vvv.", ".....", "....."], "branch"),
    ("2x2 ring", ["....", ".vv.", ".vv.", "....", "...."], "jumps"),
    ("runs off the map edge", ["...", "vv.", "..."], [((0, 1), 0x087), ((1, 1), 0x0D6)]),
    ("lone tile", ["...", ".v.", "...", "..."], "lone"),
    ("side ledge drawn flat", ["....", ".<<.", "...."], "side ledge"),
    ("row drawn as column", ["...", ".v.", ".v.", "..."], "touch vertically"),
    ("T junction", [".....", ".vvv.", "..<..", "..<..", "....."], "branch"),
    ("mixed column", ["...", ".<.", ".>.", ".>.", "..."], "jumps"),
    ("corner against column", ["......", ".>....", ".>....", ".vvvv.", "......"], "jumps"),
    ("lands on a tree", ["....", ".vv.", "TTTT", "TTTT"], "lands on a tree"),
    ("lands in water", ["....", ".vv.", "~~~~", "...."], "lands on water"),
    ("lands off the map", ["....", "....", ".vv."], "off the map"),
    ("lands on a kept tile", ["....", ".vv.", ".##.", "...."], "kept '#' tile"),
    # nobody can stand behind it, so it never jumps: allowed (a warning), like Route 118's cliffs
    ("decorative (forest behind)", ["TTTT", "TTTT", ".vv.", "TTTT", "TTTT"], [((1, 2), 0x0D5)]),
    ("lands in a pond (east)", [".....", ".>...", ".>o..", "....."], "lands on water"),
]


def build(rows):
    w, h = len(rows[0]), len(rows)
    pieces, errors = ledges.resolve(rows, w, h)
    if errors:
        return pieces, errors
    cls = [[CHAR_TO_CLASS[ch] for ch in r] for r in rows]
    assign_tree_quarters(cls, w, h)
    errs, _ = ledges.design_issues(cls, pieces, w, h)
    return pieces, errs


def shapes(verbose):
    bad = 0
    for name, rows, want in CASES:
        pieces, errors = build(rows)
        if isinstance(want, str):
            ok = any(want in m for _, _, m in errors)
            detail = errors[:1] if errors else "built, but should have been refused"
        else:
            ok = not errors and all(pieces.get(xy) == m for xy, m in want)
            detail = errors[:1] or {f"{k}": f"{v:03X}" for k, v in pieces.items()}
        bad += not ok
        if not ok or verbose:
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail if not ok else ''}")
    print(f"shapes: {len(CASES) - bad}/{len(CASES)} behave as expected")
    return bad == 0


def learned(p, _cache={}):
    if not _cache:
        from mapkit.terrain import Vocabulary, learn, class_adjacency, forbidden_pairs
        corpus = Corpus(p)
        vocab = Vocabulary(p, corpus)
        entries = vanilla_maps(corpus)
        _cache.update(corpus=corpus, vocab=vocab, rules=learn(p, vocab, entries),
                      forbidden=forbidden_pairs(class_adjacency(p, vocab, entries)))
    return _cache


ROUNDTRIP_MAPS = ["Route102", "Route103", "Route104", "Route111", "Route115", "Route116", "Route118",
                  "Route123", "LedgeLab"]


def roundtrip(p):
    """Extracting a map with ledges and compiling the sketch back must leave every ledge block
    exactly as it was (metatile, collision, elevation): rebuilding a map never disturbs them."""
    from mapkit.sketch import extract, compile_sketch
    L = learned(p)
    ok = True
    for name in (n for n in ROUNDTRIP_MAPS if n in p.map_names):
        m = p.load_map(name)
        sk = extract(p, L["vocab"], name, L["rules"])
        blocks, _ = compile_sketch(p, L["corpus"], L["rules"], sk, m.layout, L["vocab"])
        cells = [i for i, b in enumerate(m.layout.blocks) if (b & 0x3FF) in ledges.PIECES]
        changed = sum(1 for i in cells if blocks[i] != m.layout.blocks[i])
        ok &= changed == 0
        if changed:
            print(f"  roundtrip {name}: {changed}/{len(cells)} ledge blocks changed")
    print(f"roundtrip: ledge blocks {'unchanged' if ok else 'CHANGED'} on {', '.join(ROUNDTRIP_MAPS)}")
    return ok


def traps(p):
    """The checker must catch a soft-lock built from ledges. The LedgeLab sketch is compiled as
    drawn (no trap), then with its bottom meadow sealed: the lower stair rows run into the
    forest on both sides and trees fill the gap between them, so the meadow can be jumped into
    but never left. Nothing is written to disk."""
    from mapkit.sketch import Sketch, compile_sketch
    from mapkit.checks import check_map
    sketch_path = p.path("design", "maps", "LedgeLab.txt")
    if "LedgeLab" not in p.map_names or not os.path.exists(sketch_path):
        print("traps: SKIPPED (no LedgeLab map)")
        return True
    L = learned(p)
    corpus, vocab, rules, forbidden = L["corpus"], L["vocab"], L["rules"], L["forbidden"]
    ok = True
    for label, seal in (("as drawn", False), ("sealed", True)):
        sk = Sketch.load(sketch_path)
        if seal:
            sk.fill(2, 17, 8, 17, "v"); sk.fill(23, 17, 29, 17, "v")
            sk.fill(14, 17, 17, 18, "T")
        m = p.load_map("LedgeLab")
        m.layout.blocks, _ = compile_sketch(p, corpus, rules, sk, m.layout, vocab, forbidden, fresh=True)
        found = [msg for s, c, msg in check_map(p, "LedgeLab", None, corpus, mapdata=m) if c == "trap"]
        good = bool(found) == seal and (not seal or "soft-lock" in found[0])
        ok &= good
        print(f"traps: LedgeLab {label}: {'trap reported' if found else 'no trap'} "
              f"({'ok' if good else 'WRONG'}){': ' + found[0][:110] if found else ''}")
    return ok


def main(argv):
    verbose = "-v" in argv
    p = Project()
    ok = vanilla(p, verbose)
    ok = shapes(verbose) and ok
    ok = roundtrip(p) and ok
    ok = traps(p) and ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
