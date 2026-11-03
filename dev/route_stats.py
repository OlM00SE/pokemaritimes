"""Gameplay numbers for maps' crossings (mapkit/routes.py): for each pair of edge connections,
the fewest steps across, the fewest tall-grass tiles that can't be avoided, and the reachable
encounter ground. `mapgen build` prints the same numbers before and after a change.

  python dev/route_stats.py Route201_1 [Route203_1 ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit import routes

p = Project()
for name in sys.argv[1:] or ["Route201_1"]:
    print(f"{name}:")
    for line in routes.describe(None, routes.route_stats(p, p.load_map(name))):
        print(line)
