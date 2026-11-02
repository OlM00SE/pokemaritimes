"""Map validators built on the engine model. Each issue: (severity, code, message).

Severity: ERROR (broken in-game), WARN (likely wrong), INFO (worth knowing).
"""
import json, os
from .engine import World, DIRS, MAP_OFFSET
from .project import max_map_area_ok, TILE_FLAG_SURFABLE, TILE_FLAG_HAS_ENCOUNTERS, ELEVATION_DEFAULT


def _warp_kinds(p):
    """Warp trigger behaviours, taken from the engine's own predicates (field_control_avatar.c)."""
    # IsWarpMetatileBehavior: walking onto the tile warps (doors are handled by TryDoorWarp too)
    step_on = p.behavior_set("WarpDoor", "Ladder", "Escalator", "NonAnimDoor", "LavaridgeB1FWarp",
                             "Lavaridge1FWarp", "AquaHideoutWarp", "MtPyreHole", "MossdeepGymWarp",
                             "UnionRoomWarp")
    door = p.behavior_set("WarpDoor")            # TryDoorWarp: pressing north into the door tile
    step_on -= door
    arrow = {}
    for f, d in (("NorthArrowWarp", "N"), ("SouthArrowWarp", "S"), ("WestArrowWarp", "W"), ("EastArrowWarp", "E")):
        for b in p.behavior_set(f):
            arrow[b] = d
    stair = {}                                    # field_screen_effect.c IsDirectionalStairWarpMetatileBehavior
    for f, d in (("DirectionalUpLeftStairWarp", "W"), ("DirectionalDownLeftStairWarp", "W"),
                 ("DirectionalUpRightStairWarp", "E"), ("DirectionalDownRightStairWarp", "E")):
        for b in p.behavior_set(f):
            stair[b] = d
    return step_on, door, arrow, stair


def check_attributes(p, corpus, m, E, W):
    """Design-intent check: collision that contradicts how vanilla confidently uses a metatile.
    Walkable where vanilla is solid (walk through trees/rocks) is an ERROR; solid where vanilla
    is walkable (invisible wall) is a WARN. Elevation-only differences are left to the
    movement checks, which judge their actual effect."""
    from .terrain import TREE, PRIMARY
    L = m.layout
    tree_ids = set().union(*TREE.values()) if L.primary == PRIMARY else set()
    trees, walk_through, walls = [], [], []
    for y in range(L.height):
        for x in range(L.width):
            want = corpus.default_attrs(L.entry, L.mid(x, y), min_count=20, min_share=0.9)
            if not want:
                continue
            have = L.coll(x, y)
            if want[0] and not have:
                (trees if L.mid(x, y) in tree_ids else walk_through).append((x, y))
            elif have and not want[0]:
                walls.append((x, y))
    # Vanilla never makes trees walkable; it does deliberately make some rocks/cave tiles
    # walkable (hidden paths), so those are only a warning.
    if trees:
        E("attrs", f"{len(trees)} tree tiles are walkable (walk-through forest), e.g. {trees[:4]}; "
                   "fix with dev/fix_attrs.py")
    if walk_through:
        W("attrs", f"{len(walk_through)} tiles are walkable where vanilla usually makes that metatile "
                   f"solid (intended?), e.g. {walk_through[:4]}")
    if walls:
        W("attrs", f"{len(walls)} tiles are solid but vanilla makes that metatile walkable "
                   f"(invisible walls?), e.g. {walls[:4]}")


