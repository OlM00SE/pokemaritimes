"""Flora and landscape tests (no emulator).

1. Vanilla agreement: on the vanilla routes that use them most, extract finds every flower bed,
   boulder and Route 116-style sapling (00E [0C6] 017), and keeps as '#' only the ones a compile
   wouldn't put back exactly. Reported per piece; then extract -> compile must leave every flora
   block, and every block beside one, unchanged, attributes included.
2. Shapes: small sketches that must build (flowers, boulders, saplings 2 and 3 tall, a ledge
   landing on flowers) or be refused with the expected reason (a 1- or 4-tall sapling, a trunk
   on the bottom edge, flowers under a canopy overhang, a boulder on a bank, a ledge landing on
   a boulder or a sapling's trunk; landing on a sapling's crown top is fine).
3. Round trip: extract -> compile reproduces GroveLab and Route 203 block for block from the
   shape tables alone (nothing kept by extract's compile check).
4. Planting: landscape.plant() on 300 seeded random masks (blobs, stepped edges, keep-clear
   trails, both tree grids) always yields whole trees that the compiler tiles back exactly
   (no dropped cells, no tree split), never plants on keep_clear, and only builds valid saplings.

  python dev/tests/flora_pieces.py [-v]
"""
import os, random, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, vanilla_maps, load_blocks, learn, class_adjacency, forbidden_pairs
from mapkit.sketch import (Sketch, SketchError, extract, compile_sketch, assign_tree_quarters, CHAR_TO_CLASS,
                           verify_owned)
from mapkit import flora, landscape as ls

VANILLA = ["ROUTE116", "ROUTE102", "ROUTE103", "ROUTE104", "ROUTE110", "ROUTE111", "ROUTE117",
           "ROUTE118", "ROUTE119", "ROUTE120", "ROUTE121", "ROUTE123", "SAFARI_ZONE_SOUTH",
           "SAFARI_ZONE_NORTHWEST", "MOSSDEEP_CITY", "LILYCOVE_CITY"]


KIND = {"*": "flowers", "b": "boulders", "y": "saplings"}


def vanilla(p, c, v, rules, forbidden, verbose):
    """Pieces in the form we model (flora.extract_chars: flowers, boulders, saplings with an 00E
    crown top) are counted per piece (a sapling counts once, at its crown). Other sapling-like
    columns (Route 119/120 jungle hedges, saplings tucked under a tree's canopy) are reported
    as out of scope; they stay '#'."""
    found, kept, other, changed = Counter(), Counter(), 0, 0
    names = {e["id"].replace("LAYOUT_", ""): e for e in vanilla_maps(c)}
    for lid in VANILLA:
        e = names[lid]
        name = next(n for n in p.map_names if p.load_map(n).j["layout"] == e["id"])
        L = p.load_map(name).layout
        modeled = flora.extract_chars(L.mid, L.width, L.height)
        heads = {(x, y): ch for (x, y), ch in modeled.items()
                 if ch != "y" or modeled.get((x, y - 1)) != "y"}
        other += sum(1 for y in range(L.height) for x in range(L.width)
                     if L.mid(x, y) in (flora.TRUNK, 0x016) and (x, y) not in modeled)
        sk = extract(p, v, name, rules, forbidden, c)
        for (x, y), ch in heads.items():
            found[KIND[ch]] += 1
            kept[KIND[ch]] += sk.rows[y][x] == "#"
        blocks, _ = compile_sketch(p, c, rules, sk, L, v, forbidden)
        cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sk.rows]
        changed += sum(1 for y in range(L.height) for x in range(L.width)
                       if ((x, y) in modeled or verify_owned(cls, x, y, L.width, L.height))
                       and blocks[y * L.width + x] != L.get(x, y))
        if verbose:
            n = Counter(KIND[ch] for ch in heads.values())
            print(f"    {name}: {dict(n)}, kept {sum(sk.rows[y][x] == '#' for x, y in heads)}")
    for kind in ("flowers", "boulders", "saplings"):
        print(f"  {kind:8}: {found[kind] - kept[kind]}/{found[kind]} extracted as flora "
              f"({kept[kind]} kept as '#': an odd elevation, a non-grass spot, or a neighbour "
              "vanilla drew for an object there)")
    print(f"  out of scope: {other} trunks in other sapling forms (jungle hedges, under a canopy) stay '#'")
    print(f"  extract -> compile changes {changed} flora blocks or blocks beside flora")
    return changed == 0 and all(found[k] - kept[k] > 0 for k in ("flowers", "boulders", "saplings"))


