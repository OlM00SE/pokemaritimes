"""Plank bridges (mapkit/bridges.py) and copying vanilla metatiles between tilesets
(mapkit/tileimport.py). No emulator; no game data changes (imports run in a fixture).

  python dev/tests/bridge_pieces.py

1. Import, in a fixture: the bridge's four pieces go into a copy of gTileset_Petalburg as three
   tiles, palette slot 11 and four metatiles; every copied metatile draws pixel for pixel as
   Rustboro's original; Petalburg's existing tiles, palettes and metatiles are unchanged byte
   for byte; a second run appends nothing. Refused: no free palette slot, a tile index an
   existing metatile already uses (animation frames); a late failure restores every byte.
2. Shapes, compiled in memory on a Rustboro layout (the pieces' own tileset): a deck across a
   river running east-west builds with vanilla's pieces, walkable at elevation 3, and the grass
   below loses its bank; the banks beside it are the plain river's. Refused: one or three
   columns, ragged rows, a river running north-south, a boulder or sand at an end, a tileset
   that doesn't have the pieces.
3. Extract finds the deck again ('H') and recompiles it block for block; a deck cell that
   isn't part of a valid strip stays '#'.
"""
import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import warnings
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mapkit.project import Project, REPO, NUM_TILES_IN_PRIMARY
from mapkit.layout import pack
from mapkit.sketch import Sketch, SketchError, compile_sketch, extract_bridges, CHAR_TO_CLASS
from mapkit import bridges, shores, tileimport

TARGET = "gTileset_Petalburg"
results = []


def check(ok, what):
    results.append(bool(ok))
    print(f"  {'ok ' if ok else 'FAIL'} {what}")