def check_map(p, name, wild_maps=None, corpus=None):
    issues = []
    E = lambda c, m: issues.append(("ERROR", c, m))
    W = lambda c, m: issues.append(("WARN", c, m))
    I = lambda c, m: issues.append(("INFO", c, m))
    m = p.load_map(name)
    L, tp = m.layout, m.layout.tiles

    # ---- structure ----
    if not L.size_ok:
        E("size", f"map.bin size does not match layout {L.width}x{L.height}")
    if not max_map_area_ok(L.width, L.height):
        E("size", f"{L.width}x{L.height} exceeds MAX_MAP_DATA_SIZE ((w+15)*(h+14) <= 10240)")
    missing = {L.mid(x, y) for y in range(L.height) for x in range(L.width) if not tp.exists(L.mid(x, y))}
    if missing:
        E("metatile", f"metatile ids not in tileset pair: {sorted(hex(i) for i in missing)[:8]}")
    if len(L.border) != 4:
        W("border", f"border has {len(L.border)} blocks (Emerald uses 2x2)")

    if corpus is not None:
        check_attributes(p, corpus, m, E, W)

    world = World(p, m)
    w, h = L.width, L.height

    # ---- tile sanity ----
    underwater = m.j.get("map_type") == "MAP_TYPE_UNDERWATER"
    unsup = {tp.behavior(L.mid(x, y)) for y in range(h) for x in range(w)} & world.unsupported
    if unsup:
        I("unsupported", "behaviours not modelled by the checker: "
          + ", ".join(p.behavior_names.get(b, str(b)) for b in sorted(unsup)))

    # ---- connections ----
    opp = {"up": "down", "down": "up", "left": "right", "right": "left"}
    entries = []                                    # (label, [grid states])
    for c in m.connections:
        if c["direction"] not in opp:            # dive / emerge are not edge connections
            continue
        dest = p.const_to_map.get(c["map"])
        if not dest:
            E("connection", f"{c['direction']} -> unknown map {c['map']}")
            continue
        back = [k for k in p.load_map(dest).connections
                if k["map"] == m.id and k["direction"] == opp[c["direction"]]]
        if not back:
            E("connection", f"{c['direction']} -> {dest}: no reciprocal connection")
        elif back[0]["offset"] != -c["offset"]:
            E("connection", f"{c['direction']} -> {dest}: offset {c['offset']}, reverse is "
                            f"{back[0]['offset']} (must be {-c['offset']})")
        cells = [cell for cell, (d, n) in world.conn_side.items() if d == c["direction"] and n == dest]
        # cells in the margin that touch the map edge: states the player enters the map from
        touching = [(gx, gy) for gx, gy in cells
                    if any(world.in_map(gx + dx, gy + dy) for dx, dy in DIRS.values())]
        if not touching:
            E("connection", f"{c['direction']} -> {dest}: neighbour does not overlap this map's edge")
        # arriving over water means arriving while surfing
        states = [world.arrival_state(gx, gy) for gx, gy in touching if world.collision(gx, gy) == 0]
        crossable = [s for s in states if any(
            (ns := world.step(s, d)[0]) and world.in_map(ns[0], ns[1]) for d in "NSWE")]
        if touching and not crossable:
            W("connection", f"{c['direction']} -> {dest}: no walkable crossing along the shared edge")
        if crossable:
            entries.append((f"edge {c['direction']}->{dest}", crossable))

    # ---- warps ----
    step_on, door, arrow, stair = _warp_kinds(p)
    warp_needs = []                                  # (label, list of (state predicate))
    for i, wv in enumerate(m.events("warp_events")):
        x, y, el = wv["x"], wv["y"], wv.get("elevation", 0)
        if not L.inb(x, y):
            W("warp", f"warp {i} at ({x},{y}) out of bounds (can never be used)"); continue
        dest = p.const_to_map.get(wv["dest_map"])
        if wv["dest_map"] not in ("MAP_DYNAMIC", "MAP_NONE") and not dest:
            E("warp", f"warp {i} -> unknown map {wv['dest_map']}")
        elif dest:
            dw = p.load_map(dest).events("warp_events")
            wid = str(wv["dest_warp_id"])
            if wid.isdigit() and int(wid) >= len(dw):
                E("warp", f"warp {i} -> {dest} warp {wid}, but it has only {len(dw)} warps")
            elif wid.isdigit() and dw[int(wid)]["dest_map"] not in (m.id, "MAP_DYNAMIC"):
                W("warp", f"warp {i} -> {dest} warp {wid}, which leads to {dw[int(wid)]['dest_map']}")
        b = tp.behavior(L.mid(x, y))
        gx, gy = world.to_grid(x, y)
        # GetWarpEventAtPosition: event elevation must be 0 or equal the position's elevation
        on = lambda s, el=el: el == 0 or world.event_elevation(s) == el
        front = lambda s, el=el: el == 0 or world.event_elevation(s, in_front=True) == el
        if b in door:      # TryDoorWarp: player south of the door, pressing north (in-front position)
            warp_needs.append((f"warp {i} (door)", lambda s, gx=gx, gy=gy, f=front: s[:2] == (gx, gy + 1) and f(s)))
        elif b in arrow:   # TryArrowWarp: standing on the arrow tile
            warp_needs.append((f"warp {i} (arrow)", lambda s, gx=gx, gy=gy, f=on: s[:2] == (gx, gy) and f(s)))
        elif b in stair:
            warp_needs.append((f"warp {i} (stairs)", lambda s, gx=gx, gy=gy, f=on: s[:2] == (gx, gy) and f(s)))
        elif b in step_on:
            warp_needs.append((f"warp {i}", lambda s, gx=gx, gy=gy, f=on: s[:2] == (gx, gy) and f(s)))
        else:
            # Legitimate as an arrival point (scripted warps, Dive, fly/escape targets), but the
            # player cannot leave through it. On water it is almost certainly a mistake.
            fl = p.tile_flags.get(b, 0)
            (E if fl & TILE_FLAG_SURFABLE and m.j.get("map_type") != "MAP_TYPE_UNDERWATER" and
             not str(wv.get("dest_map", "")).startswith("MAP_UNDERWATER") else W)(
                "warp", f"warp {i} at ({x},{y}) is on {p.behavior_names.get(b, b)}: arrival-only, "
                        "walking onto it does nothing")
        # arriving through this warp puts the player on its tile
        entries.append((f"warp {i}", [world.arrival_state(gx, gy)]))

    # ---- other events ----
    for kind in ("object_events", "bg_events", "coord_events"):
        for i, ev in enumerate(m.events(kind)):
            if not L.inb(ev["x"], ev["y"]):
                W("event", f"{kind}[{i}] at ({ev['x']},{ev['y']}) out of bounds (never fires)"); continue
            s = ev.get("script")
            if s not in (None, "", "0x0", "NULL") and s not in p.script_labels:
                E("script", f"{kind}[{i}] script '{s}' is not defined anywhere")
            if s == "NULL":
                (E if kind == "bg_events" and ev.get("type") == "sign" else W)(
                    "script", f"{kind}[{i}] has script NULL")

    # ---- reachability (on foot, and with Surf) ----
    starts = [s for _, ss in entries for s in ss]
    # "on foot" exploration starts only from land entrances; surfing arrivals are Surf content
    foot = world.explore([s for s in starts if not world.surfing(s)], allow_surf=False) if starts else {}
    surf = world.explore(starts, allow_surf=True) if starts else {}
    # Water must only be enterable by surfing. (Water at elevation 3 is fine if the land
    # around it is at another elevation; what matters is whether a walker can step onto it.)
    walk_water = sorted({world.to_map(s[0], s[1]) for s in foot if not world.surfing(s)
                         and world.in_map(s[0], s[1]) and world.flags(s[0], s[1]) & TILE_FLAG_SURFABLE})
    if walk_water and not underwater:
        E("water", f"{len(walk_water)} surfable tiles can be walked onto without Surf, e.g. {walk_water[:4]}")
    for label, pred in warp_needs:
        if not any(pred(s) for s in foot):
            if any(pred(s) for s in surf):
                I("reach", f"{label}: reachable only with Surf")
            else:
                E("reach", f"{label}: cannot be triggered from any entrance (position/elevation)")
    # entrances split into separate areas?
    if len(entries) > 1:
        comp = {}
        for label, ss in entries:
            reach = set(world.explore(ss, allow_surf=False))
            comp[label] = {(s[0], s[1]) for s in reach}
        groups = []
        for label in comp:
            for g in groups:
                if comp[label] & comp[g[0]]:
                    g.append(label); break
            else:
                groups.append([label])
        if len(groups) > 1:
            W("reach", "on foot, entrances form separate areas: " + " | ".join("[" + ", ".join(g) + "]" for g in groups))

    # ---- encounters ----
    has_grass = any(p.tile_flags.get(tp.behavior(L.mid(x, y)), 0) & TILE_FLAG_HAS_ENCOUNTERS
                    and not p.tile_flags.get(tp.behavior(L.mid(x, y)), 0) & TILE_FLAG_SURFABLE
                    for y in range(h) for x in range(w))
    if wild_maps is not None and has_grass and m.id not in wild_maps:
        I("encounters", "has encounter tiles but no wild_encounters.json entry (no wild Pokémon)")
    return issues


def wild_encounter_maps(p):
    data = json.load(open(p.path("src/data/wild_encounters.json"), encoding="utf-8"))
    out = set()
    for g in data.get("wild_encounter_groups", []):
        for e in g.get("encounters", []):
            out.add(e.get("map"))
    return out
