"""In-game: the working rooms behind building stamps (mapkit/interiors.py) do their jobs.

  python dev/tests/ingame_buildings.py [Map ...]          (default: TownLab)

For each outdoor map, from a new game played as a player would (no test mode; text speed fast):
  - every Pokémon Center whose heal location is on the map (src/data/heal_locations.json):
      walking in through its door sets the respawn point: SaveBlock1.lastHealLocation becomes
      that heal location (this map, its x and y, no warp id), which is what a whiteout and
      Teleport read; then the nurse, talked to from a trigger tile the events model picks,
      heals party slot 0 from 1 HP to full;
  - every Mart (a room whose clerk runs <Room>_EventScript_Clerk): the clerk opens the shop,
      and buying one of the first item puts it in the bag.
Screenshots: dev/out/buildings_<Room>_*.png. Exit code 1 on any failure.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from mapkit.project import Project
from mapkit import interiors
from ingame_events import Run

OUT = os.path.join(REPO, "dev", "out")
LAST_HEAL = 0x1C                     # SaveBlock1.lastHealLocation (include/global.h)
WARP_ID_NONE = 0xFF                  # s8 -1
OPTIONS = 0x14                       # SaveBlock2: optionsTextSpeed is bits 0-2
TEXT_SPEED_FAST = 2                  # OPTIONS_TEXT_SPEED_FAST (include/constants/global.h)


def fast_text(e):
    """Text speed FAST in the save's options, so a fixed wait covers each message."""
    addr = e.read32(e.sym["gSaveBlock2Ptr"]) + OPTIONS
    e.cmd(f"write16 {addr:x} {(e.read16(addr) & ~7) | TEXT_SPEED_FAST}")


def rooms(p, outdoor):
    """[(door warp, room name)] of the map's doors."""
    m = p.load_map(outdoor)
    return [(w, p.const_to_map[w["dest_map"]]) for w in m.events("warp_events")
            if w["dest_map"] in p.const_to_map]


def stock(p, room):
    """The first item of a Mart room's stock (its scripts.pory `mart` block), else None."""
    path = p.path("data/maps", room, "scripts.pory")
    if not os.path.exists(path):
        return None
    m = re.search(r"mart\s+\w+\s*\{\s*(ITEM_\w+)", open(path, encoding="utf-8").read())
    return m.group(1) if m else None


def enter(e, outdoor, w):
    """Warp in front of the door and walk in; True if the player ends up inside."""
    e.warp(outdoor, w["x"], w["y"] + 1)
    e.press("UP", 16, 4)
    e.wait_for_control()
    return e.player()


