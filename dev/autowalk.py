"""Auto-walker: plan paths from map data (check_maps.Map) and execute them in mGBA.

  python dev/autowalk.py HomeTown_0 Route201_1 Woodstock_2   # walk a sequence of maps
  (starts a new game; the first map in the list must be reached from the start
   position via warps/connections in the listed order)

Library use:  walker = Walker(emu); walker.go_to_map("Woodstock_2")
"""
import json, os, sys
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_maps import Map, Tilesets, rp, JUMP
from mgba_bridge import Emu, REPO, UNTHROTTLED

DIRV = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
EDGE_DIR = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}


class World:
    def __init__(self):
        self.layouts = {l["id"]: l for l in json.load(open(rp("data/layouts/layouts.json")))["layouts"] if "id" in l}
        self.ts = Tilesets()
        self.maps = {}
        self.const = {}
        for d in os.listdir(rp("data/maps")):
            p = rp("data/maps", d, "map.json")
            if os.path.exists(p):
                self.const[json.load(open(p))["id"]] = d

    def get(self, name):
        if name not in self.maps:
            self.maps[name] = Map(name, self.layouts, self.ts)
        return self.maps[name]

    def exits_to(self, name, target):
        """Goal specs in `name` that lead to `target`: (tile, final_press_direction)."""
        m, goals = self.get(name), []
        tconst = self.get(target).j["id"]
        for c in m.j.get("connections") or []:
            if c["map"] != tconst:
                continue
            d = EDGE_DIR[c["direction"]]
            o, t = c["offset"], self.get(target)
            if d in ("UP", "DOWN"):
                y = 0 if d == "UP" else m.h - 1
                goals += [((x, y), d) for x in range(max(0, o), min(m.w, o + t.w))]
            else:
                x = 0 if d == "LEFT" else m.w - 1
                goals += [((x, y), d) for y in range(max(0, o), min(m.h, o + t.h))]
        for wv in m.j.get("warp_events") or []:
            if wv["dest_map"] == tconst:
                x, y = wv["x"], wv["y"]
                if m.coll(x, y):            # door: stand below it and press UP
                    goals.append(((x, y + 1), "UP"))
                else:                       # mat/stairs: step on, then nudge
                    goals.append(((x, y), None))
        return goals


def bfs(m, start, goals):
    """BFS over walkable tiles; returns (list of directions, goal) or (None, None)."""
    goal_tiles = {g[0]: g for g in goals}
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur in goal_tiles:
            g = goal_tiles[cur]
            path = []
            while prev[cur]:
                cur, d = prev[cur]
                path.append(d)
            return path[::-1], g
        x, y = cur
        for d, (dx, dy) in DIRV.items():
            n = (x + dx, y + dy)
            if not m.can_move(x, y, *n):
                continue
            if JUMP.get(m.beh(*n)):               # one press hops over the ledge
                n = (n[0] + dx, n[1] + dy)
                if not m.walkable(*n):
                    continue
            if n not in prev:
                prev[n] = (cur, d)
                q.append(n)
    return None, None


class Walker:
    def __init__(self, emu, world=None, log=print):
        self.e, self.w, self.log = emu, world or World(), log

    def here(self):
        loc = self.e.player()
        const = "MAP_" + self.e.map_name(loc)
        return self.w.const.get(const), (loc[2], loc[3])

    def go_to_map(self, target, max_legs=6):   # re-plans from the live position each leg
        for _ in range(max_legs):
            name, pos = self.here()
            if name == target:
                return True
            m = self.w.get(name)
            path, goal = bfs(m, pos, self.w.exits_to(name, target))
            if path is None:
                self.log(f"  no path in {name} from {pos} to {target}")
                return False
            for d in path:                       # walk tile by tile, stop if the map changed
                self.e.press(d, 16, 2)
                if self.here()[0] != name:
                    break
            self.e.wait(20)
            if self.here()[0] == name and goal[1]:
                self.e.press(goal[1], 16, 2)      # cross the edge / enter the door
            if self.here()[0] == name:            # mats/stairs: nudge in each direction
                for d in ("DOWN", "UP", "LEFT", "RIGHT"):
                    self.e.press(d, 16, 2); self.e.wait(40)
                    if self.here()[0] != name:
                        break
            self.e.wait(90)                      # let warp fades finish
            if not self.e.in_overworld():
                self.e.wait_until(self.e.in_overworld, 600)
        return self.here()[0] == target


def main(seq):
    out = os.path.join(REPO, "dev", "out")
    from playtest import prepare_rom
    rom = prepare_rom(fresh=True)
    ok = True
    with Emu(rom, extra_args=UNTHROTTLED) as e:
        if not e.boot_new_game():
            print("FAIL: never reached overworld"); return 1
        wk = Walker(e)
        name, pos = wk.here()
        print(f"start: {name} {pos}")
        for i, target in enumerate(seq):
            reached = wk.go_to_map(target)
            name, pos = wk.here()
            e.shot(os.path.join(out, f"route_{i:02}_{target}.png"))
            print(f"{'PASS' if reached else 'FAIL'}: -> {target}  (now {name} {pos})")
            if not reached:
                ok = False
                break
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
