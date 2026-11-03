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
   - For a new design: write a design script like `design/maps/route203_design.py` or `ledgelab_design.py`. For a brand-new map, run `dev/new_map.py` first. `route203_design.py` is the worked example of ledges on a real route (a levee terrace and a wooded bench).
2. **Edit the sketch.** Each character is a terrain type: `.` grass, `,` tall grass, `=` path, `:` sand (a beach where it meets `~`), `~` river/sea, `o` pond, `T` forest, `r` rock in water, `*` flowers, `b` boulder, `y` sapling (a vertical run of 2–3), `v` `<` `>` ledges (below), `#` keep the existing block. Design scripts draw natural forests and open ground with `mapkit/landscape.py` (below).
3. **Preview.** `dev/mapgen.py build design/maps/<Map>.txt [--fresh]` is a dry run. It runs the checker on the result in memory and writes `dev/out/<Map>_preview.png` and `_preview_overlay.png`.
   - It also reports how many cells differ from the current `map.bin`, and where. `_preview_diff.png` shows before and after side by side, cropped to the change, with changed cells outlined. When you edit an existing map, check that the change stays where you meant it to.
   - Use `--fresh` for new designs. It ignores the old map's tree placement.
   - Without `--fresh`, trees are kept on the existing 2×2 grid. A grove moved by an odd number of tiles loses trees (`dropped_tree_cells` in the report). Move groves by even amounts.
   - It prints two **landscape** numbers, before and after, for the whole map and for the changed area: the longest straight forest edge, and the largest square of bare grass. Lower is more natural.
   - It warns (`WARN reach`) when open ground a walker could reach before is now cut off: a new pocket.
4. **Apply.** `... --apply` writes `map.bin`, but only if the result has no *new* checker errors. Errors the map already had don't block a rebuild; `--force` overrides.
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

Ways out are connections and warp triggers. On a map whose only warp is a `new_map.py` spawn point, returning to the spawn also counts. Only one vanilla map has a trap: Shoal Cave's ledge pocket. It's confirmed in-game and listed in `mapkit/baseline.py`.

### Shores (riverbanks, lake shores, beaches)
Where `~` water meets land, `mapkit/shores.py` builds the edge from the shape, like ledges. It doesn't use the learned vote, which only knew straight banks and drew plain edges on coves and corners. `gTileset_General` has the same structure in two materials:
- **Grass bank:** `189` top, `190`/`192` sides, `188`/`18A` corners, `178`/`179` bank ends, `198`/`19A` inner corners, and `002` on the grass below the water.
- **Beach:** draw `:` sand against the water. The pieces are `12C`, `123`/`125`, `146`/`145`, `11B`/`11D`, `12D`/`12B`, and `11C`/`13D`/`13E` on the sand below the water. On its land side the sand keeps the sand patch's grassy rim.
- **Rocks:** `r` is a 2×2 rock standing in water (`150 151 / 158 159`). It must be a whole 2×2 with water on every side.

Tips for natural shapes (see `design/maps/route203_design.py` and `shorelab_design.py`):
- Vary the width, and change the bank one row at a time, every two to five columns. Long flat runs and big jumps look rectangular.
- Give promontories a rounded tip (4 → 5 → 4).
- For a beach in a bay, let the water bulge into the sand. Run the sand one tile past the water on each side, so the ends get `13E`/`13D`.

The compiler refuses shapes the tiles can't draw, naming the cells:
- water one tile wide between two side banks;
- a grass bank that turns into a beach at a corner (start the beach on a straight stretch);
- water squeezed between a side bank and the opposite corner;
- half a rock, or a rock touching land.

Kept `#` tiles and pond water count as "no land", because vanilla draws those edges on the object itself. `extract` keeps (`#`) any shore cell that a compile wouldn't reproduce exactly (special water such as waterfalls, vanilla's unusual joins), so extract → compile never changes a shore block. `design/maps/ShoreLab.txt` uses every piece.

### Forests, open ground and flora
**Flora pieces** (`mapkit/flora.py`) are built by shape, from vanilla's General tiles:
- `*` flowers (`004`), walkable.
- `b` a boulder (`0E0`), solid.
- `y` a sapling: a vertical run of 2 or 3 `y`, drawn as `00E` crown top / `0C6` crown middle / `017` trunk. You walk behind the crown top; the rest is solid.

Each piece stands on plain grass only. The compiler names the cells where grass would get an edge tile instead: right above a tree (canopy overhang), right below water (the bank), or beside a path rim. A ledge may land on flowers or a crown top, but not on a boulder or a trunk. `design/maps/GroveLab.txt` uses every piece.

**Design helpers** (`mapkit/landscape.py`). You compose: where the groves, clearings, meadows and accents go. The helpers draw vanilla's small-scale shapes, deterministically from a seed. Masks are sets of cells; combine them with `|`, `&` and `-`.
| Helper | What it draws |
|---|---|
| `forest_edge(x0,y0,x1,y1, open_side, amp, seed)` | Forest whose edge facing `open_side` recedes 0..amp tiles along a stepped profile: flat for 2–5 tiles, then a step of a tree, often continuing as a diagonal staircase. |
| `blob(cx,cy,rx,ry, seed, wobble)` | A rounded patch with a few smooth lobes: a grove, a clearing (subtract it), a meadow. |
| `plant(sk, mask, area, parity, keep_clear)` | Replants the forest in `area` to cover `mask`, in 2-row bands. Fringe runs start flush with open ground at any alignment, giving vanilla's staggered edge trees. Enclosed runs stay on the tree grid given by `parity`, the (x, y) parity of the trees around the area. A tile left over goes to an open end (a nook) or becomes a sapling, never a pocket. |
| `meadow(sk, mask, seed, tufts)` | Tall grass over the mask, plus a few stray tufts just outside it. |
| `sapling_stand(sk, mask, seed, density)` | A young grove of 2–3 tall saplings in a staggered rhythm. Trunks never stand side by side, so it never closes into a hedge. |
| `flower_bed(sk, x, y, n, seed)`, `nestle(sk, area, n, seed)` | A compact bed of flowers; boulders tucked into the forest's inner corners. |
| `around`, `cells_of`, `ledge_clearance` | Build `keep_clear` sets: the trail and its margin, ledges with their approach and landing tiles, the seams. |

