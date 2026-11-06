"""Copy vanilla metatiles from one secondary tileset into another, art and all.

A map has one secondary tileset, so a piece that vanilla only drew in another one (Route 104's
plank bridge is in gTileset_Rustboro; Woodstock uses gTileset_Petalburg) has to be copied in.
Nothing is redrawn: each 8x8 tile is copied pixel for pixel, each palette colour for colour, each
metatile's layers, flips and attributes as they are. Both tilesets must share the primary
(tiles and palettes below the secondary range are the primary's and stay as they are).

  plan(project, "gTileset_Rustboro", [0x34E, 0x34F], "gTileset_Petalburg")
      -> Plan: where each source metatile lands, and what would be appended
  apply(project, plan)   writes tiles.png, palettes/NN.pal, metatiles.bin, metatile_attributes.bin

Re-running is a no-op: a tile whose pixels the target already has is reused, a palette already
in its slot is reused, and a metatile identical to an existing one (layers and attributes) is
that one. Only appends: no existing tile, palette or metatile index moves, so every map on the
target tileset draws as before.

A secondary palette goes into the same slot if the target leaves it empty (all black and used
by no metatile) or already holds the same colours; otherwise into the first such slot, and the
copied layers point there. Refused, with the reason: different primaries, a source tile past
the end of its tiles.png (an animated tile, whose art isn't in the PNG), no palette slot left,
the target's tile or metatile budget, and an appended tile index that an existing metatile
already points at (a tileset's animation frames are written past its tiles.png: Petalburg's
flowers at 800-819).
"""
import io
import os
import struct
from dataclasses import dataclass, field
from PIL import Image
from .project import NUM_METATILES_IN_PRIMARY, NUM_TILES_IN_PRIMARY, NUM_PALS_IN_PRIMARY, NUM_METATILES_TOTAL
from .transaction import atomic_write, edit

CACHE = "_imported_pieces"      # project attribute: what callers found imported (cleared on apply)
NUM_PALS_TOTAL = 13             # palettes 6..12 belong to the secondary tileset
NUM_TILES_TOTAL = 1024
TILES_PER_ROW = 16


@dataclass
class Plan:
    source: str
    target: str
    mapping: dict = field(default_factory=dict)        # source metatile id -> target metatile id
    new_tiles: list = field(default_factory=list)      # [64 colour indices], appended in order
    palettes: dict = field(default_factory=dict)       # target slot -> 16 colours to write
    new_metatiles: list = field(default_factory=list)  # [(8 entries, attribute)], appended in order
    problems: list = field(default_factory=list)

    @property
    def changes(self):
        return bool(self.new_tiles or self.palettes or self.new_metatiles)


def _empty_slots(ts):
    used = {v >> 12 for e in ts.metatiles for v in e}
    return [i for i in range(NUM_PALS_IN_PRIMARY, NUM_PALS_TOTAL)
            if i not in used and all(c == (0, 0, 0) for c in ts.palettes[i])]


