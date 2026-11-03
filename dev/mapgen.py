"""Map generation pipeline: sketch -> map.bin -> checks -> renders.

  python dev/mapgen.py extract <Map> [-o design/maps/<Map>.txt]   # existing map -> editable sketch
  python dev/mapgen.py build design/maps/<Map>.txt [--fresh] [--apply]   # dry run unless --apply
      Every build runs the checker on the result in memory and writes dev/out/<Map>_preview.png
      and _preview_overlay.png (collision, elevation, ledge arrows, events, one-way traps).
      It also reports how many cells differ from the current map.bin and writes
      _preview_diff.png (before | after, cropped to the change, changed cells outlined).
      --apply writes map.bin only if the result has no NEW checker errors (errors the map
      already had don't block a rebuild); --force overrides.
      A sketch whose ledges can't be built (bad shape, or a jump landing on a tree, water, a
      solid tile, or off the map) is refused with the cells to fix.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.corpus import Corpus
from mapkit.terrain import (Vocabulary, learn, vanilla_maps, class_adjacency, forbidden_pairs,
                            grid_labels, TREE_Q)
from mapkit.sketch import Sketch, SketchError, extract, compile_sketch
from mapkit.render import render_layout, render_diff, render_contexts
from mapkit.checks import check_map
from mapkit import landscape, routes


def render_context_pair(p, m, old_blocks, margin=6):
    """The map with its neighbours' edges (render.render_context), before above after."""
    import copy
    from PIL import Image, ImageDraw
    old = copy.copy(m.layout)            # the same layout with the old blocks; m stays untouched
    old.blocks = list(old_blocks)
    before, after = render_contexts(p, m.name, [old, m.layout], margin)
    head = 14
    out = Image.new("RGB", (before.width, (before.height + head) * 2), (24, 24, 32))
    d = ImageDraw.Draw(out)
    for i, (label, im) in enumerate((("before", before), ("after", after))):
        y = i * (before.height + head)
        d.text((4, y + 1), f"{label} (neighbours dimmed, {margin}-tile strips)", fill=(255, 255, 0))
        out.paste(im, (0, y + head))
    return out


