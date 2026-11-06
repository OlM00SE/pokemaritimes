"""World revisions in mGBA: a save made on a map since redesigned continues somewhere safe.

  python dev/tests/ingame_world_revision.py                      # the current ROM only
  python dev/tests/ingame_world_revision.py --old-rom <rom.gba> [--old-rom <rom2.gba>]
                                                                  # plus real saves from those
                                                                  # builds (each .map beside it)

src/overworld.c (sWorldRevisions): a save whose VAR_MARITIMES_WORLD_REVISION is below a row's
revision and that stands on that row's map continues through vanilla's continue-game warp to
the row's safe tile (the map's heal location, else the row's x, y), with the map's people at
home; the var is then current. The rows are read from overworld.c. On the current ROM:
  * a new game starts on the current revision;
  * a save on a map no row names (Route 202), marked as made before every revision, continues
    where it was saved, and the var catches up;
  * a current save on Woodstock continues where it was saved;
  * a save made on revision 1 (M15) continues where it was on Woodstock (its row is 1), but on
    HomeTown and on Route 201 (rows of revision 2) at their safe tiles;
  * a save made before M15 on Woodstock continues in front of its Center;
  each relocation: a walkable tile, people at home, in control, the var current, and a save
  made there continues there.
With --old-rom, the cases follow the revision the old build's new games start on:
  * 0 (the phone build before M15): a save in old Woodstock's green continues in front of the
    Center; a save inside the station continues there and its door leads out to the new door;
    a save on old Route 201 by Woodstock's seam continues at Route 201's safe tile;
  * 1 (the M15 phone build): a save in front of the player's house on the old HomeTown, and one
    on old Route 201 by the seam, continue at those maps' safe tiles; a save inside the player's
    house continues there, and its door leads out to the house's new door; a save on Woodstock
    beside Route 201's seam continues there, and the strip of Route 201 the game holds beside it
    is the new route's (CONTINUE pastes the save's view of the terrain, which reaches into that
    strip, unless the revision drops it).
An old build's .map must sit beside its ROM: keep copies away from dev/out/mobile, which the
mobile publish tests rewrite (dev/out/m15/oldrom: the phone build before M15,
2026-11-05_fb2b9673ff; dev/out/m16/oldrom: the M15 phone build, 2026-11-06_3a43be36ca).
Screenshots: dev/out/world_revision_<case>.png. Disposable saves under dev/out only.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit import interiors
from mapkit.events import wander_box
from ingame_buildings import fast_text

OUT = os.path.join(REPO, "dev", "out")
VAR = "VAR_MARITIMES_WORLD_REVISION"
TOWN = "Woodstock_2"
OLD_GREEN = (14, 20)        # the old Woodstock's town green; inside a building on the new map
results = []


def check(ok, what):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}: {what}", flush=True)
    return ok


def current_revision(p):
    import re
    src = open(p.path("include/constants/vars.h"), encoding="utf-8").read()
    return int(re.search(r"#define MARITIMES_WORLD_REVISION\s+(\d+)", src).group(1))


_ROWS = {}


def revision_rows(p):
    """[(map folder, revision, (x, y) safe tile)] from sWorldRevisions in src/overworld.c, in order
    (parsed once per project)."""
    import re
    if id(p) in _ROWS:
        return _ROWS[id(p)]
    src = open(p.path("src/overworld.c"), encoding="utf-8").read()
    body = src[src.index("sWorldRevisions[] ="):]
    body = body[:body.index("};")]
    heals = {h["id"]: (h["x"], h["y"]) for h in interiors.heal_locations(p)["heal_locations"]}
    rows = []
    for m in re.finditer(r"\{\s*(\d+),\s*MAP_GROUP\((\w+)\),\s*MAP_NUM\(\w+\),\s*(\w+)"
                         r"(?:,\s*(-?\d+),\s*(-?\d+))?\s*\}", body):
        rev, mapc, heal, x, y = m.groups()
        tile = heals[heal] if heal != "HEAL_LOCATION_NONE" else (int(x), int(y))
        rows.append((p.const_to_map[mapc], int(rev), tile))
    assert rows, "no rows parsed from sWorldRevisions"
    _ROWS[id(p)] = rows
    return rows


def safe_tile(p, name, saved_rev):
    """Where a save made on `saved_rev` standing on `name` continues, or None if it stays put. The
    engine applies every row newer than the save in order, and each moves the continue-game warp,
    so the last one wins."""
    hits = [tile for m, rev, tile in revision_rows(p) if m == name and rev > saved_rev]
    return hits[-1] if hits else None


def seam_strip_wrong(e, p, route, town):
    """The blocks the game holds in `route`'s connection strip toward `town`, east or west (gBackupMapLayout,
    the grid the player walks on: the map plus 7 tiles of each neighbour), compared with
    `town`'s blocks there. CONTINUE pastes a save's view of the terrain (SaveBlock1.mapView)
    over that grid, strip included, so an old save beside the seam would show the old town.
    Returns the cells that differ, as (x, y): (held, expected) metatiles."""
    r, tj = p.load_map(route), p.load_map(town)
    c = next(c for c in r.connections if c["map"] == tj.id)
    assert c["direction"] in ("left", "right"), "only an east or west seam is checked"
    off = int(c["offset"])                       # town row = route row - offset
    east = c["direction"] == "right"
    sym = e.sym["gBackupMapLayout"]
    width, ptr = e.read32(sym), e.read32(sym + 8)
    px, py = e.player()[2:]
    wrong = {}
    for y in range(py - 7, py + 8):
        for x in (range(r.layout.width, r.layout.width + 7) if east else range(-7, 0)):
            tx, ty = (x - r.layout.width if east else tj.layout.width + x), y - off
            if not (0 <= y < r.layout.height and 0 <= ty < tj.layout.height):
                continue
            held = e.read16(ptr + 2 * ((x + 7) + width * (y + 7))) & 0x3FF
            want = tj.layout.mid(tx, ty)
            if held != want:
                wrong[(tx, ty)] = (held, want)
    return wrong


def save_and_continue(e):
    if not e.save_game():
        return False
    e.cmd("reset")
    ok = e.boot_to_overworld()
    e.wait_for_control()
    return ok


def people_at_home(e, p, name):
    """Every object the game has spawned is at its map.json home (a wanderer inside its range),
    not where an old save left it; the game spawns only objects near the camera, so one that
    isn't active must be off screen. Returns the problems; when some object's home is in view, at
    least one object must be active (a safe tile with nobody in view has nothing to compare)."""
    m = p.load_map(name)
    got = {lid: (x, y) for lid, x, y in e.objects()}
    px, py = e.player()[2:]
    in_view = [o for o in m.events("object_events") if abs(o["x"] - px) <= 7 and abs(o["y"] - py) <= 5]
    wrong = [] if got or not in_view else ["no object is active"]
    for i, o in enumerate(m.events("object_events")):
        lid, home = i + 1, (o["x"], o["y"])
        at = got.get(lid)
        if at is None:
            if o.get("flag") not in (None, "0") and e.get_flag(o["flag"]):
                continue                # picked up / hidden by its flag
            if abs(home[0] - px) <= 7 and abs(home[1] - py) <= 5:
                wrong.append(f"{lid} missing though its home {home} is on screen")
        elif "WANDER" in o["movement_type"]:
            if at not in wander_box(o, m):
                wrong.append(f"{lid} at {at}, outside its range")
        elif at != home:
            wrong.append(f"{lid} at {at}, home {home}")
    return wrong


def walk_into_view_of_someone(e, p, name):
    """When nobody lives within view of the player, walk (no map reload) to a tile from which the
    nearest person's home is in view, so the 'people at home' check compares something. Returns
    a note for the check's message."""
    m = p.load_map(name)
    px, py = e.player()[2:]
    homes = [(o["x"], o["y"]) for o in m.events("object_events")]
    if not homes or any(abs(hx - px) <= 7 and abs(hy - py) <= 5 for hx, hy in homes):
        return ""
    from autowalk import Walker
    wk = Walker(e)
    L = m.layout
    for hx, hy in sorted(homes, key=lambda h: abs(h[0] - px) + abs(h[1] - py)):
        near = sorted(((abs(tx - hx) + abs(ty - hy), tx, ty)
                       for ty in range(max(0, hy - 3), min(L.height, hy + 4))
                       for tx in range(max(0, hx - 5), min(L.width, hx + 6))
                       if L.coll(tx, ty) == 0 and (tx, ty) != (hx, hy)))
        for _, tx, ty in near[:12]:
            if wk.go_to_tile(tx, ty):
                return f", walked to {(tx, ty)} to see the person at home {(hx, hy)}"
    return ", could not walk into view of anyone"


