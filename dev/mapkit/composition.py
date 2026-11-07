"""Visual rules: what makes a map read as a natural Pokémon landscape, measured on vanilla's maps.

The piece kits (ledges, shores, cliffs, flora, bridges) and the learned rules make each cell a
metatile vanilla would use in that neighbourhood. They don't judge what the eye judges at a few
tiles' or a screen's distance: a sapling squeezed against a tree, a bank that steps down in a
perfectly regular staircase, a rectangle of tall grass floating in a lawn, a screen of nothing
but grass. This module measures those, and compares each number with what vanilla Emerald's own
maps do (design/mapping_reference.md section 18 has the findings).

Three tiers:

  strict   `pairs`: two metatiles side by side that vanilla never draws in that direction (both
           pieces General's, each one vanilla uses). Vanilla's 238 General layouts are the
           evidence, so a pair it never drew is almost always a visible seam: a cut tree, a cap
           with no tree under it, a sapling against a tree. A pairing judged right in renders and
           in-game goes in JUDGED with its reason. (Pairs across a map's edges are seams.py's.)
  context  rules about a feature and what surrounds it, with vanilla's numbers: staircases (a
           bank or forest edge repeating one step), tall grass against cover, free-standing tree
           rows, flower beds.
  screen   composition at the scale the player sees, the GBA screen (15 x 10 tiles): screens of
           bare grass, open space, straight edges.

Strict findings are warnings in the checker. Context and screen rules are guides: each is
reported against vanilla's band (p10..p90, and min/max) for the map's kind (route or town),
`unusual` outside the band, `beyond` past anything vanilla does. A design that means it (a
hay field is a rectangle on purpose) says so in its sketch: `// accept: grass_rect: why`.
The bands are calibrated from the corpus (`dev/terrain_report.py --calibrate`) and saved in
composition_bands.json, so the numbers can be reproduced and reviewed.
"""
import json, os
from collections import Counter
from .corpus import key_of
from .project import NUM_METATILES_IN_PRIMARY, TILE_FLAG_SURFABLE, TILE_FLAG_HAS_ENCOUNTERS
from .terrain import TREE, PRIMARY, PATH, SAND
from . import cliffs, flora, ledges, shores

BANDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "composition_bands.json")
SCREEN = (15, 10)            # the GBA screen in tiles (the player's tile with 7 columns each side)
SCREEN_STEP = 5
TREE_IDS = set().union(*TREE.values())
SAPLING_IDS = {flora.CROWN, flora.CROWN_MID, flora.TRUNK}
# vanilla's tall-tree forest (Routes 110, 117, 119, 120, 123): sapling pieces stacked into columns,
# 00E/00F crowns over 0C6/0C7 over 016/017. For composition it is forest like the 2x2 trees.
TALL_TREE_IDS = {0x00E, 0x00F, 0x0C6, 0x0C7, 0x016, 0x017}
FOREST_IDS = TREE_IDS | TALL_TREE_IDS
FLOWER_IDS = {flora.FLOWER}
BOULDER_IDS = {0x0E0, 0x0E1, 0x0E2}
OUTDOOR = {"MAP_TYPE_ROUTE", "MAP_TYPE_TOWN", "MAP_TYPE_CITY", "MAP_TYPE_OCEAN_ROUTE"}
TOWN_TYPES = {"MAP_TYPE_TOWN", "MAP_TYPE_CITY"}


