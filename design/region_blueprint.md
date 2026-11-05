# PokéMaritimes: regional blueprint (v0.2, 2026-11-04)

> Tom's direction (2026-11-04): **follow the real geography of the Maritimes as closely as
> practical.** Recognizable landmasses, coastlines, rivers and relative locations, with exaggerated
> terrain and the full range of biomes. *Geography guides the world; gameplay guides the details.*
> The frame takes in New Brunswick, Nova Scotia, PEI, Cape Breton, the Gaspé, Anticosti and the
> Gulf of St. Lawrence.
>
> And, the same day: **the existing maps are prototypes, not commitments.** HomeTown, Woodstock,
> Fredericton and the routes between them built the tooling; any of them may be redesigned or
> replaced if the result is better and more geographically true. Claude takes creative ownership
> of the world-building. Work stays in small, tested milestones, recoverable through git, and
> focused on the corridor: a rural start west of Woodstock → Woodstock → down the Saint John to
> Fredericton.
>
> This replaces `region_plan.md`'s "real geography is an influence, not a 1:1 copy".

## The tools
| Tool | What it does |
|---|---|
| `dev/corridor.py check` | Checks the corridor plan (`design/region/corridor.toml`): overlaps, reachability, the engine's map size limit, and every seam: the river and the road must cross it on both sides, at least 2 tiles wide. Lists the joins it derives (map.json offsets) and what changes against the game's current connections. |
| `dev/corridor.py render` | `dev/out/corridor_plan.png`: the planned maps over real geography, with the river (real data, exaggerated width) and the road drawn at tile resolution. |
| `dev/corridor.py underlay "<Map>"` | A starter sketch of a planned map: the real river `~` and the road `=` exactly where the plan has them, so every map's design starts on the true geography and its seams already match its neighbours'. Design scripts can call `geo.Plan().underlay(name)` directly. |
| `dev/corridor.py compile` | Builds every underlay with `mapgen`'s compiler on a blank in-memory layout of the planned size: the starting point is always buildable. A reused folder of another size must be resized first (`check` lists the sizes; all five differ today, so each rebuild starts with a resize). |
| `dev/blueprint.py` | The whole region: real coastlines, rivers, borders, anchor places, and the corridor plan; plus how the *game's current maps* fit reality (fitted scale, error in km, bearings). |
| `dev/tests/corridor_plan.py` | The plan's checks: projection, connection math against the game's real map.json, seams, the water cleanup, the checker's errors, every underlay compiles. |

Data: `design/region/geo/` (Natural Earth 1:10m, public domain, clipped by `dev/geo_extract.py`),
`design/region/anchors.toml` (real places), `design/region/corridor.toml` (the plan of record).

## How real geography maps onto Emerald's system
1. **One projection per section.** A section (here the western NB corridor) is planned in *world
   tiles*: one scale, origin on a real place. A map is a rectangle in that frame, so it's also a
   real-world rectangle; maps join where their edges touch, and the connections and offsets
   follow from the rectangles. The corridor uses **0.5 km per tile** with Woodstock at (0, 0).
2. **Rivers come from real data.** The Saint John's centreline (Natural Earth, lightly smoothed)
   is drawn into every map at an exaggerated width that varies along it: about 6 tiles at
   Woodstock, 10–11 on the Mactaquac headpond, 7–8 below the dam. Its bends are where they really
   are. Because all maps are cut from one world raster, a river always crosses a seam at the same
   place on both sides.
3. **Insets for the zoomed-in start.** Real Woodstock is only about 10 km from Maine, so the start
   valley (HomeTown, Route 201) is an *inset*: planned in the same frame but not to scale, with
   its water (the Meduxnekeag) drawn by hand. Start areas are always zoomed in (Littleroot and
   Route 101 are too).
4. **Topology is exact; directions are close.** Which bank a town is on, the order of places along
   the river, which way the water flows: exact. Bearings between neighbouring places stay within
   about 30°.
