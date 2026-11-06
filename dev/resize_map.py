"""Resize a map's layout, moving everything that stands on it with the terrain.

  python dev/resize_map.py Woodstock_2 48x42                       # dry run: the plan
  python dev/resize_map.py Woodstock_2 48x42 --offset 2,4          # old (0,0) lands on new (2,4)
  python dev/resize_map.py Woodstock_2 48x42 --connect Route201_1=22 --apply

The old blocks are copied to (x + dx, y + dy); new cells get the map's border pattern (solid,
like the border the player sees past the edge), ready for a redesign. With the terrain move:
  * people, warps, signs and triggers (map.json), refused if one would fall off the map;
  * heal locations on this map (src/data/heal_locations.json);
  * connections: each keeps its alignment with the moved terrain (offset + dx or dy), on both
    sides, unless --connect NEIGHBOUR=OFFSET sets it (this map's offset; the neighbour's side
    is its negative), e.g. to re-offset a seam to the corridor plan. NEIGHBOUR:DIRECTION picks
    one side when the neighbour joins on two.
Refused: a shared layout (dev/unique_layout.py first), a size the engine can't load, a crop
that loses an event, a --connect for a connection that doesn't exist (or names a neighbour
joined on two sides without the side), and an --apply whose plan differs from the preview.

Reported, not changed (they need a human):
  * scripts elsewhere that name the map with coordinates (warp, setrespawn, ...);
  * dev tests that name the map (they may hold coordinates);
  * saved games: a save standing on this map continues at its old coordinates. Add a world
    revision for the map (src/overworld.c, sWorldRevisions) so CONTINUE moves such a player to
    a safe tile, or announce a save break.
"""
import argparse
import json
import os
import re
import struct
from mapkit.project import Project, max_map_area_ok
from mapkit.layout import layout_users, pack
from mapkit.mapjson import dump_json
from mapkit.transaction import atomic_write, edit
from mapkit.geo import OPPOSITE

EVENT_KINDS = ("object_events", "warp_events", "coord_events", "bg_events")
HEAL_PATH = "src/data/heal_locations.json"
COORD_SCRIPT = re.compile(r"\b(warp\w*|setwarp|setdynamicwarp|setescapewarp|setrespawn|"
                          r"setdivewarp|setholewarp)\b[^\n]*\bMAP_(\w+)\s*,[^\n]*\d+\s*,\s*-?\d+", re.I)


class Plan:
    def __init__(self, name, old_wh, new_wh, offset):
        self.name, self.old_wh, self.new_wh, self.offset = name, old_wh, new_wh, offset
        self.blocks = []
        self.lost_cells = 0
        self.events = {}            # kind -> new list
        self.moved = []             # (kind, label, (x, y), (nx, ny))
        self.problems = []
        self.heal = None            # new heal_locations data, or None
        self.heal_moved = []
        self.connections = []       # (neighbour, direction, old, new)
        self.neighbour_json = {}    # neighbour map name -> new map.json dict
        self.references = []        # strings: things a human must check


def _label(kind, ev):
    if kind == "object_events":
        return ev.get("local_id") or ev.get("script") or ev.get("graphics_id")
    if kind == "warp_events":
        return f"warp to {ev.get('dest_map')}"
    return ev.get("script") or ev.get("type") or kind


