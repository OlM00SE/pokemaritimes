"""Shores: where river/sea water meets land, built by shape from vanilla's two piece sets.

gTileset_General draws a shoreline with the same structure in two materials (mined from the 238
vanilla layouts; tests/shore_pieces.py checks the tables against every vanilla cell where water
meets only grass or only beach sand):

  * The edge along the water's north, east and west sides is drawn on the WATER tile.
    The edge along its south side is drawn on the LAND tile below it.
  * Corners and the ends of side banks have their own water pieces.

                              grass bank (river)    beach (sand)
  water, land N               189                   12C
  water, land W / E           190 / 192             125 / 123
  water, land N+W / N+E       188 / 18A             146 / 145
  water, land E, NE water     178 (bank top end)    11B
  water, land W, NW water     179                   11D
  water, land NW only         198 (inner corner)    12D
  water, land NE only         19A                   12B
  land, water N               002 (learned rules)   11C; 13D when NE is land, 13E when NW is land
  open water                  170                   170

Sketch side: '~' is river/sea water, ':' is sand. Sand that touches water is a beach: its
water edges come from the beach set, and its land side keeps the learned sand-patch rim toward
grass. 'r' is a 2x2 rock standing in water (150 151 / 158 159; it draws its own edge).

Shapes the tiles can't draw are refused with the cells to fix, like ledges:
  * water one tile wide between two side banks (no piece has both side edges);
  * a corner where a grass bank turns into a beach (no mixed corner piece);
  * water squeezed between a side bank and the opposite diagonal (e.g. land E and land NW).
Kept '#' tiles (rocks, bridges, cliffs) and pond water count as "no land": vanilla draws those
edges on the object itself.
"""

WATER_CLS = "S"
SAND_CLS = "SA"
BANK_LAND = {"G", "TG", "P", "LD", "TL", "TR", "BL", "BR", "T"}
BEACH_LAND = {SAND_CLS}

BANK = {"N": 0x189, "W": 0x190, "E": 0x192, "NW": 0x188, "NE": 0x18A,
        "E_end": 0x178, "W_end": 0x179, "cNW": 0x198, "cNE": 0x19A}
BEACH = {"N": 0x12C, "W": 0x125, "E": 0x123, "NW": 0x146, "NE": 0x145,
         "E_end": 0x11B, "W_end": 0x11D, "cNW": 0x12D, "cNE": 0x12B}
OPEN_WATER = 0x170
SAND_EDGE = {"N": 0x11C, "N_landNE": 0x13D, "N_landNW": 0x13E}
BEACH_SAND = 0x124              # plain beach sand (the lip is on the water tile)
SAND_INTERIOR = 0x121           # the sand patch's interior; same picture as 124
GRASS_BANK_TILES = {0x002, 0x1E8, 0x1E9, 0x0D3, 0x0D4}   # grass with the bank along its top
ROCK = {(0, 0): 0x150, (1, 0): 0x151, (0, 1): 0x158, (1, 1): 0x159}
ROCK_CHAR = "r"
ROCK_CLS = "RK"

WATER_PIECES = {OPEN_WATER} | set(BANK.values()) | set(BEACH.values())
SAND_PIECES = set(SAND_EDGE.values()) | {BEACH_SAND}
ROCK_PIECES = set(ROCK.values())
ALL_PIECES = WATER_PIECES | SAND_PIECES | ROCK_PIECES
KIND_NAME = {"bank": "a grass bank", "beach": "a beach"}


def _kind(c):
    if c in BEACH_LAND:
        return "beach"
    if c in BANK_LAND:
        return "bank"
    return None                     # water, pond, kept tiles, rocks: no edge drawn on the water


def _at(cls, x, y, w, h):
    """Off the map, a cell continues the nearest edge cell (rivers run off the map edge)."""
    return cls[min(max(y, 0), h - 1)][min(max(x, 0), w - 1)]