5. **The road is part of the plan.** A hand-drawn road fixes where the way through crosses each
   seam, keeps a verge from the water (the compiler's grammar gives water a grass margin), and
   follows the real highways' banks: the Meduxnekeag's south bank, then the Saint John's west and
   south banks.
6. **Exaggerate terrain, don't invent against the grain.** NB's rolling hills become ledges and
   terraces; Mount Carleton, the Chic-Chocs and the Cape Breton Highlands become real mountains;
   the Fundy cliffs become cliffs.
7. **Borders are the edge of the world.** Maine and Québec west of the Gaspé are outside the
   region: forest or hills close the map there, never a road.
8. **Scale varies between sections.** Hoenn's own Town Map runs from 20 to 40 tiles per square
   (Route 103 vs Route 110). At the corridor's density the whole frame (about 780 × 810 km) would
   be some 1,500 tiles across, so later sections are coarser and the Gulf and the empty interior
   are compressed hardest.

## The Town Map: decision deferred
The frame is about as tall as it is wide; the GBA Town Map is 28 × 15 squares. Fitted to the
frame's width (28 km per square) it covers only the northern half (the dashed box in
`blueprint_region.png`). Options when it's built: squeeze the Gulf and the Gaspé–Anticosti strait
north to south so the land keeps its shape (recommended; it's what Hoenn's map does with the sea),
a taller or scrolling custom map, or fewer northern areas.

## The region in sections (*ideas*)
| Section | Real extent | Biome (exaggerated) | Possible role |
|---|---|---|---|
| **Upper Saint John valley** | The border hills, Woodstock, Hartland, the headpond, Fredericton | Hardwood valleys, river valley, farmland | The opening: the corridor below |
| Northern highlands | Edmundston, Mount Carleton, the Restigouche | Deep boreal forest, the region's high peaks | Mid-game wilderness, a mountain |
| Gaspé | Campbellton to Percé, the Chic-Chocs | Sea cliffs, mountains, fishing villages | Late game; Percé Rock as a landmark |
| Anticosti | The island | Remote limestone island, cliffs, waterfalls | Post-game or legendary island |
| Acadian coast | Bathurst, Miramichi, Kouchibouguac | Barrier beaches, salt marsh, salmon rivers | Coastal towns, Surf routes |
| Fundy | Saint John, Fundy NP, Hopewell Rocks, Grand Manan | Fog, cliffs, tide flats, sea stacks | Port city, tide mechanics |
| Moncton and Chignecto | Moncton, the isthmus, Tantramar marshes | Crossroads, marsh | The hinge between NB and NS |
| PEI | Charlottetown, red cliffs, farmland | Red sand, dunes, farmland | Confederation Bridge or a ferry |
| Nova Scotia mainland | Annapolis Valley, Halifax, the South Shore | Orchards, dykelands, granite coast, big city | Late game; Halifax as the League? |
| Cape Breton | The Highlands, Bras d'Or, Sydney | Mountains over the sea, a salt-water lake | Endgame |
| Offshore | Magdalen Islands, Sable Island | Red cliffs, dunes, wild horses | Ferries, post-game |

## The corridor: what the prototypes taught
`dev/blueprint.py` fits the game's current maps to the real places: 38 km off in all, Fredericton
SE of Woodstock instead of ESE. They got the river's *shape* right (Woodstock on the west bank;
Route 202 leaving south and turning east; Fredericton's river west to east), but:
- the river's **75 km east leg** (Meductic, Nackawic, the headpond, Kings Landing, the dam) is
  missing: Fredericton starts where the river turns;
- the south leg is drawn long (46 tiles for about 18 km);
- **the Meduxnekeag isn't there.** Woodstock stands at its mouth, and it's the natural spine for a
  start valley "west of Woodstock";
- Fredericton's Legislature-style building is on the north bank; the real downtown is south;
- none of the towns has the river where the real town has it (Woodstock's downtown is at the
  confluence; Fredericton spans both banks with a walking bridge).

So the corridor is **re-planned from the geography up** rather than patched, reusing the map
folders (their warps, interiors, scripts and tests carry over) and rebuilding their contents.

## The corridor plan (`design/region/corridor.toml`)
Real geography it rests on: the **Meduxnekeag** rises in the hills on the Maine side and flows
north-east into **Woodstock**, joining the Saint John at downtown (mouth about 46.148 N,
67.573 W). Below Woodstock the **Saint John** runs south about 18 km to **Meductic**, then turns
east for about 75 km: past **Nackawic** on the north bank (linked to the Trans-Canada on the south
bank by the Hawkshaw Bridge), along the **Mactaquac headpond**, past **Kings Landing** on the south
shore, over the **Mactaquac Dam**, and into **Fredericton**, whose downtown is on the south bank.

