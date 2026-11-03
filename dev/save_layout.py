"""Measure the save layout exactly, and keep include/save_layout.h in step with it.

  python dev/save_layout.py              report the layout and the room left; exit 1 if it differs
                                         from what include/save_layout.h records
  python dev/save_layout.py --update     rewrite the recorded numbers; if any changed, bump
                                         SAVE_LAYOUT_VERSION (old saves are then refused, with a
                                         message, instead of loading as garbage)

The ELF has no debug info, so the sizes come from the game's own compiler: a throwaway C file
(sizeof/offsetof of the save blocks, as a const table) is compiled in the WSL build mirror with
the build's flags and read back with objdump. It is deleted afterwards and never reaches E:.
src/save.c asserts every recorded number at build time, so a build that changes the layout
stops until this has been run.
"""
import argparse, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fastbuild

REPO = fastbuild.REPO
HEADER = os.path.join(REPO, "include", "save_layout.h")
PROBE = "zz_dev_save_layout_probe"            # src/<PROBE>.c in the mirror only
# (header name, C expression) in table order
FIELDS = [
    ("SAVE_LAYOUT_SAVEBLOCK1_SIZE", "sizeof(struct SaveBlock1)"),
    ("SAVE_LAYOUT_SAVEBLOCK2_SIZE", "sizeof(struct SaveBlock2)"),
    ("SAVE_LAYOUT_SAVEBLOCK3_SIZE", "sizeof(struct SaveBlock3)"),
    ("SAVE_LAYOUT_STORAGE_SIZE", "sizeof(struct PokemonStorage)"),
    ("SAVE_LAYOUT_FLAGS_OFFSET", "offsetof(struct SaveBlock1, flags)"),
    ("SAVE_LAYOUT_VARS_OFFSET", "offsetof(struct SaveBlock1, vars)"),
    ("SAVE_LAYOUT_FLAGS_BYTES", "NUM_FLAG_BYTES"),
    ("SAVE_LAYOUT_VARS_COUNT", "VARS_COUNT"),
    # where each saved flag range starts: moving one inside an unchanged flags[] re-points old flags
    ("SAVE_LAYOUT_TRAINER_FLAGS_START", "TRAINER_FLAGS_START"),
    ("SAVE_LAYOUT_SYSTEM_FLAGS", "SYSTEM_FLAGS"),
    ("SAVE_LAYOUT_DAILY_FLAGS_START", "DAILY_FLAGS_START"),
    ("SAVE_LAYOUT_MARITIMES_FLAGS_START", "MARITIMES_FLAGS_START"),
    # the story var block in SaveBlock3 (milestone 11)
    ("SAVE_LAYOUT_MARITIMES_VARS_OFFSET", "offsetof(struct SaveBlock3, maritimesVars)"),
    ("SAVE_LAYOUT_MARITIMES_VARS_COUNT", "MARITIMES_VARS_COUNT"),
]
# the SaveBlock3 chunks that every save writes (sectors 0-4); src/save.c asserts the var block fits
SB3_ALWAYS_WRITTEN = "SAVE_BLOCK_3_CHUNK_SIZE * (SECTOR_ID_SAVEBLOCK1_END + 1)"
# capacities, for the report (not recorded: they're the flash format, not the layout)
CAPACITY = [
    ("SaveBlock1", "SECTOR_DATA_SIZE * (SECTOR_ID_SAVEBLOCK1_END - SECTOR_ID_SAVEBLOCK1_START + 1)", 0),
    ("SaveBlock2", "SECTOR_DATA_SIZE", 1),
    ("SaveBlock3", "SAVE_BLOCK_3_CHUNK_SIZE * NUM_SECTORS_PER_SLOT", 2),
    ("PC storage", "SECTOR_DATA_SIZE * (SECTOR_ID_PKMN_STORAGE_END - SECTOR_ID_PKMN_STORAGE_START + 1)", 3),
]
BEGIN, END = "// ---- measured by dev/save_layout.py; don't edit by hand ----", "// ---- end of measured numbers ----"


def probe_source():
    exprs = [e for _, e in FIELDS] + [e for _, e, _ in CAPACITY] + [SB3_ALWAYS_WRITTEN]
    body = ",\n    ".join(f"(u32)({e})" for e in exprs)
    return ('// dev/save_layout.py probe: deleted after use, never part of the game\n'
            '#include "global.h"\n#include "save.h"\n#include "pokemon_storage_system.h"\n'
            f'const u32 gDevSaveLayoutProbe[] = {{\n    {body}\n}};\n')


