"""In-game cliff test: every cliff wall, stair and road cutting behaves in mGBA as the engine model says.

For each map (default: CliffLab and Route 202), from the map's blocks (cliff pieces: mapkit/cliffs.py):
  bump    on every walkable tile beside a wall piece, press toward the wall: the player must not move
          (walls are solid from every side: faces, rims, flanks, corners), and the model must say
          so too.
  climb   every stair column: from the tile below its foot, walk north the stairs' height + 1 steps
          and arrive on the tile above its top; then walk back south to the start.
  cut     every graded road through a wall (a road tile beside a wall tile on both sides, west and
          east or north and south): walk through the cut and back.
Every expectation comes from mapkit.engine (World.step), so the test checks the model's account of
the pieces' collision and elevation against the game. Screenshots: dev/out/cliffs_<Map>_*.png.

  python dev/tests/ingame_cliffs.py [--max N] [Map ...]
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit.engine import World, DIR_NAME
from mapkit import cliffs

DEFAULT_MAPS = ["CliffLab", "Route202_1"]
OUT = os.path.join(REPO, "dev", "out")
DELTA = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
OPP = {"N": "S", "S": "N", "W": "E", "E": "W"}


def walk_model(w, x, y, dirs):
    """The model's tile after pressing `dirs` from (x, y), one step each (None: a step blocked)."""
    s = w.arrival_state(*w.to_grid(x, y))
    for d in dirs:
        ns, _ = w.step(s, d)
        if ns is not None:
            s = ns
    return w.to_map(s[0], s[1])


def cases_for(p, name):
    m = p.load_map(name)
    w = World(p, m)
    L = m.layout
    objs = [(o["x"], o["y"]) for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near = lambda x, y: any(abs(x - ox) + abs(y - oy) <= 2 for ox, oy in objs)
    inb = lambda x, y: 0 <= x < L.width and 0 <= y < L.height
    wall = lambda x, y: inb(x, y) and L.mid(x, y) in cliffs.WALL_PIECES
    stair = lambda x, y: inb(x, y) and L.mid(x, y) in cliffs.STAIR_PIECES
    open_ = lambda x, y: inb(x, y) and L.coll(x, y) == 0 and (x, y) not in warps and not near(x, y)
    out = {"bump": [], "climb": [], "cut": []}
    for y in range(L.height):
        for x in range(L.width):
            if open_(x, y) and not stair(x, y):
                for d, (dx, dy) in DELTA.items():
                    if wall(x + dx, y + dy):
                        out["bump"].append((x, y, [d], walk_model(w, x, y, [d])))
            if stair(x, y) and not stair(x, y - 1):           # the top of a stair column
                y1 = y
                while stair(x, y1 + 1):
                    y1 += 1
                n = y1 - y + 2
                if open_(x, y1 + 1) and open_(x, y - 1):
                    out["climb"].append((x, y1 + 1, ["N"] * n, walk_model(w, x, y1 + 1, ["N"] * n)))
                    out["climb"].append((x, y - 1, ["S"] * n, walk_model(w, x, y - 1, ["S"] * n)))
            # a cutting: a way through a wall, at most 3 tiles wide, walled on both sides across
            # it (taken from its first tile on the `a` side); walk through it and back
            if open_(x, y) and not stair(x, y):
                for a, b, run in (("W", "E", "S"), ("N", "S", "E")):
                    (ax, ay), (bx, by) = DELTA[a], DELTA[b]
                    if not wall(x + ax, y + ay):
                        continue
                    k = 1
                    while k <= 3 and open_(x + k * bx, y + k * by):
                        k += 1
                    if k > 3 or not wall(x + k * bx, y + k * by):
                        continue
                    dx, dy = DELTA[run]
                    sx, sy = x - 2 * dx, y - 2 * dy
                    ex, ey = x + 2 * dx, y + 2 * dy
                    # only ways the model says go through (a passage between walls that ends
                    # against a flank is a bump, covered above)
                    if open_(sx, sy) and open_(ex, ey) and walk_model(w, sx, sy, [run] * 4) == (ex, ey):
                        out["cut"].append((sx, sy, [run] * 4, (ex, ey)))
                        out["cut"].append((ex, ey, [OPP[run]] * 4, walk_model(w, ex, ey, [OPP[run]] * 4)))
    return out


def walk(e, x, y, dirs):
    """Press each direction until the player moves or it's clearly refused; returns the tile."""
    for d in dirs:
        loc = e.player()
        before = (loc[2], loc[3])
        e.press(DIR_NAME[d], 3, 40)
        loc = e.player()
        if (loc[2], loc[3]) == before:           # the tap only turned the player
            e.press(DIR_NAME[d], 3, 50)
            loc = e.player()
        e.wait(10)
    loc = e.player()
    return (loc[2], loc[3])


def main(argv):
    cap = 0
    if "--max" in argv:
        i = argv.index("--max")
        cap = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    maps = argv or DEFAULT_MAPS
    p, rng = Project(), random.Random(2017)
    total = bad = uncovered = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        for name in maps:
            cases = cases_for(p, name)
            fails, shots = [], 0
            for kind in ("bump", "climb", "cut"):
                todo = cases[kind]
                if cap and len(todo) > cap:
                    todo = rng.sample(todo, cap)
                ok = 0
                for x, y, dirs, exp in todo:
                    pos = e.warp(name, x, y)
                    if pos[2:] != (x, y):
                        fails.append(f"{kind} ({x},{y}): warp landed at {pos[2:]}")
                        continue
                    got = walk(e, x, y, dirs)
                    good = got == exp
                    if kind == "bump" and (exp != (x, y) or got != (x, y)):
                        # a wall blocks: the model and the game must both keep the player in place
                        # (a wall piece made walkable would otherwise pass as model == game)
                        good, got = False, f"{got} (a wall must block; the model says {exp})"
                    if kind != "bump" and good and got == (x, y):
                        good, got = False, f"{got} (never moved: the model and the game agree the way is shut)"
                    if good and kind != "bump" and shots < 3:
                        e.shot(os.path.join(OUT, f"cliffs_{name}_{kind}{shots}.png"))
                        shots += 1
                    ok += good
                    if not good:
                        fails.append(f"{kind} ({x},{y}) {''.join(dirs)}: model ->{exp}, game ->{got}")
                total += len(todo)
                bad += len(todo) - ok
                print(f"{name}: {kind:5} {ok}/{len(todo)} as the model says"
                      + (" (NOT APPLICABLE: none on this map)" if not todo else ""))
            if not cases["bump"] or not cases["climb"]:
                uncovered += 1
                print(f"{name}: FAIL, no {'walls' if not cases['bump'] else 'stairs'} found (NOT TESTED)")
            for f in fails[:10]:
                print("    " + f)
    print(f"\nTOTAL: {total - bad}/{total} cliff cases behave as the model says"
          + (f"; {uncovered} coverage failures" if uncovered else ""))
    return 1 if bad or uncovered else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
