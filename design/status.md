# PokéMaritimes: project status (handoff)

> Updated 2026-11-06 (Milestone 16, the start valley). Read this first in a new session. The world's geography and
> the corridor plan live in `region_blueprint.md`; the creative brief in `region_plan.md`; tooling
> in `../dev/README.md`; engine facts in `mapping_reference.md`.

## Where we are
**Next session: Milestone 17, Route 202** (proposed below, not started; Tom asked to hold it until
he says go). M16 is merged into `develop` as `8f3f5872b6`, pushed to `origin/develop` (Tom okayed,
2026-11-06) and on the phone. Read `region_blueprint.md`, then "Next milestone" below.
Before any map work: `dev/corridor.py check` (0 errors, 0 warnings). The merge gate is
`dev/regression.py` (must end `0 failed`; quote its evidence lines). A redesign of a map saves
may stand on needs a world revision (below).

**Milestone 16: the start valley, HomeTown and Route 201 along the Meduxnekeag** (branch
`milestone16-start-valley`). Both maps rebuilt from the plan's underlays at the plan's sizes, so the
corridor's first three maps now stand on the plan of record end to end. Renders and in-game:
`dev/out/m16/start_valley.png` (the three maps stitched), `before_*_context.png` /
`after_*_context.png` (the seams), `ingame_sheet.png` (twelve spots, both gates),
`world_revision_m15_home.png` (the negative control).

**HomeTown** (`design/maps/hometown_design.py`, 36x26 -> 34x28): the border hills close the west and
north; the Meduxnekeag comes down out of them as a brook, opens into the mill pond (a boulder in
it) and runs east to Route 201 (seam rows 16-19). The player's house and the Leblancs' on the lawns
of the south-west bank (rooms and warps 0-1 kept), their gardens, yard trees, the lane; the road
steps down the valley floor and leaves east (rows 24-25). The sawmill (a `house_wide` stamp, new
room `HomeTown_Sawmill` with a sawyer) on the bench across the brook, a ledge from its bench to the
pond shore, a plank footbridge over the outflow. **The exit gate** is now every walkable tile of
the east column (x 33: rows 14-15, the trail along the brook's far bank, and 20-26, the road side;
nine coord triggers); the researcher stands by the road at (31,22) facing east and the step back is
`walk_left`. `tests/hometown_gate.py` proves on the model that nothing leaves without crossing one.

**Route 201** (`design/maps/route201_design.py`, 50x20 -> 52x28): the Meduxnekeag runs east the whole
way (seams: HomeTown rows 14-17, Woodstock 16-19), swinging north into a meander. Two ways along
the valley, as the real one has:
- the road on the south bank (seams rows 22-23), arching gently up the intervale: the farm (a
  `house_oldale` stamp, new room `Route201_Farmhouse` with a farmer), hay fields (tall grass),
  hedgerow groves, a gravel bar on the inside of the bend; the south slope wooded in segments on
  the tree grid each stretch's verge allows, with stepped bays;
- the riverside trail on the north bank, for explorers: a meadow under the hardwood slope whose
  ledge drops onto the trail where Bug Catcher Ross waits, the glade above the bridge as a terrace
  (two ledges, the trail climbing through its middle), the regrowing cutblock (the forester), the
  beaver pond (its lodge a rock; the hidden Potion in the nook east of it), then along the bank
  into Woodstock's north bank;
- a plank bridge on the farm lane joins them.
The crossing is 53 steps with no forced tall grass and no forced trainer, as before. The route sign
moved to the road out of HomeTown and points east (`{RIGHT_ARROW} WOODSTOCK`).

