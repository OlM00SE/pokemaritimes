"""In-game: every person, trainer, sign and hidden item on a map works the way the model says.

  python dev/tests/ingame_events.py [Map ...]          (default: Route201_1 Woodstock_2)

From a new game (no wild battles; trainers can see; a level-50 party Pokémon via the dev bridge),
for each event the engine model (mapkit/events.py) can trigger:
  - sign / person: walk onto one of the model's trigger tiles facing it, press A: a script must
    take control (a message box); a person must still block the tile it stands on.
  - hidden item: as above; pressing A again must do nothing (its flag is set, it's gone).
  - item ball: as above; the item lands in the bag, its flag is set, the ball is gone and A
    again does nothing.
  - gift (a spec person with gift = ...): the first talk puts the item in the bag and sets the
    flag; a second talk gives nothing more.
  - wanderer: watched for a while, it never leaves its range; then it is talked to from beside
    wherever it stands.
  - trainer: standing beside its sight (a tile the model says it can't see) starts nothing;
    stepping into its farthest sight tile makes it walk up and start a battle, which the test
    wins. Afterwards stepping into its sight starts nothing, and talking gives its after-battle
    words without a battle.
Trigger tiles are picked outside every trainer's sight, so one test can't set off another.
Screenshots of each message: dev/out/events_<Map>_<name>.png. Exit code 1 on any failure.
"""
import glob, os, sys, tomllib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED, flag_id
from playtest import prepare_rom
from mapkit.project import Project
from mapkit.engine import World, DIRS, DIR_NAME
from mapkit import events as ev
from events import analyse_map, map_token, local_id, gift_flag

OUT = os.path.join(REPO, "dev", "out")
PLAYER_MON = "STARLY"


