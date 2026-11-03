"""In-game: a save survives a reset, with flags at the edges of every saved flag range.

  python dev/tests/ingame_save.py

The save layout is ours to change (milestone 9 raised the trainer ceiling, which moves the
system and daily flags, and appended the Maritimes flag block). This test plays it for real:
from a new game it sets flags at both ends of the trainer range, the first system flag, a
badge, both ends of the Maritimes block and a hidden-item flag, leaves their neighbours clear,
gives a Pokémon, saves (dev mailbox 'SAVE', TrySavingData as the start menu does), resets the
console, CONTINUEs, and checks that the map, position, party and every flag (set or clear)
came back. Exit code 1 on any failure.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, UNTHROTTLED, flag_id
from playtest import prepare_rom

SET = ["TRAINER_FLAGS_START", "TRAINER_FLAGS_END", "FLAG_SYS_POKEMON_GET", "FLAG_BADGE08_GET",
       "MARITIMES_FLAGS_START", "MARITIMES_FLAGS_END", "FLAG_HIDDEN_ITEM_ROUTE201_1_POND_POTION"]


def main():
    ids = {n: flag_id(n) for n in SET}
    want = {v: True for v in ids.values()}
    # neighbours stay clear: a shifted bit or a byte off by one shows up here
    for n in ("TRAINER_FLAGS_END", "MARITIMES_FLAGS_START", "MARITIMES_FLAGS_END"):
        for v in (ids[n] - 1, ids[n] + 1):
            want.setdefault(v, False)
    want.pop(flag_id("FLAGS_COUNT"), None)           # past the saved flags: not a real flag
    rom = prepare_rom(fresh=True)
    failed = 0

    def check(ok, what):
        nonlocal failed
        print(f"  {'PASS' if ok else 'FAIL'}: {what}")
        failed += not ok

    with Emu(rom, extra_args=UNTHROTTLED) as e:
        if not e.boot_new_game():
            print("FAIL: never reached the overworld")
            return 1
        e.test_mode()
        e.give_mon("STARLY", 7)
        e.warp("Woodstock_2", 14, 20)
        for v, on in want.items():
            e.set_flag(v, on)
        before = e.player()
        check(all(e.get_flag(v) == on for v, on in want.items()), "flags read back before saving")
        check(e.save_game(), "the game saves (TrySavingData: SAVE_STATUS_OK)")
        e.cmd("reset")
        check(e.boot_to_overworld(), "after a reset, CONTINUE reaches the overworld")
        e.wait_for_control()
        after = e.player()
        check(after[:4] == before[:4], f"same map and position ({e.map_name(after)} {after[2:4]})")
        check(e.party_count() == 1, "the party came back")
        names = {v: n for n, v in ids.items()}
        for v, on in sorted(want.items()):
            got = e.get_flag(v)
            check(got == on, f"flag {v:#05x} {names.get(v, '(neighbour)')}: {'set' if on else 'clear'}"
                             f"{'' if got == on else ' -- got the opposite'}")
    print("PASS" if not failed else f"FAIL ({failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