**Road material:** one, Woodstock's light path (`=`), from HomeTown's lanes to Woodstock's highway
(the old logging road's sand is gone).

**Tooling:**
- **`dev/corridor.py join "<Map>" [--apply]`:** makes the game's connections between a planned map
  and its built neighbours the plan's, both sides, a direction included (HomeTown's seam turned
  from down to right, which `resize_map --connect` can't do); refused until each folder has the
  plan's size; rolls back on failure. `tests/corridor_join.py` (3 fixture tests).
- **Compiler fix, tree tiling (`mapkit/sketch.py` `_tile_trees`):** leftover edge cells were paired
  greedily from x = -1 / y = -1, so a half tree in the top band at the right edge was taken as cut by
  the top border (orphaning its lower cell), and a row of tree tops along the bottom edge read from
  x = -1 paired every top with the wrong neighbour. Single-border cuts now go before corners.
- **Two design lessons** (in the scripts' comments): groves must be whole 2-row bands on the tree
  grid or `plant` drops them silently (the first Route 201 draft lost every valley grove that way,
  and an area that excluded the valley floor hid it); and the gate test's first draft passed its
  per-trigger checks vacuously (closed tiles given in the wrong coordinate frame closed nothing),
  which its "with everything closed" check exposed; it now asserts the tiles are obstacles.

**Save compatibility: SAVES CARRY OVER** (save line 2, no layout change). World revision 2: a save
made before M16 standing on HomeTown continues once on the lane below the player's doormat (9,15),
one on Route 201 on the road by the sign (5,22); saves inside houses continue where they were (the
doors lead out to the moved doors). Proven against the M15 phone build (`2026-11-06_3a43be36ca`,
kept with its `.map` in `dev/out/m16/oldrom/`) and the build before it (`dev/out/m15/oldrom/`):
`ingame_world_revision.py --old-rom dev/out/m16/oldrom/PokeMaritimes_save2.gba --old-rom
dev/out/m15/oldrom/PokeMaritimes_save2.gba` 92/92. **Negative control:** the same M15 HomeTown save
on a build without the M16 rows continues at (9,10), inside the walls of the player's new house,
unable to move, with the wandering boy outside his range.

**Code review** (`/code-review medium`): 10 findings, all fixed.
- **`join` did half its job:** it rewrote the plan's joins but never removed an edge connection to a
  built planned map the plan no longer puts alongside (`check` still listed it). It now removes
  them on both sides (the Route 202 dry run drops the prototype's Fredericton join, as `check`
  asks); a fixture test covers it. It also closed no files and duplicated `check`'s folder and
  edge logic (now shared: `folders`, `edge_joins`).
- **The gate test ignored elevation:** a coord event fires only for a player at its elevation (or
  0; `field_control_avatar.c`), so a trigger on another elevation would be closed in the model and
  open in the game. All nine match today (3 on 3); the test now asserts it per trigger.
- **World revision test:** rows were kept one per map (a second redesign of HomeTown would have
  overwritten the first); now a list, and a save's safe tile is the last row newer than it, as
  the engine applies them. Its "people at home" check had become vacuous at Route 201's safe tile
  (nobody within view): it now walks, without a reload, until someone's home is in view (over the
  bridge to Bug Catcher Ross) and requires an active person. The old build's revision is read in
  the first case's emulator (one boot fewer), the rows parsed once.
- **Roundtrip's guard case** could index past the bottom row; it now picks sand with room below
  or fails with a message.
- **Tree tiling pass 2** scanned the whole box three times; it now visits only the border lines
  (same tiles: every map byte-identical, roundtrip and flora unchanged).
- **History:** the branch's first commits mixed map data with tooling and applied the join before
  its tool, leaving commits with redesigned maps and no world revision (a bisect hazard for real
  saves). The unpushed branch was re-layered: tooling, engine, map data, tests, docs.
- A duplicated comment in the HomeTown design script.

How it was verified (the gate: `milestone16-start-valley @ b8ed441ab5`, clean tree, ROM `2fd03fa9…`,
**49 gates passed, 2 observed, 0 failed**; report `dev/out/regression/20261106_180823_899300/`):
| Area | Result |
|---|---|
| Static | checker 40 maps, 0 errors (5 warnings as before); vanilla baseline 0 unexpected; corridor 7 maps, 0 errors, 0 warnings (the start valley's joins match the plan; only Route 202/Fredericton's remain to change); hometown_gate PASS (9 triggers, each needed, each at its tile's elevation, each step back walkable); corridor_join 4 tests; id budget, save layout (no layout change) |
| Pieces | round trip 91.7-100% (HomeTown and Route 201 now 100%, from 87.5% and 100% as hand/old maps; 2 guards PASS, the terrain guard on Route 201's gravel bar); reconstruction 87.8% (observed); ledge, shore, flora, stamp, bridge pieces PASS |
| Routes | crossings 53, 53, 30, 30 steps, 0 forced tall grass (observed): Route 201 plays the same length as before, 83 reachable tall grass |
| In-game | conformance 547/547; playthrough (both gates call the player back; starter; Route 201 to Woodstock and back; heal); doors 20 round trips (HomeTown 3 with the sawmill, Route 201's farmhouse); buildings 22/22; respawn 3 real losses; world revision 35/35 in the gate, 99/99 with `--old-rom` for the M15 phone build and the one before; bridges 134/134 (HomeTown's and Route 201's decks found from their sketches); events 134/134 on 10 maps (HomeTown 23, Route 201 21, the sawmill 4, the farmhouse 4); ledges 509/509 on 8 maps (Route 201's tour 3/3 groups); flora 447/447; encounters 12 battles; four autowalks; save 45/45; shores 624/624 |
| Negative controls | the M16 rows removed: an M15 HomeTown save continues inside the walls of the new house at (9,10), the wandering boy out of range; the gate test's per-trigger checks (any one trigger dropped opens a way out) |

**Merged** into `develop` as `8f3f5872b6` and pushed to `origin/develop` (Tom okayed, 2026-11-06). **Phone build
published:** `2026-11-06_8f3f5872b6`, ROM sha256 `2fd03fa974c112a5…`, save line 2; `dev/mobile.py
--full` 10/10 in mGBA (new game, save, CONTINUE, the play ZIP, the slice playthrough, byte-identical
ROM); Google Drive confirmed `PokeMaritimes_save2.zip` and
`builds/PokeMaritimes_2026-11-06_8f3f5872b6_save2.zip`. **SAVES CARRY OVER** (same play file name).

**Builds stay recoverable** (Drive's `PokeMaritimes playtest/builds/` keeps every published build
zipped with `build.txt`; `dev/mobile.py --status` lists them; a commit rebuilds its ROM byte for
byte). Local copies with their `.map`, which `ingame_world_revision.py --old-rom` needs (gitignored;
keep them away from `dev/out/mobile`, which the gate's publish test rewrites):
| Build | ROM sha256 | Drive (`builds/`) | Local, for `--old-rom` |
|---|---|---|---|
| **Current: M16** `2026-11-06_8f3f5872b6` | `2fd03fa9…` | `PokeMaritimes_2026-11-06_8f3f5872b6_save2.zip`, and the play file `PokeMaritimes_save2.zip` | `dev/out/m17/oldrom/` (M17's old build: boots, new games on revision 2) |
| **Previous: M15** `2026-11-06_3a43be36ca` | `c6300120…` | `PokeMaritimes_2026-11-06_3a43be36ca_save2.zip` | `dev/out/m16/oldrom/` |
| Before that: `2026-11-05_fb2b9673ff` | `7df037fe…` | `PokeMaritimes_2026-11-05_fb2b9673ff_save2.zip` | `dev/out/m15/oldrom/` |
To play an older build on the phone: unzip it from `builds/` and load the ROM inside (a save made
on the current build stays with the current play file).

Known limits:
- **Visual:** the creek's banks step in straight runs (the shore kit has no diagonal bank piece);
  the meander still reads somewhat geometric at the apex. The sawmill is the Petalburg wide house
  (its garden and hedge read as a farmstead) until Porytiles brings log piles and a saw.
- **The gate:** nine coord triggers on HomeTown's east column, not a natural choke (the brook's
  far bank is a trail into Route 201). `tests/hometown_gate.py` guards any redesign.
- **Route 201's safe tile** has nobody within view; the world revision test walks to Ross to check
  people, which is slower than the other cases.
- All new text (the sawyer, the farmer, the sign) is provisional and unread in-game by Tom.

**Milestone 15 done: Woodstock, the confluence town** (branch `milestone15-woodstock`). The first
corridor map rebuilt from the plan of record: 48x42 at 0.5 km a tile, Woodstock at world (0, 0).
Before/after and in-game: `dev/out/m15/before_after.png`, `ingame_sheet.png` (nine spots),
`before_Woodstock_context.png` / `after_Woodstock_context.png` (the seams), `bridge_Woodstock_2_0.png`
(on the deck), `migrated_old_save.png` vs `negative_control_no_migration.png`.

**The town** (`design/maps/woodstock_design.py`, from `corridor.py underlay "Woodstock"`):
- **Geography:** the Saint John down the east side from real data (the underlay's river, two
  rocks); the Meduxnekeag in from Route 201's seam (rows 30-33), east along the valley floor and
  widening into its mouth at downtown, as the real one does; downtown on the point between them,
  on the west bank; the far bank wooded; north, woods toward Hartland (later).
- **Streets:** the highway keeps to the creek's south bank (Route 201's seam at rows 36-37, Route
  202's at columns 25-26). Main Street runs north from the junction over the Meduxnekeag on a
  plank bridge (the real Main Street crosses at the mouth) into downtown and ends at the north
  edge, where a sign says the trail to Hartland is closed. Water Street is the first street over
  the bridge, King Street the one uphill.
- **Buildings (stamps):** Water Street: the Pokémon Center by the river (the corridor's first:
  `HEAL_LOCATION_WOODSTOCK_2`, so the slice has a real respawn point) and the Mart, the wide house
  beyond. King Street: the wildlife station by the river, the garden house and its community
  garden, a new two-storey house (`Woodstock_House3_1F`/`2F`; a farmer from up past Hartland).
  The station and both houses kept their rooms, people and warp ids (0-2); the Center, Mart and
  house are warps 3-5. Groves on both banks, flower beds, the riverside green.
- **Events** (`Woodstock_2.events.toml`, re-placed): the town's five people and the item ball at
  new spots, the town, station and garden signs, and two new ones: the Meduxnekeag at the bridge
  ("It joins the Saint John right here.") and the closed trail north. Text provisional.
- **Seams:** interim offsets line up today's prototypes: Route 201 at 22 (the plan: 14), Route
  202 at 7 (the plan: 16), until M16 and M17 rebuild them on the plan (`corridor.toml` notes it;
  `corridor.py check` lists them as plan changes). Accepted until then: the creek meets Route 201's
  woods; the 6-wide Saint John meets Route 202's 2-wide river behind woods, out of reach and view;
  Route 201's sand road becomes Woodstock's light path at the seam.

**Tooling added:**
- **`dev/resize_map.py`:** resizes a layout, moves people, warps, signs, triggers and heal
  locations with the terrain (refused if one would fall off), re-offsets both sides of each
  connection (or `--connect` sets one), reports scripts and tests that name the map and the save
  question; rolls back on failure. `tests/resize_map.py` (5 fixture tests).
- **Bridges** (`mapkit/bridges.py`, sketch `H`): Route 104's plank deck over river water, for a
  road crossing north-south; the deck reads as water to the shores. Refusals name the cells.
  Research: no bridge exists in General or Petalburg; vanilla's are in Mauville, Fortree and
  Rustboro (`mapping_reference.md` §15).
- **`dev/tile_import.py` / `mapkit/tileimport.py`:** copies vanilla metatiles between secondary
  tilesets (tiles deduplicated, palettes into an empty or identical slot, layers and attributes
  as they are; appends only). Petalburg gained the deck: 3 tiles, palette 11, metatiles 290-293;
  every existing map on it draws as before. `tests/bridge_pieces.py` (31 checks, from a fixture
  copy of vanilla Petalburg).
- **World revisions** (engine, `src/overworld.c` `sWorldRevisions`; `VAR_MARITIMES_WORLD_REVISION`,
  was `VAR_UNUSED_0x4083`): a save made on a map since redesigned continues once at the map's safe
  tile (its heal location) through vanilla's continue-game warp, with a full map load. Measured
  first: the published phone build's save on old Woodstock's green, CONTINUEd without it, lands
  inside the new wide house, with the people where the old save had them (the angler on the old
  pond's shore) and the old town's cliff and steps pasted around the player from the saved view.
  With it: in front of the Center, people at their new homes. Also fixes M14's limit "a Center
  that moves leaves a save made at the old spot unmatched" (the respawn point is re-pointed).

**Save compatibility: SAVES CARRY OVER** (save line 2, no layout change). A phone save standing
in Woodstock continues once in front of the new Pokémon Center; a save anywhere else, or inside
a Woodstock house, continues where it was made (the houses' doors lead out to their new spots).
**Merged** into `develop` as `3a43be36ca` and pushed to `origin/develop` (Tom okayed, 2026-11-06). **Phone build
published:** `2026-11-06_3a43be36ca`, ROM sha256 `c6300120dba7ed45…`, save line 2;
`dev/mobile.py --full` 10/10 in mGBA (new game, save, CONTINUE, the play ZIP, the slice
playthrough, byte-identical ROM); Google Drive confirmed the upload of `PokeMaritimes_save2.zip`
and `builds/PokeMaritimes_2026-11-06_3a43be36ca_save2.zip`. Same play file name, so My Boy! keeps
the save.

**The previous playable build stays recoverable** (the last one before M15, `2026-11-05_fb2b9673ff`,
ROM sha256 `7df037fe…`):
- on Drive: `PokeMaritimes playtest/builds/PokeMaritimes_2026-11-05_fb2b9673ff_save2.zip` (the ROM
  under its play name plus `build.txt`); to play it on the phone, unzip it and load that ROM (a save
  made on the M15 build stays with the M15 play file);
- in git: commit `fb2b9673ff` on `develop` (the foundation-hardening merge); building it reproduces
  the ROM byte for byte (done in this milestone);
- locally (gitignored): `dev/out/m15/oldrom/PokeMaritimes_save2.gba` with its rebuilt `.map`, which
  `tests/ingame_world_revision.py --old-rom` needs. WSL `~/maritimes-oldbuild` is the mirror that
  rebuilt it (disposable; delete it to free space).

**Code review** (`/code-review medium`): 10 findings, all fixed.
- **Saves beside the seam:** an old save on Route 201 or 202 near Woodstock's seam would paste
  its saved view of the old town into the connection strip (the view reaches past the map's
  edge). Every save made before the current revision now drops its view. Negative control with
  the published build's save: 64 cells of old Woodstock pasted over the new one; with the fix, none.
- **Extract and bridges:** an end cell's error (tall grass at a deck's end) was dropped, so a strip
  a compile refuses stayed `H`; later extract passes could leave half a strip. Errors now blame
  their strip, and the strips are re-checked after every pass.
- **Tile import:** a palette slot counted as free if the secondary didn't use it, ignoring primary
  metatiles drawn with slots 6-12; a copied tile could reuse one an animation overwrites inside
  the PNG (destinations now parsed from `tileset_anims.c`); the PNG was assumed 128 wide.
- **resize_map:** `--connect` applied to every connection to a neighbour (now `NEIGHBOUR:DIR` when
  it joins on two sides); `--apply` didn't compare with the preview (now refuses a changed plan);
  the reference scan ran twice and called `samefile` on every file; `OPPOSITE` and a flood fill were
  duplicated.
- **Found while fixing:** `LoadSavedMapView` clears the view after pasting it, so the first test's
  "view dropped" check passed regardless (vacuous); it now compares the strip the game holds with
  the new town's blocks. And the gate's mobile publish test rewrites `dev/out/mobile/check.gba`, so
  the "old ROM" there became the new one mid-session: the old build now lives in
  `dev/out/m15/oldrom/` with its `.map` rebuilt from `fb2b9673ff` (byte-identical ROM, `7df037fe…`).

How it was verified (the gate: `milestone15-woodstock @ f1c21fc2be`, clean tree, ROM `c6300120…`,
**45 gates passed, 2 observed, 0 failed**; report `dev/out/regression/20261106_144337_719700/`):
| Area | Result |
|---|---|
| Static | checker 38 maps, 0 errors (5 warnings: Fredericton's dead doors, the Centers' upstairs as vanilla's); vanilla baseline 0 unexpected; corridor 7 maps, 0 errors, 0 warnings; id budget 17/17; save layout matches (no layout change) |
| Pieces | bridge_pieces 37/37; resize_map 7 tests; stamp, shore, flora, ledge pieces PASS; round trip 87.5-100% (Woodstock 100%: 2016/2016 blocks, its 562 shore blocks unchanged, its 6 stamps and doors recognised); reconstruction 87.8% (observed) |
| Routes | crossings 52, 51, 30, 30 steps, 0 forced tall grass (Woodstock: Route 201 ↔ Route 202 in 30 steps either way) |
| In-game | conformance 545/545; doors 18 round trips (Woodstock 6 with 2 upstairs); buildings 22/22 (Woodstock's Center sets `HEAL_LOCATION_WOODSTOCK_2`, the nurse heals, the Mart sells); bridges 38/38; world revision 13/13 (35/35 with `--old-rom dev/out/m15/oldrom/PokeMaritimes_save2.gba`); events 126/126 on 8 maps; respawn 3 real losses; save 45/45; playthrough; four autowalks; ledges 490/490; shores 624/624; flora 435/435; encounters 12 battles |
| Negative controls | the migration disabled: an old Woodstock save lands inside the wide house with the old people and terrain (21/29); the view clear disabled: 64 cells of old Woodstock in Route 201's strip; 15 harness guards |

**Test infrastructure reliability (2026-11-06):** branch `test-infrastructure-reliability`
merged into `develop` as `3abcbb3b8b` and pushed to `origin/develop` (Tom okayed). The last
foundation item from the independent audit before Woodstock. Tooling only: the ROM is
byte-identical to the published phone build (`7df037fe…`), **no save break**. After the merge,
`dev/mobile.py` verified 9/9 in mGBA (new game, save, CONTINUE, the play ZIP, byte-identical ROM)
and uploaded nothing: the phone build `2026-11-05_fb2b9673ff` is already this ROM, so saves carry
over. Codex drafted most of the work uncommitted on the branch; Claude verified it, closed the
gaps below, and documented it. Codex's audit report itself isn't in the repo (only the summaries
here); if it lists findings beyond these, they haven't been assessed.
- **One gate:** `dev/regression.py` runs the whole regression set serially with per-step logs, an
  evidence line per step (its counts), and a JSON report (commit, dirty tree, ROM sha256).
  OBSERVED metrics (reconstruction, route numbers) are never counted as passes.
- **No silent passes:** tests fail on zero coverage; conformance had been counting a warp that
  landed elsewhere as agreeing (now a failure); the runner checks the claimed counts, not only
  exit codes.
- **No emulator interference:** each emulator gets a private bridge script, port and session
  token, and each test its own ROM/save folder. Added here: a step that times out or is
  interrupted is killed with its process tree (the old runner left mGBA running, shown by a
  negative control), one run at a time (OS lock), a warning when other mGBA processes are
  open, and a sweep of scratch folders from killed runs.
- `tests/harness_guards.py` (13 negative controls) and `tests/emulator_isolation.py` (two live
  emulators side by side) prove these.
- **The gate caught a real flake:** a re-run failed `ingame_events` 113/114, "the wandering child
  could not be talked to in 8 attempts" (M14's one unexplained failure was likely the same).
  Logging each attempt showed that a warp reloads the map and puts every object back on its
  home tile, so the test had been aiming at where the child stood *before* the warp, and it
  pressed A before the player's turn had finished. It now talks to the child at home and waits
  for the turn: 10 runs in a row pass, worst case attempt 5 of 20 (before: up to 17).
- `/code-review medium` raised 10 findings: 8 fixed, 1 kept by design, 1 documented as a limit.
  **Fixed:** `Emu.close()` could raise over a test's own error (now warns); the bridge port came
  from Windows' ephemeral range, where an outgoing connection could take it before mGBA bound it
  (now 20000–48000); a build timeout left `make` running inside WSL (the runner now stops it, and
  the build's timeout is 30 min for full rebuilds); shores and flora counted a map with no cases
  twice and could print a negative total; fresh test slots piled up until exit (the previous is
  removed) and a save-release wait sat on a path where it could never run; the buildings test
  duplicated the gate's TownLab rule; the ledge test re-derived the tour's skip rule; the
  isolation test bypassed the suites' own `prepare_rom`. **Kept:** conformance fails a warp that
  lands elsewhere (its start tiles come from the model's own arrival prediction, so a move is a
  real disagreement). **Limit:** the dev bridge's WARP takes signed 8-bit coordinates, so
  conformance can't sample tiles past x or y 127 (only vanilla Route 119 today; reported as
  untestable). A corridor map that long would need a 16-bit WARP (an engine change).

**Foundation hardening complete (2026-11-05):** branch `foundation-hardening` merged into
`develop` as `fb2b9673ff` and pushed to `origin/develop`. No other milestone has started.
Tom requested fixes to the independent review's highest-priority findings before the Woodstock
redesign. Scope: initial/legacy-zero respawn, shared-layout editing safety, generated floor/name
collisions, and rollback for failed authoring commands. No world redesign or new gameplay content.

Authoring changes: changed shared terrain is refused (including distinct layout IDs aliasing one
block file); `dev/unique_layout.py <Map> [--apply]` explicitly detaches one map with identical
blocks/border and unchanged events/map IDs. Standard copied rooms can keep their shared templates
until customization. Porymap bypasses the Python guard: detach before editing shared terrain there.
Building plans reserve all generated floors/constants, including orphan registered names/folders.
Source edits for maps/rooms, events/IDs, area names, layout copies and attribute batches roll back
on exceptions/Ctrl-C. This is not recovery from power loss/process termination or concurrent edits.

Respawn changes: new games initialize the existing home heal location; CONTINUE repairs an
all-zero heal location in older saves while preserving any valid Center choice. No save layout,
map ID, or heal-location ID changed; **no save break**. Three actual trainer defeats in mGBA
(fresh, repaired legacy, saved Center) confirm the destination, healed party, and returned control.
The pre-fix M14 ROM, under the same real-loss scenario, whiteouts to Petalburg City with an
all-zero fresh heal location; this reproduces the original defect directly.

Verification: 20 authoring success/fault-injection tests pass; new shared-layout/collision tests
fail against the original `develop` implementations. The build, save-layout v2 check, var-macro
check, all 20 static regression commands and all 17 emulator regression commands passed
(including conformance, real-play slice, four autowalks, doors/buildings, encounters, ledges,
events, save, shores, flora and scratch mobile-publish test). Checker: 33 maps, 0 errors;
baseline: 0 unexpected and 8 known. A separate read-only review found a detachment idempotence
edge case, now fixed and tested, and no remaining actionable findings. After the merge, the build,
save-layout and var-macro checks, 20 authoring tests, both map checkers and the three real-loss
respawn scenarios passed again on `develop`.

**Phone build published:** `2026-11-05_fb2b9673ff`, ROM sha256
`7df037fe82171ee3dbfbfdd768e24eb697fe03ccb83fc7e0302de93a2a336df3`, save line 2.
`dev/mobile.py --full` verified 10/10 in mGBA: fresh game, save, CONTINUE, play ZIP boot/save/
CONTINUE, slice playthrough and byte-identical ROM. Google Drive for Desktop confirmed upload of
`PokeMaritimes_save2.zip` and `builds/PokeMaritimes_2026-11-05_fb2b9673ff_save2.zip` to the
private **PokeMaritimes playtest** folder; a separate `dev/mobile.py --status` reported the latest
play file uploaded. **Saves carry over:** same layout version and play filename. No My Boy! synced
save was present, so a particular phone save was not boot-tested; use an in-game save rather than
an old save state, and keep My Boy!'s Quick load on start off.

*(Historical; the current pointer is at the top.)* **Next session:** the Woodstock redesign remains proposed and unstarted. Read
`region_blueprint.md` before planning it. Detach a shared interior with `dev/unique_layout.py`
before changing its terrain in Porymap, run one authoring command at a time, and keep git commits:
rollback covers exceptions/Ctrl-C, not power loss, killed processes or concurrent edits.

**Milestone 14 done: building stamps** (branch `milestone14-building-stamps`, merged into `develop` and pushed 2026-11-04). **No save break:** the save layout is unchanged (`save_layout.py` matches version 2); TownLab and its rooms are appended maps and its heal location is appended, so no id moves. **Phone build published** from `develop` after the merge: `2026-11-04_f9d2bbe2fb` (save line 2, sha256 `d22722f2…`), 9/9 in mGBA (new game, save, CONTINUE at the same spot, from the ZIP too), uploaded and confirmed by Drive; **saves carry over** (same play file, `PokeMaritimes_save2.zip`). TownLab isn't reachable in normal play (dev group, like LedgeLab).

*(Historical.)* **Starting the next session:** read `region_blueprint.md`, then "Next milestone" below (M15, Woodstock, proposed and not started). `dev/corridor.py check` should print 0 errors and 0 warnings before any map work.

Tom asked (2026-11-04) for reusable building placement so towns can be built efficiently: houses, Pokémon Centers, Marts and larger buildings with working entrances and interiors, proved on a test map before the corridor.

**What existed before:** `add_interior.py` could put a cloned vanilla interior behind a door already painted on a map (it recognises the facade, `mapkit/doors.py`), with every event stripped. `mapgen` could only *keep* a hand-painted building as `#`, so no town could be built or rebuilt from a design script, and no room it made worked as a Center or a Mart. Porymap places buildings by copy and paste, with doors wired by hand. Vanilla's own tiles were enough: no new art was needed.

**What was built:**
- **Stamps** (`dev/mapkit/stamps.py`, catalog `stamps.toml`): ten vanilla buildings cut from their source maps and copied block for block: `pokemon_center`, `mart`, `gym`, `house_small`, `house_small_wide` (all `gTileset_General`: any General map), `house_oldale`, `house_two_storey` (door right or left, with a doormat), `lab`, `house_wide` (Petalburg tileset: all our corridor maps except Fredericton). `dev/buildings.py list | sheet | find` shows them (`dev/out/stamps_sheet.png`).
- **In sketches:** `sk.place(p, "mart", x, y, "Town_Mart")` draws the cells `B` and writes `// stamp: mart @ x,y -> Town_Mart`. The compiler places the blocks and refuses a stamp off the map, overlapping, on the wrong tileset, drawn wrongly, or whose door doesn't face walkable ground. To the learned rules a building reads as grass, so its neighbours are tiled as beside a lawn (as kept "F" they copied grey steps from vanilla's other objects).
- **Doors and rooms** (`mapkit/buildings.py`, run by `mapgen build` / `--apply`): `-> <Room>` names the map behind the door. An existing room keeps its warp, which moves with the door (same index, so its exits stay right): **a building moved in a redesign keeps its room, people and warp ids**. A new room is copied from the stamp's interior template. Refused: two doors naming one room, a room belonging to another map, a two-floor room named without `_1F`, two Centers on a map, a warp left inside a building.
- **Rooms that work** (`mapkit/interiors.py`, out of `add_interior.py`, which now uses it, byte-identical for plain rooms, and takes `--kind`):
  - A **Pokémon Center** keeps its nurse (she heals and is the whiteout respawn NPC), sets the respawn point on entry (`setrespawn`, a heal location appended to `src/data/heal_locations.json`, moved with the door), and keeps vanilla's shared cable club upstairs. Copies skip the shared Union Room and Trade Center and keep their warps.
  - A **Mart** keeps its clerk, with a stock list (`mart` block in its `scripts.pory`, the designer's to edit).
  - Other rooms are empty, for `events.py` (it keeps the nurse and clerk as hand-placed and appends after them; checked with a dry run).
- **Extract** recognises catalog buildings (solid cells exact; a roof row blended with a tree behind is kept as `#`): every building on Littleroot, Oldale and Petalburg, Hoenn's Centers and Marts (37 vanilla doors), and **HomeTown's two houses and Woodstock's three buildings, with their rooms**, so the M15 and M16 rebuilds can move them.
- **TownLab** (`design/maps/townlab_design.py`; dev group, not linked; tests warp in): a 44×34 village with every stamp, ten doors, 13 rooms, `HEAL_LOCATION_TOWN_LAB`. Its Center was then moved two tiles in the design to prove the redesign path (warp 2 and the heal location moved, nothing else).

Before/after and in-game: `dev/out/TownLab_preview.png`, `dev/out/stamps_sheet.png`, `dev/out/door_TownLab_*.png`, `dev/out/buildings_TownLab_*.png` (the nurse, the shop).

How it was verified:
| Area | Result |
|---|---|
| Catalog and vanilla | `tests/stamp_pieces.py` PASS: all 10 stamps load from their source and their interiors copy; every door on Littleroot (3), Oldale (4) and Petalburg (6) is a recognised stamp, 37 vanilla doors in all; each stamp is recognised where it was cut. |
| Round trip | Extract → compile reproduces every stamp cell, drawn `B` (only blended roof cells `#`), and the whole map at least as well as keeping the cells: Littleroot 96.2%, Oldale 94.2%, Petalburg 95.9% (95.3% keeping), HomeTown 87.5%, Woodstock 95.8%, TownLab 100% (99.0%). `roundtrip.py` and `reconstruction.py` (87.8%) unchanged. |
| Refusals | Off the map, overlapping, unknown, wrong tileset (a Petalburg stamp on Fredericton's Rustboro map; the Center builds there), drawn wrongly, an uncovered `B`, in water, a door facing a tree or water, a walled-in doormat; door plans: two doors one room, another map's room, two warps into one room, `_1F` missing, two Centers, a renamed Center, a warp inside a building, a dropped building's warp and heal location. |
| `add_interior.py` | Old and new versions, run on the same dead Fredericton door (a three-floor Rustboro flat): byte-identical files and diffs. |
| TownLab, static | `mapgen`: 0 checker errors; its 13 rooms check clean (the Center's upstairs warns exactly as vanilla's does: the attendants walk you into the link rooms). A re-apply finds every door unchanged. |
| TownLab, in-game | `ingame_doors.py`: 10/10 doors in and out, 3 upper floors (the escalator boarded from its elevation-0 side). `ingame_buildings.py` 8/8 as real play (no test mode): entering the Center sets `lastHealLocation` to `HEAL_LOCATION_TOWN_LAB`, the nurse heals 1 HP → full, the Mart sells a Poké Ball (₽3000 → ₽2800). |
| Redesign | The Center moved two tiles in the design: `mapgen` moved door warp 2 and the heal location, nothing else; in-game the door, escalator, respawn point and nurse work at the new spot. |
| `events.py` on a copied Center | A dry run adding a person: the nurse is kept as hand-placed (local id 1), the person appended, 0 errors. |
| Regression set | All pass on the final code (37 steps): checker (vanilla 0 unexpected, 8 known; 33 maps 0 errors), id budget, save layout, conformance 532/532, playthrough, doors (HomeTown, Woodstock, TownLab), buildings 8/8, encounters (with and without a party), all four autowalks, ledges, events 114/114, save, shores 624/624, flora 435/435, piece tests, corridor plan and check, reconstruction 87.8%, round trip unchanged, route numbers 53/54 and 37/37, every events spec 0 changed, mobile publish. In the first full run `ingame_events.py` failed once while CPU-heavy tests ran beside the emulator; it passed four times since, alone. |
| Code review | `/code-review medium` raised 10 findings, all fixed: `name_area --interiors` would have renamed the shared Union Room and Trade Center (the closure now skips shared rooms); copied Centers and Marts played town music; a heal location clash moved the other Center's respawn point (`add_interior`, and `mapgen --force`); a building dropped from the sketch left its warp and heal location behind (now refused, `removed_doors`); two warps into one room moved only one; the checker's unknown-map errors were hidden by message suffix (now only the exact warps the plan appends); a malformed stamp line and an empty sheet crashed; the real-play test called `test_mode`. **Found while testing the fixes:** extract joined the sketch rows before marking the stamps, so every extracted building came out `#` (identical blocks, so nothing showed, and the round-trip A/B compared `#` with `#`); fixed, and the test now checks the cells are `B`. |

Known limits:
- **Tilesets:** Rustboro's city buildings (Fredericton) stand on paved ground with drop shadows drawn into neighbouring tiles; they aren't stamps (M20's research). A town's houses come from one secondary tileset (a map has one), plus the General ones.
- **The gym's room** is Rustboro's gym hall, emptied: a placeholder until there's a gym design. The lab and houses are vanilla rooms, emptied.
- **Hedges, fences, gardens, signs** beside a building aren't stamps (the wide house's hedge is part of its stamp). Hedges look like the next piece of town vocabulary.
- **One Center per map** (its heal location is named for the map). A Center that moves leaves a save made at the old spot unmatched: its whiteout falls back to the old outdoor spot (dev only; worth a migration note before release).
- **Fly:** a new Center's heal location isn't a Fly destination (no Town Map yet).
- **Whiteout itself** isn't exercised in-game: the test checks the respawn data the whiteout reads (`lastHealLocation`) and the nurse; the lookup is vanilla's.

**Milestone 13 done: the corridor plan of record** (branch `milestone13-corridor-plan`, which includes the earlier `region-blueprint` branch; merged into `develop` and pushed 2026-11-04). The phone build was re-verified after the merge: the ROM is byte-identical to the published build (sha256 `d8e0494b…`), so nothing was uploaded and saves carry over.

*(Historical.)* **Starting the next session:** read `region_blueprint.md` (the geography rules, the corridor plan, the build order), then "Next milestone" below (M14, building stamps, proposed and not started). `dev/corridor.py check` should print 0 errors and 0 warnings before any map work.

Tom's direction (2026-11-04):
- Follow the real geography of the Maritimes as closely as practical.
- The existing maps are prototypes: redesign or replace them freely, keeping everything recoverable through git.
- Claude owns the world-building.
- Small, tested milestones on the corridor: a rural start west of Woodstock → Woodstock → down the Saint John to Fredericton.

What was done (tooling and design data only; no map, script or engine change; the ROM is unchanged):
- **The plan** (`design/region/corridor.toml`, rationale in `region_blueprint.md`): seven maps in one real-world projection (0.5 km per tile, Woodstock at the origin), with the joins derived from their rectangles.
  - The start valley is an inset (HomeTown and Route 201 follow the Meduxnekeag), and Woodstock is a confluence town.
  - Route 202 is the river road to the Meductic bend; Nackawic is a bridge town on the north bank; Route 203 is the headpond with Kings Landing and the dam; Fredericton has its downtown on the south bank.
  - Five map folders are reused (rebuilt in place) and two maps are new.
- **The Saint John comes from real data** (Natural Earth, smoothed, widths per place: 6 at Woodstock, 10–11 on the headpond). The Meduxnekeag and the road are drawn by hand.
- **`dev/corridor.py`:**
  - `check`: overlaps, reachability, the size limit; at every seam the river and the road cross on both sides, at least 2 wide; the road keeps a verge from the water; the connection changes the plan asks for.
  - `render`: `dev/out/corridor_plan.png`.
  - `underlay "<Map>"`: a starter sketch with the real river and the road, seams matching.
  - `compile`: every underlay builds with mapgen's compiler.
- **`dev/mapkit/geo.py`:** the projection, the plan and the water raster. Cleanup widens one-tile water. It's cut with a margin, so neighbours agree at seams.
- **`dev/blueprint.py`:** the region view now shows the corridor plan. The game-vs-reality fit stays (the game's current maps: 38 km off).
- **`dev/tests/corridor_plan.py`** (no emulator).
- Earlier the same day (branch `region-blueprint`): the Natural Earth extract, `anchors.toml`, `blueprint.py`, and `render.world_positions` split out of `render_world`.

How it was verified:
| Area | Result |
|---|---|
| Plan check | `corridor.py check`: 7 maps, 0 errors, 0 warnings. Six joins, each carrying the river and the road across. |
| Underlays | `corridor.py compile`: all 7 build with mapgen's compiler at the planned size. The first run failed Route 203 on a one-tile water tip at the Kings Landing bend; that led to the cleanup, and the road was pulled back where it touched the water. The five reused folders all differ in size from the plan (`check` lists them), so each rebuild starts with a resize (M15). |
| Code review | `/code-review medium` raised 10 findings, all fixed.<br>**The cleanup:** it erased a one-tile diagonal river (4-neighbours only), changed water while scanning it (so a change could cross the margin and neighbours could disagree; rounds are now synchronous, `MARGIN = 2 × rounds + 1`, and all 7 maps match cuts from two other windows), and could turn road into water.<br>**`check`:** the seam rule took any overlap as "continues" (runs must now pair one to one with ends within a tile). That stricter rule caught a real plan flaw: the Route 203/Fredericton seam cut the dam's bend, so the bank jumped 3 tiles; the seam moved 4 tiles east. `check` also judged the raw road rather than the road the underlay draws.<br>**Tools:** an underlay named a folder of the wrong size as buildable; dive/emerge connections showed as removals; a bad name crashed `compile`.<br>**Cleanup:** repeated raster work (now memoized) and dead code. |
| Tests | `tests/corridor_plan.py` PASS. The connection math reproduces all 16 of the game's real connections from the maps' positions. A map cut alone matches a larger cut. The checker catches an overlap, an unreachable map, an oversized map and a river that stops at a seam. Its first run caught a real bug: the tip cleanup could erode a one-tile river from its end, cell by cell. Cleanup now widens instead. |
| Refactors | `render_world`'s output is pixel-identical after `world_positions` was split out. `blueprint.py`'s fit numbers are unchanged after it moved to `geo.py`. |
| Regression | The ROM is unchanged, so the map and event regression set wasn't re-run. |

**Milestone 12 done: mobile playtesting** (branch `milestone12-mobile-playtest`, merged into `develop`). Tooling only: the ROM is unchanged.

**Tom's workflow:** double-click `RomHackDev/Send PokeMaritimes to phone.bat` (or `dev/mobile.py`). On the phone, open the Google Drive app → **PokeMaritimes playtest** → `README.txt` says what to download and whether saves carry over. **Part of every milestone now:** after merging into `develop`, run `dev/mobile.py` and say in the handoff whether it was a save break.

**Tailored for My Boy!** (Tom's emulator; Pizza Boy GBA Pro is the fallback; follow-up branch `mobile-myboy`, merged). From My Boy!'s official FAQ (sites.google.com/site/fastemulator): saves are "stored in a private app-specific folder that you typically cannot access"; "Sync with Google Drive" mirrors them into a `MyBoy` (or `MyOldBoy`) folder on Google Drive; Settings → Misc → "Quick load on start" reloads a save state when a game opens; `.gba` and `.zip` both load; "Add game folder" adds ROMs. Not documented, and assumed from how emulators generally work: saves are keyed by the ROM's file name, and the save type and clock come from the game code. The README's first-install check (save, close, reopen, CONTINUE) proves the first two on Tom's phone, and its update step says to stop and report if CONTINUE goes missing.
- **README:** My Boy! setup (Quick load on start off, Sync with Google Drive on, a `Download/PokeMaritimes` game folder), install and update steps, the save break, a Pizza Boy GBA Pro section, and what to do if a save goes wrong. Each build says either SAVES CARRY OVER or SAVE BREAK, and `mobile.py` prints the same.
- **Phone save backups without uploading by hand:** once sync is on, each run backs up the synced `*PokeMaritimes*` files into `saves/myboy/` (dated, deduplicated by content) and boots the newest readable one in the verification. It never writes into `MyBoy/`. A synced file no layout reads shows as "can't check": the sync format isn't documented. **Pending Tom:** turn sync on, then check that the files in `My Drive/MyBoy` are plain 128 KB `.sav` images (`dev/mobile.py --status`).
- A run whose ROM is already on Drive still refreshes `README.txt` if its text changed (that's how these instructions reached Drive).
- `tests/mobile_publish.py` 43/43, twice: a fake `MyBoy/` folder is left byte for byte untouched; its game saves are backed up, but another game's save and a save state aren't; the synced save is the one booted; a file that isn't a flash image is "can't check", but a damaged image is WON'T LOAD; nothing is backed up twice; a changed save with the same timestamp gets a second backup beside the first; a stale README is refreshed.
- `/code-review medium mobile-myboy` raised 10 findings, all fixed:
  - **Saves:** a damaged synced save read as "can't check" (now only a file that isn't a flash image does). Save states syncing through `MyBoy/` would have been backed up on every change; only `.sav`/`.srm` or flash-image-sized files count now, and `--status` lists the rest. Two backups with the same name could overwrite each other.
  - **Robustness:** a file vanishing mid-sync crashed the run. Deduplication hashed the whole backup history; it now reads only the newest backup per name. A missing commit could blank the README's change list. A trailing separator in `MARITIMES_DRIVE_DIR` lost the sync folder.
  - **Cleanup:** the README was built in two places, and `MyBoy/` was walked several times per run.
  - **Test:** the `older.srm` check had lost its file.

**Downloading on the phone, fixed** (branch `mobile-zip`, merged). Tom reported that the Drive app's ⋮ menu on `PokeMaritimes_save2.gba` had no Download item.
- **Diagnosis:**
  - **The upload and permissions are fine.** Drive for Desktop's own record of the file has the same owner capabilities as the README and the archive; the only differences are the type (`application/octet-stream` vs `text/plain`/`application/zip`) and size. The file was uploaded and hash-verified.
  - **The file is private.** Requested without a sign-in, its download URL returns Google's sign-in page, which also settles the privacy check that couldn't be done in Chrome.
  - **Likely cause:** Google's help page for Android says *"When Data Saver is turned on in your network settings, the download option isn't available."* That's a phone setting, which nothing here can verify.
- **The fix, in the workflow, so it doesn't depend on that menu:**
  - The play file is now **`PokeMaritimes_save<N>.zip`** (only the ROM inside, 13 MB instead of 32, `application/zip`). My Boy!'s FAQ: "In case of .zip, My Boy! will load the first recognized file in the archive". The ZIP is deterministic, and the verification boots the ZIP itself in mGBA.
  - `README.txt` and the tool's output carry a **direct download link**, `https://drive.usercontent.google.com/download?id=<cloud id>&export=download`, built from the file's cloud id once Drive has uploaded it. It opens in Chrome, not the Drive app, and works only when signed in to Tom's account. `--status` prints it too.
  - The README explains Data Saver and says not to unzip. The loose `.gba` from before was retired from the top level; `builds/` still has it.
- `tests/mobile_publish.py` 53/53, twice. Starting from the folder as it was before the ZIPs, the same ROM is repackaged (no duplicate archive or entry) and the loose `.gba` retired. The ZIP holds only the ROM byte for byte; the verification boots it, saves, and CONTINUEs at the same spot, and the phone save is CONTINUEd from the ZIP. There's no link until Drive has uploaded the file.
- `/code-review medium mobile-zip` raised 10 findings, all fixed:
  - **The phone save** was CONTINUEd through the loose `.gba`, not the ZIP the phone opens (now the ZIP, which also saves and CONTINUEs in its own check).
  - **The link:**
    - It could be written while an overwritten ZIP, which keeps its id, was still uploading. It now waits for the measured upload signals.
    - A copy in a trashed folder could be picked up.
    - The README kept its placeholder after a timeout (`--status` now refreshes it).
    - Pending uploads were matched by substring, and `name.zip.partial` contains `name.zip`. They're now matched by the length-prefixed name.
  - **Packaging:** the same ROM would have been archived twice; the play ZIP's bytes depended on the platform.
  - **README text:** the README named `(1).gba` and a hard-coded `save2` ROM.
  - **Efficiency:** the README was rebuilt and the Drive database copied several times per run (now once, in `finish()`).

**How it works** (`dev/mobile.py`; manual: `dev/README.md`, "Play on the phone"):
| Step | What |
|---|---|
| Upload route | Google Drive for Desktop is installed and signed in (the `G:` volume): the tool copies into `G:\My Drive\PokeMaritimes playtest\` and Drive uploads it. Weighed and not chosen: the claude.ai Drive connector (needs Tom to sign in each session, isn't scriptable, and isn't suited to 32 MB binaries), and rclone or the Drive API (an OAuth client and a token to keep safe, for nothing the synced folder doesn't already do). |
| Private | The folder is created in My Drive's root, so only Tom's account can see it until someone shares it by hand. The tool never shares anything, and holds no credentials: Drive for Desktop's own sign-in does the upload. Nothing it writes is inside the repo. |
| Verified | Header (game code BPEE, which phone emulators use to pick 128 KB flash and the clock; complement check). In mGBA, on the exact bytes uploaded: a new game reaches the overworld, saves, `savefile.py` reads the save as loadable, and after a power cycle CONTINUE lands on the same spot; the newest loadable phone save in `saves/` CONTINUEs too. `--full` adds the slice playthrough. A tree with uncommitted changes is refused: a build is named by its commit. |
| Save compatibility | The play file is `PokeMaritimes_save<N>.zip` (a `.gba` until `mobile-zip`), N = `SAVE_LAYOUT_VERSION`. Phone emulators find a save by the ROM's file name, so replacing the file within a save line keeps the save; a save break gives the new build a new name and a fresh save, and the old save stays with the old file, untouched (the phone's version of `play.py` setting stale saves aside). The README announces a save break in a banner, and lists each save in `saves/` as loads / won't load. |
| History | `builds/PokeMaritimes_<date>_<commit>_save<N>.zip` (13 MB: the ROM under its play name, and `build.txt` with the commit and sha256), `builds/index.json`. Publishing a ROM that's already the phone build uploads nothing. An old play file leaves the top level only once its hash is in the archive (deleting from the Drive volume goes to Drive's trash). |
| Upload confirmed | Drive for Desktop gives a file a cloud id once it's uploaded; the tool reads that from Drive's local metadata database (a copy of it, read-only; undocumented, so best effort: "unknown" if it can't tell) and waits up to 10 minutes. |

How it was verified:
| Area | Result |
|---|---|
| Verification | `mobile.py --check`: 6/6 in mGBA (new game → save → power cycle → CONTINUE at the same spot; screenshots `dev/out/mobile/check_*.png`). |
| Publishing | `tests/mobile_publish.py` 33/33 in a scratch folder, twice: the play file and the archive's ROM are the built ROM byte for byte; a save break is announced; the old play file is retired only because an archive holds it, and a ROM whose archive is gone is kept; the game's own save in `saves/` is reported as loading and CONTINUEd in mGBA, the same save restamped for an older line (as `.srm`) is reported as that line's, a broken one as won't load; re-publishing uploads nothing. |
| Upload signal | Measured with a 32 MB throwaway file in the Drive folder, new and then overwritten (deleted afterwards): while content uploads, Drive's database shows a `local-content-size` property and a pending operation naming the file, and the cloud `modified_date` doesn't move; all three clear once it's up, about 10 s here. |
| Live | From clean `develop` at the merge: build `2026-11-04_5cd493a083` (save line 2, sha256 `d8e0494b…`), 6/6 in mGBA, uploaded and confirmed: `PokeMaritimes_save2.gba` (32 MB), `builds/PokeMaritimes_2026-11-04_5cd493a083_save2.zip` (13 MB), `README.txt`, `index.json`. A second run: "already the phone build", nothing uploaded. Privacy: by construction (a new folder in My Drive's root, owned by Tom's account, never shared); not checked in Drive's web UI, because Chrome was signed out. |
| Regression | `ingame_save.py` PASS (`savefile.check` gained a layout argument). The ROM is unchanged (same sha256 before and after the milestone), so the map and event regression set wasn't re-run. |
| Code review | `/code-review medium` raised 8 findings, all fixed: an overwritten play file (same name and size) could read as uploaded before its bytes were (now the measured signals above, scoped to the folder); an old play file was removed when the index listed its hash, without checking that an archive held it; a save from an older save line read as "WON'T LOAD" (now named as that line's: the index keeps each build's layout); `--check` refused uncommitted trees; a 10-minute wait with Drive for Desktop stopped; a save with a damaged slot was booted; the test's stray ROM could collide with the old play file; this table claimed a live publish before it happened. Also added: `.srm` saves. |

**Milestone 11 done: room for the whole region's story in the save** (branch `milestone11-save-vars`, merged into `develop`). Foundation only: no gameplay or map changed. The plan, the format and the version history: `design/save_format.md`.

**Save compatibility: layout version 2.** Saves from milestone 10 (version 1) are refused with the outdated-save message. Tom: if you're partway through the slice on the milestone 10 build, finish on that build; on this one, start a new game once.

**The recommendation, done:**
| Budget | Before | Now | Why |
|---|---|---|---|
| Story vars | 23 unused vanilla vars | **256 story vars** (`0x4100–0x41FF`) in SaveBlock3, plus the 23 as a reserve for engine features | Vanilla's Hoenn story uses about 200. SaveBlock3 had 1,620 free bytes; SaveBlock1 had 212 (about 100 vars at most) and nothing moved in it for them. |
| Maritimes flags | 256 (2 used) | **768** (2 used) | Hoenn's story uses about 800 non-trainer flags (582 hide flags, 168 item balls, 112 hidden items); with the 249 unused vanilla flags that's covered. Raised in the same version so the story costs one save break, not two. |
| SaveBlock1 room | 212 bytes | 148 | 64 bytes for the flags. |
| SaveBlock3 room | 1,620 bytes | 1,108 | 512 for the vars. |
| Trainer ids | 520 | 520 | Unchanged. |

- **Two subtleties:** SaveBlock3 is spread over the spare bytes of all 14 flash sectors, and a link or Battle Frontier save (`SAVE_LINK`) rewrites only sectors 0–4. The story block is SaveBlock3's first field, so it lies in those five sectors and is saved with the flags on every kind of save; `save.c` asserts it. And expansion never checksummed those spare bytes (the review caught it): every save slot sector's checksum now covers them, so a damaged story var is caught like a damaged vanilla var.
- **Engine** (small, marked `Maritimes:`): `GetVarPointer` maps the block, and an id between the blocks is no longer a var (vanilla pointed it into the next SaveBlock1 field). `compare`/`setvar`/`copyvar` know the block: every existing script assembles byte-identically. The debug menu's var editor and the test framework's script header know it too. The guard records the block's offset and size. Dev bridge: `VGET`, `VSET`, and `SAVE` as a link save.
- **Tooling:** `dev/save_ids.py var|flag NAME "note" [--apply]` allocates story vars and flags (append-only; re-running is a no-op; vanilla names refused); `list` shows them. `events.py` allocates its item and gift flags through the same code. `id_budget.py` checks the var block (range, contiguous ids, allocated by the tool, inside the always-written sectors) and keeps story flags out of the one-event-per-flag check. `fastbuild.probe()` compiles a throwaway file in the mirror (save_layout.py and the new macro test use it).
- **How story scripts use it:** allocate `VAR_HOMETOWN_STATE` with `save_ids.py`, then `setvar(VAR_HOMETOWN_STATE, 1)` / `if (var(VAR_HOMETOWN_STATE) == 1)` in `scripts.pory`, as with any var. Nothing is allocated yet: the names wait for the story.

How it was verified:
| Area | Result |
|---|---|
| Save | `ingame_save.py` 42/42: story vars at both ends of the block and a vanilla var survive save → reset → CONTINUE, then a link save; on flash they sit in sector 0's and sector 4's SaveBlock3 chunks; the sector checksum covers the chunk, and a story var flipped on flash makes the save refused as damaged; the id past the block can't be set and reads as itself; a NEW GAME over the save starts them at 0; the flag checks and the stale-stamp refusal as before. |
| Macros | `tests/var_macros.py` 8/8 (fails 4/8 with the old macros). Old vs new macros: `event_scripts.o` and `mystery_gift.o` (every map's scripts) assemble byte-identically. |
| Guard | Before `--update`, `save_layout.py` exited 1 naming the six changed numbers; afterwards it matches version 2. |
| Allocator | Dry runs, a refused vanilla name and bad name; on a scratch copy of the headers: appends in order, re-running is a no-op, the note is kept on one line, a full block is refused with the fix to make. |
| Budget | `id_budget.py` PASS: 520 trainer ids, 766 block flags, 256 story vars, 148 SaveBlock1 bytes. |
| Regression set | All pass, before and after the review fixes: checker (vanilla 0 unexpected, 8 known; 19 maps 0 errors), conformance 532/532, playthrough, doors, encounters (with and without a party), all four autowalks, ledges, events, shores 624/624, flora 435/435, piece tests. |
| Code review | `/code-review medium` raised 10 findings; 8 fixed, 1 guarded, 1 left. **Fixed:** the story vars had lost checksum protection (expansion never checksummed SaveBlock3's chunks; now every save slot sector's checksum covers its chunk); a recorded offset of 0 that moves didn't bump the version; a story flag reused as an item flag passed the budget; the macro test's warning check wasn't scoped to its probe; the debug var range assumed the blocks adjacent (now asserted); flash constants copied into the tests (now read from `save.h`, checked against the compiler); a duplicated sector scan; the probe's file encoding. **Guarded:** a literal in 0x4100–0x41FF given to `compare` reads as a story var (vanilla's macros do the same for their ranges): `id_budget.py` now fails on such a script. **Left:** the engine commit carries `save_layout.h` numbers that the tool commit after it teaches `save_layout.py` to measure, so `--update` run at exactly that commit would drop two lines (a bisect-only hazard; fixing it means rewriting history). |

**Milestone 10 done: the slice's towns come alive, and stale saves can't load as garbage** (branch `milestone10-slice-life`, merged into `develop`).

**Save compatibility from now on:** every save is stamped with a layout version (`include/save_layout.h`, version 1). A save from another layout is refused with a message ("This save is from an older version of the game. Please start a new game.") and the menu offers NEW GAME only. Saves from milestone 9 and earlier carry no stamp, so they get that message too. Tom: start a new game once.

**Save-flag capacity and compatibility: the assessment** (engine facts: `mapping_reference.md` §13):
| Budget | Used | Left | Notes |
|---|---|---|---|
| Trainer ids | 856 of 1376 | 520 | One saved flag each. |
| Maritimes flag block | 2 of 256 | 254 | Item balls, hidden items and gifts. A full region needs about 150–300 (vanilla Emerald has about 140 item balls, 100 hidden items and a few dozen gifts), so this lasts the next several areas. |
| Saved vars | 233 of 256 | **23 unused** | **The real future squeeze.** Story state (a town's progress, a quest) lives in vars, and vanilla's Hoenn story holds most of them. |
| SaveBlock1 | 15,660 of 15,872 bytes | 212 | 8 flags or trainers cost a byte, a var 2. |
| SaveBlock2 / SaveBlock3 / PC | 3,884 / 4 / 34,144 | 84 / 1,620 / 1,568 | |

- **What could corrupt saves silently, and what guards it now:**
  - **A layout change** (a range raised, a field added, an expansion config that resizes a block): before, an old save loaded byte for byte into the new structs. Now the build fails until `dev/save_layout.py --update` re-measures and bumps the version, and the game refuses saves stamped with an older one.
  - **A flag or trainer id that moves:** `events.py` only appends, and `id_budget.py` checks that ids are unique and contiguous and that every allocated flag belongs to one event. The guard also pins where each flag range starts.
  - **Not covered:** reordering two SaveBlock fields of the same size (nothing in our workflow does that), and the Hall of Fame and Trainer Hill sectors (nothing changes their format).
- **Strategy (recommended):**
  - **Now (development):** breaking saves is fine, but only on purpose. Bump the version whenever the layout moves; the message tells testers why.
  - **Before story work starts:** decide the var plan. Either reclaim Hoenn's vars and flags when the Hoenn maps are retired, or add a Maritimes var block once, generously (64 vars = 128 bytes of the 212). One planned break is better than several.
  - **Before any public release:** freeze the layout, and from then on add a migration (read the old stamp, move fields) instead of refusing old saves.
- **Tools:** `dev/save_layout.py` measures the layout exactly. It compiles a throwaway probe with the build's compiler, since the ELF has no debug info. `--update` rewrites `save_layout.h` and bumps the version. `id_budget.py` now reports exact room and the unused vars.

**Life in the slice** (specs in `design/maps/*.events.toml`; text provisional; no terrain changed):
| Map | Events |
|---|---|
| HomeTown | The player's mailbox, "{PLAYER}'s HOUSE". **Bug fixed:** it ran Littleroot's script, which told a girl player she lived in PROF. BIRCH'S HOUSE. Also the LEBLANC mailbox next door; the neighbour by her vegetable beds (fiddleheads by the brook); a sawmill hand on the worn patch by the small pond; a boy wandering beside the player's house, clear of the lane. |
| HomeTown, the neighbours' kitchen | Her husband ("she'll talk your ear off about fiddleheads"). |
| Woodstock Wildlife Station | The chief meets visitors; a field researcher just back from Route 201's cutblock; field notes on the desk and the scanner to read (`[[inspect]]`). The bookshelves keep vanilla's text. |
| Woodstock, the house by the garden | A mother at the counter (ice-out on the river every spring); a grandfather at the table (the old log drives). |
| Woodstock, the house by the station | A girl saving for a fishing rod (ties to the angler by the pond). |

Crossings and route numbers are unchanged; the checker is clean. In-game messages: `dev/out/events_m10_sheet.png` (a contact sheet of the new ones) and `dev/out/events_<Map>_*.png`.

**Tooling added:**
- **`events.py` works on new interiors:** a room whose `scripts.inc` is still the empty stub gets a `scripts.pory` started on `--apply`.
- **`[[inspect]]`:** text read from a solid tile with no sign post (a desk, a machine, a mailbox), wrapped like dialogue.
- **`replaces = [...]`:** the spec takes over hand-placed placeholders. Each entry must match exactly one event (`name@x,y` picks one), and a person can't be removed while hand-placed people follow it.
- **Spec text:** straight double quotes become “ ”. The charmap has none, and Poryscript's `format()` fails on an escaped one; that was a build break found here.
- **`ingame_events.py`** with no arguments tests every map that has a spec.
- **Model fix, found in-game:** a wander range of 0 means *no limit* on that axis (`IsCoordOutsideObjectEventMovementRange`), not "stays in its row". A boy given range 2×0 walked off his row. `wander_box` now spans the map on such an axis, except for one-axis movement types (vanilla's zeros). The spec refuses a 0.

How it was verified:
| Area | Result |
|---|---|
| In-game events | 114/114 on seven maps: HomeTown 22, the kitchen 4, Route 201 21, Woodstock 41, the station 14, the houses 8 and 4. |
| Save | `ingame_save.py` 19/19: flags survive save, reset and CONTINUE; the file carries the stamp; the same save rewritten with an old stamp is refused, the message shows (`dev/out/save_outdated_menu.png`), and the first menu item starts Birch's speech. |
| Guard | Raising `MARITIMES_FLAGS_COUNT` by 16: `save_layout.py` exits 1 naming three changed numbers, and the build stops on `SaveLayoutChanged_*` asserts. Reverted. |
| Budget | `id_budget.py` PASS: 520 trainer ids, 254 block flags, 23 unused vars, 212 SaveBlock1 bytes. |
| Checker | Vanilla baseline: 0 unexpected (8 known), after the wander-range model change. Our 19 maps: 0 errors. |
| Regression set | Conformance 532/532 (the new people occupy some sampled tiles), playthrough, doors, encounters (with and without a party), all four autowalks, ledges, shores 624/624, flora 435/435, piece tests PASS. |
| Code review | `/code-review medium` raised 10 findings: 9 fixed, and 1 was deliberate behaviour (now commented). Fixed: a quote opening a new box came out closed; `replaces` could delete every event sharing a script or renumber later people; the guard missed moved flag ranges; the save test's "new game" check could pass on a hang; the probe could be deleted by a mirror reseed; copy-player movers lost their range box; the default test list ignored each spec's `map`; the header had three separate parsers. The deliberate one: a refused save keeps its slot counter, so the new game's first save out-counts the stale slots. |

Known limits:
- HomeTown's upstairs room (House2 2F) stays empty, and the player's own house is still vanilla's (Littleroot's 1F/2F, with Mom).
- The dry run doesn't compile the generated Poryscript, so a text that Poryscript rejects fails at `fastbuild`. The quotes were one such case and are handled now.
- All new text is provisional and unread by Tom in-game.

**Milestone 9 done: Woodstock comes alive, and the trainer-id ceiling is gone** (branch `milestone9-woodstock`, merged into `develop`).

**Save compatibility (milestone 9): saves from before it didn't load correctly.** Raising the trainer ceiling moved the system and daily flags, and the saved flag array grew, which shifts every SaveBlock1 field after it. The game loads such a save without complaint, but with wrong flags (no starter, lost badges) and shifted vars. Start a new game. Tests always start fresh.

**The trainer-id limitation, investigated and solved** (engine facts: `mapping_reference.md` §12, "Trainer ids and the flag layout"):
- **The cause:** each trainer id `n` is also the saved flag `0x500 + n`. The trainer, system and daily flag ranges are chained, and `FLAGS_COUNT` sizes `SaveBlock1.flags[]`. Vanilla used 855 of 864 ids, and Route 201's Ross took one more, leaving 8.
- **Options weighed:**
  - Repurposing Hoenn trainers isn't possible yet: the vanilla maps still use them (tests and the checker's baseline run on them).
  - A second, separate trainer-flag range would have needed engine changes in six places and still moved the save layout.
  - Raising `MAX_TRAINERS_COUNT` is what expansion itself suggests. It's one constant, and everything else is symbolic: partners are `MAX + n`, special opponents sit at 0xFF00+, and frontier trainers have their own id space.
- **Done:**
  - `MAX_TRAINERS_COUNT_EMERALD` 864 → 1376: **520 trainer ids free**.
  - A **256-flag Maritimes block** after the daily flags, for item balls, hidden items and gifts. `events.py` now allocates there instead of renaming unused vanilla flags.
  - Cost: 96 bytes of SaveBlock1, leaving **212 bytes**. Both changes were made at once so saves break only once.
  - Static asserts:
    - the saved flags stay below the special flags (0x4000);
    - every saved flag fits a hidden item's 13-bit flag offset;
    - trainer ids fit their flags.
  - Code review caught the ROM side: `sTrainerSlides` was sized by `MAX_TRAINERS_COUNT`, which added about 160 KB of empty slots. It's now sized by the trainers that exist (2.5 KB below vanilla).
- **Guarded:**
  - `dev/tests/id_budget.py` (no emulator): trainer ids are contiguous, fit and have parties; the flag ranges don't overlap; each allocated flag belongs to one event; item flags are saved and permanent. It prints what's left of each budget.
  - `dev/tests/ingame_save.py`: flags at both ends of every range, with their neighbours clear, survive save → reset → CONTINUE (16/16).
  - The `events.py` dry run prints the remaining ids after each allocation.
- **Scaling further:** raise the constant once, generously (1 byte per 8 trainers or flags; every change breaks old saves). When the Hoenn maps go, their 855 ids and the vanilla flags can be reclaimed.

**Woodstock, populated** (`design/maps/Woodstock_2.events.toml`, provisional text; Tom's layout untouched apart from one cell):
| Event | Where | Notes |
|---|---|---|
| Town sign | (9,16), the east end of the entrance road from Route 201, beside the stairs | "WOODSTOCK / The river town in the woods." The post is the only terrain change (`mapgen patch`). A post at the road's west end would have added a step to the crossing. |
| Station sign | (19,13), Tom's post by the station door | "WOODSTOCK WILDLIFE STATION / Pokémon field research" |
| Garden sign | (5,11), Tom's post in the garden | "COMMUNITY GARDEN / Please share the harvest!" |
| Gardener | (6,12), on the garden path | Gives an **Oran Berry** once (gift flag from the block); afterwards a line about held berries. |
| Station worker | (21,14), out front of the station | Counts the Pokémon along the river; mentions the field researchers up Route 201. |
| Child | (15,19), **wanders** the green (range 2×2) | Wants to be a researcher. |
| Angler | (6,26), the pond's north shore, facing the water | "You need a fishing rod" (none in the slice yet). |
| Walker | (16,31), by the road south | Points the way to the city. |
| Poké Ball | (23,6), an **item ball** in the one-tile nook between the station and the river | |

Crossings unchanged (37 steps both ways); checker clean. In-game messages: `dev/out/events_Woodstock_2_*.png` (`events_Woodstock_2_sheet.png` is a contact sheet).

**Tooling added:**
- **`dev/mapgen.py patch <Map> s@9,16 ...`:** places a few pieces on a hand-painted map. It runs the normal build on a sketch that keeps every other cell (`#`), so the diff is exactly those cells. Bad pieces are refused (a flower on a canopy, off the map). Use it on Tom's towns instead of a rebuild, which would change about 4% of Woodstock.
- **Spec vocabulary:**
  - `[[item]]` item balls;
  - `facing = "wander"` with `range = [rx, ry]`;
  - `gift = "ITEM_..."` with `count` and `after`: given once; with a full bag the flag stays clear and they offer it again (vanilla's `goto ShowBagIsFull`);
  - a sign's `facing`.
- **Model and checker:**
  - A wanderer is tried on every tile of its range it can walk to. Cutting off an exit is a WARN, because vanilla's house wanderers do it and move on.
  - An unreachable item ball is warned about.
  - Renders draw wander ranges (dashed) and mark item balls `I`.
- **In-game event test:**
  - item balls: the item is in the bag, the flag is set, the ball is gone, A again does nothing;
  - gifts: given once;
  - wanderers: watched for 30 s, stay in their range, and are then talked to wherever they stand;
  - no other test uses a tile inside a wanderer's range.
- **Dev bridge (debug only):** `FGET` (read a flag), `ITEM` (bag count), `SAVE` (save as the start menu does); `Emu.get_flag`, `bag_count`, `save_game`, `objects()`.
- `prepare_rom` waits for the previous mGBA to release `test.sav`. A long regression run hit that once.

How it was verified:
| Area | Result |
|---|---|
| In-game events | Route 201 21/21, Woodstock 41/41, the Woodstock run three times in a row. The child stood on 12 tiles of its 5×5 range in 30 s and never left it. |
| Save | `ingame_save.py` 16/16 after the layout change. |
| Budget | `id_budget.py` PASS: 520 trainer ids, 254 block flags, about 212 save bytes left. |
| Checker | Vanilla baseline: 0 unexpected (8 known). The wanderer check started as an ERROR and flagged 11 vanilla house/corridor wanderers, hence the WARN. Our 19 maps: 0 errors. |
| Regression set | Conformance 542/542, ledges 490/490 (tours unchanged), shores 624/624, flora 435/435, piece tests PASS; playthrough, doors, encounters (with and without a party) and all four autowalks pass. |
| Code review | `/code-review` raised 10 findings: 9 fixed, and the save break is documented above (it's inherent to raising the ceiling). Fixed: the trainer-slide ROM growth; the wanderer able to block other tests' tiles; wanderer tiles it can't reach; a gift person that wanders; `call` → `goto` for a full bag; gift flags missing from the budget; a fragile save-size measurement; duplicated bridge code; naming rebuilt in the test. |

Known limits:
- The gift's full-bag path isn't exercised in-game (it would need a full berry pocket); it's vanilla's own script.
- `Route102_2` (cloned from vanilla Route 102 in the initial commit) shares `FLAG_ITEM_ROUTE_102_POTION` and Route 102's trainers. Picking up or beating one counts for both. `id_budget.py` notes it.
- A wanderer is judged at home by the route numbers. The walker keeps avoiding a beaten trainer's sight (unchanged).
- Woodstock's text is provisional and hasn't been read by Tom in-game.

**Milestone 8 done: people, signs and hidden items, first used on Route 201** (branch `milestone8-events`, merged into `develop`).

**What existed before:** the events overlay drew letters for events; the checker checked that events were in bounds and their scripts existed; `section_status` counted people and signs. Nothing placed events, and the engine model ignored objects entirely. A person could have sealed the road and every check would still pass. There was no sight model, no check that anything could be talked to, and no in-game test.

**The workflow now** (manual: `dev/README.md`, "People, signs and items"; engine facts: `mapping_reference.md` §12):
1. **Terrain:** a sign needs a sign post, sketch `s` (vanilla's `003`, a one-tile solid piece like the flora). It goes through `mapgen` like any terrain.
2. **Spec:** `design/maps/<Map>.events.toml` lists the map's people, trainers, signs and hidden items, with their text, party and item. It owns those events; anything placed by hand in Porymap is left alone.
3. **Dry run:** `dev/events.py build <spec>`:
   - It refuses bad placements, naming them.
   - It prints each event with the tiles it can be triggered from and what each trainer sees.
   - It runs the checker on the unsaved map and prints the route numbers before and after, including any trainer a crossing can't avoid.
   - It renders `dev/out/<Map>_events.png`: sight in red, trigger tiles in cyan.
4. **Apply:** `--apply` writes:
   - `map.json`;
   - a marked block in `scripts.pory`;
   - each trainer's id (appended to `opponents.h`) and party (`trainers.party`);
   - each hidden item's flag (an unused one renamed in `flags.h`).

   No id ever moves, and re-applying is a no-op.
5. **Test:** `fastbuild`, then `dev/tests/ingame_events.py <Map>`. `dev/events.py list <Map>` shows any map's events, hand-placed ones included.

**The model** (`dev/mapkit/events.py`, from the engine source; vanilla-calibrated):
- **People block:** only at compatible elevations. An object's elevation is its tile's (confirmed in-game on Safari Zone South). A ledge is still jumped past a person.
- **Trainer sight:** straight ahead, stopped by anything the trainer can't walk through.
- **Talking and reading:** facing, elevation, counters, a sign's required facing.
- **Checker:**
  - ERROR when people cut off an exit;
  - WARN for ground reachable only through people, and for a person or sign nobody can reach;
  - INFO for blind trainers and Surf-only events.
- **Route numbers:** permanent people block, and each crossing names the trainers it can't avoid. Vanilla Route 102 west-bound: Calvin, as in the game.
- **Walker and ledge tour:** both plan around people. The walker also avoids trainers' sight (a trainer battle can't be fled). The tour now runs on maps whose people stand still, so vanilla Route 116 gained one.

**Route 201** (`Route201_1.events.toml`, provisional text):
| Event | Where | Notes |
|---|---|---|
| Route sign | (12,3), on the verge where HomeTown's lane meets the route | "ROUTE 201 / ↓ WOODSTOCK", two lines like vanilla's signs. The post is 1 terrain cell. |
| Old forester | (38,13), by the regrowing cutblock | A few lines about the logged stand and the Pokémon in the young woods. |
| Bug Catcher ROSS | (17,15), at the foot of the terrace meadow, facing the ledge | Caterpie 3 and Weedle 3, sight 4. Jump the one-way shortcut and you land in his sight. No crossing passes through it, so the battle is optional. |
| Hidden Potion | (46,2), the nook behind the beaver pond | |

Route numbers are unchanged: 53/54 steps, tall grass avoidable, no trainer forced. Screenshots: `dev/out/Route201_1_events.png` (model), `dev/out/events_Route201_1_*.png` (in-game messages).

**The tree-beside-sand limitation, addressed two ways:**
- **Guard:** `mapgen build` reports `GUARD terrain` (a new error, so `--apply` refuses) when the grammar would overwrite terrain the map already has as drawn.
- **Extract:** it now keeps such joins (both sides, trees whole, plus any neighbour a compile wouldn't put back), so an extract never triggers a repair.

The real scope was bigger than recorded. `roundtrip.py` compiled without the grammar, so it hid that an extract → rebuild on `develop` would also have changed about 22% of Woodstock and 23% of Route 202. With the build's grammar now, every map round-trips with no repair: Route 201 99.1%, Woodstock 95.8%, Route 202 92.7%. The test checks the guard too.

How it was verified:
| Area | Result |
|---|---|
| In-game events | `ingame_events.py` Route 201: 21/21, run three times in a row: each event triggered from a model tile, the forester blocks, the Potion is found once, Ross ignores the tile beside his sight, battles from his farthest sight tile (won), then stays quiet. |
| Checker | Vanilla baseline: 0 unexpected (Safari Zone's exit attendant added as a known case, confirmed blocking in-game). Our 19 maps: 0 errors. |
| Pieces | Sign posts: 35/48 vanilla route signs rebuild exactly (the rest stay `#`); flora shapes 18/18. |
| Round trip | 87.5–100% with the grammar, no repaired cell, guard refuses the old lane-clearing extract. Reconstruction unchanged (87.8%). |
| Regression set | Conformance 553/553 (Route 201's people now occupy tested tiles), ledges 490/490 with tours 10/10 groups, shores 624/624, flora 435/435 (the sign post); playthrough, doors, encounters (with and without a party) and all autowalks pass. |
| Code review | `/code-review medium` raised 10 findings; 9 fixed (below). |

The review's findings:
- **Fixed, in the model:**
  - People blocked at any elevation; the engine checks elevation compatibility. Fixing that showed an object's elevation is its tile's, not its template's (verified in-game).
  - Sight lines counted flag-hidden objects as blockers.
  - The tool computed entrances its own way; it now reuses the checker's single run.
  - An oversized route search made every trainer look unavoidable.
- **Fixed, in the tooling and tests:**
  - The trainer test didn't check that its step lands in sight (it could have been a ledge jump).
  - The walker avoided sight even in test mode.
  - Hidden-item flags could have been taken from the trainer, system or daily range.
  - Duplicated trainer and direction logic in the renderer.
- **Left as is:** the Route 201 data commit includes the trainer id, the party and the flag rename. They are that map's event data, so reverting the commit should remove them together. Expansion's own comment in `opponents.h` still says "9 additional trainers"; the tool prints the true count (8 left).

A flaky test was fixed on the way. The event test's battle sometimes never ended because a level-50 Pokémon with no badges disobeys ("began to nap"). The test now sets the eighth badge flag, teaches Tackle, and uses the SET battle style.

Known limits:
- **Tooling:**
  - A Porymap edit to a spec-owned event (e.g. dragging the forester) is overwritten by the next `--apply`. The dry run shows it as a change, so move owned events in the spec.
  - Only Poryscript maps can take events; HomeTown, Route 201 and Woodstock are.
  - Item balls, wandering people, double battles and rematches aren't in the spec vocabulary yet.
- **Ids:** solved in milestone 9 (520 trainer ids, a 256-flag block).
- **Model:** a wanderer is judged at home (checker, route numbers) or as its whole range (walker), never step by step. The walker keeps avoiding a trainer's sight after the trainer is beaten.

**Milestone 7 done: Route 201, "the old logging road"** (branch `milestone7-route201`, merged into `develop`).

The first route out of HomeTown was the first map rebuilt for looks with the landscape kit. The old map was hand-painted in the initial commit: open grass with pale path patches and three free-standing ledges, no road between HomeTown's lane and Woodstock's, tall grass running off the bottom edge (no connection there), and open ground at rows 10–13 facing Woodstock's trees.

The design (`design/maps/route201_design.py`):
- **The road:** a two-tile sand logging road runs from HomeTown's lane (x 10–11) to Woodstock's road (rows 14–15), so the three maps read as one road. It runs south out of the village, east along the north woods, jogs south, passes the pond, and bends down to Woodstock. A one-tile grass verge keeps trees off the sand.
- **Woods:** forest by default, carved into clearings off the road, so it reads as a road *through* the woods. The edges step in bays and headlands with offset fringe trees.
- **Clearings:**
  - a tall-grass meadow west of the village lane;
  - a sunny clearing with a grass patch, flowers and a boulder;
  - the terrace: a ledge below the road drops into the central meadow, a one-way shortcut as the old ledges were;
  - the beaver pond (unchanged cells) with reeds;
  - a regrowing **cutblock**: saplings coming up through tall grass (Route 116's young grove), the forestry village's work.
- **Accents:** flowers on the verges, and five glacial boulders against the woods.
- **Kept as Tom painted them:** the cliff corner that continues Woodstock's row-17 cliff (with its tree and the two saplings at its foot), and the trees either side of HomeTown's lane.
- **Seams:** the bottom edge is closed with forest, and the east edge is whole trees except Woodstock's road rows.

| | Before | After |
|---|---|---|
| HomeTown → Woodstock | 53 steps, tall grass avoidable | 53 steps, tall grass avoidable |
| Woodstock → HomeTown | 54 steps, at least 4 tall-grass tiles | 54 steps, tall grass avoidable (the old ledges forced the detour) |
| Tall grass (all reachable) | 146 tiles | 137 tiles |
| Longest straight forest edge | 12 | 11 (the tree band under HomeTown) |
| Largest bare-grass square | 4 | 2 |

Tooling built along the way, all reusable:
- **Route numbers** (`mapkit/routes.py`, `dev/route_stats.py`): for each pair of edge connections, the steps across, the fewest tall-grass tiles that can't be avoided, and the reachable encounter ground, on the engine model (ledges included). `mapgen build` prints them before and after, so "plays the same" is a number.
- **Context renders:** `render_map.py --context [--margin N]` draws a map with strips of its connected neighbours. `mapgen build` writes `_preview_context.png` (before above after) for any map with connections.
- **Metrics say where:** the longest straight edge and the largest bare square now come with their location.
- **`plant()` treats a kept `#` block as closed:** an odd run's spare tile no longer lands against a hand-painted cliff, where it was a cut-off pocket. One-tile gaps beside a kept block are still left open, since it may be a walkable path. A new check in `flora_pieces.py` covers both (the old helper fails its three east-side cases).
- **The routes report flags a lost crossing** (`<- CROSSING LOST`), including one whose entrance has no walkable tile left. Context and world renders skip dive/emerge connections.
- **`shoot.py --settle N`:** waits for the area-name popup to clear before the screenshot.

Before/after: `dev/out/Route201_1_preview_diff.png`, `_preview_context.png`, `Route201_1_before.png` vs `_preview.png`, and in-game `Route201_1_ingame_compare.png` (five viewpoints; regenerate with `shoot.py --tag ... --settle 240`).

How it was verified:
| Area | Result |
|---|---|
| Checker | 19 maps, 0 errors; Route 201 0 warnings, no cut-off pockets. Vanilla baseline: 0 unexpected. |
| Rebuild | `mapgen build` from the design reproduces the applied map exactly. Extract round trip on Route 201: 99.1% (the HomeTown gap's trees beside sand, and Tom's cliff corner; see limits). |
| Play | The playthrough (wild battles on) crosses the new route both ways; all autowalks pass, plus Woodstock → Route 201 → HomeTown. Encounters: Route 201's table only; none with an empty party. |
| In-game pieces | Ledge: 20/20 approaches agree, and the terrace tour jumps the ledge and walks back to Woodstock. Flora: 77/77 pieces and 60/60 edge trees behave as the engine model says. |
| Code review | `/code-review medium` raised 10 findings; 8 fixed. `mapgen build` crashed on maps with dive/emerge connections (the new context render). The routes report stayed silent when an edit sealed an entrance. `plant()` would also have filled a walkway beside a walkable `#`. There were argument-parsing bugs in `shoot.py` and `render_map.py --context`, double rendering and a slow goal scan, and the new test overstated its coverage. Deferred: the grammar's tree-beside-sand repair (see limits); and the first tooling commit bundles five changes. |
| Regression set | Conformance 562/562, ledges 490/490 (tours 9/9 groups), shores 624/624, flora 433/433; playthrough, doors, encounters and all autowalks pass; ledge, shore and flora piece tests PASS. Route 201 is now in the default ledge and flora tests. |

Known limits:
- **Extract round trip at hand-painted joins:** Route 201 must be rebuilt from `route201_design.py`, not from an extract. A fresh extract reads the trees beside HomeTown's lane as forest, and a compile's grammar repair (no tree beside sand) would clear the lane's sand. Keeping such joins as `#` in extract only moved the difference to the neighbouring tiles (98.9%), so it was left for a later pass.
- The tree band under HomeTown (rows 0–1) is the map's longest straight edge. It is the seam with HomeTown's own tree band, so it stays.
- The beaver pond keeps its old L-shaped cells: pond shores (`o`) are still learned, not shape-resolved.
- The return trip no longer forces tall grass (it used to, through the old ledges' detour). The grass is still on both sides of the road, so the first encounters come quickly.

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
- HomeTown, Route 201, Woodstock and Woodstock's interiors are populated (milestones 10 and 15; the Center and Mart work, the two-storey house has one resident and an empty upstairs). All text is provisional and hasn't been read by Tom in-game yet.
- Woodstock's Center is the slice's only Pokémon Center (and a Fly destination only once there's a Town Map).
- HomeTown's upstairs room (House2 2F) is empty; the player's house is still vanilla Littleroot's.
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
| Dev bridge (debug builds only): WARP, FLAG, GIVE, MON0, MOVE, FGET, ITEM, SAVE (normal or link), VGET, VSET | `src/field_control_avatar.c` |
| Trainer ceiling 864 → 1376; Maritimes flag block (256) after the daily flags; static asserts | `include/constants/opponents.h`, `flags.h`, `src/event_data.c` |
| Trainer-slide table sized by `TRAINERS_COUNT` (not the ceiling) | `src/trainer_slide.c` |
| Own map sections, appended so no MAPSEC id moves | `src/data/region_map/region_map_sections.json` |
| Save layout stamp (SaveBlock2 0x16, was padding); stale saves refused with a message; build asserts the layout | `include/save_layout.h`, `include/global.h`, `src/save.c`, `src/main_menu.c` |
| Story var block 0x4100–0x41FF in SaveBlock3 (first field; asserted inside sectors 0–4); other ids below 0x8000 aren't vars; Maritimes flag block 768 | `include/constants/vars.h`, `flags.h`, `include/global.h`, `src/event_data.c`, `src/save.c` |
| Save slot sector checksums cover the SaveBlock3 chunk (`CalculateSectorChecksum`) | `src/save.c` |
| Script macros, the debug var editor and the test framework's script header know the story vars | `asm/macros/event.inc`, `src/debug.c`, `include/test/overworld_script.h` |

## Regression set (run before merging anything)
**`dev/regression.py`** runs all of it, serially, and is the merge gate: 42 steps (build, 23 static, 18 in mGBA), about 13 minutes. It must end `0 failed`; quote its evidence lines in the handoff (the report is `dev/out/regression/<run>/report.json`, and says if the tree was dirty). `--only <id>...` for a subset while working (the build always runs). How it guards against silent passes and emulator interference: `dev/README.md`, "Test suites".

Last full run (test-infrastructure-reliability @ `8766a2a6f9`, after the review fixes and the flake fix; ROM `7df037fe…`, unchanged from the published build): 40 gates passed, 2 observed, 0 failed. Conformance 537/537 (108 source tiles beyond the warp's signed 8-bit range, all on vanilla Route 119, reported as untestable), doors 15 round trips, buildings 11/11, respawn 3 real losses, encounters 12 wild battles, ledges 490/490 on 7 maps (4 tours, 3 skipped for wandering people), events 116/116 on 7 maps, save 45/45, shores 624/624, flora 435/435, mobile publish 53/53, authoring 20 tests, harness guards, checker 33 maps 0 errors and vanilla 0 unexpected, reconstruction 87.8% (observed), round trip 87.5–100%.

Add a step to `manifest()` in `dev/regression.py` when a new test or spec'd map joins the set (and a `check` when the test claims coverage its exit code can't prove). The commands it runs, for running one by hand:
```
dev/fastbuild.py
dev/tests/authoring_safety.py         # 20 fixture tests: shared terrain, room collisions, rollback and fault injection
dev/tests/harness_guards.py           # no emulator; 13 negative controls: empty/skipped tests fail, runner timeouts kill the tree, the lock holds
dev/tests/emulator_isolation.py       # two live mGBA sessions stay independent
dev/check_maps.py --baseline          # 0 unexpected, 8 known
dev/check_maps.py                     # 33 maps, 0 errors (3 WARN: Fredericton's 8 dead doors; TownLab's Center upstairs, as vanilla's)
dev/tests/id_budget.py                # no emulator; PASS (520 trainer ids, 766 block flags, 256 story vars, 148 save bytes)
dev/save_layout.py                    # "matches include/save_layout.h" (after any save-related change)
dev/tests/conformance.py              # 532/532 (seeded samples; the count moves when a map changes)
dev/tests/playthrough_slice1.py       # end to end, wild battles on
dev/tests/ingame_doors.py HomeTown_0 Woodstock_2 TownLab   # Woodstock: 6 doors, 2 upper floors; TownLab: 10 doors, 3 upper floors
dev/tests/ingame_buildings.py TownLab Woodstock_2   # entering each Center sets the respawn point, the nurse heals, the Mart sells
dev/tests/ingame_world_revision.py    # a save on a redesigned map continues at its safe tile (--old-rom <rom> for real old saves)
dev/tests/ingame_bridges.py          # every map whose sketch draws H: presses on and beside the deck, on foot and surfing; the crossing
dev/tests/ingame_respawn.py           # three real losses: fresh home, repaired legacy save, saved Center
dev/tests/ingame_encounters.py Route201_1 [--no-party]
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route203_1_2
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route101_2 Route203_1 Fredericton_0
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route201_1 HomeTown_0
dev/tests/ingame_ledges.py            # LedgeLab, Route 203, Route 201 + 4 vanilla routes: 490/490 approaches, tours 10/10 groups
dev/tests/ingame_events.py            # every spec'd map: 114/114 on seven maps (signs, inspect, people, gift, wanderers, item ball, trainer)
dev/tests/ingame_save.py              # 45/45: flags and story vars survive save/reset/CONTINUE and a link save; a stale-stamped save is refused; dev/savefile.py agrees with the game
dev/tests/var_macros.py               # no emulator (WSL mirror); 8/8: the script macros treat story vars as vars (after macro or var-range changes)
dev/tests/ingame_shores.py            # ShoreLab + Route 203: 624/624 edge cases (bump, land, rock, Surf prompt)
dev/tests/ledge_pieces.py             # no emulator; PASS
dev/tests/shore_pieces.py             # no emulator; PASS (vanilla 99.9%, 17/17 shapes, shore round trip)
dev/tests/flora_pieces.py             # no emulator; PASS (vanilla flora, 14/14 shapes, round trip, 300 plantings, kept blocks 7/7)
dev/tests/stamp_pieces.py             # no emulator; PASS (catalog, 37 vanilla doors recognised, round trips, refusals, door plans, room scripts)
dev/tests/bridge_pieces.py            # no emulator; 31 checks (import from vanilla Petalburg in a fixture, shapes, extract)
dev/tests/resize_map.py               # no emulator; 5 fixture tests
dev/tests/ingame_flora.py             # GroveLab, Route 203, Route 201: 435/435 (flora pieces incl. the sign post, staggered edge trees)
dev/tests/mobile_publish.py           # 53/53 in a scratch folder (uses the built ROM; never the real Drive); after mobile.py or save changes
dev/tests/corridor_plan.py            # no emulator; PASS (plan check, seams, cleanup, connection math vs the game, every underlay compiles)
dev/corridor.py check                 # after a plan edit: 7 maps, 0 errors, 0 warnings
dev/tests/reconstruction.py           # 87.8%; only when mapgen/terrain code changes
dev/tests/roundtrip.py                # 87.5-100% with the build's grammar, no repaired cell, guard PASS; when mapgen/terrain code changes
dev/route_stats.py Route201_1         # after a route edit: crossings 53/54 steps, grass avoidable, no trainer forced, 137 tall grass
dev/events.py build design/maps/Route201_1.events.toml   # after an events or map edit: 0 changed, 0 errors
dev/events.py build design/maps/Woodstock_2.events.toml  # 0 changed, 0 errors, crossings 30/30
dev/events.py build design/maps/<Map>.events.toml        # the same for HomeTown_0, HomeTown_House2_1F, Woodstock_Lab/House1/House2/House3_1F
```

## Next milestone (proposed, not started)
The build order is in `region_blueprint.md`, "Build order": M15 Woodstock and M16 the start valley (done), then Route 202, Nackawic, Route 203 and Fredericton.

**Milestone 17 (proposed): Route 202, the river road to the Meductic bend** (`corridor.toml`: 42x36,
folder `Route202_1`, today 42x46). South from Woodstock along the Saint John's west bank (real
data, ~6-7 wide), past islands and intervale fields, then east along the south bank at Meductic.
- **Resize** (`resize_map.py Route202_1 42x36`), then `corridor.py join "Route 202"`: Woodstock's
  south seam moves from the interim 7 to the plan's 16 (and the Fredericton prototype's join to Route
  202 goes: the plan puts Nackawic there; leave Fredericton reachable for the autowalks until M18, or
  re-point those tests). The underlay's river and road are real; the road keeps a verge.
- **World revision 3** for Route 202 (and Fredericton if its join changes), `--old-rom` against the
  M16 phone build.
- **Cliffs first?** The real valley side here is steep: General's brown mountain family (`060-0EF`)
  as shape-resolved vocabulary (like ledges and shores: faces, tops, corners, the 16 cliff-ledge
  joints) would give the river road real bluffs and taller terraces than one ledge step. That is
  a tooling milestone of its own size; recommended as M17's first half, proved on a lab map.
- Islands in the Saint John for Surf later; the Meductic bend's intervale as the route's farmland.
Still open from before:
1. **Tom plays by hand:** the current slice's text is all provisional. Since the corridor will be rebuilt, reading it matters less now; the rebuilt maps carry their events specs over and are reread then.
2. ~~Decide the var plan before any story work~~: done in milestone 11 (256 story vars, 768 block flags; `design/save_format.md`). Story scripts allocate with `dev/save_ids.py`.
3. ~~The woods around HomeTown and Woodstock~~: done; both rebuilt from the plan (M15, M16).
4. **Cliffs (`070/071`):** these also unlock the 16 cliff-ledge joints, terraces taller than one ledge step, and the elevation variety a "hills" biome needs. Rocky shores (`17A–184`) and the dirt/sand boulders (`0E1`/`0E2`) fit here too. Wanted for the valley terraces (Route 201, Route 202).
5. **Shore follow-ups:** pond shores by shape; a bank-to-beach transition tile. (River shores in the rebuilt towns come from the kit.)
6. **Bridges:** the north-south plank deck is done (M15, `H`). Still to come: an east-west deck over a river running north-south (Route 104 has the pieces), Nackawic's long bridge (north-south over the headpond: the plank deck may do; a covered bridge is a Porytiles job), Fredericton's walking bridge (Rustboro has the pieces natively), and a bridge a surfer passes under (Route 110's elevation-15 pieces).
7. **Town vocabulary after stamps:** hedges and fences (Petalburg's `24x` hedge pieces, by shape like ledges), garden beds, town signs on the Center and Mart; Rustboro's paved city buildings with their shadows for Fredericton (M20); a Maritimes gym room once there's a gym design.
8. Later:
   - The player's own house as a Maritimes room (Mom's script is vanilla's), HomeTown's upstairs room, Route 203's people (a hiker in the notch, a fisher on the beach), a rematch-free double battle in the spec.
   - Porytiles for Maritime flora: spruce/fir for a boreal look, birch, log piles, a covered bridge.
   - A Maritimes Town Map.
   - Give `Route102_2` its own flags and trainers, or retire it (it shares Route 102's).

Ideas, not done:
- The walker could read trainer flags so beaten trainers' sight stops being avoided.
- `section_status.py` could list each map's trainers and hidden items from `events.py list`.
- Flower and boulder accents on the terraces (the vocabulary has them now).
- A `landscape.path()` helper for wandering dirt paths and clearing floors (vanilla's Safari Zone style). Route 201's road is drawn from rectangles; a helper that routes a road between two seams with a verge would make the next one quicker.

## Gotchas learned
- **Redesigning a map saves may stand on:** resize with `dev/resize_map.py` first (a reused folder must match the plan's size), then add a world revision (`sWorldRevisions`, raise `MARITIMES_WORLD_REVISION`) in the same milestone, and prove it with `tests/ingame_world_revision.py --old-rom` against the last phone build (Drive's `builds/` holds it; `dev/out/mobile/check.map` is that build's symbol map while `mobile.py` hasn't run since). Without it a phone save lands at its old coordinates, inside whatever stands there now, with the old people and the old terrain's saved view around it.
- **Bridges:** draw `H` two columns wide over every water row where the river runs east-west, with grass at both ends; the road keeps its one-tile grass margin from the deck as from water. A map on a tileset without the pieces is refused with the import command (`dev/tile_import.py bridge <tileset> --apply`). Tree bands: where a street's margin and a creek's leave an odd pair of rows, plant that area on the odd grid (`parity=(0, 1)`) or it stays bare (Woodstock's design does both).
- **Copying tiles:** `dev/tile_import.py` only appends; check a tileset's animation frames (indices past its `tiles.png` that metatiles use) before copying many tiles: the tool refuses to land on them.
- **Regression runs:** use `dev/regression.py`, not the commands by hand, and don't run CPU-heavy work beside it (M14's one `ingame_events` failure came from that). A test that can pass without exercising anything is a bug: when adding a test, make it fail on zero cases and give the runner a `check` for its counts; add a negative control to `tests/harness_guards.py`.
- **Buildings:** place them with `Sketch.place` in the design script (or a `// stamp:` line with `B` cells), never by painting; `mapgen --apply` wires the doors. Name a room by its ground floor, `<Base>_1F` when the template has an upstairs (Centers, two-storey houses). Renaming a room in the sketch makes a new room; the old one stays, orphaned (the dry run shows "new room"). Never delete or reorder a map's warps by hand: rooms find their door by its warp's index (a new map's spawn point must go before the first doors are wired, as TownLab's did). Keep a Center's nurse its first object: the heal location names her local id. One Center per map.
- **Phone builds:** publish from a clean `develop` after the merge (`dev/mobile.py`), not from a milestone branch: the build is named by its commit. Phone emulators find a save by the ROM's file name, which is why the play file is named for its save line and nothing else; never put a date or commit in that name. Save states don't carry across builds (a snapshot of the old build's memory), only in-game saves; in My Boy!, "Quick load on start" must stay off. Never write into `My Drive/MyBoy`: it's My Boy!'s live sync folder, and a change there reaches Tom's phone. The upload goes through Google Drive for Desktop: if it isn't running, the files wait in its cache and the tool says the upload isn't confirmed.
- **Playing by hand:** use `RomHackDev/Play PokeMaritimes.bat` (`dev/play.py`), not `pokeemerald.gba` directly. On 2026-11-03 Tom got "The save file has been erased due to corruption or damage." from a March save sitting beside `pokeemerald.gba`. It had no layout stamp, and SaveBlock1 has grown since, so its last SaveBlock1 sector fails the checksum in both slots. The game calls that erased **before** the stamp check can say "older version": the outdated-save message only appears when a stale save's block sizes happen to match. The launcher reads the save first (`dev/savefile.py`, which agrees with the game in `ingame_save.py`) and sets stale saves aside in `playtest/old_saves/`. That save is kept there.
- **Save layout:** trainer and flag ids are a budget (`dev/tests/id_budget.py`). Raising `MAX_TRAINERS_COUNT_EMERALD` or `MARITIMES_FLAGS_COUNT` moves SaveBlock1 and breaks old saves; do it rarely and generously. The build then stops on `SaveLayoutChanged_*`: run `dev/save_layout.py --update` (it bumps the version, so old saves are refused with a message), rebuild, then `tests/ingame_save.py`. Story state: vars and flags come from `dev/save_ids.py` (256 story vars in SaveBlock3, 766 block flags); keep the 23 unused vanilla vars for engine features. The story block must stay SaveBlock3's first field (a link save writes only sectors 0–4; `save.c` asserts it). `design/save_format.md` has the version history: add a row on every bump. Anything sized by `MAX_TRAINERS_COUNT` costs ROM per id: check `pokeemerald.map` (the trainer-slide table was one).
- **Hand-painted maps:** add a sign post or a flower with `dev/mapgen.py patch <Map> s@x,y`, not a rebuild from an extract (Woodstock rebuilds at 95.8%).
- **Wander ranges:** a 0 in `movement_range_x/y` means *no limit* on that axis, not "stay in the row". Use 1–4 (the spec refuses 0), or a one-axis type like `WANDER_LEFT_AND_RIGHT`.
- **Spec text:** write straight quotes, they become “ ”. `{PLAYER}` works in any text. A text Poryscript rejects only fails at `fastbuild`, not in the dry run.
- **Interiors:** `events.py` starts `scripts.pory` for a room with no scripts. People must not stand on chairs (walkable, but it looks wrong); use the `_events.png` preview.
- **Wanderers in tests:** a wanderer may stand anywhere in its range, so tests keep other events' tiles out of it (`ingame_events.py` does). Find one in RAM by local id (= index + 1 in `object_events`) with `Emu.objects()`.
- **Events:** place people, signs and hidden items with `dev/events.py` from the map's spec, not by editing `map.json`. To move a spec-owned event, edit the spec: a Porymap move is undone by the next `--apply`. A sign needs `s` in the sketch first. Read the dry run's route numbers: a trainer whose sight covers the road shows up as `can't avoid`.
- **Object elevation:** in the game an object's elevation is its tile's (`ObjectEventUpdateElevation`), not the `elevation` in `map.json`, except on multi-level (15) tiles. Use `events.object_elevation`.
- **Battles in tests:** with no badges, a Pokémon above level 10 may disobey. Set `FLAG_BADGE08_GET`, teach a damaging first move (`teach_move("TACKLE", 0)`), and use `Emu.win_battle()` (it sets the SET style).
- **Walker and trainers:** `Walker` avoids trainers' sight by default (a trainer battle can't be fled); pass `avoid_sight=False` under `test_mode()`.
- **Grammar repairs:** `mapgen build` refuses (`GUARD terrain`) a repair that would overwrite existing terrain. Keep hand-painted joins as `#`, or give roads a verge; don't `--force` past it.
- **Test mode:** `Emu.test_mode()` means movement-only: no wild battles, no trainer sight, and story gates open (it sets `FLAG_SYS_POKEMON_GET`). Call it before the player enters the gated map; HomeTown arms its gate on map load. Tests that play as a real player (the playthrough, encounter tests) don't call it.
- **Poryscript:** edit `scripts.pory`, never the generated `scripts.inc`. `fastbuild` copies the generated `.inc` back so git tracks it.
- **Specials:** append new specials at the end of `data/specials.inc`; their ids are positional.
- **Map sections:** add them only with `dev/name_area.py` (appends). Gen 3 popups size their theme table automatically; BW-style popups would need entries.
- **Deprecated globals:** `gPlayerParty`/`gPlayerPartyCount` are deprecated in expansion 1.17.2. Use `gParties[B_TRAINER_PLAYER]` / `gPartiesCount[B_TRAINER_PLAYER]`.
- **Workflow:** each milestone goes on a branch, gets `/code-review medium <branch>`, has its findings fixed and re-verified, then merges into `develop`. Every review so far has found real bugs.
- **Planting on an existing map:** give `plant()` the grid of the forest you edit; Route 203's southern forest starts on row 29, so it uses `parity=(0, 1)`. Keep areas to whole 2-row bands, and never let two `plant` areas overlap. If an old grove straddles two areas, clear it across both first: `plant` refuses to leave a tree cut in half. Check that the diff box stays inside your scope; a stray tuft or a re-tiled tree column shows up there.
- **Flora placement:** a flower, boulder or sapling right above a tree sits on the canopy overhang, and the compiler refuses it. `landscape` helpers already avoid that row.
- **Roads and trees:** the grammar never lets a tree touch sand; it turns the *sand* into grass (trees outrank sand), which can clear a whole lane. Give roads a grass verge, and keep any trees that must stand beside a road (a seam gap) as `#`.
- **Kept boxes:** draw a `#` box around a hand-painted piece so that it holds whole trees only, never half of one. A half tree left outside the box can't be tiled and leaves a 1-tile pocket (mapgen's `WARN reach` catches it).
- **Ledge landings:** the game never checks where a jump lands. Draw ledges in sketches, not by hand; for hand-painted ledges, trust `check_maps.py`'s `ledge` and `trap` results.
- **Dev maps:** LedgeLab sits in `gMapGroup_DevMaritimes`. It ships in the ROM but nothing links to it. Its only warp is a spawn point (`MAP_DYNAMIC`, arrival-only), which gives the checker an entrance. `new_map.py` adds that spawn to every new map; delete it once the map has real connections.
- **Editing an existing map with mapgen:** build without `--fresh` so the existing trees stay put. Read the diff report and `_preview_diff.png` before `--apply`. Move groves by an even number of tiles; an odd shift falls off the 2×2 tree grid and drops trees (`dropped_tree_cells`).
- **Commit order:** a test that expects new map content goes in a commit *after* that content, so every commit passes the regression set.
- **Shores:** draw water at least two tiles wide, and start beaches on straight stretches of shore, not at corners; the compiler names the cells otherwise. To look natural, change a bank by one row at a time and often. Sand next to water becomes a beach automatically. Tall grass, paths and trees still get a grass margin from water.
- **Surf in tests:** warping onto water starts Surf by itself. To surf off a shore as a player would: `give_mon`, `teach_move("SURF")`, set `FLAG_BADGE05_GET`, face the water, then `start_surf()`.
- **Commit messages from PowerShell:** `Out-File -Encoding utf8` writes a BOM into the subject line. Write message files with `[IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
