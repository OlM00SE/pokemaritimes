"""Map sketches: human-readable terrain grids that compile to map.bin.

File format (design/maps/<Map>.txt):
    // map: Route203_1                <- target map folder
    // any other '//' lines are comments
    TTTTTTTT....~~~~
    ...

Legend (one character per metatile):
    .  grass            ,  tall grass (encounters)     =  light path      :  sand / dirt
    ~  river/sea water  o  pond water                  T  forest (auto 2x2 trees)
    #  keep the map's current block unchanged (buildings, signs, rocks, ledges, ...)
"""
from .terrain import TREE, Rules, autotile, Vocabulary, grid_labels
from .layout import pack

CHAR_TO_CLASS = {".": "G", ",": "TG", "=": "P", ":": "SA", "~": "S", "o": "W", "T": "T", "#": "F"}
CLASS_TO_CHAR = {"G": ".", "TG": ",", "P": "=", "SA": ":", "S": "~", "W": "o",
                 "TL": "T", "TR": "T", "BL": "T", "BR": "T", "F": "#"}
CLASS_ATTRS = {"G": (0, 3), "TG": (0, 3), "P": (0, 3), "SA": (0, 3), "S": (0, 1), "W": (0, 1),
               "TL": (1, 0), "TR": (1, 0), "BL": (1, 0), "BR": (1, 0)}


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
    hand-placed details (decorations, small trees, special variants) survive a round trip."""
    m = project.load_map(map_name)
    L = m.layout
    lab = grid_labels(vocab, L.entry, L.blocks, L.width, L.height)
    rows = []
    for y, row in enumerate(lab):
        out = []
        for x, c in enumerate(row):
            if rules and c not in ("F", "TL", "TR", "BL", "BR") and L.mid(x, y) not in rules.outputs(c):
                c = "F"
            out.append(CLASS_TO_CHAR[c])
        rows.append("".join(out))
    return Sketch(map_name, rows)


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
    forbidden: class pairs to repair with a grass margin (terrain.enforce_grammar)."""
    from .terrain import enforce_grammar
    w, h = sketch.w, sketch.h
    if (w, h) != (layout.width, layout.height):
        raise ValueError(f"sketch is {w}x{h} but layout is {layout.width}x{layout.height}")
    cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sketch.rows]
    grammar = dict(enforce_grammar(cls, w, h, forbidden)) if forbidden else {}
    hint = grid_labels(vocab, layout.entry, layout.blocks, w, h) if vocab and not fresh else None
    dropped = assign_tree_quarters(cls, w, h, hint)
    keep = [[layout.mid(x, y) for x in range(w)] for y in range(h)]
    mids, levels = autotile(rules, cls, w, h, keep)
    blocks = []
    for y in range(h):
        for x in range(w):
            c = cls[y][x]
            if c == "F":
                blocks.append(layout.get(x, y))
                continue
            mid = mids[y][x]
            attrs = corpus.default_attrs(layout.entry, mid) or CLASS_ATTRS[c]
            blocks.append(pack(mid, *attrs))
    return blocks, {"dropped_tree_cells": dropped, "grammar_repairs": grammar, "rule_levels": dict(levels)}
