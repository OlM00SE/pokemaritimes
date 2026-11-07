"""Visual rules report: how a map's terrain compares with what vanilla's own maps do.

  python dev/terrain_report.py [Map ...]        # report card + dev/out/terrain/<Map>.png
  python dev/terrain_report.py --calibrate      # re-measure vanilla, rewrite mapkit/composition_bands.json
  python dev/terrain_report.py --vanilla        # vanilla's calibration maps, rule by rule

With no map named it reports every Maritimes outdoor map on General. The rules and their tiers are
in mapkit/composition.py; the findings behind them in design/mapping_reference.md section 18.
The PNG draws each finding on the map: odd pairs red, guides outside vanilla's band in their colour
(the legend is in the header), accepted guides not drawn.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit import composition as C

COLOURS = {
    "pairs": (255, 40, 40), "staircase_water": (0, 230, 255), "staircase_forest": (0, 255, 120),
    "straight_forest": (255, 150, 0), "straight_water": (255, 210, 0), "grass_rect": (255, 255, 0),
    "grass_cover": (255, 0, 255), "hedge": (170, 90, 255), "flower_singles": (255, 120, 190),
    "bare_screens": (255, 255, 255), "open_space": (120, 160, 255),
}


def ours(p, corpus):
    vanilla = {e["id"] for e in corpus._vanilla_layouts()}
    out = []
    for name in p.map_names:
        m = p.load_map(name)
        if m.j.get("map_type") in C.OUTDOOR and m.layout.primary == C.PRIMARY \
                and m.layout.entry["id"] not in vanilla:
            out.append(name)
    return out


def print_report(name, rep):
    print(f"== {name} ({rep['kind']}): {C.summary_line(rep)}")
    if rep["pairs"]:
        print(f"  strict: {len(rep['pairs'])} pairs vanilla never draws side by side:")
        for line in C.describe_pairs(rep["pairs"], limit=8):
            print(f"    {line}")
    print(f"  {'guide':17s} {'value':>6}  vanilla {rep['kind']}s p10 / p50 / p90 (min-max)   verdict")
    for rule, v, ver, band, _, acc in rep["guides"]:
        b = (f"{C.fmt(band['p10']):>5} / {C.fmt(band['p50']):>5} / {C.fmt(band['p90']):>5} "
             f"({C.fmt(band['min'])}-{C.fmt(band['max'])})") if band else "(no band)"
        mark = f"accepted: {acc}" if acc and ver in ("unusual", "beyond") else ver
        print(f"  {rule:17s} {C.fmt(v):>6}  {b:38s} {mark}")


def render(p, name, rep, out):
    m = p.load_map(name)
    draw(p, m.layout, rep, name, m).save(out)


def draw(p, layout, rep, title, mapdata=None, s=2):
    """The layout with the report's findings drawn on it, under a header (title, summary, legend)."""
    from PIL import Image, ImageDraw
    from mapkit.render import render_layout
    img = render_layout(p, layout, s, (), mapdata).convert("RGBA")
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    t = 16 * s
    for rule, v, ver, band, cells, acc in rep["guides"]:
        if ver not in ("unusual", "beyond") or acc:
            continue
        col = COLOURS[rule]
        if rule == "bare_screens":
            for x, y in set(cells):
                d.rectangle([x * t, y * t, x * t + t - 1, y * t + t - 1], fill=(255, 255, 255, 40))
            continue
        if rule == "open_space":
            for x, y in cells:
                r = v * t
                cx, cy = x * t + t // 2, y * t + t // 2
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col + (255,), width=3)
            continue
        for x, y in cells:
            d.rectangle([x * t + 3, y * t + 3, x * t + t - 4, y * t + t - 4], outline=col + (255,), width=2)
    for x, y, dd, a, b in rep["pairs"]:
        nx, ny = (x + 1, y) if dd == "E" else (x, y + 1)
        d.rectangle([min(x, nx) * t, min(y, ny) * t, (max(x, nx) + 1) * t - 1, (max(y, ny) + 1) * t - 1],
                    outline=COLOURS["pairs"] + (255,), width=2)
    img = Image.alpha_composite(img, over).convert("RGB")
    summary = f"{title}: {C.summary_line(rep)}"
    shown = [r for r, v, ver, _, _, acc in rep["guides"] if ver in ("unusual", "beyond") and not acc]
    legend = ["pairs"] * bool(rep["pairs"]) + shown
    width = max(img.width, 400)
    per_line = max(40, width // 6)
    text = [summary[i:i + per_line] for i in range(0, len(summary), per_line)]
    head = 14 * len(text) + 18
    canvas = Image.new("RGB", (width, img.height + head), (24, 24, 32))
    dd = ImageDraw.Draw(canvas)
    for i, line in enumerate(text):
        dd.text((4, 2 + 14 * i), line, fill=(255, 255, 0))
    x, y = 4, 4 + 14 * len(text)
    for r in legend:
        if x + 20 + 7 * len(r) > width:
            break
        dd.rectangle([x, y, x + 10, y + 10], outline=COLOURS[r], width=2)
        dd.text((x + 14, y - 1), r, fill=(230, 230, 230))
        x += 20 + 7 * len(r)
    canvas.paste(img, (0, head))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--calibrate", action="store_true", help="re-measure vanilla and rewrite the bands")
    ap.add_argument("--vanilla", action="store_true", help="vanilla's calibration maps, rule by rule")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args()
    p = Project()
    corpus = Corpus(p)
    if a.calibrate:
        data = C.calibrate(p, corpus)
        C.save_bands(data)
        print(f"wrote {os.path.relpath(C.BANDS_FILE, p.root)}: "
              + ", ".join(f"{len(v)} {k}s" for k, v in data["maps"].items()))
        a.vanilla = True
    if a.vanilla:
        data = C.load_bands()
        for k, names in data["maps"].items():
            print(f"== vanilla {k}s ({len(names)})")
            print("  " + "map".ljust(22) + "".join(r[:12].rjust(13) for r in C.RULES))
            for n in names:
                v = data["values"][n]
                print("  " + n[:21].ljust(22) + "".join(C.fmt(v[r]).rjust(13) for r in C.RULES))
            b = data["bands"][k]
            for q in ("p10", "p50", "p90", "max"):
                print("  " + q.ljust(22) + "".join(C.fmt(b[r][q] if r in b else None).rjust(13) for r in C.RULES))
        return 0
    names = a.maps or ours(p, corpus)
    bands = C.load_bands()
    outdir = p.path("dev", "out", "terrain")
    os.makedirs(outdir, exist_ok=True)
    failed = []
    for name in names:
        m = p.load_map(name)
        try:
            rep = C.report(p, corpus, m.layout, m.j.get("map_type"), C.sketch_comments(p, name), bands)
        except ValueError as ex:          # an `// accept:` line naming no rule: report the rest
            print(f"== {name}: ERROR {ex}")
            failed.append(name)
            continue
        print_report(name, rep)
        if not a.no_png:
            out = os.path.join(outdir, f"{name}.png")
            render(p, name, rep, out)
            print(f"  -> {os.path.relpath(out, p.root)}")
    if failed:
        print(f"{len(failed)} map(s) not reported: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
