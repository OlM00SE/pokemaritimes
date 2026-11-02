"""Propose/apply collision+elevation fixes using how vanilla maps use each metatile.

  python dev/fix_attrs.py Woodstock_2                  # dry run: what would change, and why
  python dev/fix_attrs.py Woodstock_2 --apply          # write map.bin
  python dev/fix_attrs.py --maritimes --surfable --apply

--surfable limits fixes to surfable-water tiles (the safe, targeted fix for walkable water).
Only confident vanilla defaults are used (>=5 uses, >=80% agreement).
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project, TILE_FLAG_SURFABLE
from mapkit.corpus import Corpus
from check_maps import maritimes_maps


def propose(p, corpus, name, surfable_only):
    m = p.load_map(name)
    L, tp = m.layout, m.layout.tiles
    changes = []
    for y in range(L.height):
        for x in range(L.width):
            mid = L.mid(x, y)
            if surfable_only and not p.tile_flags.get(tp.behavior(mid), 0) & TILE_FLAG_SURFABLE:
                continue
            want = corpus.default_attrs(L.entry, mid)
            have = (L.coll(x, y), L.elev(x, y))
            if want and want != have:
                changes.append((x, y, mid, have, want))
    return m, changes


def main(argv):
    p = Project()
    corpus = Corpus(p)
    names = maritimes_maps(p) if "--maritimes" in argv else [a for a in argv if not a.startswith("--")]
    for n in names:
        m, ch = propose(p, corpus, n, "--surfable" in argv)
        summary = Counter((f"{mid:03X}", have, want) for _, _, mid, have, want in ch)
        print(f"{n}: {len(ch)} block(s) to change")
        for (mid, have, want), k in summary.most_common(8):
            print(f"    {k:4} x metatile {mid}: (coll,elev) {have} -> {want}")
        if ch and "--apply" in argv:
            for x, y, mid, have, want in ch:
                m.layout.set(x, y, coll=want[0], elev=want[1])
            m.layout.save()
            print("    applied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