# ------------------------------------------------------------------------------ strict: pairs ----
DIRS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
# Pairings vanilla never draws that are judged right, with the reason. (piece, direction, neighbour):
# the neighbour lies in that direction from the piece. Listed pairing by pairing, so a new joint
# still shows. The cliff entries were judged in edges-cliffs-v2 (dev/out/edges_cliffs/ground_pairs.png).
CUTTING = "a graded road's cutting: the wall ends beside the road a level down"
CORNER = "a terrace's corner or a face's top beside its flank, with the terrace's grass behind it"
JUDGED = {
    (0x068, "S", 0x001): CUTTING, (0x068, "S", 0x003): CUTTING, (0x06A, "S", 0x001): CUTTING,
    (0x070, "N", 0x001): CUTTING, (0x072, "N", 0x001): CUTTING, (0x06A, "W", 0x001): CORNER,
    (0x07A, "W", 0x001): CORNER, (0x07B, "N", 0x001): CORNER, (0x07D, "N", 0x001): CORNER,
    (0x07C, "E", 0x001): CORNER, (0x07C, "W", 0x001): CORNER,
    (0x002, "N", 0x004): "the line under a flower tuft's grass", (0x0D4, "N", 0x004): "the same",
    (0x0D3, "N", 0x002): "the line under the river bank's grass (002 there is walkable shore grass)",
    (0x0D4, "N", 0x002): "the same",
    (0x07A, "S", 0x1CF): "the cap of a tree row standing below a foot corner",
}
# By the neighbour's kind, still per piece and side (any variant of that kind).
TREE_BY_WALL = "a tree's variant beside a wall (the rules read the wall as grass)"
LEDGE_UNDER = "a ledge's end running under the wall (M17)"
ROAD_CUT = "a road's edge tile beside the wall of its cutting"
JUDGED_KINDS = {
    (0x002, "S", "TL"): TREE_BY_WALL, (0x002, "S", "TR"): TREE_BY_WALL, (0x002, "W", "BR"): TREE_BY_WALL,
    (0x06A, "E", "BL"): TREE_BY_WALL, (0x079, "N", "BR"): TREE_BY_WALL, (0x07B, "N", "BL"): TREE_BY_WALL,
    (0x07C, "E", "BL"): TREE_BY_WALL, (0x091, "S", "TL"): TREE_BY_WALL, (0x091, "S", "TR"): TREE_BY_WALL,
    (0x0D3, "S", "TL"): TREE_BY_WALL, (0x0D4, "S", "TR"): TREE_BY_WALL,
    (0x072, "N", "LD"): LEDGE_UNDER, (0x072, "S", "LD"): LEDGE_UNDER, (0x079, "E", "LD"): LEDGE_UNDER,
    (0x079, "W", "LD"): LEDGE_UNDER,
    (0x068, "W", "P"): ROAD_CUT, (0x06A, "E", "P"): ROAD_CUT, (0x06A, "N", "P"): ROAD_CUT,
    (0x072, "E", "P"): ROAD_CUT,
    # terrain-rules (dev/out/terrain/, judged on the corridor maps' renders)
    ("BLD", "S", "P"): "a building's front over the path to its door (stamps stand on lawns in "
                       "vanilla; the path's rim runs under the wall, as a doormat's would)",
    (flora.SIGN, "E", "P"): "a sign post at the road's edge", (flora.SIGN, "W", "P"): "the same",
    (flora.SIGN, "S", "P"): "the same", (flora.SIGN, "N", "P"): "the same",
    **{(0x0E0, d, cap): "a boulder tucked against the woods, beside the grass over a tree's crown"
       for d in "NSWE" for cap in (0x1CE, 0x1CF)},
    **{("P", d, cap): "a path's edge beside the grass over a tree's crown"
       for d in "WE" for cap in (0x1CE, 0x1CF)},
}
_BUILDINGS = []


def building_ids():
    """General's building pieces: every primary metatile of a stamp in the catalog (stamps.toml)."""
    if not _BUILDINGS:
        from .project import Project
        from . import stamps
        _BUILDINGS.append({b & 0x3FF for s in stamps.catalog(Project()).values() for b in s.cells.values()
                           if b & 0x3FF < NUM_METATILES_IN_PRIMARY})
    return _BUILDINGS[0]


def kind(mid):
    """The piece's kind for JUDGED_KINDS: a tree quarter (TL TR BL BR), LD a ledge, P a light path
    tile, BLD a building piece, else None."""
    for q, ids in TREE.items():
        if mid in ids:
            return q
    if mid in ledges.PIECES:
        return "LD"
    if mid in PATH:
        return "P"
    if mid in building_ids():
        return "BLD"
    return None


