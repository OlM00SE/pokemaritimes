"""Copy vanilla metatiles into a secondary tileset (mapkit/tileimport.py), art and all.

  python dev/tile_import.py bridge gTileset_Petalburg            # dry run: what would be appended
  python dev/tile_import.py bridge gTileset_Petalburg --apply
  python dev/tile_import.py copy gTileset_Rustboro 34E,34F gTileset_Petalburg [--apply]

`bridge` copies the plank bridge's pieces (mapkit/bridges.py: Route 104's deck, from
gTileset_Rustboro) so sketches on that tileset can draw 'H'. `copy` copies any metatiles, given
in the source pair's numbering (secondary ids start at 200). Only appends; re-running is a
no-op. Rebuild afterwards (dev/fastbuild.py): the tiles and palettes are compiled from the PNG
and the .pal files.
"""
import argparse
from mapkit.project import Project
from mapkit import bridges, tileimport


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bridge")
    b.add_argument("target")
    b.add_argument("--apply", action="store_true")
    c = sub.add_parser("copy")
    c.add_argument("source")
    c.add_argument("mids", help="comma-separated hex ids, e.g. 34E,34F")
    c.add_argument("target")
    c.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    p = Project()
    if a.cmd == "bridge":
        source, mids = bridges.SOURCE, list(bridges.SOURCE_PIECES)
    else:
        source, mids = a.source, [int(m, 16) for m in a.mids.split(",")]
    for name in (source, a.target):
        if name not in p.tileset_sources:
            print(f"NOT APPLIED: unknown tileset {name}")
            return 1
    pl = tileimport.plan(p, source, mids, a.target)
    for mid, to in pl.mapping.items():
        print(f"  {source} {mid:03X} -> {a.target} {to:03X}")
    print(f"  appends: {len(pl.new_tiles)} tiles, {len(pl.new_metatiles)} metatiles, "
          f"palette slots {sorted(pl.palettes) or 'none'}")
    for pr in pl.problems:
        print(f"  REFUSED: {pr}")
    if pl.problems:
        print("NOT APPLIED")
        return 1
    if not pl.changes:
        print(f"{a.target} already has these pieces; nothing to do")
        return 0
    if a.apply:
        tileimport.apply(p, pl)
        print("applied; rebuild with dev/fastbuild.py")
    else:
        print("dry run; pass --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
