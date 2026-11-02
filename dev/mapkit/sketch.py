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
    #  keep the map's current block unchanged (buildings, signs, rocks, ...)
Sand (':') that touches river/sea water ('~') becomes a beach; grass banks and beaches are built
by shape (mapkit/shores.py).
"""
from .terrain import TREE, Rules, autotile, Vocabulary, grid_labels, PRIMARY
from .layout import pack
from .project import TILE_FLAG_SURFABLE
from . import ledges, shores

CHAR_TO_CLASS = {".": "G", ",": "TG", "=": "P", ":": "SA", "~": "S", "o": "W", "T": "T", "#": "F",
                 "v": "LD", "<": "LD", ">": "LD", shores.ROCK_CHAR: shores.ROCK_CLS}
CLASS_TO_CHAR = {"G": ".", "TG": ",", "P": "=", "SA": ":", "S": "~", "W": "o",
                 "TL": "T", "TR": "T", "BL": "T", "BR": "T", "F": "#",
                 shores.ROCK_CLS: shores.ROCK_CHAR}                      # LD: ledges.piece_char
CLASS_ATTRS = {"G": (0, 3), "TG": (0, 3), "P": (0, 3), "SA": (0, 3), "S": (0, 1), "W": (0, 1),
               "TL": (1, 0), "TR": (1, 0), "BL": (1, 0), "BR": (1, 0), "LD": ledges.LEDGE_ATTRS,
               shores.ROCK_CLS: (1, 0)}


class SketchError(ValueError):
    """The sketch can't be built as drawn; .problems lists (x, y, message)."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(f"  ({x},{y}) {m}" for x, y, m in problems))


class Sketch:
    def __init__(self, map_name, rows, comments=()):
        self.map_name, self.rows, self.comments = map_name, [list(r) for r in rows], list(comments)

    @property
    def w(self): return len(self.rows[0])
    @property
    def h(self): return len(self.rows)

    @classmethod
    def load(cls, path):
        name, rows, comments = None, [], []
        for line in open(path, encoding="utf-8").read().splitlines():
            if line.startswith("//"):
                if line[2:].strip().lower().startswith("map:"):
                    name = line.split(":", 1)[1].strip()
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
        return cls(name, rows, comments)

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"// map: {self.map_name}\n")
            for c in self.comments:
                f.write(c + "\n")
            for r in self.rows:
                f.write("".join(r) + "\n")

    # ---- editing helpers for procedural design scripts ----
    def fill(self, x0, y0, x1, y1, ch):
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.rows[y][x] = ch

    def get(self, x, y): return self.rows[y][x]

    def set(self, x, y, ch):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x] = ch


def extract(project, vocab, map_name, rules=None):
    """Existing map -> sketch. Cells outside the vocabulary become '#' (kept as-is). With
    `rules`, cells whose exact tile the generator could never produce also become '#', so
    hand-placed details (decorations, small trees, special variants) survive a round trip.
    Ledges extract as v/</>; any ledge group the resolver would not rebuild tile for tile
    (e.g. Route 118's cliff pieces) is kept as '#'."""
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
            elif rules and c not in ("F", "S", "TL", "TR", "BL", "BR") and mid not in rules.outputs(c):
                c = "F"                     # (water is judged by shape, below)
            out.append(CLASS_TO_CHAR[c])
        rows.append(out)
    keep_unrebuildable_ledges(rows, L.width, L.height, lambda x, y: L.mid(x, y))
    sk = Sketch(map_name, ["".join(r) for r in rows])
    if L.primary == PRIMARY and rules:
        shores.keep_unrebuildable(sk.rows, L.width, L.height, lambda x, y: L.mid(x, y),
                                  lambda ch: CHAR_TO_CLASS[ch])
        keep_unrebuildable_shore_blocks(project, vocab, rules, sk, L)
    return sk