def expect_relocated(e, p, tag, name, saved_rev):
    pos = e.player()
    want = safe_tile(p, name, saved_rev)
    check(want is not None, f"{tag}: a row moves a revision-{saved_rev} save on {name}")
    check(e.map_name(pos) == p.load_map(name).id[4:] and pos[2:] == want,
          f"{tag}: continues on {name} at its safe tile {want} (got {e.map_name(pos)} {pos[2:]})")
    L = p.load_map(name).layout
    check(want is not None and L.coll(*want) == 0, f"{tag}: the safe tile is walkable")
    check(e.has_control(), f"{tag}: the player has control")
    check(e.get_var(VAR) == current_revision(p), f"{tag}: {VAR} is now {current_revision(p)}")
    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
    note = walk_into_view_of_someone(e, p, name)
    wrong = people_at_home(e, p, name)
    n = len(e.objects())
    check(n > 0 and not wrong, f"{tag}: the people in view are at their homes on the new map "
          f"({n} active{note})" + (f": {wrong}" if wrong else ""))
    if e.player()[2:] == want:
        e.press("Down", 3, 30)
        e.press("Down", 3, 60)
    moved = e.player()[2:]
    check(moved != want, f"{tag}: the player can walk away ({want} -> {moved})")
    check(save_and_continue(e) and e.player()[2:] == moved,
          f"{tag}: saving there and continuing stays there (got {e.player()[2:]})")


