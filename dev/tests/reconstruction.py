"""Leave-one-out reconstruction of vanilla maps by the learned auto-tiler.

  python dev/tests/reconstruction.py                  # all vanilla gTileset_General maps
  python dev/tests/reconstruction.py LAYOUT_ROUTE102  # specific layouts
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project
from mapkit.corpus import Corpus
from mapkit.terrain import Vocabulary, reconstruction_test, CLASSES

t0 = time.time()
p = Project(); c = Corpus(p); v = Vocabulary(p, c)
only = set(sys.argv[1:]) or None
per_class, per_map = reconstruction_test(p, c, v, only)
print("per class (exact metatile match on held-out maps):")
for cls in CLASSES:
    h, t = per_class.get(cls, (0, 0))
    if t:
        print(f"  {cls:3} {h / t:6.1%}  ({h}/{t})")
H = sum(h for h, t in per_class.values()); T = sum(t for h, t in per_class.values())
print(f"OVERALL {H / T:.1%} of {T} terrain cells over {len(per_map)} maps ({time.time() - t0:.0f}s)")
worst = sorted(per_map, key=lambda r: r[1] / max(r[2], 1))[:6]
print("lowest maps:", ", ".join(f"{m.replace('LAYOUT_', '')} {h / max(t, 1):.0%}" for m, h, t in worst))