def family(mid):
    """A designer's name for a General metatile, for messages."""
    if mid in TREE_IDS:
        return "tree"
    if mid in (0x1CE, 0x1CF):
        return "tree cap"
    if mid in SAPLING_IDS or mid in TALL_TREE_IDS:
        return "sapling"
    if mid in FLOWER_IDS:
        return "flowers"
    if mid in BOULDER_IDS:
        return "boulder"
    if mid == flora.SIGN:
        return "sign"
    if mid == 0x001:
        return "grass"
    if mid == 0x002:
        return "bank grass"          # the grass below water; also the terrace line's middle
    if mid in building_ids():
        return "building"
    if mid in cliffs.LINE_PIECES:
        return "terrace line"
    if mid in cliffs.FAMILY:
        return "cliff"
    if mid in ledges.PIECES:
        return "ledge"
    if mid in shores.ALL_PIECES or mid in shores.GRASS_BANK_TILES:
        return "bank"
    if mid in PATH:
        return "path"
    if mid in SAND:
        return "sand"
    if mid in (0x00D, 0x1C6, 0x1C7):        # (1C6/1C7: tall grass under a canopy)
        return "tall grass"
    if mid >= NUM_METATILES_IN_PRIMARY:
        return "secondary"
    return f"{mid:03X}"


def is_judged(a, d, b):
    """(reason or None) for the pairing: piece a with neighbour b in direction d."""
    for p, dd, q in ((a, d, b), (b, OPPOSITE[d], a)):
        for key in ((p, dd, q), (p, dd, kind(q)), (kind(p), dd, q), (kind(p), dd, kind(q))):
            why = JUDGED.get(key) or JUDGED_KINDS.get(key)
            if why:
                return why
    return None


OPPOSITE = {"N": "S", "S": "N", "W": "E", "E": "W"}


def odd_pairs(corpus, layout, judged=True):
    """Pairs of General metatiles side by side inside the map that vanilla never draws in that
    direction: [(x, y, d, a, b)], b being the neighbour of (x, y) in direction d (E or S, so each
    pair is listed once). Only pairs whose two pieces vanilla uses on some map are judged: a
    secondary tile or an imported one has no evidence either way. judged: leave out JUDGED."""
    L = layout
    if L.primary != PRIMARY:
        return []
    seen = lambda m: (PRIMARY, m) in corpus.attrs
    out = []
    for y in range(L.height):
        for x in range(L.width):
            a = L.mid(x, y)
            if a >= NUM_METATILES_IN_PRIMARY or not seen(a):
                continue
            for d, (dx, dy) in (("E", (1, 0)), ("S", (0, 1))):
                nx, ny = x + dx, y + dy
                if not L.inb(nx, ny):
                    continue
                b = L.mid(nx, ny)
                if b >= NUM_METATILES_IN_PRIMARY or not seen(b):
                    continue
                if corpus.neigh.get(key_of(L.entry, a), {}).get(d, {}).get(key_of(L.entry, b), 0):
                    continue
                if judged and is_judged(a, d, b):
                    continue
                out.append((x, y, d, a, b))
    return out


def describe_pairs(pairs, limit=6):
    """'sapling | tree x4 at (3,10)...' grouped by the two families, most common first."""
    groups = {}
    for x, y, d, a, b in pairs:
        sep = "|" if d == "E" else "/"
        groups.setdefault(f"{family(a)} {sep} {family(b)}", []).append((x, y, a, b))
    out = []
    for name, cells in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:limit]:
        x, y, a, b = cells[0]
        out.append(f"{name} x{len(cells)} (e.g. ({x},{y}) {a:03X}{'|' if '|' in name else '/'}{b:03X})")
    return out


