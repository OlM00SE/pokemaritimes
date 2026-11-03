"""Ledges: one-way jumps, assembled from the piece set vanilla Emerald uses on gTileset_General.

Sketch characters (the arrow points the way the player jumps; the high ground is behind it):
    v  south ledge (a horizontal row)     <  west ledge (a column)     >  east ledge (a column)
There are no north-facing ledge tiles in gTileset_General, so '^' is not offered.

Pieces (mined from the 238 vanilla gTileset_General layouts; tests/ledge_pieces.py
reconstructs every vanilla ledge from them):
    row      0D5 left end   087 middle   0D6 right end            all jump south
    column   0FE top        085 middle   106 bottom   (west)      all jump west
             0FF top        086 middle   107 bottom   (east)      all jump east
    corners  08D  column above, row going east  (west column)     solid, not jumpable
             08E  column above, row going west  (east column)
             06F  row from the west, column below (west column)
             06E  row from the east, column below (east column)
The corners make plateau outlines (Route 116) and one-tile stair steps (Routes 101 and 103).

Engine facts (field_player_avatar.c CheckForObjectEventCollision, event_object_movement.c
GetLedgeJumpDirection): moving in direction d into a tile whose behavior is MB_JUMP_<d> jumps two
tiles, whatever the ledge tile's collision. The landing tile is NOT checked by the game, so a
ledge that drops onto a tree or water is a real bug. The diagonal MB_JUMP_SOUTHEAST/SOUTHWEST
behaviours on the corner tiles match no jump predicate: corners are plain solid tiles.

Every adjacent pair of ledge cells (4-neighbourhood) is linked. A cell linked both horizontally
and vertically is a corner; which corner follows from its two links, so a corner may be drawn
with any ledge character.
"""
from . import flora

ROW ={"left": 0x0D5, "mid": 0x087, "right": 0x0D6}
COLUMN = {"W": {"top": 0x0FE, "mid": 0x085, "bottom": 0x106},
          "E": {"top": 0x0FF, "mid": 0x086, "bottom": 0x107}}
# links -> (metatile, side the column jumps to)
CORNERS = {frozenset("NE"): (0x08D, "W"), frozenset("NW"): (0x08E, "E"),
           frozenset("SW"): (0x06F, "W"), frozenset("SE"): (0x06E, "E")}

CHAR_DIR = {"v": "S", "<": "W", ">": "E"}
LEDGE_CHARS = set(CHAR_DIR)
DIRS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}

# metatile -> jump direction (None for the solid corners)
PIECE_DIR = {m: "S" for m in ROW.values()}
for _d, _set in COLUMN.items():
    PIECE_DIR.update({m: _d for m in _set.values()})
PIECE_DIR.update({m: None for m, _ in CORNERS.values()})
PIECES = set(PIECE_DIR)
LEDGE_ATTRS = (1, 0)      # vanilla: ledges are solid; elevation 0 (transition) is the most common


def piece_char(mid):
    """The sketch character that extracts a placed piece (corners extract as 'v')."""
    d = PIECE_DIR[mid]
    return {"W": "<", "E": ">"}.get(d, "v")


def verify_tileset(project, tiles):
    """The piece table assumes vanilla gTileset_General behaviours. Fail loudly if the tileset
    was edited so that a piece no longer jumps the way the table says."""
    want = {"S": "MB_JUMP_SOUTH", "W": "MB_JUMP_WEST", "E": "MB_JUMP_EAST"}
    jumps = set(want.values())
    bad = []
    for mid, d in PIECE_DIR.items():
        name = project.behavior_names.get(tiles.behavior(mid), "?")
        if (d and name != want[d]) or (d is None and name in jumps):
            bad.append(f"{mid:03X} is {name}")
    if bad:
        raise ValueError("gTileset_General ledge pieces changed: " + ", ".join(bad))


def runs_into_kept(chars, w, h, mid_at):
    """Where a ledge end has no end cap. Vanilla's 151 ledge ends: next to ground or trees there is
    always a cap (83/83); at the map edge the ledge runs off the map (4/4); against a kept '#'
    tile from the secondary tileset (a cliff or wall) it runs under it (35/35); against a primary
    object such as a boulder it is capped (26/29)."""
    def f(x, y):
        if not (0 <= x < w and 0 <= y < h):
            return True
        return chars[y][x] == "#" and mid_at(x, y) >= 512
    return f


