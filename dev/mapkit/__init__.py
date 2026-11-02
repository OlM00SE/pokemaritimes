"""mapkit: read, render, validate, simulate, and generate pokeemerald-expansion maps.

Modules
  project  - project index: layouts, maps, tilesets, behavior tables, script labels
  tileset  - tiles/palettes/metatiles/attributes for a primary+secondary pair
  layout   - Layout (map.bin grid, read/write) and MapData (map.json, read/write)
  engine   - faithful port of the overworld movement rules (collision, elevation,
             ledges, directional blocks, surfing, connections, event triggers)
  render   - PNG rendering with optional overlays (collision, elevation, behavior, events)
  checks   - validators built on the engine model

All engine rules cite the expansion source they mirror; see design/mapping_reference.md.
"""
