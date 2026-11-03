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
    every block flag was allocated by a tool (dev/events.py: item and gift flags, checked as
    above; dev/save_ids.py: story flags, which any script may set);
  - vars: the story var block (MARITIMES_VARS_*, in SaveBlock3) lies between the vanilla and
    the special vars, its ids are contiguous and allocated by dev/save_ids.py, and
    include/save_layout.h records its size; the unused vanilla vars are printed as a reserve;
  - save block: the room left in each save block, exact: include/save_layout.h records the
    sizes (dev/save_layout.py measures them) and src/save.c asserts them at build time. The
    story vars must lie in the part of SaveBlock3 that every save writes (sectors 0-4).
Prints what's left of each budget. Exit code 1 on any failure.
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mgba_bridge import REPO, flag_id
import save_layout, save_ids

FLASH = save_layout.flash_format()               # include/save.h
SECTOR_DATA_SIZE = FLASH["SECTOR_DATA_SIZE"]
SAVEBLOCK1_SECTORS = FLASH["SECTOR_ID_SAVEBLOCK1_END"] - FLASH["SECTOR_ID_SAVEBLOCK1_START"] + 1
SB3_CHUNK, NUM_SECTORS_PER_SLOT = FLASH["SAVE_BLOCK_3_CHUNK_SIZE"], FLASH["NUM_SECTORS_PER_SLOT"]
SB3_ALWAYS_WRITTEN = FLASH["SB3_ALWAYS_WRITTEN"]  # SaveBlock3 bytes in sectors 0-4: written by every save
SAVE_ROOM_WARN = 64                    # bytes; below this, think before spending more
VARS_WARN = 16                         # story vars left; below this, raise the block or reclaim Hoenn's


