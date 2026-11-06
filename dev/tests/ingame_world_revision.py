"""World revisions in mGBA: a save made on a map since redesigned continues somewhere safe.

  python dev/tests/ingame_world_revision.py                      # the current ROM only
  python dev/tests/ingame_world_revision.py --old-rom <rom.gba>  # plus real saves from that build
                                                                  # (its .map beside it)

src/overworld.c (sWorldRevisions): a save whose VAR_MARITIMES_WORLD_REVISION is below a row's
revision and that stands on that row's map continues through vanilla's continue-game warp to
the map's safe tile (its heal location), with the map's people at home; the var is then current.
On the current ROM (no old build needed):
  * a new game starts on the current revision;
  * a save standing on Woodstock, marked as made before M15 (the var set back to 0), continues
    in front of Woodstock's Center: on a walkable tile, people at home, the player in control,
    the var current, and a save made there continues there;
  * a current save on Woodstock continues where it was saved;
  * an old save on another map (Route 201) continues where it was saved; the var is updated.
With --old-rom (the build before the redesign, e.g. the published phone build):
  * a save made on that build in old Woodstock's green continues on this build in front of
    the Center, with the people at their new homes;
  * a save made on that build inside the station continues there, and its door leads out to
    the station's new door;
  * a save made on that build on Route 201 beside Woodstock's seam continues there, and the
    strip of Woodstock the game holds beside it is the new town's (CONTINUE pastes the save's
    view of the terrain, which reaches into that strip, unless the revision drops it).
The old build's .map must sit beside its ROM: keep a copy away from dev/out/mobile, which the
mobile publish tests rewrite (dev/out/m15/oldrom: the phone build before M15, 2026-11-05_fb2b9673ff, with its map rebuilt byte for byte).
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


def safe_tile(p):
    heal = next(h for h in interiors.heal_locations(p)["heal_locations"] if h["id"] == "HEAL_LOCATION_WOODSTOCK_2")
    return heal["x"], heal["y"]


def seam_strip_wrong(e, p, route, town):
    """The blocks the game holds in `route`'s connection strip toward `town` (gBackupMapLayout,
    the grid the player walks on: the map plus 7 tiles of each neighbour), compared with
    `town`'s blocks there. CONTINUE pastes a save's view of the terrain (SaveBlock1.mapView)
    over that grid, strip included, so an old save beside the seam would show the old town.
    Returns the cells that differ, as (x, y): (held, expected) metatiles."""
    r, tj = p.load_map(route), p.load_map(town)
    c = next(c for c in r.connections if c["map"] == tj.id)
    assert c["direction"] == "right", "only an east seam is checked"
    off = int(c["offset"])                       # town row = route row - offset
    sym = e.sym["gBackupMapLayout"]
    width, ptr = e.read32(sym), e.read32(sym + 8)
    px, py = e.player()[2:]
    wrong = {}
    for y in range(py - 7, py + 8):
        for x in range(r.layout.width, r.layout.width + 7):
            tx, ty = x - r.layout.width, y - off
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
    isn't active must be off screen. Returns the problems; at least one object must be active."""
    m = p.load_map(name)
    got = {lid: (x, y) for lid, x, y in e.objects()}
    px, py = e.player()[2:]
    wrong = [] if got else ["no object is active"]
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


def expect_relocated(e, p, tag):
    pos = e.player()
    want = safe_tile(p)
    check(e.map_name(pos) == p.load_map(TOWN).id[4:] and pos[2:] == want,
          f"{tag}: continues on {TOWN} at its safe tile {want} (got {e.map_name(pos)} {pos[2:]})")
    L = p.load_map(TOWN).layout
    check(L.coll(*want) == 0, f"{tag}: the safe tile is walkable")
    wrong = people_at_home(e, p, TOWN)
    check(not wrong, f"{tag}: the people in view are at their homes on the new map ({len(e.objects())} active)"
          + (f": {wrong}" if wrong else ""))
    check(e.has_control(), f"{tag}: the player has control")
    check(e.get_var(VAR) == current_revision(p), f"{tag}: {VAR} is now {current_revision(p)}")
    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
    e.press("Down", 3, 30)
    e.press("Down", 3, 60)
    moved = e.player()[2:]
    check(moved != want, f"{tag}: the player can walk away ({want} -> {moved})")
    check(save_and_continue(e) and e.player()[2:] == moved,
          f"{tag}: saving there and continuing stays there (got {e.player()[2:]})")


