"""Cliffs: terraces with rock walls, built from vanilla gTileset_General's brown rock family (the
pieces Routes 104, 116 and 120 draw their bluffs and plateaus with).

Sketch characters:
    ^  a cliff wall cell (solid)
    %  stairs up a south face (walkable; one or two columns wide)
Levels: every sketch cell has a level, 0-9 (Sketch.levels; `// level:` lines in the sketch file).
Levels are a design notion: walkable ground stays at elevation 3 everywhere, and walls block by
collision. A wall belongs to the terrace it bounds, so its level is its high side's. Around a
wall cell at level L, each neighbour is
    low    ground (anything but a wall or stairs) below L, or a wall or stairs below L
    high   ground at L or above, or a wall above L (a higher terrace standing right behind)
    wall   a wall or stairs at L. Off the map counts as wall: the wall runs off the map.

Pieces (the camera looks north, so a terrace shows a face on its south side, a rim on its north
side and a narrow wall on each flank). By the wall cell's four neighbours, then its diagonals:
    low N          rim               068 (low W too)   069   06A (low E too)
    low W          west flank        070               078 (low S too: the foot's corner)
    low E          east flank        072               07A (low S too)
    low S          face, 1 row       079               face bottom 091 (a wall above)
    no low N/S/W/E, one low diagonal  (the inside corners)
                   NW 0BE   NE 0BF   SW 089   SE 074
    no low anywhere  (a face taller than one row)  top 07C (high above), middle 0A9
So a face is as many rows as the sketch draws `^` (07C, 0A9..., 091; 079 alone). Beside a flank a
tall face's top is 07B (west) / 07D (east), as vanilla's are; vanilla never stands a middle row
against a flank, so a face of three rows or more must end in an inside corner or off the map.
Stairs replace the face in one or two columns: 0AF, or 0AF 0CF.

Every adjacency these rules can produce is one vanilla uses (tests/cliff_pieces.py checks it
against the corpus). Mined from 238 vanilla layouts: walls are collision 1, elevation 0 (the
modal attributes of every piece); stairs 0AF/0CF are walkable at elevation 3.

The rules level_issues() enforces: walkable ground changes level only through a wall, a ledge,
stairs, or along a road (a graded road: two path cells may differ in level, which is how a road
climbs through a cutting in a wall). A wall never touches water (a tile of ground at its foot:
cliffs straight into water aren't vocabulary yet).
"""
WALL, STAIRS = "^", "%"
CHARS = {WALL, STAIRS}
CLS = {WALL: "CL", STAIRS: "ST"}
CLASSES = set(CLS.values())

RIM, RIM_NW, RIM_NE = 0x069, 0x068, 0x06A
FLANK_W, FLANK_E, FOOT_W, FOOT_E = 0x070, 0x072, 0x078, 0x07A
FACE1, FACE_TOP, FACE_MID, FACE_BOTTOM = 0x079, 0x07C, 0x0A9, 0x091
FACE_TOP_W, FACE_TOP_E = 0x07B, 0x07D       # a tall face's top beside the west / east flank
INNER = {"NW": 0x0BE, "NE": 0x0BF, "SW": 0x089, "SE": 0x074}
STAIR_L, STAIR_R = 0x0AF, 0x0CF
WALL_PIECES = {RIM, RIM_NW, RIM_NE, FLANK_W, FLANK_E, FOOT_W, FOOT_E, FACE1, FACE_TOP, FACE_TOP_W,
               FACE_TOP_E, FACE_MID, FACE_BOTTOM, *INNER.values()}
FACES = {FACE1, FACE_TOP, FACE_TOP_W, FACE_TOP_E, FACE_MID, FACE_BOTTOM}
STAIR_PIECES = {STAIR_L, STAIR_R}
PIECES = WALL_PIECES | STAIR_PIECES
WALL_ATTRS = (1, 0)
STAIR_ATTRS = (0, 3)
NAMES = {"CL": "a cliff wall", "ST": "stairs"}

