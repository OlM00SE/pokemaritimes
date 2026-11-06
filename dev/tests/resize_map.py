"""dev/resize_map.py in disposable fixtures (no game data changes).

  python dev/tests/resize_map.py

The terrain moves cell for cell and new cells get the solid border pattern; events, heal
locations and both sides of each connection move with it; --connect sets a seam; a crop that
loses an event, a shared layout and a mismatched connection pair are refused with nothing
written; a failure while writing restores every file byte for byte.
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
import resize_map
from mapkit.project import Project, REPO

MAPS = ("Woodstock_2", "Route201_1", "Route202_1")


class ResizeMap(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        out = Path(REPO) / "dev/out"
        out.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="resize-map-", dir=out)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        src = Project()
        for rel in ("data/layouts/layouts.json", resize_map.HEAL_PATH):
            self.copy(rel)
        for name in MAPS:
            shutil.copytree(Path(REPO) / "data/maps" / name, self.root / "data/maps" / name)
            entry = src.load_map(name).layout.entry
            for key in ("blockdata_filepath", "border_filepath"):
                self.copy(entry[key])
        # a heal location on the map, as a Center would add
        heal = self.root / resize_map.HEAL_PATH
        data = json.loads(heal.read_text(encoding="utf-8"))
        data["heal_locations"].append({"id": "HEAL_LOCATION_FIXTURE", "map": "MAP_WOODSTOCK_2",
                                       "x": 10, "y": 12, "respawn_map": "MAP_WOODSTOCK_LAB",
                                       "respawn_npc": "LOCALID_X"})
        heal.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.p = Project(str(self.root))
        self.before = self.snapshot()

    def copy(self, rel):
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(REPO) / rel, dest)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def conn(self, name, to):
        j = json.loads((self.root / "data/maps" / name / "map.json").read_text(encoding="utf-8"))
        return {c["direction"]: int(c["offset"]) for c in j["connections"] if c["map"] == to}

    def test_moves_everything_with_the_terrain(self):
        old = self.p.load_map("Woodstock_2")
        old_events = {k: [(e["x"], e["y"]) for e in old.events(k)] for k in resize_map.EVENT_KINDS}
        left = self.conn("Woodstock_2", "MAP_ROUTE201_1")["left"]      # the seams as they are now
        down = self.conn("Woodstock_2", "MAP_ROUTE202_1")["down"]
        pl = resize_map.plan(self.p, "Woodstock_2", old.layout.width + 12, old.layout.height + 8, 2, 3)
        self.assertFalse(pl.problems, pl.problems)
        resize_map.apply(self.p, pl)
        p = Project(str(self.root))
        new = p.load_map("Woodstock_2")
        L, OL = new.layout, old.layout
        self.assertEqual((L.width, L.height), (OL.width + 12, OL.height + 8))
        self.assertTrue(L.size_ok)
        for y in range(OL.height):
            for x in range(OL.width):
                self.assertEqual(L.get(x + 2, y + 3), OL.get(x, y), (x, y))
        border = {b & 0x3FF for b in OL.border}
        for x, y in ((0, 0), (L.width - 1, L.height - 1), (L.width - 3, 2), (1, L.height - 2)):
            self.assertIn(L.mid(x, y), border)
            self.assertEqual(L.coll(x, y), 1, "new cells are solid")
        for k in resize_map.EVENT_KINDS:
            self.assertEqual([(e["x"], e["y"]) for e in new.events(k)],
                             [(x + 2, y + 3) for x, y in old_events[k]], k)
        heal = json.loads((self.root / resize_map.HEAL_PATH).read_text(encoding="utf-8"))
        h = next(h for h in heal["heal_locations"] if h["id"] == "HEAL_LOCATION_FIXTURE")
        self.assertEqual((h["x"], h["y"]), (12, 15))
        # left/right seams follow dy, up/down seams follow dx, on both sides
        self.assertEqual(self.conn("Woodstock_2", "MAP_ROUTE201_1"), {"left": left + 3})
        self.assertEqual(self.conn("Route201_1", "MAP_WOODSTOCK_2"), {"right": -(left + 3)})
        self.assertEqual(self.conn("Woodstock_2", "MAP_ROUTE202_1"), {"down": down + 2})
        self.assertEqual(self.conn("Route202_1", "MAP_WOODSTOCK_2"), {"up": -(down + 2)})

    def test_connect_sets_a_seam(self):
        down = self.conn("Woodstock_2", "MAP_ROUTE202_1")["down"]
        pl = resize_map.plan(self.p, "Woodstock_2", 48, 42, connect={"Route201_1": 31})
        resize_map.apply(self.p, pl, {"Route201_1": 31})
        self.assertEqual(self.conn("Woodstock_2", "MAP_ROUTE201_1"), {"left": 31})
        self.assertEqual(self.conn("Route201_1", "MAP_WOODSTOCK_2"), {"right": -31})
        self.assertEqual(self.conn("Woodstock_2", "MAP_ROUTE202_1"), {"down": down})

    def test_refusals_write_nothing(self):
        pl = resize_map.plan(self.p, "Woodstock_2", 20, 20)         # crops warps and people
        self.assertTrue(any("off the 20x20 map" in pr for pr in pl.problems), pl.problems)
        with self.assertRaises(ValueError):
            resize_map.apply(self.p, pl)
        with self.assertRaises(ValueError):
            resize_map.plan(self.p, "Woodstock_2", 48, 42, connect={"Fredericton_0": 3})
        with self.assertRaises(ValueError):
            resize_map.plan(self.p, "Woodstock_2", 120, 120)          # the engine's buffer
        # a connection pair that doesn't agree
        rj = self.root / "data/maps/Route201_1/map.json"
        j = json.loads(rj.read_text(encoding="utf-8"))
        next(c for c in j["connections"] if c["map"] == "MAP_WOODSTOCK_2")["offset"] = 5
        rj.write_text(json.dumps(j, indent=2), encoding="utf-8")
        self.before[str(rj.relative_to(self.root))] = rj.read_bytes()
        pl = resize_map.plan(Project(str(self.root)), "Woodstock_2", 48, 42)
        self.assertTrue(any("fix the pair" in pr for pr in pl.problems), pl.problems)
        self.assertEqual(self.before, self.snapshot())

    def test_shared_layout_refused(self):
        wj = self.root / "data/maps/Route202_1/map.json"
        j = json.loads(wj.read_text(encoding="utf-8"))
        j["layout"] = "LAYOUT_WOODSTOCK_2"
        wj.write_text(json.dumps(j, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "shared"):
            resize_map.plan(Project(str(self.root)), "Woodstock_2", 48, 42)

    def test_stale_preview_refused(self):
        pl = resize_map.plan(self.p, "Woodstock_2", 48, 42)
        # the seam changes (both sides, consistently) after the preview was shown
        for name, to, off in (("Woodstock_2", "MAP_ROUTE201_1", 4), ("Route201_1", "MAP_WOODSTOCK_2", -4)):
            path = self.root / "data/maps" / name / "map.json"
            j = json.loads(path.read_text(encoding="utf-8"))
            next(c for c in j["connections"] if c["map"] == to)["offset"] = off
            path.write_text(json.dumps(j, indent=2), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "changed since the preview"):
            resize_map.apply(Project(str(self.root)), pl)
        self.assertEqual(before, self.snapshot())

    def test_connect_names_a_side(self):
        # Woodstock joined to Route 201 on two sides: a bare --connect is ambiguous
        for name, to, d in (("Woodstock_2", "MAP_ROUTE201_1", "up"), ("Route201_1", "MAP_WOODSTOCK_2", "down")):
            path = self.root / "data/maps" / name / "map.json"
            j = json.loads(path.read_text(encoding="utf-8"))
            j["connections"].append({"map": to, "offset": 0, "direction": d})
            path.write_text(json.dumps(j, indent=2), encoding="utf-8")
        p = Project(str(self.root))
        with self.assertRaisesRegex(ValueError, "2 sides"):
            resize_map.plan(p, "Woodstock_2", 48, 42, connect={"Route201_1": 9})
        pl = resize_map.plan(p, "Woodstock_2", 48, 42, connect={"Route201_1:left": 9})
        self.assertFalse(pl.problems, pl.problems)
        resize_map.apply(p, pl, {"Route201_1:left": 9})
        j = json.loads((self.root / "data/maps/Woodstock_2/map.json").read_text(encoding="utf-8"))
        offs = {c["direction"]: c["offset"] for c in j["connections"] if c["map"] == "MAP_ROUTE201_1"}
        self.assertEqual(offs, {"left": 9, "up": 0})

    def test_failure_restores_every_byte(self):
        pl = resize_map.plan(self.p, "Woodstock_2", 48, 42, 1, 1)
        real = resize_map.dump_json
        calls = []

        def flaky(path, obj):
            calls.append(path)
            if "Route202_1" in str(path):
                raise OSError("simulated disk failure")
            real(path, obj)
        with patch.object(resize_map, "dump_json", flaky):
            with self.assertRaises(OSError):
                resize_map.apply(self.p, pl)
        self.assertTrue(len(calls) >= 2, "the failure came after earlier writes")
        self.assertEqual(self.before, self.snapshot())


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    n = result.testsRun
    bad = len(result.failures) + len(result.errors)
    print(f"RESULT: {n - bad}/{n} resize tests pass")
    raise SystemExit(1 if bad or n == 0 else 0)
