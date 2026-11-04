"""Clip Natural Earth 1:10m data to the PokéMaritimes frame (one-time; the result is committed).

  python dev/geo_extract.py <dir with the Natural Earth geojson files> [--apply]

Reads, from https://github.com/nvkelso/natural-earth-vector/tree/master/geojson:
  ne_10m_land.geojson, ne_10m_lakes.geojson, ne_10m_rivers_lake_centerlines.geojson,
  ne_10m_admin_0_boundary_lines_land.geojson, ne_10m_admin_1_states_provinces_lines.geojson
and writes design/region/geo/maritimes_ne10m.json: land and lake polygons clipped to the frame
(Sutherland-Hodgman, so they still fill), rivers and borders as polylines, coordinates rounded to
0.001 degrees (about 100 m). Natural Earth is public domain. The default is a dry run.
"""
import argparse, json, os, sys

FRAME = (-69.4, 43.1, -59.2, 50.4)          # lon0, lat0, lon1, lat1: NB, NS, PEI, Gaspé, Anticosti
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "design", "region", "geo",
                   "maritimes_ne10m.json")
FILES = {"land": "ne_10m_land.geojson", "lakes": "ne_10m_lakes.geojson",
         "rivers": "ne_10m_rivers_lake_centerlines.geojson",
         "border": "ne_10m_admin_0_boundary_lines_land.geojson",
         "provinces": "ne_10m_admin_1_states_provinces_lines.geojson"}


def clip_ring(ring, frame=FRAME):
    """Sutherland-Hodgman against the frame rectangle; returns the clipped ring (may be empty)."""
    x0, y0, x1, y1 = frame
    edges = [(lambda p: p[0] >= x0, lambda a, b: _cut_x(a, b, x0)),
             (lambda p: p[0] <= x1, lambda a, b: _cut_x(a, b, x1)),
             (lambda p: p[1] >= y0, lambda a, b: _cut_y(a, b, y0)),
             (lambda p: p[1] <= y1, lambda a, b: _cut_y(a, b, y1))]
    pts = list(ring)
    for inside, cut in edges:
        if not pts:
            break
        out, prev = [], pts[-1]
        for cur in pts:
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
            prev = cur
        pts = out
    return pts


def _cut_x(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _cut_y(a, b, y):
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def clip_line(line, frame=FRAME):
    """Runs of a polyline that touch the frame; a segment is kept if either end is inside."""
    x0, y0, x1, y1 = frame
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    runs, run = [], []
    for a, b in zip(line, line[1:]):
        if inside(a) or inside(b):
            if not run:
                run = [a]
            run.append(b)
        elif run:
            runs.append(run); run = []
    if run:
        runs.append(run)
    return runs


def rnd(pts):
    out = []
    for x, y in pts:
        p = [round(x, 3), round(y, 3)]
        if not out or out[-1] != p:
            out.append(p)
    return out


def polygons(geom):
    if not geom:
        return []
    t, c = geom["type"], geom["coordinates"]
    return [c] if t == "Polygon" else c if t == "MultiPolygon" else []


def lines(geom):
    if not geom:
        return []
    t, c = geom["type"], geom["coordinates"]
    return [c] if t == "LineString" else c if t == "MultiLineString" else []


def name_of(props):
    for k in ("name_en", "name", "NAME", "adm0_name"):
        if props.get(k):
            return props[k]
    if props.get("name_l") or props.get("name_r"):
        return f"{props.get('name_l')} / {props.get('name_r')}"
    return None


def extract(src):
    out = {"source": "Natural Earth 1:10m (public domain), naturalearthdata.com, clipped by "
                     "dev/geo_extract.py", "frame": FRAME,
           "land": [], "land_holes": [], "lakes": [], "rivers": [], "borders": []}
    load = lambda k: json.load(open(os.path.join(src, FILES[k]), encoding="utf-8"))["features"]
    for f in load("land"):
        for poly in polygons(f["geometry"]):
            for i, ring in enumerate(poly):
                r = rnd(clip_ring(ring))
                if len(r) >= 3:
                    (out["land"] if i == 0 else out["land_holes"]).append(r)
    for f in load("lakes"):
        for poly in polygons(f["geometry"]):
            r = rnd(clip_ring(poly[0]))
            if len(r) >= 3:
                out["lakes"].append({"name": name_of(f["properties"]), "ring": r})
    for key, dest in (("rivers", "rivers"), ("border", "borders"), ("provinces", "borders")):
        for f in load(key):
            runs = [rnd(r) for ln in lines(f["geometry"]) for r in clip_line(ln)]
            runs = [r for r in runs if len(r) >= 2]
            if runs:
                out[dest].append({"name": name_of(f["properties"]), "kind": key, "lines": runs})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    data = extract(a.src)
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    pts = sum(len(r) for r in data["land"])
    print(f"land rings {len(data['land'])} ({pts} points), holes {len(data['land_holes'])}, "
          f"lakes {len(data['lakes'])}, rivers {[r['name'] for r in data['rivers']]}, "
          f"borders {[b['name'] for b in data['borders']]}; {len(text) / 1024:.0f} KB")
    if a.apply:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote", os.path.normpath(OUT))
    else:
        print("dry run; --apply writes", os.path.normpath(OUT))


if __name__ == "__main__":
    sys.exit(main())