def measure():
    """[values] in FIELDS + CAPACITY order, then SB3_ALWAYS_WRITTEN; compiled in the mirror
    (synced from E: first)."""
    unc = fastbuild.mirror_unc()
    if not os.path.isdir(unc) or not os.path.exists(fastbuild.MANIFEST):
        # fastbuild would reseed the mirror (rm -rf) and take the probe with it
        sys.exit("no WSL build mirror (or its manifest): run dev/fastbuild.py once first")
    src = os.path.join(unc, "src", PROBE + ".c")
    obj = f"build/emerald/src/{PROBE}.o"
    with open(src, "w", newline="\n") as f:
        f.write(probe_source())
    try:
        # fastbuild with a make target: syncs E: -> mirror, then builds just that object
        if fastbuild.main([obj]) != 0:
            sys.exit("the probe didn't compile (see the log above)")
        path = 'export PATH="$HOME/.local/arm-gnu-toolchain/bin:$PATH"; '
        out = fastbuild.wsl(f"{path}cd {fastbuild.MIRROR_LINUX} && arm-none-eabi-objdump -s -j .rodata {obj}").stdout
    finally:
        for p in (src, os.path.join(unc, obj.replace("/", "\\")), os.path.join(unc, obj[:-2].replace("/", "\\") + ".d")):
            if os.path.exists(p):
                os.remove(p)
    raw = b""
    for line in out.splitlines():
        m = re.match(r"^\s*[0-9a-f]+ ((?:[0-9a-f]{2,8} ?){1,4})", line)
        if m:
            raw += bytes.fromhex(m.group(1).replace(" ", ""))
    n = len(FIELDS) + len(CAPACITY) + 1
    if len(raw) < 4 * n:
        sys.exit("couldn't read the probe's table from objdump (an LTO or -fdata-sections build keeps no "
                 f"plain .rodata; measure with a normal dev build):\n{out}")
    return list(struct.unpack(f"<{n}I", raw[:4 * n]))


def recorded(text=None):
    """{SAVE_LAYOUT_*: number} from include/save_layout.h (the one parser of it; tests import it),
    with SAVE_LAYOUT_STAMP worked out from its formula."""
    text = open(HEADER, encoding="utf-8").read() if text is None else text
    rec = {k: int(v, 0) for k, v in re.findall(r"^#define (SAVE_LAYOUT_\w+)\s+(0x[0-9A-Fa-f]+|\d+)\s*$", text, re.M)}
    base = re.search(r"^#define SAVE_LAYOUT_STAMP\s+\((0x[0-9A-Fa-f]+|\d+) \+ SAVE_LAYOUT_VERSION\)", text, re.M)
    if base:
        rec["SAVE_LAYOUT_STAMP"] = int(base.group(1), 0) + rec["SAVE_LAYOUT_VERSION"]
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="rewrite the numbers; bump the version if they changed")
    a = ap.parse_args()
    vals = measure()
    got = {k: v for (k, _), v in zip(FIELDS, vals)}
    text = open(HEADER, encoding="utf-8").read()
    rec = recorded(text)
    version = rec["SAVE_LAYOUT_VERSION"]
    print(f"save layout (version {version} recorded in include/save_layout.h):")
    for (name, _, i), cap in zip(CAPACITY, vals[len(FIELDS):]):
        size = vals[i]
        print(f"  {name:10} {size:6} of {cap:6} bytes: {cap - size:5} left")
    print(f"  flags      {got['SAVE_LAYOUT_FLAGS_BYTES'] * 8} saved flags ({got['SAVE_LAYOUT_FLAGS_BYTES']} bytes at "
          f"SaveBlock1+{got['SAVE_LAYOUT_FLAGS_OFFSET']:#x})")
    print(f"  vars       {got['SAVE_LAYOUT_VARS_COUNT']} saved vars (at SaveBlock1+{got['SAVE_LAYOUT_VARS_OFFSET']:#x})")
    vo, vn, window = got["SAVE_LAYOUT_MARITIMES_VARS_OFFSET"], got["SAVE_LAYOUT_MARITIMES_VARS_COUNT"], vals[-1]
    print(f"  story vars {vn} Maritimes vars (at SaveBlock3+{vo:#x}..{vo + 2 * vn - 1:#x}; every save writes "
          f"SaveBlock3+0..{window - 1:#x})")
    diff = {k: (rec.get(k), v) for k, v in got.items() if rec.get(k) != v}
    if not diff:
        print("matches include/save_layout.h: saves of this version load")
        return 0
    for k, (old, new) in diff.items():
        print(f"  changed: {k} {old} -> {new}")
    if not a.update:
        print("DIFFERS from include/save_layout.h: the build will stop (src/save.c). If the change is "
              "meant, run dev/save_layout.py --update (old saves will be refused).")
        return 1
    # only a number that was recorded and moved is a layout change; a newly recorded one (this
    # tool learned to measure it) or the placeholder 0s of the first measurement aren't
    moved = [k for k, (old, new) in diff.items() if old not in (None, 0)]
    first = not moved
    block = BEGIN + "\n" + "".join(f"#define {k:<33} {v}\n" for k, v in got.items()) + END
    text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    if not first:
        version += 1
        text = re.sub(r"(#define SAVE_LAYOUT_VERSION )\d+", lambda m: m.group(1) + str(version), text)
    with open(HEADER, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"updated include/save_layout.h: version {version}"
          + (" (numbers recorded; no recorded number moved, so the version stays)" if first
             else " (bumped: saves from the old layout will be refused with a message)")
          + "\nnext: dev/fastbuild.py, then dev/tests/ingame_save.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
