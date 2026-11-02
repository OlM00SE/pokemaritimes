"""Shared helpers for tools that edit map JSON (add_interior, name_area, ...)."""
import json


def dump_json(path, obj):
    """Write JSON exactly as Porymap does (2-space indent, UTF-8, trailing newline), so an
    unchanged load+dump round-trips byte-for-byte."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def indoor_closure(p, starts):
    """Indoor maps reachable from `starts` through warps, never passing through a map that is
    not MAP_TYPE_INDOOR (so a town's houses, and their upper floors, but not the next town).
    Returned in breadth-first order, excluding `starts` themselves."""
    seen, out, queue = set(starts), [], list(starts)
    while queue:
        for w in p.load_map(queue.pop(0)).events("warp_events"):
            n = p.const_to_map.get(w["dest_map"])
            if n and n not in seen and p.load_map(n).j.get("map_type") == "MAP_TYPE_INDOOR":
                seen.add(n); out.append(n); queue.append(n)
    return out
