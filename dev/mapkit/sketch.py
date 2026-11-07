"""Map sketches: human-readable terrain grids that compile to map.bin.

File format (design/maps/<Map>.txt):
    // map: Route203_1                <- target map folder
    // any other '//' lines are comments
    TTTTTTTT....~~~~
    ...

Legend (one character per metatile):
    .  grass            ,  tall grass (encounters)     =  light path      :  sand / dirt
    ~  river/sea water  o  pond water                  T  forest (auto 2x2 trees)
    v  ledge, jump south   <  ledge, jump west          >  ledge, jump east   (mapkit/ledges.py)
    r  rock standing in water (2x2)                                            (mapkit/shores.py)
    *  flowers    b  boulder    y  sapling (a vertical run of 2-3)              (mapkit/flora.py)
    s  sign post (its text is a sign event: dev/events.py)                     (mapkit/flora.py)
    B  a cell of a building stamp, placed by a `// stamp:` line               (mapkit/stamps.py)
    H  a plank bridge's deck over water, a strip two columns wide             (mapkit/bridges.py)
    ^  a cliff wall    %  stairs up a cliff's south face                       (mapkit/cliffs.py)
    #  keep the map's current block unchanged (hand-painted pieces, ...)
Levels: `// level: 0001112...` lines, one per row, give each cell a terrace level (0-9; all 0
when there are none). Cliff walls separate the levels; see mapkit/cliffs.py.
Sand (':') that touches river/sea water ('~') becomes a beach; grass banks and beaches are built
by shape (mapkit/shores.py). Flora stands on plain grass only.
Buildings: `// stamp: pokemon_center @ 10,4 -> Woodstock_PokemonCenter_1F` places a catalog
building with its top-left at (10, 4); its cells are drawn `B`. Sketch.place() does both.
"""
from .terrain import TREE, TREE_Q, Rules, autotile, Vocabulary, grid_labels, PRIMARY
from .layout import pack
from .project import TILE_FLAG_SURFABLE
from . import ledges, shores, flora, stamps, bridges, cliffs

# a bridge's deck reads as water to everything but the bridge resolver (the banks run under it)
CHAR_TO_CLASS = {".": "G", ",": "TG", "=": "P", ":": "SA", "~": "S", "o": "W", "T": "T", "#": "F",
                 "v": "LD", "<": "LD", ">": "LD", shores.ROCK_CHAR: shores.ROCK_CLS,
                 stamps.CHAR: "F", bridges.CHAR: "S", **flora.CHAR_CLASS, **cliffs.CLS}
CLASS_TO_CHAR = {"G": ".", "TG": ",", "P": "=", "SA": ":", "S": "~", "W": "o",
                 "TL": "T", "TR": "T", "BL": "T", "BR": "T", "F": "#",
                 shores.ROCK_CLS: shores.ROCK_CHAR, **flora.CLASS_CHAR,
                 **{c: ch for ch, c in cliffs.CLS.items()}}   # LD: ledges.piece_char
LEVEL_PREFIX = "// level:"
# tiles vanilla labels as grass that the learned rules must never choose: cliff stairs, sapling crowns
NEVER_GRASS = frozenset(cliffs.STAIR_PIECES | {flora.CROWN, 0x00F})
CLASS_ATTRS = {"G": (0, 3), "TG": (0, 3), "P": (0, 3), "SA": (0, 3), "S": (0, 1), "W": (0, 1),
               "TL": (1, 0), "TR": (1, 0), "BL": (1, 0), "BR": (1, 0), "LD": ledges.LEDGE_ATTRS,
               shores.ROCK_CLS: (1, 0)}


