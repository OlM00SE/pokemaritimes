"""Run the project's regression set serially, with explicit coverage and saved logs.

  python dev/regression.py                  # full gate before a milestone merge
  python dev/regression.py --list           # IDs and coverage roles
  python dev/regression.py --only conformance doors   # named subset (reported as such)

The ROM build and every emulator test run in sequence. A report and complete per-step logs go
under dev/out/regression/. OBSERVED means a metric was reported but has no quality threshold;
it is deliberately not counted as a passed gate. Each step's evidence (its counts) is printed
and kept in the report, so a handoff quotes the run instead of retyping numbers.

One run at a time (an OS lock, released if the runner dies). A step that times out or is
interrupted is killed with its whole process tree, so no orphaned mGBA keeps running beside
the next test.
"""
import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "dev" / "out" / "regression"
SCRATCH = REPO / "dev" / "out"
SCRATCH_PREFIXES = ("emutest-", "mgba-bridge-")
STALE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class Step:
    id: str
    command: tuple[str, ...]
    kind: str = "gate"             # gate or observed (measurement without a threshold)
    check: str = ""                 # extra output contract; exit code alone is insufficient
    timeout: int = 240


def manifest():
    steps = [
        # a full rebuild (a header change, --reseed) takes minutes; a typical one ~15 s
        Step("build", ("dev/fastbuild.py",), timeout=1800),
        Step("authoring", ("dev/tests/authoring_safety.py",)),
        Step("harness_guards", ("dev/tests/harness_guards.py",), timeout=240),
        Step("maps_baseline", ("dev/check_maps.py", "--baseline")),
        Step("maps", ("dev/check_maps.py",)),
        Step("ids", ("dev/tests/id_budget.py",)),
        Step("save_layout", ("dev/save_layout.py",)),
        Step("var_macros", ("dev/tests/var_macros.py",)),
        Step("ledge_pieces", ("dev/tests/ledge_pieces.py",)),
        Step("shore_pieces", ("dev/tests/shore_pieces.py",)),
        Step("flora_pieces", ("dev/tests/flora_pieces.py",)),
        Step("stamp_pieces", ("dev/tests/stamp_pieces.py",)),
        Step("corridor_plan", ("dev/tests/corridor_plan.py",)),
        Step("corridor", ("dev/corridor.py", "check")),
        Step("reconstruction", ("dev/tests/reconstruction.py",), kind="observed", timeout=360),
        Step("roundtrip", ("dev/tests/roundtrip.py",)),
        Step("route_metrics", ("dev/route_stats.py", "Route201_1", "Woodstock_2"), kind="observed"),
    ]
    for name in ("HomeTown_0", "HomeTown_House2_1F", "Route201_1", "Woodstock_2",
                 "Woodstock_House1", "Woodstock_House2", "Woodstock_Lab"):
        steps.append(Step("events_spec_" + name.lower(),
                          ("dev/events.py", "build", f"design/maps/{name}.events.toml"),
                          check="events_dryrun"))
    steps += [
        Step("emulator_isolation", ("dev/tests/emulator_isolation.py",), timeout=180),
        Step("conformance", ("dev/tests/conformance.py",), check="conformance", timeout=180),
        Step("playthrough", ("dev/tests/playthrough_slice1.py",), timeout=180),
        Step("doors", ("dev/tests/ingame_doors.py", "HomeTown_0", "Woodstock_2", "TownLab"),
             check="doors", timeout=180),
        Step("buildings", ("dev/tests/ingame_buildings.py",), check="buildings", timeout=180),
        Step("respawn", ("dev/tests/ingame_respawn.py",), timeout=180),
        Step("encounters", ("dev/tests/ingame_encounters.py", "Route201_1"),
             check="encounters", timeout=180),
        Step("encounters_no_party", ("dev/tests/ingame_encounters.py", "Route201_1", "--no-party"),
             timeout=180),
    ]
    base = ("LittlerootTown_MyHouse_1F_0", "HomeTown_0", "Route201_1", "Woodstock_2")
    for id, route in (
        ("autowalk_fredericton", base + ("Route202_1", "Fredericton_0")),
        ("autowalk_route203", base + ("Route202_1", "Fredericton_0", "Route203_1", "Route203_1_2")),
        ("autowalk_return", base + ("Route202_1", "Fredericton_0", "Route203_1",
                                      "Route101_2", "Route203_1", "Fredericton_0")),
        ("autowalk_home", base + ("Route201_1", "HomeTown_0")),
    ):
        steps.append(Step(id, ("dev/autowalk.py", *route), timeout=180))
    steps += [
        Step("ledges", ("dev/tests/ingame_ledges.py",), timeout=180),
        Step("events", ("dev/tests/ingame_events.py",), timeout=180),
        Step("save", ("dev/tests/ingame_save.py",), timeout=180),
        Step("shores", ("dev/tests/ingame_shores.py",), check="shores", timeout=180),
        Step("flora", ("dev/tests/ingame_flora.py",), check="flora", timeout=180),
        Step("mobile_publish_scratch", ("dev/tests/mobile_publish.py",), timeout=180),
    ]
    assert len({s.id for s in steps}) == len(steps), "duplicate regression step ID"
    return steps


