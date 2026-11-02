"""Shore vocabulary tests (no emulator).

1. Vanilla agreement: in every vanilla gTileset_General map, each place where river/sea water
   meets only grass-like land or beach sand (no rocks, cliffs or secondary tiles around it) is
   rebuilt by mapkit.shores from its shape alone. The rebuilt water piece, beach-sand edge, and
   grass bank must be vanilla's metatile. Disagreements are listed with vanilla's tile.
2. Shapes: small hand-drawn grids that must resolve (with the expected pieces) or be refused
   (with the expected reason): straight banks, staircases, coves, beaches drawn on the water and
   on the sand, one-tile channels, bank/beach corners, squeezed water, and rocks.
3. Round trip: extract -> compile leaves every shore block (water, beach sand, grass beside
   water, rocks) unchanged, attributes included, on ShoreLab, Route 203, Woodstock, and the
   vanilla beach and river routes.

  python dev/tests/shore_pieces.py [-v]
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, vanilla_maps, load_blocks, PRIMARY
from mapkit import shores
from mapkit.sketch import CHAR_TO_CLASS

LANDISH = {"G", "TG", "P", "SA", "LD", "TL", "TR", "BL", "BR"}   # land that draws no edge of its own


def vanilla_classes(vocab, e, b, w, h):
    """Class grid as shores sees it: beach-sand pieces are sand, rocks and everything outside the
    vocabulary are kept tiles."""
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            m = b[y * w + x] & 0x3FF
            if m >= 512:
                row.append("F")
            elif m in shores.SAND_PIECES:
                row.append("SA")
            else:
                row.append(vocab.cls.get(m, "F"))
        out.append(row)
    return out


def vanilla(p, verbose):
    corpus = Corpus(p)
    vocab = Vocabulary(p, corpus)
    agree, disagree = Counter(), Counter()
    for e in vanilla_maps(corpus):
        w, h = e["width"], e["height"]
        b = load_blocks(p, e)
        cls = vanilla_classes(vocab, e, b, w, h)
        for y in range(h):
            for x in range(w):
                c, m = cls[y][x], b[y * w + x] & 0x3FF
                ring = [shores._at(cls, x + dx, y + dy, w, h) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
                if not all(n == "S" or n in LANDISH for n in ring) or "S" not in ring:
                    continue                      # not a pure water/land meeting
                if c == "S" and m in shores.WATER_PIECES:
                    want, _ = shores.water_piece(cls, x, y, w, h)
                    kind = "water"
                elif c == "SA" and m in shores.SAND_PIECES:
                    want = shores.sand_piece(cls, x, y, w, h) or shores.BEACH_SAND
                    kind = "sand"
                elif c == "G" and shores._at(cls, x, y - 1, w, h) == "S":
                    want = m if m in shores.GRASS_BANK_TILES else 0x002
                    kind = "grass"
                else:
                    continue
                if want == m:
                    agree[kind] += 1
                else:
                    disagree[(kind, m, want)] += 1
    total_ok, total = sum(agree.values()), sum(agree.values()) + sum(disagree.values())
    for kind in ("water", "sand", "grass"):
        bad = sum(n for (k, _, _), n in disagree.items() if k == kind)
        print(f"vanilla {kind:5}: {agree[kind]}/{agree[kind] + bad} cells rebuilt exactly")
    for (kind, m, want), n in disagree.most_common(None if verbose else 8):
        print(f"    {kind}: vanilla {m:03X}, shape gives {want if want is None else f'{want:03X}'}  x{n}")
    share = total_ok / max(total, 1)
    ok = share >= 0.95
    print(f"vanilla agreement: {total_ok}/{total} ({share:.1%}) {'ok' if ok else 'TOO LOW (< 95%)'}")
    return ok


def grid(rows):
    return [[CHAR_TO_CLASS[ch] if ch != "t" else "T" for ch in r] for r in rows]


# (name, rows, expect): expect is {(x, y): metatile} that must be produced, or an error fragment
B, S = shores.BANK, shores.BEACH
CASES = [
    ("straight river", ["....", "~~~~", "~~~~", "...."],
     {(1, 1): B["N"], (1, 2): shores.OPEN_WATER}),
    ("staircase down to the east", ["......", "~~~...", "~~~~~~", "~~~~~~"],
     {(2, 1): B["NE"], (2, 2): B["cNE"], (3, 2): B["N"]}),
    ("staircase down to the west", ["......", "...~~~", "~~~~~~", "~~~~~~"],
     {(3, 1): B["NW"], (3, 2): B["cNW"], (2, 2): B["N"]}),
    ("cove", ["......", "..~~..", "~~~~~~", "~~~~~~"],
     {(2, 1): B["NW"], (3, 1): B["NE"], (1, 2): B["N"], (2, 2): B["cNW"], (3, 2): B["cNE"],
      (0, 3): shores.OPEN_WATER}),
    ("headland from the south", ["~~~~~~", "~~~~~~", "~~..~~", "......"],
     {(1, 2): B["E_end"], (4, 2): B["W_end"], (1, 1): shores.OPEN_WATER}),
    ("west and east banks", [".~~~.", ".~~~.", ".~~~."],
     {(1, 1): B["W"], (3, 1): B["E"]}),
    ("bay with a beach (edge on the water)", ["::::::", "::~~::", "~~~~~~", "~~~~~~"],
     {(2, 1): S["NW"], (3, 1): S["NE"], (1, 2): S["N"], (0, 3): shores.OPEN_WATER}),
    ("beach on the south shore (edge on the sand)", ["~~~~~~", ".~~~~.", "::::::"],
     {(1, 2): shores.SAND_EDGE["N_landNW"], (2, 2): shores.SAND_EDGE["N"],
      (4, 2): shores.SAND_EDGE["N_landNE"], (1, 1): B["W_end"]}),
    ("beach meets bank on a straight shore", ["...:::", "~~~~~~", "~~~~~~"],
     {(2, 1): B["N"], (3, 1): S["N"]}),
    ("sand spit (side edges on the water)", ["~~~~~~", "~~::~~", "~~::~~", "~~~~~~"],
     {(1, 1): S["E_end"], (4, 1): S["W_end"], (1, 2): S["E"], (2, 1): shores.SAND_EDGE["N"]}),
    ("one-tile channel", [".~.", ".~.", ".~."], "one tile wide"),
    ("bank turns into a beach at a corner", ["...:", "~~~:", "~~~~"], "turns into"),
    ("water squeezed against the far corner", ["~~~~~~", ".~~~~~", "~~.~~~", "~~~~~~"], "squeezed"),
    ("rock in the river", ["~~~~", "~rr~", "~rr~", "~~~~"], {(1, 1): 0x150, (2, 2): 0x159}),
    ("half a rock", ["~~~~", "~r~~", "~~~~"], "whole 2x2"),
    ("rock on the bank", ["....", "~rr~", "~rr~", "~~~~"], "stand in water"),
]


def shapes(verbose):
    bad = 0
    for name, rows, expect in CASES:
        cls = grid(rows)
        h, w = len(cls), len(cls[0])
        water, sand, beach, errors = shores.resolve(cls, w, h)
        rocks, rock_errors = shores.place_rocks(cls, w, h)
        errors += rock_errors
        got = {**water, **sand, **rocks}
        if isinstance(expect, str):
            ok = any(expect in msg for _, _, msg in errors)
            detail = errors[:2] or "built"
        else:
            ok = not errors and all(got.get(xy) == m for xy, m in expect.items())
            detail = errors[:2] or {f"{xy}": f"{got.get(xy, 0):03X} (want {m:03X})" for xy, m in expect.items()
                                    if got.get(xy) != m}
        bad += not ok
        if not ok or verbose:
            print(f"  {'ok  ' if ok else 'FAIL'} {name}{'' if ok else f': {detail}'}")
    print(f"shapes: {len(CASES) - bad}/{len(CASES)} behave as expected")
    return bad == 0


ROUNDTRIP_MAPS = ["ShoreLab", "Route203_1", "Woodstock_2", "Route104", "Route105", "Route109",
                  "Route110", "Route115", "Route119", "Route120", "SlateportCity", "DewfordTown"]


def roundtrip(p):
    """Extracting a map and compiling the sketch back must leave every shore block exactly as it
    was (metatile, collision, elevation)."""
    from mapkit.terrain import learn
    from mapkit.sketch import extract, compile_sketch
    corpus = Corpus(p)
    vocab = Vocabulary(p, corpus)
    rules = learn(p, vocab, vanilla_maps(corpus))
    ok = True
    for name in (n for n in ROUNDTRIP_MAPS if n in p.map_names):
        m = p.load_map(name)
        L = m.layout
        if L.primary != PRIMARY:
            continue
        sk = extract(p, vocab, name, rules)
        blocks, _ = compile_sketch(p, corpus, rules, sk, L, vocab)
        # the cells the shore resolver owns: water, rocks, sand and grass beside water
        cls = grid(sk.rows)
        w, h = L.width, L.height
        owned = lambda x, y: cls[y][x] in ("S", shores.ROCK_CLS) or (
            cls[y][x] in ("SA", "G") and shores.touches_water(cls, x, y, w, h))
        cells = [y * w + x for y in range(h) for x in range(w) if owned(x, y)]
        changed = [i for i in cells if blocks[i] != L.blocks[i]]
        ok &= not changed
        fmt = lambda b: f"{b & 0x3FF:03X}/{b >> 10 & 3}/{b >> 12}"
        print(f"  roundtrip {name:14} {len(cells) - len(changed)}/{len(cells)} shore blocks unchanged"
              + (f", {len(changed)} changed (tile/collision/elevation), e.g. " + ", ".join(
                  f"({i % w},{i // w}) '{sk.rows[i // w][i % w]}' {fmt(L.blocks[i])}->{fmt(blocks[i])}"
                  for i in changed[:3]) if changed else ""))
    print(f"roundtrip: shore blocks {'unchanged' if ok else 'CHANGED'}")
    return ok


def main(argv):
    verbose = "-v" in argv
    p = Project()
    ok = vanilla(p, verbose)
    ok = shapes(verbose) and ok
    ok = roundtrip(p) and ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