def walkable_near(p, name, x, y):
    """The walkable land tile nearest (x, y) on the current map (collision 0, not water)."""
    L = p.load_map(name).layout
    best = min(((abs(tx - x) + abs(ty - y), tx, ty) for ty in range(L.height) for tx in range(L.width)
                if L.coll(tx, ty) == 0 and L.mid(tx, ty) not in range(0x170, 0x1A0)))
    return best[1], best[2]


def old_save_relocates(e, p, name, at, saved_rev, tag):
    """A save standing on `name` at `at`, marked as made on `saved_rev`, CONTINUEd."""
    e.warp(name, *at)
    e.set_var(VAR, saved_rev)
    check(save_and_continue(e), f"{tag}: a save on {name} {at} made on revision {saved_rev} continues")
    expect_relocated(e, p, tag, name, saved_rev)


def current_rom(p):
    print("current ROM")
    rev = current_revision(p)
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        check(e.boot_new_game(), "a new game reaches the overworld")
        e.wait_for_control()
        fast_text(e)
        e.test_mode()
        check(e.get_var(VAR) == rev, f"a new game starts on world revision {rev} (got {e.get_var(VAR)})")
        # an old save on a map no row names: stays put, the var catches up
        spot = walkable_near(p, "Route202_1", 26, 2)
        e.warp("Route202_1", *spot)
        here = e.player()
        e.set_var(VAR, 0)
        check(save_and_continue(e) and e.player() == here,
              f"an old save on Route 202 continues where it was saved ({here[2:]} -> {e.player()[2:]})")
        check(e.get_var(VAR) == rev, "and the var is updated")
        # a current save on Woodstock: stays put, its view kept
        e.warp(TOWN, 25, 24)
        here = e.player()
        check(save_and_continue(e) and e.player() == here,
              f"a current save on {TOWN} continues where it was saved ({e.player()[2:]})")
        # a save made on revision 1 (M15): Woodstock's row is 1, so it stays on Woodstock...
        e.warp(TOWN, 25, 24)
        here = e.player()
        e.set_var(VAR, 1)
        check(safe_tile(p, TOWN, 1) is None and save_and_continue(e) and e.player() == here,
              f"a revision-1 save on {TOWN} continues where it was saved ({e.player()[2:]})")
        # ...but HomeTown and Route 201 were rebuilt in revision 2: it continues at their safe tiles
        for name, old in (("HomeTown_0", (20, 18)), ("Route201_1", (47, 14))):
            check(safe_tile(p, name, 1) is not None, f"a row moves revision-1 saves on {name}")
            at = walkable_near(p, name, *old)
            old_save_relocates(e, p, name, at, 1, f"simulated_{name}")
        # a save from before M15 on Woodstock, standing where the old green was (a building now)
        e.warp(TOWN, *OLD_GREEN)
        e.set_var(VAR, 0)
        check(save_and_continue(e), "an old save on Woodstock saves and continues")
        expect_relocated(e, p, "simulated", TOWN, 0)


