# PokéMaritimes: project status (handoff)

> Updated 2026-11-02. Read this first in a new session. Creative direction lives in
> `region_plan.md`; tooling in `../dev/README.md`; engine facts in `mapping_reference.md`.

## Where we are
**Milestone 4 done: Route 203 terraces, the first real route built with ledges** (branch `milestone4-route203-terraces`, merged into `develop`).

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
| Dev bridge (debug builds only): WARP, FLAG, GIVE, MON0 | `src/field_control_avatar.c` |
| Own map sections, appended so no MAPSEC id moves | `src/data/region_map/region_map_sections.json` |

## Regression set (run before merging anything)
```
dev/fastbuild.py
dev/check_maps.py --baseline          # 0 unexpected, 7 known
dev/check_maps.py                     # 17 maps, 0 errors (the 1 WARN is Fredericton's 8 dead doors)
dev/tests/conformance.py              # 480/480 (seeded samples; the count moves when a map changes)
dev/tests/playthrough_slice1.py       # end to end, wild battles on
dev/tests/ingame_doors.py HomeTown_0 Woodstock_2
dev/tests/ingame_encounters.py Route201_1 [--no-party]
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route203_1_2
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0 Route203_1 Route101_2 Route203_1 Fredericton_0
dev/tests/ingame_ledges.py            # LedgeLab, Route 203 + 4 vanilla routes: 470/470 approaches, tours 8/8 groups
dev/tests/ledge_pieces.py             # no emulator; PASS
dev/tests/reconstruction.py           # 87.8%; only when mapgen/terrain code changes
dev/tests/roundtrip.py                # 88-100%; only when mapgen/terrain code changes
```

## Next milestone (proposed, not started)
1. **Shorelines and riverbanks (`11B–12D`)**, using the same recipe: mine the pieces → resolve by shape → test against vanilla → a lab map → in-game test.
   - Route 203 shows why this comes next. The river meets the grass with a hard straight edge, and the sand flat has to sit a row back from the water.
   - Riverbank pieces would let the levee meet the water naturally, and give us beaches.
2. **Rocks and boulders:** small and self-contained. Good for breaking up open meadows like Route 203's upper terrace strip.
3. **Cliffs (`070/071`):** these also unlock the 16 cliff-ledge joints, and taller terraces than one ledge step.
4. **NPC/sign scaffolding tool:** close the slice's people and sign gaps without hand-editing JSON. Route 203 now has natural spots for a hiker or a sign on the levee.
5. Later: Porytiles for Maritime tiles (log piles, covered bridge); a Maritimes Town Map.

Ideas for the ledge design, not done:
- A `--tour` start option for maps with NPCs.
- Flower and rock accents on the terraces, once the vocabulary has them.

## Gotchas learned
- **Test mode:** `Emu.test_mode()` means movement-only: no wild battles, no trainer sight, and story gates open (it sets `FLAG_SYS_POKEMON_GET`). Call it before the player enters the gated map; HomeTown arms its gate on map load. Tests that play as a real player (the playthrough, encounter tests) don't call it.
- **Poryscript:** edit `scripts.pory`, never the generated `scripts.inc`. `fastbuild` copies the generated `.inc` back so git tracks it.
- **Specials:** append new specials at the end of `data/specials.inc`; their ids are positional.
- **Map sections:** add them only with `dev/name_area.py` (appends). Gen 3 popups size their theme table automatically; BW-style popups would need entries.
- **Deprecated globals:** `gPlayerParty`/`gPlayerPartyCount` are deprecated in expansion 1.17.2. Use `gParties[B_TRAINER_PLAYER]` / `gPartiesCount[B_TRAINER_PLAYER]`.
- **Workflow:** each milestone goes on a branch, gets `/code-review medium <branch>`, has its findings fixed and re-verified, then merges into `develop`. All three reviews so far found real bugs.
- **Ledge landings:** the game never checks where a jump lands. Draw ledges in sketches, not by hand; for hand-painted ledges, trust `check_maps.py`'s `ledge` and `trap` results.
- **Dev maps:** LedgeLab sits in `gMapGroup_DevMaritimes`. It ships in the ROM but nothing links to it. Its only warp is a spawn point (`MAP_DYNAMIC`, arrival-only), which gives the checker an entrance. `new_map.py` adds that spawn to every new map; delete it once the map has real connections.
- **Editing an existing map with mapgen:** build without `--fresh` so the existing trees stay put. Read the diff report and `_preview_diff.png` before `--apply`. Move groves by an even number of tiles; an odd shift falls off the 2×2 tree grid and drops trees (`dropped_tree_cells`).
- **Commit order:** a test that expects new map content goes in a commit *after* that content, so every commit passes the regression set.
- **Commit messages from PowerShell:** `Out-File -Encoding utf8` writes a BOM into the subject line. Write message files with `[IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
