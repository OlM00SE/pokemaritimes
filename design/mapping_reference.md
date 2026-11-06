# How maps work in pokeemerald-expansion 1.17.2 (Emerald mode)

These are notes from reading the engine source. Every rule cites where it comes from. They're encoded in `dev/mapkit/engine.py` and verified against the real game: `dev/tests/conformance.py` matched 482/482 single steps across 13 maps, and `dev/tests/ingame_ledges.py` matched every approach to every ledge on LedgeLab and four vanilla routes (378/378).

## 1. Data on disk
| File | Contents |
|---|---|
| `data/layouts/layouts.json` | Per layout: `width`, `height`, `primary_tileset`, `secondary_tileset`, and paths to `border.bin` and `map.bin`. |
| `data/layouts/<L>/map.bin` | One u16 per block, row-major. **Bits 0–9: metatile id. 10–11: collision. 12–15: elevation.** |
| `data/layouts/<L>/border.bin` | A 2×2 block pattern tiled outside the map (Emerald). It is always impassable. |
| `data/maps/<M>/map.json` | Header (music, weather, map type, region-map section, flags), `connections`, and events: `object_events`, `warp_events`, `coord_events`, `bg_events`. |
| `data/maps/map_groups.json` | Map groups. The group/num pair is the map's runtime id. |
| `data/tilesets/{primary,secondary}/<t>/` | `tiles.png` (indexed 4bpp), `palettes/NN.pal`, `metatiles.bin`, `metatile_attributes.bin`. |

## 2. Tilesets and metatiles (`include/fieldmap.h`)
- Primary tilesets hold metatiles 0–511, tiles 0–511, and palettes 0–5. Secondary tilesets hold metatiles 512–1023, tiles 512+, and palettes 6–12.
- Every map uses one primary and one secondary tileset.
- A metatile is 16×16 px, made of **8 tile entries**: 4 for the bottom layer and 4 for the top layer (order TL, TR, BL, BR).
  - Entry bits: 0–9 tile, 10 hflip, 11 vflip, 12–15 palette.
- `metatile_attributes.bin` stores one u16 per metatile: bits 0–7 are the **behavior** (`MB_*`) and bits 12–15 the **layer type**.

## 3. Layer types (`src/field_camera.c` DrawMetatile)
| Type | Bottom layer goes to | Top layer goes to | Effect |
|---|---|---|---|
| NORMAL | BG2 (middle) | BG1 (top) | The top layer covers sprites (tree tops, roofs). |
| COVERED | BG3 (bottom) | BG2 (middle) | Both layers are under sprites. |
| SPLIT | BG3 (bottom) | BG1 (top) | Nothing is drawn in the middle layer. |

## 4. The grid the engine walks on (`src/fieldmap.c`)
- The map is copied into a buffer with a **7-tile margin** on every side (`MAP_OFFSET`).
  - Size limit: **(w+15)·(h+14) ≤ 10240** (`MAX_MAP_DATA_SIZE`).
- **Connections** copy a 7-tile strip (8 on the east side) of the neighbouring map into that margin (`Fill*Connection`).
  - The player sees, and walks on, the neighbour's real blocks.
  - So the visual and walkability seams between two maps are exactly what is on their edges.
- A margin cell with no connection is undefined: you see the border pattern and can't move there (`GetMapBorderIdAt` returns `CONNECTION_INVALID`).
- Connections must be reciprocal: A→B with offset *o* needs B→A in the opposite direction with offset −*o*.

## 5. Movement rules (`event_object_movement.c` GetVanillaCollision, `field_player_avatar.c`)
A step from tile A to tile B is **blocked** if any of these hold:
- B's collision bits are non-zero, or B is undefined.
- A directional block applies (`IsMetatileDirectionallyImpassable`):
  - leaving A in direction *d* when A is "*d*-blocked", or
  - entering B when B is blocked on its opposite side (`MB_IMPASSABLE_*`).
- **Elevation mismatch** (`IsElevationMismatchAt`): the player's *current* elevation `e` isn't 0, B's elevation isn't 0 or 15, and B's elevation ≠ `e`.

Special cases, checked in this order (`CheckForObjectEventCollision`):
1. **Stop surfing:** while surfing, a mismatch onto an elevation-3 tile lands the player (`CanStopSurfing`).
2. **Ledges:** if B's behavior is `MB_JUMP_<d>` in the movement direction, the player jumps two tiles, **even if B's collision is set**.

Elevation bookkeeping (`ObjectEventUpdateElevation`):
- If the new or the old tile is 15 (bridge / multi-level), nothing changes.
- Otherwise `currentElevation` = the tile's elevation, and `previousElevation` follows it unless the tile is 0.

**Water** is not blocked by its behavior. Water tiles sit at **elevation 1**, land at **3**, and Surf puts the player at 1. So water painted at elevation 3 (or 0) is walkable, which was a real bug in six of our maps.

## 6. Events (`field_control_avatar.c`)
- Every event (warp, coord trigger, bg/sign) fires only if `event.elevation == 0` or `event.elevation == the player's previousElevation` (`PlayerGetElevation`).
  - Facing checks use 0 when the player stands on a transition (elevation-0) tile (`GetInFrontOfPlayerPosition`).
