"""Round-trip test: extract a map to a sketch, compile it back (no files touched), and count
how many metatiles render identically to the original.

  python dev/tests/roundtrip.py [Map ...]     (default: the Maritimes overworld maps)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageChops
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, learn, vanilla_maps
from mapkit.sketch import extract, compile_sketch
from mapkit.render import render_layout

maps = sys.argv[1:] or ["HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1", "Fredericton_0",
                        "Route203_1", "Route203_1_2"]
p = Project(); c = Corpus(p); v = Vocabulary(p, c)
rules = learn(p, v, vanilla_maps(c))
out = p.path("dev", "out")
for name in maps:
    m = p.load_map(name)
    before = render_layout(p, m.layout)
    sk = extract(p, v, name, rules)
    blocks, rep = compile_sketch(p, c, rules, sk, m.layout, v)
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