def _tile_count(ts):
    img = ts.tiles_image
    return (img.width // 8) * (img.height // 8)


def plan(project, source, mids, target):
    src, dst = project.tileset(source), project.tileset(target)
    pl = Plan(source, target)
    if not (src.secondary and dst.secondary):
        pl.problems.append(f"both tilesets must be secondary ({source}, {target})")
        return pl
    src_n, dst_n = _tile_count(src), _tile_count(dst)
    dst_tiles = {}
    for i in range(dst_n):
        dst_tiles.setdefault(tuple(dst.tile(i)), i)
    # tile indices a target metatile points at past its tiles.png: animation frames go there
    reserved = {(v & 0x3FF) - NUM_TILES_IN_PRIMARY for e in dst.metatiles for v in e
                if (v & 0x3FF) >= NUM_TILES_IN_PRIMARY + dst_n}
    pal_map, free = {}, _empty_slots(dst)
    tile_map = {}
    existing = {(tuple(e), a): NUM_METATILES_IN_PRIMARY + i
                for i, (e, a) in enumerate(zip(dst.metatiles, dst.attributes))}
    pending = {}
    for mid in mids:
        i = mid - NUM_METATILES_IN_PRIMARY
        if not 0 <= i < len(src.metatiles):
            pl.problems.append(f"{source} has no metatile {mid:03X}")
            continue
        entries = []
        for v in src.metatiles[i]:
            t, flips, pal = v & 0x3FF, v & 0x0C00, v >> 12
            if t >= NUM_TILES_IN_PRIMARY:
                s = t - NUM_TILES_IN_PRIMARY
                if s >= src_n:
                    pl.problems.append(f"{source} {mid:03X}: tile {t} is past its tiles.png "
                                       "(an animated tile); it can't be copied")
                    continue
                if s not in tile_map:
                    px = tuple(src.tile(s))
                    if px not in dst_tiles:
                        dst_tiles[px] = dst_n + len(pl.new_tiles)
                        pl.new_tiles.append(list(px))
                    tile_map[s] = dst_tiles[px]
                t = NUM_TILES_IN_PRIMARY + tile_map[s]
            if pal >= NUM_PALS_IN_PRIMARY:
                if pal not in pal_map:
                    colours = src.palettes[pal]
                    same = [k for k in range(NUM_PALS_IN_PRIMARY, NUM_PALS_TOTAL)
                            if (pl.palettes.get(k) or dst.palettes[k]) == colours]
                    if pal in same:
                        pal_map[pal] = pal
                    elif pal in free:
                        pal_map[pal] = pal
                        free.remove(pal)
                        pl.palettes[pal] = colours
                    elif same:
                        pal_map[pal] = same[0]
                    elif free:
                        pal_map[pal] = free.pop(0)
                        pl.palettes[pal_map[pal]] = colours
                    else:
                        pl.problems.append(f"{target} has no free palette slot for {source}'s palette {pal}")
                        pal_map[pal] = pal
                pal = pal_map[pal]
            entries.append(t | flips | (pal << 12))
        if len(entries) != 8:
            continue
        key = (tuple(entries), src.attributes[i])
        if key in existing:
            pl.mapping[mid] = existing[key]
        elif key in pending:
            pl.mapping[mid] = pending[key]
        else:
            pending[key] = NUM_METATILES_IN_PRIMARY + len(dst.metatiles) + len(pl.new_metatiles)
            pl.mapping[mid] = pending[key]
            pl.new_metatiles.append(key)
    total_tiles = dst_n + len(pl.new_tiles)
    if total_tiles > NUM_TILES_TOTAL - NUM_TILES_IN_PRIMARY:
        pl.problems.append(f"{target} would have {total_tiles} tiles (512 at most)")
    clash = sorted(reserved & set(range(dst_n, total_tiles)))
    if clash:
        pl.problems.append(f"{target}: new tiles would land on tile {NUM_TILES_IN_PRIMARY + clash[0]}, "
                           "which an existing metatile already uses (animation frames)")
    if len(dst.metatiles) + len(pl.new_metatiles) > NUM_METATILES_TOTAL - NUM_METATILES_IN_PRIMARY:
        pl.problems.append(f"{target} would have too many metatiles")
    return pl


def _bit_depth(path):
    """The PNG's bit depth (IHDR), kept when the image is rewritten (gbagfx reads it)."""
    with open(path, "rb") as f:
        head = f.read(25)
    return head[24]


def _write_pal(path, colours):
    lines = ["JASC-PAL", "0100", "16"] + [f"{r} {g} {b}" for r, g, b in colours]
    atomic_write(path, ("\r\n".join(lines) + "\r\n").encode("ascii"))


def apply(project, pl):
    """Write the plan (re-planned at the write boundary). Returns the fresh plan."""
    fresh = plan(project, pl.source, list(pl.mapping), pl.target)
    if fresh.problems:
        raise ValueError("; ".join(fresh.problems))
    if fresh.mapping != pl.mapping:
        raise ValueError("the import plan changed; preview it again")
    if not fresh.changes:
        return fresh
    dst = project.tileset(pl.target)
    folder = dst.folder
    mt_path = os.path.relpath(project.path(project.tileset_sources[pl.target][1]), project.root)
    files = [f"{folder}/tiles.png", mt_path, f"{folder}/metatile_attributes.bin"] + \
            [f"{folder}/palettes/{k:02d}.pal" for k in fresh.palettes]
    with edit(project, files):
        if fresh.new_tiles:
            img = dst.tiles_image
            n = _tile_count(dst) + len(fresh.new_tiles)
            rows = -(-n // TILES_PER_ROW)
            out = Image.new("P", (TILES_PER_ROW * 8, rows * 8), 0)
            out.putpalette(img.getpalette())
            out.paste(img, (0, 0))
            for k, px in enumerate(fresh.new_tiles):
                i = _tile_count(dst) + k
                tile = Image.new("P", (8, 8))
                tile.putdata(px)
                out.paste(tile, ((i % TILES_PER_ROW) * 8, (i // TILES_PER_ROW) * 8))
            buf = io.BytesIO()
            out.save(buf, format="PNG", bits=_bit_depth(project.path(folder, "tiles.png")))
            atomic_write(project.path(folder, "tiles.png"), buf.getvalue())
        for k, colours in fresh.palettes.items():
            _write_pal(project.path(folder, "palettes", f"{k:02d}.pal"), colours)
        mt = open(project.path(mt_path), "rb").read()
        at = open(project.path(folder, "metatile_attributes.bin"), "rb").read()
        for entries, attr in fresh.new_metatiles:
            mt += struct.pack("<8H", *entries)
            at += struct.pack("<H", attr)
        atomic_write(project.path(mt_path), mt)
        atomic_write(project.path(folder, "metatile_attributes.bin"), at)
    project._tilesets.pop(pl.target, None)
    project.__dict__.pop(CACHE, None)
    return fresh
