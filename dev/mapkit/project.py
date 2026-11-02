"""Project index: everything parsed straight from the expansion sources (no hard-coded ids)."""
import functools, json, os, re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Engine constants (include/fieldmap.h, include/global.fieldmap.h)
NUM_METATILES_IN_PRIMARY = 512
NUM_TILES_IN_PRIMARY = 512
NUM_PALS_IN_PRIMARY = 6
NUM_METATILES_TOTAL = 1024
MAP_OFFSET = 7
MAX_MAP_DATA_SIZE = 10240
ELEVATION_TRANSITION, ELEVATION_DEFAULT, ELEVATION_MULTI_LEVEL = 0, 3, 15
LAYER_NORMAL, LAYER_COVERED, LAYER_SPLIT = 0, 1, 2
TILE_FLAG_HAS_ENCOUNTERS, TILE_FLAG_SURFABLE = 1, 2


def max_map_area_ok(w, h):
    """fieldmap.c InitMapLayoutData: (w + 15) * (h + 14) must fit MAX_MAP_DATA_SIZE."""
    return (w + MAP_OFFSET * 2 + 1) * (h + MAP_OFFSET * 2) <= MAX_MAP_DATA_SIZE


class Project:
    def __init__(self, root=REPO):
        self.root = root
        self._tilesets = {}

    def path(self, *p):
        return os.path.join(self.root, *p)

    # ---------- maps & layouts ----------
    @functools.cached_property
    def layouts(self):
        data = json.load(open(self.path("data/layouts/layouts.json"), encoding="utf-8"))
        return {l["id"]: l for l in data["layouts"] if "id" in l}

    @functools.cached_property
    def map_names(self):
        d = self.path("data/maps")
        return sorted(n for n in os.listdir(d) if os.path.exists(os.path.join(d, n, "map.json")))

    @functools.cached_property
    def const_to_map(self):
        out = {}
        for n in self.map_names:
            out[json.load(open(self.path("data/maps", n, "map.json"), encoding="utf-8"))["id"]] = n
        return out

    def load_map(self, name):
        from .layout import MapData
        return MapData(self, name)

    def load_layout(self, layout_id):
        from .layout import Layout
        return Layout(self, self.layouts[layout_id])

    def tileset_pair(self, primary, secondary):
        from .tileset import TilesetPair
        return TilesetPair(self.tileset(primary), self.tileset(secondary))

    def tileset(self, name):
        from .tileset import Tileset
        if name not in self._tilesets:
            folder, metatiles, secondary = self.tileset_sources[name]
            self._tilesets[name] = Tileset(self, name, folder, metatiles, secondary)
        return self._tilesets[name]

    @functools.cached_property
    def tileset_sources(self):
        """gTileset_X -> (folder, metatiles.bin path, is_secondary), from the C headers."""
        srcs = ""
        for p in ("src/data/tilesets/graphics.h", "src/data/tilesets/metatiles.h", "src/graphics.c"):
            srcs += open(self.path(p), encoding="utf-8", errors="replace").read()
        inc = dict(re.findall(r'(\w+)\[\]\s*=\s*INC\w+\("([^"]+)"', srcs))
        hdr = open(self.path("src/data/tilesets/headers.h"), encoding="utf-8").read()
        out = {}
        for name, body in re.findall(r"const struct Tileset (\w+)\s*=\s*\{(.*?)\};", hdr, re.S):
            t = re.search(r"\.tiles\s*=\s*(\w+)", body).group(1)
            m = re.search(r"\.metatiles\s*=\s*(\w+)", body).group(1)
            sec = re.search(r"\.isSecondary\s*=\s*(\w+)", body)
            out[name] = (os.path.dirname(inc[t]), inc[m], bool(sec and sec.group(1) == "TRUE"))
        return out

    # ---------- metatile behaviors ----------
    @functools.cached_property
    def behaviors(self):
        """MB_* name -> value, parsed positionally from the enum."""
        src = open(self.path("include/constants/metatile_behaviors.h"), encoding="utf-8").read()
        body = re.sub(r"//.*", "", re.search(r"enum\s*\{(.*?)\};", src, re.S).group(1))
        out, v = {}, 0
        for item in (s.strip() for s in body.split(",")):
            if not item:
                continue
            if "=" in item:
                item, val = (s.strip() for s in item.split("="))
                v = int(val, 0)
            out[item] = v
            v += 1
        return out

    @functools.cached_property
    def behavior_names(self):
        return {v: k for k, v in self.behaviors.items()}

    @functools.cached_property
    def tile_flags(self):
        """behavior value -> TILE_FLAG_* bits, from sTileBitAttributes in metatile_behavior.c."""
        src = open(self.path("src/metatile_behavior.c"), encoding="utf-8").read()
        table = re.search(r"sTileBitAttributes\[[^\]]*\]\s*=\s*\{(.*?)\};", src, re.S).group(1)
        flags = {}
        for name, expr in re.findall(r"\[(MB_\w+)\]\s*=\s*([^,\n]+)", table):
            bits = 0
            bits |= TILE_FLAG_HAS_ENCOUNTERS if "HAS_ENCOUNTERS" in expr else 0
            bits |= TILE_FLAG_SURFABLE if "SURFABLE" in expr else 0
            flags[self.behaviors[name]] = bits
        return flags

    def mb(self, name):
        return self.behaviors[name]

    @functools.cached_property
    def _behavior_funcs(self):
        """MetatileBehavior_IsX -> set of MB values, parsed from metatile_behavior.c.
        Handles equality chains and simple >= / <= ranges; anything else returns all MB_* tokens
        mentioned in the body (good enough for the warp/door predicates we rely on)."""
        src = open(self.path("src/metatile_behavior.c"), encoding="utf-8").read()
        out = {}
        for name, body in re.findall(r"bool8 (MetatileBehavior_Is\w+)\(u\w+ metatileBehavior\)\s*\{(.*?)\n\}", src, re.S):
            vals = set()
            for lo, hi in re.findall(r"metatileBehavior\s*>=\s*(MB_\w+)\s*&&\s*metatileBehavior\s*<=\s*(MB_\w+)", body):
                vals |= set(range(self.behaviors[lo], self.behaviors[hi] + 1))
            for tok in re.findall(r"(MB_\w+)", body):
                if tok in self.behaviors:
                    vals.add(self.behaviors[tok])
            out[name] = vals
        return out

    def behavior_set(self, *funcs):
        """Union of behaviours accepted by the named MetatileBehavior_Is* predicates."""
        out = set()
        for f in funcs:
            out |= self._behavior_funcs["MetatileBehavior_Is" + f if not f.startswith("Metatile") else f]
        return out

    # ---------- scripts ----------
    @functools.cached_property
    def script_labels(self):
        labels = set()
        for root, _, files in os.walk(self.path("data")):
            for f in files:
                if f.endswith((".inc", ".s", ".pory")):
                    txt = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
                    labels.update(re.findall(r"^(\w+)::?", txt, re.M))
                    labels.update(re.findall(r"^\s*(?:script|text|movement|mapscripts)\s+(\w+)", txt, re.M))
        return labels
