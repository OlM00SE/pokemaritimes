"""Landscape design helpers for sketch design scripts: natural forest edges, groves, clearings,
meadows, and accents (flowers, boulders, saplings).

The designer composes: where the groves, clearings, meadows and boulders go, and what the
player should see. These helpers draw the small-scale shapes the way vanilla does (the numbers
are in design/mapping_reference.md section 11):

  * Forest is planted as whole 2x2 trees on the map's tree grid. Where a wavy edge doesn't line
    up with the grid, a fringe tree is offset by one tile. Vanilla offsets about 10% of tree
    joins, almost all on edges, so the interior stays an aligned canopy and the outline steps
    diagonally instead of in ruler-straight runs. A sliver too thin for a tree can take a sapling.
  * Forest edges follow a stepped profile: flat for 2-5 tiles, then a step of a tree, often
    continuing in the same direction (diagonal staircases), so edges read as bays, promontories
    and rounded corners rather than long straight runs or single-tile jitter. Blobs (groves,
    clearings, meadows) wobble in a few smooth lobes.
  * Tall grass is drawn as blobs with a few stray tufts just outside (Route 116's feathered edge).
  * Accents are sparse and purposeful. Vanilla's flowers are mostly singles or small beds of
    3-9 in sunny spots. A third of its boulders stand right against a tree, the rest in the open.

Every helper takes `keep_clear`: cells it must not touch (the trail, ledge landings, the seams
with neighbouring maps). Masks are plain sets of (x, y) cells; combine them with | & -.
Everything is deterministic: the same seed draws the same map.
"""
import math, random

FOREST_OK = set(".T,y")          # cells planting may overwrite (grass, forest, tall grass, saplings)


# ---------------------------------------------------------------- shapes (sets of cells) ----
def rect(x0, y0, x1, y1):
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def blob(cx, cy, rx, ry, seed, wobble=0.2, lobes=3):
    """A rounded patch around (cx, cy) with radii rx, ry, whose outline wobbles by up to
    `wobble` of the radius in a few smooth lobes (no spikes)."""
    rng = random.Random(seed)
    harm = [(k, rng.uniform(0.5, 1.0), rng.uniform(0, 2 * math.pi)) for k in range(2, 2 + lobes)]
    norm = sum(a for _, a, _ in harm)
    out = set()
    for y in range(int(cy - ry * 1.5) - 1, int(cy + ry * 1.5) + 2):
        for x in range(int(cx - rx * 1.5) - 1, int(cx + rx * 1.5) + 2):
            dx, dy = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            th = math.atan2(dy, dx)
            r = 1 + wobble * sum(a * math.cos(k * th + ph) for k, a, ph in harm) / norm
            if dx * dx + dy * dy <= r * r:
                out.add((x, y))
    return out


def edge_profile(n, levels, seed, run=(2, 5), momentum=0.5):
    """n integer levels in [0, levels] for a forest edge: flat for a short run (2-5 tiles), then
    a step of one level (sometimes two). With probability `momentum` a step continues the last
    direction, so the edge forms diagonal staircases as well as bays and promontories. Vanilla's
    edges change every one to three trees; long flat runs are what read as rectangular."""
    rng = random.Random(seed)
    lv, d, out = rng.randint(0, levels), rng.choice((-1, 1)), []
    while len(out) < n:
        out += [lv] * rng.randint(*run)
        if rng.random() > momentum:
            d = rng.choice((-1, 1))
        step = d * (2 if rng.random() < 0.15 else 1)
        if not 0 <= lv + step <= levels:
            d, step = -d, -step
        lv = max(0, min(levels, lv + step))
    return out[:n]


def forest_edge(x0, y0, x1, y1, open_side, amp, seed, run=(2, 5)):
    """Forest filling the rectangle, except that its edge facing `open_side` ('N', 'S', 'W' or
    'E') recedes by 0..amp tiles along a stepped profile (edge_profile). A north or south edge
    steps in whole trees (2 rows), since tree bands are 2 rows; a west or east edge steps a tile
    at a time. Combine calls with | for forest on several sides."""
    if open_side in "NS":
        d = [2 * v for v in edge_profile(x1 - x0 + 1, amp // 2, seed, run)]
        return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
                if (y >= y0 + d[x - x0] if open_side == "N" else y <= y1 - d[x - x0])}
    d = edge_profile(y1 - y0 + 1, amp, seed, run)
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
            if (x >= x0 + d[y - y0] if open_side == "W" else x <= x1 - d[y - y0])}


