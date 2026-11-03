"""Flora and ground accents on gTileset_General, placed by shape like ledges and shores.

Mined from the 238 vanilla layouts (numbers in design/mapping_reference.md section 11):

  sketch  piece      tiles                                         collision
  *       flowers    004                                           walkable
  b       boulder    0E0 (a rock on grass)                         solid
  y       sapling    a vertical run of 2 or 3 'y':                 crown top walkable, the rest solid
                       2: 00E crown / 017 trunk
                       3: 00E crown / 0C6 crown middle / 017 trunk
                     (Route 116's young grove. 00E is drawn over the player, so you walk "behind"
                     the crown; vanilla's taller stacks are Route 119's jungle hedges.)
  s       sign post  003 (vanilla's route sign; the text is a sign       solid
                     event, placed with dev/events.py)

Every piece stands on plain grass. In the compile, flora cells read as grass for the learned
rules, so they never change a neighbour's tile (vanilla's neighbours of these tiles are plain
grass 001 in most cases). A piece is refused where grass in that spot would not be plain grass:
under a tree's canopy overhang (1CE/1CF), on the bank below water (002), or where the rules pick
any other edge tile. The compiler names the cells, as it does for ledges and shores.
"""

FLOWER, BOULDER, SIGN = 0x004, 0x0E0, 0x003
CROWN, CROWN_MID, TRUNK = 0x00E, 0x0C6, 0x017
PLAIN_GRASS = 0x001

CHAR_CLASS = {"*": "FL", "b": "BO", "y": "SP", "s": "SN"}
CLASS_CHAR = {v: k for k, v in CHAR_CLASS.items()}
CLASSES = set(CHAR_CLASS.values())
# collision, elevation: ground level like the grass around them; solid pieces block
# (vanilla's route signs: 103 of 117 stand at elevation 0)
ATTRS = {FLOWER: (0, 3), BOULDER: (1, 3), CROWN: (0, 3), CROWN_MID: (1, 0), TRUNK: (1, 0), SIGN: (1, 0)}
WALKABLE_PIECES = {FLOWER, CROWN}
PIECES = set(ATTRS)
NAMES = {"FL": "flowers", "BO": "a boulder", "SP": "a sapling", "SN": "a sign post"}
SINGLE = {"FL": FLOWER, "BO": BOULDER, "SN": SIGN}           # one-tile pieces
PIECE_CLASS = {FLOWER: "FL", BOULDER: "BO", SIGN: "SN", CROWN: "SP", CROWN_MID: "SP", TRUNK: "SP"}
MAX_SAPLING = 3


def sapling_column(n):
    """Tiles of an n-tall sapling, top to bottom (n is 2 or 3)."""
    return [CROWN] + [CROWN_MID] * (n - 2) + [TRUNK]


def resolve(cls, w, h):
    """cls: final class grid. Returns ({(x, y): metatile}, errors [(x, y, msg)])."""
    pieces, errors = {}, []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c in SINGLE:
                pieces[(x, y)] = SINGLE[c]
            elif c == "SP" and (y == 0 or cls[y - 1][x] != "SP"):
                n = 1
                while y + n < h and cls[y + n][x] == "SP":
                    n += 1
                if n < 2 or n > MAX_SAPLING:
                    errors.append((x, y, f"a sapling is a vertical run of 2 or 3 'y' (crown over "
                                         f"trunk), not {n}"))
                    continue
                if y + n == h:
                    errors.append((x, y, "a sapling's trunk can't sit on the map's bottom edge "
                                         "(nothing to stand on below it)"))
                for i, mid in enumerate(sapling_column(n)):
                    pieces[(x, y + i)] = mid
    return pieces, errors


def grass_view(cls):
    """Copy of cls in which every flora cell reads as grass ('G'), for the learned rules and the
    shore resolver: the pieces sit on plain grass and don't change their neighbours."""
    return [["G" if c in CLASSES else c for c in row] for row in cls]


def walk_view(cls, pieces):
    """Copy of cls for the ledge landing check: walkable pieces (flowers, a sapling's crown top)
    read as grass; solid ones keep their class, which the ledge check names."""
    out = [row[:] for row in cls]
    for (x, y), mid in pieces.items():
        if mid in WALKABLE_PIECES:
            out[y][x] = "G"
    return out


def placement_errors(pieces, learned):
    """Refuse pieces where grass wouldn't be plain grass. learned[y][x] is the tile the rules and
    the shore resolver give the cell when it reads as grass."""
    errors = []
    for (x, y), mid in sorted(pieces.items()):
        if learned[y][x] != PLAIN_GRASS:
            what = NAMES[PIECE_CLASS[mid]]
            errors.append((x, y, f"{what} must stand on plain grass, but this spot gets edge tile "
                                 f"{learned[y][x]:03X} (a tree's canopy, a bank, a path rim...); "
                                 "move it a tile away"))
    return errors


def extract_chars(mid_at, w, h):
    """Existing map -> {(x, y): sketch char} for every cell that is exactly a flora piece:
    flowers, boulders, and whole sapling columns (00E [0C6] 017). Partial or taller columns
    aren't returned (they stay '#')."""
    out = {}
    for y in range(h):
        for x in range(w):
            m = mid_at(x, y)
            if m == FLOWER:
                out[(x, y)] = "*"
            elif m == BOULDER:
                out[(x, y)] = "b"
            elif m == SIGN:
                out[(x, y)] = "s"
            elif m == CROWN and out.get((x, y - 1)) != "y":     # (a run can't touch another)
                for n in range(2, MAX_SAPLING + 1):
                    if y + n <= h and [mid_at(x, y + i) for i in range(n)] == sapling_column(n):
                        # the run must end here: the tile below can't continue the column
                        if y + n < h and mid_at(x, y + n) in (CROWN_MID, TRUNK, 0x016):
                            continue
                        for i in range(n):
                            out[(x, y + i)] = "y"
                        break
    return out
