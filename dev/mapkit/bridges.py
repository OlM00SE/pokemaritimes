"""Bridges: a plank bridge carrying a road north-south over river water, from vanilla's pieces.

Vanilla's plank bridge is Route 104's (gTileset_Rustboro). Its vertical deck is two columns of
planks drawn over water, opaque from edge to edge:

    350 351    the north end: the deck over the water row that carries the bank
    34E 34F    the deck over open water
    001 001    the grass below the last row has no bank under the deck (002 beside it)

The deck is walkable at elevation 3 with MB_REFLECTION_UNDER_BRIDGE (the player's reflection
shows in the deck below); it isn't water, so Surf can't pass under it, as on Route 104.

On another secondary tileset the pieces must first be copied in (`dev/tile_import.py bridge
<tileset> --apply`, mapkit/tileimport.py): the art is vanilla's, appended, nothing moves.

Sketch side: draw 'H' over the water where the road crosses, a strip exactly two columns wide
covering every water row of the crossing. For everything else (shores, the grammar, the learned
rules) 'H' is water, so the banks run on beside and under the deck. Refused, naming the cells:
  * a strip that isn't two columns wide, or whose rows don't line up;
  * a crossing where the river doesn't run east-west: the top row must be water with the bank
    to its north and water on both sides (piece 189), the other rows open water (170);
  * no grass (or kept '#') at either end: the road meets the deck across a grass margin, as it
    meets water;
  * a tileset that doesn't have the pieces yet.
"""
from . import shores

CHAR = "H"
SOURCE = "gTileset_Rustboro"
NORTH = (0x350, 0x351)           # (left, right) in SOURCE's numbering
DECK = (0x34E, 0x34F)
SOURCE_PIECES = NORTH + DECK
ATTRS = (0, 3)                   # walkable, elevation 3 (vanilla Route 104)
PLAIN_GRASS = 0x001
ENDS = {"G", "F"}                # what may stand at either end of the deck


def piece_ids(project, layout):
    """{source id: id in this layout's tileset pair} if the layout's secondary has every bridge
    piece (or is SOURCE itself); else (None, message)."""
    from .tileimport import plan, CACHE
    if layout.secondary == SOURCE:
        return {m: m for m in SOURCE_PIECES}, None
    cache = project.__dict__.setdefault(CACHE, {})
    key = ("bridge", layout.secondary)
    if key not in cache:
        pl = plan(project, SOURCE, list(SOURCE_PIECES), layout.secondary)
        if pl.problems:
            cache[key] = None, f"bridge pieces can't be used on {layout.secondary}: {'; '.join(pl.problems)}"
        elif pl.changes:
            cache[key] = None, (f"{layout.secondary} doesn't have the bridge pieces yet: "
                                f"run dev/tile_import.py bridge {layout.secondary} --apply")
        else:
            cache[key] = dict(pl.mapping), None
    return cache[key]


def resolve(cls, cells, w, h, ends=None):
    """cls: final class grid as the shores see it, in which every bridge cell reads as water.
    cells: the sketch's 'H' cells. ends: the class grid the deck's ends are judged on (default
    cls; the compiler passes the one where flowers aren't grass). Returns ({(x, y): source
    piece}, {(x, y): PLAIN_GRASS} for the grass below each deck, errors)."""
    ends = ends or cls
    pieces, below, errors = {}, {}, []
    seen = set()
    for start in sorted(cells, key=lambda c: (c[1], c[0])):
        if start in seen:
            continue
        group, stack = set(), [start]
        while stack:
            c = stack.pop()
            if c in group or c not in cells:
                continue
            group.add(c)
            x, y = c
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        seen |= group
        xs = sorted({x for x, _ in group})
        ys = sorted({y for _, y in group})
        rect = {(x, y) for x in range(xs[0], xs[-1] + 1) for y in range(ys[0], ys[-1] + 1)}
        if len(xs) != 2 or xs[1] != xs[0] + 1 or group != rect:
            errors += [(x, y, "a bridge is a strip of 'H' exactly two columns wide, its rows lined up")
                       for x, y in sorted(group)]
            continue
        x0, top, bottom = xs[0], ys[0], ys[-1]
        for y in ys:
            for k, x in enumerate(xs):
                piece, err = shores.water_piece(cls, x, y, w, h)
                want = shores.BANK["N"] if y == top else shores.OPEN_WATER
                if err or piece != want:
                    where = "with the bank to its north" if y == top else "open water"
                    errors.append((x, y, f"a bridge crosses a river running east-west: this cell "
                                         f"must be {where}, water on both sides"))
                    continue
                pieces[(x, y)] = (NORTH if y == top else DECK)[k]
        for x in xs:
            for y, end in ((top - 1, "north"), (bottom + 1, "south")):
                c = ends[y][x] if 0 <= y < h else None
                if c not in ENDS:
                    errors.append((x, y, f"the bridge's {end} end needs grass (the road's margin "
                                         "from the water) or a kept '#' cell"))
                elif end == "south" and c == "G":
                    below[(x, y)] = PLAIN_GRASS
    return pieces, below, sorted(set(errors))
