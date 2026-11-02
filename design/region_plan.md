# PokéMaritimes: region plan (DRAFT v0.2)

> Status: **direction, not a locked map.** Tom set the creative direction (v0.2,
> 2026-11-02). Claude organised it. Anything marked *idea* is a proposal for Tom.
> Execution stays local: build one excellent small area, then grow outward.

## Creative direction (from Tom)
- A region inspired by **the Maritimes as a whole** (NB, NS, PEI), not just one corner of New Brunswick.
- Real geography is a **strong influence, not a 1:1 copy.** Exaggerate, compress, or rearrange whenever it makes a better Pokémon world.
- Maritime landscapes are the base, but the region must still offer the full range of classic Pokémon biomes.
- Early game: start in a **rural western/central NB forestry area**, pass through forests and small communities, and head for a **Fredericton-style river-valley city**. From there, branch toward **Saint John / the Bay of Fundy** and **Moncton / eastern NB**.
- Later: Halifax, PEI, offshore islands, and more. **Not locked down yet.**

## Pillars
- Classic GBA feel (Emerald tileset language). Gen 1–6 Pokédex. Exploration first.
- Quality over coverage. A small area is finished (see *Definition of done*) before the next one starts.
- Each part of the region should feel different at a glance: its own palette, landmarks, music, and Pokémon.

## Biome palette: Maritime source → Pokémon biome
How the real landscapes cover the classic biome list. This drives tileset and tooling priorities, not map placement.

| Pokémon biome | Maritime source | Signature details | Tiles we have / need |
|---|---|---|---|
| Dense forest | NB Crown land, Christmas Mountains | Spruce/fir, logging roads, cut blocks, log piles | Trees ✓; logging pieces *need* |
| River valley | Saint John River, Miramichi | Wide river, islands, covered bridges, intervales | River/bridge ✓ (Woodstock, Fredericton); covered bridge *need* |
| Farmland | Upper Saint John potato belt, Annapolis Valley, PEI | Fields, barns, orchards, dykelands | Fields partly ✓ (Petalburg/Fallarbor bits) |
| Port city | Saint John, Halifax | Harbour, cranes, ferries, brick | Slateport/Lilycove pieces ✓ |
| Rugged rocky coast | Fundy cliffs, Peggy's Cove granite | Sea stacks, tide flats, lighthouses | Cliffs/rocks partly ✓; *needs* cliff/shore vocabulary |
| Foggy shoreline | Fundy and Atlantic fog | Fog weather, low visibility, foghorns | `WEATHER_FOG_HORIZONTAL` ✓ (engine) |
| Red sand & dunes | PEI north shore, Sable Island | Red cliffs, marram grass | Sand ✓; red palette *need* |
| Islands | Grand Manan, Campobello, Sable | Ferries, whales, puffins | Ocean ✓ |
| Highlands / mountain | Mount Carleton, Cape Breton Highlands | Bald peaks, steep cliffs over sea | Mountain pieces ✓ (Hoenn) |
| Remote wilderness / bog | Central NB barrens, peat bogs | Bogs, moose country | Swamp-ish pieces partly ✓ |
| Caves | Gypsum caves, mines (Albert County) | Gypsum caves, karst, old mines | Cave tilesets ✓ |

## Early-game arc (the part that matters now)
```
[Forestry village] → forest route → [small river town] → river route → [Fredericton-style city]
                                                                           ├→ toward Saint John / Fundy
                                                                           └→ toward Moncton / eastern NB
```
The existing maps already fit this arc:

| Map (current name) | Role in the arc | Inspiration ideas (*Tom decides*) |
|---|---|---|
| **HomeTown_0** | Start: a small forestry village at the forest edge | *idea:* Boiestown/Stanley/Juniper-style mill or woodsmen village: sawmill yard, log piles, a ranger station |
| **Route201_1** | First forest route | Logging road through spruce; the first tall grass |
| **Woodstock_2** | First community on the river | Upper Saint John River town; covered-bridge country, potato fields |
| **Route202_1** | River route south | River on one side, forest on the other |
| **Fredericton_0** | River-valley city (1st gym?) | Legislature, river, walking bridge |
| Route203_1 / Route203_1_2 | East out of the city: the future branch point | Rough blockouts |
| Route101_2 / Route102_2 | Copies of Hoenn routes | *Replace or remove later* |

## The first slice: HomeTown → Route 201 → Woodstock
*Proposal.* This is a smaller target than all of Section 1: the **first three maps the player sees.** Fredericton is a big city and comes next, once the slice is solid.

### Definition of done (applies to any area)
1. **Terrain:** composed, readable, and `check_maps.py` clean (no ERROR, no unexplained WARN).
2. **Doors:** every door leads somewhere. Interiors can reuse vanilla layouts at first.
3. **Wild Pokémon:** every grass map has an encounter table that fits the biome. It's verified in-game.
4. **People:** at least a few NPCs and signs per town. The route gets a trainer or two.
5. **Identity:** its own map section name (not borrowed from Hoenn) and suitable music.
6. **Verified in-game:** autowalk through the slice, conformance on every map, screenshots reviewed.

`dev/section_status.py` reports items 2–5 automatically. Run it to see what's still missing.

## Wider region (*ideas, deliberately unlocked*)
| Area | Real inspiration | Possible role |
|---|---|---|
| Saint John | Port; Reversing Falls | Tidal-rapids puzzle, industrial harbour |
| Fundy coast | Hopewell Rocks, Fundy Park, fog | Low/high tide routes, cliffs, fog |
| Moncton / eastern NB | Magnetic Hill; Acadian coast | Crossroads town; colourful fishing villages |
| Miramichi / Mount Carleton | Salmon rivers; highest peak | Deep wilderness, mountain |
| PEI | Red cliffs, farmland, Confederation Bridge | Bridge or ferry crossing |
| Annapolis Valley | Orchards, dykelands | Farm country |
| South Shore | Lunenburg, Peggy's Cove | Rocky Atlantic coast |
| Halifax | Harbour, Citadel Hill | Big city, late game |
| Cape Breton Highlands | Cabot Trail | Mountains over the sea, endgame |
| Offshore islands | Grand Manan, Sable Island | Ferries, isolated islands, post-game |

## What the vision asks of the pipeline (priority order)
1. **Completeness tooling** (done: `section_status.py`, dead-door check). It keeps small areas honest.
2. **Vocabulary for river-valley and forest maps:** ledges, rocks, shoreline/riverbank edges, bridges. These cover the whole early-game arc.
3. **Stamps for town pieces** (houses, PC, Mart) with their door warps placed automatically, so a new town never ships with dead doors.
4. **Porytiles** for Maritime-specific tiles (log piles, covered bridge, red sand, lighthouses). Only once a map actually needs one.
5. Later: cliff/elevation vocabulary for the coast; fog and tide mechanics.

## Open questions for Tom
- HomeTown's name and identity: is a forestry/mill village right?
- Real names or Pokémon-ified ones? (Woodstock and Fredericton are currently real.)
- How many gyms, and where is the League? Bridge or ferry to PEI? (*Not urgent.*)
- Routes 101_2 / 102_2 (Hoenn copies): delete once the 203 branch is designed?