# ------------------------------------------------------------------------------ the feature grid --
class Features:
    """A map's cells as the eye reads them: F forest (2x2 trees, saplings, tall trees), W water
    (anything surfable, banks included), TG tall grass, X another solid tile (cliffs, rocks,
    buildings, ledges), G plain grass (001), O other walkable ground (paths, flowers, edges)."""

    def __init__(self, project, layout, map_type="MAP_TYPE_ROUTE"):
        self.L, self.w, self.h = layout, layout.width, layout.height
        self.town = map_type in TOWN_TYPES
        tp = layout.tiles
        general = layout.primary == PRIMARY
        self.g = []
        for y in range(self.h):
            row = []
            for x in range(self.w):
                m = layout.mid(x, y)
                fl = project.tile_flags.get(tp.behavior(m), 0)
                if general and m in FOREST_IDS:
                    c = "F"
                elif fl & TILE_FLAG_SURFABLE:
                    c = "W"
                elif fl & TILE_FLAG_HAS_ENCOUNTERS:
                    c = "TG"
                elif layout.coll(x, y):
                    c = "X"
                elif general and m == 0x001:
                    c = "G"
                else:
                    c = "O"
                row.append(c)
            self.g.append(row)

    def inm(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def at(self, x, y):
        return self.g[y][x] if self.inm(x, y) else None

    def mask(self, *classes):
        return lambda x, y: self.inm(x, y) and self.g[y][x] in classes

    def mid_mask(self, ids):
        return lambda x, y: self.inm(x, y) and self.L.primary == PRIMARY and self.L.mid(x, y) in ids

    def count(self, *classes):
        return sum(1 for row in self.g for c in row if c in classes)


WALK = ("G", "O", "TG")
COVER = ("F", "X", "W")


def components(mask, w, h):
    seen, out = set(), []
    for y in range(h):
        for x in range(w):
            if mask(x, y) and (x, y) not in seen:
                comp, stack = [], [(x, y)]
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if (nx, ny) not in seen and mask(nx, ny):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                out.append(comp)
    return out


# --------------------------------------------------------------------------- context rules ----
def staircase(f, mask):
    """The longest mechanical staircase on the outline of `mask`: convex corners of one
    orientation, each the same step (1-3 across, 1-3 down) from the last. Rasterised diagonals
    (a river drawn straight from map data) make long ones; vanilla's edges vary their steps.
    Returns (corners in the chain, its cells)."""
    w, h = f.w, f.h
    best, best_cells = 0, []
    for ox, oy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        corners = {(x, y) for y in range(h) for x in range(w)
                   if mask(x, y) and f.inm(x + ox, y) and f.inm(x, y + oy)
                   and not mask(x + ox, y) and not mask(x, y + oy)}
        for (x, y) in corners:
            for sx in (1, 2, 3):
                for sy in (1, 2, 3):
                    # the next corner lies along the outline: away from the open side on one axis
                    for dx, dy in ((-sx * ox, sy * oy), (sx * ox, -sy * oy)):
                        if (x - dx, y - dy) in corners:
                            continue                # not the chain's first corner
                        chain = [(x, y)]
                        while (chain[-1][0] + dx, chain[-1][1] + dy) in corners:
                            chain.append((chain[-1][0] + dx, chain[-1][1] + dy))
                        if len(chain) > best:
                            best, best_cells = len(chain), chain
    return best, best_cells


def straight_edge(f, mask):
    """The longest straight run of `mask` cells facing walkable ground along one side.
    Returns (length, cells)."""
    walk = f.mask(*WALK)
    best, cells = 0, []
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        lines = ([[(x, y) for x in range(f.w)] for y in range(f.h)] if dy else
                 [[(x, y) for y in range(f.h)] for x in range(f.w)])
        for line in lines:
            run = []
            for x, y in line:
                if mask(x, y) and walk(x + dx, y + dy):
                    run.append((x, y))
                    continue
                if len(run) > best:
                    best, cells = len(run), run
                run = []
            if len(run) > best:
                best, cells = len(run), run
    return best, cells


def grass_patches(f, min_cells=12, fill=0.9):
    """Tall grass patches of `min_cells` or more that fill `fill` of their bounding box: drawn as
    rectangles. Returns (count of rectangular patches, of all such patches, their cells)."""
    big = [c for c in components(f.mask("TG"), f.w, f.h) if len(c) >= min_cells]
    rect = []
    for c in big:
        xs = [x for x, _ in c]
        ys = [y for _, y in c]
        if len(c) / ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)) >= fill:
            rect.append(c)
    return len(rect), len(big), [xy for c in rect for xy in c]


