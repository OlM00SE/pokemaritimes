"""Layout (map.bin grid) and MapData (map.json). Both can be edited and saved.

map.bin: u16 per block, row-major. bits 0-9 metatile id, 10-11 collision, 12-15 elevation.
"""
import json, os, struct
from .mapjson import dump_json
from .transaction import atomic_write


class SharedLayoutError(ValueError):
    pass


def layout_users(project, entry):
    """Maps sharing these block bytes, including distinct layout IDs aliasing one file."""
    path = os.path.normcase(os.path.realpath(project.path(entry["blockdata_filepath"])))
    aliases = {lid for lid, e in project.layouts.items()
               if os.path.normcase(os.path.realpath(project.path(e["blockdata_filepath"]))) == path}
    return [n for n in project.map_names
            if json.load(open(project.path("data/maps", n, "map.json"), encoding="utf-8"))["layout"] in aliases]


def pack(mid, coll, elev):
    return (mid & 0x3FF) | ((coll & 3) << 10) | ((elev & 0xF) << 12)


def unpack(v):
    return v & 0x3FF, (v >> 10) & 3, v >> 12


class Layout:
    def __init__(self, project, entry):
        self.project, self.entry = project, entry
        self.id = entry["id"]
        self.width, self.height = entry["width"], entry["height"]
        self.primary, self.secondary = entry["primary_tileset"], entry["secondary_tileset"]
        raw = open(project.path(entry["blockdata_filepath"]), "rb").read()
        n = self.width * self.height
        self.size_ok = len(raw) == n * 2
        got = min(len(raw) // 2, n)
        self.blocks = list(struct.unpack(f"<{got}H", raw[:got * 2])) + [pack(0, 1, 0)] * (n - got)
        braw = open(project.path(entry["border_filepath"]), "rb").read()
        self.border = list(struct.unpack(f"<{len(braw) // 2}H", braw))

    @property
    def tiles(self):
        return self.project.tileset_pair(self.primary, self.secondary)

    def inb(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x, y):
        return self.blocks[y * self.width + x]

    def mid(self, x, y): return self.get(x, y) & 0x3FF
    def coll(self, x, y): return (self.get(x, y) >> 10) & 3
    def elev(self, x, y): return self.get(x, y) >> 12

    def set(self, x, y, mid=None, coll=None, elev=None):
        m, c, e = unpack(self.get(x, y))
        self.blocks[y * self.width + x] = pack(m if mid is None else mid,
                                               c if coll is None else coll,
                                               e if elev is None else elev)

    def border_block(self, x, y):
        """Emerald border: 2x2 pattern indexed by map-grid parity (fieldmap.c GetBorderBlockAt)."""
        gx, gy = x + 7, y + 7
        i = ((gx + 1) & 1) + ((gy + 1) & 1) * 2
        return self.border[i] if i < len(self.border) else 0

    def save(self):
        path = self.project.path(self.entry["blockdata_filepath"])
        data = struct.pack(f"<{len(self.blocks)}H", *self.blocks)
        if open(path, "rb").read() == data:
            return                     # shared, unchanged layouts are safe to re-apply
        users = layout_users(self.project, self.entry)
        if len(users) > 1:
            raise SharedLayoutError(f"layout {self.id} is shared by {', '.join(users)}; "
                                    "run dev/unique_layout.py <Map> --apply before editing its terrain")
        atomic_write(path, data)


class MapData:
    def __init__(self, project, name):
        self.project, self.name = project, name
        self.json_path = project.path("data/maps", name, "map.json")
        self.j = json.load(open(self.json_path, encoding="utf-8"))
        self.layout = project.load_layout(self.j["layout"])

    @property
    def id(self): return self.j["id"]

    def events(self, kind):
        return self.j.get(kind) or []

    @property
    def connections(self):
        return self.j.get("connections") or []

    def save(self):
        """Write map.json the way Porymap does (2-space indent, UTF-8, LF, trailing newline)."""
        dump_json(self.json_path, self.j)