def coverage_error(step, output):
    """Return a missing/invalid coverage reason, or None when the step's claim is supported."""
    if step.check == "events_dryrun":
        if not ("0 new or changed, 0 removed or changed" in output
                and "scripts and text unchanged" in output
                and "checker: 0 errors" in output):
            return "event spec differs from the applied map/script or checker has errors"
    elif step.check == "conformance":
        m = re.search(r"TOTAL: (\d+)/(\d+) executed comparisons; (\d+) skipped, (\d+) failed", output)
        if not m or int(m[2]) < 1 or int(m[1]) != int(m[2]) or int(m[3]) or int(m[4]):
            return "conformance did not execute and pass every selected comparison"
    elif step.check == "doors":
        m = re.search(r"RESULT: PASS; (\d+) completed door round trips", output)
        if not m or int(m[1]) < 1:
            return "no completed in-game door round trips reported"
    elif step.check == "buildings":
        m = re.search(r"RESULT: (\d+) passed, (\d+) failed", output)
        kinds = re.search(r"TownLab: (\d+) Centers, (\d+) Marts selected", output)
        if not m or int(m[1]) < 1 or int(m[2]) or not kinds or min(map(int, kinds.groups())) < 1:
            return "TownLab did not exercise both Center and Mart with passing checks"
    elif step.check == "encounters":
        if not re.search(r"^battle 1: wild ", output, re.M):
            return "no actual wild battle reported"
    elif step.check in ("shores", "flora"):
        m = re.search(r"TOTAL: (\d+)/(\d+) (?:shore|flora and forest-edge) cases", output)
        if not m or int(m[2]) < 1 or int(m[1]) != int(m[2]):
            return "no positive, fully passing in-game case count reported"
    return None


def _sum_fractions(pattern, output):
    pairs = [(int(a), int(b)) for a, b in re.findall(pattern, output, re.M)]
    return sum(a for a, _ in pairs), sum(b for _, b in pairs), len(pairs)


