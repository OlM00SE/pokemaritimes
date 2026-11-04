"""Read a .sav file (128 KB of flash) the way the game does: the one reader of the save format
for the tools and tests (dev/play.py, tests/ingame_save.py).

  python dev/savefile.py <file.sav>      # which slot loads, and whether this build can load it

The format's numbers come from include/save.h and include/save_layout.h (via save_layout.py), so
the answer is for the build those headers describe.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import save_layout

FLASH = save_layout.flash_format()
SECTOR_DATA_SIZE, SB3_CHUNK = FLASH["SECTOR_DATA_SIZE"], FLASH["SAVE_BLOCK_3_CHUNK_SIZE"]
NUM_SECTORS_PER_SLOT, NUM_SAVE_SLOTS = FLASH["NUM_SECTORS_PER_SLOT"], FLASH["NUM_SAVE_SLOTS"]
SECTOR_SIZE = SECTOR_DATA_SIZE + SB3_CHUNK + FLASH["SECTOR_FOOTER_SIZE"]
# struct SaveSector: data, the SaveBlock3 chunk, then id (u16), checksum (u16), signature, counter
ID_OFF = SECTOR_DATA_SIZE + SB3_CHUNK
CHECKSUM_OFF, SIGNATURE_OFF, COUNTER_OFF = ID_OFF + 2, ID_OFF + 4, ID_OFF + 8
SECTOR_SIGNATURE = 0x08012025
STAMP_OFF = 0x16                                     # offsetof(struct SaveBlock2, saveLayoutVersion)
SB1_START, SB1_END = FLASH["SECTOR_ID_SAVEBLOCK1_START"], FLASH["SECTOR_ID_SAVEBLOCK1_END"]


def words(data):
    return sum(struct.unpack(f"<{len(data) // 4}I", data[:len(data) // 4 * 4]))


def sector_checksum(buf, o, size):
    """src/save.c CalculateSectorChecksum: the 32-bit sum of the data's words and the SaveBlock3
    chunk's, folded to 16 bits."""
    total = (words(buf[o:o + size]) + words(buf[o + SECTOR_DATA_SIZE:o + SECTOR_DATA_SIZE + SB3_CHUNK])) & 0xFFFFFFFF
    return ((total >> 16) + total) & 0xFFFF


def sector_size(sector_id, rec=None):
    """Bytes of data in the sector with this id (src/save.c sSaveSlotLayout): SaveBlock2, then
    SaveBlock1's chunks, then the PC's, each at most SECTOR_DATA_SIZE."""
    rec = rec or save_layout.recorded()
    if sector_id < SB1_START:
        return rec["SAVE_LAYOUT_SAVEBLOCK2_SIZE"]
    if sector_id <= SB1_END:
        size, chunk = rec["SAVE_LAYOUT_SAVEBLOCK1_SIZE"], sector_id - SB1_START
    else:
        size, chunk = rec["SAVE_LAYOUT_STORAGE_SIZE"], sector_id - SB1_END - 1
    return max(0, min(size - chunk * SECTOR_DATA_SIZE, SECTOR_DATA_SIZE))


def sectors_with_id(buf, sector_id):
    """[(counter, offset)] of the sectors with this id and a valid signature, one per save slot."""
    return [(struct.unpack_from("<I", buf, i * SECTOR_SIZE + COUNTER_OFF)[0], i * SECTOR_SIZE)
            for i in range(NUM_SECTORS_PER_SLOT * NUM_SAVE_SLOTS)
            if struct.unpack_from("<I", buf, i * SECTOR_SIZE + SIGNATURE_OFF)[0] == SECTOR_SIGNATURE
            and struct.unpack_from("<H", buf, i * SECTOR_SIZE + ID_OFF)[0] == sector_id]


def current_slot(buf, sector_id):
    """[offset] of the sector with this id in the save slot that loads (the higher counter)."""
    found = sectors_with_id(buf, sector_id)
    return [max(found)[1]] if found else []


def slot_status(buf, slot, rec=None):
    """src/save.c GetSaveValidStatus for one slot: ('empty' | 'ok' | 'damaged', counter, SaveBlock2
    offset or None). 'ok' needs every sector id present with a matching checksum."""
    rec = rec or save_layout.recorded()
    valid, signed, counter, sb2 = set(), False, 0, None
    for i in range(NUM_SECTORS_PER_SLOT):
        o = (slot * NUM_SECTORS_PER_SLOT + i) * SECTOR_SIZE
        if struct.unpack_from("<I", buf, o + SIGNATURE_OFF)[0] != SECTOR_SIGNATURE:
            continue
        signed = True
        sid, chk = struct.unpack_from("<HH", buf, o + ID_OFF)
        if sid < NUM_SECTORS_PER_SLOT and chk == sector_checksum(buf, o, sector_size(sid, rec)):
            valid.add(sid)
            counter = struct.unpack_from("<I", buf, o + COUNTER_OFF)[0]
            if sid == 0:
                sb2 = o
    if not signed:
        return "empty", 0, None
    return ("ok" if len(valid) == NUM_SECTORS_PER_SLOT else "damaged"), counter, sb2


def check(path, rec=None):
    """Can the build the headers describe (or the layout `rec`, a save_layout.recorded() dict) load
    this save? ('none' | 'ok' | 'warn' | 'stale', why).
    'warn': one slot is damaged but the other loads (the game says "The save file is corrupted.
    The previous save file will be loaded."). 'stale': the game would refuse it, as
    erased (no slot passes its checksums: often a save from an older layout, whose blocks had
    other sizes) or as outdated (a valid slot stamped with another layout version)."""
    if not os.path.exists(path):
        return "none", "no save file"
    rec = rec or save_layout.recorded()
    buf = open(path, "rb").read()
    if len(buf) < NUM_SAVE_SLOTS * NUM_SECTORS_PER_SLOT * SECTOR_SIZE:
        return "stale", f"only {len(buf)} bytes: not a full save"
    slots = [slot_status(buf, s, rec) for s in range(NUM_SAVE_SLOTS)]
    if all(st == "empty" for st, _, _ in slots):
        return "none", "the save file is empty (never saved)"
    ok = [(ctr, sb2) for st, ctr, sb2 in slots if st == "ok"]
    if not ok:
        return "stale", ("no save slot passes its checksums with this build's layout (an older "
                         "layout, or damage): the game would say the save was erased")
    _, sb2 = max(ok)
    stamp, want = struct.unpack_from("<H", buf, sb2 + STAMP_OFF)[0], rec["SAVE_LAYOUT_STAMP"]
    if stamp != want:
        return "stale", (f"stamped with layout {stamp:#06x}, this build is {want:#06x} "
                         f"(version {rec['SAVE_LAYOUT_VERSION']}): the game would refuse it as outdated")
    if any(st == "damaged" for st, _, _ in slots):
        # GetSaveValidStatus: one slot OK, the other not -> SAVE_STATUS_ERROR, loads the OK one
        return "warn", "one save slot is damaged; the game will say so and load the other"
    return "ok", f"layout version {rec['SAVE_LAYOUT_VERSION']}, loads"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    verdict, why = check(sys.argv[1])
    print(f"{verdict}: {why}")
    sys.exit(0 if verdict in ("none", "ok", "warn") else 1)
