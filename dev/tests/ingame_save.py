"""In-game: a save survives a reset, with flags at the edges of every saved flag range.

  python dev/tests/ingame_save.py

The save layout is ours to change (milestone 9 raised the trainer ceiling, which moves the
system and daily flags, and appended the Maritimes flag block). This test plays it for real:
from a new game it sets flags at both ends of the trainer range, the first system flag, a
badge, both ends of the Maritimes block and a hidden-item flag, leaves their neighbours clear,
gives a Pokémon, saves (dev mailbox 'SAVE', TrySavingData as the start menu does), resets the
console, CONTINUEs, and checks that the map, position, party and every flag (set or clear)
came back. Story vars (the Maritimes block in SaveBlock3, milestone 11) at both ends of the
block and a vanilla var go the same way, then again through a link save (SAVE_LINK, which
rewrites only sectors 0-4); an id past the block isn't a var; and a NEW GAME over the save starts
with them at 0.

Then the save layout guard (include/save_layout.h): the saved file must carry SAVE_LAYOUT_STAMP
in SaveBlock2, and a save stamped otherwise (rewritten on disk as a milestone-9 save would be,
checksums fixed so it is a valid save in every other way) must be refused: the load reports it
outdated, the main menu explains, and its first item starts a new game instead of continuing.
Exit code 1 on any failure.
"""
import os, re, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import Emu, REPO, UNTHROTTLED, flag_id
from playtest import prepare_rom, OUT
import save_layout

# the flash format (include/save.h) and the stamp (include/save_layout.h)
SECTOR_SIZE, NUM_SECTORS_PER_SLOT, NUM_SAVE_SLOTS, SECTOR_SIGNATURE = 0x1000, 14, 2, 0x08012025
ID_OFF, CHECKSUM_OFF, SIGNATURE_OFF, COUNTER_OFF = 0xFF4, 0xFF6, 0xFF8, 0xFFC
SECTOR_DATA_SIZE, SB3_CHUNK = 3968, 116              # data bytes, then a SaveBlock3 chunk, then the footer
STAMP_OFF = 0x16                                     # offsetof(struct SaveBlock2, saveLayoutVersion)
SAVE_STATUS_CORRUPT = 2


def layout():
    rec = save_layout.recorded()
    return rec["SAVE_LAYOUT_STAMP"], rec["SAVE_LAYOUT_SAVEBLOCK2_SIZE"]