Tips (see `design/maps/route203_design.py`, milestone 6 section, and `grovelab_design.py`):
- Pass every helper the same `keep_clear`.
- Give `plant` the tree grid of the forest you are editing. Route 203's southern forest starts on an odd row, so it uses `parity=(0, 1)`.
- Keep each `plant` area to whole 2-row bands. Don't let two `plant` areas overlap: each one clears the old forest inside its area.
- Check that the diff report's box stays where you meant, and read the `WARN reach` line.
- Vanilla's accents are sparse. Use a few flower beds where a trail opens out, and a few boulders per screen.

## Test suites
| Test | What it proves |
|---|---|
| `tests/conformance.py [Map...]` | The engine model predicts single steps exactly like the game. Result: 482/482 on 13 maps. |
| `tests/reconstruction.py` | Leave-one-out regeneration of 238 vanilla maps reproduces 87.8% of terrain tiles exactly. |
| `tests/roundtrip.py` | Extracting and recompiling our maps keeps 88–100% of metatiles identical. |
| `tests/ledge_pieces.py` | No emulator, under a minute. It runs four checks:<br>• Every vanilla ledge outside 16 known cliff constructions is rebuilt piece for piece (66/66 groups).<br>• 25 sketch shapes build or are refused as expected.<br>• Extract→compile leaves every ledge block unchanged on 8 vanilla routes, LedgeLab and Route 203.<br>• The checker catches a soft-lock in a sealed copy of LedgeLab. |
| `tests/ingame_ledges.py [Map...]` | For every ledge tile, the test presses toward it from each free neighbour. The game must jump, or refuse to move, exactly as the model says, elevations included. On maps with a spawn point it also walks down the ledges and back. On maps without NPCs it runs a **terrace tour**: from the entrance (the spawn point, else the first connection's edge) it jumps down each ledge group and walks back on foot, and screenshots each landing (`dev/out/ledges_<Map>_tour<N>.png`). LedgeLab: 150/150, 6/6 groups. Route 203: 92/92, 2/2 groups. Vanilla Routes 102, 103, 116 and 123: 228/228 (they have NPCs, so no tour). A warp that fails or lands elsewhere counts as a failure. |
| `tests/shore_pieces.py [-v]` | No emulator. It runs three checks:<br>• Every vanilla place where water meets only grass or beach sand is rebuilt from its shape: 99.9% exact; beach-sand edges and grass banks 100%.<br>• 17 sketch shapes build or are refused as expected.<br>• Extract→compile, with mapgen's grammar, leaves every shore block unchanged on ShoreLab, Route 203, Woodstock and 9 vanilla beach/river maps. Our generated maps must do it from the shape tables alone, with nothing kept by extract's compile check. |
| `tests/ingame_shores.py [--max N] [--surf N] [Map...]` | At every land/water edge, in mGBA: on foot, pressing toward the water doesn't move the player. Surfing, pressing toward land comes ashore exactly where the engine model says. Rocks block. For a sample of shores, Surf works through the real field-move prompt (a party Pokémon taught Surf via the dev bridge, plus the badge flag). ShoreLab 276/276, Route 203 352/352. Screenshots: `dev/out/shores_<Map>_*.png`. |
| `tests/flora_pieces.py [-v]` | No emulator. It runs four checks:<br>• On 16 vanilla maps, extract rebuilds flowers (103/190), boulders (23/52) and Route 116 saplings (31/56) exactly, neighbours included. The rest stay `#` (an odd elevation, a non-grass spot, or a neighbour vanilla drew for the object). Extract→compile changes no flora block and no block beside one.<br>• 14 sketch shapes build or are refused as expected.<br>• GroveLab and Route 203 round-trip from the shape tables alone.<br>• 300 random `plant()` runs tile back exactly, with valid saplings and nothing on `keep_clear`. |
| `tests/ingame_flora.py [--edges N] [Map...]` | In mGBA, the test presses into every flora piece, and a sample of forest-edge trees (offset trees first), from each open neighbour. Flowers and crown tops are walked onto; boulders, trunks and trees block, exactly as the engine model says. GroveLab 168/168, Route 203 128/128. Screenshots: `dev/out/flora_<Map>_*.png`. |
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
- **Vocabulary:** route terrain, ledges, shores (grass banks, beaches, water rocks) and flora (flowers, boulders, saplings) on `gTileset_General` only. Cliffs/elevation changes, rocky shores, pond shores by shape, buildings and town pieces stay literal (`#`) or are hand-painted in Porymap. The 16 vanilla ledge groups that meet cliffs (Route 118's terraces and five others, listed in `tests/ledge_pieces.py`) extract as `#`.
- **Engine model:** doesn't cover sideways stairs, ice, currents, bikes, boulders, or NPC movement. Story maps can take control on warp-in, and conformance skips those.
- **Exact match:** isn't the same as looking right. Always review renders and in-game shots.
