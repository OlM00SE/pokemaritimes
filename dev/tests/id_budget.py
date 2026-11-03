"""Static check of the game's global ids: trainer ids, saved flags and the save block's room.

  python dev/tests/id_budget.py          (no emulator; reads the headers, maps and pokeemerald.map)

Ids are global and never move (dev/events.py appends them), so their budget is checked here:
  - trainers: ids 0..TRAINERS_COUNT-1 are unique and contiguous, fit MAX_TRAINERS_COUNT (one
    trainer flag each), and every id has a party in src/data/trainers.party;
  - flags: the saved ranges (temp, ..., trainer, system, daily, Maritimes block) don't overlap;
    each Maritimes-block flag has its own offset inside the block; each item or hidden-item flag
    is used by exactly one event on any map (a shared flag makes one pickup hide the other) and
    lies in a saved, non-temporary, non-daily range (hidden items: at or above
    FLAG_HIDDEN_ITEMS_START);
  - save block: the room left in SaveBlock1, for information (approximate: measured between
    two symbols in pokeemerald.map). The build enforces the limit: STATIC_ASSERT in src/save.c.
Prints what's left of each budget. Exit code 1 on any failure.
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import REPO, flag_id

SECTOR_DATA_SIZE, SAVEBLOCK1_SECTORS, SAVEBLOCK_MOVE_RANGE = 3968, 4, 128   # save.h, load_save.h
SAVE_ROOM_WARN = 64                    # bytes; below this, think before spending more


def read(rel):
    return open(os.path.join(REPO, rel), encoding="utf-8").read()


def main():
    fails = []

    def check(ok, what):
        print(f"  {'PASS' if ok else 'FAIL'}: {what}")
        if not ok:
            fails.append(what)
        return ok

    # ---- trainers ----
    opp = read("include/constants/opponents.h").split("#define TRAINERS_COUNT_EMERALD")[0]
    ids = {n: int(v) for n, v in re.findall(r"^#define (TRAINER_\w+)\s+(\d+)", opp, re.M)}
    count, cap = flag_id("TRAINERS_COUNT_EMERALD"), flag_id("MAX_TRAINERS_COUNT_EMERALD")
    print("trainers:")
    check(sorted(ids.values()) == list(range(count)),
          f"trainer ids are unique and run 0..{count - 1} ({len(ids)} defined)")
    check(count <= cap, f"{count} of {cap} trainer ids used: {cap - count} left")
    party = set(re.findall(r"^=== (TRAINER_\w+) ===", read("src/data/trainers.party"), re.M))
    missing = sorted(n for n in ids if n not in party and n != "TRAINER_NONE")
    check(not missing, "every trainer id has a party" + (f" (missing: {missing[:5]})" if missing else ""))

    # ---- flags ----
    print("flags:")
    v = flag_id
    ranges = [("temp", v("TEMP_FLAGS_START"), v("TEMP_FLAGS_END")),
              ("trainer", v("TRAINER_FLAGS_START"), v("TRAINER_FLAGS_END")),
              ("system", v("SYSTEM_FLAGS"), v("DAILY_FLAGS_START") - 1),
              ("daily", v("DAILY_FLAGS_START"), v("DAILY_FLAGS_END")),
              ("Maritimes block", v("MARITIMES_FLAGS_START"), v("MARITIMES_FLAGS_END"))]
    ok = all(a[2] < b[1] for a, b in zip(ranges, ranges[1:])) and v("FLAGS_COUNT") == ranges[-1][2] + 1
    check(ok, "saved flag ranges are in order and don't overlap: "
              + ", ".join(f"{n} {a:#x}-{b:#x}" for n, a, b in ranges))
    check(v("FLAGS_COUNT") <= v("SPECIAL_FLAGS_START"), "saved flags stay below the special flags")
    flags_h = read("include/constants/flags.h")
    block = {n: int(o, 0) for n, o in re.findall(
        r"^#define (FLAG_\w+)\s+\(MARITIMES_FLAGS_START \+ (0x[0-9A-Fa-f]+|\d+)\)", flags_h, re.M)}
    size = v("MARITIMES_FLAGS_COUNT")
    check(len(set(block.values())) == len(block) and all(0 <= o < size for o in block.values()),
          f"Maritimes block: {len(block)} of {size} flags used, each at its own offset: {size - len(block)} left")
    unused = [int(x, 16) for x in re.findall(r"^#define FLAG_UNUSED_0x([0-9A-Fa-f]+)\s+0x", flags_h, re.M)]
    print(f"  info: {sum(1 for x in unused if 0x20 <= x < v('TRAINER_FLAGS_START'))} unused vanilla flags "
          "below the trainer flags (the old pool; new flags go in the block)")

    def where(f):
        for n, a, b in ranges:
            if a <= f <= b:
                return n
        return "general"
    uses = {}
    for path in glob.glob(os.path.join(REPO, "data", "maps", "*", "map.json")):
        j = json.load(open(path, encoding="utf-8"))
        name = os.path.basename(os.path.dirname(path))
        if name.endswith("_Frlg"):                     # FRLG maps aren't built in Emerald mode
            continue
        for o in j.get("object_events", []):
            if o.get("script") == "Common_EventScript_FindItem" and o.get("flag") not in (None, "0"):
                uses.setdefault(o["flag"], []).append((name, "item ball"))
        for b in j.get("bg_events", []):
            if b.get("type") == "hidden_item":
                uses.setdefault(b["flag"], []).append((name, "hidden item"))
    ours = set(block) | set(re.findall(r"^#define (FLAG_\w+)[^\n]*Maritimes: dev/events\.py", flags_h, re.M))
    # our flags set by scripts (gifts): setflag(FLAG_X) in Poryscript, setflag FLAG_X in assembly
    set_by = {}
    for path in glob.glob(os.path.join(REPO, "data", "maps", "*", "scripts.pory")) + \
            glob.glob(os.path.join(REPO, "data", "maps", "*", "scripts.inc")):
        name = os.path.basename(os.path.dirname(path))
        for f in re.findall(r"\bsetflag\(?\s*(FLAG_\w+)", open(path, encoding="utf-8").read()):
            if f in ours:
                set_by.setdefault(f, set()).add(name)
    shared = {f: u for f, u in uses.items() if len(u) > 1}
    both = sorted(f for f in ours if f in uses and f in set_by)
    spread = sorted(f for f, maps in set_by.items() if len(maps) > 1)
    unused = sorted(f for f in ours if f not in uses and f not in set_by)
    check(not any(f in ours for f in shared) and not both and not spread,
          f"each flag dev/events.py allocated belongs to one event ({len(ours)} allocated: "
          f"{sum(f in uses for f in ours)} item flags, {len(set_by)} set by a map's scripts)"
          + (f"; shared: {[f for f in shared if f in ours] + both + spread}" if
             any(f in ours for f in shared) or both or spread else ""))
    if unused:
        print(f"  note: allocated but used by no event (ids never move, so they stay reserved): {unused}")
    if shared:   # vanilla flags on a map cloned from vanilla (initial commit): one pickup hides both
        print(f"  note: {len(shared)} vanilla item flags are shared by a cloned map: "
              + ", ".join(f"{f} ({' + '.join(n for n, _ in u)})" for f, u in sorted(shared.items())[:4]))
    bad = []
    for f, u in uses.items():
        try:
            val = v(f)
        except (KeyError, ValueError) as ex:
            bad.append(f"{f}: undefined ({ex})")
            continue
        kind = where(val)
        if kind in ("temp", "trainer", "system", "daily"):
            bad.append(f"{f} ({u[0][0]}) is a {kind} flag")
        if any(k == "hidden item" for _, k in u) and val < v("FLAG_HIDDEN_ITEMS_START"):
            bad.append(f"{f} ({u[0][0]}) is below FLAG_HIDDEN_ITEMS_START")
    check(not bad, "item flags are defined, saved and permanent" + (f": {bad[:4]}" if bad else ""))

    # ---- save block ----
    print("save block:")
    mp = read("pokeemerald.map")
    m = re.search(r"^\s+0x([0-9a-f]+)\s+gSaveblock1\n\s+0x([0-9a-f]+)\s+\w+", mp, re.M)
    if not m:
        print("  info: couldn't measure SaveBlock1 from pokeemerald.map (the build's STATIC_ASSERT in "
              "src/save.c still enforces the limit)")
    else:
        sb1 = int(m.group(2), 16) - int(m.group(1), 16) - SAVEBLOCK_MOVE_RANGE
        room = SECTOR_DATA_SIZE * SAVEBLOCK1_SECTORS - sb1
        print(f"  info: SaveBlock1 is about {sb1} bytes of {SECTOR_DATA_SIZE * SAVEBLOCK1_SECTORS}: about "
              f"{room} bytes left (8 trainers or 8 flags cost 1 byte; enforced by src/save.c)")
        if room < SAVE_ROOM_WARN:
            print(f"  WARN: under {SAVE_ROOM_WARN} bytes left in SaveBlock1")
    print("PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
