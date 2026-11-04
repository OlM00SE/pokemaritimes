"""The region blueprint: real geography, the places that anchor it, and how our maps fit it.

  python dev/blueprint.py                 # both views and the fit report
  python dev/blueprint.py --no-render     # the fit report only

Reads design/region/geo/maritimes_ne10m.json (Natural Earth, clipped by dev/geo_extract.py) and
design/region/anchors.toml. Writes:
  dev/out/blueprint_region.png    the whole frame: land, rivers, borders, anchors by stage, a
                                  50 km grid, and the area a 28x15 Town Map would cover
  dev/out/blueprint_corridor.png  western NB, HomeTown to Fredericton: our connected maps laid
                                  over the real river, as they are now (top) and with the
                                  [[plan]] maps inserted (bottom)

The fit: every anchor with a `map` pairs the real place (km) with its map's centre (tiles). One
scale (km per tile) and an offset are fitted by least squares, no rotation, then each anchor's
error is reported in km along with real and game bearings between neighbouring anchors. Lower
is closer to the real geography. Anchors with `fit = false` are drawn but not fitted.
"""
import argparse, json, math, os, sys, tomllib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
GEO = os.path.join(ROOT, "design", "region", "geo", "maritimes_ne10m.json")
ANCHORS = os.path.join(ROOT, "design", "region", "anchors.toml")
OUT = os.path.join(ROOT, "dev", "out")

LAT0 = 46.6                                   # projection: equirectangular, true at 46.6 N
KX = 111.32 * math.cos(math.radians(LAT0))    # km per degree of longitude
KY = 110.57                                   # km per degree of latitude
LON_W = -69.4                                 # km origin: the frame's west edge, LAT0
CORRIDOR = (-67.95, 45.70, -66.35, 46.45)     # lon0, lat0, lon1, lat1
FIT_START = "HomeTown_0"

SEA, LAND, LAKE, RIVER = (148, 186, 222), (226, 222, 196), (148, 186, 222), (70, 120, 200)
STAGE_COLOURS = {"built": (200, 40, 40), "corridor": (230, 140, 0), "later": (90, 90, 90)}


def km(lon, lat):
    """Real position in km: x east from LON_W, y south from LAT0 (screen-like)."""
    return ((lon - LON_W) * KX, (LAT0 - lat) * KY)


def load():
    with open(GEO, encoding="utf-8") as fh:
        geo = json.load(fh)
    with open(ANCHORS, "rb") as fh:
        spec = tomllib.load(fh)
    return geo, spec.get("anchor", []), spec.get("plan", [])


# --- the game's side ------------------------------------------------------------------------

def connection_graph(project, names):
    """{map: [(neighbour, direction)]} over edge connections among `names`."""
    g = {n: [] for n in names}
    for n in names:
        for c in project.load_map(n).connections:
            other = project.const_to_map.get(c["map"])
            if other in g and c["direction"] in ("up", "down", "left", "right"):
                g[n].append((other, c["direction"]))
    return g


def apply_plan(project, pos, size, plans):
    """Insert each planned map between two joined maps. Maps on the far side of the join (reached
    from the second map without crossing back) move by the new map's size along the join.
    Returns new (pos, size, planned names)."""
    pos, size, planned = dict(pos), dict(size), []
    graph = connection_graph(project, list(pos))
    for p in plans:
        a, b = p["between"]
        d = next((dr for o, dr in graph[a] if o == b), None)
        if d is None:
            raise SystemExit(f"plan {p['name']!r}: {a} and {b} aren't joined edge to edge")
        far, queue = {b}, [b]
        while queue:
            n = queue.pop()
            for o, _ in graph[n]:
                if o not in far and not (n == b and o == a):
                    far.add(o); queue.append(o)
        if a in far:
            raise SystemExit(f"plan {p['name']!r}: {a} is also reachable around the join")
        w, h = p["width"], p["height"]
        dx, dy = {"right": (w, 0), "left": (-w, 0), "down": (0, h), "up": (0, -h)}[d]
        bx, by = pos[b]
        for n in far:
            pos[n] = (pos[n][0] + dx, pos[n][1] + dy)
        # the new map takes the second map's old place, aligned on the join's axis
        ax, ay = pos[a]
        aw, ah = size[a]
        new = {"right": (ax + aw, by), "left": (ax - w, by),
               "down": (bx, ay + ah), "up": (bx, ay - h)}[d]
        pos[p["name"]], size[p["name"]] = new, (w, h)
        planned.append(p["name"])
    return pos, size, planned


