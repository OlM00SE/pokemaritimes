"""Render a pokeemerald-style map layout to PNG.

Usage:
  python render_map.py <project_dir> <MapName> [-o out.png] [--grid] [--events] [--scale N]
  python render_map.py <project_dir> --sheet <gTileset_Primary> <gTileset_Secondary> [-o out.png]

Reads data/maps/<MapName>/map.json, data/layouts/layouts.json, and tileset
sources (tiles.png, metatiles.bin, palettes/*.pal). Read-only.
"""
import argparse, json, os, re, struct
from PIL import Image, ImageDraw

NUM_PRI_TILES = 512
NUM_PRI_METATILES = 512
NUM_PRI_PALS = 6


def parse_tileset_paths(proj):
    hdr = open(os.path.join(proj, "src/data/tilesets/headers.h")).read()
    gfx = open(os.path.join(proj, "src/data/tilesets/graphics.h")).read()
    mt = open(os.path.join(proj, "src/data/tilesets/metatiles.h")).read()
    gc = open(os.path.join(proj, "src/graphics.c")).read()  # primary tilesets live here
    inc = {}
    for sym, path in re.findall(r'(\w+)\[\]\s*=\s*INC\w+\("([^"]+)"\)', gfx + mt + gc):
        inc[sym] = path
    out = {}
    for name, body in re.findall(r"const struct Tileset (\w+)\s*=\s*\{(.*?)\};", hdr, re.S):
        t = re.search(r"\.tiles\s*=\s*(\w+)", body).group(1)
        m = re.search(r"\.metatiles\s*=\s*(\w+)", body).group(1)
        out[name] = (os.path.dirname(inc[t]), inc[m])
    return out


def read_pal(path):
    lines = open(path).read().split()
    n = int(lines[2])
    vals = list(map(int, lines[3:3 + n * 3]))
    return [tuple(vals[i:i + 3]) for i in range(0, n * 3, 3)]