def main(argv):
    names = argv or ["TownLab"]
    p = Project()
    heals = interiors.heal_locations(p)["heal_locations"]
    passed = failed = 0

    def check(ok, what):
        nonlocal passed, failed
        print(f"  {'PASS' if ok else 'FAIL'}: {what}")
        passed += ok
        failed += not ok
        return ok

    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        assert e.boot_new_game()
        fast_text(e)                    # real play: no test_mode (TownLab has no grass or trainers)
        e.give_mon("STARLY", 20)
        for outdoor in names:
            m = p.load_map(outdoor)
            door_rooms = rooms(p, outdoor)
            if not door_rooms:
                check(False, f"{outdoor}: no rooms behind doors; NOT TESTED")
                continue
            e.warp(outdoor, door_rooms[0][0]["x"], door_rooms[0][0]["y"] + 1)
            group, num = e.player()[:2]
            centers = marts = 0
            for w, room in door_rooms:
                rm = interiors.load(p, room)
                heal = next((h for h in heals if h.get("respawn_map") == rm["id"] and h["map"] == m.id), None)
                nurse = next((i for i, o in enumerate(rm["object_events"])
                              if o["graphics_id"] == interiors.NURSE_GFX), None)
                is_center = heal is not None or nurse is not None or "POKEMON_CENTER" in rm["id"]
                if is_center:
                    centers += 1
                    if not check(heal is not None, f"{room}: a Center has a heal location"):
                        continue
                    print(f"{outdoor}: Pokémon Center {room} ({heal['id']})")
                    pos = enter(e, outdoor, w)
                    check(e.map_name(pos) == rm["id"][4:], f"the door at ({w['x']},{w['y']}) leads into {room}")
                    sb1 = e.read32(e.sym["gSaveBlock1Ptr"])
                    raw = e.readrange(sb1 + LAST_HEAL, 8)
                    got = (raw[0], raw[1], raw[2], int.from_bytes(raw[4:6], "little", signed=True),
                           int.from_bytes(raw[6:8], "little", signed=True))
                    want = (group, num, WARP_ID_NONE, heal["x"], heal["y"])
                    check(got == want, f"entering sets the respawn point to {heal['id']}: {got} (want {want})")
                    e.mon0(set_hp=1)
                    hp, mx = e.mon0()
                    check(hp == 1, f"party slot 0 hurt to 1/{mx} HP")
                    r = Run(e, p, room)
                    if not check(nurse is not None, f"{room}: a Center has a nurse"):
                        continue
                    spot = r.spot_for(("object_events", nurse))
                    if check(spot is not None and r.stand(*spot), f"stand at the counter facing the nurse {spot}"):
                        e.press("A", 3, 60)
                        e.shot(os.path.join(OUT, f"buildings_{room}_nurse.png"))
                        e.advance_text("A")              # YES is the default answer
                        hp, mx = e.mon0()
                        check(hp == mx, f"the nurse heals: {hp}/{mx} HP")
                        e.shot(os.path.join(OUT, f"buildings_{room}_healed.png"))
                item = stock(p, room)
                clerk = next((i for i, o in enumerate(rm["object_events"])
                              if o["script"] == f"{room}_EventScript_Clerk"), None)
                is_mart = clerk is not None or item is not None or rm["id"].endswith("_MART")
                if is_mart:
                    marts += 1
                    if not check(clerk is not None and item is not None,
                                 f"{room}: a Mart has a clerk and stock"):
                        continue
                    print(f"{outdoor}: Mart {room}")
                    pos = enter(e, outdoor, w)
                    check(e.map_name(pos) == rm["id"][4:], f"the door at ({w['x']},{w['y']}) leads into {room}")
                    r = Run(e, p, room)
                    spot = r.spot_for(("object_events", clerk))
                    before = e.bag_count(item)
                    if check(spot is not None and r.stand(*spot), f"stand at the counter facing the clerk {spot}"):
                        # one press per prompt, each after its text has finished printing (a press
                        # while text prints only speeds it up)
                        for key, wait, shot in (("A", 120, None),      # talk: "Welcome!"
                                                ("A", 120, "menu"),    # "How may I serve you?" BUY/SELL/SEE YA
                                                ("A", 120, None),      # BUY: the shop screen fades in
                                                ("A", 120, "shop"),    # the first item: "How many?"
                                                ("A", 120, "confirm"),  # 1: "That will be ...? OK?" YES/NO
                                                ("A", 120, "bought"),  # YES: "Here you go! Thank you."
                                                ("A", 90, None)):      # back to the list
                            e.press(key, 3, wait)
                            if shot:
                                e.shot(os.path.join(OUT, f"buildings_{room}_{shot}.png"))
                        e.advance_text("B")              # close the list, leave the menu, "Please come again"
                        after = e.bag_count(item)
                        check(after == before + 1, f"buying one {item}: {before} -> {after}")
            if not centers and not marts:
                check(False, f"{outdoor}: no Centers or Marts found; NOT TESTED")
            if outdoor == "TownLab":
                check(centers >= 1 and marts >= 1,
                      f"{outdoor}: expected both a Center and a Mart ({centers}, {marts})")
            print(f"{outdoor}: {centers} Centers, {marts} Marts selected")
    print(f"RESULT: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