def fit(anchors, pos, size):
    """Least-squares km = s * tile + t over anchors with a map. Returns (s, t, rows)."""
    pairs = []
    for a in anchors:
        if a.get("map") in pos:
            (x, y), (w, h) = pos[a["map"]], size[a["map"]]
            pairs.append((a, (x + w / 2, y + h / 2), km(a["lon"], a["lat"])))
    fitted = [p for p in pairs if p[0].get("fit", True)]
    if len(fitted) < 2:
        raise SystemExit("need two anchors with maps to fit")
    pairs, rest = fitted, [p for p in pairs if not p[0].get("fit", True)]
    gc = [sum(g[i] for _, g, _ in pairs) / len(pairs) for i in (0, 1)]
    rc = [sum(r[i] for _, _, r in pairs) / len(pairs) for i in (0, 1)]
    num = sum((g[0] - gc[0]) * (r[0] - rc[0]) + (g[1] - gc[1]) * (r[1] - rc[1]) for _, g, r in pairs)
    den = sum((g[0] - gc[0]) ** 2 + (g[1] - gc[1]) ** 2 for _, g, _ in pairs)
    s = num / den
    t = (rc[0] - s * gc[0], rc[1] - s * gc[1])
    # unfitted anchors are reported (and drawn) in their place, after the fitted ones' order
    ordered = sorted(fitted + rest, key=lambda p: next(i for i, a in enumerate(anchors) if a is p[0]))
    rows = [(a, g, r, (s * g[0] + t[0], s * g[1] + t[1])) for a, g, r in ordered]
    return s, t, rows


def bearing(p, q):
    """Compass bearing from p to q, both (east, south) coordinates."""
    return math.degrees(math.atan2(q[0] - p[0], -(q[1] - p[1]))) % 360