def around(cells, r=1):
    """Cells within Chebyshev distance r of `cells` (including them)."""
    return {(x + dx, y + dy) for x, y in cells for dx in range(-r, r + 1) for dy in range(-r, r + 1)}


def cells_of(sk, chars, area=None):
    """Cells of the sketch holding any of `chars` (optionally within an area set)."""
    return {(x, y) for y in range(sk.h) for x in range(sk.w)
            if sk.rows[y][x] in chars and (area is None or (x, y) in area)}


def ledge_clearance(sk, area=None):
    """Ledge cells plus the tiles you stand on before jumping and land on after: never plant there."""
    out = set()
    dirs = {"v": (0, 1), "<": (-1, 0), ">": (1, 0)}
    for (x, y) in cells_of(sk, "v<>", area):
        dx, dy = dirs[sk.rows[y][x]]
        out |= {(x, y), (x + dx, y + dy), (x + 2 * dx, y + 2 * dy), (x - dx, y - dy)}
    return out


# ------------------------------------------------------------------------------ terraces ----
def terrace(sk, area, level, face=1):
    """Raise `area` (a set of cells) to terrace `level`, walled with cliffs (mapkit/cliffs.py).
    The area's cells take the level; its edge cells beside lower ground (any of the 8
    neighbours) become wall '^': a rim on the north, flanks on the west and east, and on the
    south a face `face` rows tall (the rows above each foot cell, inside the area). Raise low
    terraces first: a higher one inside a lower one walls itself against it. Returns the wall
    cells. Draw roads, water and forest after: a wall replaces whatever the cell held."""
    inmap = lambda x, y: 0 <= x < sk.w and 0 <= y < sk.h
    area = {c for c in area if inmap(*c)}
    sk.set_level(area, level)
    lower = lambda x, y: inmap(x, y) and (x, y) not in area and sk.levels[y][x] < level
    walls = {(x, y) for x, y in area
             if any(lower(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    foot = {(x, y) for x, y in walls if lower(x, y + 1)}
    # a face rises above each foot cell; at an inside corner (lower ground only diagonally
    # below, beside a foot cell) the face's upper rows run on over the corner's column
    corner = {(x, y) for x, y in walls - foot if (lower(x - 1, y + 1) or lower(x + 1, y + 1))
              and ((x - 1, y) in foot or (x + 1, y) in foot)}
    for x, y in foot | corner:
        for k in range(1, face):
            if (x, y - k) in area:
                walls.add((x, y - k))
    for x, y in walls:
        sk.set(x, y, "^")
    return walls


def stairs(sk, x, y, width=2):
    """Stairs up a south face: the wall cells from (x, y) down through the face, in `width`
    (1 or 2) columns from x, become '%'. Give the top-left cell of the stairs (the face's top
    row). Returns the stair cells."""
    out = set()
    for cx in range(x, x + width):
        cy = y
        while 0 <= cy < sk.h and sk.get(cx, cy) == "^":
            out.add((cx, cy))
            cy += 1
    for c in out:
        sk.set(*c, "%")
    return out


def cutting(sk, cells, level, ch="="):
    """A road through a cliff: `cells` (the road's cells inside the wall) become `ch` at `level`
    (the lower terrace's, so the cut walls end in corners). Two road cells may differ in level
    (a graded road), so the road climbs through the cut; the walls stay on both sides."""
    for x, y in cells:
        sk.set(x, y, ch)
    sk.set_level(cells, level)


def cliff_clearance(sk, area=None):
    """Stairs and the tile above and below each: never plant there."""
    out = set()
    for x, y in cells_of(sk, "%", area):
        out |= {(x, y), (x, y - 1), (x, y + 1)}
    return out


# ------------------------------------------------------------------------------- forest ----
def plant(sk, mask, area, parity=(0, 0), saplings=True, keep_clear=frozenset()):
    """Replant the forest inside `area` (a set of cells) so that it covers `mask`.
    Trees are laid in bands of two rows on the tree grid's rows (y % 2 == parity[1]). In each
    band, the mask's cells on either row make runs (a one-tile gap between two runs is closed:
    it could never hold a tree, and would leave a notch). Each run is tiled with whole trees:
      * a run that ends against open ground starts flush with it, at any alignment: the fringe
        follows the edge to the tile, and neighbouring bands come out staggered (vanilla's
        offset edge trees). A tile an odd run leaves over goes to an open end (a nook), never
        to a closed one, where it would be an unreachable pocket;
      * a run enclosed by forest, a kept '#' block, the map edge or the area's edge stays on the grid
        (x % 2 == parity[0]), so a replanted canopy meets the trees around it seamlessly. An
        even run off the grid fits flush; an odd one must leave a tile against forest, which
        mapgen's reach check reports if it ends up cut off.
    It refuses (ValueError) to leave a tree or sapling cut in half by the area's edge.
    A tile a run can't fill becomes a sapling ('y': crown over trunk) where there's open ground
    below to stand on and no tree right above (if `saplings`), else grass.
    Mask cells in a band only one row deep stay grass: the outline steps in whole trees, as
    vanilla's do; it's the horizontal offsets that make it read as natural.
    Trees and saplings already in `area` but not replanted become grass. Only cells holding
    grass, forest, tall grass or saplings are planted, never `keep_clear`. Every tree is whole
    and inside the area, except where a run meets the map's right edge (the tree runs off the
    map, as vanilla's do), so the compiler tiles them back exactly.
    Returns (trees, offset_trees, saplings)."""
    px, py = parity
    inmap = lambda x, y: 0 <= x < sk.w and 0 <= y < sk.h
    can = lambda x, y: (inmap(x, y) and (x, y) in area and (x, y) not in keep_clear
                        and sk.rows[y][x] in FOREST_OK)
    band_in = lambda x, y: can(x, y) and can(x, y + 1) and ((x, y) in mask or (x, y + 1) in mask)

    def closed(x, y, kept=True):
        """Beyond a run's end: forest that stays (outside the area), the map edge, a cliff wall,
        and with `kept`, a kept '#' block (it may be solid: a cliff, a building). A leftover tile never
        goes against one. Gap filling passes kept=False: a kept block may also be walkable (a
        hand-painted path), and a one-tile walkway beside it must stay open."""
        if not inmap(x, y) or not inmap(x, y + 1):
            return True
        return any((kept and sk.rows[cy][cx] == "#") or sk.rows[cy][cx] == "^"
                   or ((cx, cy) not in area and sk.rows[cy][cx] in "Ty")
                   for cx, cy in ((x, y), (x, y + 1)))

    # close one-tile gaps (per band) between two runs, or between a run and the map edge or
    # forest that stays: such a gap could never hold a tree, and would leave a notch or a pocket
    filled = set()
    for (x, y) in mask:
        yb = y - (y - py) % 2
        if not band_in(x, yb):
            continue
        for g, beyond in ((x + 1, x + 2), (x - 1, x - 2)):
            if not band_in(g, yb) and can(g, yb) and can(g, yb + 1) and \
                    (band_in(beyond, yb) or closed(beyond, yb, kept=False)):
                filled.add((g, yb))
    ok = lambda x, y: band_in(x, y - (y - py) % 2) or (x, y - (y - py) % 2) in filled

    trees, offset, leftovers = [], 0, []
    ys = [y for _, y in mask]
    if not ys:
        return 0, 0, 0
    for y in range(min(ys) - (min(ys) - py) % 2, max(ys) + 1, 2):
        x = min(x for x, _ in mask) - 1
        xmax = max(x for x, _ in mask) + 1
        while x <= xmax:
            if not (ok(x, y) and ok(x, y + 1)):
                x += 1
                continue
            a = x
            while ok(x + 1, y) and ok(x + 1, y + 1):
                x += 1
            b = x
            x += 1
            lo, ro = not closed(a - 1, y), not closed(b + 1, y)
            # a tile left over by an odd run must fall at an open end (a nook in the edge),
            # never at a closed one, where it would be a pocket nobody can reach
            odd = (b - a + 1) % 2
            if lo and ro:
                start = a
            elif lo:            # closed on the right: flush with the open left end if the run is
                                # even or runs off the map's right edge, else flush right
                start = a if not odd or b == sk.w - 1 else a + 1
            elif ro:            # closed on the left: flush with it
                start = a
            else:               # enclosed: on the grid; an even run off the grid fits flush
                start = a if a % 2 == px or not odd else a + 1
            covered = set()
            tx = start
            while tx + 1 <= b or (tx == b and b == sk.w - 1 and lo):     # (runs off the right edge)
                trees.append((tx, y))
                offset += tx % 2 != px
                covered |= {tx, tx + 1}
                tx += 2
            leftovers += [(cx, y) for cx in range(a, b + 1) if cx not in covered]
    taken = {(qx, qy) for x, y in trees for qx, qy in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))}

    def stand(x, y):        # the tile below a trunk: open ground once the area is replanted
        if not inmap(x, y) or (x, y) in taken:
            return False
        ch = sk.rows[y][x]
        return ch in ".,=*:" or (ch in "Ty" and (x, y) in area and (x, y) not in keep_clear)

    saps = []
    for x, y in leftovers:
        # (a sapling here usually stands against its run's tree, which vanilla doesn't do: a design
        # script finishes with uncrowd_saplings, after every other placement)
        if saplings and (x, y) not in taken and (x, y + 1) not in taken and (x, y - 1) not in taken \
                and not (inmap(x, y - 1) and sk.rows[y - 1][x] in "Ty" and (x, y - 1) not in area) \
                and stand(x, y + 2):
            saps.append((x, y))
            taken |= {(x, y), (x, y + 1), (x, y + 2)}    # the sapling, and the open tile below it
    # write: clear the area's old forest, then plant
    before = _forest_damage(sk)
    for (x, y) in area:
        if inmap(x, y) and sk.rows[y][x] in "Ty" and (x, y) not in keep_clear:
            sk.rows[y][x] = "."
    for x, y in trees:
        for qx, qy in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)):
            if inmap(qx, qy):
                sk.rows[qy][qx] = "T"
    for x, y in saps:
        sk.rows[y][x] = sk.rows[y + 1][x] = "y"
    after = _forest_damage(sk)
    if after[0] > before[0] or after[1] - before[1]:
        raise ValueError(
            f"plant: the area's edge cuts through a tree or sapling that stays outside it "
            f"({after[0] - before[0]} tree cells left without a whole tree; broken saplings at "
            f"{sorted(after[1] - before[1])[:4]}). Make the area cover whole trees: whole 2-row "
            "bands on the forest's grid, and both tiles of every sapling.")
    return len(trees), offset, len(saps)


