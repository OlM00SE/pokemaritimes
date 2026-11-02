# PokéMaritimes dev tooling

Run everything from the repo root with `C:\Python313\python.exe`; the commands below omit that prefix. Test output goes to `dev/out/`, which is gitignored. Engine background is in `design/mapping_reference.md`.

## The loop
| Step | Command |
|---|---|
| Build (fast) | `dev/fastbuild.py`: syncs changes to a WSL-native mirror and builds there (~10s for a typical edit). |
| Static checks | `dev/check_maps.py [Map...]`. `--all` checks every map; `--baseline` checks that vanilla maps show only known exceptions. |
| Completeness | `dev/section_status.py [--from <Map>] [Map...]`: what a slice still *lacks* (doors leading nowhere, missing encounters, no people or signs, map sections borrowed from Hoenn, silent music). By default it covers everything reachable from HomeTown_0. It only reports. |
| Render | `dev/render_map.py <Map> --overlay collision,elevation,behavior,events,grid`. `--world` stitches the connected region; `--sheet <pri> <sec>` gives a labelled metatile index. |
| Play-test | `dev/autowalk.py <Map> <Map> ...` walks map to map in mGBA from a new game. `dev/shoot.py <Map> x,y ...` warps and takes screenshots. |
| Fill a dead door | `dev/add_interior.py <Map> x,y <NewName> [--like <VanillaInterior>] [--apply]` identifies the building from its facade (`mapkit/doors.py`). It clones the interior vanilla uses behind it (all floors, same layout, events stripped) and wires the warps both ways. The default is a dry run. |
| Name an area | `dev/name_area.py MAPSEC_X "NAME" <Map>... [--interiors] [--apply]` gives an area its own map section (the popup name). It creates the section by appending (no existing id moves), and `--interiors` also covers the area's houses. Gen 3 popups only; BW-style popups would need theme entries. |
| Fix attributes | `dev/fix_attrs.py <Map> [--surfable] [--apply]` sets collision/elevation to vanilla's confident values. |

## Making or editing a map
1. **Get a sketch.**
   - From an existing map: `dev/mapgen.py extract <Map>` writes `design/maps/<Map>.txt`.
   - For a new design: write a design script like `design/maps/route203_design.py`.
2. **Edit the sketch.** Each character is a terrain type: `.` grass, `,` tall grass, `=` path, `:` sand, `~` river/sea, `o` pond, `T` forest, `#` keep the existing block.
3. **Preview.** `dev/mapgen.py build design/maps/<Map>.txt [--fresh]` is a dry run that writes `dev/out/<Map>_preview.png` and `_preview_overlay.png`.
   - Use `--fresh` for new designs. It ignores the old map's tree placement.
4. **Apply.** `... --apply` writes `map.bin` and runs the checker.
5. **Build, then play-test.** Use `fastbuild.py`, then `autowalk.py`, `tests/conformance.py <Map>` and `shoot.py`.

How compiling works:
- Forest becomes whole 2×2 trees.
- Forbidden terrain pairs get a grass margin. Each repair is reported.
- Every cell gets the metatile vanilla uses in that neighbourhood. Unseen neighbourhoods fall back to a naive-Bayes vote.
- Collision and elevation come from vanilla's defaults.

## Test suites
| Test | What it proves |
|---|---|
| `tests/conformance.py [Map...]` | The engine model predicts single steps exactly like the game. Result: 439/439 on 12 maps. |
| `tests/reconstruction.py` | Leave-one-out regeneration of 238 vanilla maps reproduces 87.8% of terrain tiles exactly. |
| `tests/roundtrip.py` | Extracting and recompiling our maps keeps 86–99% of metatiles identical. |
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
- **Vocabulary:** route terrain on `gTileset_General` only. Rocks, ledges, cliffs/elevation changes, shorelines, buildings and town pieces stay literal (`#`) or are hand-painted in Porymap.
- **Engine model:** doesn't cover sideways stairs, ice, currents, bikes, boulders, or NPC movement. Story maps can take control on warp-in, and conformance skips those.
- **Exact match:** isn't the same as looking right. Always review renders and in-game shots.