def water_piece(cls, x, y, w, h):
    """(metatile, None) or (None, error message) for the water cell at (x, y)."""
    k = {d: _kind(_at(cls, x + dx, y + dy, w, h)) for d, (dx, dy) in
         (("N", (0, -1)), ("E", (1, 0)), ("W", (-1, 0)), ("NE", (1, -1)), ("NW", (-1, -1)))}
    n, e, wv, ne, nw = k["N"], k["E"], k["W"], k["NE"], k["NW"]
    if e and wv:
        return None, "water one tile wide here (land on both sides); make it at least two wide"
    if n:
        side = wv or e
        if side and side != n:
            return None, (f"{KIND_NAME[n]} turns into {KIND_NAME[side]} at a corner; "
                          "start the beach on a straight stretch of shore")
        key = "NW" if wv else "NE" if e else "N"
        kind = n
    elif e or wv:
        opp = nw if e else ne               # the diagonal on the far side
        if opp:
            return None, "water squeezed between a bank and the opposite corner; widen it"
        kind = e or wv
        key = ("E" if ne else "E_end") if e else ("W" if nw else "W_end")
    elif ne and nw:
        return None, "land on both upper corners of this water; widen the channel above it"
    elif ne or nw:
        kind = ne or nw
        key = "cNE" if ne else "cNW"
    else:
        return OPEN_WATER, None
    return (BEACH if kind == "beach" else BANK)[key], None


def sand_piece(cls, x, y, w, h):
    """Sand with water to its north carries the edge itself; None for other sand."""
    if _at(cls, x, y - 1, w, h) != WATER_CLS:
        return None
    if _kind(_at(cls, x + 1, y - 1, w, h)):
        return SAND_EDGE["N_landNE"]
    if _kind(_at(cls, x - 1, y - 1, w, h)):
        return SAND_EDGE["N_landNW"]
    return SAND_EDGE["N"]