def plan(p, name, new_w, new_h, dx=0, dy=0, connect=None, references=True):
    """connect: {neighbour or "neighbour:direction": offset}. references=False skips the report
    of what a human must check (apply re-plans without it)."""
    connect = dict(connect or {})
    if name not in p.map_names:
        raise ValueError(f"unknown map {name}")
    m = p.load_map(name)
    L = m.layout
    users = layout_users(p, L.entry)
    if len(users) > 1:
        raise ValueError(f"layout {L.id} is shared by {', '.join(users)}; "
                         f"run dev/unique_layout.py {name} --apply first")
    if new_w < 1 or new_h < 1:
        raise ValueError("the new size must be at least 1x1")
    if not max_map_area_ok(new_w, new_h):
        raise ValueError(f"{new_w}x{new_h} is too big for the engine's map buffer "
                         "((w + 15) * (h + 14) <= 10240)")
    pl = Plan(name, (L.width, L.height), (new_w, new_h), (dx, dy))

    # --- terrain: old blocks at +offset, new cells from the border pattern (solid) ---
    for y in range(new_h):
        for x in range(new_w):
            ox, oy = x - dx, y - dy
            if L.inb(ox, oy):
                pl.blocks.append(L.get(ox, oy))
            else:
                pl.blocks.append(pack(L.border_block(x, y) & 0x3FF, 1, 0))
    for y in range(L.height):
        for x in range(L.width):
            if not (0 <= x + dx < new_w and 0 <= y + dy < new_h):
                pl.lost_cells += 1

    # --- events ---
    for kind in EVENT_KINDS:
        out = []
        for ev in m.events(kind):
            ev = dict(ev)
            x, y = ev["x"], ev["y"]
            nx, ny = x + dx, y + dy
            if not (0 <= nx < new_w and 0 <= ny < new_h):
                pl.problems.append(f"{kind[:-7]} {_label(kind, ev)} at ({x},{y}) would be at "
                                   f"({nx},{ny}), off the {new_w}x{new_h} map")
            ev["x"], ev["y"] = nx, ny
            if (dx, dy) != (0, 0):
                pl.moved.append((kind, _label(kind, ev), (x, y), (nx, ny)))
            out.append(ev)
        pl.events[kind] = out

    # --- heal locations on this map ---
    heal = json.load(open(p.path(HEAL_PATH), encoding="utf-8"))
    changed = False
    for h in heal["heal_locations"]:
        if h.get("map") == m.id:
            nx, ny = h["x"] + dx, h["y"] + dy
            if not (0 <= nx < new_w and 0 <= ny < new_h):
                pl.problems.append(f"heal location {h['id']} at ({h['x']},{h['y']}) would be off the map")
            pl.heal_moved.append((h["id"], (h["x"], h["y"]), (nx, ny)))
            h["x"], h["y"] = nx, ny
            changed = changed or (dx, dy) != (0, 0)
        if h.get("respawn_map") == m.id and "respawn_x" in h:
            nx, ny = h["respawn_x"] + dx, h["respawn_y"] + dy
            pl.heal_moved.append((h["id"] + " (respawn)", (h["respawn_x"], h["respawn_y"]), (nx, ny)))
            h["respawn_x"], h["respawn_y"] = nx, ny
            changed = changed or (dx, dy) != (0, 0)
    pl.heal = heal if changed else None

    # --- connections, both sides ---
    links = [(p.const_to_map.get(c["map"]), c["direction"]) for c in m.connections]
    for key in connect:
        nb, _, d = key.partition(":")
        hits = [l for l in links if l[0] == nb and (not d or l[1] == d)]
        if not hits:
            raise ValueError(f"--connect {key}: {name} has no such connection")
        if len(hits) > 1:
            raise ValueError(f"--connect {key}: {name} joins {nb} on {len(hits)} sides; "
                             f"name one, e.g. {nb}:{hits[0][1]}")
    for c in m.connections:
        nb = p.const_to_map.get(c["map"])
        d = c["direction"]
        if d not in OPPOSITE:                 # dive/emerge: whole-map links, no offset to keep
            continue
        old = int(c["offset"])
        new = connect.get(f"{nb}:{d}", connect.get(nb, old + (dx if d in ("up", "down") else dy)))
        pl.connections.append((nb, d, old, new))
        if nb is None:
            pl.problems.append(f"connection {d} to {c['map']}: no such map folder")
            continue
        nj = pl.neighbour_json.get(nb) or json.load(open(p.path("data/maps", nb, "map.json"), encoding="utf-8"))
        back = [bc for bc in nj.get("connections") or []
                if bc["map"] == m.id and bc["direction"] == OPPOSITE[d]]
        if len(back) != 1:
            pl.problems.append(f"{nb} has {len(back)} connections {OPPOSITE[d]} to {name} (expected 1)")
            continue
        if int(back[0]["offset"]) != -old:
            pl.problems.append(f"{nb}'s connection back to {name} has offset {back[0]['offset']}, "
                               f"not {-old}: fix the pair before resizing")
            continue
        back[0]["offset"] = -new
        pl.neighbour_json[nb] = nj

    if references:
        pl.references = _references(p, name, m.id[4:])
    return pl


def _references(p, name, short):
    """What a human must check: scripts elsewhere naming the map with coordinates, dev scripts
    naming the map, and the saves standing on it."""
    out = []
    me = os.path.normcase(os.path.abspath(__file__))
    for root in ("data/maps", "data/scripts"):
        for dirpath, _, files in os.walk(p.path(root)):
            if os.path.normcase(dirpath).startswith(os.path.normcase(p.path("data/maps", name))):
                continue
            for f in files:
                if not f.endswith((".inc", ".pory", ".s")):
                    continue
                txt = open(os.path.join(dirpath, f), encoding="utf-8", errors="replace").read()
                for mm in COORD_SCRIPT.finditer(txt):
                    if mm.group(2) == short:
                        rel = os.path.relpath(os.path.join(dirpath, f), p.root).replace("\\", "/")
                        out.append(f"script {rel}: {mm.group(0).strip()[:90]}")
    tests = []
    for dirpath, _, files in os.walk(p.path("dev")):
        if "out" in os.path.relpath(dirpath, p.path("dev")).split(os.sep):
            continue
        for f in files:
            if os.path.normcase(os.path.abspath(os.path.join(dirpath, f))) == me:
                continue
            if f.endswith(".py") and name in open(os.path.join(dirpath, f), encoding="utf-8",
                                                  errors="replace").read():
                tests.append(os.path.relpath(os.path.join(dirpath, f), p.root).replace("\\", "/"))
    if tests:
        out.append("dev scripts that name the map (check any coordinates they hold): "
                   + ", ".join(sorted(tests)))
    out.append(f"saved games standing on {name} continue at their old coordinates: "
               "add a world revision (src/overworld.c, sWorldRevisions) or announce a save break")
    return out


