"""Real geography for the region blueprint and the corridor plan.

Projection: equirectangular, true at LAT0. km(lon, lat) gives (east, south) km from a fixed
origin, screen-like (y grows south). The corridor plan (design/region/corridor.toml) puts world
tile (0, 0) on an anchor place and uses one km-per-tile scale, so a map's rectangle in world
tiles is also a real-world rectangle, and the real river can be drawn into it.

Water in the plan:
  - `natural_earth = "<river name>"`: the river's centreline from the clipped Natural Earth data,
    smoothed (Chaikin), with a width in tiles that varies along it: `widths` gives the width at
    named anchors, and every point takes the inverse-distance blend of the two nearest.
  - `world = [[x, y], ...]` with one `width`: a polyline drawn by hand in world tiles, for
    water the data doesn't have or for an inset (a map drawn zoomed in, not to the plan's scale).
A cell is water when its centre is within width / 2 of the line. Every map's underlay is cut from
the same world raster, so neighbours always agree at a seam.
"""
import json, math, os, tomllib

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
GEO = os.path.join(ROOT, "design", "region", "geo", "maritimes_ne10m.json")
ANCHORS = os.path.join(ROOT, "design", "region", "anchors.toml")
CORRIDOR = os.path.join(ROOT, "design", "region", "corridor.toml")

LAT0 = 46.6                                   # projection: equirectangular, true at 46.6 N
KX = 111.32 * math.cos(math.radians(LAT0))    # km per degree of longitude
KY = 110.57                                   # km per degree of latitude
LON_W = -69.4                                 # km origin: the frame's west edge, at LAT0
EDGES = ("up", "down", "left", "right")
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def km(lon, lat):
    """Real position in km: x east from LON_W, y south from LAT0 (screen-like)."""
    return ((lon - LON_W) * KX, (LAT0 - lat) * KY)


def lonlat(x, y):
    """Inverse of km()."""
    return (x / KX + LON_W, LAT0 - y / KY)


