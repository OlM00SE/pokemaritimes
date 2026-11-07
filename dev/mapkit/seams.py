"""Seams: what a player sees of a neighbouring map across an edge connection, and of nothing at an
edge with no neighbour.

Engine facts (pokeemerald-expansion 1.17.2; design/mapping_reference.md, "Seams"):
- fieldmap.c Fill*Connection copies a neighbour's edge strip (7 tiles deep, 8 on the east) block for
  block into the current map's padded grid, and the strip is drawn with the CURRENT map's tilesets.
  A neighbour's secondary metatile in it shows whatever the current secondary has at that index
  (Route 203 drew Fredericton's Rustboro fence as a black column).
- People: TrySpawnObjectEvents (event_object_movement.c) spawns only the current map's object
  events (LoadObjEventTemplatesFromHeader reloads them on the camera transition, overworld.c). A
  person or item ball in a neighbour is invisible from across the seam and appears the step the
  player crosses it. Vanilla's maps keep people clear of their seams.
- The screen is 15 x 10 tiles: the player's tile has 7 columns beside it on each side, 4 rows above
  and 5 below; a person's 32-pixel sprite on the row just below the screen still shows its head.
  The step that crosses a seam loads the new map's people as it starts, while the next column or
  row scrolls in, so what a player standing just across an edge sees of this map before crossing
  is: 7 columns in beside it (the edge column and 6 more), 6 rows in when looking down (5 and a
  head), 4 rows in when looking up. As distances from the edge (0 = the edge row or column): the
  SEEN_ACROSS limits below.
- A margin cell with no connection draws the map's border pattern; with OW_EDGE_WATER the engine
  first carries water that reaches such an edge on into the margin (fieldmap.c ExtendEdgeWater;
  margin_fill below is its model).
"""
from .corpus import key_of
from .project import MAP_OFFSET, NUM_METATILES_IN_PRIMARY, TILE_FLAG_SURFABLE

EDGES = ("up", "down", "left", "right")
VIEW_X, VIEW_UP, VIEW_DOWN = 7, 4, 5          # tiles beside, above and below the player's
# how far into a map, counted from its edge (0 = the edge row/column), a person can be seen from
# across that edge before the player crosses: the player stands just beyond the edge, so a person
# `dist` in is dist + 1 away. Below the player a head shows one row further.
SEEN_ACROSS = {"left": VIEW_X - 1, "right": VIEW_X - 1,
               "up": VIEW_DOWN,               # the player is above, looking down into this map
               "down": VIEW_UP - 1}           # the player is below, looking up
OUTDOOR = {"MAP_TYPE_TOWN", "MAP_TYPE_CITY", "MAP_TYPE_ROUTE", "MAP_TYPE_OCEAN_ROUTE"}
COLLISION_MASK = 0x0C00                      # MAPGRID_COLLISION_MASK, the border's own collision


def strip_depth(direction):
    """How many rows/columns of a neighbour the engine copies on that side."""
    return MAP_OFFSET + 1 if direction == "right" else MAP_OFFSET


def _span(m, n, direction, offset):
    """The neighbour's cells in this map's coordinates that the engine copies into its margin:
    [(x, y, nx, ny)]. x/y may lie outside the map (the strip runs on into the corners)."""
    L, N = m.layout, n.layout
    out = []
    d = strip_depth(direction)
    if direction in ("up", "down"):
        for nx in range(N.width):
            x = nx + offset
            if not -MAP_OFFSET <= x < L.width + MAP_OFFSET + 1:
                continue
            for k in range(d):
                ny = N.height - 1 - k if direction == "up" else k
                y = -1 - k if direction == "up" else L.height + k
                if 0 <= ny < N.height:
                    out.append((x, y, nx, ny))
    else:
        for ny in range(N.height):
            y = ny + offset
            if not -MAP_OFFSET <= y < L.height + MAP_OFFSET:
                continue
            for k in range(d):
                nx = N.width - 1 - k if direction == "left" else k
                x = -1 - k if direction == "left" else L.width + k
                if 0 <= nx < N.width:
                    out.append((x, y, nx, ny))
    return out


def edge_pairs(m, n, direction, offset):
    """Cells side by side across the seam: [(x, y) on this map, (nx, ny) on the neighbour]."""
    L, N = m.layout, n.layout
    out = []
    if direction in ("up", "down"):
        y, ny = (0, N.height - 1) if direction == "up" else (L.height - 1, 0)
        for x in range(L.width):
            if 0 <= x - offset < N.width:
                out.append(((x, y), (x - offset, ny)))
    else:
        x, nx = (0, N.width - 1) if direction == "left" else (L.width - 1, 0)
        for y in range(L.height):
            if 0 <= y - offset < N.height:
                out.append(((x, y), (nx, y - offset)))
    return out


