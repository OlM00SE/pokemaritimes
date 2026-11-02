"""Put an interior behind a door that leads nowhere.

  python dev/add_interior.py Woodstock_2 7,9 Woodstock_House1            # dry run: show the plan
  python dev/add_interior.py Woodstock_2 7,9 Woodstock_House1 --apply
  python dev/add_interior.py HomeTown_0 27,9 HomeTown_House2 --like LittlerootTown_MaysHouse_1F

The building is identified from its facade (mapkit/doors.py), and the interior vanilla puts
behind that facade is cloned: the same layout (no new map.bin), with the warps rewired and
every story event stripped. Multi-floor interiors are cloned whole; floors get the vanilla
floor suffix (e.g. HomeTown_House2_1F, HomeTown_House2_2F). The new maps go in
gMapGroup_IndoorMaritimes, and their scripts are included from data/event_scripts.s.
Edits JSON and script includes only. Run check_maps.py and an in-game test afterwards.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.doors import door_tiles, identify, map_const
from mapkit.mapjson import dump_json, indoor_closure

GROUP = "gMapGroup_IndoorMaritimes"
STRIP_KEYS = ("shared_events_map", "shared_scripts_map")


def load(p, name):
    return json.load(open(p.path("data/maps", name, "map.json"), encoding="utf-8"))


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dump_json(path, obj)


def floors(p, first):
    """`first` plus the vanilla interiors reachable from it without going back outside."""
    return [first] + indoor_closure(p, [first])


def plan(p, outdoor, x, y, base, like=None):
    m = p.load_map(outdoor)
    if (x, y) not in door_tiles(p, m):
        sys.exit(f"({x},{y}) on {outdoor} is not a door tile")
    if any((w["x"], w["y"]) == (x, y) for w in m.events("warp_events")):
        sys.exit(f"the door at ({x},{y}) on {outdoor} already has a warp")
    if like:
        if like not in p.map_names:
            sys.exit(f"--like {like}: no such map")
        vint = like
        outs = [w["dest_map"] for w in load(p, like).get("warp_events") or []
                if p.const_to_map.get(w["dest_map"])
                and load(p, p.const_to_map[w["dest_map"]]).get("map_type") != "MAP_TYPE_INDOOR"]
        if not outs:
            sys.exit(f"--like {like}: none of its warps leads outdoors, so there is no exit to rewire")
        vext = outs[0]
        why = f"--like {like}"
    else:
        hit = identify(p, m, x, y)
        if not hit:
            sys.exit(f"no vanilla building matches the door at ({x},{y}); pass --like <VanillaInterior>")
        score, vmap, vx, vy, dest = hit
        vint, vext = p.const_to_map[dest], load(p, vmap)["id"]
        why = f"facade matches {vmap} ({vx},{vy}) {score}/20"
    fl = floors(p, vint)
    if len(fl) == 1:
        names = {fl[0]: base}
    else:
        names = {v: f"{base}_{v.rsplit('_', 1)[-1]}" for v in fl}
        if len(set(names.values())) != len(fl):
            names = {v: f"{base}_{i + 1}" for i, v in enumerate(fl)}
    for n in names.values():
        if n in p.map_names:
            sys.exit(f"map {n} already exists")
        if map_const(n) in p.const_to_map:
            sys.exit(f"{n} would get id {map_const(n)}, which {p.const_to_map[map_const(n)]} already uses")
    # Every warp on a cloned floor must lead outside (rewired to this door) or to another
    # cloned floor; anything else (a second exit, MAP_DYNAMIC) would still point into Hoenn.
    vconsts = {load(p, v)["id"] for v in fl}
    for v in fl:
        for w in load(p, v).get("warp_events") or []:
            if w["dest_map"] != vext and w["dest_map"] not in vconsts:
                sys.exit(f"{v} has a warp at ({w['x']},{w['y']}) to {w['dest_map']}, which this tool "
                         "cannot rewire (a second exit?); clone this building by hand in Porymap")
    return m, vint, vext, names, why


def apply(p, m, x, y, vint, vext, names):
    ext = load(p, m.name)
    vconst = {load(p, v)["id"]: n for v, n in names.items()}
    ext_warps = ext.setdefault("warp_events", []) or []
    new_ext_id = len(ext_warps)
    # Which warp of the first floor leads outside: the exterior warp points at it.
    first = load(p, vint)
    exit_id = next(i for i, w in enumerate(first["warp_events"]) if w["dest_map"] == vext)
    for v, n in names.items():
        j = load(p, v)
        j["id"], j["name"] = map_const(n), n
        j["music"] = ext.get("music", j["music"])
        j["region_map_section"] = ext.get("region_map_section", j["region_map_section"])
        if "region" in j and "region" not in ext:
            del j["region"]
        for k in STRIP_KEYS:
            j.pop(k, None)
        j["object_events"], j["coord_events"], j["bg_events"] = [], [], []
        for w in j.get("warp_events") or []:
            if w["dest_map"] == vext:
                w["dest_map"], w["dest_warp_id"] = ext["id"], str(new_ext_id)
            elif w["dest_map"] in vconst:
                w["dest_map"] = map_const(vconst[w["dest_map"]])
        dump(p.path("data/maps", n, "map.json"), j)
        with open(p.path("data/maps", n, "scripts.inc"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{n}_MapScripts::\n\t.byte 0\n")
    ext_warps.append({"x": x, "y": y, "elevation": 0,
                      "dest_map": map_const(names[vint]), "dest_warp_id": str(exit_id)})
    ext["warp_events"] = ext_warps
    dump(p.path("data/maps", m.name, "map.json"), ext)

    gpath = p.path("data/maps/map_groups.json")
    groups = json.load(open(gpath, encoding="utf-8"))
    if GROUP not in groups:
        groups["group_order"].append(GROUP)
        groups[GROUP] = []
    groups[GROUP].extend(names.values())
    dump(gpath, groups)

    spath = p.path("data/event_scripts.s")
    src = open(spath, encoding="utf-8").read()
    lines = src.split("\n")
    marker = next(i for i, l in enumerate(lines) if l.startswith("@ ---- Pok") and "Maritimes" in l)
    end = marker + 1
    while end < len(lines) and lines[end].strip().startswith(".include"):
        end += 1
    lines[end:end] = [f'\t.include "data/maps/{n}/scripts.inc"' for n in names.values()]
    with open(spath, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    like = None
    if "--like" in argv:
        like = argv[argv.index("--like") + 1]
        args.remove(like)
    if len(args) != 3:
        print(__doc__); return 2
    outdoor, xy, base = args
    x, y = (int(v) for v in xy.split(","))
    p = Project()
    m, vint, vext, names, why = plan(p, outdoor, x, y, base, like)
    print(f"{outdoor} door ({x},{y}): {why}")
    for v, n in names.items():
        print(f"  {v}  ->  {n}  ({map_const(n)}, layout {load(p, v)['layout']})")
    if "--apply" not in flags:
        print("dry run; pass --apply to write"); return 0
    apply(p, m, x, y, vint, vext, names)
    print("written. Next: dev/check_maps.py, dev/fastbuild.py, then an in-game check (dev/shoot.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
