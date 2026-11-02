"""Terrain language: semantic classes <-> metatiles, with rules learned from vanilla maps.

A map is described as a grid of terrain classes. The auto-tiler picks each cell's metatile
from rules mined from vanilla Emerald: for a cell of class C whose 8 neighbours have classes
(n0..n7), use the metatile vanilla most often used in exactly that situation. Fallbacks:
4-neighbourhood, then the class's most common tile.

Classes (gTileset_General primary; v1 covers route terrain):
  G   grass / open ground (incl. canopy-overhang and bank-shadow variants)
  TG  tall grass (wild encounters)
  P   light sand path patch (3x3 autotile family)
  W   pond water (MB_POND_WATER family, brown banks)
  S   river/sea water (other surfable General water, blue banks)
  TL TR BL BR   tree quarters (Emerald trees are 2x2 metatiles)
  F   anything else: kept literally (buildings, rocks, signs, ledges...)
"""
import os, pickle, struct
from collections import Counter, defaultdict
from .project import NUM_METATILES_IN_PRIMARY, TILE_FLAG_SURFABLE

PRIMARY = "gTileset_General"
TREE = {"TL": {0x1D4, 0x1D6}, "TR": {0x1D5, 0x1D7},
        "BL": {0x1DC, 0x1E4, 0x1E6, 0x1F3}, "BR": {0x1DD, 0x1E5, 0x1E7, 0x1F2}}
PATH = {0x1D0, 0x1D1, 0x1D2, 0x1D8, 0x1D9, 0x1DA, 0x1E0, 0x1E1, 0x1E2}
SAND = {0x118, 0x119, 0x11A, 0x120, 0x121, 0x122, 0x128, 0x129, 0x12A}
CLASSES = ["G", "TG", "P", "SA", "W", "S", "TL", "TR", "BL", "BR"]
NEIGH8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]   # N NE E SE S SW W NW
NEIGH4_IDX = [0, 2, 4, 6]
OUT = "X"   # outside the map


class Vocabulary:
    """Which class each General metatile belongs to (derived from behaviour + vanilla usage)."""

    def __init__(self, project, corpus):
        self.p, self.c = project, corpus
        tp = project.tileset_pair(PRIMARY, "gTileset_Petalburg")
        self.cls = {}
        for m in range(NUM_METATILES_IN_PRIMARY):
            self.cls[m] = self._classify(tp, m)
        self.decorations = self._find_decorations()
        for m in self.decorations:
            self.cls[m] = "F"
        self.object_parts = self._find_object_parts()
        for m in self.object_parts:
            self.cls[m] = "F"

    def _find_object_parts(self, min_share=0.6, min_count=10):
        """Walkable tiles that are really part of an object (e.g. the leafy top of a small tree,
        whose trunk below is solid): in some direction they are almost always next to one
        specific F tile. Treating them as grass would cut the object in half."""
        out = set()
        for m, c in self.cls.items():
            if c not in ("G", "TG", "P", "SA") or m == 0x001:
                continue
            k = (PRIMARY, m)
            if sum(self.c.attrs.get(k, {}).values()) < min_count:
                continue
            for d, cnt in self.c.neigh.get(k, {}).items():
                tot = sum(cnt.values()) or 1
                (nk, n), = cnt.most_common(1)
                if nk[0] == PRIMARY and self.cls.get(nk[1]) == "F" and n / tot >= min_share:
                    out.add(m)
                    break
        return out

    def _find_decorations(self, min_share=0.5, min_count=20):
        """Grass-class tiles (other than plain grass 001) that vanilla mostly places with grass
        on all four sides: flowers, tufts, pebbles. Their placement is an artistic choice, so
        they are excluded from the structural rules (a separate decoration pass can add them)."""
        out = set()
        for m, c in self.cls.items():
            if c != "G" or m == 0x001:
                continue
            k = (PRIMARY, m)
            total = sum(self.c.attrs.get(k, {}).values())
            if total < min_count:
                continue
            neigh = self.c.neigh.get(k, {})
            share = 1.0
            for d in "NESW":
                cnt = neigh.get(d, {})
                tot = sum(cnt.values()) or 1
                g = sum(n for nk, n in cnt.items() if nk[0] == PRIMARY and self.cls.get(nk[1]) == "G")
                share = min(share, g / tot)
            if share >= min_share:
                out.add(m)
        return out

    def _classify(self, tp, m):
        for q, ids in TREE.items():
            if m in ids:
                return q
        if m in PATH:
            return "P"
        if m in SAND:
            return "SA"
        b = tp.behavior(m)
        name = self.p.behavior_names.get(b, "")
        a = self.c.attrs.get((PRIMARY, m))
        modal = a.most_common(1)[0][0] if a else None
        if name == "MB_TALL_GRASS":
            return "TG"
        if self.p.tile_flags.get(b, 0) & TILE_FLAG_SURFABLE and modal and modal[1] == 1:
            return "W" if name == "MB_POND_WATER" else "S"
        if name == "MB_NORMAL" and modal == (0, 3):
            return "G"
        return "F"

    def label(self, layout_entry, mid):
        if layout_entry["primary_tileset"] != PRIMARY or mid >= NUM_METATILES_IN_PRIMARY:
            return "F"
        return self.cls.get(mid, "F")


