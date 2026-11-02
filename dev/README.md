# PokéMaritimes dev tooling

Run everything from the repo root with `C:\Python313\python.exe`; the commands below omit that prefix. Test output goes to `dev/out/`, which is gitignored. Engine background is in `design/mapping_reference.md`.

## The loop
| Step | Command |
|---|---|
| Build (fast) | `dev/fastbuild.py`: syncs changes to a WSL-native mirror and builds there (~10s for a typical edit). |
| Static checks | `dev/check_maps.py [Map...]`. `--all` checks every map; `--baseline` checks that vanilla maps show only known exceptions. Includes ledge landings and one-way traps (below). |
| Completeness | `dev/section_status.py [--from <Map>] [Map...]`: what a slice still *lacks* (doors leading nowhere, missing encounters, no people or signs, map sections borrowed from Hoenn, silent music). By default it covers everything reachable from HomeTown_0. It only reports. |
| Render | `dev/render_map.py <Map> --overlay collision,elevation,behavior,events,grid,traps [--crop x0,y0,x1,y1]`. `behavior` draws each ledge's jump direction as an arrow; `traps` tints one-way dead ends (magenta: never left; orange: only with Surf). `--world` stitches the connected region; `--sheet <pri> <sec>` gives a labelled metatile index. |
| Play-test | `dev/autowalk.py <Map> <Map> ...` walks map to map in mGBA from a new game. `dev/shoot.py <Map> x,y ...` warps and takes screenshots. |
| Fill a dead door | `dev/add_interior.py <Map> x,y <NewName> [--like <VanillaInterior>] [--apply]` identifies the building from its facade (`mapkit/doors.py`). It clones the interior vanilla uses behind it (all floors, same layout, events stripped) and wires the warps both ways. The default is a dry run. |
| Name an area | `dev/name_area.py MAPSEC_X "NAME" <Map>... [--interiors] [--apply]` gives an area its own map section (the popup name). It creates the section by appending (no existing id moves), and `--interiors` also covers the area's houses. Gen 3 popups only; BW-style popups would need theme entries. |
| Fix attributes | `dev/fix_attrs.py <Map> [--surfable] [--apply]` sets collision/elevation to vanilla's confident values. |
| New blank map | `dev/new_map.py <Name> <W>x<H> [--like <Map>] [--group G] [--spawn x,y] [--apply]` makes an all-grass outdoor map with the `--like` map's tilesets, border and header, and no connections. A spawn point (an arrival-only warp to `MAP_DYNAMIC`) gives the checker an entrance until real connections exist. It appends to `gMapGroup_DevMaritimes` by default (no id moves). The default is a dry run. |

## Making or editing a map
1. **Get a sketch.**
   - From an existing map: `dev/mapgen.py extract <Map>` writes `design/maps/<Map>.txt`.
   - For a new design: write a design script like `design/maps/route203_design.py` or `ledgelab_design.py`. For a brand-new map, run `dev/new_map.py` first.
2. **Edit the sketch.** Each character is a terrain type: `.` grass, `,` tall grass, `=` path, `:` sand, `~` river/sea, `o` pond, `T` forest, `v` `<` `>` ledges (below), `#` keep the existing block.
3. **Preview.** `dev/mapgen.py build design/maps/<Map>.txt [--fresh]` is a dry run. It runs the checker on the result in memory and writes `dev/out/<Map>_preview.png` and `_preview_overlay.png`.
   - Use `--fresh` for new designs. It ignores the old map's tree placement.
4. **Apply.** `... --apply` writes `map.bin`, but only if the checker reports no errors.
5. **Build, then play-test.** Use `fastbuild.py`, then `autowalk.py`, `tests/conformance.py <Map>` and `shoot.py`. If the map has ledges, also run `tests/ingame_ledges.py <Map>`.

How compiling works:
- Forest becomes whole 2×2 trees.
- Forbidden terrain pairs get a grass margin. Each repair is reported.
- Every cell gets the metatile vanilla uses in that neighbourhood. Unseen neighbourhoods fall back to a naive-Bayes vote.
- Ledges are assembled from vanilla's pieces by shape (`mapkit/ledges.py`), not voted on.
- Collision and elevation come from vanilla's defaults.

### Ledges
Draw a ledge as a line of the character for the direction the player jumps. The high ground is behind the arrow.
- `v` jumps south. Draw it as a horizontal row.
- `<` jumps west and `>` jumps east. Draw them as vertical columns.
- There's no `^`: `gTileset_General` has no north-facing ledge.

The compiler picks each piece from the shape:
- **Ends:** end caps.
- **Corners:** where a column meets a row, it uses the plateau corner (Route 116) or the one-tile stair step (Routes 101 and 103). A corner may be drawn with either character.
- **Running on:** a ledge running off the map edge, or into a kept `#` cliff or wall from the secondary tileset, has no cap. This is what vanilla does.