def metatile_rgb(ts_pair, mid):
    """The metatile's two layers composed as RGB, 16x16 (palette colour 0 transparent)."""
    out = [None] * 256
    for layer in (0, 1):
        for q in range(4):
            v = ts_pair.entries(mid)[layer * 4 + q]
            px = ts_pair.tile(v & 0x3FF) or [0] * 64
            pal = ts_pair.palette(v >> 12)
            for i, c in enumerate(px):
                x, y = i % 8, i // 8
                if v & 0x400:
                    x = 7 - x
                if v & 0x800:
                    y = 7 - y
                if c or layer == 0:
                    out[((q // 2) * 8 + y) * 16 + (q % 2) * 8 + x] = pal[c]
    return out


VANILLA = Path(REPO).parent / "pokeemerald"       # the pristine reference (read only)


def fixture():
    """General and Rustboro from the game, Petalburg as vanilla shipped it (the game's own copy
    gains the pieces once they're imported)."""
    out = Path(REPO) / "dev/out"
    tmp = tempfile.TemporaryDirectory(prefix="bridge-pieces-", dir=out)
    root = Path(tmp.name)
    for rel in ("src/data/tilesets/graphics.h", "src/data/tilesets/metatiles.h",
                "src/data/tilesets/headers.h", "src/graphics.c"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(REPO) / rel, root / rel)
    for folder in ("data/tilesets/primary/general", "data/tilesets/secondary/rustboro"):
        shutil.copytree(Path(REPO) / folder, root / folder)
    shutil.copytree(VANILLA / "data/tilesets/secondary/petalburg", root / "data/tilesets/secondary/petalburg")
    return tmp, root


class FakeLayout:
    primary, secondary = "gTileset_General", TARGET


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_import():
    print("1. import into a copy of Petalburg")
    tmp, root = fixture()
    try:
        fp = Project(str(root))
        ids, why = bridges.piece_ids(fp, FakeLayout)
        check(ids is None and "tile_import.py bridge" in why, "before the import, a bridge on Petalburg is refused with the fix")
        pl = tileimport.plan(fp, bridges.SOURCE, list(bridges.SOURCE_PIECES), TARGET)
        check(not pl.problems, f"plan has no problems {pl.problems or ''}")
        check(len(pl.mapping) == 4, f"4 pieces mapped: {', '.join(f'{a:03X}->{b:03X}' for a, b in pl.mapping.items())}")
        check(len(pl.new_tiles) == 3 and sorted(pl.palettes) == [11] and len(pl.new_metatiles) == 4,
              f"appends 3 tiles, palette 11, 4 metatiles (got {len(pl.new_tiles)}, "
              f"{sorted(pl.palettes)}, {len(pl.new_metatiles)})")
        old = fp.tileset(TARGET)
        old_mt, old_n = list(old.metatiles), (old.tiles_image.width // 8) * (old.tiles_image.height // 8)
        old_tiles = [old.tile(i) for i in range(old_n)]
        old_pals = [list(old.palettes[i]) for i in range(13)]
        tileimport.apply(fp, pl)
        fp = Project(str(root))
        new = fp.tileset(TARGET)
        check(new.metatiles[:len(old_mt)] == old_mt, "existing metatiles unchanged")
        check([new.tile(i) for i in range(old_n)] == old_tiles, "existing tiles unchanged pixel for pixel")
        check(all(list(new.palettes[i]) == old_pals[i] for i in range(13) if i not in pl.palettes),
              "other palettes unchanged")
        src = fp.tileset_pair("gTileset_General", bridges.SOURCE)
        dst = fp.tileset_pair("gTileset_General", TARGET)
        same = all(metatile_rgb(src, a) == metatile_rgb(dst, b) for a, b in pl.mapping.items())
        check(same, "every copied metatile draws exactly as Rustboro's")
        check(all(src.attribute(a) == dst.attribute(b) for a, b in pl.mapping.items()), "attributes copied")
        again = tileimport.plan(fp, bridges.SOURCE, list(bridges.SOURCE_PIECES), TARGET)
        check(not again.changes and again.mapping == pl.mapping, "a second run appends nothing")
        check(bridges.piece_ids(fp, FakeLayout)[0] == pl.mapping, "afterwards the bridge finds its pieces")
    finally:
        tmp.cleanup()
    tmp, root = fixture()
    try:
        fp = Project(str(root))
        t = fp.tileset(TARGET)
        for k in range(6, 13):                       # every secondary slot taken, none matching
            t.palettes[k] = [(8, 8, 8 + k)] * 16
        pl = tileimport.plan(fp, bridges.SOURCE, list(bridges.SOURCE_PIECES), TARGET)
        check(any("palette slot" in pr for pr in pl.problems), "no free palette slot is refused")
        fp = Project(str(root))
        t = fp.tileset(TARGET)
        n = (t.tiles_image.width // 8) * (t.tiles_image.height // 8)
        e = list(t.metatiles[0])
        e[4] = NUM_TILES_IN_PRIMARY + n + 1           # a metatile drawing an animation frame there
        t.metatiles[0] = tuple(e)
        pl = tileimport.plan(fp, bridges.SOURCE, list(bridges.SOURCE_PIECES), TARGET)
        check(any("animation" in pr for pr in pl.problems), "appending onto an animation frame's tile is refused")
        fp = Project(str(root))
        before = snapshot(root)
        pl = tileimport.plan(fp, bridges.SOURCE, list(bridges.SOURCE_PIECES), TARGET)
        real_write = tileimport.atomic_write
        calls = []

        def flaky(path, data):
            calls.append(path)
            if str(path).endswith("metatile_attributes.bin"):
                raise OSError("simulated failure")
            real_write(path, data)
        with patch.object(tileimport, "atomic_write", flaky):
            try:
                tileimport.apply(fp, pl)
                check(False, "the simulated failure was raised")
            except OSError:
                pass
        check(len(calls) >= 2 and snapshot(root) == before, "a late failure restores every byte")
    finally:
        tmp.cleanup()


SHAPE = [
    "TTTTTTTTTTTT",
    "............",
    "....==......",
    "............",
    "~~~~~HH~~~~~",
    "~~~~~HH~~~~~",
    "~~~~~HH~~~~~",
    "............",
    "....==......",
    "TTTTTTTTTTTT",
]


def kit_layout(p, like, w, h):
    L = copy.copy(p.load_map(like).layout)
    L.width, L.height = w, h
    L.blocks = [pack(1, 0, 3)] * (w * h)
    return L


def build(p, kit, rows, like="Fredericton_0"):
    corpus, vocab, rules, forbidden = kit
    L = kit_layout(p, like, len(rows[0]), len(rows))
    return L, compile_sketch(p, corpus, rules, Sketch("BridgeTest", rows), L, vocab, forbidden, fresh=True)


def refused(p, kit, rows, like="Fredericton_0"):
    try:
        build(p, kit, rows, like)
        return None
    except SketchError as ex:
        return ex.problems


def test_shapes(p, kit):
    print("2. shapes (Rustboro layout)")
    L, (blocks, report) = build(p, kit, SHAPE)
    w = len(SHAPE[0])
    mid = lambda x, y: blocks[y * w + x] & 0x3FF
    attrs = lambda x, y: ((blocks[y * w + x] >> 10) & 3, blocks[y * w + x] >> 12)
    check([mid(5, 4), mid(6, 4)] == list(bridges.NORTH), f"north end is 350 351 (got {mid(5, 4):03X} {mid(6, 4):03X})")
    check(all([mid(5, y), mid(6, y)] == list(bridges.DECK) for y in (5, 6)), "deck rows are 34E 34F")
    check(all(attrs(x, y) == bridges.ATTRS for x in (5, 6) for y in (4, 5, 6)), "deck walkable at elevation 3")
    check(mid(5, 7) == bridges.PLAIN_GRASS and mid(6, 7) == bridges.PLAIN_GRASS, "no bank under the deck's south end")
    check(mid(4, 7) == 0x002 and mid(7, 7) == 0x002, "the bank runs on beside it (002)")
    check(mid(4, 4) == shores.BANK["N"] and mid(7, 5) == shores.OPEN_WATER, "the river beside the deck is the plain river's")
    check(report.get("bridge_tiles") == 6, f"report counts 6 deck tiles ({report.get('bridge_tiles')})")
    cases = {
        "one column": [r.replace("HH", "H~") for r in SHAPE],
        "three columns": [r.replace("~HH", "HHH") for r in SHAPE],
        "ragged rows": SHAPE[:5] + ["~~~~~~HH~~~~"] + SHAPE[6:],
        "a strip running off the map (no grass at its end)": ["...~~HH~~...", "...~~HH~~...", "...~~HH~~..."],
        "a deck against the bank (land beside it)": SHAPE[:4] + [".....HH~~~~~"] * 3 + SHAPE[7:],
        "a boulder at the south end": SHAPE[:7] + [".....b......"] + SHAPE[8:],
        "sand at the north end": SHAPE[:3] + [".....::....."] + SHAPE[4:],
    }
    for what, rows in cases.items():
        pr = refused(p, kit, rows)
        check(pr, f"refused: {what}" + (f" ({pr[0][2][:70]})" if pr else ""))
    return L, blocks


def test_extract(p, kit, L, blocks):
    print("3. extract")
    L.blocks = list(blocks)
    w, h = L.width, L.height
    want = {(x, y) for y, r in enumerate(SHAPE) for x, ch in enumerate(r) if ch == "H"}
    # extract labels the deck cells as unknown first; the water and land around it as drawn
    full = [list(r.replace("H", "~")) for r in SHAPE]
    extract_bridges(p, L, full)
    check({(x, y) for y in range(h) for x in range(w) if full[y][x] == "H"} == want, "the deck extracts as 'H'")
    L2, (blocks2, _) = build(p, kit, ["".join(r) for r in full])
    check(blocks2 == blocks, "and recompiles block for block")
    # half a deck (one column painted over): neither column extracts as H
    L.blocks[4 * w + 6] = pack(shores.OPEN_WATER, 0, 1)
    half = [list(r.replace("H", "~")) for r in SHAPE]
    extract_bridges(p, L, half)
    check(not any(ch == "H" for r in half for ch in r) and half[5][5] == "#",
          "a broken strip stays '#'")


def main():
    warnings.simplefilter("ignore", ResourceWarning)
    import corridor
    p = Project()
    test_import()
    kit = corridor.build_kit(p)
    L, blocks = test_shapes(p, kit)
    test_extract(p, kit, L, blocks)
    n, bad = len(results), results.count(False)
    print(f"RESULT: {n - bad}/{n} bridge checks pass")
    return 1 if bad or not n else 0


if __name__ == "__main__":
    raise SystemExit(main())
