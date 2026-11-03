# PokéMaritimes: saved state and the save format

> Milestone 11 (2026-11-03). How the region's story state is stored, how much room there is, how
> the save format may change, and what each layout version changed. Engine facts with source
> references: `mapping_reference.md` §12–13. Tools: `dev/README.md`.

## Where each kind of state goes

| State | Storage | Allocate with | Room (version 2) |
|---|---|---|---|
| Anything with **stages**: a town's progress, a quest, a rival's arc | a **story var**, `0x4100–0x41FF` (`SaveBlock3`) | `dev/save_ids.py var VAR_<NAME> "values" --apply` | 256 |
| A **yes/no that stays**: a person hidden for good, a one-time event done | a **story flag** in the Maritimes flag block | `dev/save_ids.py flag FLAG_<NAME> "what" --apply` | 766, shared with the row below |
| Item balls, hidden items, gifts | a flag in the same block | `dev/events.py` (automatic, from the map's spec) | |
| A trainer beaten | its trainer flag (one per trainer id) | `dev/events.py` | 520 trainer ids |
| Scratch within one map visit | `VAR_TEMP_0`–`F`, `FLAG_TEMP_1`–`1F` | none | cleared on every map load |
| An engine or expansion feature that needs a var (`B_VAR_*`, `OW_*_VAR` configs) | one of the 23 `VAR_UNUSED_*` in SaveBlock1 | rename it in `vars.h` | 23 (a reserve; e.g. expansion's debug menu only toggles `B_VAR_NO_BAG_USE` when it lies in `0x4000–0x40FF`) |

**Conventions:**
- One var per storyline, counting up: `VAR_HOMETOWN_STATE` 0 = just arrived, 1 = has a starter, 2 = ... (vanilla's `VAR_LITTLEROOT_TOWN_STATE` works this way). Put the meaning of each value in the note; `save_ids.py` writes it beside the id. A var is 16 bits, so one var can carry a whole storyline.
- Flags for things that are only ever set: `FLAG_HIDE_<MAP>_<WHO>` (an object's hide flag), `FLAG_<EVENT>_DONE`.
- Don't pack several things into one var's bits (vanilla's Fan Club does). It's hard to read in scripts and impossible to check with the tools.
- Ids never move and are never reused. A feature that is dropped leaves its id reserved; `id_budget.py` lists event flags nothing uses.

## The budget for a whole region

| | Vanilla Emerald's Hoenn uses | PokéMaritimes has now | Later, when the Hoenn maps are retired |
|---|---|---|---|
| Story vars | about 200 of its 256 (233 are used, counting system vars) | 256 story vars, plus 23 unused vanilla vars as a reserve | Hoenn's story vars become free too |
| Non-trainer flags | about 800: 582 hide flags, 168 item balls, 112 hidden items | 768 in the block (2 used), plus 249 unused vanilla flags | about 800 more |
| Trainer ids | 855 | 520 free | 855 more |

So the region's story can be written at Hoenn's scale without touching the save layout again, and
the Hoenn reclaim stays an option rather than a necessity. Reclaiming has to wait until no vanilla
map or test uses those ids, because a vanilla script that still sets one would corrupt the new
meaning silently.

## Why this design (options weighed in milestone 11)

1. **Grow `VARS_END` in SaveBlock1.** The simplest code: one constant. But SaveBlock1 had only 212
   bytes left (about 100 vars at most), which flags, trainers and expansion's own options also need.
   It also moves every SaveBlock1 field after `vars[]`.
2. **Reclaim Hoenn's vars and flags now.** Free in bytes, but the vanilla maps still serve as tests
   and as the checker's baseline, and a missed vanilla script that sets a reclaimed var is a silent
   bug. Deferred until the Hoenn maps go.
3. **A story var block in SaveBlock3 (chosen).** SaveBlock3 is expansion's extra save block, kept in
   the spare bytes of each flash sector; 1,620 of its 1,624 bytes were free. The block takes 512 of
   them and leaves SaveBlock1 alone. The engine change is small: `GetVarPointer` maps the range, and
   the script macros, the debug menu's var editor and the test framework's script header learn it.
   The one subtlety is that a link or Battle Frontier save rewrites only sectors 0–4. The block is
   SaveBlock3's first field, so it lies in those sectors' chunks and is saved together with the
   flags on every kind of save. `save.c` asserts this, and the in-game test checks a link save and
   the bytes on flash. The other subtlety, found by the code review: expansion's sector checksum
   skipped the chunks, so story vars would have lost the protection vanilla's vars have. The
   checksum now covers them (a flipped story var on flash is refused, in-game test).

The flag block was raised from 256 to 768 in the same version, so that the region's story flags cost
one save break rather than two. That took 64 bytes of SaveBlock1; 148 are left for expansion's options
and any later need.

## The save format (version 2)

- **Flash:** two save slots of 14 sectors (they alternate; the slot with the higher counter loads),
  then the Hall of Fame (2), Trainer Hill (1) and a recorded battle (1). Each 4 KB sector holds
  3,968 data bytes, then a 116-byte SaveBlock3 chunk, then the footer: id, checksum, signature
  `0x08012025` and counter. **The checksum covers the data bytes and, since version 2, the chunk**
  (`CalculateSectorChecksum`; expansion covered only the data, so a damaged SaveBlock3 loaded
  silently). A sector that fails it makes its slot unusable, and the other slot loads instead.
- **Sector 0:** SaveBlock2 (3,884 bytes: the player, options, Pokédex). The **layout stamp**
  `SAVE_LAYOUT_STAMP` = `0x4D00 + SAVE_LAYOUT_VERSION` is at offset 0x16, among vanilla fields, so a
  save of any version can be read for it.
- **Sectors 1–4:** SaveBlock1 (15,724 bytes: location, party, bag, the 3,680 saved flags at +0x1270,
  the 256 vanilla vars at +0x143C, and the rest of the world).
- **Sectors 5–13:** the PC boxes (34,144 bytes).
- **SaveBlock3** (516 bytes), spread over the chunks: the 256 story vars at 0–511 (sectors 0–4), then
  expansion's fields (DexNav chain, and anything its config enables).
- `include/save_layout.h` records the sizes, the offsets of the flag and var arrays and of the story
  block, the block's size, and where each flag range starts. `src/save.c` asserts each number.

## Changing the format

**Doesn't change the layout** (saves keep loading): allocating vars and flags inside their blocks
(`save_ids.py`, `events.py`), adding trainers within the ceiling, any map, script or text change.

**Changes the layout:** raising a block (`MARITIMES_VARS_COUNT`, `MARITIMES_FLAGS_COUNT`,
`MAX_TRAINERS_COUNT_EMERALD`), adding or resizing a SaveBlock field, or an expansion config that does
(`OW_USE_FAKE_RTC`, `FNPC_ENABLE_NPC_FOLLOWERS`, `OW_SHOW_ITEM_DESCRIPTIONS` first-time mode,
`APRICORN_TREE_COUNT`, bag and PC item capacities, ...). The build stops on a `SaveLayoutChanged_*`
assert. Then:
1. `python dev/save_layout.py --update`: it re-measures and bumps `SAVE_LAYOUT_VERSION`.
2. `dev/fastbuild.py`, `dev/tests/ingame_save.py`, `dev/tests/id_budget.py`.
3. Add a row to the history below, and tell Tom that old saves will be refused.

**During development** this is the whole process: a save from another version is refused on load
with "This save is from an older version of the game. Please start a new game.", and NEW GAME
overwrites it.

**Before a public release:** freeze the layout. From then on, a layout change needs a migration
instead of a refusal: read the old stamp (its offset never moves), move the fields to their new
places, then stamp the new version. Released ids must also keep their meaning forever.

## Version history

| Version | Milestone | What changed | Old saves |
|---|---|---|---|
| (none) | up to 8 | Vanilla expansion layout, plus Maritimes data only. | |
| (none) | 9 | Trainer ceiling 864 → 1376; a 256-flag Maritimes block after the daily flags. `flags[]` grew 96 bytes, shifting the rest of SaveBlock1. | Loaded without complaint but with wrong flags and vars: there was no stamp yet. |
| 1 | 10 | The stamp itself (in SaveBlock2's padding) and the layout guard. Same layout as milestone 9. | Unstamped saves refused with the message. |
| 2 | 11 | A 256-var story block first in SaveBlock3 (+512 bytes; expansion's SaveBlock3 fields moved up by 512). The Maritimes flag block 256 → 768 (+64 bytes of SaveBlock1: `vars[]` and every field after `flags[]` moved). Save slot checksums also cover the SaveBlock3 chunk. | Version 1 refused with the outdated message. (A version 1 save whose SaveBlock3 bytes weren't all 0 fails the new checksum instead, and is refused as a damaged save: also a new game.) |

## Known limits

- Expansion's `USE_DEXNAV_SEARCH_LEVELS` needs a byte per species (about 1.7 KB), more than SaveBlock3
  holds even without the story block, so it can't be enabled either way.
- Script macros decide by value whether an argument is a var. A literal between 0x4100 and 0x41FF
  passed to `compare` now reads a story var, as vanilla's macros already do for 0x4000–0x40FF and
  0x8000+. No existing script does it (every script assembles byte-identically before and after the
  change), and `id_budget.py` fails on any script that compares a var with such a number.
