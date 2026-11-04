# PokéMaritimes: regional blueprint (v0.1, 2026-11-04)

> Tom's direction (2026-11-04): **follow the real geography of the Maritimes as closely as
> practical.** Recognizable landmasses, coastlines, rivers and relative locations, with exaggerated
> terrain and the full range of biomes. *Geography guides the world; gameplay guides the details.*
> The frame takes in New Brunswick, Nova Scotia, PEI, Cape Breton, the Gaspé, Anticosti and the
> Gulf of St. Lawrence. Development stays in the western NB corridor (HomeTown → Woodstock →
> Fredericton); everything else here is a blueprint, not a plan of work.
>
> This updates `region_plan.md`'s "real geography is an influence, not a 1:1 copy": geography
> now comes first, and a departure from it needs a gameplay reason.

## The tool
`dev/blueprint.py` draws the real geography (Natural Earth 1:10m, public domain, clipped by
`dev/geo_extract.py` into `design/region/geo/`) with the anchor places in
`design/region/anchors.toml`, and measures how our connected maps fit them:
- `dev/out/blueprint_region.png`: the whole frame, the anchors, a 50 km grid, our maps as boxes.
- `dev/out/blueprint_corridor.png`: western NB with our maps laid over the real river, as they
  are now (top) and with the planned maps (`[[plan]]` in `anchors.toml`) inserted (bottom).
- The report: one scale (km per tile) and an offset fitted to the anchors that have a map, each
  anchor's error in km, and real vs game bearings between neighbouring anchors.

Use it whenever a map is added or a connection changes: the fit error should not grow without a
gameplay reason. It reads only data; it changes nothing.

## How real geography maps onto Emerald's system
1. **Topology is exact.** What connects to what, which bank of a river a town stands on, the
   order of places along a river or coast, and the side a river enters from. Breaking one of these
   needs Tom's okay.
2. **Directions are close.** Between neighbouring anchors the game's bearing stays within about
   30° of the real one. The blueprint report prints it.
3. **Scale is per section, not global.** Hoenn's own Town Map runs from 20 to 40 tiles per square
   (Route 103 vs Route 110, measured), so it's a schematic too. Inside a section (western NB, the
   Fundy coast...) one scale holds so distances feel right; between sections, the empty parts are
   compressed. The corridor's fitted scale, about **0.6 km per tile**, is the reference for western
   NB.
   - At that density the whole frame (about 780 × 810 km) would be some 1,250 tiles across,
     roughly twice Hoenn. So the outer sections must be coarser, and the Gulf, the central NB
     barrens and open sea are compressed hardest.
   - **Start areas are zoomed in.** HomeTown and Route 201 cover about 10 real km in 58 tiles, as
     Littleroot and Route 101 do. The fit leaves HomeTown out.
4. **Rivers are continuous and flow the right way.** A river crosses every seam it meets at the
   same width and position, and the real river's bends survive as the route's shape. The Saint
   John is the backbone of western NB: wide enough to Surf below Woodstock, a lake at the
   Mactaquac headpond.
5. **Coastlines are recognizable at Town Map scale, not tile by tile.** The Bay of Fundy, the
   Northumberland Strait, PEI's crescent, the Chignecto isthmus and Cape Breton's Bras d'Or read
   from the shapes of the sections, not from tracing the shore.
