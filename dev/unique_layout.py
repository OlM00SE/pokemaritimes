"""Give one map its own editable terrain, preserving geometry, events and saved map IDs.

  python dev/unique_layout.py TownLab_SmallHouse          # preview
  python dev/unique_layout.py TownLab_SmallHouse --apply  # copy blocks and border; append layout

Copied standard interiors may keep sharing geometry until they need customization.
Layout.save refuses changes to shared terrain; this is the explicit opt-out.
"""
import argparse
import copy
import json
import os
from mapkit.project import Project
from mapkit.doors import map_const
from mapkit.layout import layout_users
from mapkit.mapjson import dump_json
from mapkit.transaction import atomic_write, edit


def plan(p, name):
    if name not in p.map_names:
        raise ValueError(f"unknown map {name}")
    m = p.load_map(name)
    entry = copy.deepcopy(m.layout.entry)
    lid = "LAYOUT_" + map_const(name)[4:]
    folder = f"data/layouts/{name}"
    if len(layout_users(p, entry)) <= 1:
        return m, None
    if entry["id"] == lid:                # the original layout's namesake is itself shared
        lid += "_UNIQUE"
        folder += "_Unique"
    if lid in p.layouts or os.path.exists(p.path(folder)):
        raise ValueError(f"{lid} or {folder} already exists; refusing to overwrite it")
    entry.update(id=lid, name=f"{name}_Layout", blockdata_filepath=f"{folder}/map.bin",
                 border_filepath=f"{folder}/border.bin")
    return m, entry


def apply(p, m, entry):
    # Re-plan at the write boundary, so an old preview cannot overwrite a new layout.
    m, expected = plan(p, m.name)
    if entry != expected or entry is None:
        raise ValueError("layout plan changed; preview the operation again")
    folder = os.path.dirname(entry["blockdata_filepath"])
    with edit(p, ["data/layouts/layouts.json", f"data/maps/{m.name}/map.json"], [folder]):
        os.makedirs(p.path(folder))
        for key in ("blockdata_filepath", "border_filepath"):
            atomic_write(p.path(entry[key]), open(p.path(m.layout.entry[key]), "rb").read())
        data = json.load(open(p.path("data/layouts/layouts.json"), encoding="utf-8"))
        data["layouts"].append(entry)      # no existing layout/map ID moves
        dump_json(p.path("data/layouts/layouts.json"), data)
        m.j["layout"] = entry["id"]
        m.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    p = Project()
    try:
        m, entry = plan(p, a.map)
        if entry is None:
            print(f"{a.map} already has its own layout; nothing to do")
            return 0
        print(f"{a.map}: {m.layout.id} -> {entry['id']} (identical blocks and border)")
        print("current users: " + ", ".join(layout_users(p, m.layout.entry)))
        if a.apply:
            apply(p, m, entry)
            print("applied; map IDs, warps, events and source geometry unchanged")
        else:
            print("dry run; pass --apply to write")
        return 0
    except ValueError as ex:
        print(f"NOT APPLIED: {ex}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
