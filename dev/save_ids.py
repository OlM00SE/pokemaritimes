"""Allocate the region's saved story state: vars and flags in the Maritimes blocks.

  python dev/save_ids.py var  VAR_HOMETOWN_STATE "HomeTown's story: 0 arrived, 1 has a starter"
  python dev/save_ids.py flag FLAG_HIDE_WOODSTOCK_RIVAL "the rival by the station, until ..."
  python dev/save_ids.py ... --apply      write it (without: a dry run that shows the id)
  python dev/save_ids.py list             every allocated var and flag, and the room left

Ids are appended in order below the block's marker as (MARITIMES_VARS_START + n) in
include/constants/vars.h or (MARITIMES_FLAGS_START + n) in include/constants/flags.h, with the
note as a comment. Ids never move and are never reused, so saves stay readable when more are
added (the save layout doesn't change: the blocks are sized already). Re-running with a name that
exists is a no-op. dev/events.py allocates its item and gift flags in the same flag block,
through this module.

Which to use (design/save_format.md):
  - a var for anything with stages (a town's progress, a quest): one var per storyline, with
    values 0, 1, 2, ... (vanilla's VAR_LITTLEROOT_TOWN_STATE);
  - a flag for a yes/no that stays (an NPC hidden for good, a one-time event);
  - VAR_TEMP_* / FLAG_TEMP_* for scratch that may be forgotten on the next map load.
"""
import argparse, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BlockFull(ValueError):
    pass


class Block:
    def __init__(self, kind, header, start, count, prefix, width, cost):
        self.kind, self.header, self.start, self.count = kind, header, start, count
        self.prefix, self.width, self.cost = prefix, width, cost
        self.end_marker = f"// ---- end of Maritimes {kind}s ----"

    def text(self, repo=REPO):
        return open(os.path.join(repo, self.header), encoding="utf-8").read()

    def size(self, repo=REPO, text=None):
        text = self.text(repo) if text is None else text
        return int(re.search(rf"^#define {self.count}\s+(\d+)", text, re.M).group(1))

    def allocated(self, repo=REPO, text=None):
        """{name: (offset, comment)} in the block, in file order."""
        text = self.text(repo) if text is None else text
        return {n: (int(o, 0), (c or "").strip()) for n, o, c in re.findall(
            rf"^#define ({self.prefix}\w+)\s+\({self.start} \+ (0x[0-9A-Fa-f]+|\d+)\)[ \t]*(//[^\n]*)?", text, re.M)}

    def plan(self, names, repo=REPO):
        """({name: offset} for the names not defined anywhere in the header yet, after the last
        id; ids left after them). Raises BlockFull if they don't fit."""
        text = self.text(repo)
        exists = set(re.findall(rf"^#define ({self.prefix}\w+)", text, re.M))
        have, size = self.allocated(repo, text), self.size(repo, text)
        nxt = max((o for o, _ in have.values()), default=-1) + 1
        new = [n for n in dict.fromkeys(names) if n not in exists]
        if nxt + len(new) > size:
            raise BlockFull(f"no room for {len(new)} new {self.kind}s: {nxt} of {size} in the Maritimes {self.kind} "
                            f"block used; raise {self.count} in {self.header} ({self.cost}; it changes the save "
                            "layout: dev/save_layout.py --update)")
        return {n: nxt + i for i, n in enumerate(new)}, size - nxt - len(new)

    def write(self, plan, tag, notes=None, repo=REPO):
        """Append the planned ids below the marker, each with '// Maritimes: <tag>[: note]'."""
        if not plan:
            return
        path = os.path.join(repo, self.header)
        text = self.text(repo)
        assert text.count(self.end_marker) == 1, f"{self.header}: the Maritimes {self.kind} block marker is missing"
        notes = notes or {}
        lines = []
        for n, o in plan.items():
            note = " ".join(str(notes.get(n, "")).split())       # one line
            lines.append(f"#define {n:<{self.width}} ({self.start} + 0x{o:X})  // Maritimes: {tag}"
                         + (f": {note}" if note else "") + "\n")
        text = text.replace(self.end_marker, "".join(lines) + self.end_marker)
        open(path, "w", encoding="utf-8", newline="\n").write(text)


VARS = Block("var", "include/constants/vars.h", "MARITIMES_VARS_START", "MARITIMES_VARS_COUNT", "VAR_", 48,
             "a var costs 2 bytes of SaveBlock3")
FLAGS = Block("flag", "include/constants/flags.h", "MARITIMES_FLAGS_START", "MARITIMES_FLAGS_COUNT", "FLAG_", 43,
              "8 flags cost 1 byte of SaveBlock1")
BLOCKS = {"var": VARS, "flag": FLAGS}
TAG = "dev/save_ids.py"            # the comment on story ids
EVENTS_TAG = "dev/events.py"       # the comment on the item and gift flags dev/events.py allocates


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for kind in BLOCKS:
        s = sub.add_parser(kind, help=f"allocate a story {kind}")
        s.add_argument("name", help=f"{BLOCKS[kind].prefix}... (upper case)")
        s.add_argument("note", help="what it records (and, for a var, what its values mean)")
        s.add_argument("--apply", action="store_true", help="write it (default: dry run)")
    sub.add_parser("list", help="every allocated var and flag, and the room left")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for b in BLOCKS.values():
            have, size = b.allocated(), b.size()
            print(f"Maritimes {b.kind}s: {len(have)} of {size} used, {size - len(have)} left ({b.header})")
            for n, (o, c) in have.items():
                print(f"  {b.start} + 0x{o:X}  {n}  {c}")
        return 0

    b = BLOCKS[a.cmd]
    if not re.fullmatch(rf"{b.prefix}[A-Z0-9_]+", a.name):
        print(f"refused: a {a.cmd} name is {b.prefix} followed by upper case, digits and _ (got {a.name})")
        return 1
    if not a.note.strip():
        print("refused: say what it records")
        return 1
    have = b.allocated()
    if a.name in have:
        print(f"{a.name} exists: {b.start} + 0x{have[a.name][0]:X} (nothing to do)")
        return 0
    try:
        plan, left = b.plan([a.name])
    except BlockFull as ex:
        print(f"refused: {ex}")
        return 1
    if not plan:
        print(f"refused: {a.name} is already defined in {b.header} outside the Maritimes block (a vanilla id)")
        return 1
    print(f"{a.name} = {b.start} + 0x{plan[a.name]:X} ({left} {a.cmd}s left after it)")
    if not a.apply:
        print("dry run: add --apply to write it")
        return 0
    b.write(plan, TAG, {a.name: a.note})
    print(f"written to {b.header}; dev/fastbuild.py, then use it in scripts.pory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