- **Warps** trigger in three ways:
  - **Stepping onto** a tile with a warp behavior (`IsWarpMetatileBehavior`): ladders, escalators, non-animated doors, special warps.
  - **Pressing north into** an animated door (`TryDoorWarp`): the warp sits on the door tile, and the player stands below it.
  - **Pressing the arrow's direction** while standing on an arrow mat or directional stairs (`TryArrowWarp`).
  - A warp on any other tile is **arrival-only**: you can land on it, but walking onto it does nothing.
- Landing on a door or arrow tile makes the player step out of it. Arriving on an animated door (`MetatileBehavior_IsDoor`), the game walks the player one tile **down** (`field_screen_effect.c` SetUpWarpExitTask → Task_ExitDoor). A non-animated door walks them on in the direction they face. The checker starts door arrivals below the door. Starting on the door tile itself made walkable roof tiles above some doors look reachable (Routes 110 and 111).
- Encounter tiles and surfable water come from `sTileBitAttributes` (`TILE_FLAG_HAS_ENCOUNTERS`, `TILE_FLAG_SURFABLE`) in `metatile_behavior.c`.

## 7. How vanilla builds terrain (mined from 238 vanilla layouts on gTileset_General)
- **Trees are 2×2 metatiles.**
  - Top-left `1D4/1D6`, top-right `1D5/1D7`.
  - Bottom-left `1DC/1E4/1E6/1F3`, bottom-right `1DD/1E5/1E7/1F2`.
  - The bottom variant depends on what's below: another tree, ground, or a corner.
  - Canopies overhang the grass tile above, which uses `1CE/1CF`.
  - Trees are solid (collision 1, elevation 0). Vanilla never makes a tree walkable.
- **Water** is elevation 1, collision 0.
  - Pond family: `0A1` with `0B0–0D2` edges.
  - River/sea family: `170`, `189`, `190`, `192`, …
  - The bottom bank is drawn on the *land* tile below (`002`).
  - `0D1` looks like pond water but is `MB_PUDDLE`, which you walk through.
- **Paths:** two 3×3 families. Light path `1D0–1E2`, sand/dirt `118–12A`.
- **Grammar:** vanilla keeps a grass margin between water and tall grass, paths, or the sand patch. Sand never touches trees. Beaches use their own sand family (`124`, with `11B–12D` edges; section 10).

## 8. Ledges (engine source, plus 238 vanilla layouts; encoded in `dev/mapkit/ledges.py`)
**Movement:**
- **A jump needs only the behavior.** Moving in direction *d* into a tile whose behavior is `MB_JUMP_<d>` jumps two tiles. The ledge tile's collision is ignored (`field_player_avatar.c` CheckForObjectEventCollision → ShouldJumpLedge → `event_object_movement.c` GetLedgeJumpDirection).
- **The landing tile is never checked.** A ledge that drops onto a tree, rock or water is a real bug. `mapgen` refuses such sketches, and `check_maps.py` reports `ledge`.
- **Only four behaviors jump.** The predicates `MetatileBehavior_IsJump{North,South,East,West}` each match exactly one behavior. `MB_JUMP_SOUTHEAST/SOUTHWEST` (on the corner tiles) match none, so corners are plain solid tiles.
- **Elevation during a jump.** The jump first moves the player's coordinates onto the ledge tile, then to the landing at the halfway point (InitJump, then UpdateJumpAnim → ShiftObjectEventCoords). So the landing's "previous" tile is the ledge tile, and elevation bookkeeping uses the ledge and landing tiles. `engine.py` already did this; `tests/ingame_ledges.py` confirms it, elevations included.

