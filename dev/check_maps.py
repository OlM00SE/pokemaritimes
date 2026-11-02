"""Static map checker: catches broken maps without running the game.

  python dev/check_maps.py              # Maritimes maps (those not in upstream expansion)
  python dev/check_maps.py HomeTown_0   # specific maps
  python dev/check_maps.py --all        # every map

Checks: layout size vs map.bin; warps (bounds, destination, tile is enterable,
not water); connections (target exists, reciprocal with matching offset);
events in bounds; script labels defined; on-foot reachability between all
entrances/exits (warps + connection edges), honoring collision, water,
elevation and one-way ledges. Exit code 1 if any ERROR.
"""
import json, os, re, struct, subprocess, sys
from collections import deque

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "dev"))
from render_map import parse_tileset_paths

UPSTREAM = "expansion/1.17.2"


def rp(*p): return os.path.join(REPO, *p)


def behaviors():
    """Parse the MB_* enum (by position) -> {name: value}."""
    src = open(rp("include/constants/metatile_behaviors.h")).read()
    body = re.search(r"enum\s*\{(.*?)\};", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    out, v = {}, 0
    for item in [s.strip() for s in body.split(",") if s.strip()]:
        if "=" in item:
            name, val = [s.strip() for s in item.split("=")]
            v = int(val, 0)
        else:
            name = item
        out[name] = v
        v += 1
    return out


MB = behaviors()
WATER = {MB[n] for n in MB if re.search(r"(DEEP|OCEAN|POND|FAST|CYCLING_ROAD)_WATER$|WATERFALL|NO_SURFACING|CURRENT", n)}
ENTERABLE = {MB[n] for n in MB if re.search(r"DOOR|WARP|LADDER|STAIRS|HOLE|ESCALATOR", n)}
JUMP = {MB.get("MB_JUMP_EAST"): (1, 0), MB.get("MB_JUMP_WEST"): (-1, 0),
        MB.get("MB_JUMP_NORTH"): (0, -1), MB.get("MB_JUMP_SOUTH"): (0, 1)}


class Tilesets:
    def __init__(self):
        self.paths = parse_tileset_paths(REPO)
        self.cache = {}

    def attrs(self, ts):
        if ts not in self.cache:
            folder, _ = self.paths[ts]
            raw = open(rp(folder, "metatile_attributes.bin"), "rb").read()
            self.cache[ts] = struct.unpack(f"<{len(raw)//2}H", raw)
        return self.cache[ts]

    def behavior(self, pri, sec, mid):
        a = self.attrs(pri) if mid < 512 else self.attrs(sec)
        i = mid if mid < 512 else mid - 512
        return a[i] & 0xFF if i < len(a) else 0


def all_labels():
    labels = set()
    for root, _, files in os.walk(rp("data")):
        for f in files:
            if f.endswith((".inc", ".s", ".pory")):
                txt = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
                labels.update(re.findall(r"^(\w+)::?", txt, re.M))
                labels.update(re.findall(r"^\s*(?:script|text|movement|mapscripts)\s+(\w+)", txt, re.M))
    return labels


def maritimes_maps():
    r = subprocess.run(["git", "-C", REPO, "ls-tree", "-d", "--name-only", f"{UPSTREAM}:data/maps"],
                       capture_output=True, text=True)
    upstream = set(r.stdout.split())
    return sorted(d for d in os.listdir(rp("data/maps"))
                  if os.path.isdir(rp("data/maps", d)) and d not in upstream)


class Map:
    def __init__(self, name, layouts, ts):
        self.name = name
        self.j = json.load(open(rp("data/maps", name, "map.json")))
        lay = layouts[self.j["layout"]]
        self.w, self.h = lay["width"], lay["height"]
        raw = open(rp(lay["blockdata_filepath"]), "rb").read()
        self.size_ok = len(raw) == self.w * self.h * 2
        n = min(len(raw) // 2, self.w * self.h)
        self.blocks = list(struct.unpack(f"<{n}H", raw[: n * 2])) + [0x0400] * (self.w * self.h - n)
        self.pri, self.sec = lay["primary_tileset"], lay["secondary_tileset"]
        self.ts = ts

    def inb(self, x, y): return 0 <= x < self.w and 0 <= y < self.h
    def block(self, x, y): return self.blocks[y * self.w + x]
    def coll(self, x, y): return (self.block(x, y) >> 10) & 3
    def elev(self, x, y): return self.block(x, y) >> 12
    def beh(self, x, y): return self.ts.behavior(self.pri, self.sec, self.block(x, y) & 0x3FF)

    def walkable(self, x, y):
        return self.inb(x, y) and self.coll(x, y) == 0 and self.beh(x, y) not in WATER

    def can_move(self, x, y, nx, ny):
        if not self.walkable(nx, ny):
            return False
        a, b = self.elev(x, y), self.elev(nx, ny)
        if a not in (0, 15) and b not in (0, 15) and a != b:
            return False
        jd = JUMP.get(self.beh(nx, ny))   # ledge tile: only enter moving in its direction
        if jd and (nx - x, ny - y) != jd:
            return False
        return True

    def component_map(self):
        comp, cid = {}, 0
        for sy in range(self.h):
            for sx in range(self.w):
                if (sx, sy) in comp or not self.walkable(sx, sy):
                    continue
                q = deque([(sx, sy)]); comp[(sx, sy)] = cid
                while q:
                    x, y = q.popleft()
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if (nx, ny) not in comp and self.can_move(x, y, nx, ny):
                            # ledges are one-way: jumping lands one past the ledge
                            jd = JUMP.get(self.beh(nx, ny))
                            if jd:
                                lx, ly = nx + jd[0], ny + jd[1]
                                if self.walkable(lx, ly) and (lx, ly) not in comp:
                                    comp[(lx, ly)] = cid; q.append((lx, ly))
                                continue
                            comp[(nx, ny)] = cid; q.append((nx, ny))
                cid += 1
        return comp


def check(names, verbose=False):
    layouts = {l["id"]: l for l in json.load(open(rp("data/layouts/layouts.json")))["layouts"] if "id" in l}
    ts = Tilesets()
    labels = all_labels()
    errors = warnings = 0
    cache = {}

    def get(n):
        if n not in cache:
            cache[n] = Map(n, layouts, ts)
        return cache[n]

    const_to_name = {}
    for d in os.listdir(rp("data/maps")):
        p = rp("data/maps", d, "map.json")
        if os.path.exists(p):
            const_to_name[json.load(open(p))["id"]] = d

    for name in names:
        issues = []
        def err(msg): issues.append(("ERROR", msg))
        def warn(msg): issues.append(("warn", msg))
        m = get(name)
        if not m.size_ok:
            err(f"map.bin size does not match layout {m.w}x{m.h}")
        entries = []   # (label, set of tiles)

        for i, wv in enumerate(m.j.get("warp_events") or []):
            x, y = wv["x"], wv["y"]
            if not m.inb(x, y):
                err(f"warp {i} at ({x},{y}) is out of bounds"); continue
            b = m.beh(x, y)
            if b in WATER:
                err(f"warp {i} at ({x},{y}) sits on WATER")
            elif m.coll(x, y) != 0 and b not in ENTERABLE:
                err(f"warp {i} at ({x},{y}) is on a blocked tile with no door/warp behavior")
            dest = const_to_name.get(wv["dest_map"])
            if wv["dest_map"] not in ("MAP_DYNAMIC", "MAP_NONE") and not dest:
                err(f"warp {i} -> unknown map {wv['dest_map']}")
            elif dest:
                dw = get(dest).j.get("warp_events") or []
                wid = str(wv["dest_warp_id"])
                if wid.isdigit() and int(wid) >= len(dw):
                    err(f"warp {i} -> {dest} warp {wid}, but {dest} has only {len(dw)} warps")
                elif wid.isdigit() and dw[int(wid)]["dest_map"] != m.j["id"]:
                    warn(f"warp {i} -> {dest} warp {wid}, which leads to {dw[int(wid)]['dest_map']} (not back here)")
            # A door is entered from the tile in front of it; count both as the entry.
            tiles = {(x, y), (x, y + 1)} if m.coll(x, y) else {(x, y)}
            entries.append((f"warp {i}", tiles))

        opp = {"up": "down", "down": "up", "left": "right", "right": "left"}
        for c in m.j.get("connections") or []:
            dest = const_to_name.get(c["map"])
            if not dest:
                err(f"connection {c['direction']} -> unknown map {c['map']}"); continue
            back = [k for k in (get(dest).j.get("connections") or [])
                    if k["map"] == m.j["id"] and k["direction"] == opp[c["direction"]]]
            if not back:
                err(f"connection {c['direction']} -> {dest} has no reciprocal connection back")
            elif back[0]["offset"] != -c["offset"]:
                err(f"connection {c['direction']} -> {dest} offset {c['offset']} but reverse offset "
                    f"{back[0]['offset']} (should be {-c['offset']})")
            d, o, other = c["direction"], c["offset"], get(dest)
            if d in ("up", "down"):
                y = 0 if d == "up" else m.h - 1
                span = [(x, y) for x in range(max(0, o), min(m.w, o + other.w))]
            else:
                x = 0 if d == "left" else m.w - 1
                span = [(x, y) for y in range(max(0, o), min(m.h, o + other.h))]
            if not span:
                err(f"connection {d} -> {dest} does not overlap this map (offset {o})")
            open_tiles = {t for t in span if m.walkable(*t)}
            if span and not open_tiles:
                warn(f"connection {d} -> {dest}: no walkable tile along the shared edge")
            if open_tiles:
                entries.append((f"edge {d}->{dest}", open_tiles))

        for kind in ("object_events", "bg_events", "coord_events"):
            for i, ev in enumerate(m.j.get(kind) or []):
                if not m.inb(ev["x"], ev["y"]):
                    err(f"{kind}[{i}] at ({ev['x']},{ev['y']}) out of bounds")
                s = ev.get("script")
                if s is not None and s not in ("0x0", "") and s not in labels:
                    err(f"{kind}[{i}] script '{s}' is not defined anywhere")

        comp = m.component_map()
        groups = {}
        for label, tiles in entries:
            cids = {comp[t] for t in tiles if t in comp}
            if not cids:
                err(f"{label}: no walkable tile here (unreachable on foot)")
            groups[label] = cids
        if len(entries) > 1:
            main = max(groups.values(), key=len, default=set())
            # union-find style: entries sharing any component are connected
            reach = {}
            for label, cids in groups.items():
                reach[label] = cids
            linked = [set(c) for c in reach.values() if c]
            merged = []
            for s in linked:
                for t in merged:
                    if s & t:
                        t |= s; break
                else:
                    merged.append(s)
            if len(merged) > 1:
                parts = []
                for s in merged:
                    parts.append("[" + ", ".join(l for l, c in reach.items() if c & s) + "]")
                warn("on foot, entrances split into separate areas: " + " | ".join(parts))

        nerr = sum(1 for k, _ in issues if k == "ERROR")
        errors += nerr; warnings += len(issues) - nerr
        status = "OK " if not issues else ("ERR" if nerr else "WRN")
        print(f"[{status}] {name} ({m.w}x{m.h})")
        for k, msg in issues:
            print(f"      {k}: {msg}")
    print(f"\n{len(names)} maps, {errors} errors, {warnings} warnings")
    return errors


if __name__ == "__main__":
    args = sys.argv[1:]
    names = sorted(os.listdir(rp("data/maps"))) if "--all" in args else (
        [a for a in args if not a.startswith("--")] or maritimes_maps())
    names = [n for n in names if os.path.exists(rp("data/maps", n, "map.json"))]
    sys.exit(1 if check(names) else 0)