def narrow_paths(sk, ch="="):
    """Runs of path one tile wide: [(cells, side)], side the direction ('E' or 'S') across the run.
    The light path and sand families have no one-wide pieces: the compiler gives such a lane its rim
    on one side only and a ragged edge on the other (composition rule `pairs`: path | grass)."""
    is_p = lambda x, y: 0 <= x < sk.w and 0 <= y < sk.h and sk.rows[y][x] == ch
    out = []
    for vertical in (True, False):
        seen = set()
        for y in range(sk.h):
            for x in range(sk.w):
                if (x, y) in seen or not is_p(x, y):
                    continue
                if vertical:
                    narrow = lambda cx, cy: is_p(cx, cy) and not is_p(cx - 1, cy) and not is_p(cx + 1, cy)
                    step = (0, 1)
                else:
                    narrow = lambda cx, cy: is_p(cx, cy) and not is_p(cx, cy - 1) and not is_p(cx, cy + 1)
                    step = (1, 0)
                if not narrow(x, y):
                    continue
                run, cx, cy = [], x, y
                while narrow(cx, cy):
                    run.append((cx, cy))
                    cx, cy = cx + step[0], cy + step[1]
                seen.update(run)
                if len(run) >= 2:
                    out.append((run, "E" if vertical else "S"))
    return out