def wrong_tileset_cells(m, n, direction, offset):
    """The neighbour's strip cells this map's tilesets can't draw as the neighbour does:
    [(nx, ny, metatile)] in the neighbour's coordinates."""
    L, N = m.layout, n.layout
    if L.primary == N.primary and L.secondary == N.secondary:
        return []
    bad = []
    for x, y, nx, ny in _span(m, n, direction, offset):
        mid = N.mid(nx, ny)
        if L.primary != N.primary or mid >= NUM_METATILES_IN_PRIMARY:
            bad.append((nx, ny, mid))
    return bad


def people_in_view(m, direction, overlap):
    """This map's object events a player standing across the seam would see if the engine drew
    them: [(index, x, y, distance to the edge)]. overlap: (lo, hi), the edge cells the neighbour
    covers (columns for up/down, rows for left/right)."""
    L = m.layout
    lo, hi = overlap
    out = []
    for i, o in enumerate(m.events("object_events")):
        x, y = int(o["x"]), int(o["y"])
        rx, ry = int(o.get("movement_range_x", 0) or 0), int(o.get("movement_range_y", 0) or 0)
        # dist: how far in from the edge; along: the position along it; side: how far along the
        # edge beyond the shared part a player there can still see (rows: 5 below + a head, 4 above)
        if direction == "left":
            dist, along, reach, side = x - rx, y, ry, VIEW_DOWN + 1
        elif direction == "right":
            dist, along, reach, side = L.width - 1 - (x + rx), y, ry, VIEW_DOWN + 1
        elif direction == "up":
            dist, along, reach, side = y - ry, x, rx, VIEW_X
        else:
            dist, along, reach, side = L.height - 1 - (y + ry), x, rx, VIEW_X
        if dist <= SEEN_ACROSS[direction] and along + reach >= lo - side and along - reach <= hi + side:
            out.append((i, x, y, dist))
    return out


def unvanilla_pairs(corpus, m, n, direction, offset, skip=frozenset()):
    """Pairs across the seam that vanilla never draws side by side, as the engine draws them (the
    neighbour's block in this map's tilesets): [((x, y), mine, theirs)]. skip: neighbour cells
    already reported as unreadable (wrong tileset)."""
    L, N = m.layout, n.layout
    d = {"up": "N", "down": "S", "left": "W", "right": "E"}[direction]
    out = []
    for (x, y), (nx, ny) in edge_pairs(m, n, direction, offset):
        if (nx, ny) in skip:
            continue
        a, b = L.mid(x, y), N.mid(nx, ny)
        if not corpus.neigh.get(key_of(L.entry, a), {}).get(d, {}).get(key_of(L.entry, b), 0):
            out.append(((x, y), a, b))
    return out


def outside_labels(p, vocab, m, depth=2):
    """{(x, y): class} for the cells just across each connected edge of map m, `depth` deep (2:
    the 8-neighbourhood needs 1, a cut tree's other half needs 2), as the vocabulary labels the
    neighbour's blocks (tree quarters TL TR BL BR, G, S...). compile_sketch's `seams`.
    Labelled in the neighbour's own tilesets, i.e. what the land there is: across a seam between
    tilesets the player sees other graphics in the strip, and that is `seam_tileset`'s to report
    (an error on the plan's joins), not something an edge can be shaped around.
    Not yet seen by the grammar's forbidden-pair repair, flora, shores or cliffs: a forbidden pair
    across a seam shows up as `seam_tiles` instead."""
    out = {}
    for c in m.connections:
        name = p.const_to_map.get(c["map"])
        if c["direction"] not in EDGES or not name:
            continue
        n = p.load_map(name)
        N = n.layout
        for x, y, nx, ny in _span(m, n, c["direction"], int(c["offset"])):
            if max(-1 - x, x - m.layout.width, -1 - y, y - m.layout.height) < depth:
                out[(x, y)] = vocab.label(N.entry, N.mid(nx, ny))
    return out


