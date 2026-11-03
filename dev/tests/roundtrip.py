"""Round-trip test: extract a map to a sketch, compile it back (no files touched), and count
how many metatiles render identically to the original.

  python dev/tests/roundtrip.py [Map ...]     (default: the Maritimes overworld maps)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageChops
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, learn, vanilla_maps, class_adjacency, forbidden_pairs
from mapkit.sketch import extract, compile_sketch
from mapkit.render import render_layout

maps = sys.argv[1:] or ["HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1", "Fredericton_0",
                        "Route203_1", "Route203_1_2"]
p = Project(); c = Corpus(p); v = Vocabulary(p, c)
entries = vanilla_maps(c)
rules = learn(p, v, entries)
# compile the way mapgen build does, grammar repair included: a repair that touches an
# extracted map is terrain a rebuild would damage (e.g. the sand beside hand-painted trees)
forbidden = forbidden_pairs(class_adjacency(p, v, entries))
out = p.path("dev", "out")
damaged = 0
for name in maps:
    m = p.load_map(name)
    before = render_layout(p, m.layout)
    sk = extract(p, v, name, rules, forbidden, c)
    blocks, rep = compile_sketch(p, c, rules, sk, m.layout, v, forbidden)
    if rep["grammar_cells"]:
        damaged += 1
        print(f"{name:14} FAIL: the grammar repairs {len(rep['grammar_cells'])} extracted cells, "
              f"e.g. {sorted(rep['grammar_cells'])[:4]}")
    orig = m.layout.blocks
    m.layout.blocks = blocks
    after = render_layout(p, m.layout)
    m.layout.blocks = orig
    d = ImageChops.difference(before, after).convert("L")
    W, H = m.layout.width, m.layout.height
    diff = [(x, y) for y in range(H) for x in range(W) if d.crop((x * 16, y * 16, x * 16 + 16, y * 16 + 16)).getbbox()]
    print(f"{name:14} {W * H - len(diff):5}/{W * H} identical ({1 - len(diff) / (W * H):.1%})  "
          f"dropped trees: {rep['dropped_tree_cells']}")
    if diff:
        from PIL import Image, ImageDraw
        comp = Image.new("RGB", (before.width * 2 + 8, before.height))
        comp.paste(before, (0, 0)); comp.paste(after, (before.width + 8, 0))
        dr = ImageDraw.Draw(comp)
        for x, y in diff:
            dr.rectangle((before.width + 8 + x * 16, y * 16, before.width + 8 + x * 16 + 15, y * 16 + 15), outline=(255, 0, 0))
        comp.save(os.path.join(out, f"roundtrip_{name}.png"))
print("PASS: no extracted cell is repaired by the grammar" if not damaged else
      f"FAIL: {damaged} maps would be changed by the grammar on a rebuild")

# the guard: an extract as it was before joins were kept (HomeTown's lane-side trees read as
# forest beside the sand) must be refused by mapgen build's terrain guard
from mapgen import terrain_guard
m = p.load_map("Route201_1")
sk = extract(p, v, "Route201_1", rules, forbidden, c)
for y in (0, 1):
    for x in (8, 9, 12, 13):
        sk.rows[y][x] = "T"
    for x in (10, 11):
        sk.rows[y][x] = ":"
_, rep = compile_sketch(p, c, rules, sk, m.layout, v, forbidden)
msg = terrain_guard(v, m.layout, rep["grammar_cells"])
lane = {(10, 0), (11, 0), (10, 1), (11, 1)}
guard_ok = bool(msg) and lane <= set(rep["grammar_cells"])
print(("PASS" if guard_ok else "FAIL") + ": the terrain guard refuses a build that clears HomeTown's lane"
      + (f" ({msg[:60]}...)" if msg else ""))
sys.exit(1 if damaged or not guard_ok else 0)