def compass(b):
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W",
            "WNW", "NW", "NNW"][int((b + 11.25) // 22.5) % 16]


def report(title, s, rows):
    print(f"\n{title}: {s:.2f} km per tile")
    total = 0.0
    for a, g, r, f in rows:
        err = math.dist(r, f)
        if a.get("fit", True):
            total += err
        print(f"  {a['name']:<12} {a['map']:<14} off by {err:5.1f} km"
              + ("" if a.get("fit", True) else "  (not fitted)"))
    print(f"  total {total:.1f} km")
    for (a, g1, r1, _), (b, g2, r2, _) in zip(rows, rows[1:]):
        rb, gb = bearing(r1, r2), bearing(g1, g2)
        diff = (gb - rb + 180) % 360 - 180
        print(f"  {a['name']} -> {b['name']}: real {math.dist(r1, r2):5.1f} km {compass(rb):>3} "
              f"({rb:3.0f}); game {math.dist(g1, g2):5.1f} tiles {compass(gb):>3} ({gb:3.0f}), "
              f"bearing off {diff:+.0f}")
    return total


# --- drawing --------------------------------------------------------------------------------

def font(size):
    """A TrueType font with accents (Gaspé, Percé); PIL's built-in one lacks them."""
    from PIL import ImageFont
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


class Canvas:
    def __init__(self, frame, px_per_km, margin=30):
        from PIL import Image, ImageDraw
        self.ppk, self.m = px_per_km, margin
        self.x0, self.y0 = km(frame[0], frame[3])
        x1, y1 = km(frame[2], frame[1])
        self.img = Image.new("RGB", (int((x1 - self.x0) * px_per_km) + 2 * margin,
                                     int((y1 - self.y0) * px_per_km) + 2 * margin), SEA)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def p(self, kx, ky):
        return (self.m + (kx - self.x0) * self.ppk, self.m + (ky - self.y0) * self.ppk)

    def ll(self, lon, lat):
        return self.p(*km(lon, lat))

    def geography(self, geo, river_width=2):
        for ring in geo["land"]:
            self.d.polygon([self.ll(*pt) for pt in ring], fill=LAND)
        for lake in geo["lakes"]:
            self.d.polygon([self.ll(*pt) for pt in lake["ring"]], fill=LAKE)
        for r in geo["rivers"]:
            for ln in r["lines"]:
                self.d.line([self.ll(*pt) for pt in ln], fill=RIVER, width=river_width)
        for b in geo["borders"]:
            for ln in b["lines"]:
                self.dashed([self.ll(*pt) for pt in ln], (120, 100, 140, 220))

    def dashed(self, pts, colour, on=6, off=4, width=1):
        acc, draw = 0.0, True
        for a, b in zip(pts, pts[1:]):
            seg = math.dist(a, b)
            pos = 0.0
            while pos < seg:
                step = min((on if draw else off) - acc, seg - pos)
                if draw:
                    t0, t1 = pos / seg, (pos + step) / seg
                    self.d.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                                 (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)],
                                fill=colour, width=width)
                pos += step; acc += step
                if acc >= (on if draw else off):
                    acc, draw = 0.0, not draw

    def rect_dashed(self, box, colour, width=2):
        x0, y0, x1, y1 = box
        self.dashed([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], colour, 8, 5, width)

    def grid(self, step_km, colour=(0, 0, 0, 28)):
        w, h = self.img.size
        k = math.ceil(self.x0 / step_km) * step_km
        while self.p(k, 0)[0] < w:
            x = self.p(k, 0)[0]; self.d.line([(x, 0), (x, h)], fill=colour); k += step_km
        k = math.ceil(self.y0 / step_km) * step_km
        while self.p(0, k)[1] < h:
            y = self.p(0, k)[1]; self.d.line([(0, y), (w, y)], fill=colour); k += step_km

    def anchor(self, a, f, r=4, label=True):
        x, y = self.ll(a["lon"], a["lat"])
        c = STAGE_COLOURS.get(a.get("stage"), (0, 0, 0))
        self.d.ellipse((x - r, y - r, x + r, y + r), fill=c, outline=(255, 255, 255))
        if label:
            if a.get("label") == "left":
                w = self.d.textlength(a["name"], font=f)
                self.text((x - r - 3 - w, y - 7), a["name"], f, c)
            else:
                self.text((x + r + 3, y - 7), a["name"], f, c)

    def text(self, xy, s, f, colour=(0, 0, 0)):
        x, y = xy
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.d.text((x + dx, y + dy), s, font=f, fill=(255, 255, 255, 200))
        self.d.text((x, y), s, font=f, fill=colour)

    def scale_bar(self, kmlen, f):
        x, y = self.m, self.img.size[1] - self.m // 2 - 6
        self.d.rectangle((x, y, x + kmlen * self.ppk, y + 4), fill=(0, 0, 0))
        self.text((x + kmlen * self.ppk + 6, y - 6), f"{kmlen} km", f)


def draw_maps(cv, project, pos, size, s, t, planned, f, render_tiles=True):
    """Our maps placed by the fit; rendered maps translucent, planned ones as dashed boxes."""
    from PIL import Image
    from mapkit import render
    for name, (x, y) in pos.items():
        w, h = size[name]
        p0 = cv.p(s * x + t[0], s * y + t[1])
        p1 = cv.p(s * (x + w) + t[0], s * (y + h) + t[1])
        box = tuple(int(round(v)) for v in (*p0, *p1))
        if name in planned:
            cv.d.rectangle(box, fill=(255, 255, 255, 70))
            cv.rect_dashed(box, (230, 140, 0, 255), 3)
            cv.text((box[0] + 4, box[1] + 3), name, f, (180, 90, 0))
            continue
        if render_tiles and box[2] > box[0] and box[3] > box[1]:
            tile = render.render_map(project, name).resize((box[2] - box[0], box[3] - box[1]),
                                                          Image.LANCZOS).convert("RGBA")
            tile.putalpha(150)
            cv.img.paste(tile, box[:2], tile)
        cv.d.rectangle(box, outline=(255, 255, 255, 230), width=2)
        cv.text((box[0] + 4, box[1] + 3), name, f, (20, 20, 120))