def seam_issues(p, m, corpus=None, only=None, accept=frozenset()):
    """[(severity, code, message)] for every edge connection of map m (or only those to the
    neighbour folders in `only`). accept: this map's edge cells whose pair across the seam a
    designer has judged and accepted (corridor.toml `seam_ok`, each with its reason)."""
    issues = []
    for c in m.connections:
        direction = c["direction"]
        name = p.const_to_map.get(c["map"])
        if direction not in EDGES or not name or (only is not None and name not in only):
            continue
        n = p.load_map(name)
        off = int(c["offset"])
        bad = wrong_tileset_cells(m, n, direction, off)
        if bad:
            ex = ", ".join(f"({x},{y}) {mid:03X}" for x, y, mid in bad[:4])
            # WARN: vanilla does it in 12 places (Route 112/113, Slateport/Route 134...); the
            # corridor's planned joins are held to it by corridor.py check
            issues.append(("WARN", "seam_tileset",
                           f"{direction} -> {name}: {len(bad)} cells of its strip are metatiles of "
                           f"{n.layout.secondary if n.layout.primary == m.layout.primary else n.layout.primary}, "
                           f"which this map draws with {m.layout.secondary}'s (wrong graphics across "
                           f"the seam), e.g. {ex} on {name}"))
        pairs = edge_pairs(m, n, direction, off)
        if not pairs:
            continue
        along = [xy[0] if direction in ("up", "down") else xy[1] for xy, _ in pairs]
        for i, x, y, dist in people_in_view(m, direction, (min(along), max(along))):
            o = m.events("object_events")[i]
            issues.append(("WARN", "seam_person",
                           f"object_events[{i}] ({o.get('graphics_id', '?')}) at ({x},{y}) is {dist} "
                           f"tiles from the {direction} seam with {name}: invisible from there, it "
                           "appears the step the player crosses (keep people out of view of a seam)"))
        if corpus is not None:
            odd = [o for o in unvanilla_pairs(corpus, m, n, direction, off, {(x, y) for x, y, _ in bad})
                   if o[0] not in accept]
            if odd:
                ex = ", ".join(f"({x},{y}) {a:03X}|{b:03X}" for (x, y), a, b in odd[:5])
                issues.append(("WARN", "seam_tiles",
                               f"{direction} -> {name}: {len(odd)} of {len(pairs)} pairs across the seam "
                               f"are ones vanilla never draws side by side (a cut tree, a bank or cliff "
                               f"that stops), e.g. {ex}"))
    return issues


def margin_fill(p, m, layout=None):
    """Model of fieldmap.c ExtendEdgeWater: {(x, y): block} for margin cells (outside the map) that
    the engine fills by carrying edge water on outward, on each side with no connection at all (a
    side with any connection is left to it: GetMapBorderIdAt must keep answering INVALID for
    what's filled). layout: draw from this version of the map's blocks (a preview) instead of the
    saved one.

    Each water cell (surfable: MetatileBehavior_IsSurfableWaterOrUnderwater) on an edge runs on
    straight out to the margin's depth. So does a verge beside each run of it: the edge cell next to
    the run if a player could stand on it (the bank's grass), copied out, and one more cell of that
    same verge where the border pattern's 2x2 tree beyond it would otherwise lose a half (the
    pattern pairs grid lines odd-even). Filled cells are impassable (the border's own collision
    bits). Outdoor maps only (MAP_TYPE_TOWN, CITY, ROUTE, OCEAN_ROUTE)."""
    if m.j.get("map_type") not in OUTDOOR:
        return {}
    L = layout or m.layout
    tp = L.tiles
    w, h = L.width, L.height
    connected = {c["direction"] for c in m.connections if c["direction"] in EDGES}
    wet = lambda x, y: bool(p.tile_flags.get(tp.behavior(L.mid(x, y)), 0) & TILE_FLAG_SURFABLE)
    out = {}
    for direction in EDGES:
        if direction in connected:
            continue
        n_along = w if direction in ("up", "down") else h
        depth = strip_depth(direction)
        edge = {"up": lambda k: (k, 0), "down": lambda k: (k, h - 1),
                "left": lambda k: (0, k), "right": lambda k: (w - 1, k)}[direction]
        out_cell = {"up": lambda k, s: (k, -1 - s), "down": lambda k, s: (k, h + s),
                    "left": lambda k, s: (-1 - s, k), "right": lambda k, s: (w + s, k)}[direction]
        # the same rule, cell by cell, as fieldmap.c EdgeSource: water, else a verge (walkable,
        # beside water), else the cell beyond a verge whose border tree it would split
        water = lambda k: 0 <= k < n_along and wet(*edge(k))
        verge = lambda k: (0 <= k < n_along and not water(k) and not L.coll(*edge(k))
                           and (water(k - 1) or water(k + 1)))
        source = {}                                               # margin line -> edge cell copied
        for k in range(n_along):
            if water(k) or verge(k):
                source[k] = k
                continue
            g = k + MAP_OFFSET                                    # grid line, as the border reads it
            partner = g + 1 if g % 2 == 1 else g - 1
            for side in (1, -1):                                  # the verge before it, then after
                v = k - side
                if verge(v) and water(v - side) and partner == v + MAP_OFFSET:
                    source[k] = v
                    break
        for k, src in source.items():
            block = L.get(*edge(src)) | COLLISION_MASK
            for s in range(depth):        # straight out from the map's own edge: no connection
                out[out_cell(k, s)] = block   # strip lies there (a side's strip stays on its side)
    return out