class Run:
    def __init__(self, e, p, name):
        self.e, self.p, self.name = e, p, name
        self.m = p.load_map(name)
        self.a, _, _ = analyse_map(p, self.m)
        w = self.world = World(p, self.m, self.a["blockers"])      # people at home, as analysed
        self.states = {}                                             # map tile -> reachable states
        for s in self.a["reach"]:
            if w.in_map(s[0], s[1]):
                self.states.setdefault(w.to_map(s[0], s[1]), []).append(s)
        self.reach = set(self.states)
        self.sight = set().union(*self.a["seen"].values()) if self.a["seen"] else set()
        # a wanderer may be anywhere in its range: no other test stands, steps or turns there
        self.ranges = set().union(set(), *(ev.wander_box(o, self.m) for o in self.m.events("object_events")
                                           if ev.moves(o) and not ev.hidden_by_flag(o)))
        self.avoid = self.sight | self.ranges
        self.passed = self.failed = 0
        self.gifts = spec_gifts(p, name)

    def check(self, ok, what):
        print(f"  {'PASS' if ok else 'FAIL'}: {what}")
        self.passed += ok
        self.failed += not ok
        return ok

    def stand(self, x, y, d):
        """Get onto (x, y) facing d: from the tile behind it, step forward (so the player faces d).
        Falls back to warping onto the tile and tapping d to turn in place."""
        dx, dy = DIRS[d]
        behind = (x - dx, y - dy)
        if behind in self.reach and behind not in self.avoid:
            self.e.warp(self.name, *behind)
            self.e.press(DIR_NAME[d], 16, 2)
            self.e.wait(12)
        else:
            self.e.warp(self.name, x, y)
            self.e.press(DIR_NAME[d], 2, 8)
        pos = self.e.player()
        return (pos[2], pos[3]) == (x, y) and self.e.facing() == d

    def spot_for(self, key):
        """A trigger tile outside every trainer's sight and every wanderer's range, preferring one
        with a free tile behind."""
        spots = [s for s in self.a["spots"].get(key, []) if (s[0], s[1]) not in self.avoid]
        def behind_ok(s):
            dx, dy = DIRS[s[2]]
            return (s[0] - dx, s[1] - dy) in self.reach and (s[0] - dx, s[1] - dy) not in self.avoid
        spots.sort(key=lambda s: (not behind_ok(s), s))
        return spots[0] if spots else None

    def press_a(self, tag):
        """Press A; True if a script took control. Screenshots the message, then closes it."""
        self.e.press("A", 3, 30)
        took = not self.e.has_control(6)
        if took:
            self.e.wait(150)                     # let the first box finish printing
            self.e.shot(os.path.join(OUT, f"events_{self.name}_{tag}.png"))
            self.e.advance_text("B")
        return took

    def talk(self, kind, i, evt, tag):
        spot = self.spot_for((kind, i))
        where = f"({evt['x']},{evt['y']})"
        if not self.check(spot is not None, f"{tag} {where}: the model gives a trigger tile outside sight"):
            return False
        x, y, d = spot
        if not self.check(self.stand(x, y, d), f"{tag}: stand on ({x},{y}) facing {d}"):
            return False
        return self.check(self.press_a(tag), f"{tag}: A from ({x},{y}) facing {d} runs its script")

    def person(self, i, o, tag):
        if self.talk("object_events", i, o, tag):
            x, y, d = self.spot_for(("object_events", i))
            self.e.press(DIR_NAME[d], 16, 2)
            self.e.wait(10)
            pos = self.e.player()
            self.check((pos[2], pos[3]) == (x, y) and self.e.object_at(o["x"], o["y"]),
                       f"{tag}: blocks its tile ({o['x']},{o['y']})")

    def item_ball(self, i, o, tag):
        item, flag = o["trainer_sight_or_berry_tree_id"], o["flag"]
        before = self.e.bag_count(item)
        if self.talk("object_events", i, o, tag):
            self.e.wait_for_control()
            self.check(self.e.bag_count(item) == before + 1, f"{tag}: {item} is in the bag ({before} -> "
                                                            f"{self.e.bag_count(item)})")
            self.check(self.e.get_flag(flag), f"{tag}: {flag} is set")
            self.check(not self.e.object_at(o["x"], o["y"]), f"{tag}: the ball is gone")
            self.check(not self.press_a(tag + "_again"), f"{tag}: A again does nothing")

    def gift(self, i, o, tag, g):
        item, count, flag = g
        before = self.e.bag_count(item)
        if self.talk("object_events", i, o, tag):
            self.e.wait_for_control()
            got = self.e.bag_count(item)
            self.check(got == before + count, f"{tag}: gives {count} {item} ({before} -> {got})")
            self.check(self.e.get_flag(flag), f"{tag}: {flag} is set")
            if self.talk("object_events", i, o, tag + "_again"):
                self.e.wait_for_control()
                self.check(self.e.bag_count(item) == got, f"{tag}: a second talk gives nothing more")

    def wanderer(self, i, o, tag, watch_frames=1800):
        box = ev.wander_box(o, self.m)
        lid = i + 1                               # map_event_ids.h: local ids follow object order
        # watch from a tile outside its range, so the player doesn't hem it in
        far = next((t for t in sorted(self.reach - box - self.sight,
                                      key=lambda t: abs(t[0] - o["x"]) + abs(t[1] - o["y"]))
                    if max(abs(t[0] - o["x"]), abs(t[1] - o["y"])) >= 4), None)
        if not self.check(far is not None, f"{tag}: a tile to watch it from"):
            return
        self.e.warp(self.name, *far)
        seen = set()
        for _ in range(watch_frames // 30):
            self.e.wait(30)
            seen |= {(x, y) for l, x, y in self.e.objects() if l == lid}
        self.check(bool(seen) and seen <= box, f"{tag}: stays in its range {min(box)}-{max(box)} "
                                               f"(stood on {len(seen)} tiles: {sorted(seen)[:6]}"
                                               f"{'...' if len(seen) > 6 else ''})")
        self.check(len(seen) > 1, f"{tag}: it does wander")
        for attempt in range(8):                  # it may step away between the warp and the A press
            pos = next(((x, y) for l, x, y in self.e.objects() if l == lid), None)
            spot = pos and next(((pos[0] - dx, pos[1] - dy, d) for d, (dx, dy) in DIRS.items()
                                 if (pos[0] - dx, pos[1] - dy) in self.reach
                                 and (pos[0] - dx, pos[1] - dy) not in self.sight), None)
            if not spot:
                self.e.wait(60)
                continue
            x, y, d = spot
            self.e.warp(self.name, x, y)
            self.e.press(DIR_NAME[d], 2, 4)
            now = next(((ox, oy) for l, ox, oy in self.e.objects() if l == lid), None)
            if now != pos or self.e.facing() != d:
                continue
            if self.press_a(tag):
                self.check(True, f"{tag}: talked to from ({x},{y}) facing {d} (attempt {attempt + 1})")
                return
        self.check(False, f"{tag}: could not be talked to in 8 attempts")

    def hidden(self, i, b, tag):
        if self.talk("bg_events", i, b, tag):
            self.check(not self.press_a(tag + "_again"), f"{tag}: found once; A again does nothing")

    def trainer(self, i, o, tag):
        seen = self.a["seen"].get(i, set())
        if not self.check(bool(seen), f"{tag}: the model says a walker can step into its sight"):
            return
        # the farthest seen tile, entered from a tile the trainer can't see
        far = sorted(seen, key=lambda t: -abs(t[0] - o["x"]) - abs(t[1] - o["y"]))

        def walks_onto(n, d, t):
            """In the model, a plain step d from a reachable state on n lands on t (not a ledge
            jump past it, not a refusal)."""
            for s in self.states.get(n, ()):
                ns, kind = self.world.step(s, d)
                if ns is not None and kind == "walk" and self.world.to_map(ns[0], ns[1]) == t:
                    return True
            return False
        pick = next(((t, n, d) for t in far for d, (dx, dy) in DIRS.items()
                     for n in [(t[0] - dx, t[1] - dy)]
                     if n in self.reach and n not in self.avoid and t not in self.ranges
                     and walks_onto(n, d, t)), None)
        if not self.check(pick is not None, f"{tag}: a tile beside its sight to step in from"):
            return
        t, n, d = pick
        self.e.warp(self.name, *n)
        self.e.wait(60)
        self.check(self.e.has_control() and not self.e.in_battle(), f"{tag}: at {n}, outside its sight, nothing happens")
        self.e.press(DIR_NAME[d], 16, 2)
        self.e.wait(70)
        self.e.shot(os.path.join(OUT, f"events_{self.name}_{tag}_spotted.png"))
        started = False
        for _ in range(60):                       # its walk, then the intro text
            if self.e.in_battle():
                started = True
                break
            self.e.press("B", 3, 15)
        if not self.check(started, f"{tag}: stepping into its sight at {t} starts a battle"):
            return
        self.e.win_battle()
        self.check(self.e.in_overworld() and self.e.has_control(), f"{tag}: the battle is won")
        self.e.warp(self.name, *n)
        self.e.press(DIR_NAME[d], 16, 2)
        self.e.wait(90)
        self.check(self.e.has_control() and not self.e.in_battle(), f"{tag}: once beaten, its sight starts nothing")
        if self.talk("object_events", i, o, tag + "_after"):
            self.e.wait(30)
            self.check(not self.e.in_battle(), f"{tag}: talking after the battle starts no battle")

    def run(self):
        print(f"{self.name}:")
        objs, bgs = self.m.events("object_events"), self.m.events("bg_events")
        for i, o in enumerate(objs):
            tag = (o.get("local_id") or f"object{i}").replace("LOCALID_", "").lower()
            if ev.is_item_ball(o):
                self.item_ball(i, o, tag)
            elif ev.hidden_by_flag(o) or o.get("script") in ev.NO_SCRIPT or ev.is_trainer(o):
                continue
            elif o.get("local_id") in self.gifts:
                self.gift(i, o, tag, self.gifts[o["local_id"]])
            elif ev.moves(o):
                self.wanderer(i, o, tag)
            else:
                self.person(i, o, tag)
        for i, b in enumerate(bgs):
            tag = f"{b.get('type')}{i}"
            if b.get("type") == "sign":
                self.talk("bg_events", i, b, tag)
            elif b.get("type") == "hidden_item":
                self.hidden(i, b, tag)
        for i, o in enumerate(objs):              # last: a battle changes the party's state
            if ev.is_trainer(o) and not ev.hidden_by_flag(o):
                self.trainer(i, o, (o.get("local_id") or f"trainer{i}").replace("LOCALID_", "").lower())
        print(f"{self.name}: {self.passed}/{self.passed + self.failed} checks pass")
        return self.failed == 0


def spec_gifts(p, name):
    """{local id: (item, count, flag)} for the gift people in the map's events spec, if any."""
    out = {}
    for path in glob.glob(p.path("design", "maps", f"{name}.events.toml")):
        spec = tomllib.load(open(path, "rb"))
        tok = map_token(p.load_map(name))
        for e in spec.get("person", []):
            if "gift" in e:
                out[local_id(tok, e["name"])] = (e["gift"], e.get("count", 1), gift_flag(tok, e["name"]))
    return out


def main(argv):
    names = argv or ["Route201_1", "Woodstock_2"]
    p = Project()
    rom = prepare_rom(fresh=True)
    ok = True
    with Emu(rom, extra_args=UNTHROTTLED) as e:
        if not e.boot_new_game():
            print("FAIL: never reached the overworld")
            return 1
        e.test_mode(trainer_sight=True)
        e.give_mon(PLAYER_MON, 50)
        # win_battle uses the first move every turn, so make it a plain damaging one, and make
        # the Pokémon obey: with no badges a level-50 Pokémon disobeys ("began to nap") and
        # the battle can go on forever. The eighth badge makes every level obey.
        e.teach_move("TACKLE", 0)
        e.set_flag(flag_id("FLAG_BADGE08_GET"))
        for name in names:
            ok &= Run(e, p, name).run()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
