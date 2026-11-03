"""The script macros treat the story var block's ids as vars (no emulator; needs the WSL mirror).

  python dev/tests/var_macros.py

asm/macros/event.inc decides by value whether an argument is a var: `compare` becomes
compare_var_to_var or compare_var_to_value, and `setvar`/`copyvar` warn when an argument looks
like the wrong kind. Poryscript's `if (var(VAR_X) == ...)` compiles to `compare`. Milestone 11
added the Maritimes var block (MARITIMES_VARS_START..END) to those tests; without it a script
comparing a var to a story var would compare it to the story var's *id*.

This assembles a throwaway probe with the build's own preprocessor, assembler and headers (the
same includes as data/event_scripts.s), in the WSL mirror only (dev/fastbuild.py probe), and
checks that `compare` emits the same bytes as the explicit macro it should pick: _var_to_var for
both ends of the block and a vanilla var, _var_to_value for the id just past the block and a
small number. It also checks the build log: copyvar from a story var doesn't warn, setvar with a
story var's id as the value does. Exit code 1 on any failure.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fastbuild

PROBE = "data/zz_dev_var_macro_probe.s"
# (argument, the macro `compare` should become)
CASES = [("MARITIMES_VARS_START", "compare_var_to_var"), ("MARITIMES_VARS_END", "compare_var_to_var"),
         ("VARS_END", "compare_var_to_var"), ("VAR_RESULT", "compare_var_to_var"),
         ("(MARITIMES_VARS_END + 1)", "compare_var_to_value"), ("5", "compare_var_to_value")]
COMPARE_SIZE = 5                     # opcode, 2-byte var, 2-byte var or value
BEGIN, END = "var_macros probe: warnings begin", "var_macros probe: warnings end"


def probe_source():
    head = open(os.path.join(fastbuild.REPO, "data", "event_scripts.s"), encoding="utf-8").read()
    # everything up to the macros and constants: the includes data/event_scripts.s itself builds with
    cut = head.index('.include "constants/constants.inc"') + len('.include "constants/constants.inc"')
    lines = [head[:cut], "", "\t.section .rodata", "gDevVarMacroProbe::"]
    for arg, explicit in CASES:
        lines += [f"\tcompare VAR_TEMP_0, {arg}", f"\t{explicit} VAR_TEMP_0, {arg}"]
    # the data rule pipes the source through stdin, so the assembler names no file in its
    # warnings: markers bracket this probe's own lines in the make log
    lines += [f'\t.warning "{BEGIN}"',
              "\tcopyvar VAR_TEMP_1, MARITIMES_VARS_START   @ must not warn",
              "\tsetvar VAR_TEMP_1, MARITIMES_VARS_END     @ must warn (did you mean copyvar?)",
              f'\t.warning "{END}"', ""]
    return "\n".join(lines)


def between_markers(log):
    """The log lines between this probe's BEGIN and END warnings, or None if they're missing."""
    lines = log.splitlines()
    try:
        a = next(i for i, l in enumerate(lines) if BEGIN in l)
        b = next(i for i, l in enumerate(lines) if END in l and i > a)
    except StopIteration:
        return None
    return lines[a + 1:b]


def main():
    raw, out = fastbuild.probe(PROBE, probe_source())
    log = fastbuild.wsl("cat ~/maritimes-build/.fastbuild.log", check=False).stdout
    fails = 0

    def check(ok, what):
        nonlocal fails
        print(f"  {'PASS' if ok else 'FAIL'}: {what}")
        fails += not ok

    need = 2 * COMPARE_SIZE * len(CASES)
    if len(raw) < need:
        print(f"FAIL: the probe's .rodata has {len(raw)} bytes, expected at least {need}:\n{out}")
        return 1
    for i, (arg, explicit) in enumerate(CASES):
        a = raw[2 * i * COMPARE_SIZE:(2 * i + 1) * COMPARE_SIZE]
        b = raw[(2 * i + 1) * COMPARE_SIZE:(2 * i + 2) * COMPARE_SIZE]
        check(a == b, f"compare VAR_TEMP_0, {arg} is {explicit} ({a.hex()} vs {b.hex()})")
    probe_log = between_markers(log)
    if probe_log is None:
        print("FAIL: the probe's marker warnings aren't in the make log (~/maritimes-build/.fastbuild.log)")
        return 1
    check(not any("copyvar with a value that is not" in l for l in probe_log),
          "copyvar from a story var gives no warning")
    check(any("setvar with a value that might be a VAR_" in l for l in probe_log),
          "setvar with a story var's id as the value warns (did you mean copyvar?)")
    print("PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