def widen_paths(sk, keep_clear=frozenset(), ch="="):
    """Widen every one-tile-wide run of path (narrow_paths) to two, on the side where every cell of
    the run has open grass ('.') beside it (east or south first, else west or north); a run with
    neither stays as it is. Only grass becomes path, so nothing turns solid: call it last in a design
    script and nothing else moves. Returns the cells added."""
    out = []
    for run, side in narrow_paths(sk, ch):
        d = (1, 0) if side == "E" else (0, 1)
        for sx, sy in (d, (-d[0], -d[1])):
            cells = [(x + sx, y + sy) for x, y in run]
            if all(0 <= x < sk.w and 0 <= y < sk.h and sk.rows[y][x] == "." and (x, y) not in keep_clear
                   for x, y in cells):
                for x, y in cells:
                    sk.rows[y][x] = ch
                out += cells
                break
    return out


def crowded_saplings(sk):
    """Saplings (runs of 'y') with a tree ('T') among the 8 neighbours of any of their cells.
    Vanilla doesn't stand a sapling against a tree: of 5817 sapling-piece cells in its General
    layouts, 15 touch a tree or its cap (5 sideways or below, 10 diagonally), all in Route 116's one
    grove tucked under a canopy (composition rule `pairs`: sapling | tree). Returns [[cells]]."""
    out, seen = [], set()
    for x in range(sk.w):
        for y in range(sk.h):
            if sk.rows[y][x] != "y" or (x, y) in seen:
                continue
            run = []
            while y < sk.h and sk.rows[y][x] == "y":
                run.append((x, y))
                y += 1
            seen.update(run)
            if any(0 <= cx + dx < sk.w and 0 <= cy + dy < sk.h and sk.rows[cy + dy][cx + dx] == "T"
                   for cx, cy in run for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                out.append(run)
    return out


def uncrowd_saplings(sk, keep_clear=frozenset(), hold=frozenset()):
    """Turn every sapling standing against a tree (crowded_saplings) into grass. Call it last in a
    design script, after every placement that reads the ground (beds, boulders, meadows), so that
    nothing else moves. A sapling may have closed a gap in the woods (its trunk is solid; the crown
    top is walk-behind): read the route numbers and mapgen's reach line after the build, and name
    such a sapling's cells in `hold`: its trunk becomes a boulder (as solid, and a boulder against a
    tree is a pairing vanilla draws often), the rest grass. Returns the cells changed."""
    out = []
    for run in crowded_saplings(sk):
        if any(c in keep_clear for c in run):
            continue
        boulder = run[-1] if any(c in hold for c in run) else None
        for x, y in run:
            sk.rows[y][x] = "b" if (x, y) == boulder else "."
            out.append((x, y))
    return out


def _forest_damage(sk):
    """(forest cells that can't form a whole tree, cells of invalid saplings) in the sketch."""
    from .sketch import CHAR_TO_CLASS, assign_tree_quarters
    from . import flora
    cls = [[CHAR_TO_CLASS[ch] for ch in row] for row in sk.rows]
    dropped = assign_tree_quarters(cls, sk.w, sk.h)
    _, errors = flora.resolve(cls, sk.w, sk.h)
    return dropped, {(x, y) for x, y, _ in errors}


def sapling_stand(sk, mask, seed=0, density=0.45, keep_clear=frozenset()):
    """A young grove (Route 116): saplings 2 or 3 tall scattered through the mask's open grass.
    Each column gets saplings at a seeded rhythm, so neighbours are staggered, not in rows.
    Every trunk keeps an open tile below it, saplings never touch end to end, and no solid part
    (trunk, crown middle) stands beside another's, so a stand never closes into a hedge. The
    stand is walkable between trunks (the crown tops are walk-behind tiles).
    Returns the number planted."""
    rng = random.Random(seed)
    ok = lambda x, y: (0 <= x < sk.w and 0 <= y < sk.h and (x, y) in mask and (x, y) not in keep_clear
                       and sk.rows[y][x] == ".")
    solid = set()                            # trunks and crown middles planted so far
    n = 0
    for x in sorted({x for x, _ in mask}):
        ys = sorted(y for xx, y in mask if xx == x)
        y = ys[0] + rng.randrange(3)
        while y <= ys[-1]:
            if rng.random() < density:
                hgt = 3 if rng.random() < 0.35 else 2
                col = [(x, y + i) for i in range(hgt)]
                below = (x, y + hgt)
                hard = col[1:]
                if all(ok(*c) for c in col) and 0 <= below[1] < sk.h and \
                        sk.rows[below[1]][below[0]] in ".,=*" and \
                        (y == 0 or sk.rows[y - 1][x] not in "Ty") and \
                        not any((cx + dx, cy) in solid for cx, cy in hard for dx in (-1, 1)):
                    for cx, cy in col:
                        sk.rows[cy][cx] = "y"
                    solid.update(hard)
                    n += 1
                    y += hgt + 1 + rng.randrange(2)
                    continue
            y += 1 + rng.randrange(2)
    return n


# ------------------------------------------------------------------------------ meadows ----
def meadow(sk, mask, seed=0, tufts=0, keep_clear=frozenset(), ch=","):
    """Tall grass over the mask's open grass, plus `tufts` stray single tufts one or two tiles
    outside it (spread apart, never touching each other). Returns the number of cells painted."""
    rng = random.Random(seed)
    painted = {(x, y) for (x, y) in mask if 0 <= x < sk.w and 0 <= y < sk.h
               and sk.rows[y][x] == "." and (x, y) not in keep_clear}
    for x, y in painted:
        sk.rows[y][x] = ch
    ring = sorted(c for c in around(painted, 2) - around(painted, 0)
                  if 0 <= c[0] < sk.w and 0 <= c[1] < sk.h and sk.rows[c[1]][c[0]] == "."
                  and c not in keep_clear)
    rng.shuffle(ring)
    placed = []
    for x, y in ring:
        if len(placed) >= tufts:
            break
        if all(max(abs(x - px), abs(y - py)) >= 3 for px, py in placed):
            sk.rows[y][x] = ch
            placed.append((x, y))
    return len(painted) + len(placed)


# ------------------------------------------------------------------------------ accents ----
def _sunny(sk, x, y, keep_clear):
    """Open grass where an accent can stand on plain grass: not on the row just above a tree
    (its canopy overhangs there), not under water's bank, not in keep_clear."""
    if not (0 <= x < sk.w and 0 <= y < sk.h) or sk.rows[y][x] != "." or (x, y) in keep_clear:
        return False
    below = sk.rows[y + 1][x] if y + 1 < sk.h else "."
    above = sk.rows[y - 1][x] if y > 0 else "."
    return below != "T" and above not in "~o"


def flower_bed(sk, cx, cy, n, seed=0, keep_clear=frozenset()):
    """A compact bed of up to n flowers grown from (cx, cy) over open grass. Returns the cells."""
    rng = random.Random(seed)
    if not _sunny(sk, cx, cy, keep_clear):
        return []
    bed = [(cx, cy)]
    while len(bed) < n:
        front = {}
        for x, y in bed:
            for c in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if c not in bed and _sunny(sk, *c, keep_clear):
                    # prefer cells that touch more of the bed: compact, rounded beds
                    front[c] = sum((c[0] + dx, c[1] + dy) in bed for dx, dy in
                                   ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if not front:
            break
        best = max(front.values())
        pick = sorted(c for c, v in front.items() if v == best)
        bed.append(pick[rng.randrange(len(pick))])
    for x, y in bed:
        sk.rows[y][x] = "*"
    return bed


def sprinkle(sk, cx, cy, n, seed=0, keep_clear=frozenset(), radius=2):
    """Up to n single flowers scattered within `radius` tiles of (cx, cy), none touching another
    side by side: a route's flowers as vanilla draws them (singles in 90-100% of its route beds;
    composition rule flower_singles). A compact bed (flower_bed) is a garden's, in a town.
    Returns the cells."""
    rng = random.Random(seed)
    spots = [(x, y) for y in range(cy - radius, cy + radius + 1) for x in range(cx - radius, cx + radius + 1)
             if _sunny(sk, x, y, keep_clear)]
    rng.shuffle(spots)
    spots.sort(key=lambda c: max(abs(c[0] - cx), abs(c[1] - cy)) + rng.random())   # near the spot first
    out = []
    for x, y in spots:
        if len(out) >= n:
            break
        if any(0 <= x + dx < sk.w and 0 <= y + dy < sk.h and sk.rows[y + dy][x + dx] == "*"
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            continue
        sk.rows[y][x] = "*"
        out.append((x, y))
    return out


def loosen_flowers(sk, area=None):
    """Thin every bed of two or more flowers to singles that don't touch side by side (a route's
    flowers, as vanilla's are: composition rule flower_singles). Each bed keeps the cells of one
    checkerboard colour (the colour holding more of it; the bed's first cell's on a tie), so a pair
    keeps one flower, a row of three keeps both ends. Only flower cells change (to grass): call it
    last in a design script and nothing else moves. Returns the cells cleared."""
    beds, seen = [], set()
    for y in range(sk.h):
        for x in range(sk.w):
            if sk.rows[y][x] != "*" or (x, y) in seen or (area is not None and (x, y) not in area):
                continue
            bed, stack = [], [(x, y)]
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                bed.append((cx, cy))
                for c in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if c not in seen and 0 <= c[0] < sk.w and 0 <= c[1] < sk.h and sk.rows[c[1]][c[0]] == "*":
                        seen.add(c)
                        stack.append(c)
            beds.append(sorted(bed, key=lambda c: (c[1], c[0])))
    out = []
    for bed in beds:
        if len(bed) < 2:
            continue
        first = (bed[0][0] + bed[0][1]) % 2
        n_first = sum((x + y) % 2 == first for x, y in bed)
        keep = first if n_first * 2 >= len(bed) else 1 - first
        for x, y in bed:
            if (x + y) % 2 != keep:
                sk.rows[y][x] = "."
                out.append((x, y))
    return out


def nestle(sk, area, n, seed=0, ch="b", min_gap=5, keep_clear=frozenset()):
    """Up to n accents (boulders by default) tucked against the forest edge inside `area`:
    open grass with a tree beside it, preferring inner corners (trees on two sides), spread at
    least min_gap apart. Returns the cells."""
    rng = random.Random(seed)
    spots = []
    for (x, y) in sorted(area):
        if not _sunny(sk, x, y, keep_clear):
            continue
        sides = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, -1))
                 if 0 <= x + dx < sk.w and 0 <= y + dy < sk.h and sk.rows[y + dy][x + dx] == "T"]
        # never block a gap: the opposite side of each tree it leans on must stay open
        if sides and all(_open(sk, x - dx, y - dy) for dx, dy in sides):
            # inner corners first, but not strictly: a strict order lines boulders up along
            # one edge row
            spots.append((1.5 * rng.random() - len(sides), x, y))
    chosen = []
    for _, x, y in sorted(spots):
        if len(chosen) >= n:
            break
        if all(max(abs(x - a), abs(y - b)) >= min_gap for a, b in chosen):
            chosen.append((x, y))
            sk.rows[y][x] = ch
    return chosen