DIRS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIAG = {"NW": (-1, -1), "NE": (1, -1), "SW": (-1, 1), "SE": (1, 1)}
WALKABLE = {"G", "TG", "P", "SA", "FL"}          # final classes a player stands on
WATERY = {"S", "W", "RK"}                         # water, pond, water rocks (bridges read as S)


def zero_levels(w, h):
    return [[0] * w for _ in range(h)]


def neighbour(chars, levels, w, h, x, y, L):
    """'low', 'high' or 'wall' for the cell at (x, y), seen from a wall at level L."""
    if not (0 <= x < w and 0 <= y < h):
        return "wall"
    lv = levels[y][x]
    if chars[y][x] in CHARS:
        return "wall" if lv == L else ("high" if lv > L else "low")
    return "high" if lv >= L else "low"


def piece_for(n, d):
    """n: {N, S, W, E: kind}, d: {NW, NE, SW, SE: kind}. Returns (metatile, None) or (None, why)."""
    low = {k for k, v in n.items() if v == "low"}
    if {"N", "S"} <= low or {"W", "E"} <= low:
        return None, "low ground on both sides of a one-tile wall: walls need high ground on one side"
    if "N" in low:
        return (RIM_NW if "W" in low else RIM_NE if "E" in low else RIM), None
    if "W" in low:
        return (FOOT_W if "S" in low else FLANK_W), None
    if "E" in low:
        return (FOOT_E if "S" in low else FLANK_E), None
    if "S" in low:
        return (FACE_BOTTOM if n["N"] == "wall" else FACE1), None
    dlow = [k for k, v in d.items() if v == "low"]
    if len(dlow) > 1:
        return None, f"low ground on {len(dlow)} diagonals ({', '.join(dlow)}): the wall is pinched here"
    if dlow:
        return INNER[dlow[0]], None
    if n["S"] != "wall":
        return None, "no low ground beside this wall (a wall inside its own terrace?)"
    return (FACE_TOP if n["N"] == "high" else FACE_MID), None


def resolve(chars, levels, w, h):
    """chars: grid of sketch characters; levels: grid of ints. Returns (pieces {(x, y): metatile},
    errors [(x, y, msg)]). Walls by their neighbours (piece_for); stairs by their run's width."""
    pieces, errors = {}, []
    for y in range(h):
        for x in range(w):
            if chars[y][x] != WALL:
                continue
            L = levels[y][x]
            kind = lambda dx, dy: neighbour(chars, levels, w, h, x + dx, y + dy, L)
            n = {k: kind(*v) for k, v in DIRS.items()}
            d = {k: kind(*v) for k, v in DIAG.items()}
            mid, why = piece_for(n, d)
            if why:
                errors.append((x, y, why))
            else:
                pieces[(x, y)] = mid
    # a tall face beside a flank: vanilla tops it with 07B (west) / 07D (east), never 07C, and
    # never stands a middle row (0A9) against a flank
    for (x, y), mid in list(pieces.items()):
        west, east = pieces.get((x - 1, y)) == FLANK_W, pieces.get((x + 1, y)) == FLANK_E
        if mid == FACE_TOP and (west or east):
            if west and east:
                errors.append((x, y, "a face taller than one row needs two columns or more between "
                                     "its flanks"))
            pieces[(x, y)] = FACE_TOP_W if west else FACE_TOP_E
        elif mid == FACE_MID and (west or east):
            errors.append((x, y, "a face more than two rows tall can't end against a flank "
                                 "(vanilla has no piece for it): make it two rows there, or end it "
                                 "in an inside corner or off the map"))
    is_st = lambda x, y: 0 <= x < w and 0 <= y < h and chars[y][x] == STAIRS
    for y in range(h):
        for x in range(w):
            if not is_st(x, y):
                continue
            L = levels[y][x]
            if is_st(x - 1, y) and is_st(x - 2, y) or is_st(x + 1, y) and is_st(x + 2, y):
                errors.append((x, y, "stairs are one or two columns wide"))
                continue
            pieces[(x, y)] = STAIR_R if is_st(x - 1, y) else STAIR_L
            for dx in (-1, 1):
                nx = x + dx
                if is_st(nx, y):
                    if levels[y][nx] != L:
                        errors.append((x, y, "stairs side by side at different levels"))
                    continue
                if not (0 <= nx < w) or chars[y][nx] != WALL or levels[y][nx] != L:
                    errors.append((x, y, "stairs need the face's wall on both sides, at the stairs' level "
                                         "(they cut through a south face)"))
    # a stair column must run from high ground above to lower ground below
    for y in range(h):
        for x in range(w):
            if is_st(x, y) and not is_st(x, y - 1):
                L = levels[y][x]
                y1 = y
                while is_st(x, y1 + 1):
                    if levels[y1 + 1][x] != L:
                        errors.append((x, y1 + 1, "a stair column changes level part way"))
                    y1 += 1
                if y == 0 or chars[y - 1][x] in CHARS or levels[y - 1][x] < L:
                    errors.append((x, y, f"the top of the stairs needs ground at level {L} or above "
                                         "above it"))
                if y1 == h - 1 or chars[y1 + 1][x] in CHARS or levels[y1 + 1][x] >= L:
                    errors.append((x, y1, f"the foot of the stairs needs ground below level {L} "
                                          "under it"))
    # the faces beside stairs: a stair cell's wall neighbours must be faces
    for (x, y), mid in list(pieces.items()):
        if mid in STAIR_PIECES:
            for dx in (-1, 1):
                m = pieces.get((x + dx, y))
                if m is not None and m not in FACES and m not in STAIR_PIECES:
                    errors.append((x, y, "stairs climb a south face only (not a rim, a flank or a corner)"))
                    break
    return pieces, sorted(set(errors))


