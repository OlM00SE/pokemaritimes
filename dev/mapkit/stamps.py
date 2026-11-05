"""Building stamps: whole vanilla buildings placed from a sketch, block for block.

The catalog (stamps.toml) cuts each building from a vanilla map. In a sketch a placed building
is a line `// stamp: <name> @ x,y -> <Interior>` (x, y = the stamp's top-left) and its cells
drawn as `B`; design scripts call `Sketch.place(...)`, which does both. Compiling copies the
stamp's blocks (metatile, collision, elevation) into those cells; the terrain around them is
tiled as usual, with the building as context. A cell of a stamp may also be `#`: it keeps the
map's current block (extract uses that for vanilla's blends, e.g. Oldale's Mart roof corner
drawn over a tree). `-> <Interior>` names the room behind the door; `mapgen --apply` wires the
door to it, creating it from the stamp's interior template if it doesn't exist yet
(mapkit/buildings.py).
"""
import functools, os, re, tomllib
from .layout import pack

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stamps.toml")
CHAR = "B"
LINE = re.compile(r"^//\s*stamp:\s*(\w+)\s*@\s*(\d+)\s*,\s*(\d+)\s*(?:->\s*(\w+))?\s*$")
KINDS = ("plain", "pokemon_center", "mart")
PRIMARY_LIMIT = 512                      # metatile ids below this come from the primary tileset


class Stamp:
    """One catalog entry, with its blocks read from the source map."""

    def __init__(self, project, entry):
        self.name, self.source = entry["name"], entry["source"]
        self.about = entry.get("about", "")
        self.interior, self.kind = entry["interior"], entry.get("kind", "plain")
        sx, sy = entry["at"]
        self.shape = entry["shape"]
        self.h, self.w = len(self.shape), len(self.shape[0])
        m = project.load_map(self.source)
        L = m.layout
        self.primary = L.primary
        self.cells = {}                  # (dx, dy) -> block
        for dy, row in enumerate(self.shape):
            for dx, ch in enumerate(row):
                if ch == "#":
                    self.cells[(dx, dy)] = L.get(sx + dx, sy + dy)
        uses_secondary = any(b & 0x3FF >= PRIMARY_LIMIT for b in self.cells.values())
        self.secondary = L.secondary if uses_secondary else None
        door = project.behavior_set("WarpDoor")
        tp = L.tiles
        doors = [c for c, b in self.cells.items() if tp.behavior(b & 0x3FF) in door]
        self.door = doors[0] if len(doors) == 1 else None
        self.problems = self._problems(entry, L, sx, sy, doors)

    def _problems(self, entry, L, sx, sy, doors):
        out = []
        if len({len(r) for r in self.shape}) != 1 or set("".join(self.shape)) - {"#", "."}:
            out.append("shape rows must be equal width, of '#' and '.'")
        if not (L.inb(sx, sy) and L.inb(sx + self.w - 1, sy + self.h - 1)):
            out.append(f"the rectangle at {entry['at']} ({self.w}x{self.h}) runs off {self.source}")
        if len(doors) != 1:
            out.append(f"has {len(doors)} door tiles; a stamp has exactly one")
        if self.kind not in KINDS:
            out.append(f"kind {self.kind!r} is not one of {KINDS}")
        return out

    def footprint(self, x, y):
        """Map cells of the stamp placed with its top-left at (x, y)."""
        return {(x + dx, y + dy) for dx, dy in self.cells}

    def door_at(self, x, y):
        return (x + self.door[0], y + self.door[1])

    def fits(self, primary, secondary):
        return primary == self.primary and (self.secondary is None or secondary == self.secondary)

    def tileset_note(self):
        return "any General map" if self.secondary is None else f"{self.secondary[len('gTileset_'):]} maps"


@functools.lru_cache(maxsize=None)
def _catalog(root):
    from .project import Project
    p = Project(root)
    entries = tomllib.load(open(CATALOG, "rb"))["stamp"]
    return {e["name"]: Stamp(p, e) for e in entries}


def catalog(project):
    """{name: Stamp}, read once per project root."""
    return _catalog(project.root)


class Placement:
    def __init__(self, name, x, y, interior=None):
        self.name, self.x, self.y, self.interior = name, x, y, interior

    def line(self):
        return f"// stamp: {self.name} @ {self.x},{self.y}" + (f" -> {self.interior}" if self.interior else "")

    def __repr__(self):
        return self.line()[3:]


def parse_line(line):
    """A `// stamp:` comment line -> Placement, or None if the line isn't one."""
    m = LINE.match(line.strip())
    if not m:
        if line[2:].strip().lower().startswith("stamp:"):
            raise ValueError(f"bad stamp line {line!r}: write // stamp: <name> @ x,y [-> <Interior>]")
        return None
    return Placement(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))


