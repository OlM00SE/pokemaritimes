"""Tilesets: graphics + metatile definitions + attributes (Emerald format).

metatiles.bin: 8 u16 tile entries per metatile (4 bottom layer, 4 top layer; TL,TR,BL,BR)
  entry bits: 0-9 tile index, 10 hflip, 11 vflip, 12-15 palette
metatile_attributes.bin: u16 per metatile; bits 0-7 behavior, 12-15 layer type
Tile indices >= 512 and palettes >= 6 come from the secondary tileset.
"""
import functools, os, struct
from PIL import Image
from .project import NUM_METATILES_IN_PRIMARY, NUM_TILES_IN_PRIMARY, NUM_PALS_IN_PRIMARY


def read_jasc(path):
    vals = open(path).read().split()
    n = int(vals[2])
    nums = list(map(int, vals[3:3 + 3 * n]))
    return [tuple(nums[i:i + 3]) for i in range(0, 3 * n, 3)]


class Tileset:
    def __init__(self, project, name, folder, metatiles_path, secondary):
        self.project, self.name, self.folder, self.secondary = project, name, folder, secondary
        raw = open(project.path(metatiles_path), "rb").read()
        self.metatiles = [struct.unpack_from("<8H", raw, i) for i in range(0, len(raw) - 15, 16)]
        ap = project.path(folder, "metatile_attributes.bin")
        a = open(ap, "rb").read() if os.path.exists(ap) else b""
        self.attributes = list(struct.unpack(f"<{len(a) // 2}H", a))

    @functools.cached_property
    def tiles_image(self):
        img = Image.open(self.project.path(self.folder, "tiles.png"))
        if img.mode != "P":
            raise ValueError(f"{self.folder}/tiles.png must be an indexed PNG")
        return img

    @functools.cached_property
    def palettes(self):
        out = []
        for i in range(16):
            p = self.project.path(self.folder, "palettes", f"{i:02}.pal")
            out.append(read_jasc(p) if os.path.exists(p) else [(0, 0, 0)] * 16)
        return out

    @functools.lru_cache(maxsize=None)
    def tile(self, idx):
        """8x8 tile as 64 color indices (0-15), or None if out of range."""
        img = self.tiles_image
        per_row = img.width // 8
        if idx >= per_row * (img.height // 8):
            return None
        x, y = (idx % per_row) * 8, (idx // per_row) * 8
        return [v & 0xF for v in img.crop((x, y, x + 8, y + 8)).getdata()]


class TilesetPair:
    """A primary+secondary pair as the engine sees it (metatile ids 0..1023)."""

    def __init__(self, primary, secondary):
        self.pri, self.sec = primary, secondary

    def _split(self, mid):
        if mid < NUM_METATILES_IN_PRIMARY:
            return self.pri, mid
        return self.sec, mid - NUM_METATILES_IN_PRIMARY

    def exists(self, mid):
        ts, i = self._split(mid)
        return i < len(ts.metatiles)

    def entries(self, mid):
        ts, i = self._split(mid)
        return ts.metatiles[i] if i < len(ts.metatiles) else None

    def attribute(self, mid):
        ts, i = self._split(mid)
        return ts.attributes[i] if i < len(ts.attributes) else 0

    def behavior(self, mid):
        return self.attribute(mid) & 0xFF

    def layer_type(self, mid):
        return (self.attribute(mid) >> 12) & 0xF

    def palette(self, n):
        return (self.pri if n < NUM_PALS_IN_PRIMARY else self.sec).palettes[n]

    def tile(self, t):
        return self.pri.tile(t) if t < NUM_TILES_IN_PRIMARY else self.sec.tile(t - NUM_TILES_IN_PRIMARY)

    def metatile_ids(self):
        return list(range(len(self.pri.metatiles))) + \
            [NUM_METATILES_IN_PRIMARY + i for i in range(len(self.sec.metatiles))]
