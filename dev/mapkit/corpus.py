"""Statistics mined from vanilla Emerald layouts: how the original maps use each metatile.

Keys are (tileset_name, local_index) so primary metatiles pool across every map that uses
that primary, and secondary metatiles are specific to their secondary tileset.

  attrs[key]      Counter of (collision, elevation)
  neigh[key][d]   Counter of neighbour keys in direction d (N,S,W,E)
"""
import json, os, pickle, struct, subprocess
from collections import Counter, defaultdict
from .project import NUM_METATILES_IN_PRIMARY

UPSTREAM = "expansion/1.17.2"


def key_of(layout_entry, mid):
    if mid < NUM_METATILES_IN_PRIMARY:
        return (layout_entry["primary_tileset"], mid)
    return (layout_entry["secondary_tileset"], mid - NUM_METATILES_IN_PRIMARY)


class Corpus:
    def __init__(self, project, cache=True):
        self.p = project
        path = project.path("dev", "out", "corpus.pkl")
        src_mtime = os.path.getmtime(project.path("data/layouts/layouts.json"))
        if cache and os.path.exists(path) and os.path.getmtime(path) > src_mtime:
            self.__dict__.update(pickle.load(open(path, "rb")))
            self.p = project
            return
        self.attrs = defaultdict(Counter)
        self.neigh = defaultdict(lambda: defaultdict(Counter))
        self.layouts_used = 0
        for entry in self._vanilla_layouts():
            self._ingest(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {"attrs": dict(self.attrs), "layouts_used": self.layouts_used,
                "neigh": {k: dict(v) for k, v in self.neigh.items()}}
        pickle.dump(data, open(path, "wb"))
        self.attrs = defaultdict(Counter, data["attrs"])

    def _vanilla_layouts(self):
        """Emerald layouts that exist upstream (excludes our own and FRLG layouts)."""
        r = subprocess.run(["git", "-C", self.p.root, "show", f"{UPSTREAM}:data/layouts/layouts.json"],
                           capture_output=True, check=True)
        upstream = {l["id"] for l in json.loads(r.stdout)["layouts"] if "id" in l}
        for lid, e in self.p.layouts.items():
            if lid in upstream and not lid.endswith("_FRLG") and "Frlg" not in e.get("name", ""):
                path = self.p.path(e["blockdata_filepath"])
                if os.path.exists(path) and e["primary_tileset"] in self.p.tileset_sources:
                    yield e

    def _ingest(self, e):
        w, h = e["width"], e["height"]
        raw = open(self.p.path(e["blockdata_filepath"]), "rb").read()
        if len(raw) < w * h * 2:
            return
        b = struct.unpack(f"<{w * h}H", raw[: w * h * 2])
        self.layouts_used += 1
        for y in range(h):
            for x in range(w):
                v = b[y * w + x]
                k = key_of(e, v & 0x3FF)
                self.attrs[k][((v >> 10) & 3, v >> 12)] += 1
                for d, (dx, dy) in (("N", (0, -1)), ("S", (0, 1)), ("W", (-1, 0)), ("E", (1, 0))):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        self.neigh[k][d][key_of(e, b[ny * w + nx] & 0x3FF)] += 1

    def default_attrs(self, layout_entry, mid, min_count=5, min_share=0.8):
        """Most common (collision, elevation) for this metatile in vanilla, if confident."""
        c = self.attrs.get(key_of(layout_entry, mid))
        if not c:
            return None
        (ce, n), total = c.most_common(1)[0], sum(c.values())
        if total >= min_count and n / total >= min_share:
            return ce
        return None