def resolve(project, rows, placements, layout):
    """The blocks the placed stamps put on the map: ({(x, y): block}, problems [(x, y, msg)]).
    Refused: an unknown stamp, one off the map or on the wrong tilesets, two that overlap,
    a stamp cell drawn as anything but `B` (or `#`, keep the current block), and a `B` that no
    stamp covers."""
    cat = catalog(project)
    w, h = layout.width, layout.height
    blocks, owner, problems = {}, {}, []
    for pl in placements:
        st = cat.get(pl.name)
        if st is None:
            problems.append((pl.x, pl.y, f"unknown stamp {pl.name!r} (dev/buildings.py list shows them)"))
            continue
        if st.problems:
            problems.append((pl.x, pl.y, f"stamp {pl.name} is broken in the catalog: {'; '.join(st.problems)}"))
            continue
        if not st.fits(layout.primary, layout.secondary):
            problems.append((pl.x, pl.y, f"{pl.name} needs {st.tileset_note()}, not "
                                         f"{layout.primary}/{layout.secondary}"))
            continue
        for (dx, dy), b in st.cells.items():
            x, y = pl.x + dx, pl.y + dy
            if not (0 <= x < w and 0 <= y < h):
                problems.append((x, y, f"{pl.name} at ({pl.x},{pl.y}) runs off the map ({w}x{h})"))
                break
            if (x, y) in owner:
                problems.append((x, y, f"{pl.name} at ({pl.x},{pl.y}) overlaps {owner[(x, y)]}"))
                continue
            owner[(x, y)] = f"{pl.name} at ({pl.x},{pl.y})"
            ch = rows[y][x]
            if ch == CHAR:
                blocks[(x, y)] = b
            elif ch != "#":
                problems.append((x, y, f"a cell of {pl.name} at ({pl.x},{pl.y}) is drawn as {ch!r}; "
                                       f"draw it {CHAR!r} (or '#' to keep the current block)"))
    for y in range(h):
        for x in range(w):
            if rows[y][x] == CHAR and (x, y) not in owner:
                problems.append((x, y, f"{CHAR!r} that no stamp covers (add a // stamp: line, or redraw it)"))
    return blocks, problems


def door_problems(project, placements, blocks_at, w, h, tiles):
    """Each placed door must face a walkable tile (the player stands south of a door and presses
    up). If that tile is part of the stamp (a doormat), a walkable tile must lead onto it.
    blocks_at(x, y) gives the compiled block; tiles is the layout's tileset pair. [(x, y, msg)]."""
    from .project import TILE_FLAG_SURFABLE
    cat = catalog(project)
    out = []
    walk = lambda x, y: 0 <= x < w and 0 <= y < h and (blocks_at(x, y) >> 10) & 3 == 0 and not (
        project.tile_flags.get(tiles.behavior(blocks_at(x, y) & 0x3FF), 0) & TILE_FLAG_SURFABLE)
    for pl in placements:
        st = cat.get(pl.name)
        if st is None or st.door is None:
            continue
        dx, dy = st.door_at(pl.x, pl.y)
        fx, fy = dx, dy + 1
        if not walk(fx, fy):
            out.append((fx, fy, f"the door of {pl.name} at ({dx},{dy}) faces ({fx},{fy}), which isn't "
                                f"walkable ground"))
            continue
        if (fx - pl.x, fy - pl.y) in st.cells:          # a mat: something must lead onto it
            fp = st.footprint(pl.x, pl.y)
            if not any(walk(nx, ny) and (nx, ny) not in fp
                       for nx, ny in ((fx, fy + 1), (fx - 1, fy), (fx + 1, fy))):
                out.append((fx, fy, f"nothing walkable leads onto the doormat of {pl.name} at ({fx},{fy})"))
    return out


def recognise(project, layout):
    """Stamps standing on a layout: [(Stamp, x, y, kept)], where `kept` are the stamp's cells
    whose block differs from the catalog's (a vanilla blend; extract keeps them as '#').
    A stamp is recognised when every solid cell (collision != 0, the door included) matches
    block for block; only walk-behind cells (a roof's top row, a doormat) may differ: vanilla
    blends a roof's top row with whatever stands behind it (a tree, a hedge, a fence).
    Larger stamps win where two would overlap."""
    cat = catalog(project)
    found, taken = [], set()
    w, h = layout.width, layout.height
    for st in sorted(cat.values(), key=lambda s: -len(s.cells)):
        if st.problems or not st.fits(layout.primary, layout.secondary):
            continue
        solid = [(c, b) for c, b in st.cells.items() if (b >> 10) & 3]
        soft = [(c, b) for c, b in st.cells.items() if not (b >> 10) & 3]
        (ax, ay), ab = solid[0]
        for y in range(h - st.h + 1):
            for x in range(w - st.w + 1):
                if layout.get(x + ax, y + ay) != ab:
                    continue
                if any(layout.get(x + dx, y + dy) != b for (dx, dy), b in solid):
                    continue
                fp = st.footprint(x, y)
                if fp & taken:
                    continue
                kept = [(x + dx, y + dy) for (dx, dy), b in soft if layout.get(x + dx, y + dy) != b]
                found.append((st, x, y, kept))
                taken |= fp
    return found