def terrain_guard(vocab, layout, repaired):
    """The grammar repairs forbidden joins by turning the lower-ranked cell into grass (trees
    outrank sand). On a fresh design that is design feedback; on terrain the map already has,
    it is damage: e.g. a hand-painted tree beside a sand lane makes the build clear the lane.
    Returns a message naming the cells where a repair overwrites terrain the current map already
    has as the sketch draws it, or None. mapgen counts it as a new error (--apply refuses)."""
    if not repaired:
        return None
    cur = grid_labels(vocab, layout.entry, layout.blocks, layout.width, layout.height)
    norm = lambda c: "T" if c in TREE_Q else c
    hit = sorted((x, y) for (x, y), (drawn, _) in repaired.items() if norm(cur[y][x]) == drawn)
    if not hit:
        return None
    kinds = sorted({repaired[c][0] for c in hit})
    return (f"the grammar would turn {len(hit)} cells of existing terrain ({', '.join(kinds)}) into grass, "
            f"e.g. {hit[:6]} (outranked by {[repaired[c][1] for c in hit[:6]]}). A hand-painted join "
            "the grammar forbids, such as trees beside a sand lane: keep both sides as '#' (whole "
            "trees), or give the road a grass verge")


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
        entries = vanilla_maps(corpus)
        # shore cells are verified by compiling, with the same grammar a build uses
        sk = extract(p, vocab, a.target, learn(p, vocab, entries),
                     forbidden_pairs(class_adjacency(p, vocab, entries)), corpus)
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
    repaired = report.pop("grammar_cells", {})
    print(f"{sk.map_name}: compiled {sk.w}x{sk.h}; {report}")
    for wmsg in warnings:
        print(f"  ledge warning {wmsg}")
    guard = terrain_guard(vocab, m.layout, repaired)
    if guard:
        print(f"  GUARD terrain: {guard}   <- NEW")
    # errors the map already has (accepted or known) don't block a rebuild; only new ones do
    old_detail = {}
    before = {(c, msg) for s, c, msg in check_map(p, sk.map_name, None, corpus, mapdata=m, detail=old_detail)
              if s == "ERROR"}
    old_metrics = landscape.metrics(m.layout)
    old_routes = routes.route_stats(p, m) if m.connections else None
    old_blocks = list(m.layout.blocks)
    m.layout.blocks = blocks          # in memory only; nothing is written without --apply
    outdir = p.path("dev", "out")
    os.makedirs(outdir, exist_ok=True)
    # what this build changes in the existing map.bin, so an edit can be reviewed (and kept small)
    diff_png = os.path.join(outdir, f"{sk.map_name}_preview_diff.png")
    diff, changed = render_diff(p, m.layout, old_blocks)
    if diff is None:
        print("changes vs current map.bin: none")
        if os.path.exists(diff_png):
            os.remove(diff_png)       # don't leave a stale diff from an earlier build
    else:
        xs = [x for x, _ in changed]; ys = [y for _, y in changed]
        mids = sum(1 for x, y in changed
                   if old_blocks[y * m.layout.width + x] & 0x3FF != m.layout.mid(x, y))
        print(f"changes vs current map.bin: {len(changed)} cells ({mids} metatiles, the rest collision/"
              f"elevation only) in x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}")
        diff.save(diff_png)
    # the seams as the player crosses them: before above after, with the neighbours' edges
    ctx_png = os.path.join(outdir, f"{sk.map_name}_preview_context.png")
    if diff is not None and m.connections:
        render_context_pair(p, m, old_blocks).save(ctx_png)
    elif os.path.exists(ctx_png):
        os.remove(ctx_png)
    # the checker runs on the unsaved result, so a dry run already shows traps and bad landings
    detail = {}
    issues = check_map(p, sk.map_name, None, corpus, mapdata=m, detail=detail)
    render_layout(p, m.layout, 1, (), m).save(os.path.join(outdir, f"{sk.map_name}_preview.png"))
    render_layout(p, m.layout, 2, ("collision", "elevation", "behavior", "events", "grid", "traps"), m,
                  detail).save(os.path.join(outdir, f"{sk.map_name}_preview_overlay.png"))
    print(f"previews: dev/out/{sk.map_name}_preview.png, _preview_overlay.png"
          + (", _preview_diff.png" if diff is not None else "")
          + (", _preview_context.png" if diff is not None and m.connections else ""))
    # landscape: Tom's two visual complaints as numbers (lower is more natural), for the whole
    # map and for the part this build changes
    new_metrics = landscape.metrics(m.layout)
    at = lambda box: f" at x {box[0]}-{box[2]}, y {box[1]}-{box[3]}" if box else ""
    print("landscape: longest straight forest edge {} -> {} tiles{}; largest bare grass square {} -> {}{}"
          .format(old_metrics["straight_edge"], new_metrics["straight_edge"],
                  at(new_metrics["straight_edge_at"]), old_metrics["open_square"],
                  new_metrics["open_square"], at(new_metrics["open_square_at"])))
    if diff is not None:
        box = (min(xs), min(ys), max(xs), max(ys))
        after = landscape.metrics(m.layout, box)
        new_blocks, m.layout.blocks = m.layout.blocks, old_blocks
        before_box = landscape.metrics(m.layout, box)
        m.layout.blocks = new_blocks
        print("  in the changed area x {}-{}, y {}-{}: straight edge {} -> {}; bare square {} -> {}"
              .format(box[0], box[2], box[1], box[3], before_box["straight_edge"], after["straight_edge"],
                      before_box["open_square"], after["open_square"]))
    # gameplay: each crossing's length and unavoidable tall grass, and the encounter ground,
    # so a redesign can show it still plays the same
    if m.connections:
        print("routes (on foot, between edge connections):")
        for line in routes.describe(old_routes, routes.route_stats(p, m)):
            print(line)
    # accessibility: open land nobody can walk to, where this build is responsible: it was
    # reachable before, or this build changed it (e.g. a pocket left where forest was cleared)
    if "foot" in old_detail and "foot" in detail:
        L = m.layout
        touched = set(changed or ())
        land = lambda x, y: L.coll(x, y) == 0 and not \
            p.tile_flags.get(L.tiles.behavior(L.mid(x, y)), 0) & TILE_FLAG_SURFABLE
        cut = sorted((x, y) for y in range(L.height) for x in range(L.width)
                     if land(x, y) and (x, y) not in detail["foot"]
                     and ((x, y) in old_detail["foot"] or (x, y) in touched))
        if cut:
            print(f"  WARN reach: {len(cut)} open tiles can't be reached on foot (newly cut off, or "
                  f"changed by this build), e.g. {cut[:6]}   <- a pocket? check the overlay")
    elif diff is not None:
        print("  (reach not compared: the walk exploration was truncated on this map)")
    new = [guard] if guard else []
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