SHAPES = [
    # (name, [(x, y, char)], expect None (builds) or a substring of the refusal)
    ("flowers in the open", [(10, 10, "*"), (11, 10, "*"), (10, 11, "*")], None),
    ("boulder in the open", [(10, 10, "b")], None),
    ("sapling 2 tall", [(10, 10, "y"), (10, 11, "y")], None),
    ("sapling 3 tall", [(10, 10, "y"), (10, 11, "y"), (10, 12, "y")], None),
    ("flowers beside a tree", [(12, 10, "*")] + [(10 + dx, 10 + dy, "T") for dx in (0, 1) for dy in (0, 1)], None),
    ("ledge landing on flowers", [(x, 10, "v") for x in range(8, 13)] + [(10, 11, "*")], None),
    ("sapling 1 tall", [(10, 10, "y")], "vertical run of 2 or 3"),
    ("sapling 4 tall", [(10, y, "y") for y in range(10, 14)], "vertical run of 2 or 3"),
    ("trunk on the bottom edge", [(10, 30, "y"), (10, 31, "y")], "bottom edge"),
    ("flowers under a canopy", [(10, 9, "*")] + [(10 + dx, 10 + dy, "T") for dx in (0, 1) for dy in (0, 1)],
     "plain grass"),
    ("boulder on a bank", [(x, y, "~") for x in range(8, 14) for y in range(6, 9)] + [(10, 9, "b")],
     "plain grass"),
    ("ledge landing on a boulder", [(x, 10, "v") for x in range(8, 13)] + [(10, 11, "b")], "a boulder"),
    ("ledge landing on a sapling's crown", [(x, 10, "v") for x in range(8, 13)] + [(10, 11, "y"), (10, 12, "y")],
     None),                                   # the crown top is walkable (00E)
    ("ledge landing on a sapling's trunk", [(10, y, "<") for y in range(8, 13)] + [(9, 9, "y"), (9, 10, "y")],
     "lands on a sapling"),
]


def shapes(p, c, v, rules, forbidden):
    m = p.load_map("GroveLab")
    ok = 0
    for name, cells, expect in SHAPES:
        sk = Sketch("GroveLab", ["." * m.layout.width for _ in range(m.layout.height)])
        for x, y, ch in cells:
            sk.set(x, y, ch)
        try:
            compile_sketch(p, c, rules, sk, m.layout, v, forbidden, fresh=True)
            got = None
        except SketchError as ex:
            got = str(ex)
        good = (expect is None and got is None) or (expect is not None and got is not None and expect in got)
        ok += good
        if not good:
            print(f"  FAIL {name}: expected {'build' if expect is None else 'refusal: ' + expect}, got "
                  f"{'build' if got is None else got.strip()}")
    print(f"  {ok}/{len(SHAPES)} shapes build or are refused as expected")
    return ok == len(SHAPES)


def roundtrip(p, c, v, rules, forbidden):
    good = True
    for name in ("GroveLab", "Route203_1"):
        m = p.load_map(name)
        sk = extract(p, v, name, rules, forbidden, c, verify_shores=False)    # shape tables alone
        blocks, _ = compile_sketch(p, c, rules, sk, m.layout, v, forbidden)
        same = sum(b == m.layout.blocks[i] for i, b in enumerate(blocks))
        n_flora = sum(ch in flora.CHAR_CLASS for row in sk.rows for ch in row)
        print(f"  {name}: {same}/{len(blocks)} blocks identical ({n_flora} flora cells, "
              f"{sum(ch == '#' for row in sk.rows for ch in row)} kept)")
        good &= same == len(blocks)
    return good


def planting(n=300):
    rng = random.Random(6)
    W, H = 40, 32
    bad = 0
    for i in range(n):
        sk = Sketch("t", ["." * W for _ in range(H)])
        mask = set()
        for _ in range(rng.randint(1, 4)):
            if rng.random() < 0.5:
                mask |= ls.blob(rng.uniform(4, W - 4), rng.uniform(4, H - 4), rng.uniform(2, 8),
                                rng.uniform(2, 6), seed=rng.random(), wobble=rng.uniform(0, 0.4))
            else:
                side = rng.choice("NSWE")
                mask |= ls.forest_edge(0, 0, W - 1, H - 1, side, rng.randint(2, 8), rng.random()) & (
                    ls.rect(0, 0, W - 1, 9) if side == "S" else ls.rect(0, H - 10, W - 1, H - 1) if side == "N"
                    else ls.rect(W - 10, 0, W - 1, H - 1) if side == "W" else ls.rect(0, 0, 9, H - 1))
        y0 = rng.randrange(H - 2)
        trail = ls.rect(0, y0, W - 1, y0 + 1) if rng.random() < 0.7 else set()
        for x, y in trail:
            sk.set(x, y, "=")
        keep = ls.around(trail, 1)
        ls.plant(sk, mask, ls.rect(0, 0, W - 1, H - 1), parity=(rng.randrange(2), rng.randrange(2)),
                 keep_clear=keep)
        cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sk.rows]
        trees = sum(ch == "T" for row in sk.rows for ch in row)
        dropped = assign_tree_quarters(cls, W, H)
        _, errs = flora.resolve(cls, W, H)
        on_keep = [(x, y) for x, y in keep if 0 <= x < W and 0 <= y < H and sk.rows[y][x] in "Ty"]
        if dropped or errs or on_keep or trees % 2:
            bad += 1
            if bad <= 3:
                print(f"  FAIL mask {i}: dropped {dropped}, sapling errors {errs[:2]}, on keep_clear {on_keep[:3]}")
    print(f"  {n - bad}/{n} random plantings tile back exactly with valid saplings")
    return bad == 0


def main(argv):
    verbose = "-v" in argv
    p = Project(); c = Corpus(p); v = Vocabulary(p, c)
    entries = vanilla_maps(c)
    rules = learn(p, v, entries)
    forbidden = forbidden_pairs(class_adjacency(p, v, entries))
    results = []
    print("1. vanilla agreement"); results.append(vanilla(p, c, v, rules, forbidden, verbose))
    print("2. shapes"); results.append(shapes(p, c, v, rules, forbidden))
    print("3. round trip"); results.append(roundtrip(p, c, v, rules, forbidden))
    print("4. planting"); results.append(planting())
    print("PASS" if all(results) else "FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