def contiguous(offsets):
    n = len(list(offsets))
    return f", at offsets 0..{n - 1} with none shared or skipped" if n else ""


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
    fblock = save_ids.FLAGS.allocated(REPO, flags_h)
    block = {n: o for n, (o, _) in fblock.items()}
    size = v("MARITIMES_FLAGS_COUNT")
    check(sorted(block.values()) == list(range(len(block))) and len(block) <= size,
          f"Maritimes block: {len(block)} of {size} flags used" + contiguous(block.values())
          + f": {size - len(block)} left")
    story_flags = {n for n, (_, c) in fblock.items() if f"Maritimes: {save_ids.TAG}" in c}
    untagged = sorted(n for n, (_, c) in fblock.items()
                      if n not in story_flags and f"Maritimes: {save_ids.EVENTS_TAG}" not in c)
    check(not untagged, f"every block flag was allocated by a tool ({len(block) - len(story_flags)} by dev/events.py, "
                        f"{len(story_flags)} story flags by dev/save_ids.py)"
                        + (f"; by hand: {untagged[:5]}" if untagged else ""))
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
    # event flags (item balls, hidden items, gifts) each belong to one event; story flags are set
    # wherever the story needs them, so only the event flags are checked here
    ours = set(re.findall(rf"^#define (FLAG_\w+)[^\n]*Maritimes: {re.escape(save_ids.EVENTS_TAG)}", flags_h, re.M))
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
    # a story flag (dev/save_ids.py) on an item ball or hidden item would tie the pickup to the story
    misused = sorted(f for f in story_flags if f in uses)
    check(not misused, "no story flag is used as an item ball's or hidden item's flag"
                       + (f": {[(f, [n for n, _ in uses[f]]) for f in misused][:4]}" if misused else ""))
    vanilla_shared = {f: u for f, u in shared.items() if f not in block and f not in ours}
    if vanilla_shared:   # vanilla flags on a map cloned from vanilla (initial commit): one pickup hides both
        print(f"  note: {len(vanilla_shared)} vanilla item flags are shared by a cloned map: "
              + ", ".join(f"{f} ({' + '.join(n for n, _ in u)})" for f, u in sorted(vanilla_shared.items())[:4]))
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

    # ---- vars ----
    lay = save_layout.recorded()
    print("vars:")
    vars_h = read("include/constants/vars.h")
    vblock = save_ids.VARS.allocated(REPO, vars_h)
    voffs = sorted(o for o, _ in vblock.values())
    vsize = v("MARITIMES_VARS_COUNT")
    check(v("MARITIMES_VARS_START") > v("VARS_END") and v("MARITIMES_VARS_END") < v("SPECIAL_VARS_START"),
          f"the story var block {v('MARITIMES_VARS_START'):#x}-{v('MARITIMES_VARS_END'):#x} lies between the "
          f"vanilla vars (..{v('VARS_END'):#x}) and the special vars ({v('SPECIAL_VARS_START'):#x}..)")
    check(voffs == list(range(len(voffs))) and len(voffs) <= vsize,
          f"story var block: {len(voffs)} of {vsize} vars used" + contiguous(voffs) + f": {vsize - len(voffs)} left")
    hand = sorted(n for n, (_, c) in vblock.items() if f"Maritimes: {save_ids.TAG}" not in c)
    check(not hand, "every story var was allocated by dev/save_ids.py" + (f"; by hand: {hand[:5]}" if hand else ""))
    check(lay.get("SAVE_LAYOUT_MARITIMES_VARS_COUNT") == vsize,
          f"include/save_layout.h records the block's {vsize} vars (the build asserts it too)")
    # the script macros read a number in the block's range as a var (compare_var_to_var), so a
    # script comparing a var with such a literal would silently compare it with a story var
    lo, hi = v("MARITIMES_VARS_START"), v("MARITIMES_VARS_END")
    lit = re.compile(r"(?:\bcompare\s+\w+\s*,|\bvar\(\s*\w+\s*\)\s*(?:==|!=|<=|>=|<|>))\s*(0x[0-9A-Fa-f]+|\d+)\b")
    literal = []
    for path in glob.glob(os.path.join(REPO, "data", "**", "*.inc"), recursive=True) + \
            glob.glob(os.path.join(REPO, "data", "**", "*.pory"), recursive=True):
        for m in lit.finditer(open(path, encoding="utf-8", errors="replace").read()):
            if lo <= int(m.group(1), 0) <= hi:
                literal.append(f"{os.path.relpath(path, REPO)}: {m.group(0).strip()}")
    check(not literal, f"no script compares a var with a number in {lo:#x}-{hi:#x} (it would read as a story var)"
                       + (f": {literal[:4]}" if literal else ""))
    free_vars = re.findall(r"^#define (VAR_UNUSED_0x[0-9A-Fa-f]+)\s", vars_h, re.M)
    print(f"  info: {len(free_vars)} of {lay['SAVE_LAYOUT_VARS_COUNT']} vanilla saved vars unused (VAR_UNUSED_*): "
          "a reserve for engine or expansion features that need a SaveBlock1 var; story vars go in the block")
    if vsize - len(voffs) < VARS_WARN:
        print(f"  WARN: under {VARS_WARN} story vars left (raise MARITIMES_VARS_COUNT, or reclaim Hoenn's vars)")

    # ---- save block ----
    print("save block:")
    sb1 = lay["SAVE_LAYOUT_SAVEBLOCK1_SIZE"]
    room = SECTOR_DATA_SIZE * SAVEBLOCK1_SECTORS - sb1
    check(sb1 > 0 and lay["SAVE_LAYOUT_FLAGS_BYTES"] * 8 >= v("FLAGS_COUNT"),
          f"include/save_layout.h is measured (version {lay['SAVE_LAYOUT_VERSION']}) and holds every saved flag")
    print(f"  info: SaveBlock1 is {sb1} of {SECTOR_DATA_SIZE * SAVEBLOCK1_SECTORS} bytes: {room} left; SaveBlock2 "
          f"{SECTOR_DATA_SIZE - lay['SAVE_LAYOUT_SAVEBLOCK2_SIZE']} left (8 trainers or 8 flags cost 1 byte; story "
          "vars are in SaveBlock3, 2 bytes each; dev/save_layout.py re-measures)")
    if room < SAVE_ROOM_WARN:
        print(f"  WARN: under {SAVE_ROOM_WARN} bytes left in SaveBlock1")
    sb3, vend = lay["SAVE_LAYOUT_SAVEBLOCK3_SIZE"], lay["SAVE_LAYOUT_MARITIMES_VARS_OFFSET"] + 2 * vsize
    check(vend <= SB3_ALWAYS_WRITTEN,
          f"the story vars (SaveBlock3+0..{vend - 1:#x}) lie in the part every save writes "
          f"(sectors 0-4: SaveBlock3+0..{SB3_ALWAYS_WRITTEN - 1:#x})")
    print(f"  info: SaveBlock3 is {sb3} of {SB3_CHUNK * NUM_SECTORS_PER_SLOT} bytes: "
          f"{SB3_CHUNK * NUM_SECTORS_PER_SLOT - sb3} left")
    print("PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
