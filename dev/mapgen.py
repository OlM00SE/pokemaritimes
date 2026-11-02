"""Map generation pipeline: sketch -> map.bin -> checks -> renders.

  python dev/mapgen.py extract <Map> [-o design/maps/<Map>.txt]   # existing map -> editable sketch
  python dev/mapgen.py build design/maps/<Map>.txt [--apply]      # compile; dry run unless --apply
      dry run writes dev/out/<Map>_preview.png (+ overlays) without touching the map
      --apply writes map.bin, then runs the checker
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, learn, vanilla_maps
from mapkit.sketch import Sketch, extract, compile_sketch
from mapkit.render import render_layout
from mapkit.checks import check_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "build"])
    ap.add_argument("target")
    ap.add_argument("-o", "--out")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    p = Project()
    corpus = Corpus(p)
    vocab = Vocabulary(p, corpus)
    if a.cmd == "extract":
        sk = extract(p, vocab, a.target, learn(p, vocab, vanilla_maps(corpus)))
        out = a.out or p.path("design", "maps", f"{a.target}.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sk.save(out)
        print(f"wrote {out} ({sk.w}x{sk.h})")
        return 0

    sk = Sketch.load(a.target)
    m = p.load_map(sk.map_name)
    rules = learn(p, vocab, vanilla_maps(corpus))
    blocks, report = compile_sketch(p, corpus, rules, sk, m.layout, vocab)
    print(f"{sk.map_name}: compiled {sk.w}x{sk.h}; {report}")
    old = list(m.layout.blocks)
    m.layout.blocks = blocks
    outdir = p.path("dev", "out")
    os.makedirs(outdir, exist_ok=True)
    render_layout(p, m.layout, 1, (), m).save(os.path.join(outdir, f"{sk.map_name}_preview.png"))
    render_layout(p, m.layout, 2, ("collision", "elevation", "behavior", "events", "grid"), m) \
        .save(os.path.join(outdir, f"{sk.map_name}_preview_overlay.png"))
    print(f"previews: dev/out/{sk.map_name}_preview.png, _preview_overlay.png")
    if not a.apply:
        m.layout.blocks = old
        return 0
    m.layout.save()
    issues = check_map(p, sk.map_name)
    for s, c, msg in issues:
        print(f"  {s} {c}: {msg}")
    errors = sum(1 for s, _, _ in issues if s == "ERROR")
    print(f"applied; checker: {errors} errors, {len(issues) - errors} other")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
