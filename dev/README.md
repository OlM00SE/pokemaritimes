# PokéMaritimes dev tooling

Run everything from the repo root with `C:\Python313\python.exe`; the commands below omit that prefix. Test output goes to `dev/out/`, which is gitignored. Engine background is in `design/mapping_reference.md`.

## The loop
| Step | Command |
|---|---|
| Build (fast) | `dev/fastbuild.py`: syncs changes to a WSL-native mirror and builds there (~10s for a typical edit). |
| Static checks | `dev/check_maps.py [Map...]`. `--all` checks every map; `--baseline` checks that vanilla maps show only known exceptions. Includes ledge landings and one-way traps (below). |
| Completeness | `dev/section_status.py [--from <Map>] [Map...]`: what a slice still *lacks* (doors leading nowhere, missing encounters, no people or signs, map sections borrowed from Hoenn, silent music). By default it covers everything reachable from HomeTown_0. It only reports. |
| Render | `dev/render_map.py <Map> --overlay collision,elevation,behavior,events,grid,traps [--crop x0,y0,x1,y1]`. `behavior` draws each ledge's jump direction as an arrow; `traps` tints one-way dead ends (magenta: never left; orange: only with Surf); `events` marks warps `W`, people `P`, trainers `Tr`, signs `S`, hidden items `H`, tints each trainer's sight red and puts a cyan tick on every tile an event is triggered from. `--context [--margin N]` draws the map with an N-tile strip (default 8) of each connected neighbour, dimmed, to judge seams. `--world` stitches the connected region; `--sheet <pri> <sec>` gives a labelled metatile index. |
| Route numbers | `dev/route_stats.py <Map>...`: for each pair of edge connections, the fewest steps across, the fewest tall-grass tiles that can't be avoided, the trainers whose sight can't be avoided, and the reachable encounter ground (`mapkit/routes.py`, on the engine model, ledges and people included). `mapgen build` prints the same before and after. |
| Play by hand | Double-click `RomHackDev/Play PokeMaritimes.bat` (= `dev/play.py --build`): builds, copies the ROM to `RomHackDev/playtest/PokeMaritimes.gba` (outside the repo; the save lives beside it) and opens it in the installed mGBA. A save this build can't load (an older save layout, or damage; `dev/savefile.py <file.sav>` says which) is moved to `playtest/old_saves/` first, so the game starts clean instead of reporting a corrupt save. `--new` sets the current save aside for a fresh game, `--check` only reports. Don't play `pokeemerald.gba` itself: every build overwrites it. |
| Play on the phone | Double-click `RomHackDev/Send PokeMaritimes to phone.bat` (= `dev/mobile.py`): builds, checks the cartridge header, verifies in mGBA that the exact bytes boot, start a new game, save and CONTINUE to the same spot (and that the newest phone save in Drive's `saves/` that this build can read CONTINUEs), then copies the ROM into `<My Drive>/PokeMaritimes playtest/` on Google Drive for Desktop's volume, which uploads it (no API keys; the folder is in My Drive's root, private to the account). The play file is `PokeMaritimes_save<N>.zip` (only the ROM inside, 13 MB; My Boy! plays it as is, and the verification boots the ZIP itself), N being the save layout version, so a phone emulator keeps its save across builds of one save line and starts fresh after a save break; `builds/` keeps every build zipped with `build.txt`, `README.txt` and the tool's output give a direct download link (`drive.usercontent.google.com`, from the file's cloud id: it opens in Chrome, not the Drive app, whose Download item Android's Data Saver hides; without the owner's sign-in it shows Google's sign-in page). `README.txt` holds the phone instructions (written for My Boy!, Tom's emulator; Pizza Boy GBA Pro as the fallback), what changed, and the save checks (`saves/*.sav` and `.srm`; a save from an older save line is named as that line's). **My Boy!:** its saves live in a private app folder, so backups come from its "Sync with Google Drive" setting, which mirrors them into `<My Drive>/MyBoy`. Each run reads the files there named `*PokeMaritimes*` (never writes there: that would sync back to the phone), copies new content into `saves/myboy/<time>_<name>`, and boots the newest readable phone save in the verification. A run with an unchanged ROM still refreshes `README.txt` if its text changed. It refuses an uncommitted tree (`--allow-dirty`), skips the upload when that ROM is already the phone build, and waits for Drive to confirm the upload (read from Drive's local metadata database, best effort). `--full` adds the slice playthrough, `--check` only verifies, `--status` reports. `MARITIMES_DRIVE_DIR` overrides the folder. |
| Play-test | `dev/autowalk.py <Map> <Map> ...` walks map to map in mGBA from a new game. `dev/shoot.py <Map> x,y ... [--tag T] [--settle 240]` warps and takes screenshots; `--settle` waits for the area-name popup to go. |
| People, signs, items | `dev/events.py build design/maps/<Map>.events.toml [--apply]` places people, trainers, signs, item balls, hidden items and gifts from a spec (below). `dev/events.py list <Map>` shows any map's events with where each is triggered and what each trainer sees. |
| Fill a dead door | `dev/add_interior.py <Map> x,y <NewName> [--like <VanillaInterior>] [--apply]` identifies the building from its facade (`mapkit/doors.py`). It clones the interior vanilla uses behind it (all floors, same layout, events stripped) and wires the warps both ways. The default is a dry run. |
| Name an area | `dev/name_area.py MAPSEC_X "NAME" <Map>... [--interiors] [--apply]` gives an area its own map section (the popup name). It creates the section by appending (no existing id moves), and `--interiors` also covers the area's houses. Gen 3 popups only; BW-style popups would need theme entries. |
| Patch a hand-painted map | `dev/mapgen.py patch <Map> s@9,16 [*@4,20 ...] [--apply]` places a few pieces (`s` sign post, `*` flowers, `b` boulder...) and touches nothing else: the normal build on a sketch that keeps every other cell as `#`. Use it on Tom's hand-mapped towns instead of a rebuild. |
| Story vars and flags | `dev/save_ids.py var VAR_<NAME> "what it records" [--apply]` (or `flag FLAG_<NAME> ...`) appends a story var or flag to the Maritimes block, `(MARITIMES_VARS_START + n)` in `vars.h` or `(MARITIMES_FLAGS_START + n)` in `flags.h`, with the note as a comment. Ids never move; re-running is a no-op; vanilla names are refused. `dev/save_ids.py list` shows them all. A var for anything with stages (one per storyline), a flag for a yes/no that stays; `design/save_format.md` has the plan. |
| Id budget | `dev/tests/id_budget.py` (no emulator): trainer ids, saved flags, the story var block, the unused vanilla vars and the save blocks' room, with what's left of each. |
| Save layout | `dev/save_layout.py [--update]` measures the save blocks exactly (a probe compiled in the WSL mirror) and compares with `include/save_layout.h`, which the build asserts. After a change that moves the layout (a flag or trainer range raised, a SaveBlock field added): `--update` rewrites the numbers and bumps `SAVE_LAYOUT_VERSION`, so old saves are refused with a message instead of loading as garbage. Then run `tests/ingame_save.py`. |
| Fix attributes | `dev/fix_attrs.py <Map> [--surfable] [--apply]` sets collision/elevation to vanilla's confident values. |
| New blank map | `dev/new_map.py <Name> <W>x<H> [--like <Map>] [--group G] [--spawn x,y] [--apply]` makes an all-grass outdoor map with the `--like` map's tilesets, border and header, and no connections. A spawn point (an arrival-only warp to `MAP_DYNAMIC`) gives the checker an entrance until real connections exist. It appends to `gMapGroup_DevMaritimes` by default (no id moves). The default is a dry run. |

## Making or editing a map
1. **Get a sketch.**
   - From an existing map: `dev/mapgen.py extract <Map>` writes `design/maps/<Map>.txt`.
   - For a new design: write a design script like `design/maps/route203_design.py` or `ledgelab_design.py`. For a brand-new map, run `dev/new_map.py` first. `route203_design.py` is the worked example of ledges on a real route (a levee terrace and a wooded bench).
2. **Edit the sketch.** Each character is a terrain type: `.` grass, `,` tall grass, `=` path, `:` sand (a beach where it meets `~`), `~` river/sea, `o` pond, `T` forest, `r` rock in water, `*` flowers, `b` boulder, `y` sapling (a vertical run of 2–3), `s` sign post (its text is a sign event, below), `v` `<` `>` ledges (below), `#` keep the existing block. Design scripts draw natural forests and open ground with `mapkit/landscape.py` (below).
3. **Preview.** `dev/mapgen.py build design/maps/<Map>.txt [--fresh]` is a dry run. It runs the checker on the result in memory and writes `dev/out/<Map>_preview.png` and `_preview_overlay.png`.
   - It also reports how many cells differ from the current `map.bin`, and where. `_preview_diff.png` shows before and after side by side, cropped to the change, with changed cells outlined. When you edit an existing map, check that the change stays where you meant it to.
   - Use `--fresh` for new designs. It ignores the old map's tree placement.
   - Without `--fresh`, trees are kept on the existing 2×2 grid. A grove moved by an odd number of tiles loses trees (`dropped_tree_cells` in the report). Move groves by even amounts.
   - It prints two **landscape** numbers, before and after, for the whole map and for the changed area: the longest straight forest edge, and the largest square of bare grass, each with where it is. Lower is more natural.
   - It prints the **routes**, before and after: for each pair of edge connections, the steps across and the tall grass that can't be avoided, and the reachable tall grass. A redesign that should play the same keeps these close.
   - On a map with connections it writes `_preview_context.png`: before above after, with strips of the neighbours, so the seams can be judged.
   - It warns (`WARN reach`) when open ground a walker could reach before is now cut off: a new pocket.
   - **Terrain guard:** the grammar repairs a forbidden join by turning the lower-ranked cell into grass (a tree beside sand clears the sand). If a repair would overwrite terrain the current map *already has* as the sketch draws it, the build prints `GUARD terrain` and counts it as a new error. This is how a hand-painted join (HomeTown's lane between trees) gets damaged, so keep such joins as `#`. `extract` now does that by itself: it keeps both sides of a join the grammar forbids (trees whole), plus any neighbour a compile wouldn't put back.
4. **Apply.** `... --apply` writes `map.bin`, but only if the result has no *new* checker errors (a terrain guard hit counts as one). Errors the map already had don't block a rebuild; `--force` overrides.
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
- For a wooded route, start from forest everywhere and carve clearings (`blob`s) off the road, rather than placing groves on open grass; it reads as "through the woods". See `design/maps/route201_design.py`.
- Keep hand-painted pieces (a cliff, a seam's trees) as `#`. `plant` treats a kept block as closed, so it never leaves a leftover tile against one. Put a whole tree on either side of a `#` box, never half of one.
- Trees never touch sand (`:`) directly; the grammar would clear them. Give a road a one-tile grass verge (`around(ROAD, 1)` in `keep_clear`), and keep the trees beside a road's seam gap as `#`.

## People, signs and items
A spec per map (`design/maps/<Map>.events.toml`; `Route201_1.events.toml` and `Woodstock_2.events.toml` are the worked examples outdoors, `Woodstock_Lab.events.toml` indoors) lists the map's people, trainers, signs, things to inspect, item balls and hidden items. The spec owns those events. Anything placed by hand in Porymap is left alone (shown as `[hand-placed]`), so the two can be mixed.
```toml
map = "Route201_1"
replaces = ["LittlerootTown_EventScript_BrendansHouseSign"]           # optional: hand-placed events to take over
[[sign]]         name = "RouteSign", at = [12, 3], text = "..."           # two lines, like vanilla's
                 facing = "up"                    # optional: readable only from below (default any)
[[inspect]]      name = "FieldNotes", at = [7, 1], text = "..."           # furniture, a desk, a poster: any length
[[person]]       name, at, gfx = "OLD_MAN", facing = "left", text
                 facing = "wander", range = [2, 2]                    # optional: a wanderer
                 gift = "ITEM_ORAN_BERRY", count = 1, after = "..."   # optional: gives it once
[[trainer]]      name, at, gfx, facing, sight = 4, class = "Bug Catcher", trainer_name = "ROSS",
                 party = ["Caterpie 3", "Weedle 3"], intro, defeat, after
[[item]]         name, at, item = "ITEM_POKE_BALL"                    # an item ball
[[hidden_item]]  name, at, item = "ITEM_POTION"
```
`facing` is `down`, `up`, `left`, `right`, `around` or `wander` (with `range = [rx, ry]`, each 1–4; default `[1, 1]`. The game reads a 0 as *no limit* on that axis, so the tool refuses it). A gift person says `text`, gives the item and says `after`; later talks only say `after`. With a full bag they give nothing and offer it again next time. In dialogue, a blank line starts a new message box, and Poryscript's `format()` wraps the rest. Straight double quotes become “ ” (the charmap has no `"`). `[[inspect]]` is text read from a solid tile that has no sign post: a desk, a machine, a mailbox; it wraps like dialogue. Bookshelves, PCs and TVs already have vanilla's text (a tile behaviour), so they need no event. `replaces` names hand-placed events (by script or local id; `"<name>@x,y"` when several share a script) that the spec removes, so a spec event can take their tile: HomeTown's mailbox ran Littleroot's house-sign script. Each entry must match exactly one event, and a person can't be removed while hand-placed people follow it, because local ids are positions and hand scripts use them. A trainer's Pic, Gender and Music follow the first vanilla trainer of its class unless the spec gives them.

The workflow:
1. **Terrain first.** A sign needs a sign post under it: draw `s` in the map's design script and rebuild with `mapgen` (one cell; check the diff). On a hand-painted map without a design script, use `dev/mapgen.py patch <Map> s@x,y` (Woodstock's town sign).
2. **Dry run:** `dev/events.py build design/maps/<Map>.events.toml`. It refuses bad placements, naming them: out of bounds, two events on a tile, people on solid ground or water, a sign without a post, a sign over two lines, unknown graphics/items/species/classes. Then it prints every event with the tiles it can be triggered from, each trainer's reachable sight, and the ids it would allocate. It also runs the checker on the unsaved map, prints the route numbers before and after (a trainer on the road shows up as `can't avoid <trainer>`), and writes `dev/out/<Map>_events.png`.
3. **Apply:** `--apply` refuses new checker errors (`--force` overrides). It writes the owned events into `map.json` (after the hand-placed ones, whose local ids don't move) and the scripts into a marked block in `scripts.pory`. A room made by `add_interior.py` has no scripts at all (a stub `scripts.inc`); the tool starts its `scripts.pory`. A map with real assembly scripts must be converted by hand first. Each trainer gets an id appended to `opponents.h` and its party in `trainers.party`. Each item ball, hidden item and gift takes the next flag of the Maritimes block in `flags.h`, `(MARITIMES_FLAGS_START + n)`. Re-applying an unchanged spec changes nothing; ids are never reused or moved.
4. **Build and test:** `dev/fastbuild.py`, then `dev/tests/ingame_events.py <Map>`.

What the checker knows (`mapkit/events.py`, engine facts in `design/mapping_reference.md` §12):
- **ERROR `people`:** an exit (a warp, or a connection's edge) is reachable when nobody stands in the way but not with the map's permanent people at home.
- **WARN `people`:** ground reachable only through people. A person, item ball or sign with a script that nobody can reach to talk to, pick up or read (position, elevation, facing). A wanderer that can cut off an exit while it stands somewhere in its range (each tile is tried; vanilla does this in small houses, so it's a warning: the wanderer moves on).
- **INFO:** a trainer nobody can walk into the sight of (battles only when talked to); an event reachable only with Surf.

People's names follow the map: `LOCALID_<MAP>_<NAME>`, `<Map>_EventScript_<Name>`, `TRAINER_<MAP>_<NAME>`, `FLAG_HIDDEN_ITEM_<MAP>_<NAME>`, `FLAG_ITEM_<MAP>_<NAME>`, `FLAG_<MAP>_<NAME>_GIFT`.

**Id budget.** Trainer ids and saved flags are global and never move. Milestone 9 raised `MAX_TRAINERS_COUNT_EMERALD` to 1376 (520 ids free) and added a Maritimes flag block after the daily flags; milestone 11 sized that block for a whole region (768 flags) and added a 256-var story block in SaveBlock3 (`design/save_format.md`). The block flags are shared: `events.py` takes item and gift flags from it, `save_ids.py` story flags. The dry run prints what's left after each new id, and `dev/tests/id_budget.py` checks the whole budget. To grow a block, raise the constant (`opponents.h`, `MARITIMES_FLAGS_COUNT` in `flags.h`, `MARITIMES_VARS_COUNT` in `vars.h`). That changes the save layout: the build stops until `dev/save_layout.py --update` bumps the version, and old saves are refused. Prefer one generous raise to several small ones, and run `tests/ingame_save.py` afterwards. Once the Hoenn maps are removed, their trainer ids, flags and vars can be reclaimed too.

## Test suites
| Test | What it proves |
|---|---|
| `tests/conformance.py [Map...]` | The engine model predicts single steps exactly like the game. Result: 482/482 on 13 maps. |
| `tests/reconstruction.py` | Leave-one-out regeneration of 238 vanilla maps reproduces 87.8% of terrain tiles exactly. |
| `tests/roundtrip.py` | Extracting and recompiling our maps, with the build's grammar, keeps 87–100% of metatiles identical, and the grammar repairs no extracted cell (it fails if one would be). It also checks that the terrain guard refuses an extract that would clear HomeTown's lane. |
| `tests/ingame_events.py [Map...]` | In mGBA, every person, sign, item ball and hidden item is triggered from a tile the model picks (outside every trainer's sight): a script runs, people block their tile, a hidden item is found once. An item ball's item lands in the bag, its flag is set and the ball is gone. A gift person gives its item once. A wanderer, watched for 30 seconds, stays in its range, and is then talked to wherever it stands. Each trainer starts nothing from beside its sight, battles when the player steps into its farthest sight tile (the test wins), and afterwards neither its sight nor talking starts a battle. With no arguments it runs every map with a spec: 114/114 on seven maps (HomeTown 22, its neighbours' kitchen 4, Route 201 21, Woodstock 41, the station 14, the two houses 8 and 4). Screenshots: `dev/out/events_<Map>_*.png`. |
| `tests/ingame_save.py` | Flags at both ends of every saved range (trainer, system, Maritimes block, plus a hidden item), with their neighbours clear, survive save → reset → CONTINUE, along with the map, position and party. Then the layout guard: the saved file carries `SAVE_LAYOUT_STAMP`; the same save rewritten with an old stamp (checksums fixed) is refused on load, the menu explains (`dev/out/save_outdated_menu.png`), and its first item starts a new game. Story vars at both ends of the block, and a vanilla var, survive a save, then a link save (`SAVE_LINK`, which rewrites only sectors 0–4); on flash they sit in sector 0's and sector 4's SaveBlock3 chunks; the id past the block isn't a var; a NEW GAME over the save starts them at 0. The sector checksum covers the SaveBlock3 chunk, and a story var flipped on flash makes the save refused as damaged: 42/42. Run it after any change to the save layout. |
| `tests/id_budget.py` | No emulator. Trainer ids are contiguous, fit their flags and have parties. The saved flag ranges don't overlap. Every block flag and story var was allocated by a tool, with contiguous ids; no story flag is an item flag; no script compares a var with a number in the story block's range. Each flag `events.py` allocated is used by exactly one event, and item flags are saved and permanent. The story vars lie in the SaveBlock3 part every save writes. SaveBlock1 fits. It prints what's left. |
| `tests/var_macros.py` | No emulator (needs the WSL mirror). Assembles a probe with the build's script macros: `compare` treats both ends of the story var block as vars and the id past it as a value; `copyvar` from a story var doesn't warn, `setvar` with one as the value does. |
| `tests/ledge_pieces.py` | No emulator, under a minute. It runs four checks:<br>• Every vanilla ledge outside 16 known cliff constructions is rebuilt piece for piece (66/66 groups).<br>• 25 sketch shapes build or are refused as expected.<br>• Extract→compile leaves every ledge block unchanged on 8 vanilla routes, LedgeLab and Route 203.<br>• The checker catches a soft-lock in a sealed copy of LedgeLab. |
| `tests/ingame_ledges.py [Map...]` | For every ledge tile, the test presses toward it from each free neighbour. The game must jump, or refuse to move, exactly as the model says, elevations included. On maps with a spawn point it also walks down the ledges and back. On maps without wandering people it runs a **terrace tour** (paths go around the people who stand still): from the entrance (the spawn point, else the first connection's edge) it jumps down each ledge group and walks back on foot, and screenshots each landing (`dev/out/ledges_<Map>_tour<N>.png`). LedgeLab: 150/150, 6/6 groups. Route 203: 92/92, 2/2 groups. Route 201: 20/20, 1/1 group. Vanilla Routes 102, 103, 116 and 123: 228/228; Route 116 is toured (1/1 group), the others have wandering people. A warp that fails or lands elsewhere counts as a failure. |
| `tests/shore_pieces.py [-v]` | No emulator. It runs three checks:<br>• Every vanilla place where water meets only grass or beach sand is rebuilt from its shape: 99.9% exact; beach-sand edges and grass banks 100%.<br>• 17 sketch shapes build or are refused as expected.<br>• Extract→compile, with mapgen's grammar, leaves every shore block unchanged on ShoreLab, Route 203, Woodstock and 9 vanilla beach/river maps. Our generated maps must do it from the shape tables alone, with nothing kept by extract's compile check. |
| `tests/ingame_shores.py [--max N] [--surf N] [Map...]` | At every land/water edge, in mGBA: on foot, pressing toward the water doesn't move the player. Surfing, pressing toward land comes ashore exactly where the engine model says. Rocks block. For a sample of shores, Surf works through the real field-move prompt (a party Pokémon taught Surf via the dev bridge, plus the badge flag). ShoreLab 276/276, Route 203 352/352. Screenshots: `dev/out/shores_<Map>_*.png`. |
| `tests/flora_pieces.py [-v]` | No emulator. It runs four checks:<br>• On 16 vanilla maps, extract rebuilds flowers (103/190), boulders (23/52) and Route 116 saplings (31/56) exactly, neighbours included. The rest stay `#` (an odd elevation, a non-grass spot, or a neighbour vanilla drew for the object). Extract→compile changes no flora block and no block beside one.<br>• 14 sketch shapes build or are refused as expected.<br>• GroveLab and Route 203 round-trip from the shape tables alone.<br>• 300 random `plant()` runs tile back exactly, with valid saplings and nothing on `keep_clear`. Against a kept `#` block, an odd run leaves its spare tile at the open end, and a one-tile walkway beside the block stays open (7/7). |
| `tests/ingame_flora.py [--edges N] [Map...]` | In mGBA, the test presses into every flora piece, and a sample of forest-edge trees (offset trees first), from each open neighbour. Flowers and crown tops are walked onto; boulders, trunks and trees block, exactly as the engine model says. GroveLab 168/168, Route 203 128/128, Route 201 137/137. Screenshots: `dev/out/flora_<Map>_*.png`. |
| `check_maps.py --baseline` | The checker raises no false errors on vanilla. Known special cases are listed in `mapkit/baseline.py`. |
| `tests/playthrough_slice1.py` | End-to-end, wild battles on: a new player is stopped at HomeTown's exit, gets a starter from the researcher, walks Route 201 to Woodstock fleeing battles, and returns to be healed. |
| `tests/ingame_doors.py <Map>...` | Every door warp enters its interior (stairs followed), and walking out returns to the door. |
| `tests/ingame_encounters.py <Map> [--battles N] [--no-party]` | Wild battles start on the map's grass, and only species from its land table appear. `--no-party` checks that a player with no Pokémon never gets a wild battle. |
| `tests/ingame_warp.py`, `tests/ingame_water_woodstock.py` | Targeted in-game checks. |

## In-game dev hooks (non-release builds only)
`DEBUG_DEV_BRIDGE` in `include/config/debug.h` enables `gDevBridge` in `src/field_control_avatar.c`. Python uses it to warp anywhere, set and read flags (`Emu.set_flag`, `Emu.get_flag`), give the player a Pokémon (`Emu.give_mon`), count an item in the bag (`Emu.bag_count`), read and set vars (`Emu.get_var`, `Emu.set_var`), save the game (`Emu.save_game`, as the start menu does; `link=True` as a link save does), and wait until the player has control. `Emu.objects()` lists each object's local id and position.

`WE_FLAG_NO_ENCOUNTER` and `OW_FLAG_NO_TRAINER_SEE` are assigned to unused flags. `Emu.test_mode()` sets them for movement-only tests, and also sets `FLAG_SYS_POKEMON_GET` so story gates (HomeTown's exit) are open; `test_mode(trainer_sight=True)` leaves trainers able to see. Other helpers: `Emu.flee_battle()`, `Emu.win_battle()` (first move every turn), `Emu.advance_text()`, `Emu.has_control()`, `Emu.facing()`, `Emu.object_at(x, y)`, `mgba_bridge.flag_id(name)`. `Walker(e, on_interrupt=e.flee_battle)` walks with wild battles on, re-planning after each one. It plans around people and, by default, around every trainer's sight (a trainer battle can't be fled).

Map scripts may be written in Poryscript (`scripts.pory`). `fastbuild.py` copies the generated `scripts.inc` back so git tracks the current output.

## Known limits (v1)
- **Vocabulary:** route terrain, ledges, shores (grass banks, beaches, water rocks) and flora (flowers, boulders, saplings) on `gTileset_General` only. Cliffs/elevation changes, rocky shores, pond shores by shape, buildings and town pieces stay literal (`#`) or are hand-painted in Porymap. The 16 vanilla ledge groups that meet cliffs (Route 118's terraces and five others, listed in `tests/ledge_pieces.py`) extract as `#`.
- **Engine model:** doesn't cover sideways stairs, ice, currents, bikes or boulders. People block where they stand; a wanderer is judged at home (route numbers), tile by tile for exits (checker), or as its whole range (walker). Buried trainers (Lavaridge Gym) aren't modelled as blockers. Story maps can take control on warp-in, and conformance skips those.
- **Exact match:** isn't the same as looking right. Always review renders and in-game shots.