def touches_water(cls, x, y, w, h):
    return any(_at(cls, x + dx, y + dy, w, h) == WATER_CLS
               for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


def place_rocks(cls, w, h):
    """Turn ROCK_CLS cells into whole 2x2 rocks. Returns ({(x, y): metatile}, errors)."""
    pieces, errors = {}, []
    for y in range(h):
        for x in range(w):
            if cls[y][x] != ROCK_CLS or (x, y) in pieces:
                continue
            quad = [(x + dx, y + dy) for dx, dy in ROCK]
            if not all(0 <= qx < w and 0 <= qy < h and cls[qy][qx] == ROCK_CLS and (qx, qy) not in pieces
                       for qx, qy in quad):
                errors.append((x, y, "a water rock is a whole 2x2 block of 'r'"))
                continue
            for (dx, dy), mid in ROCK.items():
                pieces[(x + dx, y + dy)] = mid
    for (x, y) in list(pieces):
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in pieces and cls[ny][nx] != WATER_CLS:
                errors.append((x, y, f"a water rock must stand in water, but ({nx},{ny}) is not water"))
    return pieces, sorted(set(errors))


def resolve(cls, w, h):
    """cls: final class grid (after grammar repair and tree placement).
    Returns (water {(x, y): metatile}, sand_edges {(x, y): metatile}, beach_cells set, errors).
    beach_cells: sand that touches water without carrying an edge; the compiler turns the
    learned sand interior there into beach sand."""
    water, sand, beach, errors = {}, {}, set(), []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c == WATER_CLS:
                mid, err = water_piece(cls, x, y, w, h)
                if err:
                    errors.append((x, y, err))
                else:
                    water[(x, y)] = mid
            elif c == SAND_CLS and touches_water(cls, x, y, w, h):
                mid = sand_piece(cls, x, y, w, h)
                if mid is None:
                    beach.add((x, y))
                else:
                    sand[(x, y)] = mid
    return water, sand, beach, errors


def grass_piece(cls, x, y, w, h, learned):
    """Grass beside water: the bank along its top when water is north (keeping the learned
    tree-canopy variants 1E8/1E9); with land north of it, no bank at all. None: leave the
    learned tile (e.g. under a kept '#' tile, which may be water from another tileset)."""
    n = _at(cls, x, y - 1, w, h)
    if n == WATER_CLS:
        return learned if learned in GRASS_BANK_TILES else 0x002
    if learned in GRASS_BANK_TILES and _kind(n):
        return 0x001
    return None


def apply(cls, mids, w, h, sand_view_mids=None):
    """Overwrite the learned tiles in `mids` with shore pieces, in place. Returns the number of
    cells changed. sand_view_mids: learned tiles computed with water seen as sand (so the
    sand patch's rim faces only grass); used for sand cells that touch water.
    Every '~' cell gets its shore piece: a sketch's '~' is surface water, and a special water
    tile (a waterfall, deep water, a current) is kept with '#' (sketch.extract does that)."""
    water, sand, beach, errors = resolve(cls, w, h)
    if errors:
        raise ValueError(f"unresolved shore shapes: {errors[:3]}")
    changed = 0

    def put(x, y, mid):
        nonlocal changed
        if mid is not None and mids[y][x] != mid:
            mids[y][x] = mid
            changed += 1
    for (x, y), mid in water.items():
        put(x, y, mid)
    for (x, y), mid in sand.items():
        put(x, y, mid)
    for (x, y) in beach:
        learned = sand_view_mids[y][x] if sand_view_mids else mids[y][x]
        put(x, y, BEACH_SAND if learned in (SAND_INTERIOR, BEACH_SAND) else learned)
    for y in range(h):
        for x in range(w):
            if cls[y][x] == "G" and touches_water(cls, x, y, w, h):
                put(x, y, grass_piece(cls, x, y, w, h, mids[y][x]))
    return changed


def keep_unrebuildable(rows, w, h, mid_at, to_cls):
    """Extraction: turn every shore cell a compile would not reproduce into '#' (kept as is):
    water ('~') whose tile isn't its shape's piece (special water such as waterfalls included),
    beach sand whose edge doesn't match, grass beside water whose bank doesn't match, and
    rocks that aren't whole 2x2 rocks in water. Kept cells count as "no land", so the loop
    repeats until nothing changes. Returns the number of cells kept."""
    kept = 0
    while True:
        cls = [[to_cls(ch) for ch in row] for row in rows]
        water, sand, beach, errors = resolve(cls, w, h)
        rocks, rock_errors = place_rocks(cls, w, h)
        bad = {(x, y) for x, y, _ in errors + rock_errors}
        bad |= {xy for xy, mid in rocks.items() if mid != mid_at(*xy)}
        for y in range(h):
            for x in range(w):
                ch, m = rows[y][x], mid_at(x, y)
                if ch == "~":
                    if water.get((x, y), m) != m:
                        bad.add((x, y))
                elif ch == ":":
                    if (x, y) in sand:
                        ok = sand[(x, y)] == m
                    elif (x, y) in beach:      # beach sand, or the learned rim toward grass
                        ok = m == BEACH_SAND or m not in SAND_PIECES
                    else:
                        ok = m not in SAND_PIECES
                    if not ok:
                        bad.add((x, y))
                elif cls[y][x] == "G" and touches_water(cls, x, y, w, h):
                    want = grass_piece(cls, x, y, w, h, m)
                    if want is not None and want != m:
                        bad.add((x, y))
        if not bad:
            return kept
        for x, y in bad:
            rows[y][x] = "#"
            kept += 1


def learning_view(cls):
    """Copy of cls for the learned rules: a water rock reads as a kept tile ('F'), which is how
    the vanilla maps the rules were learned from label it."""
    return [["F" if c == ROCK_CLS else c for c in row] for row in cls]


def sand_view(cls, w, h):
    """Copy of cls in which water touching sand reads as sand, for learning the sand rim."""
    out = [row[:] for row in cls]
    for y in range(h):
        for x in range(w):
            if cls[y][x] == WATER_CLS and any(
                    0 <= x + dx < w and 0 <= y + dy < h and cls[y + dy][x + dx] == SAND_CLS
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                out[y][x] = SAND_CLS
    return out