```
      [HomeTown] ── Route 201 ── [WOODSTOCK] ── (north, later: Hartland, the covered bridge)
       inset       Meduxnekeag       │
                   valley (inset) Route 202  the river road south, Meductic bend
                                     │
                                     └── [NACKAWIC] ── Route 203 ─────── [FREDERICTON] ── (east, later)
                                         bridge town    the headpond,      downtown on the
                                         (north bank)   Kings Landing,     south bank
                                                        the dam
```

| Map | Size | Folder | Design |
|---|---|---|---|
| HomeTown | 34×28 | HomeTown_0 | A hamlet in the Meduxnekeag hills against the border; forest closes the west and north. The brook comes down from the hills through the village; a small sawmill yard; the road leaves east. |
| Route 201 | 52×28 | Route201_1 | The **Meduxnekeag valley**: the creek runs east the whole way, the road on its south bank. Appalachian hardwood forest (the real valley's preserve), a farm clearing, a ledge terrace down to the creek flats, a beaver pond. |
| Woodstock | 48×42 | Woodstock_2 | **The confluence town** on the west bank: the Meduxnekeag comes in from the south-west and meets the Saint John at downtown. Main street by the big river, a bridge over the creek, the wildlife station. North edge: the way to Hartland (later). |
| Route 202 | 42×36 | Route202_1 | **The river road**: south along the west bank past islands and intervale fields, upland ledges down to the flats; at Meductic the river swings east and the road follows its south bank. |
| Nackawic | 36×42 | new | **The bridge town**: the road stays on the south bank (Pokiok); a long bridge crosses the widening headpond to Nackawic on the north bank: the mill and the giant axe. |
| Route 203 | 62×46 | new | **The headpond**: a wide lake, the road on the south shore through mixed woods and old farms, the Kings Landing heritage hamlet, islands for Surf later. Ends past the dam's bend, the gateway to Fredericton. |
| Fredericton | 52×60 | Fredericton_0 | **The capital on the river**: downtown on the south bank (the Legislature, Officers' Square, the Green), the walking bridge to the north side, where the Nashwaak comes in. East exit toward Oromocto (later). |

Pacing: start hamlet → first route → river town → river route → a small town with a Pokémon
Center halfway → a long scenic route → the capital. That's the Littleroot → Rustboro rhythm, laid
on the real river.

Map names are provisional (the routes may be renumbered). The prototypes east of Fredericton
(Route203_1, Route203_1_2 and the Hoenn copies Route101_2/102_2) stay attached as they are until
that area's turn.

## Build order (each a milestone)
1. **M13: the plan of record and its tools** (this): plan, checks, underlays, tests. No game data
   changes.
2. **M14: building stamps** (done). Ten vanilla buildings (Pokémon Center, Mart, gym, five
   houses, the lab) are placed from design scripts (`Sketch.place`), and `mapgen --apply` wires
   their doors: a moved building keeps its room, a new one gets a copied room, and the Center and
   Mart rooms work (the nurse heals and sets the respawn point; the clerk sells). Extract
   recognises the buildings already on HomeTown and Woodstock with their rooms, so they can be
   moved in the rebuilds. TownLab is the dev map. Rustboro's paved city buildings (Fredericton)
   are not stamps yet: that's M20's research.
3. **M15: Woodstock**, the anchor town. First a small `resize_map` step (a layout to the planned
   size, events kept or reported if they fall outside); every reused folder needs it. Then: the confluence, downtown, the creek bridge (which vanilla
   bridge pieces fit, and how their elevations work, is research for that milestone), the
   station, and probably the corridor's first Pokémon Center and Mart (stamps; the station, its two
   houses and their rooms carry over by moving their stamps). Its seams move to the plan (Route 201's and Route 202's
   connections are re-offset; until they're rebuilt, the creek meets an old seam, which is
   acceptable for one milestone).
4. **M16: the start valley**: HomeTown and Route 201 together, along the Meduxnekeag (the starter
   scene and the events specs move with them).
5. **M17: Route 202**, **M18: Nackawic** (a long bridge), **M19: Route 203**,
   **M20: Fredericton.** The dam and the giant axe need custom tiles (Porytiles), so they get
   stand-ins first.

Every map milestone: start from the underlay, design with the kit, keep the plan's seams,
`corridor.py check`, the usual three-way verification (checker, renders, in-game), the
regression set, review, then the phone build.