class SketchError(ValueError):
    """The sketch can't be built as drawn; .problems lists (x, y, message)."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(f"  ({x},{y}) {m}" for x, y, m in problems))


class Sketch:
    def __init__(self, map_name, rows, comments=(), placements=(), levels=None):
        self.map_name, self.rows, self.comments = map_name, [list(r) for r in rows], list(comments)
        self.stamps = list(placements)          # [stamps.Placement]: the buildings
        # terrace levels (mapkit/cliffs.py), one int per cell; all 0 for a map without cliffs
        self.levels = [list(r) for r in levels] if levels else cliffs.zero_levels(self.w, self.h)
        if (len(self.levels[0]), len(self.levels)) != (self.w, self.h):
            raise ValueError(f"levels are {len(self.levels[0])}x{len(self.levels)}, the sketch {self.w}x{self.h}")

    @property
    def w(self): return len(self.rows[0])
    @property
    def h(self): return len(self.rows)

    @classmethod
    def load(cls, path):
        name, rows, comments, placements, levels = None, [], [], [], []
        for line in open(path, encoding="utf-8").read().splitlines():
            if line.startswith(LEVEL_PREFIX):
                digits = line[len(LEVEL_PREFIX):].strip()
                if not digits.isdigit():
                    raise ValueError(f"{path}: a level line holds digits only: {line!r}")
                levels.append([int(c) for c in digits])
            elif line.startswith("//"):
                if line[2:].strip().lower().startswith("map:"):
                    name = line.split(":", 1)[1].strip()
                elif (pl := stamps.parse_line(line)) is not None:
                    placements.append(pl)
                else:
                    comments.append(line)
            elif line.strip():
                rows.append(line.rstrip("\n"))
        widths = {len(r) for r in rows}
        if len(widths) != 1:
            raise ValueError(f"{path}: rows have different widths {sorted(widths)}")
        bad = {ch for r in rows for ch in r} - set(CHAR_TO_CLASS)
        if bad:
            raise ValueError(f"{path}: unknown characters {sorted(bad)}")
        if levels and (len(levels) != len(rows) or {len(r) for r in levels} != widths):
            raise ValueError(f"{path}: {len(levels)} level lines for {len(rows)} rows (one per row, "
                             "as wide as the rows)")
        return cls(name, rows, comments, placements, levels or None)

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"// map: {self.map_name}\n")
            for pl in self.stamps:
                f.write(pl.line() + "\n")
            for c in self.comments:
                f.write(c + "\n")
            for r in self.rows:
                f.write("".join(r) + "\n")
            if any(v for r in self.levels for v in r):
                for r in self.levels:
                    f.write(f"{LEVEL_PREFIX} {''.join(str(v) for v in r)}\n")

    def level(self, x, y): return self.levels[y][x]

    def set_level(self, cells, v):
        """Give every cell of `cells` (a set of (x, y)) terrace level v (0-9); cells off the
        sketch are ignored."""
        if not 0 <= v <= 9:
            raise ValueError(f"levels are 0-9, not {v}")
        for x, y in cells:
            if 0 <= x < self.w and 0 <= y < self.h:
                self.levels[y][x] = v

    def place(self, project, name, x, y, interior=None):
        """Put building stamp `name` with its top-left at (x, y): draws its cells `B` and adds
        the `// stamp:` line. `interior` names the room behind the door (created by
        `mapgen --apply` from the stamp's interior template if it doesn't exist). Returns the
        stamp's door (x, y). ValueError if it's unknown, runs off the sketch, overlaps another
        stamp or stands in water; compile checks the rest (tilesets, the ground in front of the
        door). Over forest it clears a lot: trees it cuts in half are reported as dropped cells."""
        st = stamps.catalog(project).get(name)
        if st is None:
            raise ValueError(f"unknown stamp {name!r}; known: {', '.join(stamps.catalog(project))}")
        fp = st.footprint(x, y)
        if any(not (0 <= cx < self.w and 0 <= cy < self.h) for cx, cy in fp):
            raise ValueError(f"{name} at ({x},{y}) ({st.w}x{st.h}) runs off the {self.w}x{self.h} map")
        cat = stamps.catalog(project)
        for pl in self.stamps:
            other = cat.get(pl.name)
            if other and fp & other.footprint(pl.x, pl.y):
                raise ValueError(f"{name} at ({x},{y}) overlaps {pl.name} at ({pl.x},{pl.y})")
        wet = sorted((cx, cy) for cx, cy in fp if CHAR_TO_CLASS[self.rows[cy][cx]] in ("S", "W", shores.ROCK_CLS))
        if wet:
            raise ValueError(f"{name} at ({x},{y}) would stand in water at {wet[:4]}")
        for cx, cy in fp:
            self.rows[cy][cx] = stamps.CHAR
        self.stamps.append(stamps.Placement(name, x, y, interior))
        return st.door_at(x, y)

    # ---- editing helpers for procedural design scripts ----
    def accept(self, rule, why):
        """Say in the sketch that a visual guide's finding is meant (mapkit/composition.py), e.g.
        accept("grass_rect", "hay fields are fields"): `// accept: rule: why`. The report then shows
        the guide as accepted, with the reason, instead of flagging it."""
        from .composition import RULES, ACCEPT_PREFIX
        if rule not in RULES:
            raise ValueError(f"accept: unknown rule {rule!r}; rules are {sorted(RULES)}")
        if not why.strip():
            raise ValueError("accept: give the reason")
        self.comments = [c for c in self.comments
                         if not c.startswith(f"{ACCEPT_PREFIX} {rule}:")] + [f"{ACCEPT_PREFIX} {rule}: {why}"]

    def fill(self, x0, y0, x1, y1, ch):
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.rows[y][x] = ch

    def get(self, x, y): return self.rows[y][x]

    def set(self, x, y, ch):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x] = ch


def extract(project, vocab, map_name, rules=None, forbidden=None, corpus=None, verify_shores=True):
    """Existing map -> sketch. Cells outside the vocabulary become '#' (kept as-is). With
    `rules`, cells whose exact tile the generator could never produce also become '#', so
    hand-placed details (decorations, small trees, special variants) survive a round trip.
    Ledges extract as v/</>; any ledge group the resolver would not rebuild tile for tile
    (e.g. Route 118's cliff pieces) is kept as '#'.
    Shores (General primary, with `rules`): any shore cell a compile wouldn't reproduce is kept
    as '#'. Pass the `forbidden` pairs mapgen builds with, so the check compiles the way the
    build will; verify_shores=False skips the compile-based check (tests use it to see what
    the shape tables alone reproduce)."""
    m = project.load_map(map_name)
    L = m.layout
    lab = grid_labels(vocab, L.entry, L.blocks, L.width, L.height)
    rows = []
    for y, row in enumerate(lab):
        out = []
        for x, c in enumerate(row):
            mid = L.mid(x, y)
            if L.primary == PRIMARY and cliffs.is_cliff_block(L.get(x, y)):
                out.append("#")         # cliffs are kept: their levels aren't recovered (yet)
                continue
            if c == "LD":
                out.append(ledges.piece_char(mid))
                continue
            if c == "F" and L.primary == PRIMARY and mid in shores.SAND_PIECES:
                c = "SA"                    # beach sand; shores.keep_unrebuildable verifies it
            elif c == "F" and L.primary == PRIMARY and mid in shores.ROCK_PIECES:
                c = shores.ROCK_CLS
            elif rules and c not in ("F", "TL", "TR", "BL", "BR") and mid not in rules.outputs(c) \
                    and not (c == "S" and L.primary == PRIMARY):
                c = "F"                     # (General water is judged by shape, below)
            out.append(CLASS_TO_CHAR[c])
        rows.append(out)
    if L.primary == PRIMARY:
        # flowers, boulders and whole saplings; extract's compile check below keeps ('#') any
        # that a compile wouldn't put back exactly (e.g. flowers under a canopy overhang)
        for (x, y), ch in flora.extract_chars(lambda x, y: L.mid(x, y), L.width, L.height).items():
            rows[y][x] = ch
        extract_bridges(project, L, rows)
    keep_unrebuildable_ledges(rows, L.width, L.height, lambda x, y: L.mid(x, y))
    placements = recognise_stamps(project, m, rows)      # marks the stamps' cells in rows: first
    sk = Sketch(map_name, ["".join(r) for r in rows], placements=placements)
    if L.primary == PRIMARY and rules:
        shores.keep_unrebuildable(sk.rows, L.width, L.height, lambda x, y: L.mid(x, y),
                                  lambda ch: CHAR_TO_CLASS[ch])
        if verify_shores:
            # verified as mapgen builds: with what lies past each edge (seams, border)
            from . import seams as seam_kit
            keep_unrebuildable_shore_blocks(project, vocab, rules, sk, L, forbidden, corpus,
                                            **seam_kit.compile_context(project, vocab, m))
    if L.primary == PRIMARY:
        recheck_bridges(project, L, sk.rows)       # the passes above may have kept a deck's neighbours
    return sk


def recheck_bridges(project, layout, rows):
    """keep_valid_bridges against the layout's own bridge pieces (nothing if it has none)."""
    ids, _ = bridges.piece_ids(project, layout)
    if ids and any(bridges.CHAR in row for row in rows):
        want = {v: k for k, v in ids.items()}
        keep_valid_bridges(rows, layout.width, layout.height, lambda x, y: want.get(layout.mid(x, y)))


def extract_bridges(project, layout, rows):
    """Bridge decks (mapkit/bridges.py) become 'H', where the strip resolves exactly (deck
    pieces where the shape asks for them, grass or kept cells at its ends); any other deck cell
    stays '#' (Route 104's turning bridge over pond water, Fredericton's hand-painted ones)."""
    ids, _ = bridges.piece_ids(project, layout)
    if not ids:
        return
    want = {v: k for k, v in ids.items()}
    for y in range(layout.height):
        for x in range(layout.width):
            if layout.mid(x, y) in want:
                rows[y][x] = bridges.CHAR
    keep_valid_bridges(rows, layout.width, layout.height, lambda x, y: want.get(layout.mid(x, y)))


def keep_valid_bridges(rows, w, h, piece_at):
    """Turn every 'H' strip that doesn't resolve to the pieces standing there into '#', whole
    (half a deck can't be rebuilt). piece_at(x, y): the bridge piece (bridges.SOURCE numbering)
    the layout holds there, or None. Extract runs it again after its later passes, which can
    keep a deck's neighbours or ends as '#'. Returns the number of cells kept."""
    kept = 0
    while True:
        cells = {(x, y) for y in range(h) for x in range(w) if rows[y][x] == bridges.CHAR}
        if not cells:
            return kept
        cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in rows]
        pieces, _, errors = bridges.resolve(cls, cells, w, h)
        bad = {c for c, m in pieces.items() if m != piece_at(*c)}
        for x, y, _ in errors:          # an end's error names the cell beyond the deck: its strip
            bad |= {(x, y), (x, y - 1), (x, y + 1)} & cells
        if not bad:
            return kept
        for group in bridges.strips(cells):
            if group & bad:
                for x, y in group:
                    rows[y][x] = "#"
                    kept += 1