def _open(sk, x, y):
    return 0 <= x < sk.w and 0 <= y < sk.h and sk.rows[y][x] in ".,=*:"


# ------------------------------------------------------------------------------ metrics ----
def metrics(layout, area=None):
    """How "designed" a map's open ground and forest edges look, from its blocks:
      straight_edge: the longest straight run of tree tiles facing open ground along one side
                     (Tom's "rectangular forest groupings");
      open_square:   the side of the largest square of nothing but plain grass (001), i.e. no
                     tall grass, flowers, trees, paths or edges ("large uniform grassy areas").
    area: optional (x0, y0, x1, y1) to measure only part of the map."""
    from .terrain import TREE
    trees = set().union(*TREE.values())
    w, h = layout.width, layout.height
    x0, y0, x1, y1 = area or (0, 0, w - 1, h - 1)
    tree = lambda x, y: layout.mid(x, y) in trees
    opn = lambda x, y: 0 <= x < w and 0 <= y < h and layout.coll(x, y) == 0 and not tree(x, y)
    best, best_at = 0, None
    for side, (dx, dy) in (("N", (0, -1)), ("S", (0, 1)), ("W", (-1, 0)), ("E", (1, 0))):
        if dy:          # horizontal runs
            for y in range(y0, y1 + 1):
                run = 0
                for x in range(x0, x1 + 1):
                    run = run + 1 if tree(x, y) and opn(x, y + dy) else 0
                    if run > best:
                        best, best_at = run, (x - run + 1, y, x, y)
        else:
            for x in range(x0, x1 + 1):
                run = 0
                for y in range(y0, y1 + 1):
                    run = run + 1 if tree(x, y) and opn(x + dx, y) else 0
                    if run > best:
                        best, best_at = run, (x, y - run + 1, x, y)
    sq, size, size_at = {}, 0, None
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if layout.mid(x, y) == 0x001:
                s = 1 + min(sq.get((x - 1, y), 0), sq.get((x, y - 1), 0), sq.get((x - 1, y - 1), 0))
                sq[(x, y)] = s
                if s > size:
                    size, size_at = s, (x - s + 1, y - s + 1, x, y)
    # *_at: (x0, y0, x1, y1) of the longest edge / largest square, to find it on the map
    return {"straight_edge": best, "open_square": size, "straight_edge_at": best_at,
            "open_square_at": size_at}