def load_geo(path=GEO):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_toml(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def anchors_by_name(path=ANCHORS):
    return {a["name"]: a for a in load_toml(path).get("anchor", [])}


def chaikin(pts, rounds=2):
    """Corner-cutting smoothing; keeps both ends."""
    for _ in range(rounds):
        out = [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1),
                    (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        out.append(pts[-1])
        pts = out
    return pts


def seg_dist(px, py, ax, ay, bx, by):
    """Distance from p to segment ab, and the closest point."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), (cx, cy)


class Plan:
    """The corridor plan: projection, maps (rectangles in world tiles) and water."""

    def __init__(self, path=CORRIDOR, geo=None, anchors=None, spec=None):
        """spec: the parsed plan (a dict), instead of reading `path` (tests use it)."""
        spec = spec if spec is not None else load_toml(path)
        self.path = path
        self.anchors = anchors if anchors is not None else anchors_by_name()
        proj = spec["projection"]
        self.kpt = float(proj["km_per_tile"])
        o = self.anchors[proj["origin"]]
        self.origin = proj["origin"]
        self.ox, self.oy = km(o["lon"], o["lat"])
        self.maps = spec.get("map", [])
        self.by_name = {m["name"]: m for m in self.maps}
        geo = geo if geo is not None else load_geo()
        self.water = [self._water(w, geo) for w in spec.get("water", [])]
        self.roads = [self._line(r["name"], r["world"], r["width"]) for r in spec.get("road", [])]

    # --- projection ---
    def world(self, lon, lat):
        """World tile coordinates (float) of a real place."""
        x, y = km(lon, lat)
        return ((x - self.ox) / self.kpt, (y - self.oy) / self.kpt)

    def to_km(self, wx, wy):
        return (self.ox + wx * self.kpt, self.oy + wy * self.kpt)

    def anchor_world(self, name):
        a = self.anchors[name]
        return self.world(a["lon"], a["lat"])

    # --- water ---
    def _water(self, w, geo):
        if "natural_earth" in w:
            runs = [r for r in geo["rivers"] if r["name"] == w["natural_earth"]]
            if not runs:
                raise ValueError(f"water {w['name']!r}: no river {w['natural_earth']!r} in the geo data")
            lines = [chaikin([self.world(*p) for p in ln], w.get("smooth", 2))
                     for r in runs for ln in r["lines"]]
            widths = [(self.anchor_world(n), float(v)) for n, v in w["widths"]]
        else:
            return {**self._line(w["name"], w["world"], w["width"]), "inset": bool(w.get("inset", False))}
        segs = [(a[0], a[1], b[0], b[1]) for ln in lines for a, b in zip(ln, ln[1:])]
        return {"name": w["name"], "segs": segs, "widths": widths, "lines": lines,
                "inset": bool(w.get("inset", False))}

    @staticmethod
    def _line(name, world, width):
        """A hand-drawn polyline in world tiles with one width."""
        ln = [tuple(map(float, p)) for p in world]
        return {"name": name, "segs": [(a[0], a[1], b[0], b[1]) for a, b in zip(ln, ln[1:])],
                "widths": [(ln[0], float(width))], "lines": [ln], "inset": False}

    @staticmethod
    def width_at(water, x, y):
        """Inverse-distance blend of the two nearest width points."""
        ws = sorted(water["widths"], key=lambda p: math.hypot(p[0][0] - x, p[0][1] - y))[:2]
        if len(ws) == 1:
            return ws[0][1]
        (p0, w0), (p1, w1) = ws
        d0, d1 = math.hypot(p0[0] - x, p0[1] - y), math.hypot(p1[0] - x, p1[1] - y)
        if d0 < 1e-9:
            return w0
        a, b = 1 / d0 ** 2, 1 / d1 ** 2
        return (a * w0 + b * w1) / (a + b)

    def water_cells(self, x0, y0, w, h):
        """{(x, y) world tile: water name} for the rectangle; a cell is water when its centre is
        within half the local width of the line."""
        return self._cells(self.water, x0, y0, w, h)

    def road_cells(self, x0, y0, w, h):
        """{(x, y) world tile: road name}, the same way (a 2-wide road covers 2 cells across)."""
        return self._cells(self.roads, x0, y0, w, h)

    def _cells(self, features, x0, y0, w, h):
        out = {}
        for wt in features:
            maxw = max(v for _, v in wt["widths"])
            # only segments that come near the rectangle
            segs = [s for s in wt["segs"]
                    if min(s[0], s[2]) <= x0 + w + maxw and max(s[0], s[2]) >= x0 - maxw
                    and min(s[1], s[3]) <= y0 + h + maxw and max(s[1], s[3]) >= y0 - maxw]
            if not segs:
                continue
            for y in range(y0, y0 + h):
                for x in range(x0, x0 + w):
                    cx, cy = x + 0.5, y + 0.5
                    best, near = None, None
                    for s in segs:
                        d, c = seg_dist(cx, cy, *s)
                        if best is None or d < best:
                            best, near = d, c
                    if best is not None and best <= self.width_at(wt, *near) / 2:
                        out[(x, y)] = wt["name"]
        return out

    # --- maps ---
    @staticmethod
    def rect(m):
        x, y, w, h = m["rect"]
        return x, y, w, h

    def overlaps(self):
        """Pairs of maps whose rectangles overlap."""
        out = []
        for i, a in enumerate(self.maps):
            ax, ay, aw, ah = self.rect(a)
            for b in self.maps[i + 1:]:
                bx, by, bw, bh = self.rect(b)
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    out.append((a["name"], b["name"]))
        return out

    def connections(self, min_shared=1):
        """Edge-to-edge joins: [(a, direction from a, b, offset, shared tiles)], in Emerald's
        terms: b's offset along the edge relative to a (map.json `offset`)."""
        out = []
        for a in self.maps:
            ax, ay, aw, ah = self.rect(a)
            for b in self.maps:
                if a is b:
                    continue
                bx, by, bw, bh = self.rect(b)
                if bx == ax + aw or bx + bw == ax:           # side by side
                    shared = min(ay + ah, by + bh) - max(ay, by)
                    d, off = ("right" if bx == ax + aw else "left"), by - ay
                elif by == ay + ah or by + bh == ay:         # stacked
                    shared = min(ax + aw, bx + bw) - max(ax, bx)
                    d, off = ("down" if by == ay + ah else "up"), bx - ax
                else:
                    continue
                if shared >= min_shared:
                    out.append((a["name"], d, b["name"], off, shared))
        return out

    MARGIN = 8              # cleanup looks this far past a map's edge, so neighbours agree
    CLEAN_ROUNDS = 4        # < MARGIN: a change can't travel from outside the margin to the map

    def clean_water(self, x0, y0, w, h):
        """Water cells of the rectangle, made buildable: a cell one tile wide across (land on both
        sides, left/right or up/down) is widened (toward the right or down, or the other way if
        that's road); a cell with no water neighbour at all goes. Never erode a thin cell with a
        neighbour: on a one-tile river that would eat the river from its end, cell by cell.
        Computed on the rectangle plus MARGIN and cut, so two maps agree along a shared edge."""
        X0, Y0, W, H = x0 - self.MARGIN, y0 - self.MARGIN, w + 2 * self.MARGIN, h + 2 * self.MARGIN
        water = set(self.water_cells(X0, Y0, W, H))
        road = set(self.road_cells(X0, Y0, W, H))
        for _ in range(self.CLEAN_ROUNDS):
            changed = False
            for (x, y) in sorted(water):
                if (x, y) not in water:
                    continue
                for (ax, ay), (bx, by) in (((x - 1, y), (x + 1, y)), ((x, y - 1), (x, y + 1))):
                    if (ax, ay) in water or (bx, by) in water:
                        continue
                    n = sum(c in water for c in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
                    if n == 0:
                        water.discard((x, y))
                    else:
                        water.add((bx, by) if (bx, by) not in road else (ax, ay))
                    changed = True
                    break
            if not changed:
                break
        return {c for c in water if x0 <= c[0] < x0 + w and y0 <= c[1] < y0 + h}

    def underlay(self, name):
        """The map's rows as sketch characters: '~' water, '=' the road, '.' everything else.
        Where the road meets water it stays water (a bridge is the map's design to make)."""
        m = self.by_name[name]
        x0, y0, w, h = self.rect(m)
        water, road = self.clean_water(x0, y0, w, h), self.road_cells(x0, y0, w, h)
        ch = lambda c: "~" if c in water else "=" if c in road else "."
        return ["".join(ch((x0 + x, y0 + y)) for x in range(w)) for y in range(h)]