def link_lines(cv, rows):
    """From each fitted map centre to its real place."""
    for a, g, r, fpos in rows:
        cv.d.line([cv.p(*fpos), cv.ll(a["lon"], a["lat"])], fill=(200, 0, 0, 220), width=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    geo, anchors, plans = load()
    from mapkit.project import Project
    from mapkit import render
    project = Project()
    pos, size = render.world_positions(project, FIT_START)
    s0, t0, rows0 = fit(anchors, pos, size)
    e0 = report("Now", s0, rows0)
    ppos, psize, planned = apply_plan(project, pos, size, plans)
    s1, t1, rows1 = fit(anchors, ppos, psize)
    e1 = report("With the plan (" + ", ".join(planned) + ")", s1, rows1)
    print(f"\nfit error: now {e0:.1f} km, with the plan {e1:.1f} km")
    if a.no_render:
        return
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    f, fb = font(13), font(18)

    # the whole region
    rc = Canvas(geo["frame"], 1.35)
    rc.geography(geo, 2)
    rc.grid(50)
    tm_w = 28                                          # a 28x15 Town Map fitted to the frame width
    sq = (km(geo["frame"][2], LAT0)[0] - km(geo["frame"][0], LAT0)[0]) / tm_w
    top = km(0 + LON_W, 50.0)[1]
    box = (*rc.p(0, top), *rc.p(tm_w * sq, top + 15 * sq))
    rc.rect_dashed(box, (0, 0, 0, 150), 2)
    rc.text((box[0] + 6, box[1] + 4), f"Dashed box: what a 28x15 Town Map covers at {sq:.0f} km "
            "per square, fitted to the frame's width", f, (40, 40, 40))
    for name, (x, y) in ppos.items():
        w, h = psize[name]
        b = (*rc.p(s1 * x + t1[0], s1 * y + t1[1]), *rc.p(s1 * (x + w) + t1[0], s1 * (y + h) + t1[1]))
        rc.d.rectangle(b, outline=(230, 140, 0) if name in planned else (200, 40, 40), width=1)
    for an in anchors:                     # the corridor's places are too close to label here
        rc.anchor(an, f, label=an.get("stage") == "later" or an["name"] in ("Woodstock", "Fredericton"))
    rc.text((rc.m, 4), "PokéMaritimes blueprint: anchors (red built, orange corridor, grey later); "
                       "our maps as boxes at the corridor's fit; 50 km grid", fb)
    rc.scale_bar(100, f)
    rc.img.save(os.path.join(OUT, "blueprint_region.png"))

    # the corridor, now and with the plan
    panels = []
    for title, (pp, ps, s, t, rows, pl) in (
            (f"Now: our maps fitted to the real places ({s0:.2f} km per tile, {e0:.0f} km off in all)",
             (pos, size, s0, t0, rows0, [])),
            (f"With the plan: {', '.join(planned)} ({s1:.2f} km per tile, {e1:.0f} km off in all)",
             (ppos, psize, s1, t1, rows1, planned))):
        cv = Canvas(CORRIDOR, 7.0, 34)
        cv.geography(geo, 5)
        cv.grid(10)
        draw_maps(cv, project, pp, ps, s, t, pl, f)
        link_lines(cv, rows)
        for an in anchors:
            if CORRIDOR[0] <= an["lon"] <= CORRIDOR[2] and CORRIDOR[1] <= an["lat"] <= CORRIDOR[3]:
                cv.anchor(an, fb, 6)
        cv.text((cv.m, 8), title, fb)
        cv.scale_bar(10, f)
        panels.append(cv.img)
    out = Image.new("RGB", (max(p.width for p in panels), sum(p.height for p in panels)), (0, 0, 0))
    y = 0
    for p in panels:
        out.paste(p, (0, y)); y += p.height
    out.save(os.path.join(OUT, "blueprint_corridor.png"))
    print("wrote dev/out/blueprint_region.png, dev/out/blueprint_corridor.png")


if __name__ == "__main__":
    sys.exit(main())
