"""Render maps, tileset sheets, or the connected region (thin CLI over dev/mapkit/render.py).

  python dev/render_map.py <Map> [-o out.png] [--scale N] [--overlay grid,collision,elevation,behavior,events]
  python dev/render_map.py <Map> --events --grid          # legacy flags still work
  python dev/render_map.py <Map> --world [--shrink 2]     # stitch everything connected to <Map>
  python dev/render_map.py --sheet gTileset_General gTileset_Petalburg [--start 1C0 --count 64]
A leading project-dir argument ('.') is accepted for backwards compatibility.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit import render

ap = argparse.ArgumentParser()
ap.add_argument("args", nargs="*")
ap.add_argument("-o", "--out")
ap.add_argument("--scale", type=int, default=1)
ap.add_argument("--overlay", default="")
ap.add_argument("--grid", action="store_true")
ap.add_argument("--events", action="store_true")
ap.add_argument("--world", action="store_true")
ap.add_argument("--shrink", type=int, default=2)
ap.add_argument("--sheet", nargs=2, metavar=("PRIMARY", "SECONDARY"))
ap.add_argument("--start", default="0")
ap.add_argument("--count", type=int)
a = ap.parse_args()
args = [x for x in a.args if not (os.path.isdir(x) and os.path.exists(os.path.join(x, "Makefile")))]
p = Project()
overlays = set(filter(None, a.overlay.split(","))) | ({"grid"} if a.grid else set()) | ({"events"} if a.events else set())
if a.sheet:
    img = render.render_sheet(p, *a.sheet, start=int(a.start, 16), count=a.count)
    out = a.out or f"sheet_{a.sheet[1]}.png"
elif a.world:
    img, pos = render.render_world(p, args[0], a.shrink)
    out = a.out or f"world_{args[0]}.png"
    print(f"{len(pos)} maps:", ", ".join(pos))
else:
    img = render.render_map(p, args[0], a.scale, overlays)
    out = a.out or f"{args[0]}.png"
img.save(out)
print(out, img.size)