def evidence(step, output):
    """A one-line summary of what the step actually exercised, taken from its output."""
    if step.id == "events":
        ok, n, maps = _sum_fractions(r"^\S+: (\d+)/(\d+) checks pass", output)
        return f"{ok}/{n} checks on {maps} maps" if maps else ""
    if step.id == "ledges":
        ok, n, maps = _sum_fractions(r"^\S+: (\d+)/(\d+) executed ledge approaches agree", output)
        tours = re.search(r"(\d+) tours attempted, (\d+) explicitly skipped", output)
        return (f"{ok}/{n} approaches on {maps} maps"
                + (f"; {tours[1]} tours, {tours[2]} skipped (wandering people)" if tours else ""))
    if step.id == "reconstruction":
        m = re.search(r"^OVERALL (.*?) \(", output, re.M)
        return m[1] if m else ""
    if step.id == "roundtrip":
        pcts = [float(p) for p in re.findall(r"identical \(([\d.]+)%\)", output)]
        guards = len(re.findall(r"^PASS: ", output, re.M))
        return (f"{min(pcts):.1f}-{max(pcts):.1f}% identical on {len(pcts)} maps; {guards} guards PASS"
                if pcts else "")
    if step.id == "route_metrics":
        steps = re.findall(r"^  \S+ -> \S+: (\d+) steps, (\d+) in tall grass", output, re.M)
        return ("crossings " + ", ".join(f"{s}" for s, _ in steps)
                + f" steps; {sum(int(g) for _, g in steps)} forced tall grass") if steps else ""
    if step.id == "encounters":
        return f"{len(re.findall(r'^battle \d+: wild ', output, re.M))} wild battles"
    unit = re.search(r"^Ran (\d+) tests? in .*\n\s*\n(OK.*|FAILED.*)$", output, re.M)
    if unit:      # unittest's summary (stderr, so it can land before the tests' own stdout)
        return f"{unit[1]} tests {unit[2]}"
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    verdict = next((l for l in reversed(lines)
                    if re.match(r"(TOTAL|RESULT|PASS|FAIL|checker|accuracy|\d+ maps)", l, re.I)
                    or "%" in l), lines[-1] if lines else "")
    # tests built on check(ok, what) print one "PASS: what" / "FAIL: what" line per check
    passes = len(re.findall(r"^\s+PASS: ", output, re.M))
    fails = len(re.findall(r"^\s+FAIL: ", output, re.M))
    if passes + fails and (verdict in ("PASS", "FAIL") or verdict.startswith("FAIL (")):
        return f"{passes}/{passes + fails} checks"
    return verdict[:140]


def evaluate(step, exit_code, output):
    if exit_code != 0:
        return "FAILED", f"exit code {exit_code}"
    reason = coverage_error(step, output)
    if reason:
        return "FAILED", reason
    if step.kind == "observed":
        return "OBSERVED", "measurement only; no quality threshold"
    return "PASSED", ""


