"""Real trainer defeats verify initial, legacy-save and Center whiteout destinations.

  python dev/tests/ingame_respawn.py

No test_mode: give one level-1 Magikarp with Splash, hurt it, talk to Ross and actually
lose. Check the battle outcome, destination, healing and restored player control.
Also save/reset/CONTINUE an explicitly zeroed legacy respawn and a working Center.
Only a disposable test save under dev/out is used. Build the current branch first.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED, load_map_names
from playtest import prepare_rom
from mapkit.project import Project
from mapkit import interiors
from ingame_events import Run
from ingame_buildings import enter, fast_text

OUT = os.path.join(REPO, "dev", "out")
LAST_HEAL = 0x1C                       # include/global.h: SaveBlock1.lastHealLocation
B_OUTCOME_LOST = 2                     # include/constants/battle.h


def check(ok, what):
    print(f"{'PASS' if ok else 'FAIL'}: {what}", flush=True)
    if not ok:
        raise AssertionError(what)


def last_heal(e):
    sb1 = e.read32(e.sym["gSaveBlock1Ptr"])
    return struct.unpack("<bbbxhh", e.readrange(sb1 + LAST_HEAL, 8))


def expected(heal):
    ids = {name: pair for pair, name in load_map_names().items()}
    return (*ids[heal["map"][4:]], -1, heal["x"], heal["y"])


def continue_save(e, want, tag):
    here = e.player()
    check(e.save_game(), f"{tag}: save succeeds")
    e.cmd("reset")
    check(e.boot_to_overworld(), f"{tag}: CONTINUE reaches the overworld")
    e.wait_for_control()
    check(e.player() == here, f"{tag}: player location survives CONTINUE")
    check(last_heal(e) == want, f"{tag}: correct respawn after CONTINUE: {last_heal(e)}")


def lose_to_ross(e, p, destination, tag, xy=None):
    check(e.party_count() == 1, f"{tag}: exactly one party member")
    e.mon0(set_hp=1)
    e.teach_move("SPLASH")
    e.set_battle_options()
    r = Run(e, p, "Route201_1")
    i = next(i for i, o in enumerate(r.m.events("object_events"))
             if o["script"] == "Route201_1_EventScript_BugCatcherRoss")
    spot = r.spot_for(("object_events", i))
    check(spot is not None and r.stand(*spot), f"{tag}: stand beside Ross")
    e.press("A", 3, 30)
    for _ in range(100):
        if e.in_battle():
            break
        e.press("B", 3, 15)
    check(e.in_battle(), f"{tag}: an actual trainer battle starts")
    e.shot(os.path.join(OUT, f"respawn_{tag}_battle.png"))
    # A chooses FIGHT/Splash and advances loss/whiteout/nurse text; never set battle outcome.
    for _ in range(600):
        if e.in_overworld() and e.has_control(4):
            break
        e.press("A", 3, 15)
    else:
        raise AssertionError(f"{tag}: loss/whiteout never returned control")
    check(e.read8(e.sym["gBattleOutcome"]) == B_OUTCOME_LOST, f"{tag}: battle was lost")
    pos = e.player()
    check(e.map_name(pos) == p.load_map(destination).id[4:],
          f"{tag}: whiteout reaches {destination} (got {e.map_name(pos)} {pos[2:]})")
    if xy is not None:
        check(pos[2:] == xy, f"{tag}: correct home respawn tile {xy}")
    hp, mx = e.mon0()
    check(hp == mx > 0, f"{tag}: party healed to {hp}/{mx} HP")
    check(e.has_control(), f"{tag}: player can move again")
    e.shot(os.path.join(OUT, f"respawn_{tag}_arrival.png"))


def main():
    p = Project()
    heals = interiors.heal_locations(p)["heal_locations"]
    home = next(h for h in heals if h["id"] == "HEAL_LOCATION_LITTLEROOT_TOWN_MY_HOUSE_2F")
    center = next(h for h in heals if h["id"] == "HEAL_LOCATION_TOWN_LAB")
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        try:
            check(e.boot_new_game(), "fresh game reaches the overworld")
            e.wait_for_control()
            fast_text(e)
            check(last_heal(e) == expected(home), f"new game initializes home respawn: {last_heal(e)}")
            e.give_mon("MAGIKARP", 1)
            lose_to_ross(e, p, "LittlerootTown_MyHouse_2F_0", "newgame", (home["x"], home["y"]))

            sb1 = e.read32(e.sym["gSaveBlock1Ptr"])
            for off in range(8):
                e.cmd(f"write8 {sb1 + LAST_HEAL + off:x} 0")
            check(last_heal(e) == (0, 0, 0, 0, 0), "legacy fixture has an uninitialized respawn")
            continue_save(e, expected(home), "legacy")
            lose_to_ross(e, p, "LittlerootTown_MyHouse_2F_0", "legacy", (home["x"], home["y"]))

            town = p.load_map("TownLab")
            door = next(w for w in town.events("warp_events") if w["dest_map"] == center["respawn_map"])
            enter(e, "TownLab", door)    # actual door entry runs the Center's setrespawn
            check(e.map_name() == center["respawn_map"][4:], "enter the working Center through its door")
            check(last_heal(e) == expected(center), "Center entry replaces home respawn")
            continue_save(e, expected(center), "center")
            lose_to_ross(e, p, "TownLab_PokemonCenter_1F", "center")
            check(last_heal(e) == expected(center), "Center respawn remains selected after whiteout")
            print("RESULT: PASS (three actual trainer defeats)", flush=True)
            return 0
        except (AssertionError, RuntimeError):
            e.shot(os.path.join(OUT, "respawn_FAILED.png"))
            raise


if __name__ == "__main__":
    raise SystemExit(main())
