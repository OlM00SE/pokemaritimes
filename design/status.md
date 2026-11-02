# PokéMaritimes: project status (handoff)

> Updated 2026-11-02. Read this first in a new session. Creative direction lives in
> `region_plan.md`; tooling in `../dev/README.md`; engine facts in `mapping_reference.md`.

## Where we are
**Milestone 2 done** (`develop` at `e24df24f65`, pushed). The first slice, **HomeTown → Route 201 → Woodstock**, is a small playable experience:
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
dev/check_maps.py --baseline          # 0 unexpected
dev/check_maps.py                     # 0 errors (the 1 WARN is Fredericton's 8 dead doors)
dev/tests/conformance.py              # 442/442
dev/tests/playthrough_slice1.py       # end to end, wild battles on
dev/tests/ingame_doors.py HomeTown_0 Woodstock_2
dev/tests/ingame_encounters.py Route201_1 [--no-party]
dev/autowalk.py LittlerootTown_MyHouse_1F_0 HomeTown_0 Route201_1 Woodstock_2 Route202_1 Fredericton_0
dev/tests/reconstruction.py           # 87.8%; only when mapgen/terrain code changes
```

## Next milestone (proposed, not started)
1. **Ledge vocabulary for `mapgen`:** a sketch character, learned tiles and grammar, checked by the engine's jump model. Then riverbanks and rocks.
2. **NPC/sign scaffolding tool:** close the slice's people and sign gaps without hand-editing JSON.
3. Later: Porytiles for Maritime tiles (log piles, covered bridge); a Maritimes Town Map.

## Gotchas learned
- **Test mode:** `Emu.test_mode()` means movement-only: no wild battles, no trainer sight, and story gates open (it sets `FLAG_SYS_POKEMON_GET`). Call it before the player enters the gated map; HomeTown arms its gate on map load. Tests that play as a real player (the playthrough, encounter tests) don't call it.
- **Poryscript:** edit `scripts.pory`, never the generated `scripts.inc`. `fastbuild` copies the generated `.inc` back so git tracks it.
- **Specials:** append new specials at the end of `data/specials.inc`; their ids are positional.
- **Map sections:** add them only with `dev/name_area.py` (appends). Gen 3 popups size their theme table automatically; BW-style popups would need entries.
- **Deprecated globals:** `gPlayerParty`/`gPlayerPartyCount` are deprecated in expansion 1.17.2. Use `gParties[B_TRAINER_PLAYER]` / `gPartiesCount[B_TRAINER_PLAYER]`.
- **Workflow:** each milestone goes on a branch, gets `/code-review medium <branch>`, has its findings fixed and re-verified, then merges into `develop`. Both reviews so far found real bugs.