**Pieces** (`gTileset_General`). All are collision 1. Elevation is 0 in 66% of vanilla uses (345/525) and 3 in the rest; a rebuilt map keeps a ledge cell's existing elevation.
| Piece | Ids |
|---|---|
| Row (jumps south) | `0D5` left end, `087` middle, `0D6` right end |
| West column (jumps west) | `0FE` top, `085` middle, `106` bottom |
| East column (jumps east) | `0FF` top, `086` middle, `107` bottom |
| Corners (solid) | `08D` west column above, row going east (a plateau's south-west corner) |
| | `08E` east column above, row going west |
| | `06F` row from the west, west column below |
| | `06E` row from the east, east column below |

- `06F` over `08D` makes a one-tile stair step down to the east (Route 103). `06E` over `08E` steps down to the west (Route 101).
- There are no north-facing ledges in this tileset.
- **Ends.** Next to ground or trees, a ledge end always gets a cap (83/83). At the map edge, the middle piece runs off the map (4/4). Against a secondary-tileset cliff or wall, it runs under it (35/35). Against a primary object such as a boulder, it gets a cap (26/29).
- **Not modelled.** Route 118's mountain terraces and five other ledge-meets-cliff joints use cliff tiles (`070/071`, secondary cliffs). They're future vocabulary. Our own ledges meet our cliffs by running under the wall, no cap (§16).

## 9. One-way traps (`checks.check_traps`)
**How the check works:** ledges make one-way moves, so the checker builds the full movement graph from every entrance (on foot) and finds tiles that can be reached but can't reach a way out.

Ways out:
- a connection edge;
- any warp's trigger position;
- a dev map's spawn point (checks.spawn_point: the only warp, to MAP_DYNAMIC, on a map with no connections). Other arrival-only tiles, such as fly targets, scripted arrivals and Route 115's Terra Cave holes, never count.

**Vanilla result:** exactly one real trap, the ledge pocket in `ShoalCave_LowTideEntranceRoom`. All 50 moves out of it were confirmed blocked in mGBA. Escape Rope or Dig gets the player out.

## 10. Shores (mined from 238 vanilla layouts; encoded in `dev/mapkit/shores.py`)
**Structure.** Where river/sea water (`170` family) meets land, the edge along the water's north, east and west sides is drawn on the **water** tile. The edge along its south side is drawn on the **land** tile below. `gTileset_General` has this structure in two materials, which share one shape table:

| Shape (for a water cell, unless noted) | Grass bank | Beach |
|---|---|---|
| land N | `189` | `12C` |
| land W / E | `190` / `192` | `125` / `123` |
| land N+W / N+E (corner) | `188` / `18A` | `146` / `145` |
| land E, water NE (top end of a side bank) | `178` | `11B` |
| land W, water NW | `179` | `11D` |
| land NW only / NE only (inner corner) | `198` / `19A` | `12D` / `12B` |
| land cell, water N | `002` (`1E8`/`1E9` with a tree below) | `11C`; `13D` if NE is land, `13E` if NW is land |
| open water | `170` | `170` |

`180`/`181` are the same corners against rock rather than grass. Water rocks are 2×2 (`150 151 / 158 159`, solid, elevation 0 or 1) and draw their own edge.

**How well the table fits vanilla.** Take every vanilla cell where water meets only grass-like land or beach sand. The table rebuilds 99.9% of them (25,556/25,589): all 265 beach-sand edges, all 73 grass banks, and the water pieces apart from 33 one-off variants (e.g. `190` where the shape says `179`). This is `tests/shore_pieces.py`.

**Shapes with no tiles.** No piece has both side banks, so water must be at least two wide. There is no mixed bank/beach corner. A water cell can't carry a side bank and the opposite inner corner at once. The compiler refuses these shapes.

**Attributes and movement.** Water pieces sit at elevation 1 with collision 0. Beach sand (`124`, `11C`, `13D`, `13E`; `MB_SAND`) and grass sit at elevation 3. Stepping from land toward water is an elevation mismatch, so on foot it's blocked, and facing water with Surf offers the field move. Surfing toward elevation-3 land comes ashore (`CanStopSurfing`). Warping onto water starts the player surfing. `tests/ingame_shores.py` checks every land/water edge of ShoreLab and Route 203 against this model: bump, landing, rock, and Surf through the prompt.
## 11. Forests, open ground and flora (mined from 238 vanilla layouts; encoded in `dev/mapkit/flora.py` and `landscape.py`)
**Flora pieces on `gTileset_General`.**
| Piece | Tiles | Attributes | Vanilla use |
|---|---|---|---|
| Flowers | `004` | walkable, elevation 3 (66%; 0 in towns) | 615 tiles. Mostly singles (268 of 328 beds), the rest beds of 2–12. About half stand within 4 tiles of a tree. |
| Boulder on grass | `0E0` (`0E1` on dirt, `0E2` on sand) | solid, elevation 3 or 0 | 101 tiles, mainly the Safari Zone, Routes 111 and 123. A third stand right against a tree. |
| Sapling (Route 116, 110) | `00E` crown top / optional `0C6` crown middle / `017` trunk | crown top walkable (`MB_NORMAL`, elevation 3; the player passes behind it); middle and trunk solid | Route 116's young grove. The trunk always has open ground below. |

Not used:
- `0C6`/`0C7` over `016`/`017`, stacked 3–6 tall, are Route 119/120's jungle hedges. Saplings tucked under a tree's canopy (a `1EC`/`1ED` tree bottom over `0C6`) are not used either. Both stay `#`.
- `0CE` is a cliff-top shrub: its neighbours are mountain tiles.
- `14B–14D` / `113–115` is berry-tree soil, which is functional, not decoration.
- The `101`/`108–111` "decorations" the vocabulary found are Route 113's ash grass.

Each flora tile's most common neighbour is plain grass `001` (or another flora tile), so the compiler treats flora as grass for the learned rules. It refuses a piece where grass would get an edge tile (the `1CE`/`1CF` canopy overhang above a tree, the `002` bank below water, a path rim). `tests/flora_pieces.py` runs on 16 vanilla maps. Extract rebuilds 103/190 flower tiles, 23/52 boulders and 31/56 saplings in this form exactly, neighbours included. The rest stay `#` for one of three reasons:
- an unusual elevation (flowers at elevation 0 in towns);
- a spot that isn't plain grass;
- a neighbour vanilla drew with the object in mind. Examples are a crown top `00E`/`00F` of a jungle-form sapling beside the piece, or a tree-bottom variant next to a Safari Zone boulder.

Reading the piece as grass would change that neighbour, so extract keeps the piece. 995 trunks belong to the jungle forms.

**Forest edges.** About 10% of vanilla's tree joins are offset by one tile (124 sideways, 122 vertically, against 1,359 aligned each way), almost all on a forest's edge. The `1E4/1E6/1F3` and `1E5/1E7/1F2` bottom variants exist for these joins. Interiors stay on one 2×2 grid. Natural-looking edges step every one to three trees, in bays, headlands and diagonal staircases. Lone trees and pairs stand one or two tiles out. Tall grass comes in irregular patches with stray single tufts at the fringe (Route 116).

**Sign posts.** Vanilla's route sign is `003` (solid; 103 of 117 at elevation 0), a one-tile piece on plain grass like the flora: sketch `s`. On the 16 flora test maps extract rebuilds 35/48 exactly. Its text is a `sign` bg event on the same tile (§12).

**Tiling.** A sketch drawn as whole, non-overlapping 2×2 trees always tiles back tree for tree. The first forest cell in reading order must be some tree's top-left, so the tiling is unique. `landscape.plant` only ever draws such trees. A tree may run off the map's right or bottom edge, as vanilla's do, but never off the left or top: there the greedy tiler would pair the cut tree's cells with the next tree's.
## 12. People, signs, items and the id budget (engine source; encoded in `dev/mapkit/events.py`, verified in-game by `tests/ingame_events.py`)
- **People block.** An object on the target tile is `COLLISION_OBJECT_EVENT` (`GetCollisionAtCoords`), checked after the tile's own collision and elevation, and only if the two elevations are compatible (`AreElevationsCompatible`: equal, or either is 0), so a person on a bridge doesn't block the path below. A ledge jump is tested first (`CheckForObjectEventCollision`), so a person on a ledge tile doesn't stop the jump. `CanStopSurfing` refuses a shore tile with a person at elevation 3 (or 0) on it.
  - **An object's elevation is its tile's**, not its template's: every frame `ObjectEventUpdateElevation` sets it to the elevation of the tile it stands on, unless that tile is multi-level (15), where the template's stays. Confirmed in-game: Safari Zone South's exit attendant has elevation 4 in `map.json` but stands on elevation-3 ground, and blocks a player walking north at elevation 3. Blocking, talking and sight all use this effective elevation (`events.object_elevation`).
  - Facing-only movement types (`FACE_*`, `LOOK_AROUND`, in-place animations) never leave home, whatever `movement_range_x/y` says (vanilla gives some a range of 1). Wanderers and walkers stay inside their range box.
  - Objects with a hide flag (`flag` other than `0`) come and go with the story: item balls, story blockers. The checker and the route numbers only count permanent people (flag `0`), at home. The walker plans around everyone present, wanderers' whole box.
  - **Wanderers** (`MOVEMENT_TYPE_WANDER_AROUND`) step to any tile of their range box that `GetCollisionAtCoords` allows (`IsCoordOutsideObjectEventMovementRange` keeps them in), and they stop and face the player while talked to. Nothing stops one on a door mat or in a corridor for a while: vanilla's house wanderers do it (Fortree House 3, Route 119's house, the Abandoned Ship). The checker tries the wanderer on every tile of its range and warns about any exit it can cut off. Verified in-game: Woodstock's child, range 2×2, stood on 12 tiles of its 5×5 box in 30 seconds and never left it.
  - **A range of 0 means no limit on that axis**, not "stays in its row": `IsCoordOutsideObjectEventMovementRange` only checks an axis whose range isn't 0. Found in-game: a HomeTown wanderer given range 2×0 walked off its row. Vanilla's zeros are almost all on the axis a type never moves along (`WANDER_LEFT_AND_RIGHT` with `range_y` 0, `WALK_UP_AND_DOWN` with `range_x` 0); only three vanilla `WANDER_AROUND`s are really unbounded on one axis. `events.wander_box` spans the map on such an axis (copy-player types, which mirror the player's steps, keep their box with a 0 axis taken as home: not modelled), and the spec tool refuses a 0.
  - **Item balls** are objects with `OBJ_EVENT_GFX_ITEM_BALL`, script `Common_EventScript_FindItem`, the item in `trainer_sight_or_berry_tree_id` and a flag in `flag`. Picking one up runs `finditem` (`data/scripts/obtain_item.inc`), which gives the item and then `removeobject`, which sets the object's flag so it stays gone. Verified in-game (Woodstock): the bag gains the item, the flag is set, and the ball is gone.
- **Talking** (`GetInteractedObjectEventScript`): the object on the tile in front of the player, if its elevation matches (`ObjectEventDoesElevationMatch`: equal, or either is 0). If that tile is a counter (`MetatileBehavior_IsCounter`), the engine looks one tile further.
- **Signs and hidden items** (`GetInteractedBackgroundEventScript`): the bg event on the tile in front, if its elevation is 0 or equals the player's (`GetInFrontOfPlayerPosition`, §6). A sign's `player_facing_dir` can require one facing. A hidden item whose flag is set does nothing. Its flag must be ≥ `FLAG_HIDDEN_ITEMS_START` (0x1F4): the bg event stores `flag - start` (`bg_hidden_item_event`, `asm/macros/map.inc`), so any saved flag from there up works, within a 13-bit offset (`hiddenItemId:13`; a static assert in `event_data.c` checks every saved flag fits). Daily flags are cleared every day (the item would come back), and temp flags (0x00–0x1F) on every map load, so neither may be used.
- **Trainer sight** (`trainer_see.c`): a `TRAINER_TYPE_NORMAL` trainer sees straight ahead in the direction it faces (all four for `LOOK_AROUND` and `SEE_ALL_DIRECTIONS`), up to `trainer_sight_or_berry_tree_id` tiles. Every tile between it and the player must be passable *for the trainer* (`CheckPathBetweenTrainerAndPlayer`: tile collision, a directional block judged from the trainer's own tile, elevation against the trainer's elevation, other people), and the player's tile too. So sight stops at the first solid tile, ledge, person or elevation change. It is checked as the player steps (`PlayerGetDestCoords`), not on warp arrival.
- **Trainer ids and the flag layout** (`opponents.h`, `flags.h`, `global.h`). Each trainer id `n` is also the saved flag `TRAINER_FLAGS_START + n` (0x500 + n), and the ranges are chained: `TRAINER_FLAGS_END = 0x500 + MAX_TRAINERS_COUNT - 1`, the system flags follow, then the daily flags, and `FLAGS_COUNT` sizes `SaveBlock1.flags[]`. Vanilla Emerald used 855 of 864 ids, so 9 were free. Milestone 9 raised `MAX_TRAINERS_COUNT_EMERALD` to 1376 and appended a 256-flag Maritimes block (`MARITIMES_FLAGS_START`, after the daily flags). Now the trainer flags run 0x500–0xA5F, the system flags start at 0xA60, the daily flags at 0xB20, and the block covers 0xB60–0xE5F (768 flags since milestone 11; 256 before). The `FLAG_UNUSED_0x8xx`/`0x9xx` names keep vanilla's numbers but no longer equal them.
  - **Cost:** 1 save byte per 8 trainers or flags. `sizeof(SaveBlock1)` went from 15,564 to 15,660 bytes of 15,872 (`gSaveblock1` in `pokeemerald.map` minus its 128-byte ASLR pad). `flags[]` sits in the middle of SaveBlock1, so any change to the flag count moves the fields after it and old saves stop loading correctly.
  - **Nothing else is keyed to the numbers:** trainer ids are `u16` in battle parameters; partners are `MAX_TRAINERS_COUNT + n` (symbolic); special opponents sit at 0xFF00+; frontier trainers have their own id space; `GetFlagPointer` only splits at `SPECIAL_FLAGS_START` (0x4000), so a static assert keeps `FLAGS_COUNT` below it. The one thing sized by the ceiling was the trainer-slide table (`sTrainerSlides`, 312 bytes per id: about 160 KB of empty ROM at 1376). It is now sized by `TRAINERS_COUNT`, with partner entries at `TRAINER_SLIDE_PARTNER(p)`. Verified in-game by `tests/ingame_save.py`: flags at both ends of each range survive save, reset and CONTINUE.
- **Vanilla calibration:** with these rules the checker finds no new errors on the 939 vanilla maps except one explained case: Safari Zone South's exit attendant stands below the exit door and blocks it (you leave through their script). Lavaridge Gym's buried trainers aren't modelled as blockers. **Testing note:** with no badges, a Pokémon above level 10 may disobey ("began to nap"), so a test that fights must give its Pokémon the eighth badge flag, not just a high level. Swimmers are talkable only with Surf (INFO). Routes 132–134's swimmers sit in currents, which the model doesn't cover. Route 117's twin trainers stand in the fence gap to the Day Care garden.

## 13. Saves and the layout version (`src/save.c`, `include/save_layout.h`; verified in-game by `tests/ingame_save.py`)
- **What a save is:** two slots of 14 flash sectors (SaveBlock2, SaveBlock1 in 4 sectors, the PC in 9), each sector 3,968 data bytes, a 116-byte SaveBlock3 chunk (expansion's extra block lives in the footers), then `id`, `checksum` (over the data only), `signature` 0x08012025 and `counter`. The slot with the higher counter loads. Nothing in vanilla records the *layout*: a save written with other struct sizes passes every check and is copied byte for byte into the new structs. That is how milestone 9's flag growth broke old saves silently (shifted flags and vars, no starter, lost badges).
- **The stamp:** SaveBlock2 had 2 bytes of padding at 0x16 (after the options bitfield, before the 4-aligned Pokédex). It is now `saveLayoutVersion`, set to `SAVE_LAYOUT_STAMP` (0x4D00 + version: never 0, never 0xFFFF) on every path that writes SaveBlock2 (`HandleSavingData`, `LinkFullSave_Init`, `WriteSaveBlock2`). Its offset depends only on vanilla fields, so it can be read from a save of any version. `LoadGameSave` treats a save with another stamp as erased (`SAVE_STATUS_CORRUPT`, so the intro resets the options and RTC as for any unusable save) and sets `gSaveFileOutdated`; the main menu then says "This save is from an older version of the game. Please start a new game." and offers NEW GAME and OPTION only. Saving the new game overwrites the old slots. Unlike vanilla's CORRUPT, the refused save's slot counter is kept, so the new game's first save out-counts both stale slots and is the one that loads.
- **The guard:** `include/save_layout.h` records, for the current version, the sizes of SaveBlock1/2/3 and the PC, the offsets of `flags` and `vars` and their sizes, and where the trainer, system, daily and Maritimes flag ranges start (moving a range inside an unchanged `flags[]` would re-point old saves' flags). `src/save.c` asserts each one, so a change to the layout (a range raised, a field added, an expansion config that resizes a block) fails the build until `dev/save_layout.py --update` re-measures and bumps the version. The tool compiles a throwaway probe with the build's own compiler (the ELF has no debug info). Not covered: a reordering that keeps every recorded size and offset (no workflow here does that), and the Hall of Fame / Trainer Hill / recorded-battle sectors, whose formats nothing here changes.
- **SaveBlock3 on flash:** each sector's footer holds a 116-byte chunk (`saveBlock3Chunk`, after the 3,968 data bytes), so SaveBlock3 byte *b* lives in sector *b* / 116 (`CopyFromSaveBlock3`/`CopyToSaveBlock3`). The chunk is written and read with its sector. Expansion's sector checksum covered only the data bytes; since milestone 11 (`CalculateSectorChecksum`) a save slot sector's checksum also sums its chunk's words, so a damaged chunk makes the slot unusable like damaged data (the Hall of Fame sectors keep vanilla's checksum). A torn write is caught by the signature, which is written last. Normal saves write all 14 sectors; `SAVE_LINK` (link rooms, the Battle Frontier between battles) and `WriteSaveBlock2`/`WriteSaveBlock1Sector` rewrite only sectors 0–4 in place, so chunks 5–13 keep what the last full save wrote. `NewGameInitData` clears SaveBlock3 (`ClearSav3`).
- **Vars** (`GetVarPointer`, `src/event_data.c`): 0x4000–0x40FF are `SaveBlock1.vars[]` (0x4000–0x400F are the temp vars, cleared on every map load); **0x4100–0x41FF are the Maritimes story vars, `SaveBlock3.maritimesVars[]`** (milestone 11); 0x8000+ are the special vars (RAM, not saved). Any other id below 0x8000 isn't a var: `VarGet` returns the id itself and `VarSet` fails (vanilla pointed it past `vars[]` into the next SaveBlock1 field). The story block is SaveBlock3's first field, so it occupies bytes 0–511, inside the 580 bytes of sectors 0–4: it is written by every kind of save together with the flags (`save.c` asserts it; `tests/ingame_save.py` checks a link save and the bytes on flash). Script macros decide by value whether an argument is a var (`compare`, and `setvar`/`copyvar`'s warnings, `asm/macros/event.inc`); they know the block (`tests/var_macros.py`), and every existing script assembles byte-identically with the change.
- **Room (version 2, milestone 11):** SaveBlock1 15,724 of 15,872 bytes (148 left), SaveBlock2 3,884 of 3,968 (84), SaveBlock3 516 of 1,624 (1,108), PC 34,144 of 35,712. 3,680 saved flags (460 bytes; the Maritimes flag block is 768 of them), 256 vanilla saved vars (23 still `VAR_UNUSED_*`) and 256 story vars. The plan and the version history: `design/save_format.md`.

## 14. Buildings, doors and the rooms behind them (engine source and vanilla maps; encoded in `dev/mapkit/stamps.py`, `interiors.py`, `buildings.py`; verified in-game by `tests/ingame_doors.py` and `tests/ingame_buildings.py`)
- **A building is a rectangle of metatiles.** The Pokémon Center (`048`–`063`), the Mart (`028`–`043`, sharing the Center's `060` corner), the Gym (`1AA`–`1CD`) and a small red-roofed house in two widths (`008`–`022`) are in `gTileset_General`, so they work on every General map; Littleroot's two-storey houses and lab, Oldale's brown-roofed house and Petalburg's wide house use `gTileset_Petalburg` tiles (ids ≥ 0x200). The canonical Mart roof row is `028 029 029 02B` (Slateport, Mauville). Rustboro's buildings (Fredericton's set) stand on paved ground with drop shadows drawn into the neighbouring tiles; they aren't stamps yet.
- **The roof's top row is walk-behind:** collision 0, elevation 3, its tiles drawn over the player, so you can walk behind a building's top edge. Vanilla blends this row with whatever stands behind it: Oldale's Center (`282`/`283`) and Mart (`285`) and Petalburg's Mart (`250`/`251`, `258`/`259`, solid) have a tree's foot in their roof tiles, and Wally's house a hedge (the row made solid). The solid cells below never vary, so they identify a building (`stamps.recognise`): every door on Littleroot, Oldale and Petalburg, every Center and Mart on General maps, and every building on HomeTown and Woodstock (37 vanilla doors in all).
- **Doors** (`field_control_avatar.c` `TryDoorWarp`): a door tile (`MetatileBehavior_IsWarpDoor`) works only with a warp event on it, and only for a player standing on the tile below pressing north. Arriving through it, the player is put on the door and walked one tile south by script, ignoring collision (`Task_ExitDoor`). Littleroot's doors have a mat below them (`201`, walkable, a Petalburg tile); it belongs to the building.
- **Interiors** are indoor maps with their own tilesets (any interior can stand behind any facade). The outdoor door's warp names one of the room's warps by index (`dest_warp_id`); the room's exit warps (two, on the mat) name the outdoor warp by index. So a building moved in a redesign keeps its room by moving its warp's x, y and nothing else: no index changes. A copied room must lead only to its own door, its other floors, or a shared room (below).
- **The Center's escalator** (`LAYOUT_POKEMON_CENTER_1F`, (1,6)) is `MB_UP_ESCALATOR` at elevation 4, a step-on warp. It is boarded from the elevation-0 tile to its right: from below (elevation 3) the step is refused, because a step can change elevation only through 0 or 15.
- **Shared rooms:** every Center's upstairs warps to `MAP_UNION_ROOM` and `MAP_TRADE_CENTER`, whose exits are all `MAP_DYNAMIC` (back where you came from), so one pair serves every Center. The attendants run `Common_EventScript_*` and the floor's map scripts are `CableClub_On*`; they address the attendant through `VAR_0x8007`/`VAR_LAST_TALKED`, not a fixed local id, so a copy keeps them as they are. The Mystery Gift man has a hide flag of his own and isn't copied.
- **The respawn point.** Entering a Center runs `setrespawn HEAL_LOCATION_X` (its `ON_TRANSITION` map script), which stores the heal location as warp data, `{group, num, warpId −1, x, y}` (the tile outside the door), in `SaveBlock1.lastHealLocation` (offset 0x1C). A whiteout looks that warp data up again (`GetHealLocationIndexByWarpData`) to find the room to respawn in (`respawn_map`, at (7,4) by default) and the nurse who greets you (`respawn_npc`, a local id). Heal locations live in `src/data/heal_locations.json` (the build generates the id enum and tables); ids are positions, so new ones are appended. Because the save holds the position, not the id, a Center that moves leaves a save made at the old spot unmatched: its whiteout falls back to the old outdoor spot. Verified in-game: TownLab's Center set the warp data to its heal location, and again after the Center moved two tiles.
- **The nurse** is `setvar VAR_0x800B, <her local id>` then `call Common_EventScript_PkmnCenterNurse`. A local id is the object's position in `object_events` (index + 1), so she stays first; `events.py` keeps her as a hand-placed event and appends its own people after her. Talked to across the counter (the engine looks past a counter tile), she heals the party (TownLab: 1 HP to full).
- **The Mart's clerk** says `gText_HowMayIServeYou` ("Welcome!", then "How may I serve you?") and runs `pokemart <list>`; Poryscript writes the list as a `mart` block. Verified in-game: buying a Poké Ball for ₽200.
- **Tiling around a building:** to the learned terrain rules a building is just "a kept tile" (class F), shared with fences, signs and steps, so its neighbours used to copy whatever vanilla drew beside any object (grey steps showed up beside TownLab's buildings). Vanilla's buildings stand on plain grass, so the compiler shows a stamp to the rules as grass. Extract → compile with stamps matches the original at least as well as keeping the buildings' cells as `#` does: the same on Littleroot, Oldale, HomeTown and Woodstock, better on Petalburg (95.9% vs 95.3%) and TownLab (100% vs 99.0%).
## 15. Bridges, tilesets and saves on redesigned maps (engine source and vanilla maps; encoded in `dev/mapkit/bridges.py`, `tileimport.py`, `src/overworld.c`; verified in-game by `tests/ingame_bridges.py` and `tests/ingame_world_revision.py`)
- **No bridge in General or Petalburg.** Every vanilla bridge piece sits in a secondary tileset: Route 110's in Mauville (`MB_BRIDGE_OVER_OCEAN` at elevation 4 or 15, which a surfer passes under), Routes 119/120 and Fortree's in Fortree (`MB_BRIDGE_OVER_POND_*`, `MB_FORTREE_BRIDGE`), Route 104's plank bridge in Rustboro. A map has one secondary tileset, so a General + Petalburg town borrows a piece by copying it in (`tileimport`): appended tiles, an empty palette slot, appended metatiles, nothing moved.
- **Route 104's deck** (`34E`/`34F`, the north end `350`/`351` over the water row that carries the bank) is planks drawn over General water tile 270 in Rustboro palette 11, opaque from edge to edge, layer type 1. It is `MB_REFLECTION_UNDER_BRIDGE` (in `MetatileBehavior_IsReflective`: a player on the deck is mirrored in the planks below), collision 0, elevation 3. So it's ordinary ground at the land's elevation: walked from the grass at either end, refused from the water on either side (elevation 1 against 3; on foot, the water needs Surf). Route 104 puts plain grass `001` under the south end where the bank `002` would be.
- **Animation frames live past a tileset's PNG:** Petalburg's metatiles `24A`/`24B` point at tiles 800-819, which its 160-tile `tiles.png` doesn't hold; the animation writes them. Appended tiles must stay below such indices.
- **What a save remembers about the map it stands on** (`SaveBlock1`): the position (`pos`, `location`), the map's objects with their positions (`objectEvents`; CONTINUE restores them, `LoadSaveblockObjEventScripts` only refreshes their scripts), and `mapView`, the 15x14 metatiles around the player when saving, which `LoadSavedMapView` pastes back over the grid on CONTINUE and then clears (so it always reads empty after a CONTINUE). The grid includes the connected maps' strips: a save on Route 201 beside Woodstock's seam pasted 64 cells of old Woodstock over the new one in the negative control, and Woodstock's old cliff and steps appeared in the new town from a save on it. Also warp data with coordinates: `continueGameWarp`, `dynamicWarp`, `escapeWarp`, `lastHealLocation`; a warp with a valid `warpId` uses the warp's position instead (`SetPlayerCoordsFromWarp`), so warps by id survive a redesign that keeps warp indices.
- **The continue-game warp** (`CB2_ContinueSavedGame`): if `SaveBlock2.specialSaveWarpFlags` has `CONTINUE_GAME_WARP`, CONTINUE warps to `continueGameWarp` and loads the map as any warp does (`CB2_LoadMap`): people from the map's templates, no saved view, the avatar's state fitted to the tile (on foot on land). Vanilla uses it for saves made in special places; the world revisions use it to move a save off a redesigned map.
## 16. Cliffs and terraces (mined from 238 vanilla layouts; encoded in `dev/mapkit/cliffs.py`; verified in-game by `tests/ingame_cliffs.py` and `tests/conformance.py`)
**The family.** `gTileset_General`'s brown rock pieces (`060-0EF`) draw raised ground in Hoenn's three-quarter view: the camera looks north, so a terrace shows a **face** on its south side, a thin **rim** on its north side and a narrow **flank** on each side. Hoenn uses them two ways: as rock-topped mountains (Routes 111, 116; the top is `071`, `MB_MOUNTAIN_TOP`, solid as mass in 4278 of 7206 uses and walkable rock floor in the rest) and as grass-topped bluffs and terraces (Routes 104, 120). Route 120's long cliffs also use Fortree secondary pieces; the General ones alone are enough for grass-topped terraces.

| Role (the wall cell's low side) | Pieces | Vanilla neighbour evidence |
|---|---|---|
| Rim (low N) | `068` NW corner, `069`, `06A` NE corner | `069` N: grass 108/261; `068` S: `070` 56; `06A` S: `072` 48 |
| Flank (low W / E) | `070` / `072` | `070` W: grass 254; `072` E: grass 188 |
| Foot corners (low S and W / E) | `078` / `07A` | `078` N: `070` 128; `07A` N: `072` 90 |
| Face, one row (low S) | `079` | `079` N: `071`/grass; S: grass 299, water 336 |
| Face, taller | top `07C`, middle `0A9`, bottom `091`; the top beside a flank `07B` (west) / `07D` (east) | `0A9` above `0A9` 367; `091` S: grass 175; `070` E `07B` 63, `07D` E `072` 37; **`07C` beside a flank: never**; **`0A9` beside a flank: never** |
| Inside corners (low on one diagonal) | NW `0BE`, NE `0BF`, SW `089`, SE `074` | `0BE` W: `069` 21; `0BF` E: `069` 25; `089` S: `070` 120; `074` S: `072` 82 |
| Stairs (through a face) | `0AF`, two wide `0AF 0CF` | `0AF` E: `0CF` 109/131; walkable, elevation 3 (77) or 0 (42) |

- **Attributes:** every wall piece's modal attributes are collision 1, elevation 0; stairs 0/3. Walls are `MB_NORMAL` or `MB_MOUNTAIN_TOP`, plain solid tiles: they block from every side by collision. Plateau tops in vanilla sit at elevation 3, 4 or 5 with no consistent rule; nothing needs it, so our terraces keep walkable ground at 3 (levels are a design notion).
- **Vanilla labels the stairs as grass** (`MB_NORMAL`, modal 0/3), so the learned rules can choose `0AF`/`0CF` for a grass cell beside a kept object (two did beside kept cliffs on CliffLab, and one on Route 203's second map's extract). The compiler excludes them from the rules' choices (`Rules.pick(exclude=...)`); no existing map held one, so nothing else changed.
- **Not vocabulary yet:** faces straight into water (vanilla: `079` over plain water `170`, `07C` over the bank piece `189`); the sand and water variants of the rim and flanks (`080-082`, `088`, `08A`, `090`, `092`, `098-09A`); the rock-ledge joints `08F`, `095`, `096` (8 uses); rock-topped mountains (`071`, `073`, `075`, `06B-06D`, `093/094/09B/09C`); caves (`064`/`0A7`).