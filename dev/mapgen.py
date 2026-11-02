"""Map generation pipeline: sketch -> map.bin -> checks -> renders.

  python dev/mapgen.py extract <Map> [-o design/maps/<Map>.txt]   # existing map -> editable sketch
  python dev/mapgen.py build design/maps/<Map>.txt [--fresh] [--apply]   # dry run unless --apply
      Every build runs the checker on the result in memory and writes dev/out/<Map>_preview.png
      and _preview_overlay.png (collision, elevation, ledge arrows, events, one-way traps).
      --apply writes map.bin only if the result has no NEW checker errors (errors the map
      already had don't block a rebuild); --force overrides.
      A sketch whose ledges can't be built (bad shape, or a jump landing on a tree, water, a
      solid tile, or off the map) is refused with the cells to fix.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, learn, vanilla_maps, class_adjacency, forbidden_pairs
from mapkit.sketch import Sketch, SketchError, extract, compile_sketch
from mapkit.render import render_layout
from mapkit.checks import check_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "build"])
    ap.add_argument("target")
    ap.add_argument("-o", "--out")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="new design: ignore the existing map's tree placement")
    ap.add_argument("--force", action="store_true",
                    help="apply even if the result has new checker errors")
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
    entries = vanilla_maps(corpus)
    rules = learn(p, vocab, entries)
    forbidden = forbidden_pairs(class_adjacency(p, vocab, entries))
    try:
        blocks, report = compile_sketch(p, corpus, rules, sk, m.layout, vocab, forbidden, fresh=a.fresh)
    except SketchError as ex:
        print(f"{sk.map_name}: NOT BUILT, the sketch has {len(ex.problems)} problem(s) (x,y = column,row):")
        print(ex)
        return 1
    warnings = report.pop("ledge_warnings", [])
    print(f"{sk.map_name}: compiled {sk.w}x{sk.h}; {report}")
    for wmsg in warnings:
        print(f"  ledge warning {wmsg}")
    # errors the map already has (accepted or known) don't block a rebuild; only new ones do
    before = {(c, msg) for s, c, msg in check_map(p, sk.map_name, None, corpus, mapdata=m) if s == "ERROR"}
    m.layout.blocks = blocks          # in memory only; nothing is written without --apply
    outdir = p.path("dev", "out")
    os.makedirs(outdir, exist_ok=True)
    # the checker runs on the unsaved result, so a dry run already shows traps and bad landings
    detail = {}
    issues = check_map(p, sk.map_name, None, corpus, mapdata=m, detail=detail)
    render_layout(p, m.layout, 1, (), m).save(os.path.join(outdir, f"{sk.map_name}_preview.png"))
    render_layout(p, m.layout, 2, ("collision", "elevation", "behavior", "events", "grid", "traps"), m,
                  detail).save(os.path.join(outdir, f"{sk.map_name}_preview_overlay.png"))
    print(f"previews: dev/out/{sk.map_name}_preview.png, _preview_overlay.png")
    new = []
    for s, c, msg in issues:
        is_new = s == "ERROR" and (c, msg) not in before
        new += [msg] if is_new else []
        print(f"  {s} {c}: {msg}{'   <- NEW' if is_new else ''}")
    errors = sum(1 for s, _, _ in issues if s == "ERROR")
    print(f"checker: {errors} errors ({len(new)} new from this sketch), {len(issues) - errors} other")
    if not a.apply:
        print("dry run: nothing written (pass --apply to write map.bin)")
        return 1 if new else 0
    if new and not a.force:
        print("NOT APPLIED: fix the errors marked NEW first (or pass --force)")
        return 1
    m.layout.save()
    print(f"applied: {m.layout.entry['blockdata_filepath']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
