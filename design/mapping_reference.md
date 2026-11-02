# How maps work in pokeemerald-expansion 1.17.2 (Emerald mode)

These are notes from reading the engine source. Every rule cites where it comes from. They're encoded in `dev/mapkit/engine.py` and verified against the real game: `dev/tests/conformance.py` matched 482/482 single steps across 13 maps, and `dev/tests/ingame_ledges.py` matched every approach to every ledge on LedgeLab and four vanilla routes (280/280).

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
- **Grammar:** vanilla keeps a grass margin between water and tall grass, paths, or sand. Sand never touches trees. Shorelines use dedicated tiles (`11B–12D`), which aren't modelled yet.

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
- **Not modelled.** Route 118's mountain terraces and five other ledge-meets-cliff joints use cliff tiles (`070/071`, secondary cliffs). They're future vocabulary.

## 9. One-way traps (`checks.check_traps`)
**How the check works:** ledges make one-way moves, so the checker builds the full movement graph from every entrance (on foot) and finds tiles that can be reached but can't reach a way out.

Ways out:
- a connection edge;
- any warp's trigger position;
- a walkable arrival tile. A dev map's spawn point counts; solid arrival tiles such as Route 115's Terra Cave holes don't.

**Vanilla result:** exactly one real trap, the ledge pocket in `ShoalCave_LowTideEntranceRoom`. All 50 moves out of it were confirmed blocked in mGBA. Escape Rope or Dig gets the player out.