def grass_cover(f, r=2):
    """Share of tall grass cells with cover (forest, a solid tile, water) within r tiles: in vanilla
    tall grass grows against the woods, cliffs and banks, rarely as an island in a lawn.
    Returns (share or None without enough tall grass, the cells without cover)."""
    tg = [(x, y) for y in range(f.h) for x in range(f.w) if f.g[y][x] == "TG"]
    if len(tg) < 20:
        return None, []
    bare = [(x, y) for x, y in tg
            if not any(f.at(x + dx, y + dy) in COVER for dx in range(-r, r + 1) for dy in range(-r, r + 1))]
    return 1 - len(bare) / len(tg), bare


def hedge(f):
    """The longest free-standing row of trees one tree thick (two tiles), with walkable ground on
    both long sides: a planted line. Returns (tiles, cells)."""
    forest, walk = f.mask("F"), f.mask(*WALK)
    best, cells = 0, []
    for horizontal in (True, False):
        outer = range(f.h) if horizontal else range(f.w)
        inner = range(f.w + 1) if horizontal else range(f.h + 1)
        for a in outer:
            run = []
            for b in inner:
                x, y = (b, a) if horizontal else (a, b)
                if horizontal:
                    on = forest(x, y) and forest(x, y + 1) and walk(x, y - 1) and walk(x, y + 2)
                else:
                    on = forest(x, y) and forest(x + 1, y) and walk(x - 1, y) and walk(x + 2, y)
                if on:
                    run.append((x, y))
                else:
                    if len(run) > best:
                        best, cells = len(run), run
                    run = []
    return best, cells


def flower_beds(f):
    """(beds, share that are single flowers or None with fewer than 3 beds, cells of the beds of
    two or more)."""
    beds = components(f.mid_mask(FLOWER_IDS), f.w, f.h)
    if len(beds) < 3:
        return len(beds), None, []
    return len(beds), sum(len(b) == 1 for b in beds) / len(beds), [xy for b in beds if len(b) > 1 for xy in b]


# ---------------------------------------------------------------------------- screen rules ----
def screens(f):
    """Each screen-sized window (15 x 10, every 5 tiles): (x0, y0, share of plain grass 001)."""
    sw, sh = SCREEN
    out = []
    for y0 in range(0, max(1, f.h - sh + 1), SCREEN_STEP):
        for x0 in range(0, max(1, f.w - sw + 1), SCREEN_STEP):
            cells = [(x, y) for y in range(y0, min(f.h, y0 + sh)) for x in range(x0, min(f.w, x0 + sw))]
            out.append((x0, y0, sum(f.g[y][x] == "G" for x, y in cells) / len(cells)))
    return out


BARE = 0.5     # a screen more than half plain grass reads as empty (vanilla: 0-5% of a map's screens)


def clearance(f):
    """The largest open space: the most tiles from any walkable cell to the nearest tile you can't
    walk on (Chebyshev; off the map counts as open). Returns (radius, the cell)."""
    walk = f.mask(*WALK)
    INF = 99
    d = [[INF if walk(x, y) else 0 for x in range(f.w)] for y in range(f.h)]
    for passes in ((range(f.h), range(f.w), ((-1, 0), (0, -1), (-1, -1), (1, -1))),
                   (range(f.h - 1, -1, -1), range(f.w - 1, -1, -1), ((1, 0), (0, 1), (1, 1), (-1, 1)))):
        ys, xs, nbrs = passes
        for y in ys:
            for x in xs:
                if d[y][x]:
                    for dx, dy in nbrs:
                        if f.inm(x + dx, y + dy):
                            d[y][x] = min(d[y][x], d[y + dy][x + dx] + 1)
    best, at = 0, None
    for y in range(f.h):
        for x in range(f.w):
            if d[y][x] != INF and d[y][x] > best:
                best, at = d[y][x], (x, y)
    return best, at


