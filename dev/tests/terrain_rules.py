"""Visual rules (mapkit/composition.py) tests, no emulator.

1. Bands: re-measuring vanilla gives exactly mapkit/composition_bands.json (the bands are
   reproducible from the corpus, and up to date with the rules' code).
2. Vanilla: its own maps show no odd pairs (the evidence is read the way it was collected).
3. Scenes: small landscapes compiled with mapgen's compiler on a blank General + Petalburg
   layout, each drawn badly and well. Each rule must flag the bad one and pass the good one
   (forest edge, river banks, meadow, hedge, flowers, bare lawn, saplings). The finishing helpers
   (loosen_flowers, uncrowd_saplings) must turn a bad scene into a good one.
   Sheet: dev/out/terrain/scenes.png.
4. Ratchet: the corridor maps' odd pairs may only go down, and no guide may newly fall outside
   vanilla's band (unless the sketch accepts it with a reason).
5. Accepting: an `// accept:` line must name a rule and give a reason.

  python dev/tests/terrain_rules.py [-v]
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.layout import pack
from mapkit.sketch import Sketch, compile_sketch
from mapkit import composition as C, landscape as ls
from corridor import build_kit, BLANK_LIKE

RESULTS = []
W, H = 32, 20


def check(ok, what):
    RESULTS.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}: {what}")
    return ok


# ------------------------------------------------------------------------------------ scenes ----
def blank_sketch():
    return Sketch("Scene", ["." * W for _ in range(H)])


def forest(sk, mask, keep_clear=frozenset()):
    ls.plant(sk, mask, ls.rect(0, 0, W - 1, H - 1), keep_clear=keep_clear)


def scene_forest(good):
    sk = blank_sketch()
    if good:
        forest(sk, ls.forest_edge(0, 0, W - 1, 9, "S", amp=4, seed=31))
    else:
        forest(sk, ls.rect(0, 0, W - 1, 7))
    return sk


def scene_river(good):
    sk = blank_sketch()
    if good:     # a river across the map whose banks step in varied runs
        top = [7 + v for v in ls.edge_profile(W, 2, seed=7, run=(2, 5))]
        bottom = [12 + v for v in ls.edge_profile(W, 2, seed=8, run=(2, 5))]
        for x in range(W):
            for y in range(top[x], bottom[x]):
                sk.set(x, y, "~")
    else:        # a river drawn straight along a diagonal: a staircase of one-tile steps
        for x in range(W):
            for y in range(H):
                if 0 <= y - x + 8 <= 3:
                    sk.set(x, y, "~")
    return sk


def scene_meadow(good):
    sk = blank_sketch()
    forest(sk, ls.forest_edge(0, 0, W - 1, 5, "S", amp=2, seed=41))
    if good:     # tall grass grown out from the woods' edge, irregular
        ls.meadow(sk, ls.blob(15, 6, 7, 1.8, seed=42, wobble=0.3), seed=43, tufts=3)
    else:        # a rectangle of tall grass out in the lawn
        ls.meadow(sk, ls.rect(11, 12, 21, 16), seed=43)
    return sk


def scene_hedge(good):
    sk = blank_sketch()
    if good:     # a lone tree, a pair, a clump
        forest(sk, ls.rect(4, 8, 5, 9) | ls.rect(12, 6, 15, 7) | ls.rect(22, 9, 27, 12))
    else:        # five trees in a row, one tree thick, out in the open
        forest(sk, ls.rect(6, 8, 17, 9))
    return sk


SPOTS = [(5, 5), (12, 14), (20, 6), (26, 15), (9, 10)]


def scene_flowers(good):
    sk = blank_sketch()
    for i, (x, y) in enumerate(SPOTS):
        (ls.sprinkle if good else ls.flower_bed)(sk, x, y, 2, seed=50 + i)
    return sk


def scene_bare(good):
    sk = blank_sketch()
    if good:     # woods with a bay, a grove, a meadow against the woods, a path, accents
        for x in range(W):              # a road through the woods, a meadow against them
            sk.set(x, 10, "=")
            sk.set(x, 11, "=")
        forest(sk, ls.forest_edge(0, 0, W - 1, 8, "S", amp=4, seed=61)
               | ls.forest_edge(0, 13, W - 1, H - 1, "N", amp=4, seed=62) | ls.rect(24, 6, 27, 7),
               keep_clear=ls.around(ls.cells_of(sk, "="), 1))
        ls.meadow(sk, ls.blob(9, 7, 6, 1.6, seed=63), seed=64, tufts=2)
        ls.meadow(sk, ls.blob(20, 13, 4, 1.4, seed=66), seed=67, tufts=1)
        ls.meadow(sk, ls.blob(28, 8, 4, 1.2, seed=68), seed=69, tufts=1)
        for i, (x, y) in enumerate(((15, 8), (29, 13), (3, 13))):
            ls.sprinkle(sk, x, y, 1, seed=65 + i)
    else:        # a lawn
        forest(sk, ls.rect(0, 0, W - 1, 1))
    return sk


def scene_saplings(good):
    rows = ["." * W for _ in range(H)]
    sk = Sketch("Scene", rows)
    for (x, y) in ((8, 8), (20, 8)):
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            sk.set(x + dx, y + dy, "T")
        sk.set(x + 2, y, "y")
        sk.set(x + 2, y + 1, "y")
    if good:
        ls.uncrowd_saplings(sk)
    return sk


SCENES = [
    ("forest edge", "straight_forest", scene_forest),
    ("river banks", "staircase_water", scene_river),
    ("meadow", "grass_rect", scene_meadow),
    ("meadow", "grass_cover", scene_meadow),
    ("hedge", "hedge", scene_hedge),
    ("flowers", "flower_singles", scene_flowers),
    ("bare lawn", "bare_screens", scene_bare),
    ("bare lawn", "open_space", scene_bare),
    ("saplings", "pairs", scene_saplings),
]


def compile_scene(p, kit, sk):
    corpus, vocab, rules, forbidden = kit
    L = copy.copy(p.load_map(BLANK_LIKE).layout)
    L.width, L.height = sk.w, sk.h
    L.blocks = [pack(1, 0, 3)] * (sk.w * sk.h)
    # a lawn all round (off the map the rules would otherwise see the unknown OUT, and draw tree caps
    # along the edges as if the border's trees stood there)
    lawn = {(x, y): "G" for x in range(-2, sk.w + 2) for y in range(-2, sk.h + 2)
            if not (0 <= x < sk.w and 0 <= y < sk.h)}
    L.blocks, _ = compile_sketch(p, corpus, rules, sk, L, vocab, forbidden, fresh=True, border=lawn)
    return L


def flagged(rep, rule):
    if rule == "pairs":
        return bool(rep["pairs"])
    return next(ver for r, _, ver, _, _, _ in rep["guides"] if r == rule) in ("unusual", "beyond")


def value(rep, rule):
    if rule == "pairs":
        return f"{len(rep['pairs'])} odd pairs ({'; '.join(C.describe_pairs(rep['pairs'], 2))})"
    return C.fmt(next(v for r, v, _, _, _, _ in rep["guides"] if r == rule))


def scenes(p, kit, bands, verbose):
    from PIL import Image
    from terrain_report import draw
    print("scenes (each rule must flag the bad scene and pass the good one):")
    tiles, done = [], set()
    for name, rule, make in SCENES:
        reps = {}
        for good in (False, True):
            L = compile_scene(p, kit, make(good))
            rep = C.report(p, kit[0], L, "MAP_TYPE_ROUTE", (), bands)
            reps[good] = rep
            if (name, good) not in done:
                tiles.append(draw(p, L, rep, f"{name} ({'good' if good else 'bad'})", None, s=1))
                done.add((name, good))
        check(flagged(reps[False], rule) and not flagged(reps[True], rule),
              f"{name}: {rule} flags the bad scene ({value(reps[False], rule)}) and passes the good "
              f"one ({value(reps[True], rule)})")
    # the finishing helpers turn a bad scene into a good one
    sk = scene_flowers(False)
    ls.loosen_flowers(sk)
    rep = C.report(p, kit[0], compile_scene(p, kit, sk), "MAP_TYPE_ROUTE", (), bands)
    check(not flagged(rep, "flower_singles") and value(rep, "flower_singles") == "1.00",
          f"loosen_flowers: the bad flower scene's beds become singles ({value(rep, 'flower_singles')})")
    sk = scene_saplings(False)
    check(len(ls.crowded_saplings(sk)) == 2, "crowded_saplings finds both saplings against a tree")
    ls.uncrowd_saplings(sk, hold={(10, 9)})
    rep = C.report(p, kit[0], compile_scene(p, kit, sk), "MAP_TYPE_ROUTE", (), bands)
    check(sk.get(10, 9) == "b" and sk.get(10, 8) == "." and sk.get(22, 8) == "." and not rep["pairs"],
          f"uncrowd_saplings(hold=): the held sapling's trunk is a boulder, the other is grass, "
          f"no odd pairs ({len(rep['pairs'])})")
    cols = 2
    tw = max(t.width for t in tiles)
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (tw * cols, th * ((len(tiles) + cols - 1) // cols)), (24, 24, 32))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    out = p.path("dev", "out", "terrain", "scenes.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(f"  sheet: {os.path.relpath(out, p.root)}")


# ---------------------------------------------------------------------------------- ratchet ----
# terrain-rules (2026-11-07): what the corridor maps show now. Odd pairs may only go down; a guide
# outside vanilla's band that isn't listed here (or accepted in the sketch) fails. Lower the
# numbers when a redesign fixes something; the listed guides are known findings for a later pass.
RATCHET = {
    "HomeTown_0": (11, {"staircase_water"}),       # the brook's one-tile staircase (its banks: 7 pairs)
    "Route201_1": (16, set()),
    "Woodstock_2": (14, {"straight_water", "hedge"}),   # the far channel's straight bank; the row by the river
    "Route202_1": (9, {"staircase_water", "straight_forest", "straight_water"}),   # the ruler-straight brook
}


def ratchet(p, corpus, bands):
    print("ratchet (the corridor maps):")
    for name, (most, known) in RATCHET.items():
        m = p.load_map(name)
        rep = C.report(p, corpus, m.layout, m.j.get("map_type"), C.sketch_comments(p, name), bands)
        out = {r for r, _, ver, _, _, acc in rep["guides"] if ver in ("unusual", "beyond") and not acc}
        check(len(rep["pairs"]) <= most, f"{name}: {len(rep['pairs'])} odd pairs (at most {most})")
        check(out <= known, f"{name}: guides outside vanilla's band {sorted(out) or 'none'} "
                            f"(known: {sorted(known) or 'none'})")


# ------------------------------------------------------------------------------- the rest ----
def bands_reproducible(p, corpus, bands):
    fresh = C.calibrate(p, corpus)
    same = fresh == bands
    diff = [] if same else [k for k in ("maps", "bands", "values") if fresh.get(k) != bands.get(k)]
    check(same and len(fresh["maps"]["route"]) >= 20 and len(fresh["maps"]["town"]) >= 10,
          f"bands: vanilla re-measured gives composition_bands.json "
          f"({len(fresh['maps']['route'])} routes, {len(fresh['maps']['town'])} towns)"
          + (f"; differs in {diff}: run dev/terrain_report.py --calibrate" if diff else ""))


def vanilla_clean(p, corpus):
    for name in ("Route104", "Route116", "Route120", "PetalburgCity"):
        n = len(C.odd_pairs(corpus, p.load_map(name).layout, judged=False))
        check(n == 0, f"vanilla {name}: {n} odd pairs")


def accepting():
    sk = blank_sketch()
    try:
        sk.accept("no_such_rule", "why")
        ok = False
    except ValueError:
        ok = True
    try:
        sk.accept("hedge", " ")
        ok = False
    except ValueError:
        pass
    sk.accept("hedge", "an old fence line")
    sk.accept("hedge", "a windbreak")          # a second accept replaces the first
    acc = C.accepted(sk.comments)
    check(ok and acc == {"hedge": "a windbreak"}, f"accept: refuses unknown rules and empty reasons; {acc}")
    try:
        C.report(Project(), None, None, "MAP_TYPE_ROUTE", ["// accept: hedgerow: typo"])
        bad = False
    except ValueError:
        bad = True
    check(bad, "report: an `// accept:` line naming no rule is an error")


def main():
    verbose = "-v" in sys.argv
    p = Project()
    kit = build_kit(p)
    corpus = kit[0]
    bands = C.load_bands()
    bands_reproducible(p, corpus, bands)
    vanilla_clean(p, corpus)
    scenes(p, kit, bands, verbose)
    ratchet(p, corpus, bands)
    accepting()
    print(f"RESULT: {sum(RESULTS)}/{len(RESULTS)} checks pass")
    return 0 if all(RESULTS) and RESULTS else 1


if __name__ == "__main__":
    sys.exit(main())