def old_slot(rom):
    mp = os.path.splitext(rom)[0] + ".map"
    if not os.path.exists(mp):
        raise SystemExit(f"{mp} is missing: the old ROM's symbol map must sit beside it")
    d = tempfile.mkdtemp(prefix="emutest-oldrom-", dir=OUT)
    shutil.copyfile(rom, os.path.join(d, "test.gba"))
    shutil.copyfile(mp, os.path.join(d, "test.map"))
    return d


def walk_out_of(e, p, room, outside, tag):
    """Walk out of `room` through its door to `outside`; check it lands below the door."""
    r = p.load_map(room)
    exit_warp = next(w for w in r.events("warp_events") if w["dest_map"] == p.load_map(outside).id)
    e.warp(room, exit_warp["x"], exit_warp["y"] - 1)
    e.press("Down", 3, 30)
    e.press("Down", 3, 120)
    e.wait_for_control()
    door = next(w for w in p.load_map(outside).events("warp_events") if w["dest_map"] == r.id)
    out = e.player()
    check(e.map_name(out) == p.load_map(outside).id[4:] and out[2:] == (door["x"], door["y"] + 1),
          f"{tag}: walking out of {room} lands at its new door on {outside} ({e.map_name(out)} {out[2:]})")


def inside_door(room, outside="HomeTown_0"):
    """The tile just inside a room's door to `outside` (the room keeps its layout across builds)."""
    p = Project()
    w = next(w for w in p.load_map(room).events("warp_events") if w["dest_map"] == p.load_map(outside).id)
    return w["x"], w["y"] - 1


# Cases per old build, by the world revision its new games start on: (tag, setup on the old build,
# what this build must do: "relocate:<Map>", "stay", "room:<Room>:<Outside>", "seam:<Map>:<Other>")
OLD_CASES = {
    0: [("old_green", lambda e: e.warp(TOWN, *OLD_GREEN), "relocate:" + TOWN),
        ("old_station", lambda e: e.warp("Woodstock_Lab", 6, 10), "room:Woodstock_Lab:" + TOWN),
        ("old_route201_seam", lambda e: e.warp("Route201_1", 47, 14), "relocate:Route201_1")],
    1: [("m15_home", lambda e: e.warp("HomeTown_0", 9, 10), "relocate:HomeTown_0"),
        ("m15_route201", lambda e: e.warp("Route201_1", 47, 14), "relocate:Route201_1"),
        ("m15_house", lambda e: e.warp("LittlerootTown_MyHouse_1F_0", *inside_door("LittlerootTown_MyHouse_1F_0")),
         "room:LittlerootTown_MyHouse_1F_0:HomeTown_0"),
        ("m15_woodstock_seam", lambda e: e.warp(TOWN, 1, 36), "seam:" + TOWN + ":Route201_1")],
}


