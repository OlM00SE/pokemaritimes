"""dev/corridor.py join in disposable fixtures (no game data changes).

  python dev/tests/corridor_join.py

The joins between a planned map and its built neighbours are set as the plan derives them, on
both sides, a direction included (HomeTown's seam turned from down to right in M16); other
connections are kept in place; a re-run changes nothing; a folder not yet at the plan's size is
refused with nothing written; a failure while writing restores every file byte for byte.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import corridor
from mapkit.geo import Plan
from mapkit.project import Project, REPO

MAPS = ("HomeTown_0", "Route201_1", "Woodstock_2", "Route202_1")
# the connections as they were before M16: HomeTown joined Route 201 downward, Woodstock at 22
OLD = {
    "HomeTown_0": [{"map": "MAP_ROUTE201_1", "offset": 0, "direction": "down"}],
    "Route201_1": [{"map": "MAP_WOODSTOCK_2", "offset": -22, "direction": "right"},
                   {"map": "MAP_HOME_TOWN_0", "offset": 0, "direction": "up"}],
}


class CorridorJoin(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        out = Path(REPO) / "dev/out"
        out.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="corridor-join-", dir=out)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        src = Project()
        self.copy("data/layouts/layouts.json")
        for name in MAPS:
            shutil.copytree(Path(REPO) / "data/maps" / name, self.root / "data/maps" / name)
            entry = src.load_map(name).layout.entry
            for key in ("blockdata_filepath", "border_filepath"):
                self.copy(entry[key])
        for name, conns in OLD.items():
            self.set_conns(name, conns)
        wj = self.load("Woodstock_2")
        for c in wj["connections"]:
            if c["map"] == "MAP_ROUTE201_1":
                c["offset"] = 22
        self.save("Woodstock_2", wj)
        self.p = Project(str(self.root))
        self.plan = Plan()

    def copy(self, rel):
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(REPO) / rel, dest)

    def load(self, name):
        return json.loads((self.root / "data/maps" / name / "map.json").read_text(encoding="utf-8"))

    def save(self, name, j):
        (self.root / "data/maps" / name / "map.json").write_text(json.dumps(j, indent=2), encoding="utf-8")

    def set_conns(self, name, conns):
        j = self.load(name)
        j["connections"] = [dict(c) for c in conns]
        self.save(name, j)

    def conns(self, name):
        return [(c["map"], c["direction"], int(c["offset"])) for c in self.load(name)["connections"]]

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_sets_the_plans_joins_both_sides(self):
        changes, jsons, problems = corridor.join_plan(self.plan, "Route 201", self.p)
        self.assertEqual(problems, [])
        self.assertEqual(len(changes), 4, changes)
        corridor.join_apply(self.p, jsons)
        self.assertEqual(self.conns("HomeTown_0"), [("MAP_ROUTE201_1", "right", 2)])
        # Route 201 keeps its order: Woodstock first (re-offset), then HomeTown (turned)
        self.assertEqual(self.conns("Route201_1"), [("MAP_WOODSTOCK_2", "right", -14),
                                                    ("MAP_HOME_TOWN_0", "left", -2)])
        # Woodstock's other connection (Route 202) is untouched
        wood = self.conns("Woodstock_2")
        self.assertIn(("MAP_ROUTE201_1", "left", 14), wood)
        self.assertEqual([c for c in wood if c[0] == "MAP_ROUTE202_1"],
                         [c for c in [(c["map"], c["direction"], int(c["offset"]))
                                      for c in json.loads((Path(REPO) / "data/maps/Woodstock_2/map.json")
                                                          .read_text(encoding="utf-8"))["connections"]]
                          if c[0] == "MAP_ROUTE202_1"])
        again = corridor.join_plan(self.plan, "Route 201", Project(str(self.root)))
        self.assertEqual((again[0], again[2]), ([], []), "a re-run changes nothing")

    def test_removes_a_join_the_plan_doesnt_have(self):
        # a stale seam: Route 201 joined to Route 202 below it (the plan doesn't put them side by
        # side); dive/emerge links are kept whatever they point at
        r = self.load("Route201_1")
        r["connections"] += [{"map": "MAP_ROUTE202_1", "offset": 3, "direction": "down"},
                             {"map": "MAP_ROUTE202_1", "offset": 0, "direction": "dive"}]
        self.save("Route201_1", r)
        q = self.load("Route202_1")
        q["connections"].append({"map": "MAP_ROUTE201_1", "offset": -3, "direction": "up"})
        self.save("Route202_1", q)
        changes, jsons, problems = corridor.join_plan(self.plan, "Route 201", Project(str(self.root)))
        self.assertEqual(problems, [])
        self.assertTrue(any("Route201_1 -> Route202_1: down 3  =>  removed" in c for c in changes), changes)
        corridor.join_apply(Project(str(self.root)), jsons)
        self.assertEqual([c for c in self.conns("Route201_1") if c[0] == "MAP_ROUTE202_1"],
                         [("MAP_ROUTE202_1", "dive", 0)])
        self.assertEqual([c for c in self.conns("Route202_1") if c[0] == "MAP_ROUTE201_1"], [])

    def test_refuses_a_folder_not_at_the_plans_size(self):
        lj = self.root / "data/layouts/layouts.json"
        data = json.loads(lj.read_text(encoding="utf-8"))
        entry = next(l for l in data["layouts"] if l.get("id") == "LAYOUT_HOME_TOWN_0")
        entry["width"] = 36
        lj.write_text(json.dumps(data, indent=2), encoding="utf-8")
        before = self.snapshot()
        changes, jsons, problems = corridor.join_plan(self.plan, "Route 201", Project(str(self.root)))
        self.assertTrue(any("HomeTown_0 is 36x28" in pr for pr in problems), problems)
        self.assertEqual(self.snapshot(), before, "nothing is written by a refused plan")

    def test_a_failure_while_writing_restores_every_file(self):
        changes, jsons, problems = corridor.join_plan(self.plan, "Route 201", self.p)
        before = self.snapshot()
        from mapkit import mapjson
        real, calls = mapjson.dump_json, []

        def flaky(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise RuntimeError("disk full (injected)")
            return real(path, data)
        with patch("mapkit.mapjson.dump_json", flaky):
            with self.assertRaises(RuntimeError):
                corridor.join_apply(self.p, jsons)
        self.assertEqual(len(calls), 2, "the fault was injected mid-write")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    n = result.testsRun
    bad = len(result.failures) + len(result.errors)
    print(f"RESULT: {n - bad}/{n} corridor join tests pass")
    sys.exit(1 if bad or not n else 0)