# --------------------------------------------------------------------------- the rule table ----
# id: (tier, worse ("high" | "low"), what it measures, why it matters)
RULES = {
    "staircase_water": ("context", "high", "longest bank staircase repeating one step (corners)",
                        "a river drawn straight from map data steps like a ruler; vanilla varies its steps"),
    "staircase_forest": ("context", "high", "longest forest-edge staircase repeating one step (corners)",
                         "vanilla's diagonal woods step irregularly"),
    "straight_forest": ("screen", "high", "longest straight forest edge facing open ground (tiles)",
                        "Tom's 'rectangular forest groupings'"),
    "straight_water": ("screen", "high", "longest straight bank facing open ground (tiles)",
                       "long ruler-straight banks read as canals"),
    "grass_rect": ("context", "high", "share of tall grass patches (12+ cells) drawn as rectangles",
                   "vanilla's patches are irregular; a rectangle is a field, on purpose or not"),
    "grass_cover": ("context", "low", "share of tall grass within 2 tiles of cover (woods, cliffs, water)",
                    "vanilla's tall grass grows against cover, rarely as an island in a lawn"),
    "hedge": ("context", "high", "longest free-standing row of trees one tree thick (tiles)",
              "vanilla's free-standing trees stand alone or in pairs; long single rows read as planted"),
    "flower_singles": ("context", "low", "share of flower beds that are a single flower",
                       "vanilla's route flowers are singles (90-100%); repeated pairs read as a pattern"),
    "bare_screens": ("screen", "high", f"share of screens (15x10) more than {int(BARE * 100)}% plain grass",
                     "a screen of nothing but grass is the 'large uniform grassy areas' Tom saw"),
    "open_space": ("screen", "high", "largest open space (tiles from any walkable cell to a solid one)",
                   "vanilla's routes are corridors and pockets; a field wider than that reads empty"),
}


def measure(project, layout, map_type="MAP_TYPE_ROUTE"):
    """{rule: (value or None, cells)} for one map (or a preview's layout)."""
    f = Features(project, layout, map_type)
    out = {}
    out["staircase_water"] = staircase(f, f.mask("W"))
    out["staircase_forest"] = staircase(f, f.mask("F"))
    out["straight_forest"] = straight_edge(f, f.mask("F"))
    out["straight_water"] = straight_edge(f, f.mask("W"))
    nrect, nbig, rcells = grass_patches(f)
    out["grass_rect"] = ((nrect / nbig) if nbig else None, rcells)
    out["grass_cover"] = grass_cover(f)
    out["hedge"] = hedge(f)
    _, singles, bed_cells = flower_beds(f)
    out["flower_singles"] = (singles, bed_cells)
    scr = screens(f)
    bare = [(x0, y0) for x0, y0, s in scr if s > BARE]
    out["bare_screens"] = (len(bare) / len(scr) if scr else None,
                           [(x, y) for x0, y0 in bare for y in range(y0, min(f.h, y0 + SCREEN[1]))
                            for x in range(x0, min(f.w, x0 + SCREEN[0]))])
    r, at = clearance(f)
    out["open_space"] = (r, [at] if at else [])
    return out


# ---------------------------------------------------------------------------- calibration ----
def map_kind(map_type):
    return "town" if map_type in TOWN_TYPES else "route"


