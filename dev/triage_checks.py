"""Group check_map ERRORs across all maps by pattern, with example maps. For checker development."""
import os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.checks import check_map

p = Project()
sev_filter = sys.argv[1] if len(sys.argv) > 1 else "ERROR"
groups = defaultdict(list)
for n in p.map_names:
    if n.endswith("_Frlg"):
        continue
    try:
        issues = check_map(p, n)
    except Exception as ex:
        issues = [("ERROR", "crash", f"{type(ex).__name__}: {ex}")]
    for s, c, msg in issues:
        if s == sev_filter:
            key = c + ": " + re.sub(r"\d+", "#", re.sub(r"\(.*?\)|\[.*?\]|'.*?'", "", msg))[:110]
            groups[key].append((n, msg))
for key, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"{len(items):4}  {key}")
    for n, msg in items[:2]:
        print(f"        e.g. {n}: {msg[:150]}")
