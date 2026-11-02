"""Doors: find them, and identify which vanilla building a door belongs to.

A building is recognised by the metatiles of its facade: the 5x4 block whose bottom-centre
cell is the door. Vanilla outdoor maps that use the same tileset pair are the reference
set, and each reference door's warp says which interior vanilla puts behind it.
"""
import functools, json, re, subprocess

OUTDOOR = ("MAP_TYPE_TOWN", "MAP_TYPE_CITY", "MAP_TYPE_ROUTE", "MAP_TYPE_OCEAN_ROUTE")
UPSTREAM = "expansion/1.17.2"
MIN_SCORE = 16          # of 20 facade cells; real matches score 20, unrelated buildings < 8


def door_tiles(p, m):
    door = p.behavior_set("WarpDoor")
    L = m.layout
    return [(x, y) for y in range(L.height) for x in range(L.width) if L.tiles.behavior(L.mid(x, y)) in door]


def facade(L, x, y):
    return tuple(L.mid(xx, yy) if L.inb(xx, yy) else -1
                 for yy in range(y - 3, y + 1) for xx in range(x - 2, x + 3))


@functools.lru_cache(maxsize=None)
def _upstream_maps(root):
    r = subprocess.run(["git", "-C", root, "ls-tree", "-d", "--name-only", f"{UPSTREAM}:data/maps"],
                       capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError(f"cannot list vanilla maps from git ref {UPSTREAM} (fetch the expansion "
                           f"remote's tags?): {r.stderr.strip()}")
    return frozenset(r.stdout.split())


def reference_doors(p):
    """[(tileset pair, facade, vanilla map, x, y, interior map const)] for every vanilla outdoor door warp."""
    if not hasattr(p, "_ref_doors"):
        refs = []
        for n in sorted(_upstream_maps(p.root)):
            if n.endswith("_Frlg") or n not in p.map_names:
                continue
            j = json.load(open(p.path("data/maps", n, "map.json"), encoding="utf-8"))
            if j.get("map_type") not in OUTDOOR or not j.get("warp_events"):
                continue
            m = p.load_map(n)
            L = m.layout
            doors = set(door_tiles(p, m))
            for w in m.events("warp_events"):
                if (w["x"], w["y"]) in doors:
                    refs.append(((L.primary, L.secondary), facade(L, w["x"], w["y"]), n, w["x"], w["y"],
                                 w["dest_map"]))
        p._ref_doors = refs
    return p._ref_doors


def identify(p, m, x, y):
    """Best vanilla match for the door at (x, y): (score, vanilla map, vx, vy, interior const) or None."""
    L = m.layout
    q = facade(L, x, y)
    best = None
    for pair, f, n, vx, vy, dest in reference_doors(p):
        if pair != (L.primary, L.secondary):
            continue
        s = sum(a == b for a, b in zip(f, q))
        if best is None or s > best[0]:
            best = (s, n, vx, vy, dest)
    return best if best and best[0] >= MIN_SCORE else None


def map_const(name):
    """HomeTown_House2_1F -> MAP_HOME_TOWN_HOUSE2_1F. Follows vanilla's names (SSTidal -> SS_TIDAL);
    Porymap may differ on runs of capitals, which is harmless because map.json stores the id."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name)       # "1F" and "House2" stay joined
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return "MAP_" + s.upper()