def resolve(chars, w, h, runs_into=None):
    """chars: grid of sketch characters. Returns (pieces {(x, y): metatile}, errors [(x, y, msg)]).
    runs_into(x, y): True where a ledge end continues into a non-ledge cell without an end cap
    (default: off the map; see runs_into_kept). Only structure is judged here; what lies
    around the ledges is design_issues()' job."""
    is_l = lambda x, y: 0 <= x < w and 0 <= y < h and chars[y][x] in LEDGE_CHARS
    if runs_into is None:
        runs_into = lambda x, y: not (0 <= x < w and 0 <= y < h)
    open_ = lambda x, y, d, ln: d in ln or runs_into(x + DIRS[d][0], y + DIRS[d][1])
    links, pieces, errors, side = {}, {}, [], {}
    for y in range(h):
        for x in range(w):
            if is_l(x, y):
                links[(x, y)] = frozenset(d for d, (dx, dy) in DIRS.items() if is_l(x + dx, y + dy))
    for (x, y), ln in links.items():
        ch, hz, vt = chars[y][x], ln & {"W", "E"}, ln & {"N", "S"}
        if hz and vt:
            if ln not in CORNERS:
                errors.append((x, y, "ledges branch here (a T or + junction, or rows stacked "
                                     "against each other); a ledge cell joins at most two others"))
                continue
            pieces[(x, y)], side[(x, y)] = CORNERS[ln]
        elif vt:
            if ch == "v":
                errors.append((x, y, "'v' cells touch vertically: two south ledges stacked, or a "
                                     "side ledge drawn with 'v' (use '<' or '>' for columns)"))
                continue
            d = CHAR_DIR[ch]
            up, down = open_(x, y, "N", ln), open_(x, y, "S", ln)
            pieces[(x, y)] = COLUMN[d]["mid" if up and down else "top" if down else "bottom"]
            side[(x, y)] = d
        elif hz:
            if ch != "v":
                errors.append((x, y, f"'{ch}' is a side ledge but has no ledge above or below it; "
                                     "side ledges are columns (draw rows with 'v')"))
                continue
            left, right = open_(x, y, "W", ln), open_(x, y, "E", ln)
            pieces[(x, y)] = ROW["mid" if left and right else "left" if right else "right"]
        else:
            errors.append((x, y, "a lone ledge tile: ledges are at least two tiles long"))
    # a column (and the corners closing it) must jump one way along its whole length
    for (x, y), d in side.items():
        if (x, y + 1) in side and side[(x, y + 1)] != d:
            errors.append((x, y, f"this column jumps {d} but the cell below jumps {side[(x, y + 1)]} "
                                 "(check the '<'/'>' characters and the corner shape)"))
    return pieces, sorted(set(errors))


WALKABLE = {"G", "TG", "P", "SA"}


def design_issues(cls, pieces, w, h, kept_walkable=None):
    """cls: final class grid (after grammar repair and tree placement). Returns (errors, warnings)
    as [(x, y, msg)]. Landing is checked strictly because the game never checks it.
    kept_walkable(x, y): whether the block a '#' cell keeps can be stood on (collision 0, not
    water), e.g. mountain ground or flowers. Without it, '#' counts as solid."""
    errors, warnings = [], []
    name = {"T": "a tree", "TL": "a tree", "TR": "a tree", "BL": "a tree", "BR": "a tree",
            "S": "water", "W": "water", "F": "a solid kept '#' tile", "LD": "another ledge",
            "RK": "a rock", **flora.NAMES}
    ok = lambda x, y: cls[y][x] in WALKABLE or (cls[y][x] == "F" and kept_walkable and kept_walkable(x, y))
    for (x, y), mid in sorted(pieces.items()):
        d = PIECE_DIR[mid]
        if d is None:
            continue
        dx, dy = DIRS[d]
        lx, ly, ax, ay = x + dx, y + dy, x - dx, y - dy
        if 0 <= ax < w and 0 <= ay < h and not ok(ax, ay):
            # nobody can stand on the high side, so the jump never happens (vanilla's cliff
            # ledges on Route 118 are like this): decoration, not a bug
            warnings.append((x, y, f"nothing walkable on the high side ({ax},{ay}); this tile can "
                                   "never be jumped"))
            continue
        if not (0 <= lx < w and 0 <= ly < h):
            errors.append((x, y, f"jumping {d} lands off the map at ({lx},{ly})"))
        elif not ok(lx, ly):
            errors.append((x, y, f"jumping {d} lands on {name.get(cls[ly][lx], cls[ly][lx])} at ({lx},{ly})"))
    return errors, warnings