6. **Terrain is exaggerated, never invented against the grain.** NB's rolling hills become ledges
   and terraces; Mount Carleton, the Chic-Chocs and the Cape Breton Highlands become real
   mountains; the Fundy cliffs become cliffs. A desert or a volcano would need a gameplay case and
   a Maritime excuse (the Sable Island dunes, the Magdalen Islands' red cliffs).
7. **Borders are the edge of the world.** Maine and Québec west of the Gaspé are out of the
   region: the land there is forest or hills that close the map, never a road.

## The Town Map: decision deferred
The frame is about as tall as it is wide, and the GBA Town Map is 28 × 15 squares. Fitted to the
frame's width (28 km per square), a 28 × 15 map covers only the northern half: the dashed box in
`blueprint_region.png`. When the Town Map is built (`status.md`, "Later"), the options are:
- **Squeeze the empty parts:** compress the Gulf and the Gaspé–Anticosti strait north to south,
  so the land keeps its shape. Recommended: it's what Hoenn's map does with the sea.
- A taller or scrolling custom map (new art and engine work).
- Fewer northern areas (drop Anticosti or the north Gaspé shore).

Nothing in the corridor depends on this.

## The region in sections (*all ideas; Tom decides*)
| Section | Real extent | Biome (exaggerated) | Possible role |
|---|---|---|---|
| **Upper Saint John valley** | Woodstock, Hartland, the headpond, Fredericton | River valley, rural woodland, farmland | The opening: the corridor below |
| Northern highlands | Edmundston, Mount Carleton, the Restigouche | Deep boreal forest, the region's high peaks | Mid-game wilderness, a mountain |
| Gaspé | Campbellton to Percé, the Chic-Chocs | Sea cliffs, mountains, fishing villages | Late game; Percé Rock as a landmark |
| Anticosti | The island | Remote limestone island, cliffs, waterfalls | Post-game or legendary island |
| Acadian coast | Bathurst, Miramichi, Kouchibouguac | Sandy barrier beaches, salt marsh, salmon rivers | Coastal towns, Surf routes |
| Fundy | Saint John, Fundy NP, Hopewell Rocks, Grand Manan | Fog, cliffs, tide flats, sea stacks | Port city, tide mechanics |
| Moncton and Chignecto | Moncton, the isthmus, Tantramar marshes | Crossroads, marsh | The hinge between NB and NS |
| PEI | Charlottetown, red cliffs, farmland | Red sand, dunes, farmland | Confederation Bridge or a ferry |
| Nova Scotia mainland | Annapolis Valley, Halifax, the South Shore | Orchards, dykelands, granite coast, big city | Late game; Halifax as the League? |
| Cape Breton | The Highlands, Bras d'Or, Sydney | Mountains over the sea, a salt-water lake | Endgame |
| Offshore | Magdalen Islands, Sable Island | Red cliffs, dunes, wild horses | Ferries, post-game |

## The corridor: assessment of the existing maps
Real geography (anchors in `anchors.toml`):
- **Woodstock** is on the river's **west bank**, where the Meduxnekeag comes in from the west.
  The Maine border is only about 10 km west, so "west of Woodstock" is a short strip of hills.
- **Below Woodstock** the Saint John runs **south** for about 18 km to Meductic, then turns
  **east** for about 75 km: past Nackawic (the giant axe), along the Mactaquac headpond (wide,
  lake-like; Kings Landing heritage village on its south shore), over the Mactaquac Dam, and into
  Fredericton.
- **Fredericton:** the river flows west to east through the city. The downtown (the Legislature,
  Officers' Square, the walking bridge) is on the **south bank**; the north side is residential,
  and the Nashwaak joins there from the north. The road from Woodstock arrives on the south bank.
- **Upriver**, north of Woodstock, Hartland has the world's longest covered bridge.

How our maps fit (`dev/blueprint.py`; the overlay is `blueprint_corridor.png`):
| Map | What fits | What doesn't |
|---|---|---|
| HomeTown_0 | A forest village at the region's western edge, as wanted | It sits north of Route 201, so Woodstock is ESE instead of due east (26° off: within tolerance). Zoomed in, as start areas are. |
| Route201_1 | A logging road east into Woodstock's west side: right direction, right biome | Nothing. The Meduxnekeag could be its creek one day (an idea). |
| Woodstock_2 | River on the east side flowing south: **the town is on the west bank**, as in reality | Nothing structural. The pond in the south-west corner is where the Meduxnekeag's mouth would be (an idea; Tom's hand map). |
| Route202_1 | Leaves Woodstock south along the west bank and turns east with the river: **the right shape** | It's the south leg drawn long (46 tiles for about 18 km), and **the 75 km east leg along the headpond is missing**: the river turns east and Fredericton starts at once. Borrows Route 103's name; no wild Pokémon, people or signs. |
| Fredericton_0 | River west to east through the middle; one footbridge; the player arrives on the south bank | **The Legislature-style building is on the north bank**; the real downtown is on the south bank. 8 dead doors, no people or signs, borrows Rustboro's name and music. |
| Route203_1 onward | Leaves Fredericton east along the south bank, toward Oromocto | Out of scope now. |

**In numbers:** fitted to Woodstock and Fredericton, our maps are **38 km** off in all, and
Fredericton lies **SE** of Woodstock instead of **ESE** (30° off). Inserting one map of about
60 × 34 tiles for the headpond leg between Route 202 and Fredericton brings it to **12 km** and
9°, with nothing else moving except the maps east of Fredericton, which shift as a block. The
plan panel of `blueprint_corridor.png` shows it.

## The corridor blueprint
```
            (Maine border: forested hills close the map)
HomeTown ─ Route 201 ─ WOODSTOCK ─ (north, later: Hartland covered bridge, potato country)
                          │
                       Route 202   south leg along the west bank (exists)
                          │
                          └─ Headpond route ─ FREDERICTON ─ Route 203 → Oromocto (exists)
                             Nackawic, Kings Landing,        south bank: downtown
                             the Mactaquac Dam               north bank: residential, Nashwaak
```
- **Route 202:** keep it. It's Tom's map, it has the right shape, and its south leg is close
  enough. Later (optional): a Meductic landmark where the river turns.
- **The headpond route (new, about 60 × 34):** the river widens into the headpond: a wide
  Surf-able lake to the north, the road along its south shore through woods and old farmland, a
  Kings Landing-style heritage hamlet (a couple of houses, a mill), and the dam at the east end as
  the gateway to Fredericton. A small Nackawic-style stop could come later as its own town if the
  route feels long.
- **Fredericton:** the city is Tom's hand map. To match reality, the Legislature-style building
  belongs on the south bank. Options for Tom: swap the halves, or read the north building as
  something that really is on the north side (the Marysville cotton mill, a big brick mill on the
  Nashwaak). No change without his okay.

## What this changes in practice
- New maps are placed from the blueprint: its anchors and section scale first, then the design.
- The blueprint report is part of a map milestone's verification (fit error, bearings), beside
  the checker, renders and in-game tests.
- `region_plan.md` stays the creative brief; this file is the geography.
