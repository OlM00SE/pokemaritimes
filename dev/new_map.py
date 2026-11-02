"""Create a new, blank outdoor map: the starting point for a sketch (dev/mapgen.py build --fresh).

  python dev/new_map.py <Name> <W>x<H> [--like Route203_1] [--group G] [--spawn x,y]   # dry run
  python dev/new_map.py LedgeLab 32x28 --apply

The map is all plain grass. It takes the --like map's tilesets, border, and header (music,
weather, map type, map section, flags) but no connections and no events except a spawn point:
an arrival-only warp to MAP_DYNAMIC at --spawn (default: the centre). The checker treats that
tile as the map's entrance, so reachability and trap checks work before the map is connected to
anything. Delete the spawn warp once the map has real connections or doors.

The map is appended to --group (default gMapGroup_DevMaritimes, a group for test maps that
the world never links to), so no existing map id moves. Edits JSON, writes map.bin/border.bin,
and includes scripts.inc from data/event_scripts.s. Never overwrites an existing map.
"""
import json, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, max_map_area_ok
from mapkit.layout import pack
from mapkit.doors import map_const
from mapkit.mapjson import dump_json, add_to_group, add_script_includes

DEV_GROUP = "gMapGroup_DevMaritimes"
GRASS = 0x001
HEADER_KEYS = ("music", "region_map_section", "requires_flash", "weather", "map_type", "allow_cycling",
               "allow_escaping", "allow_running", "show_map_name", "battle_scene")


def plan(p, name, w, h, like, spawn):
    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        sys.exit(f"{name}: use letters, digits and '_' (it becomes a folder and a constant)")
    if name in p.map_names or os.path.exists(p.path("data/maps", name)):
        sys.exit(f"map {name} already exists")
    const = map_const(name)
    layout_id = "LAYOUT_" + const[4:]
    if const in p.const_to_map:
        sys.exit(f"{name} would get id {const}, which {p.const_to_map[const]} already uses")
    if layout_id in p.layouts or os.path.exists(p.path("data/layouts", name)):
        sys.exit(f"layout {layout_id} (or data/layouts/{name}) already exists")
    if not max_map_area_ok(w, h):
        sys.exit(f"{w}x{h} is too big: (w+15)*(h+14) must be <= 10240")
    if like not in p.map_names:
        sys.exit(f"--like {like}: no such map")
    src = p.load_map(like)
    sx, sy = spawn if spawn else (w // 2, h // 2)
    if not (0 <= sx < w and 0 <= sy < h):
        sys.exit(f"--spawn {sx},{sy} is outside a {w}x{h} map")
    return const, layout_id, src, (sx, sy)


def apply(p, name, w, h, const, layout_id, src, spawn, group):
    ldir = p.path("data/layouts", name)
    os.makedirs(ldir)
    with open(os.path.join(ldir, "map.bin"), "wb") as f:
        f.write(struct.pack(f"<{w * h}H", *([pack(GRASS, 0, 3)] * (w * h))))
    shutil.copyfile(p.path(src.layout.entry["border_filepath"]), os.path.join(ldir, "border.bin"))
    lpath = p.path("data/layouts/layouts.json")
    layouts = json.load(open(lpath, encoding="utf-8"))
    layouts["layouts"].append({
        "id": layout_id, "name": f"{name}_Layout", "width": w, "height": h,
        "primary_tileset": src.layout.primary, "secondary_tileset": src.layout.secondary,
        "border_filepath": f"data/layouts/{name}/border.bin",
        "blockdata_filepath": f"data/layouts/{name}/map.bin"})
    dump_json(lpath, layouts)

    j = {"id": const, "name": name, "layout": layout_id}
    j.update({k: src.j[k] for k in HEADER_KEYS if k in src.j})
    j.update({"connections": None, "object_events": [],
              "warp_events": [{"x": spawn[0], "y": spawn[1], "elevation": 0,
                               "dest_map": "MAP_DYNAMIC", "dest_warp_id": "WARP_ID_DYNAMIC"}],
              "coord_events": [], "bg_events": []})
    mdir = p.path("data/maps", name)
    os.makedirs(mdir)
    dump_json(os.path.join(mdir, "map.json"), j)
    with open(os.path.join(mdir, "scripts.inc"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{name}_MapScripts::\n\t.byte 0\n")
    add_to_group(p, group, [name])
    add_script_includes(p, [name])


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    opts = {}
    for k in ("--like", "--group", "--spawn"):
        if k in argv:
            opts[k] = argv[argv.index(k) + 1]
    args = [a for a in argv if not a.startswith("--") and a not in opts.values()]
    if len(args) != 2 or "x" not in args[1]:
        print(__doc__); return 2
    name, size = args
    w, h = (int(v) for v in size.lower().split("x"))
    spawn = tuple(int(v) for v in opts["--spawn"].split(",")) if "--spawn" in opts else None
    like, group = opts.get("--like", "Route203_1"), opts.get("--group", DEV_GROUP)
    p = Project()
    const, layout_id, src, spawn = plan(p, name, w, h, like, spawn)
    print(f"{name}: {w}x{h} grass, {const} / {layout_id}, tilesets {src.layout.primary} + "
          f"{src.layout.secondary}, header from {like}, group {group}, spawn at {spawn}")
    if "--apply" not in flags:
        print("dry run; pass --apply to write"); return 0
    apply(p, name, w, h, const, layout_id, src, spawn, group)
    print("written. Next: write a sketch (// map: " + name + "), dev/mapgen.py build <sketch> --fresh, "
          "then dev/fastbuild.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
