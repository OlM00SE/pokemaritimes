"""End-to-end playthrough of the first slice, as a new player would play it.

  python dev/tests/playthrough_slice1.py

New game (no test mode: wild battles are ON) ->
  1. leave the house into HomeTown;
  2. try to leave town without a Pokémon, by the road and by the trail along the brook: the
     researcher must call the player back both times;
  3. talk to the researcher: choose a starter, receive Poké Balls;
  4. the exit is now open: walk Route 201 to Woodstock, fleeing every wild battle;
  5. come back to the researcher and get healed.
Screenshots: dev/out/play_*.png. Exit code 1 on the first failed step.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED
from playtest import prepare_rom
from autowalk import Walker

OUT = os.path.join(REPO, "dev", "out")
RESEARCHER = (31, 22)          # beside the road where it leaves the hamlet, facing east
TALK_FROM = (32, 22)           # east of him (he faces right)
# the exit gate is the hamlet's east column (x = 33): one tile short of it, on the road and on
# the trail along the brook's far bank (over the footbridge)
EXITS = [(32, 24), (32, 14)]


class Fail(Exception):
    pass


def check(cond, msg):
    print(("PASS: " if cond else "FAIL: ") + msg)
    if not cond:
        raise Fail(msg)


def main():
    with Emu(prepare_rom(fresh=True), extra_args=UNTHROTTLED) as e:
        try:
            check(e.boot_new_game(), "new game reaches the overworld")
            wk = Walker(e, on_interrupt=e.flee_battle)
            check(e.party_count() == 0, "a new player has no Pokémon")

            for m in ("LittlerootTown_MyHouse_1F_0", "HomeTown_0"):
                check(wk.go_to_map(m), f"walk to {m}")

            # 2. the exit is guarded, on the road and on the trail
            for i, exit_tile in enumerate(EXITS):
                check(wk.go_to_tile(*exit_tile), f"reach the hamlet's edge at {exit_tile}")
                e.press("RIGHT", 16, 2)
                e.wait(30)
                e.shot(os.path.join(OUT, f"play_01_blocked{'_trail' if i else ''}.png"))
                check(not e.has_control(), f"stepping onto the edge east of {exit_tile} starts the "
                      "researcher's call (a script holds the player)")
                e.advance_text("B")
                name, pos = wk.here()
                check(name == "HomeTown_0" and pos[0] <= exit_tile[0],
                      f"without a Pokémon the player is sent back from {exit_tile} (now {name} {pos})")

            # 3. the researcher gives a starter
            check(wk.go_to_tile(*TALK_FROM), "stand beside the researcher")
            e.press("LEFT", 3, 6)                     # face him
            e.press("A", 3, 30)                       # talk
            for _ in range(300):                      # A through text, the bag, and "choose this?"
                if e.party_count() == 1:
                    break
                e.press("A", 3, 12)
            check(e.party_count() == 1, "the starter is in the party")
            e.wait(60)
            e.shot(os.path.join(OUT, "play_02_starter.png"))
            e.advance_text("B")                       # Poké Balls + goodbye text

            # 4. the way is open; wild battles are real now
            hp, max_hp = e.mon0()
            check(hp == max_hp > 0, f"the starter starts at full HP ({hp}/{max_hp})")
            for m in ("Route201_1", "Woodstock_2"):
                check(wk.go_to_map(m), f"walk to {m} (wild battles so far: {wk.battles})")
            e.shot(os.path.join(OUT, "play_03_woodstock.png"))
            hp, max_hp = e.mon0()
            check(hp > 0, f"the starter survived the trip ({hp}/{max_hp} HP)")

            # 5. back to the researcher to heal: hurt the starter first so the heal is real
            for m in ("Route201_1", "HomeTown_0"):
                check(wk.go_to_map(m), f"walk back to {m}")
            check(wk.go_to_tile(*TALK_FROM), "back beside the researcher")
            hp, max_hp = e.mon0(set_hp=1)
            check(hp == 1, "test setup: starter HP set to 1")
            e.press("LEFT", 3, 6)
            e.press("A", 3, 30)
            e.advance_text("B")
            check(e.has_control(), "the heal dialogue ends and the player has control")
            hp, max_hp = e.mon0()
            check(hp == max_hp, f"the researcher healed the starter ({hp}/{max_hp} HP)")
            print(f"wild battles fled on the way: {wk.battles}")
            print("RESULT: PASS")
            return 0
        except Fail:
            e.shot(os.path.join(OUT, "play_fail.png"))
            print("RESULT: FAIL (screenshot dev/out/play_fail.png)")
            return 1


if __name__ == "__main__":
    sys.exit(main())
