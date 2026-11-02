"""Create a new, blank outdoor map: the starting point for a sketch (dev/mapgen.py build --fresh).

  python dev/new_map.py <Name> <W>x<H> [--like Route203_1] [--group G] [--spawn x,y]   # dry run
  python dev/new_map.py LedgeLab 32x28 --apply

The map is all plain grass. It takes the --like map's tilesets, border, and header (music,
weather, map type, map section, flags) but no connections and no events except a spawn point:
an arrival-only warp to MAP_DYNAMIC at --spawn (default: the centre). While it is the map's
only warp and the map has no connections, the checker treats it as the entrance and as a way
out (checks.spawn_point), so reachability and trap checks work before the map is linked to
anything. Delete the spawn warp once the map has real connections or doors.

The map is appended to --group (default gMapGroup_DevMaritimes, a group for test maps that
the world never links to), so no existing map id moves. Edits JSON, writes map.bin/border.bin,
and includes scripts.inc from data/event_scripts.s. Never overwrites an existing map.
"""
import argparse, json, os, re, shutil, struct, sys
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
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        sys.exit(f"{name}: use ASCII letters, digits and '_', starting with a letter "
                 "(it becomes a folder and a C constant)")
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


SHARED = ("data/layouts/layouts.json", "data/maps/map_groups.json", "data/event_scripts.s")


def apply(p, name, w, h, const, layout_id, src, spawn, group):
    """All or nothing: if any step fails, the shared files are restored and the new folders
    removed, so a retry starts clean."""
    saved = {f: open(p.path(f), "rb").read() for f in SHARED}
    try:
        _write(p, name, w, h, const, layout_id, src, spawn, group)
    except BaseException:
        for f, data in saved.items():
            with open(p.path(f), "wb") as out:
                out.write(data)
        for d in (p.path("data/layouts", name), p.path("data/maps", name)):
            shutil.rmtree(d, ignore_errors=True)
        print("failed; every change was rolled back")
        raise


def _write(p, name, w, h, const, layout_id, src, spawn, group):
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("size", help="WxH, e.g. 32x28")
    ap.add_argument("--like", default="Route203_1")
    ap.add_argument("--group", default=DEV_GROUP)
    ap.add_argument("--spawn", help="x,y (default: the centre)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    try:
        w, h = (int(v) for v in a.size.lower().split("x"))
        spawn = tuple(int(v) for v in a.spawn.split(",")) if a.spawn else None
        if spawn is not None and len(spawn) != 2:
            raise ValueError
    except ValueError:
        ap.error("size must be WxH and --spawn x,y")
    name, like, group = a.name, a.like, a.group
    p = Project()
    const, layout_id, src, spawn = plan(p, name, w, h, like, spawn)
    print(f"{name}: {w}x{h} grass, {const} / {layout_id}, tilesets {src.layout.primary} + "
          f"{src.layout.secondary}, header from {like}, group {group}, spawn at {spawn}")
    if not a.apply:
        print("dry run; pass --apply to write"); return 0
    apply(p, name, w, h, const, layout_id, src, spawn, group)
    print("written. Next: write a sketch (// map: " + name + "), dev/mapgen.py build <sketch> --fresh, "
          "then dev/fastbuild.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
