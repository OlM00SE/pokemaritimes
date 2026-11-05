"""Building stamps: what the catalog holds (dev/mapkit/stamps.toml, mapkit/stamps.py).

  python dev/buildings.py list                 # each stamp: size, door, tilesets, interior
  python dev/buildings.py sheet [Map]          # dev/out/stamps_sheet.png: every stamp drawn,
                                               # labelled (only those that fit Map's tilesets)
  python dev/buildings.py find <Map>           # the stamps standing on a map (as extract sees them)

Placing one: in a design script, `sk.place(p, "pokemon_center", x, y, "Town_PokemonCenter_1F")`
(x, y = the stamp's top-left), or in a sketch a line `// stamp: pokemon_center @ x,y ->
Town_PokemonCenter_1F` with the stamp's cells drawn `B`. `mapgen build` places it, and `--apply`
wires its door (mapkit/buildings.py): an existing room keeps its warp (moved with the door),
a new one is copied from the stamp's interior template (two-floor ones are named <Base>_1F).
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit import stamps
from mapkit.layout import pack


def cmd_list(p):
    print(f"{'stamp':22s} {'size':5s} {'door':7s} {'works on':22s} {'kind':15s} interior template")
    for st in stamps.catalog(p).values():
        print(f"{st.name:22s} {st.w}x{st.h:<3d} {str(st.door):7s} {st.tileset_note():22s} {st.kind:15s} {st.interior}"
              + (f"   BROKEN: {'; '.join(st.problems)}" if st.problems else ""))
        print(f"{'':22s} {st.about}")


def cmd_sheet(p, map_name=None):
    from PIL import Image, ImageDraw
    from mapkit.render import render_layout
    cat = list(stamps.catalog(p).values())
    if map_name:
        L = p.load_map(map_name).layout
        cat = [st for st in cat if st.fits(L.primary, L.secondary)]
        if not cat:
            print(f"no stamp fits {map_name}'s tilesets ({L.primary}/{L.secondary})")
            return
    pad, scale, label = 1, 2, 26
    tiles = []
    for st in cat:
        L = copy.copy(p.load_map(st.source).layout)
        L.width, L.height = st.w + 2 * pad, st.h + 2 * pad
        L.blocks = [pack(0x001, 0, 3)] * (L.width * L.height)
        for (dx, dy), b in st.cells.items():
            L.blocks[(dy + pad) * L.width + dx + pad] = b
        im = render_layout(p, L, scale)
        d = ImageDraw.Draw(im)
        dx, dy = st.door
        x0, y0 = (dx + pad) * 16 * scale, (dy + pad) * 16 * scale
        d.rectangle([x0, y0, x0 + 16 * scale - 1, y0 + 16 * scale - 1], outline=(255, 64, 64), width=2)
        tiles.append((st, im))
    cols = 4
    cw = max(im.width for _, im in tiles)
    ch = max(im.height for _, im in tiles) + label
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, ch * rows), (24, 24, 32))
    d = ImageDraw.Draw(sheet)
    for i, (st, im) in enumerate(tiles):
        x, y = (i % cols) * cw, (i // cols) * ch
        d.text((x + 4, y + 2), f"{st.name} {st.w}x{st.h}", fill=(255, 255, 0))
        d.text((x + 4, y + 13), f"{st.tileset_note()}, {st.kind}", fill=(200, 200, 200))
        sheet.paste(im, (x, y + label))
    out = p.path("dev", "out", "stamps_sheet.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(f"wrote {out} ({len(tiles)} stamps; the door is outlined in red)")


def cmd_find(p, map_name):
    m = p.load_map(map_name)
    warps = {(w["x"], w["y"]): w["dest_map"] for w in m.events("warp_events")}
    found = stamps.recognise(p, m.layout)
    for st, x, y, kept in found:
        dest = p.const_to_map.get(warps.get(st.door_at(x, y)), "(no warp)")
        print(f"  {st.name} @ {x},{y} -> {dest}" + (f"   (keeps {len(kept)} blended cells)" if kept else ""))
    print(f"{len(found)} stamps on {map_name}")


def main(argv):
    if not argv or argv[0] not in ("list", "sheet", "find"):
        print(__doc__)
        return 2
    p = Project()
    if argv[0] == "list":
        cmd_list(p)
    elif argv[0] == "sheet":
        cmd_sheet(p, argv[1] if len(argv) > 1 else None)
    else:
        if len(argv) < 2:
            print(__doc__)
            return 2
        cmd_find(p, argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
