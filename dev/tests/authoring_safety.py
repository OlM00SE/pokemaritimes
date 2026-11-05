"""Authoring safety regressions, with real writers in disposable project fixtures.

  python dev/tests/authoring_safety.py

No game data is changed. Check shared-layout refusal/detachment, generated room name
collisions, successful creation, and byte-for-byte rollback after late write failures.
"""
import copy
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
import add_interior
import events
import mapgen
import name_area
import new_map
import fix_attrs
import unique_layout
from mapkit import buildings, interiors, stamps
from mapkit.layout import SharedLayoutError, layout_users
from mapkit.project import Project, REPO
from mapkit.transaction import edit


class AuthoringSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Existing map readers use short-lived open(...).read() handles; unittest enables
        # ResourceWarning globally, which otherwise buries the actual regression results.
        warnings.simplefilter("ignore", ResourceWarning)
        cls.source = Project()
        cls.cat = stamps.catalog(cls.source)

    def setUp(self):
        out = Path(REPO) / "dev/out"
        out.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="authoring-safety-", dir=out)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.p = Project(str(self.root))
        for rel in ("data/layouts/layouts.json", "data/maps/map_groups.json", "data/event_scripts.s",
                    interiors.HEAL_JSON, name_area.SECTIONS, "include/constants/opponents.h",
                    "include/constants/flags.h", "src/data/trainers.party"):
            self.copy(rel)
        names = {"TownLab", "TownLab_SmallHouse", "TownLab_OldaleHouse", "HomeTown_0", "UnionRoom", "TradeCenter"}
        for kind in ("pokemon_center", "mart", "house_two_storey"):
            names.update(interiors.floors(self.source, self.cat[kind].interior))
            names.add(self.source.const_to_map[interiors.exterior_of(self.source, self.cat[kind].interior)])
        for name in names:
            src = Path(REPO) / "data/maps" / name
            shutil.copytree(src, self.root / "data/maps" / name)
            entry = self.source.load_map(name).layout.entry
            for key in ("blockdata_filepath", "border_filepath"):
                self.copy(entry[key])
        heal = self.root / interiors.HEAL_JSON
        data = json.loads(heal.read_text(encoding="utf-8"))
        data["heal_locations"] = [e for e in data["heal_locations"] if e["id"] != "HEAL_LOCATION_TOWN_LAB"]
        heal.write_text(json.dumps(data), encoding="utf-8")
        self.before = self.snapshot()

    def copy(self, rel):
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(REPO) / rel, dest)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def assert_restored(self):
        self.assertEqual(self.before, self.snapshot())
        self.assertFalse(any(p.name.startswith("ZzSafety") for p in self.root.rglob("*")))

    def door_plan(self):
        # Use catalog geometry from real assets with an otherwise private new-town fixture.
        m = self.p.load_map("TownLab")
        m.j["warp_events"] = []
        with patch.object(stamps, "catalog", return_value=self.cat):
            dp = buildings.plan(self.p, m, [
                stamps.Placement("pokemon_center", 3, 2, "ZzSafetyCenter_1F"),
                stamps.Placement("mart", 12, 2, "ZzSafetyMart")])
        self.assertFalse(dp.problems, dp.problems)
        buildings.preview(m, dp)
        # Ensure the outer terrain write differs, so rollback really has work to undo.
        m.layout.blocks[0] ^= 0x0400
        return m, dp

    def test_shared_layout_refuses_change_and_allows_noop(self):
        a = self.p.load_map("TownLab_SmallHouse")
        self.assertIn("TownLab_OldaleHouse", layout_users(self.p, a.layout.entry))
        a.layout.save()
        a.layout.blocks[0] ^= 0x0400
        with self.assertRaisesRegex(SharedLayoutError, "unique_layout"):
            a.layout.save()
        self.assert_restored()

    def test_failed_single_file_replacement_keeps_original_and_cleans_temp(self):
        m = self.p.load_map("TownLab")
        m.layout.blocks[0] ^= 0x0400
        with patch("mapkit.transaction.os.replace", side_effect=OSError("injected replacement failure")):
            with self.assertRaises(OSError):
                m.layout.save()
        self.assert_restored()

    def test_distinct_layout_ids_aliasing_one_binary_are_protected(self):
        data = json.loads((self.root / "data/layouts/layouts.json").read_text(encoding="utf-8"))
        e = copy.deepcopy(self.p.load_map("TownLab_SmallHouse").layout.entry)
        e["id"] = "LAYOUT_ZZ_ALIAS"
        data["layouts"].append(e)
        (self.root / "data/layouts/layouts.json").write_text(json.dumps(data), encoding="utf-8")
        m = self.p.load_map("TownLab_OldaleHouse")
        m.j["layout"] = e["id"]
        m.save()
        self.p.__dict__.pop("layouts", None)
        a = self.p.load_map("TownLab_SmallHouse")
        a.layout.blocks[0] ^= 0x0400
        with self.assertRaises(SharedLayoutError):
            a.layout.save()

    def test_detach_preserves_ids_events_geometry_and_isolates_later_edits(self):
        group = (self.root / "data/maps/map_groups.json").read_bytes()
        m, e = unique_layout.plan(self.p, "TownLab_SmallHouse")
        original = copy.deepcopy(m.j)
        source = Path(self.p.path(m.layout.entry["blockdata_filepath"]))
        original_bytes = source.read_bytes()
        unique_layout.apply(self.p, m, e)
        detached = self.p.load_map(m.name)
        expected = dict(original, layout=e["id"])
        self.assertEqual(expected, detached.j)
        self.assertEqual(original_bytes, Path(self.p.path(e["blockdata_filepath"])).read_bytes())
        self.assertEqual(Path(self.p.path(m.layout.entry["border_filepath"])).read_bytes(),
                         Path(self.p.path(e["border_filepath"])).read_bytes())
        self.assertEqual(group, (self.root / "data/maps/map_groups.json").read_bytes())
        detached.layout.blocks[0] ^= 0x0400
        detached.layout.save()
        self.assertEqual(original_bytes, source.read_bytes())
        self.assertNotEqual(original_bytes, Path(self.p.path(e["blockdata_filepath"])).read_bytes())
        self.assertIsNone(unique_layout.plan(self.p, m.name)[1])

    def test_detach_failure_after_registry_write_restores_everything(self):
        m, e = unique_layout.plan(self.p, "TownLab_SmallHouse")
        with patch.object(type(m), "save", side_effect=OSError("injected map write failure")):
            with self.assertRaises(OSError):
                unique_layout.apply(self.p, m, e)
        self.assert_restored()

    def test_detaching_the_namesake_of_a_shared_layout(self):
        m = self.p.load_map("TownLab_SmallHouse")
        m.j["layout"] = "LAYOUT_TOWN_LAB"
        m.save()                              # share the namesake's existing layout
        m, e = unique_layout.plan(self.p, "TownLab")
        self.assertEqual("LAYOUT_TOWN_LAB_UNIQUE", e["id"])
        unique_layout.apply(self.p, m, e)
        self.assertEqual("LAYOUT_TOWN_LAB_UNIQUE", self.p.load_map("TownLab").j["layout"])
        self.assertIsNone(unique_layout.plan(self.p, "TownLab")[1])

    def test_generated_upper_floor_and_constant_collisions_in_both_orders(self):
        m = self.source.load_map("TownLab")
        m.j["warp_events"] = []
        pairs = [
            [stamps.Placement("house_two_storey", 2, 2, "ZzSafety_1F"),
             stamps.Placement("house_small", 12, 2, "ZzSafety_2F")],
            [stamps.Placement("house_small", 2, 2, "ZzSafetyRoom"),
             stamps.Placement("house_small", 12, 2, "ZzSafety_Room")]]
        for pair in pairs:
            for pls in (pair, list(reversed(pair))):
                with self.subTest(names=[p.interior for p in pls]):
                    dp = buildings.plan(self.source, m, pls)
                    self.assertTrue(dp.problems, "colliding generated rooms must be refused")
                    with self.assertRaises(interiors.InteriorError):
                        buildings.apply(self.p, self.p.load_map("TownLab"), dp)
        self.assert_restored()

    def test_successful_building_apply_preserves_return_warp_indices(self):
        m, dp = self.door_plan()
        mapgen.apply(self.p, m, dp)
        ext = self.p.load_map("TownLab")
        self.assertEqual(2, len(ext.events("warp_events")))
        groups = json.loads((self.root / "data/maps/map_groups.json").read_text(encoding="utf-8"))
        for i, (_, ip, _) in enumerate(dp.creates):
            self.assertEqual(ip.exit_id, int(ext.events("warp_events")[i]["dest_warp_id"]))
            for n in ip.names.values():
                self.assertEqual(1, groups[interiors.GROUP].count(n))
                self.assertIn(n, self.p.map_names)
            room = self.p.load_map(ip.first)
            exits = [w for w in room.events("warp_events") if w["dest_map"] == ext.id]
            self.assertTrue(exits)
            self.assertTrue(all(int(w["dest_warp_id"]) == i for w in exits))
        heal = next(e for e in interiors.heal_locations(self.p)["heal_locations"]
                    if e["id"] == "HEAL_LOCATION_TOWN_LAB")
        self.assertEqual("MAP_ZZ_SAFETY_CENTER_1F", heal["respawn_map"])

    def test_late_heal_failure_rolls_back_terrain_rooms_registries_and_events(self):
        m, dp = self.door_plan()
        real = interiors.set_heal_location

        def fail(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("injected after heal location write")

        with patch.object(interiors, "set_heal_location", side_effect=fail):
            with self.assertRaises(OSError):
                mapgen.apply(self.p, m, dp)
        self.assert_restored()
        self.assertNotIn("ZzSafetyMart", self.p.map_names)

    def test_second_room_failure_and_ctrl_c_restore_first_completed_room(self):
        for error in (OSError, KeyboardInterrupt):
            m, dp = self.door_plan()
            real = interiors.write
            calls = 0

            def fail(*args, **kwargs):
                nonlocal calls
                calls += 1
                result = real(*args, **kwargs)
                if calls == 2:
                    raise error("injected after second room")
                return result

            with self.subTest(error=error.__name__), patch.object(interiors, "write", side_effect=fail):
                with self.assertRaises(error):
                    mapgen.apply(self.p, m, dp)
            self.assert_restored()

    def test_standalone_add_interior_failure_restores_exterior_and_includes(self):
        m = self.p.load_map("TownLab")
        ip = interiors.Plan(self.p, "OldaleTown_Mart", "ZzSafetyMart", "mart")
        real = interiors.add_script_includes

        def fail(*args):
            real(*args)
            raise OSError("injected after script includes")

        with patch.object(interiors, "add_script_includes", side_effect=fail):
            with self.assertRaises(OSError):
                add_interior.apply(self.p, m, 2, 2, ip)
        self.assert_restored()

    def test_orphan_room_directory_is_never_overwritten(self):
        folder = self.root / "data/maps/ZzSafetyMart"
        folder.mkdir()
        (folder / "notes.txt").write_text("keep me", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(interiors.InteriorError):
            interiors.Plan(self.p, "OldaleTown_Mart", "ZzSafetyMart", "mart")
        self.assertEqual(before, self.snapshot())

    def test_orphan_registered_map_name_is_not_reallocated(self):
        path = self.root / "data/maps/map_groups.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[interiors.GROUP].append("ZzSafetyMart")
        path.write_text(json.dumps(data), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(interiors.InteriorError):
            interiors.Plan(self.p, "OldaleTown_Mart", "ZzSafetyMart", "mart")
        self.assertEqual(before, self.snapshot())

    def test_orphan_registered_constant_is_not_reallocated_with_another_spelling(self):
        path = self.root / "data/maps/map_groups.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[interiors.GROUP].append("ZzSafety_Mart")
        path.write_text(json.dumps(data), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(interiors.InteriorError, "reserved by registered"):
            interiors.Plan(self.p, "OldaleTown_Mart", "ZzSafetyMart", "mart")
        self.assertEqual(before, self.snapshot())

    def test_standalone_interior_writer_rolls_back_completed_registration(self):
        ip = interiors.Plan(self.p, "OldaleTown_Mart", "ZzSafetyMart", "mart")
        real = interiors.add_script_includes

        def fail(*args):
            real(*args)
            raise OSError("injected after registration")

        with patch.object(interiors, "add_script_includes", side_effect=fail):
            with self.assertRaises(OSError):
                interiors.write(self.p, ip, "TownLab", "MAP_TOWN_LAB", 0)
        self.assert_restored()

    def test_event_failure_restores_map_script_party_and_saved_ids(self):
        m = self.p.load_map("TownLab_SmallHouse")  # no scripts.pory yet: rollback must remove it
        m.j["bg_events"] = [{"type": "sign", "script": "ZzSafetyEvent", "x": 0, "y": 0}]
        trainers, _ = events.plan_trainers(self.p, ["TRAINER_ZZ_SAFETY"])
        flags, _ = events.plan_flags(self.p, ["FLAG_ZZ_SAFETY"])
        real = events.write_flags

        def fail(*args):
            real(*args)
            raise OSError("injected after allocating saved flag")

        with patch.object(events, "write_flags", side_effect=fail):
            with self.assertRaises(OSError):
                events.apply_events(self.p, m, "script ZzSafetyEvent { end }\n", trainers,
                                    {"TRAINER_ZZ_SAFETY": "=== TRAINER_ZZ_SAFETY ===\n"}, flags)
        self.assert_restored()

    def test_area_name_failure_restores_section_and_maps(self):
        real = name_area.dump
        calls = 0

        def fail(*args):
            nonlocal calls
            real(*args)
            calls += 1
            if calls == 2:
                raise OSError("injected after first map rename")

        with patch.object(name_area, "Project", return_value=self.p), patch.object(name_area, "dump", side_effect=fail):
            with self.assertRaises(OSError):
                name_area.main(["MAPSEC_ZZ_SAFETY", "SAFETY", "TownLab", "HomeTown_0", "--apply"])
        self.assert_restored()

    def test_attribute_batch_rolls_back_earlier_map_when_a_shared_layout_is_refused(self):
        town = self.p.load_map("TownLab")
        room = self.p.load_map("TownLab_SmallHouse")
        plans = [(m, [(0, 0, m.layout.mid(0, 0), (m.layout.coll(0, 0), m.layout.elev(0, 0)), (0, 2))])
                 for m in (town, room)]
        with patch.object(fix_attrs, "Project", return_value=self.p), patch.object(fix_attrs, "Corpus"), \
                patch.object(fix_attrs, "propose", side_effect=plans):
            self.assertEqual(1, fix_attrs.main([town.name, room.name, "--apply"]))
        self.assert_restored()

    def test_existing_new_map_rollback_still_restores_shared_registries(self):
        real = new_map.add_script_includes

        def fail(*args):
            real(*args)
            raise OSError("injected after new map includes")

        with patch.object(new_map, "add_script_includes", side_effect=fail):
            with self.assertRaises(OSError):
                new_map.apply(self.p, "ZzSafetyNewMap", 20, 20, "MAP_ZZ_SAFETY_NEW_MAP",
                              "LAYOUT_ZZ_SAFETY_NEW_MAP", self.p.load_map("TownLab"), (2, 2), "gMapGroup_DevMaritimes")
        self.assert_restored()

    def test_transaction_rejects_paths_outside_project(self):
        with self.assertRaises(ValueError):
            with edit(self.p, ["../outside.txt"]):
                self.fail("out-of-project path accepted")
        self.assert_restored()


if __name__ == "__main__":
    unittest.main(verbosity=2)