def acquire_lock():
    """An OS-held lock on dev/out/regression/run.lock; None if another run holds it. The OS
    releases it when this process exits, however it exits, so a crashed run never blocks."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = open(OUT / "run.lock", "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def kill_tree(proc, wsl_build=False):
    """Kill a step and every Windows process it started (its mGBA). Killing wsl.exe doesn't
    stop the Linux side, so a build step also stops make in the WSL mirror (wsl_build)."""
    if proc.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if wsl_build:
        sys.path.insert(0, str(REPO / "dev"))
        import fastbuild
        subprocess.run(["wsl", "-d", fastbuild.DISTRO, "--exec", "pkill", "-x", "make"],
                       capture_output=True)


def other_emulators():
    """mGBA processes already running (Tom's own, or a test started by hand)."""
    if sys.platform != "win32":
        return []
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq mGBA.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [row[1] for row in csv.reader(io.StringIO(out)) if len(row) > 1 and row[0].lower() == "mgba.exe"]


def sweep_scratch():
    """Remove emulator scratch folders left by killed runs (older than STALE_SECONDS, so a test
    started by hand right now keeps its folder)."""
    removed = 0
    for d in SCRATCH.iterdir() if SCRATCH.exists() else ():
        if d.is_dir() and d.name.startswith(SCRATCH_PREFIXES) and time.time() - d.stat().st_mtime > STALE_SECONDS:
            shutil.rmtree(d, ignore_errors=True)
            removed += not d.exists()
    return removed


def run_step(command, log, timeout, wsl_build=False):
    """Run one step with its output in log; returns the exit code (124 on timeout)."""
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(command, cwd=REPO, stdout=out, stderr=subprocess.STDOUT)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc, wsl_build)
            out.write(f"\n[regression] TIMEOUT after {timeout}s: step and its processes killed\n")
            return 124
        except BaseException:
            kill_tree(proc, wsl_build)
            raise


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list every full-regression step")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run named steps and the build")
    args = parser.parse_args(argv)
    steps = manifest()
    if args.list:
        for step in steps:
            print(f"{step.id:28} {step.kind:8} {' '.join(step.command)}")
        print(f"{len(steps)} steps in the full regression")
        return 0
    ids = {step.id for step in steps}
    unknown = set(args.only or ()) - ids
    if unknown:
        parser.error("unknown step IDs: " + ", ".join(sorted(unknown)))
    selected = ({"build", *args.only} if args.only else ids)
    lock = acquire_lock()
    if lock is None:
        print("FAIL: another regression run holds dev/out/regression/run.lock; wait for it to finish")
        return 2
    others = other_emulators()
    if others:
        print(f"WARNING: {len(others)} mGBA already running (pid {', '.join(others)}). The tests use "
              "their own sessions, but a busy CPU slows timing-sensitive steps; close it if a step times out.")
    swept = sweep_scratch()
    if swept:
        print(f"Removed {swept} stale emulator scratch folders from killed runs")
    run_dir = OUT / (datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1000000}")
    run_dir.mkdir()
    results = []
    print(f"Regression: {len(selected)} selected of {len(steps)} steps; serial execution")
    if args.only:
        print("SELECTED SUBSET: unselected steps will be reported SKIPPED")
    build_failed = False
    for i, step in enumerate(steps, 1):
        record = {"id": step.id, "kind": step.kind, "command": [sys.executable, "-B", *step.command]}
        if step.id not in selected or build_failed:
            record.update(status="SKIPPED", reason="build failed" if build_failed else "excluded by --only")
        else:
            log = run_dir / f"{i:02}_{step.id}.log"
            print(f"START {i}/{len(steps)} {step.id}", flush=True)
            start = time.monotonic()
            code = run_step(record["command"], log, step.timeout, wsl_build=step.id == "build")
            output = log.read_text(encoding="utf-8", errors="replace")
            status, reason = evaluate(step, code, output)
            if code == 124:
                reason = f"timed out after {step.timeout}s (process tree killed)"
            record.update(status=status, reason=reason, exit_code=code, seconds=round(time.monotonic()-start, 1),
                          evidence=evidence(step, output), log=str(log.relative_to(REPO)))
            print(f"{status} {step.id} ({record['seconds']}s)" + (f": {reason}" if reason else "")
                  + (f"  [{record['evidence']}]" if record["evidence"] else ""), flush=True)
            if status == "FAILED":
                print("\n".join(output.splitlines()[-15:]), flush=True)
            if step.id == "build" and status == "FAILED":
                build_failed = True
        results.append(record)
    git = lambda *a: subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()
    rom = REPO / "pokeemerald.gba"
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    report = {"branch": git("branch", "--show-current"), "commit": git("rev-parse", "HEAD"),
              "dirty": dirty,
              "rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest() if rom.exists() else None,
              "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "selection": sorted(selected), "steps": results}
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    counts = {state: sum(r["status"] == state for r in results)
              for state in ("PASSED", "OBSERVED", "SKIPPED", "FAILED")}
    print("\nEvidence:")
    for r in results:
        if r["status"] != "SKIPPED":
            print(f"  {r['status']:8} {r['id']:30} {r.get('evidence', '')}")
    print(f"\nTested {report['branch']} @ {report['commit'][:10]}"
          + (" WITH UNCOMMITTED CHANGES" if dirty else "") + f", ROM sha256 {str(report['rom_sha256'])[:16]}")
    print(f"\nRESULT: {counts['PASSED']} gates passed, {counts['OBSERVED']} observed metrics, "
          f"{counts['SKIPPED']} skipped, {counts['FAILED']} failed")
    print(f"Report: {run_dir / 'report.json'}")
    return 1 if counts["FAILED"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
