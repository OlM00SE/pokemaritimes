"""Seam checks (mapkit/seams.py) and the compiler's seam context, without an emulator.

Each check has a negative control: the same rule on a case built to break it.
  people      the view band across each kind of seam: in at its limit, out one tile further
  tileset     Route 203 sees Fredericton's Rustboro fence; same-tileset seams see nothing
  pairs       the corridor's seams are clean; a tree cut at Route 201's seam (as before the fix) is
              caught
  trees       a cut tree at a connected edge needs the neighbour's other half; an unconnected edge
              cuts freely
  border      past an edge with no neighbour: the border's pattern and edge water; woods tiled on
              its grid where they can be, a leftover still cut beside it (no grass strip)
  signature   across a seam the autotiler sees the neighbour, not OUT
  margin      edge water and its verges, and the border-pattern widening, on a made-up edge
  gate        corridor.py check turns a person back at HomeTown's old spot into an error

  python dev/tests/seam_checks.py
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project, MAP_OFFSET, TILE_FLAG_SURFABLE
from mapkit.corpus import Corpus
from mapkit import seams
from mapkit.sketch import _tile_trees
from mapkit.terrain import signature, OUT, NEIGH8

results = []


def check(ok, what):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}: {what}")


def with_person(m, x, y, rx=0, ry=0):
    m2 = copy.copy(m)
    m2.j = copy.deepcopy(m.j)
    m2.j["object_events"] = [{"graphics_id": "TEST", "x": x, "y": y,
                              "movement_range_x": rx, "movement_range_y": ry}]
    return m2


def main():
    p = Project()
    corpus = Corpus(p)
    home, r201, wood = (p.load_map(n) for n in ("HomeTown_0", "Route201_1", "Woodstock_2"))

    print("people (seams.SEEN_ACROSS)")
    W, H = home.layout.width, home.layout.height
    for direction, inside, outside in (
            ("right", (W - 1 - 6, 20), (W - 1 - 7, 20)),
            ("left", (6, 20), (7, 20)),
            ("up", (10, 5), (10, 6)),
            ("down", (10, H - 1 - 3), (10, H - 1 - 4))):
        hit = seams.people_in_view(with_person(home, *inside), direction, (0, 40))
        miss = seams.people_in_view(with_person(home, *outside), direction, (0, 40))
        check(hit and not miss, f"{direction}: seen at {inside}, not at {outside}")
    wander = seams.people_in_view(with_person(home, W - 1 - 8, 20, rx=2), "right", (0, 40))
    check(wander, "a wanderer whose range reaches the band counts")
    far = seams.people_in_view(with_person(home, W - 3, 2), "right", (20, 25))
    check(not far, "a person far along the edge from the shared part doesn't count")

    print("tileset")
    r203, fred = p.load_map("Route203_1"), p.load_map("Fredericton_0")
    bad = seams.wrong_tileset_cells(r203, fred, "left", -17)
    check(len(bad) > 0 and all(mid >= 0x200 and x >= fred.layout.width - 7 for x, y, mid in bad),
          f"Route 203 sees {len(bad)} Rustboro cells of Fredericton's strip, all secondary, all in the strip")
    check(not seams.wrong_tileset_cells(r201, wood, "right", -14), "Route 201 / Woodstock share tilesets: none")

    print("pairs")
    odd = seams.unvanilla_pairs(corpus, r201, wood, "right", -14)
    check(not odd, f"Route 201 -> Woodstock: {len(odd)} pairs vanilla never draws")
    broken = copy.copy(r201)
    broken.layout = copy.copy(r201.layout)
    broken.layout.blocks = list(r201.layout.blocks)
    L = broken.layout
    for y in range(2, 10):          # the seam before the fix: a left half against Woodstock's left half
        L.set(L.width - 1, y, mid=0x1D4 if y % 2 == 0 else 0x1DC)
    caught = seams.unvanilla_pairs(corpus, broken, wood, "right", -14)
    check(len(caught) >= 8, f"a cut tree at the seam is caught ({len(caught)} pairs)")

    print("trees (sketch._tile_trees)")
    def tile(outside):
        g = [["T", "T", "T"], ["T", "T", "T"]]    # 3 wide: the last column can only be a cut tree
        _tile_trees(g, 3, 2, None, outside=outside)
        return g
    free = tile(None)
    check(free[0][2] == "TL", "an unconnected right edge cuts the tree (TL at x 2)")
    refused = tile({(3, 0): "TL", (3, 1): "BL"})
    check(refused[0][2] == "G", "a connected edge whose neighbour starts its own tree refuses the cut")
    matched = tile({(3, 0): "TR", (3, 1): "BR"})
    check(matched[0][2] == "TL", "a connected edge whose neighbour holds the other half keeps it")

    print("border (seams.border_cells / border_pairs, sketch.assign_tree_quarters(border=))")
    bc = seams.border_cells(p, r201, 1)
    covered = [xy for xy in bc if xy in seams.strip_cells(p, r201, 1)]
    check(bc and not covered, f"Route 201: {len(bc)} margin cells past its edges are the border's, "
                              "none under a neighbour's strip")
    corner = (r201.layout.width, r201.layout.height)        # bottom-right, past every strip
    check(bc.get(corner) == r201.layout.border_block(*corner),
          "a cell past no neighbour draws the border's 2x2 pattern")
    fill = seams.margin_fill(p, home)
    check(fill and all(seams.border_cells(p, home, 1).get(xy, b) == b for xy, b in fill.items()),
          "edge water carried on is what the border cells hold there")
    check(not seams.border_pairs(corpus, p, r201),
          "Route 201's woods meet the border on its grid: no pair vanilla never draws")
    shifted = copy.copy(r201)
    shifted.layout = copy.copy(r201.layout)
    shifted.layout.blocks = list(r201.layout.blocks)
    L = shifted.layout
    for x in range(0, 10):          # the bottom row's trees a row off the border's grid (M17's)
        L.set(x, L.height - 1, mid=0x1D4 if x % 2 == 0 else 0x1D5)
    off = seams.border_pairs(corpus, p, shifted)
    check(len(off) >= 10, f"tree tops on the bottom row under the border's tops are caught ({len(off)})")
    from mapkit.sketch import assign_tree_quarters, misaligned
    def quarters(rows, border, outside=None):
        g = [list(r) for r in rows]
        assign_tree_quarters(g, len(g[0]), len(g), None, outside=outside, border=border)
        return g
    # a band three rows deep at the bottom edge, the border's tops below it (TL at even x, even y)
    band = ["....", "TTTT", "TTTT", "TTTT"]
    below = {(x, 4): ("TL" if x % 2 == 0 else "TR") for x in range(-2, 6)}
    g = quarters(band, below)
    check(g[3][0] == "BL" and g[1][0] == "G", "against the border the band keeps whole trees on the "
                                              "border's grid and gives up its inner row")
    check(not misaligned({(x, y): q for y, r in enumerate(g) for x, q in enumerate(r)}, below),
          "and lines up with it")
    g = quarters(band, None)
    check(g[1][0] == "TL" and g[3][0] == "TL", "without the border the band is tiled from its top "
                                               "(the last row cut freely)")
    # soft: three columns between two edges whose beyond starts a tree on the wrong side each time,
    # so nothing in the sketch can match: the leftover column is still cut (no grass strip)
    sides = {(-1, 0): "TR", (-1, 1): "BR", (3, 0): "TL", (3, 1): "BL"}
    g = quarters(["TTT", "TTT"], sides)
    check(all(q != "G" for r in g for q in r), f"a leftover beside the border is still cut, not "
                                               f"dropped to grass ({g[0]})")
    g = quarters(["TTT", "TTT"], None, outside=sides)
    check(sum(q == "G" for r in g for q in r) == 2,
          f"beside a neighbour's strip the same cut is refused (strict: {g[0]})")
    g = quarters(["TTT", "TTT"], {(3, 0): "TL", (3, 1): "BL"})
    check(g[0] == ["TR", "TL", "TR"], "with one side free, the tiling cuts there and lines up with "
                                      "the border on the other")

    print("signature")
    lab = [["G", "G"], ["G", "G"]]
    below = NEIGH8.index((0, 1))
    check(signature(lab, 0, 1, 2, 2)[below] == OUT, "without seams, below the bottom row is OUT")
    check(signature(lab, 0, 1, 2, 2, {(0, 2): "TL"})[below] == "TL",
          "with seams, the neighbour's class is seen there")

    print("margin (seams.margin_fill)")
    fill = seams.margin_fill(p, home)
    up = sorted({x for x, y in fill if y < 0})
    check(up and all(-MAP_OFFSET <= y < 0 for x, y in fill if x in up and y < 0)
          and len([1 for x, y in fill if y < 0]) == len(up) * MAP_OFFSET,
          f"HomeTown's brook runs on north {MAP_OFFSET} deep over columns {up}")
    water = [x for x in range(home.layout.width)
             if p.tile_flags.get(home.layout.tiles.behavior(home.layout.mid(x, 0)), 0) & TILE_FLAG_SURFABLE]
    check(set(water) < set(up) and min(up) < min(water) and max(up) > max(water),
          f"with a verge each side (water {water})")
    # border pairing: a verge whose next cell shares its border tree widens by one
    for k in up:
        g = k + MAP_OFFSET
        partner = g + 1 if g % 2 else g - 1
        if partner - MAP_OFFSET not in up and k not in water:
            nb = partner - MAP_OFFSET
            check(False, f"verge column {k} splits the border tree with column {nb}")
            break
    else:
        check(True, "no verge splits a border tree")
    lab_map = p.load_map("Woodstock_Lab")
    check(lab_map.j.get("map_type") not in seams.OUTDOOR and not seams.margin_fill(p, lab_map),
          f"an indoor map ({lab_map.j.get('map_type')}) gets nothing")
    covered = seams.margin_fill(p, r201)
    check(not covered, "Route 201's water meets its edges only where neighbours connect: nothing filled")
    # a side with any connection is never filled (GetMapBorderIdAt would read its flag as set)
    joined = copy.copy(home)
    joined.j = copy.deepcopy(home.j)
    joined.j["connections"] = list(home.connections) + [
        {"map": r201.id, "direction": "up", "offset": 40}]      # covers none of the brook
    check(not any(y < 0 for x, y in seams.margin_fill(p, joined)),
          "with any connection on its north side, HomeTown's brook isn't carried north")
    stray = []
    for n in ("HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1", "ShoreLab"):
        mm = p.load_map(n)
        W2, H2 = mm.layout.width, mm.layout.height
        side_of = lambda x, y: "up" if y < 0 else "down" if y >= H2 else "left" if x < 0 else "right"
        on = {c["direction"] for c in mm.connections}
        stray += [(n, x, y) for x, y in seams.margin_fill(p, mm) if side_of(x, y) in on]
    check(not stray, f"no filled cell on a connected side of five maps ({stray[:3]})")

    print("gate (corridor.py check's seam_issues)")
    clean = seams.seam_issues(p, home, corpus, only={"Route201_1"}, accept={(33, 5)})
    check(not clean, f"HomeTown -> Route 201 is clean ({len(clean)} findings)")
    back = with_person(home, 31, 22)
    found = [c for s, c, _ in seams.seam_issues(p, back, corpus, only={"Route201_1"}, accept={(33, 5)})]
    check(found == ["seam_person"], f"the researcher back at (31,22) is caught: {found}")

    n, ok = len(results), sum(results)
    print(f"\nRESULT: {ok}/{n} seam checks pass")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
