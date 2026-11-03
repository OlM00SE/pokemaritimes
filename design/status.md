# PokéMaritimes: project status (handoff)

> Updated 2026-11-03. Read this first in a new session. Creative direction lives in
> `region_plan.md`; tooling in `../dev/README.md`; engine facts in `mapping_reference.md`.

## Where we are
**Milestone 6 done: natural forests and open ground** (branch `milestone6-flora`, merged into `develop`).

Tom's review named two problems: "rectangular forest groupings" and "large uniform grassy areas". The first step was studying how vanilla composes these (`mapping_reference.md` §11):
- **Forest edges:** about 10% of tree joins are offset by one tile, almost all on edges. Edges step every one to three trees, in bays, headlands and diagonal staircases. Lone trees and pairs stand just outside.
- **Tall grass:** irregular patches, with stray tufts at the fringe (Route 116).
- **Accents:** sparse. Flowers are mostly singles or small beds. A third of boulders stand against a tree.
- **Saplings:** Route 116's young grove uses a 1×2 sapling (a walk-behind crown over a trunk).
- **Ruled out:** `0CE` is a cliff shrub, `14B–14D` is berry soil, and the "decorations" the vocabulary had found are Route 113's ash grass.

What was built:
- **Flora pieces** (`dev/mapkit/flora.py`): `*` flowers (`004`), `b` boulder (`0E0`), and `y` sapling (a vertical run of 2–3: `00E` / `0C6` / `017`). They are resolved by shape, like ledges and shores. Each stands only on plain grass. The compiler refuses a piece under a canopy overhang, on a bank, or as a bad ledge landing, naming the cells. Flora reads as grass to the learned rules, so it never changes a neighbour. Extract finds flora and keeps any piece a compile wouldn't put back exactly, neighbours included.
- **Landscape helpers** (`dev/mapkit/landscape.py`). The designer composes and the helpers draw the small-scale shapes, deterministically from a seed:
  - `plant()` lays forest in 2-row bands. Fringe runs start flush with open ground at any alignment (vanilla's staggered edge trees). Enclosed runs stay on the forest's grid. Leftover tiles become nooks or saplings, never pockets. It refuses to cut a tree in half at its area's edge.
  - `forest_edge()` gives a stepped profile with diagonal staircases. `blob()`, `meadow()` (with stray tufts), `sapling_stand()` (never a hedge), `flower_bed()` and `nestle()` (boulders in inner corners) cover the rest.
- **Trees tiled per grove:** each 4-connected grove keeps the old map's trees only if that drops no more cells than tiling it afresh. A redesigned edge isn't knocked out by old trees.
- **`mapgen build` reports:**
  - Landscape metrics, before and after, for the whole map and the changed area: the longest straight forest edge and the largest bare-grass square.
  - `WARN reach`: open land nobody can walk to that was reachable before or that this build changed, i.e. a new pocket.
- **GroveLab** (`design/maps/grovelab_design.py`): a dev-only 40×32 woodland meadow using every helper and piece.
- **Route 203's valley floor** (`route203_design.py`, milestone 6 section):
  - The southern forest's straight wall now comes and goes in bays and headlands.
  - The bench, middle and pond groves are rounded with staggered fringes; the middle grove has a sunny notch with flowers and boulders.
  - Tall-grass rectangles became patches with tufts, and saplings come up by the south branch.
  - 300 cells changed, all within x 2–46, y 14–31. In that area the longest straight forest edge went from 42 to 12 tiles, and the largest bare-grass square from 6 to 4. The trail, pond, ledges, river and seams are untouched.

Before/after: `dev/out/Route203_1_preview_diff.png` and `GroveLab_preview.png` (regenerate with `mapgen build`). In-game shots: `dev/out/flora_*.png`.

How it was verified:
| Area | Result |
|---|---|
| Vanilla agreement | On 16 vanilla maps, extract rebuilds 103/190 flowers, 23/52 boulders and 31/56 Route 116 saplings exactly, neighbours included. The rest stay `#`: an odd elevation, or a neighbour vanilla drew for the object. |
| Shapes | 14/14 sketch shapes build or are refused as expected. |
| Planting | 300/300 seeded random `plant()` runs tile back exactly: no dropped cells, valid saplings, nothing on keep-clear. |
| Round trip | GroveLab and Route 203: 100%, from the shape tables alone. Our other maps are unchanged from `develop` (HomeTown 88.1%, Woodstock 95.9%, Route 202 92.6%). |
| Checker | 19 maps, 0 errors. Vanilla baseline: 0 unexpected. Neither map has a cut-off pocket. |
| In-game flora | `ingame_flora.py`: GroveLab 168/168, Route 203 128/128. Flowers and crown tops are walked onto (the player passes behind the crown). Boulders, trunks and staggered edge trees block, exactly as the engine model says. |
| Regression set | Conformance 562/562 (GroveLab added). Playthrough, doors, encounters (with and without a party) and all three autowalks pass, crossing the new Route 203. Ledges PASS, shores 624/624, ledge and shore piece tests PASS. |
| Code review | `/code-review medium` raised 10 findings; all 10 fixed, see below. My first fix for one of them, verifying flora's neighbours, kept the changed neighbour as `#`. The round trip caught that it split trees on HomeTown, so it now keeps the flora piece instead. |

The review's findings, all fixed:
- **`plant()`:** an area edge could cut a tree (it now refuses), and an enclosed off-grid run could leave pockets.
- **The reach warning:** it missed pockets in newly opened ground, and diffed truncated explorations.
- **Extract:** it didn't verify flora's neighbours.
- **The in-game test:** its "offset first" sample assumed an even grid.
- **Cleanups:** per-grove tiling was O(groves·map), piece names were triplicated, and one design script carried a BOM.

Known limits:
- North and south forest edges step in whole trees (2 rows), because tree bands are 2 rows; west and east edges step a tile at a time. Vanilla mostly does the same; the horizontal offsets do the work.
- Route 203's north bank tree row (rows 0–1) is still one straight 54-tile line, the map's global straight-edge figure. It's a single tree row against the river bank, so softening it means redesigning the north bank. That's out of this milestone's scope.
- Only grass-route flora so far. Jungle hedges (Route 119), cut trees, land rocks on dirt or sand (`0E1`/`0E2`) and berry soil aren't vocabulary.

**Milestone 5: natural riverbanks, lake shores and beaches** (branch `milestone5-shorelines`, merged).

Route 203's river used to be a straight four-row band with ruler-straight banks. Now:
- **Width:** it varies from 3 to 6 tiles.
- **Banks:** grass promontories with rounded tips and reeds push in from the north. The south bank swings out into a bay on the outside of the bend, and a small creek-mouth bay sits below the east trail.
- **Beach:** the old sand flat is now a point-bar beach that the river bulges into.
- **Rocks:** two rocks stand mid-stream.
- **Scope:** the seams (rows 3–6 at both ends), the trail, the trees and the terraces are untouched. 181 cells changed, all within x 5–56, y 2–11.

Before/after: `dev/out/Route203_1_river_compare.png` (regenerate with `mapgen build`; `dev/out` is gitignored).

What was built (`dev/mapkit/shores.py`), using the ledge recipe: mine the pieces, resolve by shape, test against vanilla, a lab map, then an in-game test:
- **Shape resolver.** `gTileset_General` draws shores with one structure in two materials, a grass bank and a beach (table in `mapping_reference.md` §10). The resolver picks each water, beach-sand and grass-bank tile from its neighbours' shape. It replaces the learned vote at the water's edge, which only knew straight banks: it drew coves and convex corners with plain edges and stubs.
- **Sketch vocabulary.** `:` sand that touches `~` water becomes a beach, with the sand patch's grassy rim on its land side. `r` is a 2×2 rock in water. Shapes with no tiles are refused, naming the cells: one-tile channels, a bank turning into a beach at a corner, squeezed water, half rocks.
- **Extraction.** `extract` keeps (`#`) any shore cell that a compile wouldn't reproduce, so extract → compile never changes a shore block. That covers special water and vanilla's odd joins.
- **ShoreLab** (`design/maps/shorelab_design.py`): a dev-only 40×32 lakeside map with a river, a lake, an island, a cove, two kinds of beach and rocks. It uses every piece.
- **Dev bridge `MOVE`** (debug builds only): teaches party slot 0 a move. `Emu.teach_move`, `Emu.start_surf()` and `Emu.surfing()` let tests use Surf through the real field-move prompt.

Research first: no Gen 3 shoreline autotiler or free shore tileset turned up (Porymap has none; Porytiles compiles tilesets but doesn't place them). Vanilla's own General pieces cover banks, beaches and rocks, so no new art was needed for this step.

How it was verified:
| Area | Result |
|---|---|
| Vanilla agreement | 25,556/25,589 (99.9%) of vanilla's water/land meetings rebuilt from shape alone; all 265 beach-sand edges and 73 grass banks exact. |
| Shapes | 17/17 sketch shapes build or are refused as expected. |
| Round trip | Extract → compile leaves every shore block unchanged on ShoreLab, Route 203, Woodstock and 9 vanilla beach/river maps; ShoreLab and Route 203 do it from the shape tables alone (nothing kept). General round trip is at or above `develop` on every map (Woodstock 95.2→95.9%, Route 202 92.4→92.6%); ShoreLab, LedgeLab and Route 203 100%. |
| Checker | 18 maps, 0 errors. Vanilla baseline: 0 unexpected. |
| In-game shores | ShoreLab 276/276, Route 203 352/352: every land/water edge bumps on foot, comes ashore exactly where the model says, rocks block, and Surf works off sampled shores through the prompt. |
| Renders and play | Previews and in-game shots reviewed at each iteration (three design passes on Route 203). Conformance 516/516 (ShoreLab added), ledges unchanged (470/470, tours 8/8), the playthrough, doors, encounters and all three autowalks pass. Reconstruction unchanged at 87.8%. |
| Code review | `/code-review medium` raised 10 candidates; 8 fixed. Extraction could crash on a refused shape, its fixpoint loop could stop silently, and it compiled without the build's grammar. The round-trip test was circular; now our own maps must round-trip from the shape tables alone. A ledge directly below water is now refused. A commit mixed engine and tooling (split before merging). Two were not bugs: non-General layouts never have the water class, and a vertical bank/beach join on a straight stretch is the allowed seam. |

Known limits:
- Where a grass bank meets a beach on a straight shore, the join is a straight seam: there's no transition tile.
- Banks still step in whole tiles, because General has no diagonal bank pieces. "Natural" comes from varied widths, frequent one-row steps, rounded corners, beaches and rocks.
- Pond water (`o`, the brown-edged family) is still learned, not shape-resolved.

**Milestone 4: Route 203 terraces, the first real route built with ledges** (branch `milestone4-route203-terraces`, merged).

The design is in `design/maps/route203_design.py`:
- **Levee terrace:** the riverside meadow is a natural levee, one step above the valley floor. Its scarp has a west flank over the trail's first climb, a south edge with one stair step, and an east flank over the second climb. You can hop down onto the valley trail anywhere along it; the trail's two climbs (x 16–17 and x 38–39) are the ways back up.
- **Wooded bench:** in the west, the grove stands on a raised bench. Its south edge drops into the tall grass, and its east flank meets it with a plateau corner. You climb back up around the open west end or the north side.
- **Small moves:** the riverside stand moved up 2 tiles to make room, and the sand flat lost 2 columns so it stays clear of the trees.
- **Scope:** 116 cells changed, all within x 2–37, y 7–21. Connections, seams, encounters and events are untouched.

Tooling added:
- **`mapgen build` diffs against the current map:** it reports the changed cells and writes `dev/out/<Map>_preview_diff.png` (before and after, cropped, changes outlined).
- **`ingame_ledges.py` terrace tour:** on maps without NPCs, for each ledge group it starts from the entrance, jumps down, and walks back on foot, screenshotting each landing. It fails on groups that are jumpable but unreachable, on traps, and on bad warps.

How it was verified:
| Area | Result |
|---|---|
| Checker | Route 203: 0 errors, 0 warnings. All 17 maps: 0 errors. Vanilla baseline: 0 unexpected. |
| Ledge approaches in mGBA | Route 203: 92/92 (39 jumps, 53 refusals). LedgeLab still 150/150; vanilla still 228/228. |
| Terrace tour | Route 203: both groups jumped and climbed back. LedgeLab: 6/6 groups. |
| Round trip | Extracting and recompiling Route 203 reproduces 100% of its blocks, ledges included. |
| Play | New-game walks from the player's house through Route 203 to both exits (Route203_1_2, Route101_2), and back from Route 101 to Fredericton. |
| Code review | `/code-review medium` raised 10 findings, all in test tooling or efficiency, none in the map. 9 fixed; the triple map load in `ingame_ledges.py` was left as is (it costs milliseconds). The failure paths were checked offline on a sealed LedgeLab. |

**Milestone 3: ledges in the map pipeline** (branch `milestone3-ledges`, merged).

**Sketches:** draw ledges with `v` (jump south), `<` (jump west) and `>` (jump east). `mapgen` assembles them from vanilla's 13 `gTileset_General` pieces:
- end caps, plateau corners and one-tile stair steps;
- ends that run off the map edge or under a cliff without a cap, as vanilla does.

It refuses sketches it can't build, naming the cells to fix: branching or stacked ledges, and any jump that would land on a tree, water, a solid tile, or off the map. The game never checks the landing tile, so these would be real bugs.

**Checker:** two new checks work on any map, hand-painted ones too:
- `ledge`: a reachable jump that lands somewhere bad.
- `trap`: tiles you can jump or walk into but never leave, i.e. a soft-lock.

Every `mapgen` build runs the checker in memory, and `--apply` refuses a result with *new* errors (`--force` overrides).

**Inspection:** the renderer draws each ledge's jump direction as an arrow, and a `traps` overlay tints dead ends. `render_map.py --crop` zooms in.

**New tool:** `dev/new_map.py` makes a blank outdoor map to sketch on.

**LedgeLab** (`design/maps/ledgelab_design.py`) is a dev-only 32×28 terraced meadow that uses every piece. It isn't linked into the world; tests warp in.

How it was verified:
| Area | Result |
|---|---|
| Vanilla ledges | Rebuilt piece for piece: 66/66 groups. The other 16 meet cliffs, which is future vocabulary. |
| Ledge approaches in mGBA | Every approach to every ledge matches the model (tile and elevation): LedgeLab 150/150; Routes 102, 103, 116 and 123: 228/228. |
| Round trip | Walks down LedgeLab's ledges and back. |
| Trap check | Exactly one vanilla trap (Shoal Cave's ledge pocket, confirmed blocked in-game). It catches a sealed LedgeLab. |
| Existing maps | No existing map's data changed. |
| Code review | `/code-review medium` raised 10 candidates. All were valid and fixed. The most important: `--apply` blocked any map with old errors; every `MAP_DYNAMIC` warp was excused; the in-game test could skip cases silently. |

The first slice, **HomeTown → Route 201 → Woodstock** (milestone 2), is a small playable experience:
- **New game:** you wake in the player's house in HomeTown, a quiet forestry/mill village (provisional).
- **Starter intro (temporary):** a field researcher from the Woodstock wildlife station stands by the exit.
  - Leave without a Pokémon and they call you back.
  - Talk to them to pick a starter from the bag (no battle) and get 5 Poké Balls.
  - Later they heal your party.
  - The scene is self-contained in `data/maps/HomeTown_0/scripts.pory`, so a real intro can replace it.
- **Route 201:** wild Pokémon, with a Maritime-flavoured table (proposal).
- **Woodstock:** every door leads to an empty placeholder interior; the lab is a possible wildlife research station.
- **Names:** the map popups read HOMETOWN, ROUTE 201, WOODSTOCK (provisional).

Tom's decisions so far: forestry/mill HomeTown; possible wildlife station in Woodstock; starter received in HomeTown before Route 201. Names and story details stay provisional.

## Still missing in the slice (`dev/section_status.py HomeTown_0 Route201_1 Woodstock_2`)
- No NPCs on Route 201 or in Woodstock, and no Woodstock town sign.
- Starters are still Treecko/Torchic/Mudkip (`GRASS/FIRE/WATER_STARTER` in `src/starter_choose.c`).
- No Town Map squares for the new map sections (there's no Maritimes region map image yet).
- The fishing guard (`CanFish`, empty party) is checked by the build only: no rod can be obtained in the slice.
- Nobody has played the intro by hand yet: check the dialogue and the fade into the starter bag.

## Engine changes (all small; marked `Maritimes:` in the source)
| Change | Where |
|---|---|
| No wild battles while the party is empty | `src/wild_encounter.c` (StandardWildEncounter) |
| No fishing while the party is empty | `src/item_use.c` (CanFish) |
| `ChooseStarterNoBattle` special: the starter bag without Birch's rescue battle | `src/battle_setup.c`, appended to `data/specials.inc` |
| Dev bridge (debug builds only): WARP, FLAG, GIVE, MON0, MOVE | `src/field_control_avatar.c` |
| Own map sections, appended so no MAPSEC id moves | `src/data/region_map/region_map_sections.json` |

## Regression set (run before merging anything)
```
dev/fastbuild.py
dev/check_maps.py --baseline          # 0 unexpected, 7 known
dev/check_maps.py                     # 19 maps, 0 errors (the 1 WARN is Fredericton's 8 dead doors)
dev/tests/conformance.py              # 562/562 (seeded samples; the count moves when a map changes)
dev/tests/playthrough_slice1.py       # end to end, wild battles on
dev/tests/ingame_doors.py HomeTown_0 Woodstock_2
dev/tests/ingame_encounters.py Route201_1 [--no-party]
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route203_1_2
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route101_2 Route203_1 Fredericton_0
dev/tests/ingame_ledges.py            # LedgeLab, Route 203 + 4 vanilla routes: 470/470 approaches, tours 8/8 groups
dev/tests/ingame_shores.py            # ShoreLab + Route 203: 624/624 edge cases (bump, land, rock, Surf prompt)
dev/tests/ledge_pieces.py             # no emulator; PASS
dev/tests/shore_pieces.py             # no emulator; PASS (vanilla 99.9%, 17/17 shapes, shore round trip)
dev/tests/flora_pieces.py             # no emulator; PASS (vanilla flora, 14/14 shapes, round trip, 300 plantings)
dev/tests/ingame_flora.py             # GroveLab + Route 203: 296/296 (flora pieces, staggered edge trees)
dev/tests/reconstruction.py           # 87.8%; only when mapgen/terrain code changes
dev/tests/roundtrip.py                # 88-100%; only when mapgen/terrain code changes
```

## Next milestone (proposed, not started)
1. **Apply the landscape kit to the first slice (recommended next):** Route 201 and the woods around HomeTown and Woodstock. These are the maps a new player sees first, and the forestry theme suits sapling stands and clearings. Do it as separate, reviewable diffs, Route 203 style: scope each to a box, use `KEEP` sets, and read the reach and metric lines. Tom hand-mapped Fredericton and Woodstock, so propose before touching them. Route 203's north bank and levee meadow (the 54-tile straight tree row) are a small follow-up.
2. **Cliffs (`070/071`):** these also unlock the 16 cliff-ledge joints, terraces taller than one ledge step, and the elevation variety a "hills" biome needs. Rocky shores (`17A–184`) and the dirt/sand boulders (`0E1`/`0E2`) fit here too.
3. **Shore follow-ups:** apply shores to Woodstock's and Fredericton's rivers; resolve pond shores by shape; add a bank-to-beach transition tile (Porytiles) to soften the straight seam.
4. **NPC/sign scaffolding tool:** close the slice's people and sign gaps without hand-editing JSON. Route 203 now has natural spots for a hiker in the middle grove's notch, a fisher on the beach, or a sign.
5. Later:
   - Porytiles for Maritime flora: spruce/fir trees for a boreal look, birch, log piles, a covered bridge. Vanilla's broadleaf trees are all the General tileset offers.
   - A Maritimes Town Map.

Ideas, not done:
- A `--tour` start option for maps with NPCs.
- Flower and boulder accents on the terraces (the vocabulary has them now).
- A `landscape.path()` helper for wandering dirt paths and clearing floors (vanilla's Safari Zone style).

## Gotchas learned
- **Test mode:** `Emu.test_mode()` means movement-only: no wild battles, no trainer sight, and story gates open (it sets `FLAG_SYS_POKEMON_GET`). Call it before the player enters the gated map; HomeTown arms its gate on map load. Tests that play as a real player (the playthrough, encounter tests) don't call it.
- **Poryscript:** edit `scripts.pory`, never the generated `scripts.inc`. `fastbuild` copies the generated `.inc` back so git tracks it.
- **Specials:** append new specials at the end of `data/specials.inc`; their ids are positional.
- **Map sections:** add them only with `dev/name_area.py` (appends). Gen 3 popups size their theme table automatically; BW-style popups would need entries.
- **Deprecated globals:** `gPlayerParty`/`gPlayerPartyCount` are deprecated in expansion 1.17.2. Use `gParties[B_TRAINER_PLAYER]` / `gPartiesCount[B_TRAINER_PLAYER]`.
- **Workflow:** each milestone goes on a branch, gets `/code-review medium <branch>`, has its findings fixed and re-verified, then merges into `develop`. Every review so far has found real bugs.
- **Planting on an existing map:** give `plant()` the grid of the forest you edit; Route 203's southern forest starts on row 29, so it uses `parity=(0, 1)`. Keep areas to whole 2-row bands, and never let two `plant` areas overlap. If an old grove straddles two areas, clear it across both first: `plant` refuses to leave a tree cut in half. Check that the diff box stays inside your scope; a stray tuft or a re-tiled tree column shows up there.
- **Flora placement:** a flower, boulder or sapling right above a tree sits on the canopy overhang, and the compiler refuses it. `landscape` helpers already avoid that row.
- **Ledge landings:** the game never checks where a jump lands. Draw ledges in sketches, not by hand; for hand-painted ledges, trust `check_maps.py`'s `ledge` and `trap` results.
- **Dev maps:** LedgeLab sits in `gMapGroup_DevMaritimes`. It ships in the ROM but nothing links to it. Its only warp is a spawn point (`MAP_DYNAMIC`, arrival-only), which gives the checker an entrance. `new_map.py` adds that spawn to every new map; delete it once the map has real connections.
- **Editing an existing map with mapgen:** build without `--fresh` so the existing trees stay put. Read the diff report and `_preview_diff.png` before `--apply`. Move groves by an even number of tiles; an odd shift falls off the 2×2 tree grid and drops trees (`dropped_tree_cells`).
- **Commit order:** a test that expects new map content goes in a commit *after* that content, so every commit passes the regression set.
- **Shores:** draw water at least two tiles wide, and start beaches on straight stretches of shore, not at corners; the compiler names the cells otherwise. To look natural, change a bank by one row at a time and often. Sand next to water becomes a beach automatically. Tall grass, paths and trees still get a grass margin from water.
- **Surf in tests:** warping onto water starts Surf by itself. To surf off a shore as a player would: `give_mon`, `teach_move("SURF")`, set `FLAG_BADGE05_GET`, face the water, then `start_surf()`.
- **Commit messages from PowerShell:** `Out-File -Encoding utf8` writes a BOM into the subject line. Write message files with `[IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
