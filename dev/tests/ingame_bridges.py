"""In-game bridge test: plank decks (mapkit/bridges.py) behave in mGBA as the engine model says.

For each map (default: every map whose blocks hold a bridge piece; today Woodstock):
  foot    from every walkable tile on or beside a deck: press in each direction. The deck is
          walked along and stepped off at its ends; from the deck, the water on either side
          refuses a walker;
  surf    from every water tile beside a deck (warping onto water starts Surf): press toward
          the deck. The deck is at elevation 3 and the water at 1, so a surfer can't climb onto
          it or pass under it (Route 104's deck does the same);
  cross   walk the whole crossing, from the grass north of the deck to the grass south of it
          and back, on foot.
The expected result of every press comes from mapkit.engine (World.step). Screenshots:
dev/out/bridge_<Map>_<n>.png (on the deck: the player's reflection shows in the planks).

  python dev/tests/ingame_bridges.py [Map ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.engine import World, DIR_NAME
from mapkit import bridges

OUT = os.path.join(REPO, "dev", "out")
DELTA = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}


def deck_cells(p, m):
    ids, _ = bridges.piece_ids(p, m.layout)
    if not ids:
        return set()
    want = set(ids.values())
    L = m.layout
    return {(x, y) for y in range(L.height) for x in range(L.width) if L.mid(x, y) in want}


def bridge_maps(p):
    """Maps whose design sketch (design/maps/*.txt) draws a bridge."""
    from mapkit.sketch import Sketch
    out, folder = [], p.path("design", "maps")
    for f in sorted(os.listdir(folder)):
        if f.endswith(".txt"):
            sk = Sketch.load(os.path.join(folder, f))
            if sk.map_name in p.map_names and any(bridges.CHAR in row for row in sk.rows):
                out.append(sk.map_name)
    return out


def cases_for(p, name):
    m = p.load_map(name)
    w = World(p, m)
    L = m.layout
    deck = deck_cells(p, m)
    objs = {(o["x"], o["y"]) for o in m.events("object_events")}
    inb = lambda x, y: 0 <= x < L.width and 0 <= y < L.height
    wet = lambda x, y: inb(x, y) and bool(w.flags(*w.to_grid(x, y)) & TILE_FLAG_SURFABLE)
    foot, surf = [], []
    near = {(x + dx, y + dy) for x, y in deck for dx, dy in list(DELTA.values()) + [(0, 0)]}
    for x, y in sorted(near):
        if not inb(x, y) or (x, y) in objs:
            continue
        for d, (dx, dy) in DELTA.items():
            nx, ny = x + dx, y + dy
            if not inb(nx, ny) or (nx, ny) in objs:
                continue
            if (x, y) not in deck and (nx, ny) not in deck:
                continue                       # only presses onto, along or off a deck
            ns, kind = w.step(w.arrival_state(*w.to_grid(x, y)), d)
            # "surf_on" is the model saying Surf (a field move) could start here; a press alone
            # leaves a walker where it stands, as on any shore (tests/ingame_shores.py)
            exp = (x, y) if ns is None or kind == "surf_on" else w.to_map(ns[0], ns[1])
            case = (x, y, d, exp, kind)
            if wet(x, y):
                surf.append(case)
            elif L.coll(x, y) == 0:
                foot.append(case)
    return deck, foot, surf


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
    p = Project()
    maps = argv or bridge_maps(p)
    if not maps:
        print("FAIL: no map has a bridge (NOT TESTED)")
        return 1
    total = bad = uncovered = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # no wild battles, no trainer sight
        for name in maps:
            deck, foot, surf = cases_for(p, name)
            if not deck or not foot:
                uncovered += 1
                print(f"{name}: FAIL, no bridge deck to test (NOT TESTED)")
                continue
            fails = []
            for label, todo in (("foot", foot), ("surf", surf)):
                ok = 0
                for x, y, d, exp, model in todo:
                    pos = e.warp(name, x, y)
                    if pos[2:] != (x, y):
                        fails.append(f"{label} ({x},{y}): warp landed at {pos[2:]}")
                        continue
                    got = press_toward(e, d, x, y)
                    good = got == exp
                    ok += good
                    if not good:
                        fails.append(f"{label} ({x},{y}) {d}: model {model}->{exp}, game ->{got}")
                total += len(todo); bad += len(todo) - ok
                print(f"{name}: {label:5} {ok}/{len(todo)} presses as the model says"
                      + (" (NOT APPLICABLE: no cases)" if not todo else ""))
            # the whole crossing, each column, there and back
            xs = sorted({x for x, _ in deck})
            top, bottom = min(y for _, y in deck), max(y for _, y in deck)
            for x in xs:
                for start, end, d in ((top - 1, bottom + 1, "S"), (bottom + 1, top - 1, "N")):
                    total += 1
                    e.warp(name, x, start)
                    for i in range(abs(end - start)):
                        press_toward(e, d, x, start + (i if d == "S" else -i))
                        if d == "S" and i == 2 and x == xs[0]:
                            e.shot(os.path.join(OUT, f"bridge_{name}_0.png"))
                    got = e.player()[2:]
                    if got != (x, end):
                        bad += 1
                        fails.append(f"cross column {x} {d}: ended at {got}, want {(x, end)}")
                    else:
                        print(f"{name}: cross column {x} {'south' if d == 'S' else 'north'}: ({x},{start}) -> ({x},{end}) ok")
            e.warp(name, xs[0], bottom + 4)
            e.wait(30)
            e.shot(os.path.join(OUT, f"bridge_{name}_1.png"))
            for f in fails[:10]:
                print("    " + f)
    print(f"\nTOTAL: {total - bad}/{total} bridge cases behave as the model says"
          + (f"; {uncovered} maps not tested" if uncovered else ""))
    return 1 if bad or uncovered else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