`design/maps/LedgeLab.txt` shows every piece.

The sketch is refused, with the cells to fix, in these cases:
- Ledges branch, stack, or are a single tile.
- A column mixes `<` and `>`.
- A usable ledge lands on a tree, water, a solid tile, or off the map. The game never checks the landing tile, so this would be a real bug.

A ledge with nothing walkable behind it can never be jumped. That's allowed (vanilla's cliff ledges are like this) but reported as a warning.

The checker (`check_maps.py`) adds two map-level checks for any map, hand-painted ones included:
- **`ledge`:** a reachable jump that lands on a solid tile or in water.
- **`trap`:** tiles a player can walk or jump into but never leave. This is an ERROR. If Surf is the only way out, it's a WARN.

Ways out are connections, warp triggers, and walkable arrival tiles. Only one vanilla map has a trap: Shoal Cave's ledge pocket. It's confirmed in-game and listed in `mapkit/baseline.py`.

## Test suites
| Test | What it proves |
|---|---|
| `tests/conformance.py [Map...]` | The engine model predicts single steps exactly like the game. Result: 482/482 on 13 maps. |
| `tests/reconstruction.py` | Leave-one-out regeneration of 238 vanilla maps reproduces 87.8% of terrain tiles exactly. |
| `tests/roundtrip.py` | Extracting and recompiling our maps keeps 88–100% of metatiles identical. |
| `tests/ledge_pieces.py` | No emulator, about 2 minutes. It runs four checks:<br>• Every vanilla ledge outside 16 known cliff constructions is rebuilt piece for piece (66/66 groups).<br>• 25 sketch shapes build or are refused as expected.<br>• Extract→compile leaves every ledge block unchanged on 8 vanilla routes and LedgeLab.<br>• The checker catches a soft-lock in a sealed copy of LedgeLab. |
| `tests/ingame_ledges.py [Map...]` | For every ledge tile, the test presses toward it from each free neighbour. The game must jump, or refuse to move, exactly as the model says, elevations included. On maps with a spawn point it also walks down the ledges and back. LedgeLab: 150/150. Vanilla Routes 102, 103, 116 and 123: 130/130. |
| `check_maps.py --baseline` | The checker raises no false errors on vanilla. Known special cases are listed in `mapkit/baseline.py`. |
| `tests/playthrough_slice1.py` | End-to-end, wild battles on: a new player is stopped at HomeTown's exit, gets a starter from the researcher, walks Route 201 to Woodstock fleeing battles, and returns to be healed. |
| `tests/ingame_doors.py <Map>...` | Every door warp enters its interior (stairs followed), and walking out returns to the door. |
| `tests/ingame_encounters.py <Map> [--battles N] [--no-party]` | Wild battles start on the map's grass, and only species from its land table appear. `--no-party` checks that a player with no Pokémon never gets a wild battle. |
| `tests/ingame_warp.py`, `tests/ingame_water_woodstock.py` | Targeted in-game checks. |

## In-game dev hooks (non-release builds only)
`DEBUG_DEV_BRIDGE` in `include/config/debug.h` enables `gDevBridge` in `src/field_control_avatar.c`. Python uses it to warp anywhere, set flags, give the player a Pokémon (`Emu.give_mon`), and wait until the player has control.

`WE_FLAG_NO_ENCOUNTER` and `OW_FLAG_NO_TRAINER_SEE` are assigned to unused flags. `Emu.test_mode()` sets them for movement-only tests, and also sets `FLAG_SYS_POKEMON_GET` so story gates (HomeTown's exit) are open. Other helpers: `Emu.flee_battle()`, `Emu.advance_text()`, `Emu.has_control()`, `mgba_bridge.flag_id(name)`. `Walker(e, on_interrupt=e.flee_battle)` walks with wild battles on, re-planning after each one.

Map scripts may be written in Poryscript (`scripts.pory`). `fastbuild.py` copies the generated `scripts.inc` back so git tracks the current output.

## Known limits (v1)
- **Vocabulary:** route terrain and ledges on `gTileset_General` only. Rocks, cliffs/elevation changes, shorelines, buildings and town pieces stay literal (`#`) or are hand-painted in Porymap. The 16 vanilla ledge groups that meet cliffs (Route 118's terraces and five others, listed in `tests/ledge_pieces.py`) extract as `#`.
- **Engine model:** doesn't cover sideways stairs, ice, currents, bikes, boulders, or NPC movement. Story maps can take control on warp-in, and conformance skips those.
- **Exact match:** isn't the same as looking right. Always review renders and in-game shots.
