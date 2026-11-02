"""Static map checker (engine-faithful). See dev/mapkit/checks.py for the rules.

  python dev/check_maps.py              # Maritimes maps (not in upstream expansion)
  python dev/check_maps.py HomeTown_0   # specific maps
  python dev/check_maps.py --all        # every map (vanilla maps double as a test corpus)
  python dev/check_maps.py --all --summary   # only counts per issue code
Exit code 1 if any ERROR.
"""
import os, subprocess, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapkit.project import Project
from mapkit.checks import check_map, wild_encounter_maps
from mapkit.corpus import Corpus

UPSTREAM = "expansion/1.17.2"


def maritimes_maps(p):
    r = subprocess.run(["git", "-C", p.root, "ls-tree", "-d", "--name-only", f"{UPSTREAM}:data/maps"],
                       capture_output=True, text=True)
    upstream = set(r.stdout.split())
    return [n for n in p.map_names if n not in upstream]


def baseline(p):
    """Regression test for the checker: vanilla maps must produce only the known, explained errors."""
    from mapkit.baseline import KNOWN
    upstream = set(p.map_names) - set(maritimes_maps(p))
    unexpected, seen = [], set()
    corpus = Corpus(p)
    for n in sorted(upstream):
        if n.endswith("_Frlg"):
            continue
        for s, c, msg in check_map(p, n, None, corpus):
            if s == "ERROR":
                if (n, c) in KNOWN:
                    seen.add((n, c))
                else:
                    unexpected.append(f"{n}: {c}: {msg}")
    stale = set(KNOWN) - seen
    print(f"vanilla corpus: {len(upstream)} maps, {len(unexpected)} unexpected errors, "
          f"{len(seen)} known exceptions matched, {len(stale)} stale exceptions")
    for u in unexpected:
        print("  UNEXPECTED", u)
    for k in sorted(stale):
        print("  STALE", k)
    return 1 if unexpected or stale else 0


def main(argv):
    p = Project()
    flags = {a for a in argv if a.startswith("--")}
    if "--baseline" in flags:
        return baseline(p)
    names = p.map_names if "--all" in flags else ([a for a in argv if not a.startswith("--")] or maritimes_maps(p))
    if "--all" in flags:   # FRLG maps are not built in Emerald mode
        names = [n for n in names if not n.endswith("_Frlg")]
    wild = wild_encounter_maps(p)
    corpus = Corpus(p)
    totals, codes, failed = Counter(), Counter(), []
    for n in names:
        try:
            issues = check_map(p, n, wild, corpus)
        except Exception as ex:          # a crash on a map is itself a finding
            issues = [("ERROR", "crash", f"{type(ex).__name__}: {ex}")]
        sev = Counter(s for s, _, _ in issues)
        totals.update(sev)
        codes.update(f"{s}:{c}" for s, c, _ in issues)
        if sev["ERROR"]:
            failed.append(n)
        if "--summary" not in flags:
            status = "ERR" if sev["ERROR"] else "WRN" if sev["WARN"] else "OK "
            if issues or "--all" not in flags:
                print(f"[{status}] {n}")
                for s, c, msg in issues:
                    print(f"      {s} {c}: {msg}")
    print(f"\n{len(names)} maps: {totals['ERROR']} errors, {totals['WARN']} warnings, {totals['INFO']} info")
    if "--summary" in flags:
        for k, v in codes.most_common():
            print(f"  {v:5} {k}")
        print("maps with errors:", ", ".join(failed[:40]))
    return 1 if totals["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
