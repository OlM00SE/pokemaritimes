"""In-game edge water: the engine's padded map grid matches the model, cell for cell, in the margin.

For each map (default: every Maritimes outdoor map), warp onto it and read gBackupMapLayout from
RAM. Every margin cell (outside the map) must be what the model says (mapkit/engine.World for the
connection strips, mapkit/seams.margin_fill for edge water that runs on where there is no
connection, MAPGRID_UNDEFINED elsewhere: the border pattern). Then, from each walkable edge cell
next to a filled margin cell, press outward: the player must not move (filled cells carry the
border's collision). Screenshots: dev/out/edge_water_<Map>.png at the first filled stretch.

The test fails on a map whose model fills nothing when the defaults include no such map at all
(it would pass vacuously): at least one map must have filled cells.

  python dev/tests/ingame_edge_water.py [Map ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project, MAP_OFFSET, TILE_FLAG_SURFABLE
from mapkit.engine import World, DIR_NAME
from mapkit.seams import margin_fill, OUTDOOR
from check_maps import maritimes_maps

OUT = os.path.join(REPO, "dev", "out")
UNDEFINED = 0x03FF
OUTWARD = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}


def expected_margin(p, m):
    """{(gx, gy): block} for every margin cell of the padded grid, as the model says."""
    w = World(p, m)
    fill = margin_fill(p, m)
    out = {}
    for gy in range(w.H):
        for gx in range(w.W):
            if w.in_map(gx, gy):
                continue
            c = w.cell(gx, gy)
            x, y = w.to_map(gx, gy)
            out[(gx, gy)] = c[0] if c is not None else fill.get((x, y), UNDEFINED)
    return out, fill


def read_grid(e):
    base = e.sym["gBackupMapLayout"]
    width, height, ptr = e.read32(base), e.read32(base + 4), e.read32(base + 8)
    raw = b""
    n = width * height * 2
    for off in range(0, n, 2048):
        raw += e.readrange(ptr + off, min(2048, n - off))
    return width, height, [raw[i] | raw[i + 1] << 8 for i in range(0, n, 2)]


def stand_tile(L, near):
    """The walkable tile nearest `near` (the dev warp ignores collision)."""
    return min(((x, y) for y in range(L.height) for x in range(L.width) if L.coll(x, y) == 0),
               key=lambda c: abs(c[0] - near[0]) + abs(c[1] - near[1]))


def main(argv):
    p = Project()
    maps = argv or [n for n in maritimes_maps(p) if p.load_map(n).j.get("map_type") in OUTDOOR]
    total_cells = bad_cells = filled_seen = bumps = bad_bumps = 0
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        e.test_mode()                       # movement only: no battles, gates open
        for name in maps:
            m = p.load_map(name)
            L = m.layout
            want, fill = expected_margin(p, m)
            x, y = stand_tile(L, (L.width // 2, L.height // 2))
            pos = e.warp(name, x, y)
            if pos[2:] != (x, y):
                print(f"{name}: FAIL, the warp landed at {pos[2:]}"); bad_cells += 1; continue
            W, H, grid = read_grid(e)
            if (W, H) != (L.width + 2 * MAP_OFFSET + 1, L.height + 2 * MAP_OFFSET):
                print(f"{name}: FAIL, the game's grid is {W}x{H}"); bad_cells += 1; continue
            wrong = [(c, b, grid[c[1] * W + c[0]]) for c, b in want.items() if grid[c[1] * W + c[0]] != b]
            filled = sum(1 for c, b in want.items() if (c[0] - MAP_OFFSET, c[1] - MAP_OFFSET) in fill)
            filled_seen += filled
            total_cells += len(want); bad_cells += len(wrong)
            print(f"{name}: margin {len(want) - len(wrong)}/{len(want)} cells as the model says "
                  f"({filled} filled by edge water)")
            for (gx, gy), b, got in wrong[:6]:
                print(f"    ({gx - MAP_OFFSET},{gy - MAP_OFFSET}): model {b:04X}, game {got:04X}")
            # bumps: walkable edge cells beside a filled margin cell
            cases = []
            for (fx, fy) in fill:
                for d, (dx, dy) in OUTWARD.items():
                    ex, ey = fx - dx, fy - dy          # the map cell the fill lies outward from
                    if L.inb(ex, ey) and L.coll(ex, ey) == 0 and not \
                            p.tile_flags.get(L.tiles.behavior(L.mid(ex, ey)), 0) & TILE_FLAG_SURFABLE:
                        cases.append((ex, ey, d))
            shot, mine, mine_bad = False, 0, 0
            for ex, ey, d in sorted(set(cases)):
                pos = e.warp(name, ex, ey)
                if pos[2:] != (ex, ey):
                    print(f"    bump ({ex},{ey}): the warp landed at {pos[2:]}")
                    bad_bumps += 1; bumps += 1
                    continue
                if not shot:
                    e.wait(30)
                    e.shot(os.path.join(OUT, f"edge_water_{name}.png"))
                    shot = True
                for _ in range(2):                    # turn, then try to step
                    e.press(DIR_NAME[d], 3, 40)
                e.wait(20)
                got = e.player()
                bumps += 1; mine += 1
                if tuple(got) != tuple(pos):          # (group, num, x, y): same map, same tile
                    bad_bumps += 1; mine_bad += 1
                    print(f"    bump ({ex},{ey}) {d}: moved to {got}")
            if cases:
                print(f"{name}: bumps into filled cells {mine - mine_bad}/{mine} stay put")
    print(f"\nTOTAL: margin {total_cells - bad_cells}/{total_cells} cells as the model says on {len(maps)} maps, "
          f"{filled_seen} filled by edge water; bumps {bumps - bad_bumps}/{bumps} stay put")
    if not filled_seen:
        print("FAIL: no map had edge water to test (NOT TESTED)")
    return 1 if bad_cells or bad_bumps or not filled_seen or not bumps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