def recognise_stamps(project, m, rows):
    """Catalog buildings standing on map m become stamps in the extracted rows: their cells `B`,
    except cells where the map blends the building with what stands behind it (kept `#`).
    Each placement names the room its door's warp leads to. Returns the placements."""
    warps = {(w["x"], w["y"]): w["dest_map"] for w in m.events("warp_events")}
    out = []
    for st, x, y, kept in stamps.recognise(project, m.layout):
        for cx, cy in st.footprint(x, y):
            rows[cy][cx] = "#" if (cx, cy) in kept else stamps.CHAR
        dest = project.const_to_map.get(warps.get(st.door_at(x, y)))
        out.append(stamps.Placement(st.name, x, y, dest))
    return out


def shore_owned(cls, x, y, w, h):
    """The cells the shore resolver decides: water, rocks, and sand or grass beside water."""
    c = cls[y][x]
    return c in (shores.WATER_CLS, shores.ROCK_CLS) or (
        c in (shores.SAND_CLS, "G") and shores.touches_water(cls, x, y, w, h))


def verify_owned(cls, x, y, w, h):
    """Cells extract's compile check compares: shore cells, flora pieces, and the cells around
    flora (flora reads as grass in a compile, where vanilla's rules saw a kept tile, so a
    neighbour's learned tile could change)."""
    return shore_owned(cls, x, y, w, h) or any(
        0 <= x + dx < w and 0 <= y + dy < h and cls[y + dy][x + dx] in flora.CLASSES
        for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def whole_tree(labels, x, y, w, h):
    """The cells of the 2x2 tree that (x, y) belongs to, by the layout's tree-quarter labels;
    just {(x, y)} if it isn't a tree quarter. Keeping a tree whole never leaves half a tree."""
    q = labels[y][x]
    if q not in TREE_Q:
        return {(x, y)}
    x0, y0 = x - (q in ("TR", "BR")), y - (q in ("BL", "BR"))
    return {(x0 + dx, y0 + dy) for dx in (0, 1) for dy in (0, 1) if 0 <= x0 + dx < w and 0 <= y0 + dy < h}


def keep_unrebuildable_shore_blocks(project, vocab, rules, sk, layout, forbidden=None, corpus=None,
                                    seams=None, border=None):
    """Compile the extracted sketch and keep ('#') every shore or flora cell whose block wouldn't
    come back exactly: e.g. vanilla beach sand that meets grass without a rim, sand at
    elevation 0, or flowers under a canopy overhang. If a cell beside flora wouldn't come back,
    the flora next to it is kept instead (verify_owned).
    Joins the grammar forbids (a hand-painted tree beside a sand lane) are kept too, both sides
    (trees whole), with any neighbour that wouldn't come back beside them: a compile would
    otherwise "repair" the join by turning the sand into grass.
    Cells a compile refuses are kept too. Every round keeps at least one more cell, so the loop
    ends; it stops when a compile reproduces every shore and flora block, which is what makes
    extract -> compile never change one."""
    if corpus is None:
        from .corpus import Corpus
        corpus = Corpus(project)
    w, h = sk.w, sk.h
    labels = grid_labels(vocab, layout.entry, layout.blocks, w, h)
    joins = set()                       # cells kept because the grammar would repair them
    near_join = lambda x, y: any((x + dx, y + dy) in joins for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    while True:
        refused = None
        try:
            blocks, report = compile_sketch(project, corpus, rules, sk, layout, vocab, forbidden,
                                            seams=seams, border=border)
            cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sk.rows]
            # a hand-painted join the grammar forbids (a tree beside a sand lane): the repair
            # would turn a drawn cell into grass. Keep both sides as they are, a tree whole.
            grammar_kept = set()
            for (x, y), (_, by) in report.get("grammar_cells", {}).items():
                grammar_kept |= {(x, y)} | whole_tree(labels, *by, w, h)
            joins |= grammar_kept
            changed = lambda x, y: blocks[y * w + x] != layout.get(x, y)
            bad = [(x, y) for y in range(h) for x in range(w) if verify_owned(cls, x, y, w, h) and changed(x, y)]
            # a changed neighbour of flora (e.g. a tree quarter, or grass picking another variant)
            # changed because the flora now reads as grass: keep the flora instead, which puts
            # back the context vanilla's rules saw (keeping the neighbour could split a tree)
            bad = [c for x, y in bad for c in (
                [(x, y)] if shore_owned(cls, x, y, w, h) or cls[y][x] in flora.CLASSES else
                [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if 0 <= x + dx < w and 0 <= y + dy < h and cls[y + dy][x + dx] in flora.CLASSES])]
            # beside a kept join, a neighbour's learned tile can change (it now sees a kept tile
            # where vanilla's rules saw sand or a tree): keep that neighbour too, a tree whole
            bad += sorted(grammar_kept) + [c for y in range(h) for x in range(w)
                                           if near_join(x, y) and changed(x, y)
                                           for c in whole_tree(labels, x, y, w, h)]
        except SketchError as ex:
            refused = ex
            bad = [(x, y) for x, y, _ in ex.problems]
        bad = [(x, y) for x, y in bad if 0 <= x < w and 0 <= y < h and sk.rows[y][x] != "#"]
        if not bad:
            if refused:                 # refused, but nothing left to keep: can't be fixed here
                raise RuntimeError(f"{sk.map_name}: extracted sketch can't be compiled: {refused}")
            return
        for x, y in bad:
            sk.rows[y][x] = "#"
        keep_unrebuildable_ledges(sk.rows, w, h, lambda x, y: layout.mid(x, y))
        shores.keep_unrebuildable(sk.rows, w, h, lambda x, y: layout.mid(x, y), lambda ch: CHAR_TO_CLASS[ch])
        recheck_bridges(project, layout, sk.rows)


def keep_unrebuildable_ledges(rows, w, h, mid_at):
    """Turn every connected ledge group that resolve() would not reproduce exactly into '#'.
    Groups are never adjacent, so one pass is enough; the loop re-checks to make the guarantee
    explicit. Returns the number of cells kept."""
    kept = 0
    while True:
        pieces, errors = ledges.resolve(rows, w, h, ledges.runs_into_kept(rows, w, h, mid_at))
        bad = {(x, y) for x, y, _ in errors}
        bad |= {xy for xy, mid in pieces.items() if mid != mid_at(*xy)}
        if not bad:
            return kept
        stack = list(bad)
        while stack:
            x, y = stack.pop()
            if not (0 <= x < w and 0 <= y < h) or rows[y][x] not in ledges.LEDGE_CHARS:
                continue
            rows[y][x] = "#"
            kept += 1
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


QUARTERS = ("TL", "TR", "BL", "BR")


def misaligned(quarters, beyond):
    """How many tree quarters in `quarters` ({(x, y): class}) sit beside a tree quarter of `beyond`
    (the cells past an edge) that doesn't continue their 2x2 pattern: across a side seam the next
    tree's half in the same row (TL's east is TR, TR's east is TL), across a top or bottom one the
    next tree's half in the same column (TL's north is BL)."""
    n = 0
    for (x, y), q in quarters.items():
        if q not in QUARTERS:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            o = beyond.get((x + dx, y + dy))
            if o not in QUARTERS:
                continue
            want = q[0] + {"L": "R", "R": "L"}[q[1]] if dx else {"T": "B", "B": "T"}[q[0]] + q[1]
            n += o != want
    return n


def assign_tree_quarters(cls_grid, w, h, hint=None, outside=None, border=None):
    """Turn 'T' cells into whole 2x2 trees (TL TR / BL BR). Greedy row-major tiling: the first
    free T cell becomes a tree's top-left if the 2x2 block from it is all free T. This places
    trees at any alignment (single trees, staggered rows). Leftover T cells can't hold a whole
    tree and become grass (returned as a count, so designers can see what was dropped).
    A sketch drawn as whole non-overlapping 2x2 trees always comes back tree for tree.
    hint (the existing map's labels): each grove (a 4-connected group of T cells) keeps the old
    map's tree placement if that drops no more cells than tiling it afresh. A redesigned grove
    edge, e.g. staggered trees beside old aligned ones, is tiled afresh, so old trees that
    straddle the new ones don't knock them out.
    outside ({(x, y): class} across connected seams, compile_sketch's `seams`): a tree is cut by a
    connected edge only where the neighbour holds its other half.
    border ({(x, y): class} past the edges no neighbour covers, compile_sketch's `border`): the
    same, softly: a leftover edge cell is still cut freely when nothing matches (_tile_trees'
    `soft`). A grove that touches an edge is also tiled on each of the four 2x2 grids, so a band a
    row or column off the border's grid can give up a cell on its inner fringe (the forest's edge
    moves by a row) to line up with the border's trees. The tiling kept is the one with the fewest
    cells dropped at an edge with forest inside them (a strip of grass against the trees beyond,
    often a new walkway along the edge), then the lowest cost: two for each edge tree out of
    line with the border, one for each cell dropped anywhere; ties keep the old placement, then
    the plain greedy tiling."""
    border, outside = border or {}, outside or {}
    soft = frozenset(border) - frozenset(outside)      # a neighbour's strip always wins
    outside = {**border, **outside}
    if not hint and not outside:
        return _tile_trees(cls_grid, w, h, None)
    seen, dropped = set(), 0
    scratch = [["X"] * w for _ in range(h)]
    for y0 in range(h):
        for x0 in range(w):
            if cls_grid[y0][x0] != "T" or (x0, y0) in seen:
                continue
            comp, stack = [], [(x0, y0)]
            seen.add((x0, y0))
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and cls_grid[ny][nx] == "T":
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            # tile the grove alone, on one shared scratch grid, within its bounding box
            box = (min(x for x, _ in comp), min(y for _, y in comp),
                   max(x for x, _ in comp), max(y for _, y in comp))
            at_edge = lambda x, y: x in (0, w - 1) or y in (0, h - 1)

            def strip_drops(result):
                """Cells dropped at an edge with a tree on their inner side (grass between the
                forest and what lies past the edge; a corner given up on the fringe is harmless),
                or on a connected seam where the neighbour's cell is open ground (a gap there can
                open a way between the maps) or half a tree whose other half is this cell."""
                n = 0
                if not outside:                 # no context: the old choice (fewest dropped)
                    return 0
                for (x, y), q in result.items():
                    if q != "G" or not at_edge(x, y):
                        continue
                    inward = [(x + (x == 0) - (x == w - 1), y), (x, y + (y == 0) - (y == h - 1))]
                    seam = False
                    for dx, dy, into in ((-1, 0, "L"), (1, 0, "R"), (0, -1, "T"), (0, 1, "B")):
                        o = (x + dx, y + dy)
                        if o in outside and o not in soft:
                            lab = outside[o]
                            seam |= lab not in QUARTERS or into in lab
                    n += seam or any(result.get(c, "G") in QUARTERS for c in inward if c != (x, y))
                return n
            variants = ([(hint, None)] if hint else []) + [(None, None)]
            if outside and any(at_edge(x, y) for x, y in comp):
                variants += [(None, g) for g in ((0, 0), (1, 0), (0, 1), (1, 1))]
            trials = []
            for hh, grid in variants:
                for x, y in comp:
                    scratch[y][x] = "T"
                n = _tile_trees(scratch, w, h, hh, box, outside, grid, soft)
                result = {(x, y): scratch[y][x] for x, y in comp}
                # a tree out of line with the border shows at the edge; a fringe cell given up
                # moves the forest's edge by a row: one counts as two dropped cells, so a grove
                # isn't stripped of its staggered fringe to line up one tree
                cost = 2 * misaligned(result, border) + n
                trials.append(((strip_drops(result), cost), result, n))
                for x, y in comp:
                    scratch[y][x] = "X"
            _, result, n = min(trials, key=lambda t: t[0])    # ties: the first (the old placement)
            dropped += n
            for (x, y), q in result.items():
                cls_grid[y][x] = q
    return dropped


def _tile_trees(cls_grid, w, h, hint, box=None, outside=None, grid=None, soft=frozenset()):
    """box (x0, y0, x1, y1): only cells in it can be forest; loops stay inside it.
    outside: classes past the edges (a neighbour's or the border's); there a cut tree's off-map
    half must be the matching quarter (an edge with no labels cuts trees freely).
    soft: off-map cells whose labels are the border's: a leftover edge cell that matches nothing
    is still cut there (the old free cut, a seam vanilla never draws) rather than dropped to grass,
    which would open a strip between the forest and the border's trees.
    grid (gx, gy): whole trees inside the map only with their top-left at x = gx, y = gy mod 2."""
    x0, y0, x1, y1 = box or (0, 0, w - 1, h - 1)
    inside = lambda x, y: 0 <= x < w and 0 <= y < h
    outside = outside or {}

    def place(x, y, allow_offmap, free=frozenset()):
        if grid and not allow_offmap and ((x - grid[0]) % 2 or (y - grid[1]) % 2):
            return
        quad = [(x, y, "TL"), (x + 1, y, "TR"), (x, y + 1, "BL"), (x + 1, y + 1, "BR")]
        ok = all((inside(qx, qy) and cls_grid[qy][qx] == "T") or
                 (allow_offmap and not inside(qx, qy) and
                  ((qx, qy) in free or outside.get((qx, qy), q) == q))
                 for qx, qy, q in quad)
        if ok and any(inside(qx, qy) for qx, qy, _ in quad):
            for qx, qy, q in quad:
                if inside(qx, qy):
                    cls_grid[qy][qx] = q

    if hint:                        # pass 0: keep the existing map's tree placement where unchanged
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if cls_grid[y][x] == "T" and hint[y][x] in ("TL", "TR", "BL", "BR"):
                    cls_grid[y][x] = "t" + hint[y][x]       # provisional
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                c = cls_grid[y][x]
                if not c.startswith("t"):
                    continue
                # a provisional quarter is kept only if its whole tree is still forest in the sketch
                # (and a half off the map is what lies there: the neighbour's or the border's)
                q = c[1:]
                ox, oy = x - (q[1] == "R"), y - (q[0] == "B")
                ok = all(outside.get((ox + dx, oy + dy), qq) == qq if not inside(ox + dx, oy + dy) else
                         cls_grid[oy + dy][ox + dx] in ("t" + qq, qq)
                         for dx, dy, qq in ((0, 0, "TL"), (1, 0, "TR"), (0, 1, "BL"), (1, 1, "BR")))
                cls_grid[y][x] = q if ok else "T"
    for y in range(y0, y1 + 1):     # pass 1: whole trees inside the map
        for x in range(x0, x1 + 1):
            place(x, y, False)
    # pass 2: leftovers at the edges become trees cut by the border, the least-cut first. A tree
    # cut by one border must not be taken as one cut by two: a half tree in the top band at the
    # right edge read as cut by the top border (from row -1) orphans its lower cell, and a row of
    # tree tops along the bottom read from x = -1 pairs every top with the wrong neighbour.
    # Only a tree whose top-left is at x = -1 or w - 1 (or y = -1 or h - 1) can be cut, so only
    # those lines are visited.
    # Pass 3 (with `soft`): what's left beside the border is cut anyway.
    xs = [x for x in (-1, w - 1) if x0 - 1 <= x <= x1]
    ys = [y for y in (-1, h - 1) if y0 - 1 <= y <= y1]
    for free in (frozenset(), soft) if soft else (frozenset(),):
        for x in xs:                                 # cut by the left or right border
            for y in range(y0, min(y1, h - 2) + 1):
                place(x, y, True, free)
        for y in ys:                                 # cut by the top or bottom border
            for x in range(max(x0, 0), min(x1, w - 2) + 1):
                place(x, y, True, free)
        for y in ys:                                 # the corners
            for x in xs:
                place(x, y, True, free)
    dropped = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if cls_grid[y][x] == "T":
                cls_grid[y][x] = "G"
                dropped += 1
    return dropped


def compile_sketch(project, corpus, rules, sketch, layout, vocab=None, forbidden=None, fresh=False,
                   seams=None, border=None):
    """Sketch -> new block list for `layout` (same size). Returns (blocks, report dict).
    vocab + not fresh: keep the layout's existing tree placement where the sketch keeps forest.
    forbidden: class pairs to repair with a grass margin (terrain.enforce_grammar).
    Raises SketchError if the ledges can't be built as drawn (shape, or a landing that isn't
    walkable). Ledge warnings (a ledge nobody can reach) go in the report.
    seams: {(x, y): class} for the cells just across each connected edge (seams.outside_labels):
    edge cells are tiled for what the player sees beyond them, and trees are cut by a connected
    edge only where the neighbour holds the other half. None: off the map is unknown (OUT).
    border: {(x, y): class} for the cells past the edges no neighbour covers (seams.border_labels:
    the border's trees, edge water): edge cells are tiled for them too, and trees cut there line up
    with the border's where the forest allows (assign_tree_quarters)."""
    outside = {**(border or {}), **(seams or {})} or None
    from .terrain import enforce_grammar, PRIMARY
    w, h = sketch.w, sketch.h
    if (w, h) != (layout.width, layout.height):
        raise ValueError(f"sketch is {w}x{h} but layout is {layout.width}x{layout.height}")
    # buildings: the stamps' blocks stand in for the layout's under their `B` cells
    stamp_blocks, stamp_problems = stamps.resolve(project, sketch.rows, sketch.stamps, layout)
    if stamp_problems:
        raise SketchError(stamp_problems)
    kept = lambda x, y: stamp_blocks.get((x, y), layout.get(x, y))     # the block of a kept cell
    kept_mid = lambda x, y: kept(x, y) & 0x3FF
    # cliffs: walls and stairs by shape and level (a ledge's end runs under a wall)
    cliff_pieces, cliff_problems = cliffs.resolve(sketch.rows, sketch.levels, w, h)
    if cliff_pieces and layout.primary != PRIMARY:
        raise SketchError([(*min(cliff_pieces), f"cliffs need {PRIMARY} as the primary tileset, "
                                                f"not {layout.primary}")])
    if cliff_problems:
        raise SketchError(cliff_problems)
    if cliff_pieces:
        cliffs.verify_tileset(project, layout.tiles)
    runs_into = cliffs.runs_into(sketch.rows, w, h, ledges.runs_into_kept(sketch.rows, w, h, kept_mid))
    pieces, problems = ledges.resolve(sketch.rows, w, h, runs_into)
    if pieces and layout.primary != PRIMARY:
        raise SketchError([(0, 0, f"ledges need {PRIMARY} as the primary tileset, not {layout.primary}")])
    if problems:
        raise SketchError(problems)
    if pieces:
        ledges.verify_tileset(project, layout.tiles)
    cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sketch.rows]
    repaired = {}                       # cell -> (class the sketch drew, the cell that outranked it)
    grammar = dict(enforce_grammar(cls, w, h, forbidden, where=repaired)) if forbidden else {}
    hint = grid_labels(vocab, layout.entry, layout.blocks, w, h) if vocab and not fresh else None
    dropped = assign_tree_quarters(cls, w, h, hint, outside=seams, border=border)
    # flora (flowers, boulders, saplings): resolved by shape; for everything else they read as grass
    fpieces, flora_errors = flora.resolve(cls, w, h)
    if fpieces and layout.primary != PRIMARY:
        raise SketchError([(0, 0, f"flowers, boulders and saplings need {PRIMARY} as the primary tileset")])
    if flora_errors:
        raise SketchError(flora_errors)
    # judged on the final classes: grammar repair and leftover forest can change a landing tile
    tp = layout.tiles
    kept_walkable = lambda x, y: (kept(x, y) >> 10) & 3 == 0 and not \
        project.tile_flags.get(tp.behavior(kept_mid(x, y)), 0) & TILE_FLAG_SURFABLE
    ledge_errors, ledge_warnings = ledges.design_issues(flora.walk_view(cls, fpieces), pieces, w, h,
                                                        kept_walkable)
    if ledge_errors:
        raise SketchError(ledge_errors)
    # levels: walkable ground changes level only through a wall, a ledge, stairs or a graded road
    level_errors = cliffs.level_issues(flora.walk_view(cls, fpieces), sketch.levels, w, h)
    if level_errors:
        raise SketchError(level_errors)
    gview = flora.grass_view(cls) if fpieces else cls
    # to the learned rules, banks and bridges a wall is land, like grass: vanilla's ground beside
    # these walls is plain grass (069 N, 070 W, 072 E: 001 in nearly every case), and a wall never
    # touches water
    if cliff_pieces:
        gview = [[("G" if c in cliffs.CLASSES else c) for c in row] for row in gview]
    # bridges: the deck's pieces by shape; the deck reads as water for the shores below
    bridge_cells = {(x, y) for y, row in enumerate(sketch.rows) for x, ch in enumerate(row)
                    if ch == bridges.CHAR}
    bridge_mids, bridge_below = {}, {}
    if bridge_cells:
        if layout.primary != PRIMARY:
            raise SketchError([(*min(bridge_cells), f"bridges need {PRIMARY} as the primary tileset")])
        ids, why = bridges.piece_ids(project, layout)
        if why:
            raise SketchError([(*min(bridge_cells), why)])
        bp, bridge_below, bridge_errors = bridges.resolve(gview, bridge_cells, w, h, ends=cls)
        if bridge_errors:
            raise SketchError(bridge_errors)
        bridge_mids = {c: ids[m] for c, m in bp.items()}
    # shores: rocks in the water, then the shapes of banks and beaches (on the final classes)
    rocks, rock_errors = shores.place_rocks(gview, w, h)
    _, _, _, shore_errors = shores.resolve(gview, w, h)
    has_water = any(c == shores.WATER_CLS for row in cls for c in row)
    if rocks and layout.primary != PRIMARY:
        raise SketchError([(0, 0, f"water rocks need {PRIMARY} as the primary tileset")])
    if layout.primary != PRIMARY:
        shore_errors = []              # (no General water class exists on other primaries)
    if rock_errors or shore_errors:
        raise SketchError(sorted(set(rock_errors + shore_errors)))
    pieces = {**pieces, **rocks}
    keep = [[pieces.get((x, y)) or kept_mid(x, y) for x in range(w)] for y in range(h)]
    learn_view = shores.learning_view(gview) if rocks else gview
    if stamp_blocks:
        # vanilla's buildings stand on plain grass: to the learned rules a stamp reads as grass,
        # so its neighbours are tiled as if beside a lawn (as kept "F" they would copy whatever
        # vanilla drew beside any object: steps, fences, ledges). The stamp's own blocks still
        # come from `kept` below.
        learn_view = [[("G" if (x, y) in stamp_blocks else c) for x, c in enumerate(row)]
                      for y, row in enumerate(learn_view)]
    # vanilla labels its cliff stairs as grass, and a sapling's crown top (walk-behind): the rules must
    # never draw either in open ground (a lone crown showed beside a kept cliff once a sapling there
    # became grass: terrain-rules)
    mids, levels = autotile(rules, learn_view, w, h, keep, exclude=NEVER_GRASS, outside=outside)
    shore_tiles = 0
    if has_water and layout.primary == PRIMARY:
        view = shores.sand_view(learn_view, w, h)
        sand_mids = autotile(rules, view, w, h, keep, exclude=NEVER_GRASS, outside=outside)[0] \
            if view != learn_view else None
        shore_tiles = shores.apply(gview, mids, w, h, sand_mids)
    if fpieces:
        bad_spots = flora.placement_errors(fpieces, mids)
        if bad_spots:
            raise SketchError(bad_spots)
        for (x, y), mid in fpieces.items():
            mids[y][x] = mid
    for (x, y), mid in {**bridge_mids, **bridge_below}.items():
        mids[y][x] = mid
    blocks = []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c == "F":
                blocks.append(kept(x, y))
                continue
            if c in cliffs.CLASSES:
                blocks.append(pack(cliff_pieces[(x, y)],
                                   *(cliffs.WALL_ATTRS if c == "CL" else cliffs.STAIR_ATTRS)))
                continue
            mid = mids[y][x]
            if (x, y) in bridge_mids:
                blocks.append(pack(mid, *bridges.ATTRS))
                continue
            if c in flora.CLASSES:
                blocks.append(pack(mid, *flora.ATTRS[mid]))
                continue
            if c == "LD":
                # always solid; vanilla uses elevation 0 or 3 for ledges, so a cell that already
                # holds a ledge keeps its elevation (re-building a map doesn't touch it)
                old = layout.get(x, y)
                elev = old >> 12 if (old & 0x3FF) in ledges.PIECES else CLASS_ATTRS["LD"][1]
                attrs = (CLASS_ATTRS["LD"][0], elev)
            elif c == shores.ROCK_CLS:
                # always solid; vanilla's water rocks sit at elevation 0 or 1, so an unchanged
                # rock keeps its elevation
                old = layout.get(x, y)
                elev = old >> 12 if (old & 0x3FF) == mid else CLASS_ATTRS[c][1]
                attrs = (CLASS_ATTRS[c][0], elev)
            elif c == "S" and layout.mid(x, y) == mid and layout.get(x, y) >> 12 == 1:
                # unchanged water at the water elevation keeps its collision (vanilla blocks a
                # few water cells, e.g. beside bridges on Route 119)
                attrs = ((layout.get(x, y) >> 10) & 3, 1)
            else:
                attrs = corpus.default_attrs(layout.entry, mid) or CLASS_ATTRS[c]
            blocks.append(pack(mid, *attrs))
    # every door must face walkable ground (judged on the final blocks)
    door_errors = stamps.door_problems(project, sketch.stamps, lambda x, y: blocks[y * w + x], w, h, tp)
    if door_errors:
        raise SketchError(door_errors)
    report = {"dropped_tree_cells": dropped, "grammar_repairs": grammar, "rule_levels": dict(levels),
              "grammar_cells": repaired}
    if sketch.stamps:
        report["buildings"] = len(sketch.stamps)
    if bridge_mids:
        report["bridge_tiles"] = len(bridge_mids)
    if cliff_pieces:
        report["cliff_tiles"] = sum(m in cliffs.WALL_PIECES for m in cliff_pieces.values())
        report["stair_tiles"] = sum(m in cliffs.STAIR_PIECES for m in cliff_pieces.values())
    if len(pieces) > len(rocks):
        report["ledge_tiles"] = len(pieces) - len(rocks)
    if shore_tiles or rocks:
        report["shore_tiles"] = shore_tiles
        report["water_rocks"] = len(rocks) // 4
    if fpieces:
        report["flora"] = {"flowers": sum(m == flora.FLOWER for m in fpieces.values()),
                           "boulders": sum(m == flora.BOULDER for m in fpieces.values()),
                           "saplings": sum(m == flora.TRUNK for m in fpieces.values()),
                           **({"signs": n} if (n := sum(m == flora.SIGN for m in fpieces.values())) else {})}
    if ledge_warnings:
        report["ledge_warnings"] = [f"({x},{y}) {m}" for x, y, m in ledge_warnings]
    return blocks, report