def calibration_maps(project, corpus):
    """Vanilla's outdoor maps on General, by kind: towns and cities; land routes with woods
    (forest at least 8% of the map, water at most half: the sea routes have nothing to say about
    woods and meadows)."""
    vanilla = {e["id"] for e in corpus._vanilla_layouts()}
    out = {"route": [], "town": []}
    for name in project.map_names:
        m = project.load_map(name)
        t = m.j.get("map_type")
        L = m.layout
        if t not in OUTDOOR or L.primary != PRIMARY or L.entry["id"] not in vanilla:
            continue
        f = Features(project, L, t)
        n = f.w * f.h
        if map_kind(t) == "route" and (f.count("F") < 0.08 * n or f.count("W") > 0.5 * n):
            continue
        out[map_kind(t)].append(name)
    return out


def calibrate(project, corpus):
    """The bands: for each kind and rule, vanilla's values over the calibration maps."""
    data = {"maps": calibration_maps(project, corpus), "bands": {}, "values": {}}
    for k, names in data["maps"].items():
        vals = {r: [] for r in RULES}
        for name in names:
            m = project.load_map(name)
            got = measure(project, m.layout, m.j.get("map_type"))
            data["values"][name] = {r: v for r, (v, _) in got.items()}
            for r, (v, _) in got.items():
                if v is not None:
                    vals[r].append(v)
        bands = {}
        for r, vs in vals.items():
            vs = sorted(vs)
            if not vs:
                continue
            q = lambda p: vs[min(len(vs) - 1, int(len(vs) * p))]
            bands[r] = {"n": len(vs), "min": vs[0], "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "max": vs[-1]}
        data["bands"][k] = bands
    return data


def load_bands():
    return json.load(open(BANDS_FILE, encoding="utf-8"))


def save_bands(data):
    with open(BANDS_FILE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------- judging ----
ACCEPT_PREFIX = "// accept:"


def accepted(comments):
    """{rule: reason} from a sketch's `// accept: <rule>: <reason>` lines."""
    out = {}
    for c in comments or ():
        if c.startswith(ACCEPT_PREFIX):
            rule, _, why = c[len(ACCEPT_PREFIX):].partition(":")
            out[rule.strip()] = why.strip()
    return out


def sketch_comments(project, name):
    """The comments of the map's sketch (design/maps/<Map>.txt), if it has one."""
    path = project.path("design", "maps", f"{name}.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [l.rstrip("\n") for l in fh if l.startswith("//")]


def verdict(rule, value, band):
    """'ok', 'unusual' (outside vanilla's p10..p90) or 'beyond' (past vanilla's min/max)."""
    if value is None or band is None:
        return "n/a"
    worse = RULES[rule][1]
    if worse == "high":
        return "beyond" if value > band["max"] else "unusual" if value > band["p90"] else "ok"
    return "beyond" if value < band["min"] else "unusual" if value < band["p10"] else "ok"


def report(project, corpus, layout, map_type, comments=(), bands=None):
    """{'pairs': [...odd pairs...], 'guides': [(rule, value, verdict, band, cells, accepted reason)]}."""
    bands = bands or load_bands()
    band = bands["bands"].get(map_kind(map_type), {})
    acc = accepted(comments)
    unknown = set(acc) - set(RULES) - {"pairs"}
    if unknown:
        raise ValueError(f"// accept: unknown rule(s) {sorted(unknown)}; rules are {sorted(RULES)}")
    guides = []
    for rule, (value, cells) in measure(project, layout, map_type).items():
        guides.append((rule, value, verdict(rule, value, band.get(rule)), band.get(rule), cells, acc.get(rule)))
    return {"pairs": odd_pairs(corpus, layout), "guides": guides, "kind": map_kind(map_type)}


def fmt(v):
    if v is None:
        return "-"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def summary_line(rep):
    """One line: strict pairs, then each guide outside vanilla's band."""
    flagged = [f"{r} {fmt(v)} ({'accepted' if acc else ver})" for r, v, ver, _, _, acc in rep["guides"]
               if ver in ("unusual", "beyond")]
    return f"{len(rep['pairs'])} odd pairs; " + ("; ".join(flagged) if flagged else "every guide inside vanilla's band")