def level_issues(cls, levels, w, h):
    """Errors [(x, y, msg)] where the terrain contradicts the levels: walkable cells side by side
    at different levels (unless both are road: a graded road), or a wall touching water.
    cls: the final class grid (after grammar repair, trees and flora)."""
    errors = []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx >= w or ny >= h:
                    continue
                o = cls[ny][nx]
                if c in WALKABLE and o in WALKABLE and levels[y][x] != levels[ny][nx] \
                        and not (c == "P" and o == "P"):
                    errors.append((x, y, f"level {levels[y][x]} meets level {levels[ny][nx]} at "
                                         f"({nx},{ny}) on open ground: put a wall (^), a ledge or "
                                         "stairs between them, or a road through a cutting"))
            if c in CLASSES:
                for dx, dy in DIRS.values():
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and cls[ny][nx] in WATERY:
                        errors.append((x, y, "a cliff touches water: leave a tile of ground at its "
                                             "foot (cliffs straight into water aren't vocabulary yet)"))
                        break
    return errors


def runs_into(chars, w, h, base):
    """A ledge's runs_into predicate (ledges.resolve) that also lets a ledge end run under a cliff
    wall or stairs, as vanilla's ledges run under the cliffs they meet."""
    return lambda x, y: base(x, y) or (0 <= x < w and 0 <= y < h and chars[y][x] in CHARS)


def verify_tileset(project, tiles):
    """The pieces are vanilla gTileset_General's; fail loudly if one stopped being what the table
    assumes (a wall that turned into a ledge or water is a hole in every cliff). Walls are plain
    solid tiles in vanilla (MB_NORMAL, or MB_MOUNTAIN_TOP on rims and corners); stairs MB_NORMAL."""
    bad = []
    for mid in sorted(PIECES):
        name = project.behavior_names.get(tiles.behavior(mid), "?")
        ok = {"MB_NORMAL"} if mid in STAIR_PIECES else {"MB_NORMAL", "MB_MOUNTAIN_TOP"}
        if name not in ok:
            bad.append(f"{mid:03X} is {name}")
    if bad:
        raise ValueError("gTileset_General cliff pieces changed: " + ", ".join(bad))