class Tileset:
    def __init__(self, proj, folder, metatiles_path):
        img = Image.open(os.path.join(proj, folder, "tiles.png"))
        if img.mode != "P":
            raise SystemExit(f"{folder}/tiles.png is not indexed")
        self.w = img.width // 8
        self.tiles_img = img
        self.ntiles = self.w * (img.height // 8)
        raw = open(os.path.join(proj, metatiles_path), "rb").read()
        self.metatiles = [struct.unpack_from("<8H", raw, i) for i in range(0, len(raw), 16)]
        self.pals = []
        for i in range(16):
            p = os.path.join(proj, folder, "palettes", f"{i:02}.pal")
            self.pals.append(read_pal(p) if os.path.exists(p) else [(0, 0, 0)] * 16)
        self._tile_cache = {}

    def tile_indices(self, idx):
        if idx not in self._tile_cache:
            if idx >= self.ntiles:
                self._tile_cache[idx] = None
            else:
                x, y = (idx % self.w) * 8, (idx // self.w) * 8
                crop = self.tiles_img.crop((x, y, x + 8, y + 8))
                self._tile_cache[idx] = [v & 0xF for v in crop.getdata()]
        return self._tile_cache[idx]


class Renderer:
    def __init__(self, proj, primary, secondary):
        paths = parse_tileset_paths(proj)
        self.pri = Tileset(proj, *paths[primary])
        self.sec = Tileset(proj, *paths[secondary])
        self.cache = {}

    def palette(self, n):
        return (self.pri if n < NUM_PRI_PALS else self.sec).pals[n]

    def metatile(self, mid):
        if mid in self.cache:
            return self.cache[mid]
        if mid < NUM_PRI_METATILES:
            mts = self.pri.metatiles; i = mid
        else:
            mts = self.sec.metatiles; i = mid - NUM_PRI_METATILES
        im = Image.new("RGB", (16, 16), self.palette(0)[0])
        if i < len(mts):
            px = im.load()
            entries = mts[i]
            for layer in range(2):
                for q in range(4):
                    e = entries[layer * 4 + q]
                    t, hf, vf, pal = e & 0x3FF, (e >> 10) & 1, (e >> 11) & 1, e >> 12
                    src = self.pri.tile_indices(t) if t < NUM_PRI_TILES else self.sec.tile_indices(t - NUM_PRI_TILES)
                    if src is None:
                        continue
                    colors = self.palette(pal)
                    ox, oy = (q % 2) * 8, (q // 2) * 8
                    for yy in range(8):
                        for xx in range(8):
                            c = src[yy * 8 + xx]
                            if c == 0 and layer == 1:
                                continue
                            if c == 0:
                                continue
                            dx = 7 - xx if hf else xx
                            dy = 7 - yy if vf else yy
                            px[ox + dx, oy + dy] = colors[c]
        else:
            ImageDraw.Draw(im).rectangle((0, 0, 15, 15), fill=(255, 0, 255))
        self.cache[mid] = im
        return im


def load_layout(proj, layout_id):
    layouts = json.load(open(os.path.join(proj, "data/layouts/layouts.json")))["layouts"]
    for l in layouts:
        if l.get("id") == layout_id:
            return l
    raise SystemExit(f"layout {layout_id} not found")


def render_map(proj, map_name, grid, events, scale):
    mj = json.load(open(os.path.join(proj, "data/maps", map_name, "map.json")))
    lay = load_layout(proj, mj["layout"])
    w, h = lay["width"], lay["height"]
    raw = open(os.path.join(proj, lay["blockdata_filepath"]), "rb").read()
    blocks = struct.unpack(f"<{w * h}H", raw[: w * h * 2])
    r = Renderer(proj, lay["primary_tileset"], lay["secondary_tileset"])
    img = Image.new("RGB", (w * 16, h * 16))
    for y in range(h):
        for x in range(w):
            img.paste(r.metatile(blocks[y * w + x] & 0x3FF), (x * 16, y * 16))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    d = ImageDraw.Draw(img, "RGBA")
    s = 16 * scale
    if grid:
        for x in range(w):
            d.line([(x * s, 0), (x * s, h * s)], fill=(0, 0, 0, 40 if x % 5 else 110))
            if x % 5 == 0:
                d.text((x * s + 2, 1), str(x), fill=(255, 255, 0))
        for y in range(h):
            d.line([(0, y * s), (w * s, y * s)], fill=(0, 0, 0, 40 if y % 5 else 110))
            if y % 5 == 0:
                d.text((2, y * s + 2), str(y), fill=(255, 255, 0))
    if events:
        def mark(ev, color, label):
            x, y = ev["x"], ev["y"]
            d.rectangle((x * s + 1, y * s + 1, x * s + s - 2, y * s + s - 2), outline=color, width=2)
            d.text((x * s + 3, y * s + 3), label, fill=color)
        for i, e in enumerate(mj.get("warp_events") or []):
            mark(e, (255, 0, 0, 255), f"W{i}")
        for e in mj.get("object_events") or []:
            mark(e, (0, 120, 255, 255), "O")
        for e in mj.get("coord_events") or []:
            mark(e, (255, 160, 0, 255), "T")
        for e in mj.get("bg_events") or []:
            mark(e, (180, 0, 255, 255), "S")
    return img


def render_sheet(proj, primary, secondary, scale):
    r = Renderer(proj, primary, secondary)
    ids = list(range(len(r.pri.metatiles))) + [NUM_PRI_METATILES + i for i in range(len(r.sec.metatiles))]
    cols = 8
    cell = 16 * scale
    rows = (len(ids) + cols - 1) // cols
    lab = 34
    img = Image.new("RGB", (cols * (cell + lab), rows * (cell + 2)), (40, 40, 40))
    d = ImageDraw.Draw(img)
    for n, mid in enumerate(ids):
        cx, cy = (n % cols) * (cell + lab), (n // cols) * (cell + 2)
        d.text((cx + 1, cy + cell // 2 - 5), f"{mid:03X}", fill=(255, 255, 255))
        img.paste(r.metatile(mid).resize((cell, cell), Image.NEAREST), (cx + lab - 4, cy))
    return img


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("map", nargs="?")
    ap.add_argument("--sheet", nargs=2, metavar=("PRIMARY", "SECONDARY"))
    ap.add_argument("-o", "--out")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--events", action="store_true")
    ap.add_argument("--scale", type=int, default=1)
    a = ap.parse_args()
    if a.sheet:
        img = render_sheet(a.project, *a.sheet, max(a.scale, 2))
        out = a.out or f"sheet_{a.sheet[1]}.png"
    else:
        img = render_map(a.project, a.map, a.grid, a.events, a.scale)
        out = a.out or f"{a.map}.png"
    img.save(out)
    print(out, img.size)