def keep_unrebuildable_shore_blocks(project, vocab, rules, sk, layout, max_rounds=6):
    """Compile the extracted sketch and keep ('#') every shore cell (water, rocks, and sand or
    grass beside water) whose block wouldn't come back exactly: e.g. vanilla beach sand that
    meets grass without a rim, or sand at elevation 0. Repeats until a compile reproduces
    them all, so extract -> compile never changes a shore block."""
    from .corpus import Corpus
    corpus = Corpus(project)
    w, h = sk.w, sk.h
    for _ in range(max_rounds):
        blocks, _ = compile_sketch(project, corpus, rules, sk, layout, vocab)
        cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sk.rows]
        bad = [(x, y) for y in range(h) for x in range(w)
               if (cls[y][x] in ("S", shores.ROCK_CLS) or
                   (cls[y][x] in ("SA", "G") and shores.touches_water(cls, x, y, w, h)))
               and blocks[y * w + x] != layout.get(x, y)]
        if not bad:
            return
        for x, y in bad:
            sk.rows[y][x] = "#"
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
    tree and become grass (returned as a count, so designers can see what was dropped)."""
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
        for y in range(h):
            for x in range(w):
                if cls_grid[y][x] == "T" and hint[y][x] in ("TL", "TR", "BL", "BR"):
                    cls_grid[y][x] = "t" + hint[y][x]       # provisional
        for y in range(h):
            for x in range(w):
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
    for y in range(h):              # pass 1: whole trees inside the map
        for x in range(w):
            place(x, y, False)
    for y in range(-1, h):          # pass 2: leftovers at the edges become trees cut by the border
        for x in range(-1, w):
            place(x, y, True)
    dropped = 0
    for y in range(h):
        for x in range(w):
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
    pieces, problems = ledges.resolve(sketch.rows, w, h, ledges.runs_into_kept(sketch.rows, w, h, layout.mid))
    if pieces and layout.primary != PRIMARY:
        raise SketchError([(0, 0, f"ledges need {PRIMARY} as the primary tileset, not {layout.primary}")])
    if problems:
        raise SketchError(problems)
    if pieces:
        ledges.verify_tileset(project, layout.tiles)
    cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sketch.rows]
    grammar = dict(enforce_grammar(cls, w, h, forbidden)) if forbidden else {}
    hint = grid_labels(vocab, layout.entry, layout.blocks, w, h) if vocab and not fresh else None
    dropped = assign_tree_quarters(cls, w, h, hint)
    # judged on the final classes: grammar repair and leftover forest can change a landing tile
    tp = layout.tiles
    kept_walkable = lambda x, y: layout.coll(x, y) == 0 and not \
        project.tile_flags.get(tp.behavior(layout.mid(x, y)), 0) & TILE_FLAG_SURFABLE
    ledge_errors, ledge_warnings = ledges.design_issues(cls, pieces, w, h, kept_walkable)
    if ledge_errors:
        raise SketchError(ledge_errors)
    # shores: rocks in the water, then the shapes of banks and beaches (on the final classes)
    rocks, rock_errors = shores.place_rocks(cls, w, h)
    _, _, _, shore_errors = shores.resolve(cls, w, h)
    has_water = any(c == shores.WATER_CLS for row in cls for c in row)
    if rocks and layout.primary != PRIMARY:
        raise SketchError([(0, 0, f"water rocks need {PRIMARY} as the primary tileset")])
    if layout.primary != PRIMARY:
        shore_errors = []              # (no General water class exists on other primaries)
    if rock_errors or shore_errors:
        raise SketchError(sorted(set(rock_errors + shore_errors)))
    pieces = {**pieces, **rocks}
    keep = [[pieces.get((x, y)) or layout.mid(x, y) for x in range(w)] for y in range(h)]
    learn_view = shores.learning_view(cls) if rocks else cls
    mids, levels = autotile(rules, learn_view, w, h, keep)
    shore_tiles = 0
    if has_water and layout.primary == PRIMARY:
        view = shores.sand_view(learn_view, w, h)
        sand_mids = autotile(rules, view, w, h, keep)[0] if view != learn_view else None
        shore_tiles = shores.apply(cls, mids, w, h, sand_mids)
    blocks = []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c == "F":
                blocks.append(layout.get(x, y))
                continue
            mid = mids[y][x]
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
    report = {"dropped_tree_cells": dropped, "grammar_repairs": grammar, "rule_levels": dict(levels)}
    if len(pieces) > len(rocks):
        report["ledge_tiles"] = len(pieces) - len(rocks)
    if shore_tiles or rocks:
        report["shore_tiles"] = shore_tiles
        report["water_rocks"] = len(rocks) // 4
    if ledge_warnings:
        report["ledge_warnings"] = [f"({x},{y}) {m}" for x, y, m in ledge_warnings]
    return blocks, report
