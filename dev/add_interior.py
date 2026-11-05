"""Put an interior behind a door that leads nowhere.

  python dev/add_interior.py Woodstock_2 7,9 Woodstock_House1            # dry run: show the plan
  python dev/add_interior.py Woodstock_2 7,9 Woodstock_House1 --apply
  python dev/add_interior.py HomeTown_0 27,9 HomeTown_House2 --like LittlerootTown_MaysHouse_1F
  python dev/add_interior.py Town_0 6,16 Town_PokemonCenter --like OldaleTown_PokemonCenter_1F --kind pokemon_center

The building is identified from its facade (mapkit/doors.py), and the interior vanilla puts
behind that facade is cloned: the same layout (no new map.bin), with the warps rewired and
every story event stripped. Multi-floor interiors are cloned whole; floors get the vanilla
floor suffix (e.g. HomeTown_House2_1F, HomeTown_House2_2F). The new maps go in
gMapGroup_IndoorMaritimes, and their scripts are included from data/event_scripts.s.
--kind pokemon_center / mart makes the copy work (a nurse and the respawn point, a clerk with a
stock list; mapkit/interiors.py). On maps built from a sketch, building stamps do all of this
from `mapgen --apply` (mapkit/buildings.py); this tool is for hand-painted maps.
Edits JSON and script includes only. Run check_maps.py and an in-game test afterwards.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.doors import door_tiles, identify
from mapkit.mapjson import dump_json
from mapkit import interiors


def plan(p, outdoor, x, y, base, like=None, kind="plain"):
    m = p.load_map(outdoor)
    if (x, y) not in door_tiles(p, m):
        sys.exit(f"({x},{y}) on {outdoor} is not a door tile")
    if any((w["x"], w["y"]) == (x, y) for w in m.events("warp_events")):
        sys.exit(f"the door at ({x},{y}) on {outdoor} already has a warp")
    if like:
        if like not in p.map_names:
            sys.exit(f"--like {like}: no such map")
        template, why = like, f"--like {like}"
    else:
        hit = identify(p, m, x, y)
        if not hit:
            sys.exit(f"no vanilla building matches the door at ({x},{y}); pass --like <VanillaInterior>")
        score, vmap, vx, vy, dest = hit
        template, why = p.const_to_map[dest], f"facade matches {vmap} ({vx},{vy}) {score}/20"
    try:
        return m, interiors.Plan(p, template, base, kind), why
    except interiors.InteriorError as ex:
        sys.exit(str(ex))


def apply(p, m, x, y, pl):
    ext = interiors.load(p, m.name)
    ext_warps = ext.get("warp_events") or []
    new_id = len(ext_warps)
    ext_warps.append({"x": x, "y": y, "elevation": 0,
                      "dest_map": interiors.map_const(pl.first), "dest_warp_id": str(pl.exit_warp_id(p))})
    ext["warp_events"] = ext_warps
    dump_json(p.path("data/maps", m.name, "map.json"), ext)
    interiors.write(p, pl, m.name, ext["id"], new_id)
    if pl.kind == "pokemon_center":
        print("  heal location", interiors.heal_location_id(m.name),
              interiors.set_heal_location(p, interiors.heal_location_id(m.name), ext["id"], x, y + 1,
                                          interiors.map_const(pl.first), interiors.nurse_local_id(pl.first)))


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    opts = {}
    for k in ("--like", "--kind"):
        if k in argv:
            opts[k] = argv[argv.index(k) + 1]
            args.remove(opts[k])
    if len(args) != 3:
        print(__doc__); return 2
    outdoor, xy, base = args
    x, y = (int(v) for v in xy.split(","))
    p = Project()
    m, pl, why = plan(p, outdoor, x, y, base, opts.get("--like"), opts.get("--kind", "plain"))
    print(f"{outdoor} door ({x},{y}): {why}")
    for line in pl.describe(p):
        print("  " + line)
    if "--apply" not in flags:
        print("dry run; pass --apply to write"); return 0
    apply(p, m, x, y, pl)
    print("written. Next: dev/check_maps.py, dev/fastbuild.py, then an in-game check (dev/shoot.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
