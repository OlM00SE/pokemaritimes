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
    #  keep the map's current block unchanged (hand-painted pieces, ...)
Sand (':') that touches river/sea water ('~') becomes a beach; grass banks and beaches are built
by shape (mapkit/shores.py). Flora stands on plain grass only.
Buildings: `// stamp: pokemon_center @ 10,4 -> Woodstock_PokemonCenter_1F` places a catalog
building with its top-left at (10, 4); its cells are drawn `B`. Sketch.place() does both.
"""
from .terrain import TREE, TREE_Q, Rules, autotile, Vocabulary, grid_labels, PRIMARY
from .layout import pack
from .project import TILE_FLAG_SURFABLE
from . import ledges, shores, flora, stamps

CHAR_TO_CLASS = {".": "G", ",": "TG", "=": "P", ":": "SA", "~": "S", "o": "W", "T": "T", "#": "F",
                 "v": "LD", "<": "LD", ">": "LD", shores.ROCK_CHAR: shores.ROCK_CLS,
                 stamps.CHAR: "F", **flora.CHAR_CLASS}
CLASS_TO_CHAR = {"G": ".", "TG": ",", "P": "=", "SA": ":", "S": "~", "W": "o",
                 "TL": "T", "TR": "T", "BL": "T", "BR": "T", "F": "#",
                 shores.ROCK_CLS: shores.ROCK_CHAR, **flora.CLASS_CHAR}   # LD: ledges.piece_char
CLASS_ATTRS = {"G": (0, 3), "TG": (0, 3), "P": (0, 3), "SA": (0, 3), "S": (0, 1), "W": (0, 1),
               "TL": (1, 0), "TR": (1, 0), "BL": (1, 0), "BR": (1, 0), "LD": ledges.LEDGE_ATTRS,
               shores.ROCK_CLS: (1, 0)}


class SketchError(ValueError):
    """The sketch can't be built as drawn; .problems lists (x, y, message)."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(f"  ({x},{y}) {m}" for x, y, m in problems))


class Sketch:
    def __init__(self, map_name, rows, comments=(), placements=()):
        self.map_name, self.rows, self.comments = map_name, [list(r) for r in rows], list(comments)
        self.stamps = list(placements)          # [stamps.Placement]: the buildings

    @property
    def w(self): return len(self.rows[0])
    @property
    def h(self): return len(self.rows)

    @classmethod
    def load(cls, path):
        name, rows, comments, placements = None, [], [], []
        for line in open(path, encoding="utf-8").read().splitlines():
            if line.startswith("//"):
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
        return cls(name, rows, comments, placements)

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"// map: {self.map_name}\n")
            for pl in self.stamps:
                f.write(pl.line() + "\n")
            for c in self.comments:
                f.write(c + "\n")
            for r in self.rows:
                f.write("".join(r) + "\n")

    def place(self, project, name, x, y, interior=None):
        """Put building stamp `name` with its top-left at (x, y): draws its cells `B` and adds
        the `// stamp:` line. `interior` names the room behind the door (created by
        `mapgen --apply` from the stamp's interior template if it doesn't exist). Returns the
        stamp's door (x, y). ValueError if it's unknown, runs off the sketch or overlaps
        another stamp; compile checks the rest (tilesets, the ground in front of the door)."""
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
        for cx, cy in fp:
            self.rows[cy][cx] = stamps.CHAR
        self.stamps.append(stamps.Placement(name, x, y, interior))
        return st.door_at(x, y)

    # ---- editing helpers for procedural design scripts ----
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
    keep_unrebuildable_ledges(rows, L.width, L.height, lambda x, y: L.mid(x, y))
    sk = Sketch(map_name, ["".join(r) for r in rows], placements=recognise_stamps(project, m, rows))
    if L.primary == PRIMARY and rules:
        shores.keep_unrebuildable(sk.rows, L.width, L.height, lambda x, y: L.mid(x, y),
                                  lambda ch: CHAR_TO_CLASS[ch])
        if verify_shores:
            keep_unrebuildable_shore_blocks(project, vocab, rules, sk, L, forbidden, corpus)
    return sk


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


def keep_unrebuildable_shore_blocks(project, vocab, rules, sk, layout, forbidden=None, corpus=None):
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
            blocks, report = compile_sketch(project, corpus, rules, sk, layout, vocab, forbidden)
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


