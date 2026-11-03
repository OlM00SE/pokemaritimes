"""In-game flora test: flowers, boulders, saplings and forest edges behave in mGBA as the model says.

For each map (default: GroveLab and Route 203), from every walkable tile next to:
  piece   a flora piece (flowers, a boulder, any tile of a sapling): press toward it. Flowers and
          a sapling's crown top are walked onto (you pass behind the crown); boulders, trunks and
          crown middles block;
  edge    a tree tile on the forest's edge (a sample, --edges N, default 60 per map, offset trees
          first): press toward it; the player must not move.
The expected result comes from mapkit.engine (World.step), so the test also checks the engine
model on the new tiles. Screenshots: dev/out/flora_<Map>_crown.png (the player behind a crown) and
dev/out/flora_<Map>_<n>.png (views of the planted areas).

  python dev/tests/ingame_flora.py [--edges N] [Map ...]
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.engine import World, DIR_NAME
from mapkit.terrain import TREE
from mapkit import flora

DEFAULT_MAPS = ["GroveLab", "Route203_1"]
VIEWS = {"GroveLab": [(10, 16), (25, 12), (32, 6)], "Route203_1": [(18, 25), (34, 28), (8, 20)]}
OUT = os.path.join(REPO, "dev", "out")
DELTA = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
TREES = set().union(*TREE.values())


def cases_for(p, name, n_edges, rng):
    m = p.load_map(name)
    w = World(p, m)
    L = m.layout
    objs = [(o["x"], o["y"]) for o in m.events("object_events")]
    warps = {(wv["x"], wv["y"]) for wv in m.events("warp_events")}
    near = lambda x, y: (x, y) in warps or any(abs(x - ox) + abs(y - oy) <= 2 for ox, oy in objs)
    inb = lambda x, y: 0 <= x < L.width and 0 <= y < L.height
    walk = lambda x, y: inb(x, y) and L.coll(x, y) == 0 and not \
        w.flags(*w.to_grid(x, y)) & TILE_FLAG_SURFABLE and L.mid(x, y) not in TREES
    pieces, edges = [], []
    for y in range(L.height):
        for x in range(L.width):
            if not walk(x, y) or near(x, y):
                continue
            for d, (dx, dy) in DELTA.items():
                nx, ny = x + dx, y + dy
                if not inb(nx, ny) or near(nx, ny):
                    continue
                ns, kind = w.step(w.arrival_state(*w.to_grid(x, y)), d)
                exp = (x, y) if ns is None else w.to_map(ns[0], ns[1])
                case = (x, y, d, exp, kind, L.mid(nx, ny))
                if L.mid(nx, ny) in flora.PIECES:
                    pieces.append(case)
                elif L.mid(nx, ny) in TREES:
                    # offset trees first: a tree top-left on the off-grid column or row
                    tl_x = nx - (L.mid(nx, ny) in TREE["TR"] | TREE["BR"])
                    tl_y = ny - (L.mid(nx, ny) in TREE["BL"] | TREE["BR"])
                    edges.append((tl_x % 2 == 1 or tl_y % 2 == 1, case))
    rng.shuffle(edges)
    edges.sort(key=lambda t: not t[0])
    return pieces, [c for _, c in edges[:n_edges]]


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
    n_edges = 60
    if "--edges" in argv:
        i = argv.index("--edges"); n_edges = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    maps = argv or DEFAULT_MAPS
    p, rng = Project(), random.Random(2027)
    total = bad = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        for name in maps:
            pieces, edges = cases_for(p, name, n_edges, rng)
            fails, crown_shot = [], False
            for label, todo in (("piece", pieces), ("edge", edges)):
                ok = 0
                for x, y, d, exp, model, mid in todo:
                    pos = e.warp(name, x, y)
                    if pos[2:] != (x, y):
                        fails.append(f"{label} ({x},{y}): warp landed at {pos[2:]}")
                        continue
                    got = press_toward(e, d, x, y)
                    good = got == exp
                    ok += good
                    if good and mid == flora.CROWN and got != (x, y) and not crown_shot:
                        e.shot(os.path.join(OUT, f"flora_{name}_crown.png"))
                        crown_shot = True
                    if not good:
                        fails.append(f"{label} ({x},{y}) {d} into {mid:03X}: model {model}->{exp}, game ->{got}")
                total += len(todo); bad += len(todo) - ok
                print(f"{name}: {label:5} {ok}/{len(todo)} as the model says")
            L = p.load_map(name).layout
            for i, (vx, vy) in enumerate(VIEWS.get(name, [])):
                # the dev warp ignores collision: stand on the nearest walkable tile instead
                x, y = min(((x, y) for y in range(L.height) for x in range(L.width) if L.coll(x, y) == 0),
                           key=lambda c: abs(c[0] - vx) + abs(c[1] - vy))
                e.warp(name, x, y)
                e.wait(30)
                e.shot(os.path.join(OUT, f"flora_{name}_{i}.png"))
            for f in fails[:10]:
                print("    " + f)
    print(f"\nTOTAL: {total - bad}/{total} flora and forest-edge cases behave as the model says")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