def apply(p, pl, connect=None):
    # Re-plan at the write boundary: refuse if anything changed since the preview.
    fresh = plan(p, pl.name, *pl.new_wh, *pl.offset, connect=connect, references=False)
    if fresh.problems:
        raise ValueError("; ".join(fresh.problems))
    if (fresh.blocks, fresh.events, fresh.connections, fresh.heal, fresh.neighbour_json) != \
            (pl.blocks, pl.events, pl.connections, pl.heal, pl.neighbour_json):
        raise ValueError("the map or its neighbours changed since the preview; preview it again")
    m = p.load_map(pl.name)
    files = ["data/layouts/layouts.json", m.layout.entry["blockdata_filepath"],
             f"data/maps/{pl.name}/map.json"] + [f"data/maps/{nb}/map.json" for nb in fresh.neighbour_json]
    if fresh.heal is not None:
        files.append(HEAL_PATH)
    with edit(p, files):
        atomic_write(p.path(m.layout.entry["blockdata_filepath"]),
                     struct.pack(f"<{len(fresh.blocks)}H", *fresh.blocks))
        data = json.load(open(p.path("data/layouts/layouts.json"), encoding="utf-8"))
        entry = next(l for l in data["layouts"] if l.get("id") == m.layout.id)
        entry["width"], entry["height"] = fresh.new_wh
        dump_json(p.path("data/layouts/layouts.json"), data)
        for kind, evs in fresh.events.items():
            if kind in m.j:
                m.j[kind] = evs
        for c in m.j.get("connections") or []:
            nb = p.const_to_map.get(c["map"])
            for cn, d, _, new in fresh.connections:
                if cn == nb and d == c["direction"]:
                    c["offset"] = new
        m.save()
        for nb, nj in fresh.neighbour_json.items():
            dump_json(p.path("data/maps", nb, "map.json"), nj)
        if fresh.heal is not None:
            dump_json(p.path(HEAL_PATH), fresh.heal)
    return fresh


def report(pl):
    (ow, oh), (nw, nh), (dx, dy) = pl.old_wh, pl.new_wh, pl.offset
    print(f"{pl.name}: {ow}x{oh} -> {nw}x{nh}, old (0,0) at new ({dx},{dy})")
    added = nw * nh - (ow * oh - pl.lost_cells)
    print(f"  terrain: {ow * oh - pl.lost_cells} cells kept, {added} new (border fill, solid), "
          f"{pl.lost_cells} cropped")
    n = sum(len(v) for v in pl.events.values())
    print(f"  events: {n} on the map, {len(pl.moved)} moved")
    for kind, label, a, b in pl.moved:
        print(f"    {kind[:-7]:6s} {label}: {a} -> {b}")
    for hid, a, b in pl.heal_moved:
        print(f"  heal location {hid}: {a} -> {b}")
    for nb, d, old, new in pl.connections:
        print(f"  connection {d:5s} {nb}: offset {old} -> {new}" + ("" if old != new else " (unchanged)"))
    for r in pl.references:
        print(f"  CHECK: {r}")
    for pr in pl.problems:
        print(f"  REFUSED: {pr}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("size", help="WxH, e.g. 48x42")
    ap.add_argument("--offset", default="0,0", help="dx,dy: where the old (0,0) lands")
    ap.add_argument("--connect", action="append", default=[], metavar="MAP[:DIR]=OFFSET",
                    help="set this map's connection offset to a neighbour (its side gets -OFFSET); "
                         "name the direction when the neighbour joins on two sides")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    try:
        w, h = (int(v) for v in a.size.lower().split("x"))
        dx, dy = (int(v) for v in a.offset.split(","))
        connect = {}
        for c in a.connect:
            k, v = c.split("=")
            connect[k.strip()] = int(v)
    except ValueError:
        print("NOT APPLIED: give the size as WxH, --offset as dx,dy and --connect as MAP=OFFSET")
        return 2
    p = Project()
    try:
        pl = plan(p, a.map, w, h, dx, dy, connect)
        report(pl)
        if pl.problems:
            print("NOT APPLIED")
            return 1
        if a.apply:
            apply(p, pl, connect)
            print("applied")
        else:
            print("dry run; pass --apply to write")
        return 0
    except ValueError as ex:
        print(f"NOT APPLIED: {ex}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