def current_rom(p):
    print("current ROM")
    rev = current_revision(p)
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        check(e.boot_new_game(), "a new game reaches the overworld")
        e.wait_for_control()
        fast_text(e)
        e.test_mode()
        check(e.get_var(VAR) == rev, f"a new game starts on world revision {rev} (got {e.get_var(VAR)})")
        # an old save on another map, beside Woodstock's seam: stays put, the var catches up, and
        # its saved view (which reaches into Woodstock's strip) is dropped
        e.warp("Route201_1", 47, 14)
        here = e.player()
        e.set_var(VAR, 0)
        check(save_and_continue(e) and e.player() == here,
              f"an old save on Route 201 by the seam continues where it was saved ({here[2:]} -> {e.player()[2:]})")
        check(e.get_var(VAR) == rev, "and the var is updated")
        # a current save on Woodstock: stays put, its view kept
        e.warp(TOWN, 25, 24)
        here = e.player()
        check(save_and_continue(e) and e.player() == here,
              f"a current save on {TOWN} continues where it was saved ({e.player()[2:]})")
        # an old save on Woodstock, standing where the old green was (a building now)
        e.warp(TOWN, *OLD_GREEN)
        e.set_var(VAR, 0)
        check(save_and_continue(e), "an old save on Woodstock saves and continues")
        expect_relocated(e, p, "simulated")


def old_slot(rom):
    mp = os.path.splitext(rom)[0] + ".map"
    if not os.path.exists(mp):
        raise SystemExit(f"{mp} is missing: the old ROM's symbol map must sit beside it")
    d = tempfile.mkdtemp(prefix="emutest-oldrom-", dir=OUT)
    shutil.copyfile(rom, os.path.join(d, "test.gba"))
    shutil.copyfile(mp, os.path.join(d, "test.map"))
    return d


def old_rom(p, rom):
    for tag, setup in (("old_green", lambda e: e.warp(TOWN, *OLD_GREEN)),
                       ("old_station", lambda e: e.warp("Woodstock_Lab", 6, 10)),
                       ("old_route201_seam", lambda e: e.warp("Route201_1", 47, 14))):
        print(f"old ROM ({os.path.basename(rom)}): {tag}")
        d = old_slot(rom)
        try:
            with Emu(os.path.join(d, "test.gba"), extra_args=UNTHROTTLED) as e:
                check(e.boot_new_game(), f"{tag}: the old build starts a new game")
                e.wait_for_control()
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
                if tag == "old_green":
                    expect_relocated(e, p, tag)
                elif tag == "old_route201_seam":
                    pos = e.player()
                    check(pos == old_pos, f"{tag}: continues on Route 201 where it was saved ({pos[2:]})")
                    wrong = seam_strip_wrong(e, p, "Route201_1", TOWN)
                    check(not wrong, f"{tag}: the strip of Woodstock beside the seam shows the new town, "
                                     f"not the save's view of the old one" + (f": {len(wrong)} cells differ, "
                                     f"e.g. {sorted(wrong.items())[:3]}" if wrong else ""))
                    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
                    e.step("Right", 3)                 # (47,14) -> (49,14) -> Woodstock (0,36)
                    e.wait_for_control()
                    out = e.player()
                    check(e.map_name(out) == "WOODSTOCK_2" and out[2:] == (0, 36),
                          f"{tag}: walking east crosses into Woodstock's highway ({e.map_name(out)} {out[2:]})")
                else:
                    pos = e.player()
                    check(pos == old_pos, f"{tag}: continues inside the station where it was saved ({pos[2:]})")
                    check(e.get_var(VAR) == current_revision(p), f"{tag}: the var is updated")
                    room = p.load_map("Woodstock_Lab")
                    exit_warp = next(w for w in room.events("warp_events") if w["dest_map"] == "MAP_WOODSTOCK_2")
                    e.warp("Woodstock_Lab", exit_warp["x"], exit_warp["y"] - 1)
                    e.press("Down", 3, 30)
                    e.press("Down", 3, 120)
                    e.wait_for_control()
                    door = next(w for w in p.load_map(TOWN).events("warp_events")
                                if w["dest_map"] == "MAP_WOODSTOCK_LAB")
                    out = e.player()
                    check(e.map_name(out) == "WOODSTOCK_2" and out[2:] == (door["x"], door["y"] + 1),
                          f"{tag}: walking out of the station lands at its new door ({out[2:]})")
                    e.shot(os.path.join(OUT, f"world_revision_{tag}.png"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


def main(argv):
    p = Project()
    current_rom(p)
    if "--old-rom" in argv:
        old_rom(p, os.path.abspath(argv[argv.index("--old-rom") + 1]))
    n, bad = len(results), results.count(False)
    print(f"RESULT: {n - bad}/{n} world revision checks pass")
    return 1 if bad or not n else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
