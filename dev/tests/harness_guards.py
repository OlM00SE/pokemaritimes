"""Negative controls: empty or skipped tests must fail, and regression claims need evidence.

  python dev/tests/harness_guards.py

These checks mock the emulator only to force the failure paths; emulator_isolation.py and the
normal game suites exercise the real bridge.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import re
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEV)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import regression
import conformance
import ingame_buildings
import ingame_doors
import ingame_encounters
import ingame_events
import ingame_flora
import ingame_shores


class FakeEmu:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def boot_new_game(self):
        return True

    def test_mode(self, **kwargs):
        pass

    def give_mon(self, *args):
        pass

    def teach_move(self, *args):
        pass

    def set_flag(self, *args):
        pass

    def warp(self, *args):
        return (0, 0, 99, 99)

    def player(self):
        return (0, 0, 1, 2)


def quietly(fn, *args):
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue()


class HarnessGuards(unittest.TestCase):
    def test_conformance_rejects_zero_samples(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ex:
            conformance.main(["--samples", "0", "Route201_1"])
        self.assertNotEqual(ex.exception.code, 0)

    def test_conformance_relocated_warp_is_failure_not_a_pass(self):
        with mock.patch.object(conformance, "Emu", FakeEmu), \
             mock.patch.object(conformance, "prepare_rom", return_value="unused"), \
             mock.patch.object(conformance, "samples_for",
                               return_value=([(1, 2, "N", (1, 1), "walk")], 0)):
            code, output = quietly(conformance.main, ["Route201_1"])
        self.assertEqual(code, 1)
        self.assertIn("0/0 executed, 1 planned, 1 skipped, 1 failed", output)

    def test_conformance_warp_error_does_not_pass_or_hide_remaining_maps(self):
        class FailingWarp(FakeEmu):
            def warp(self, *args):
                raise RuntimeError("transport closed")
        with mock.patch.object(conformance, "Emu", FailingWarp), \
             mock.patch.object(conformance, "prepare_rom", return_value="unused"), \
             mock.patch.object(conformance, "samples_for",
                               return_value=([(1, 2, "N", (1, 1), "walk")], 0)):
            code, output = quietly(conformance.main, ["Route201_1", "Woodstock_2"])
        self.assertEqual(code, 1)
        self.assertIn("Remaining 1 maps NOT RUN", output)

    def test_doors_without_maps_or_doors_fail(self):
        self.assertEqual(quietly(ingame_doors.main, [])[0], 1)
        project = mock.Mock()
        project.load_map.return_value = SimpleNamespace(events=lambda kind: [])
        with mock.patch.object(ingame_doors, "Emu", FakeEmu), \
             mock.patch.object(ingame_doors, "prepare_rom", return_value="unused"), \
             mock.patch.object(ingame_doors, "Project", return_value=project), \
             mock.patch.object(ingame_doors, "door_tiles", return_value=[]):
            code, output = quietly(ingame_doors.main, ["Route201_1"])
        self.assertEqual(code, 1)
        self.assertIn("NOT TESTED", output)

    def test_buildings_without_active_rooms_fail(self):
        project = mock.Mock()
        project.load_map.return_value = SimpleNamespace(id="MAP_EMPTY")
        with mock.patch.object(ingame_buildings, "Project", return_value=project), \
             mock.patch.object(ingame_buildings, "Emu", FakeEmu), \
             mock.patch.object(ingame_buildings, "prepare_rom", return_value="unused"), \
             mock.patch.object(ingame_buildings, "fast_text"), \
             mock.patch.object(ingame_buildings, "rooms",
                               return_value=[({"x": 1, "y": 1}, "EmptyRoom")]), \
             mock.patch.object(ingame_buildings.interiors, "heal_locations",
                               return_value={"heal_locations": []}), \
             mock.patch.object(ingame_buildings.interiors, "load",
                               return_value={"id": "MAP_EMPTY_ROOM", "object_events": []}), \
             mock.patch.object(ingame_buildings, "stock", return_value=None):
            code, output = quietly(ingame_buildings.main, ["EmptyOutdoor"])
        self.assertEqual(code, 1)
        self.assertIn("NOT TESTED", output)

    def test_events_without_specs_or_checks_fail(self):
        with mock.patch.object(ingame_events.glob, "glob", return_value=[]):
            self.assertEqual(quietly(ingame_events.main, [])[0], 1)
        run = ingame_events.Run.__new__(ingame_events.Run)
        run.name = "Empty"
        run.m = SimpleNamespace(events=lambda kind: [])
        run.passed = run.failed = 0
        self.assertFalse(quietly(run.run)[0])

    def test_shores_and_flora_without_cases_fail(self):
        project = mock.Mock()
        project.load_map.return_value = SimpleNamespace(layout=SimpleNamespace())
        for module, cases in ((ingame_shores, {"bump": [], "land": [], "rock": []}),
                              (ingame_flora, ([], []))):
            with self.subTest(module=module.__name__), \
                 mock.patch.object(module, "Project", return_value=project), \
                 mock.patch.object(module, "Emu", FakeEmu), \
                 mock.patch.object(module, "prepare_rom", return_value="unused"), \
                 mock.patch.object(module, "cases_for", return_value=cases):
                if module is ingame_shores:
                    with mock.patch.object(module, "flag_id", return_value=1):
                        code, output = quietly(module.main, ["Empty"])
                else:
                    code, output = quietly(module.main, ["Empty"])
            self.assertEqual(code, 1)
            self.assertIn("NOT TESTED", output)

    def test_zero_requested_battles_fail(self):
        self.assertEqual(quietly(ingame_encounters.main, ["Route201_1", "--battles", "0"])[0], 1)

    def test_runner_rejects_empty_success_and_distinguishes_observation(self):
        conf = next(s for s in regression.manifest() if s.id == "conformance")
        self.assertEqual(regression.evaluate(conf, 0,
            "TOTAL: 0/0 executed comparisons; 0 skipped, 0 failed")[0], "FAILED")
        dry = next(s for s in regression.manifest() if s.check == "events_dryrun")
        self.assertEqual(regression.evaluate(dry, 0, "checker: 0 errors")[0], "FAILED")
        metric = next(s for s in regression.manifest() if s.id == "reconstruction")
        self.assertEqual(regression.evaluate(metric, 0, "accuracy 0%")[0], "OBSERVED")

    def test_runner_evidence_reports_counts(self):
        steps = {s.id: s for s in regression.manifest()}
        self.assertEqual(regression.evidence(steps["events"],
            "HomeTown_0: 22/22 checks pass\nWoodstock_2: 40/41 checks pass\nFAIL\n"), "62/63 checks on 2 maps")
        self.assertEqual(regression.evidence(steps["save"],
            "  PASS: a\n  PASS: b\n  FAIL: c\nFAIL (1)\n"), "2/3 checks")
        self.assertEqual(regression.evidence(steps["encounters"],
            "battle 1: wild ZIGZAGOON after 3 steps\nbattle 2: wild WURMPLE after 9 steps\nRESULT: PASS\n"),
            "2 wild battles")
        self.assertEqual(regression.evidence(steps["conformance"],
            "x\nTOTAL: 5/5 executed comparisons; 0 skipped, 0 failed\n"),
            "TOTAL: 5/5 executed comparisons; 0 skipped, 0 failed")
        self.assertEqual(regression.evidence(steps["authoring"],
            "...\nRan 20 tests in 14.1s\n\nOK\nfailed; every change was rolled back\n"), "20 tests OK")

    def test_runner_timeout_kills_the_whole_process_tree(self):
        # a step that starts a long-lived child (as a test starts mGBA), then hangs
        script = ("import subprocess, sys, time\n"
                  "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                  "print('child', p.pid, flush=True)\n"
                  "time.sleep(120)\n")
        with tempfile.TemporaryDirectory() as folder:
            log = regression.Path(folder) / "step.log"
            code = regression.run_step([sys.executable, "-c", script], log, timeout=5)
            text = log.read_text(encoding="utf-8")
        self.assertEqual(code, 124)
        self.assertIn("TIMEOUT", text)
        child = int(re.search(r"child (\d+)", text)[1])
        self.assertFalse(process_alive(child), "the step's child process survived the timeout")

    def test_runner_lock_refuses_a_second_run(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(regression, "OUT", regression.Path(folder)):
            first = regression.acquire_lock()
            try:
                self.assertIsNotNone(first)
                self.assertIsNone(regression.acquire_lock())
            finally:
                first.close()
            again = regression.acquire_lock()      # released with its holder
            self.assertIsNotNone(again)
            again.close()

    def test_runner_sweeps_only_stale_scratch(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(regression, "SCRATCH", regression.Path(folder)):
            root = regression.Path(folder)
            for name in ("emutest-old", "emutest-new", "keep-old"):
                (root / name).mkdir()
            old = time.time() - regression.STALE_SECONDS - 60
            os.utime(root / "emutest-old", (old, old))
            os.utime(root / "keep-old", (old, old))
            self.assertEqual(regression.sweep_scratch(), 1)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["emutest-new", "keep-old"])


def process_alive(pid):
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


if __name__ == "__main__":
    unittest.main(verbosity=2)