def old_rom(p, rom):
    old_rev, cases, i = None, None, 0
    while cases is None or i < len(cases):
        d = old_slot(rom)
        try:
            with Emu(os.path.join(d, "test.gba"), extra_args=UNTHROTTLED) as e:
                ok = e.boot_new_game()
                e.wait_for_control()
                if cases is None:
                    # the cases follow the revision the old build's new games start on
                    old_rev = e.get_var(VAR)
                    cases = OLD_CASES.get(old_rev)
                    if not check(ok and cases is not None, f"the old build {os.path.basename(rom)} starts "
                                 f"a new game on revision {old_rev}, which has cases"):
                        return
                tag, setup, expect = cases[i]
                print(f"old ROM ({os.path.basename(rom)}, revision {old_rev}): {tag}")
                check(ok, f"{tag}: the old build starts a new game")
                e.test_mode()
                setup(e)
                old_pos = e.player()
                check(e.save_game(), f"{tag}: the old build saves at {e.map_name(old_pos)} {old_pos[2:]}")
                e.shot(os.path.join(OUT, f"world_revision_{tag}_before.png"))
            slot = os.path.dirname(prepare_rom(fresh=True))
            shutil.copyfile(os.path.join(d, "test.sav"), os.path.join(slot, "test.sav"))
            with Emu(os.path.join(slot, "test.gba"), extra_args=UNTHROTTLED) as e:
                check(e.boot_to_overworld(), f"{tag}: this build CONTINUEs the old save")
                e.wait_for_control()
                e.test_mode()
                kind, _, rest = expect.partition(":")
                if kind == "relocate":
                    expect_relocated(e, p, tag, rest, old_rev)
                elif kind == "room":
                    room, outside = rest.split(":")
                    pos = e.player()
                    check(pos == old_pos, f"{tag}: continues inside {room} where it was saved ({pos[2:]})")
                    check(e.get_var(VAR) == current_revision(p), f"{tag}: the var is updated")
                    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
                    walk_out_of(e, p, room, outside, tag)
                elif kind == "seam":
                    here, other = rest.split(":")
                    pos = e.player()
                    check(pos == old_pos, f"{tag}: continues on {here} where it was saved ({pos[2:]})")
                    wrong = seam_strip_wrong(e, p, here, other)
                    check(not wrong, f"{tag}: the strip of {other} beside the seam shows the new map, "
                                     f"not the save's view of the old one" + (f": {len(wrong)} cells differ, "
                                     f"e.g. {sorted(wrong.items())[:3]}" if wrong else ""))
                    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
                    c = next(c for c in p.load_map(here).connections if c["map"] == p.load_map(other).id)
                    e.step("Left" if c["direction"] == "left" else "Right", 3)
                    e.wait_for_control()
                    out = e.player()
                    check(e.map_name(out) == p.load_map(other).id[4:],
                          f"{tag}: walking {c['direction']} crosses into {other} ({e.map_name(out)} {out[2:]})")
        finally:
            shutil.rmtree(d, ignore_errors=True)
        i += 1


def main(argv):
    p = Project()
    current_rom(p)
    for i, a in enumerate(argv):
        if a == "--old-rom":
            old_rom(p, os.path.abspath(argv[i + 1]))
    n, bad = len(results), results.count(False)
    print(f"RESULT: {n - bad}/{n} world revision checks pass")
    return 1 if bad or not n else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
