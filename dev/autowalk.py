"""Auto-walker: plan with the engine model (mapkit.engine) and execute in mGBA.

  python dev/autowalk.py HomeTown_0 Route201_1 Woodstock_2    # new game, then walk map to map
  python dev/autowalk.py --to Woodstock_2 23,14               # ...then walk to a tile

Library:  wk = Walker(emu); wk.go_to_map("Woodstock_2"); wk.go_to_tile(23, 14)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.engine import World, DIR_NAME
from mapkit.checks import _warp_kinds
from mgba_bridge import Emu, REPO, UNTHROTTLED


class Walker:
    def __init__(self, emu, project=None, log=print):
        self.e, self.p, self.log = emu, project or Project(), log
        self._worlds = {}
        self.step_on, self.door, self.arrow, self.stair = _warp_kinds(self.p)

    def world(self, name):
        if name not in self._worlds:
            self._worlds[name] = World(self.p, self.p.load_map(name))
        return self._worlds[name]

    def here(self):
        loc = self.e.player()
        return self.p.const_to_map.get("MAP_" + self.e.map_name(loc)), (loc[2], loc[3])

    def player_elevations(self):
        """(currentElevation, previousElevation): ObjectEvent byte 0x0B, low/high nibble."""
        oid = self.e.read8(self.e.sym["gPlayerAvatar"] + 5)
        v = self.e.read8(self.e.sym["gObjectEvents"] + oid * 0x24 + 0x0B)
        return v & 0xF, v >> 4

    def surfing(self):
        return bool(self.e.read8(self.e.sym["gPlayerAvatar"]) & 0x08)   # PLAYER_AVATAR_FLAG_SURFING

    def _state(self, w):
        name, (x, y) = self.here()
        gx, gy = w.to_grid(x, y)
        return (gx, gy, *self.player_elevations(), self.surfing())

    def _goals(self, name, target):
        """(predicate on state, final press or None) for leaving `name` toward `target`."""
        w, m = self.world(name), self.p.load_map(name)
        tconst = self.p.load_map(target).id
        goals = [(lambda s, c=cell: (s[0], s[1]) == c, None)
                 for cell, (d, n) in w.conn_side.items() if n == target]
        for wv in m.events("warp_events"):
            if wv["dest_map"] != tconst:
                continue
            gx, gy = w.to_grid(wv["x"], wv["y"])
            b = w.behavior(gx, gy)
            if b in self.door:
                goals.append((lambda s, gx=gx, gy=gy: (s[0], s[1]) == (gx, gy + 1), "N"))
            elif b in self.arrow:
                goals.append((lambda s, gx=gx, gy=gy: (s[0], s[1]) == (gx, gy), self.arrow[b]))
            elif b in self.stair:
                goals.append((lambda s, gx=gx, gy=gy: (s[0], s[1]) == (gx, gy), self.stair[b]))
            else:
                goals.append((lambda s, gx=gx, gy=gy: (s[0], s[1]) == (gx, gy), None))
        return goals

    def _walk(self, w, goals, allow_surf=False):
        start = self._state(w)
        seen = w.explore([start], allow_surf=allow_surf)
        hit = next(((s, press) for s in seen for pred, press in goals if pred(s)), None)
        if not hit:
            return False
        for d, kind in w.path_to(seen, hit[0]):
            self.e.press(DIR_NAME[d], 16 if kind != "jump" else 4, 2)
            self.e.wait(20 if kind == "jump" else 0)
        if hit[1]:
            self.e.press(DIR_NAME[hit[1]], 16, 2)
        return True

    def go_to_map(self, target, max_legs=4):
        for _ in range(max_legs):
            name, pos = self.here()
            if name == target:
                return True
            if not self._walk(self.world(name), self._goals(name, target)):
                self.log(f"  no path in {name} from {pos} toward {target}")
                return False
            self.e.wait(90)
            self.e.wait_until(self.e.in_overworld, 600)
        return self.here()[0] == target

    def go_to_tile(self, x, y, allow_surf=False):
        name, _ = self.here()
        w = self.world(name)
        gx, gy = w.to_grid(x, y)
        ok = self._walk(w, [(lambda s: (s[0], s[1]) == (gx, gy), None)], allow_surf)
        self.e.wait(20)
        return ok and self.here()[1] == (x, y)


def main(argv):
    from playtest import prepare_rom
    out = os.path.join(REPO, "dev", "out")
    to = None
    if "--to" in argv:
        i = argv.index("--to")
        to = tuple(map(int, argv[i + 2].split(",")))
        argv = argv[:i] + [argv[i + 1]]
    rom = prepare_rom(fresh=True)
    ok = True
    with Emu(rom, extra_args=UNTHROTTLED) as e:
        if not e.boot_new_game():
            print("FAIL: never reached overworld"); return 1
        e.test_mode()           # no wild battles or trainer sight: the walker only tests movement
        wk = Walker(e)
        print("start:", *wk.here())
        for i, target in enumerate(argv):
            reached = wk.go_to_map(target)
            e.shot(os.path.join(out, f"route_{i:02}_{target}.png"))
            print(f"{'PASS' if reached else 'FAIL'}: -> {target}  (now {wk.here()[0]} {wk.here()[1]})")
            ok &= reached
            if not reached:
                break
        if ok and to:
            r = wk.go_to_tile(*to)
            e.shot(os.path.join(out, "route_tile.png"))
            print(f"{'PASS' if r else 'FAIL'}: -> tile {to}  (now {wk.here()[1]})")
            ok &= r
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
