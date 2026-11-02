"""In-game shore test: every place where land meets water behaves in mGBA as the engine model says.

For each map (default: ShoreLab and Route 203), at every land/water edge:
  bump   on foot on the land tile, press toward the water (or a water rock): the player must not move.
  land   surfing on the water tile (a warp onto water starts Surf), press toward the land: the
         player must come ashore exactly where mapkit.engine predicts (onto beach sand, or onto the
         grass bank), or be refused where the model refuses (a rock, a ledge, a solid tile).
  rock   surfing beside a water rock, press into it: blocked.
  surf   real play, for a sample of edges: on foot on the shore, facing the water, use Surf through
         the field-move prompt (a party Pokémon that knows Surf, the Balance Badge flag set): the
         player must end up surfing on that water tile.
Screenshots of the first landings go to dev/out/shores_<Map>_*.png.

  python dev/tests/ingame_shores.py [--max N] [--surf N] [Map ...]
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED, flag_id
from playtest import prepare_rom
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.engine import World, DIR_NAME
from mapkit import shores

DEFAULT_MAPS = ["ShoreLab", "Route203_1"]
OUT = os.path.join(REPO, "dev", "out")
DELTA = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
OPP = {"N": "S", "S": "N", "W": "E", "E": "W"}


def cases_for(p, name):
    m = p.load_map(name)
    w = World(p, m)
    L = m.layout
    objs = [(o["x"], o["y"]) for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near = lambda x, y: (x, y) in warps or any(abs(x - ox) + abs(y - oy) <= 2 for ox, oy in objs)
    water = lambda x, y: bool(w.flags(*w.to_grid(x, y)) & TILE_FLAG_SURFABLE)
    rock = lambda x, y: L.mid(x, y) in shores.ROCK_PIECES
    land = lambda x, y: L.coll(x, y) == 0 and not water(x, y)
    out = {"bump": [], "land": [], "rock": []}
    for y in range(L.height):
        for x in range(L.width):
            for d, (dx, dy) in DELTA.items():
                nx, ny = x + dx, y + dy
                if not (0 <= nx < L.width and 0 <= ny < L.height) or near(x, y) or near(nx, ny):
                    continue
                if land(x, y) and (water(nx, ny) or rock(nx, ny)):
                    out["bump"].append((x, y, d, (x, y), "blocked on foot"))
                if water(x, y) and (land(nx, ny) or rock(nx, ny)):
                    ns, kind = w.step(w.arrival_state(*w.to_grid(x, y)), d)
                    exp = (x, y) if ns is None else w.to_map(ns[0], ns[1])
                    out["rock" if rock(nx, ny) else "land"].append((x, y, d, exp, kind))
    return out


def press_toward(e, d, x, y):
    """A tap turns the player if facing elsewhere, or moves if already facing d."""
    e.press(DIR_NAME[d], 3, 40)
    loc = e.player()
    if (loc[2], loc[3]) == (x, y):
        e.press(DIR_NAME[d], 3, 60)
        loc = e.player()
    e.wait(20)
    return (loc[2], loc[3])


def main(argv):
    def opt(name, default):
        nonlocal argv
        if name in argv:
            i = argv.index(name); v = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
            return v
        return default
    cap, n_surf = opt("--max", 0), opt("--surf", 6)
    maps = argv or DEFAULT_MAPS
    p, rng = Project(), random.Random(2026)
    total = bad = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        e.give_mon("WAILMER", 30)           # a Surf user, as a player would have
        e.teach_move("SURF")
        e.set_flag(flag_id("FLAG_BADGE05_GET"))
        for name in maps:
            cases = cases_for(p, name)
            fails, shots = [], 0
            for kind in ("bump", "land", "rock"):
                todo = cases[kind]
                if cap and len(todo) > cap:
                    todo = rng.sample(todo, cap)
                ok = 0
                for x, y, d, exp, model in todo:
                    pos = e.warp(name, x, y)
                    if pos[2:] != (x, y):
                        fails.append(f"{kind} ({x},{y}): warp landed at {pos[2:]}")
                        continue
                    if kind != "bump" and not e.surfing():
                        fails.append(f"{kind} ({x},{y}): arrived on water but not surfing")
                        continue
                    got = press_toward(e, d, x, y)
                    good = got == exp
                    if good and kind == "land" and model == "surf_off" and e.surfing():
                        good, got = False, f"{got} still surfing"
                    if good and kind == "land" and model == "surf_off" and shots < 4:
                        e.shot(os.path.join(OUT, f"shores_{name}_landing{shots}.png"))
                        shots += 1
                    ok += good
                    if not good:
                        fails.append(f"{kind} ({x},{y}) {d}: model {model}->{exp}, game ->{got}")
                total += len(todo); bad += len(todo) - ok
                print(f"{name}: {kind:4} {ok}/{len(todo)} as the model says")
            # real play: surf off the shore through the field-move prompt
            edges = [(x, y, d) for x, y, d, _, _ in cases["bump"]
                     if p.load_map(name).layout.mid(x + DELTA[d][0], y + DELTA[d][1]) not in shores.ROCK_PIECES]
            ok = 0
            sample = rng.sample(edges, min(n_surf, len(edges)))
            for i, (x, y, d) in enumerate(sample):
                e.warp(name, x, y)
                press_toward(e, d, x, y)              # face the water (a bump if already facing)
                wx, wy = x + DELTA[d][0], y + DELTA[d][1]
                started = e.start_surf()
                pos = e.player()[2:]
                good = started and pos == (wx, wy)
                if good and i == 0:
                    e.shot(os.path.join(OUT, f"shores_{name}_surf.png"))
                if not good:
                    fails.append(f"surf ({x},{y}) {d}: expected surfing at {(wx, wy)}, "
                                 f"got {pos} surfing={e.surfing()}")
                    for _ in range(10):
                        e.press("B", 3, 10)
                ok += good
            total += len(sample); bad += len(sample) - ok
            print(f"{name}: surf {ok}/{len(sample)} surfed off the shore through the Surf prompt")
            for f in fails[:10]:
                print("    " + f)
    print(f"\nTOTAL: {total - bad}/{total} shore cases behave as the model says")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