def grid_labels(vocab, entry, blocks, w, h):
    return [[vocab.label(entry, blocks[y * w + x] & 0x3FF) for x in range(w)] for y in range(h)]


def signature(lab, x, y, w, h):
    out = []
    for dx, dy in NEIGH8:
        nx, ny = x + dx, y + dy
        out.append(lab[ny][nx] if 0 <= nx < w and 0 <= ny < h else OUT)
    return tuple(out)


TREE_Q = {"TL", "TR", "BL", "BR"}


def same_mask(cls, sig):
    """Binary neighbourhood: is each neighbour 'my kind' (trees: any tree quarter)?"""
    mine = TREE_Q if cls in TREE_Q else {cls}
    return tuple(n in mine for n in sig)


class Rules:
    """Lookup levels, most specific first:
       8  exact classes of all 8 neighbours        4  exact classes of N,E,S,W
       7  same/different for all 8 neighbours      3  same/different for N,E,S,W
       0  the class's most common tile
    Exact levels capture type-specific details (canopy overhang above a tree, bank shadow below
    water); binary levels generalise edges to neighbour types vanilla never paired."""

    def __init__(self):
        self.t = {lvl: defaultdict(lambda: defaultdict(Counter)) for lvl in (8, 7, 4, 3)}
        self.base = defaultdict(Counter)

    @staticmethod
    def keys(cls, sig):
        s4 = tuple(sig[i] for i in NEIGH4_IDX)
        b8 = same_mask(cls, sig)
        return {8: sig, 7: b8, 4: s4, 3: tuple(b8[i] for i in NEIGH4_IDX)}

    def add(self, cls, sig, mid):
        for lvl, k in self.keys(cls, sig).items():
            self.t[lvl][cls][k][mid] += 1
        self.base[cls][mid] += 1

    MIN_SUPPORT = 3   # a neighbourhood seen fewer times than this is a one-off design choice

    def outputs(self, cls):
        """Every metatile the rules can actually produce for `cls` (any level)."""
        if not hasattr(self, "_outputs"):
            self._outputs = defaultdict(set)
            for lvl, by_cls in self.t.items():
                for c, table in by_cls.items():
                    for cnt in table.values():
                        if sum(cnt.values()) >= self.MIN_SUPPORT or lvl == 3:
                            self._outputs[c].add(cnt.most_common(1)[0][0])
            for c, cnt in self.base.items():
                self._outputs[c].add(cnt.most_common(1)[0][0])
        return self._outputs[cls]

    def pick(self, cls, sig):
        keys = self.keys(cls, sig)
        for lvl in (8, 7, 4, 3):
            c = self.t[lvl][cls].get(keys[lvl])
            if c and (sum(c.values()) >= self.MIN_SUPPORT or lvl == 3):
                return c.most_common(1)[0][0], lvl
        if self.base[cls]:
            return self.base[cls].most_common(1)[0][0], 0
        return None, -1


def vanilla_maps(corpus):
    return [e for e in corpus._vanilla_layouts() if e["primary_tileset"] == PRIMARY]


def load_blocks(p, e):
    w, h = e["width"], e["height"]
    raw = open(p.path(e["blockdata_filepath"]), "rb").read()
    return struct.unpack(f"<{w * h}H", raw[: w * h * 2])


def learn(p, vocab, entries, exclude=None):
    rules = Rules()
    for e in entries:
        if exclude and e["id"] == exclude:
            continue
        w, h = e["width"], e["height"]
        b = load_blocks(p, e)
        lab = grid_labels(vocab, e, b, w, h)
        for y in range(h):
            for x in range(w):
                c = lab[y][x]
                if c != "F":
                    rules.add(c, signature(lab, x, y, w, h), b[y * w + x] & 0x3FF)
    return rules


def autotile(rules, lab, w, h, keep=None):
    """lab: class grid (F cells need `keep[y][x]` metatile). Returns (metatile grid, stats)."""
    out = [[0] * w for _ in range(h)]
    levels = Counter()
    for y in range(h):
        for x in range(w):
            c = lab[y][x]
            if c == "F":
                out[y][x] = keep[y][x] if keep else 0x001
                continue
            mid, lvl = rules.pick(c, signature(lab, x, y, w, h))
            out[y][x] = mid if mid is not None else 0x001
            levels[lvl] += 1
    return out, levels


def reconstruction_test(p, corpus, vocab, only=None):
    """Leave-one-out: label each vanilla General map, regenerate its class cells from rules
    learned on all *other* maps, and count exact metatile matches per class."""
    entries = vanilla_maps(corpus)
    tests = [e for e in entries if not only or e["id"] in only]
    per_class = defaultdict(lambda: [0, 0])
    per_map = []
    for e in tests:
        rules = learn(p, vocab, entries, exclude=e["id"])
        w, h = e["width"], e["height"]
        b = load_blocks(p, e)
        lab = grid_labels(vocab, e, b, w, h)
        keep = [[b[y * w + x] & 0x3FF for x in range(w)] for y in range(h)]
        gen, _ = autotile(rules, lab, w, h, keep)
        hit = tot = 0
        for y in range(h):
            for x in range(w):
                c = lab[y][x]
                if c == "F":
                    continue
                ok = gen[y][x] == keep[y][x]
                per_class[c][0] += ok
                per_class[c][1] += 1
                hit += ok
                tot += 1
        per_map.append((e["id"], hit, tot))
    return per_class, per_map
