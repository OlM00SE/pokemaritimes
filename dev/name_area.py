"""Give an area its own region-map section (the name in the map popup), instead of a borrowed
Hoenn one.

  python dev/name_area.py MAPSEC_WOODSTOCK "WOODSTOCK" Woodstock_2 --interiors        # dry run
  python dev/name_area.py MAPSEC_WOODSTOCK "WOODSTOCK" Woodstock_2 --interiors --apply

Creates the section in src/data/region_map/region_map_sections.json if it is missing
(appended, so no existing MAPSEC id moves), or renames it if the name differs. Then sets
region_map_section on the listed maps; --interiors also covers every indoor map reachable
from them through warps (houses, upper floors).
New sections have no region-map square yet (no x/y): they show in popups, not on the Town Map.
Names are uppercase, at most 16 characters (popup width).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.mapjson import dump_json, indoor_closure

SECTIONS = "src/data/region_map/region_map_sections.json"
MAX_NAME = 16


dump = dump_json


def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__); return 2
    sec, name, maps = args[0], args[1], args[2:]
    if not sec.startswith("MAPSEC_") or not sec.replace("_", "").isalnum() or not sec.isupper():
        sys.exit(f"bad section id {sec!r} (want MAPSEC_UPPER_CASE)")
    if len(name) > MAX_NAME or name != name.upper():
        sys.exit(f"name {name!r} must be uppercase and at most {MAX_NAME} characters")
    p = Project()
    for m in maps:
        if m not in p.map_names:
            sys.exit(f"unknown map {m}")
    targets = maps + (indoor_closure(p, maps) if "--interiors" in flags else [])

    spath = p.path(SECTIONS)
    data = json.load(open(spath, encoding="utf-8"))
    entry = next((s for s in data["map_sections"] if s["id"] == sec), None)
    if entry is None:
        action = f"create {sec} = {name!r} (id {len(data['map_sections'])}, appended)"
    elif entry["name"] != name:
        action = f"rename {sec}: {entry['name']!r} -> {name!r}"
    else:
        action = f"{sec} = {name!r} already exists"
    print(action)
    changes = []
    for m in targets:
        old = p.load_map(m).j.get("region_map_section")
        if old != sec:
            changes.append((m, old))
            print(f"  {m}: {old} -> {sec}")
    if not changes and entry is not None and entry["name"] == name:
        print("nothing to do"); return 0
    if "--apply" not in flags:
        print("dry run; pass --apply to write"); return 0
    if entry is None:
        data["map_sections"].append({"id": sec, "name": name})
    else:
        entry["name"] = name
    dump(spath, data)
    for m, _ in changes:
        mp = p.path("data/maps", m, "map.json")
        j = json.load(open(mp, encoding="utf-8"))
        j["region_map_section"] = sec
        dump(mp, j)
    print(f"written: {len(changes)} maps. Next: dev/fastbuild.py, then check the popup in-game.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
