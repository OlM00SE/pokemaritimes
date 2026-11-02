"""Section completeness report: what a playable slice still needs, map by map.

  python dev/section_status.py                  # everything reachable from HomeTown_0
  python dev/section_status.py Woodstock_2 ...  # just these maps
  python dev/section_status.py --from Fredericton_0

Reachability follows connections and warps. For each map it reports doors that lead
nowhere, missing wild encounters, people and signs, and metadata still borrowed from
Hoenn (placeholder map section, silent music). It complements check_maps.py: the
checker asks "is anything broken?", this asks "is anything missing?".
It only reports; it changes nothing. Exit code is always 0.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, TILE_FLAG_HAS_ENCOUNTERS, TILE_FLAG_SURFABLE
from mapkit.checks import wild_encounter_maps

UPSTREAM = "expansion/1.17.2"
OUTDOOR = ("MAP_TYPE_TOWN", "MAP_TYPE_CITY", "MAP_TYPE_ROUTE", "MAP_TYPE_OCEAN_ROUTE")


def upstream_mapsecs(p):
    r = subprocess.run(["git", "-C", p.root, "show", f"{UPSTREAM}:src/data/region_map/region_map_sections.json"],
                       capture_output=True, text=True, encoding="utf-8")
    try:
        return {s["id"] for s in json.loads(r.stdout)["map_sections"]}
    except Exception:
        return set()


def reachable(p, start):
    seen, queue = [start], [start]
    while queue:
        m = p.load_map(queue.pop(0))
        targets = [c["map"] for c in m.connections] + [w["dest_map"] for w in m.events("warp_events")]
        for t in targets:
            n = p.const_to_map.get(t)
            if n and n not in seen:
                seen.append(n); queue.append(n)
    return seen


def wild_kinds(p):
    """map const -> set of encounter kinds present (land_mons, water_mons, fishing_mons...)."""
    data = json.load(open(p.path("src/data/wild_encounters.json"), encoding="utf-8"))
    out = {}
    for g in data.get("wild_encounter_groups", []):
        for e in g.get("encounters", []):
            out.setdefault(e.get("map"), set()).update(k for k in e if k.endswith("_mons"))
    return out


def status(p, name, mapsecs, wild):
    m = p.load_map(name)
    L, tp = m.layout, m.layout.tiles
    door = p.behavior_set("WarpDoor")
    warp_xy = {(w["x"], w["y"]) for w in m.events("warp_events")}
    doors = [(x, y) for y in range(L.height) for x in range(L.width) if tp.behavior(L.mid(x, y)) in door]
    flags = [p.tile_flags.get(tp.behavior(L.mid(x, y)), 0) for y in range(L.height) for x in range(L.width)]
    grass = sum(1 for f in flags if f & TILE_FLAG_HAS_ENCOUNTERS and not f & TILE_FLAG_SURFABLE)
    water = sum(1 for f in flags if f & TILE_FLAG_SURFABLE)
    objs = m.events("object_events")
    trainers = sum(1 for o in objs if o.get("trainer_type", "TRAINER_TYPE_NONE") != "TRAINER_TYPE_NONE")
    signs = sum(1 for b in m.events("bg_events") if b.get("type") == "sign")
    kinds = wild.get(m.id, set())

    todo = []
    dead = [d for d in doors if d not in warp_xy]
    if dead:
        todo.append(f"{len(dead)} of {len(doors)} doors lead nowhere {dead[:4]}")
    # towns use tall grass as decoration (vanilla towns have no encounter tables)
    if grass and "land_mons" not in kinds and m.j.get("map_type") not in ("MAP_TYPE_TOWN", "MAP_TYPE_CITY"):
        todo.append(f"{grass} grass tiles, no land encounters")
    if water and "water_mons" not in kinds and m.j.get("map_type") in OUTDOOR:
        todo.append(f"{water} water tiles, no surf encounters (fine until Surf)")
    if m.j.get("map_type") in OUTDOOR and not objs:
        todo.append("no people or objects")
    if m.j.get("map_type") in ("MAP_TYPE_TOWN", "MAP_TYPE_CITY") and not signs:
        todo.append("no town sign")
    sec = m.j.get("region_map_section", "")
    if sec in mapsecs:
        todo.append(f"map section {sec} is borrowed from Hoenn")
    if m.j.get("music") in ("MUS_DUMMY", "MUS_NONE"):
        todo.append("silent (music MUS_DUMMY)")
    row = dict(map=name, type=m.j.get("map_type", "").replace("MAP_TYPE_", "").lower(),
               size=f"{L.width}x{L.height}", doors=f"{len(doors) - len(dead)}/{len(doors)}",
               wild=",".join(sorted(k.replace("_mons", "") for k in kinds)) or "-",
               people=f"{len(objs)} ({trainers} trainers)", signs=signs)
    return row, todo


def main(argv):
    p = Project()
    args = [a for a in argv if not a.startswith("--")]
    if "--from" in argv:
        names = reachable(p, args[0])
    else:
        names = args or reachable(p, "HomeTown_0")
    mapsecs, wild = upstream_mapsecs(p), wild_kinds(p)
    rows = [status(p, n, mapsecs, wild) for n in names]
    cols = ["map", "type", "size", "doors", "wild", "people", "signs"]
    width = {c: max(len(c), *(len(str(r[c])) for r, _ in rows)) for c in cols}
    print("  ".join(c.ljust(width[c]) for c in cols))
    print("  ".join("-" * width[c] for c in cols))
    for r, _ in rows:
        print("  ".join(str(r[c]).ljust(width[c]) for c in cols))
    print()
    open_items = 0
    for r, todo in rows:
        if todo:
            print(f"{r['map']}:")
            for t in todo:
                print(f"  - {t}")
            open_items += len(todo)
    print(f"\n{len(rows)} maps, {open_items} open items")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
