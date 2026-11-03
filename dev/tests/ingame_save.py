"""In-game: a save survives a reset, with flags at the edges of every saved flag range.

  python dev/tests/ingame_save.py

The save layout is ours to change (milestone 9 raised the trainer ceiling, which moves the
system and daily flags, and appended the Maritimes flag block). This test plays it for real:
from a new game it sets flags at both ends of the trainer range, the first system flag, a
badge, both ends of the Maritimes block and a hidden-item flag, leaves their neighbours clear,
gives a Pokémon, saves (dev mailbox 'SAVE', TrySavingData as the start menu does), resets the
console, CONTINUEs, and checks that the map, position, party and every flag (set or clear)
came back.

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

# the flash format (include/save.h) and the stamp (include/save_layout.h)
SECTOR_SIZE, NUM_SECTORS_PER_SLOT, NUM_SAVE_SLOTS, SECTOR_SIGNATURE = 0x1000, 14, 2, 0x08012025
ID_OFF, CHECKSUM_OFF, SIGNATURE_OFF = 0xFF4, 0xFF6, 0xFF8
STAMP_OFF = 0x16                                     # offsetof(struct SaveBlock2, saveLayoutVersion)
SAVE_STATUS_CORRUPT = 2


def layout():
    txt = open(os.path.join(REPO, "include", "save_layout.h"), encoding="utf-8").read()
    v = {k: int(n) for k, n in re.findall(r"#define (SAVE_LAYOUT_\w+)\s+(\d+)\s*$", txt, re.M)}
    return 0x4D00 + v["SAVE_LAYOUT_VERSION"], v["SAVE_LAYOUT_SAVEBLOCK2_SIZE"]


def checksum(data):
    """src/save.c CalculateChecksum: 32-bit sum of the words, folded to 16 bits."""
    total = sum(struct.unpack(f"<{len(data) // 4}I", data[:len(data) // 4 * 4])) & 0xFFFFFFFF
    return ((total >> 16) + total) & 0xFFFF


def saveblock2_sectors(buf):
    """Offsets of the SaveBlock2 sector (id 0, valid signature) in each save slot."""
    return [i * SECTOR_SIZE for i in range(NUM_SECTORS_PER_SLOT * NUM_SAVE_SLOTS)
            if struct.unpack_from("<I", buf, i * SECTOR_SIZE + SIGNATURE_OFF)[0] == SECTOR_SIGNATURE
            and struct.unpack_from("<H", buf, i * SECTOR_SIZE + ID_OFF)[0] == 0]


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

    # ---- the layout stamp ----
    stamp, sb2_size = layout()
    sav = os.path.join(OUT, "test.sav")
    buf = sav_io(sav)
    secs = saveblock2_sectors(buf)
    stamps = [struct.unpack_from("<H", buf, o + STAMP_OFF)[0] for o in secs]
    check(bool(secs) and all(x == stamp for x in stamps),
          f"the saved file carries the layout stamp {stamp:#06x} (SaveBlock2 sectors: {[hex(x) for x in stamps]})")
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
        reached = e.wait_until(e.in_overworld, max_frames=600)
        e.shot(os.path.join(OUT, "save_outdated_first_item.png"))
        check(not reached, "the menu's first item doesn't continue the old save (no CONTINUE offered); "
                           "screenshots dev/out/save_outdated_*.png")
    print("PASS" if not failed else f"FAIL ({failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
