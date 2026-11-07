"""Seam checks (mapkit/seams.py) and the compiler's seam context, without an emulator.

Each check has a negative control: the same rule on a case built to break it.
  people      the view band across each kind of seam: in at its limit, out one tile further
  tileset     Route 203 sees Fredericton's Rustboro fence; same-tileset seams see nothing
  pairs       the corridor's seams are clean; a tree cut at Route 201's seam (as before the fix) is
              caught
  trees       a cut tree at a connected edge needs the neighbour's other half; an unconnected edge
              cuts freely
  signature   across a seam the autotiler sees the neighbour, not OUT
  margin      edge water and its verges, and the border-pattern widening, on a made-up edge
  gate        corridor.py check turns a person back at HomeTown's old spot into an error

  python dev/tests/seam_checks.py
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project, MAP_OFFSET
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
             if p.tile_flags.get(home.layout.tiles.behavior(home.layout.mid(x, 0)), 0) & 2]
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
