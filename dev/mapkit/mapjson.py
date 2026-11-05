"""Shared helpers for tools that edit map JSON (add_interior, name_area, ...)."""
import json


def dump_json(path, obj):
    """Write JSON exactly as Porymap does (2-space indent, UTF-8, trailing newline), so an
    unchanged load+dump round-trips byte-for-byte."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def add_to_group(p, group, names):
    """Append maps to a map group (created at the end of group_order if new), so no existing
    map's group/number id moves."""
    gpath = p.path("data/maps/map_groups.json")
    groups = json.load(open(gpath, encoding="utf-8"))
    if group not in groups:
        groups["group_order"].append(group)
        groups[group] = []
    groups[group].extend(names)
    dump_json(gpath, groups)


def add_script_includes(p, names):
    """Include each map's scripts.inc from data/event_scripts.s, at the end of the
    PokéMaritimes block."""
    spath = p.path("data/event_scripts.s")
    lines = open(spath, encoding="utf-8").read().split("\n")
    marker = next(i for i, l in enumerate(lines) if l.startswith("@ ---- Pok") and "Maritimes" in l)
    end = marker + 1
    while end < len(lines) and lines[end].strip().startswith(".include"):
        end += 1
    lines[end:end] = [f'\t.include "data/maps/{n}/scripts.inc"' for n in names]
    with open(spath, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))


def shared_room(p, name):
    """A room every Pokémon Center links to (the Union Room, the Trade Center): each of its exits
    is MAP_DYNAMIC ("back where you came from"). It belongs to no town."""
    ws = p.load_map(name).events("warp_events")
    return bool(ws) and all(w["dest_map"] == "MAP_DYNAMIC" for w in ws)


def indoor_closure(p, starts):
    """Indoor maps reachable from `starts` through warps, never passing through a map that is
    not MAP_TYPE_INDOOR (so a town's houses, and their upper floors, but not the next town),
    and never into a shared room (a Center's upstairs leads to the Union Room, which every
    Center shares). Returned in breadth-first order, excluding `starts` themselves."""
    seen, out, queue = set(starts), [], list(starts)
    while queue:
        for w in p.load_map(queue.pop(0)).events("warp_events"):
            n = p.const_to_map.get(w["dest_map"])
            if n and n not in seen and p.load_map(n).j.get("map_type") == "MAP_TYPE_INDOOR" \
                    and not shared_room(p, n):
                seen.add(n); out.append(n); queue.append(n)
    return out