def checksum(data):
    """src/save.c CalculateChecksum: 32-bit sum of the words, folded to 16 bits."""
    total = sum(struct.unpack(f"<{len(data) // 4}I", data[:len(data) // 4 * 4])) & 0xFFFFFFFF
    return ((total >> 16) + total) & 0xFFFF


def saveblock2_sectors(buf):
    """Offsets of the SaveBlock2 sector (id 0, valid signature) in each save slot."""
    return [i * SECTOR_SIZE for i in range(NUM_SECTORS_PER_SLOT * NUM_SAVE_SLOTS)
            if struct.unpack_from("<I", buf, i * SECTOR_SIZE + SIGNATURE_OFF)[0] == SECTOR_SIGNATURE
            and struct.unpack_from("<H", buf, i * SECTOR_SIZE + ID_OFF)[0] == 0]


def current_slot(buf, sector_id):
    """[offset] of the sector with this id in the save slot that loads (the higher counter)."""
    found = [(struct.unpack_from("<I", buf, i * SECTOR_SIZE + COUNTER_OFF)[0], i * SECTOR_SIZE)
             for i in range(NUM_SECTORS_PER_SLOT * NUM_SAVE_SLOTS)
             if struct.unpack_from("<I", buf, i * SECTOR_SIZE + SIGNATURE_OFF)[0] == SECTOR_SIGNATURE
             and struct.unpack_from("<H", buf, i * SECTOR_SIZE + ID_OFF)[0] == sector_id]
    return [max(found)[1]] if found else []


def sav_io(path, data=None):
    """Read the save file, or write it back in place. mGBA may still be closing it (on Windows
    it keeps the file mapped for a moment), so retry."""
    for _ in range(40):
        try:
            with open(path, "r+b") as f:
                if data is None:
                    return bytearray(f.read())
                f.write(data)
                return data
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{path} stayed locked")


SET = ["TRAINER_FLAGS_START", "TRAINER_FLAGS_END", "FLAG_SYS_POKEMON_GET", "FLAG_BADGE08_GET",
       "MARITIMES_FLAGS_START", "MARITIMES_FLAGS_END", "FLAG_HIDDEN_ITEM_ROUTE201_1_POND_POTION"]
# vars: both ends of the story var block (SaveBlock3) and a vanilla one (SaveBlock1), with
# distinct values; the last vanilla var, next to the block, stays 0. Two values per var: the
# normal save, then a link save.
VARS = {"MARITIMES_VARS_START": (0x1234, 0x2468), "MARITIMES_VARS_END": (0xBEEF, 0x0F0F),
        "VAR_UNUSED_0x40F7": (0x0077, 0x7700), "VARS_END": (0, 0)}


def check_vars(e, check, phase, which):
    for n, vals in VARS.items():
        got = e.get_var(n)
        check(got == vals[which], f"{phase}: var {flag_id(n):#06x} {n} = {vals[which]:#06x}"
                                  + ("" if got == vals[which] else f" -- got {got:#06x}"))


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
        check(all(e.get_var(n) == 0 for n in VARS), "a new game starts with the story vars at 0")
        for n, vals in VARS.items():
            if n != "VARS_END":
                e.set_var(n, vals[0])
        gap = flag_id("MARITIMES_VARS_END") + 1      # past the block, below the special vars
        check(not e.set_var(gap, 1) and e.get_var(gap) == gap,
              f"{gap:#06x}, past the block, isn't a var: it can't be set and reads as itself (VarGet)")
        before = e.player()
        check(all(e.get_flag(v) == on for v, on in want.items()), "flags read back before saving")
        check_vars(e, check, "before saving", 0)
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
        check_vars(e, check, "after CONTINUE", 0)

        # a link / Battle Frontier save rewrites only SaveBlock2 and SaveBlock1's sectors (0-4):
        # the story vars must be in their SaveBlock3 chunks to come back
        for n, vals in VARS.items():
            if n != "VARS_END":
                e.set_var(n, vals[1])
        e.set_flag(ids["MARITIMES_FLAGS_START"], False)
        check(e.save_game(link=True), "a link save (SAVE_LINK) succeeds")
        e.cmd("reset")
        check(e.boot_to_overworld(), "after the link save and a reset, CONTINUE reaches the overworld")
        e.wait_for_control()
        check_vars(e, check, "after the link save", 1)
        check(not e.get_flag(ids["MARITIMES_FLAGS_START"]) and e.get_flag(ids["MARITIMES_FLAGS_END"]),
              "after the link save: the block flag cleared before it stays clear, the other stays set")

    # NEW GAME over a save must not inherit its story vars (NewGameInitData: ClearSav3)
    rom = prepare_rom(fresh=False)
    with Emu(rom, extra_args=UNTHROTTLED) as e:
        check(e.boot_new_game(), "a new game over the save reaches the overworld")
        check(all(e.get_var(n) == 0 for n in VARS) and not e.get_flag(ids["MARITIMES_FLAGS_END"]),
              "the new game's story vars and block flags start at 0, not the save's")

    # ---- the layout stamp ----
    stamp, sb2_size = layout()
    sav = os.path.join(OUT, "test.sav")
    buf = sav_io(sav)
    secs = saveblock2_sectors(buf)
    stamps = [struct.unpack_from("<H", buf, o + STAMP_OFF)[0] for o in secs]
    check(bool(secs) and all(x == stamp for x in stamps),
          f"the saved file carries the layout stamp {stamp:#06x} (SaveBlock2 sectors: {[hex(x) for x in stamps]})")
    # the story vars on flash: SaveBlock3 byte b is in sector b // 116's footer chunk (after the
    # 3,968 data bytes); the last save was the link save
    rec = save_layout.recorded()
    for n in ("MARITIMES_VARS_START", "MARITIMES_VARS_END"):
        b = rec["SAVE_LAYOUT_MARITIMES_VARS_OFFSET"] + 2 * (flag_id(n) - flag_id("MARITIMES_VARS_START"))
        got = [struct.unpack_from("<H", buf, o + SECTOR_DATA_SIZE + b % SB3_CHUNK)[0] for o in current_slot(buf, b // SB3_CHUNK)]
        check(got == [VARS[n][1]], f"on flash, {n} is in sector {b // SB3_CHUNK}'s SaveBlock3 chunk: "
                                   f"{[hex(x) for x in got]} (want {VARS[n][1]:#06x})")
    for o in secs:                                   # rewrite as a save from the previous layout
        struct.pack_into("<H", buf, o + STAMP_OFF, 0)
        struct.pack_into("<H", buf, o + CHECKSUM_OFF, checksum(bytes(buf[o:o + sb2_size])))
    sav_io(sav, bytes(buf))
    rom = prepare_rom(fresh=False)
    with Emu(rom, extra_args=UNTHROTTLED) as e:
        e.wait_until(lambda: e.read8(e.sym["gSaveFileOutdated"]), max_frames=600)   # set while booting
        check(e.read8(e.sym["gSaveFileOutdated"]) == 1 and e.read16(e.sym["gSaveFileStatus"]) == SAVE_STATUS_CORRUPT,
              "a save stamped with another layout is refused on load (outdated, treated as erased)")
        for _ in range(10):                          # past the intro and the title screen to the main
            e.press("START", 3, 45)                  # menu (START does nothing there or on its message)
        e.wait(60)
        e.shot(os.path.join(OUT, "save_outdated_menu.png"))
        e.press("A", 3, 40)                          # dismiss the message
        e.press("A", 3, 40)                          # the first item: NEW GAME (CONTINUE would load it)
        # NEW GAME's first act is Birch's speech, which plays MUS_ROUTE122 (main_menu.c); the
        # music player's first field is the song header playing
        birch = e.wait_until(lambda: e.read32(e.sym["gMPlayInfo_BGM"]) == e.sym["mus_route122"], max_frames=600)
        e.shot(os.path.join(OUT, "save_outdated_first_item.png"))
        check(birch and not e.in_overworld(),
              "the menu's first item starts a new game (Birch's speech), not CONTINUE; "
              "screenshots dev/out/save_outdated_*.png")
    print("PASS" if not failed else f"FAIL ({failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