def assign_tree_quarters(cls_grid, w, h, hint=None):
    """Turn 'T' cells into whole 2x2 trees (TL TR / BL BR). Greedy row-major tiling: the first
    free T cell becomes a tree's top-left if the 2x2 block from it is all free T. This places
    trees at any alignment (single trees, staggered rows). Leftover T cells can't hold a whole
    tree and become grass (returned as a count, so designers can see what was dropped).
    A sketch drawn as whole non-overlapping 2x2 trees always comes back tree for tree.
    hint (the existing map's labels): each grove (a 4-connected group of T cells) keeps the old
    map's tree placement if that drops no more cells than tiling it afresh. A redesigned grove
    edge, e.g. staggered trees beside old aligned ones, is tiled afresh, so old trees that
    straddle the new ones don't knock them out."""
    if not hint:
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
            trials = []
            for hh in (hint, None):
                for x, y in comp:
                    scratch[y][x] = "T"
                n = _tile_trees(scratch, w, h, hh, box)
                trials.append((n, {(x, y): scratch[y][x] for x, y in comp}))
                for x, y in comp:
                    scratch[y][x] = "X"
            n, result = min(trials, key=lambda t: t[0])     # ties keep the old placement (first)
            dropped += n
            for (x, y), q in result.items():
                cls_grid[y][x] = q
    return dropped


def _tile_trees(cls_grid, w, h, hint, box=None):
    """box (x0, y0, x1, y1): only cells in it can be forest; loops stay inside it."""
    x0, y0, x1, y1 = box or (0, 0, w - 1, h - 1)
    inside = lambda x, y: 0 <= x < w and 0 <= y < h

    def place(x, y, allow_offmap):
        quad = [(x, y, "TL"), (x + 1, y, "TR"), (x, y + 1, "BL"), (x + 1, y + 1, "BR")]
        ok = all((inside(qx, qy) and cls_grid[qy][qx] == "T") or (allow_offmap and not inside(qx, qy))
                 for qx, qy, _ in quad)
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
                q = c[1:]
                ox, oy = x - (q[1] == "R"), y - (q[0] == "B")
                ok = all(not inside(ox + dx, oy + dy) or
                         cls_grid[oy + dy][ox + dx] in ("t" + qq, qq)
                         for dx, dy, qq in ((0, 0, "TL"), (1, 0, "TR"), (0, 1, "BL"), (1, 1, "BR")))
                cls_grid[y][x] = q if ok else "T"
    for y in range(y0, y1 + 1):     # pass 1: whole trees inside the map
        for x in range(x0, x1 + 1):
            place(x, y, False)
    for y in range(y0 - 1, y1 + 1):  # pass 2: leftovers at the edges become trees cut by the border
        for x in range(x0 - 1, x1 + 1):
            place(x, y, True)
    dropped = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if cls_grid[y][x] == "T":
                cls_grid[y][x] = "G"
                dropped += 1
    return dropped


def compile_sketch(project, corpus, rules, sketch, layout, vocab=None, forbidden=None, fresh=False):
    """Sketch -> new block list for `layout` (same size). Returns (blocks, report dict).
    vocab + not fresh: keep the layout's existing tree placement where the sketch keeps forest.
    forbidden: class pairs to repair with a grass margin (terrain.enforce_grammar).
    Raises SketchError if the ledges can't be built as drawn (shape, or a landing that isn't
    walkable). Ledge warnings (a ledge nobody can reach) go in the report."""
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
    pieces, problems = ledges.resolve(sketch.rows, w, h, ledges.runs_into_kept(sketch.rows, w, h, kept_mid))
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
    dropped = assign_tree_quarters(cls, w, h, hint)
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
    gview = flora.grass_view(cls) if fpieces else cls
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
    mids, levels = autotile(rules, learn_view, w, h, keep)
    shore_tiles = 0
    if has_water and layout.primary == PRIMARY:
        view = shores.sand_view(learn_view, w, h)
        sand_mids = autotile(rules, view, w, h, keep)[0] if view != learn_view else None
        shore_tiles = shores.apply(gview, mids, w, h, sand_mids)
    if fpieces:
        bad_spots = flora.placement_errors(fpieces, mids)
        if bad_spots:
            raise SketchError(bad_spots)
        for (x, y), mid in fpieces.items():
            mids[y][x] = mid
    blocks = []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c == "F":
                blocks.append(kept(x, y))
                continue
            mid = mids[y][x]
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
