import unittest

from .. import logic
from ..data import (FINAL_ACTIVITIES, ITEMS, LOCATIONS, LOCATIONS_BY_ID, NONZERO, UNLOCK_FLAGS)
from ..logic import All, Any, Has, RequirementError, parse


class TestParser(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse(""), logic.NOTHING)
        self.assertEqual(parse("nothing needed"), logic.NOTHING)
        self.assertEqual(parse("Coil"), Has("Coil"))
        self.assertEqual(parse("Coil, Shift"), All((Has("Coil"), Has("Shift"))))
        self.assertEqual(parse("Coil & Shift | MAG Rope"),
                         Any((All((Has("Coil"), Has("Shift"))), Has("MAG Rope"))))
        self.assertEqual(parse("Coil & (Shift | MAG Rope)"),
                         All((Has("Coil"), Any((Has("Shift"), Has("MAG Rope"))))))

    def test_aliases_and_counts(self):
        self.assertEqual(parse("double wallrun"), Has("Progressive Wallrun", 2))
        self.assertEqual(parse("Wallrun"), Has("Progressive Wallrun", 1))
        self.assertEqual(parse("Unlocks_Coil"), Has("Coil"))
        self.assertEqual(parse("ExcludeVault"), Has("Springboard"))
        self.assertEqual(parse("Data Shard:3"), Has("Data Shard", 3))

    def test_quoted_name_with_comma(self):
        name = "Opportunity Unlock - Game Over, Runner. Game Over."
        self.assertIn(name, ITEMS)
        self.assertEqual(parse(f'"{name}" & Coil'), All((Has(name), Has("Coil"))))

    def test_errors(self):
        for bad in ("Coli", "Coil &", "(Coil", "Coil)", "| Coil", "Coil:x"):
            with self.subTest(bad=bad), self.assertRaises(RequirementError):
                parse(bad)

    def test_shipped_requirements_load(self):
        logic.load_requirements()

    def test_unknown_location_rejected(self):
        with self.assertRaises(RequirementError):
            logic.load_requirements("location,requires\nNot A Place,Coil\n")
        with self.assertRaises(RequirementError):
            logic.load_requirements("location,requires\n999,Coil\n")

    def test_rows_by_id(self):
        r = logic.load_requirements("location,requires\n1317005,Coil\n")
        self.assertEqual(r.for_location("Side Mission - Drone Works"), Has("Coil"))


class TestData(unittest.TestCase):
    def test_ids_in_ranges(self):
        for loc in LOCATIONS.values():
            if loc.category == "Dash":
                self.assertTrue(1330000 <= loc.id <= 1330999, loc.name)
            else:
                self.assertTrue(1310000 <= loc.id <= 1319999, loc.name)
        for item in ITEMS.values():
            self.assertTrue(1320000 <= item.id <= 1329999, item.name)
        self.assertEqual(len({l.id for l in LOCATIONS.values()}), len(LOCATIONS))
        self.assertEqual(len({i.id for i in ITEMS.values()}), len(ITEMS))

    def test_no_check_is_detected_on_a_flag_an_item_writes(self):
        written = {i.flag for i in ITEMS.values() if i.kind == "flag"}
        for loc in LOCATIONS.values():
            self.assertNotIn(loc.flag, written, loc.name)
            for f in loc.flags:
                self.assertNotIn(f, written, loc.name)

    def test_opportunities_with_unlocks_use_completed_time(self):
        opp = [l for l in LOCATIONS.values() if l.category == "Opportunity"]
        self.assertEqual(sum(l.rule == NONZERO for l in opp), 32)
        self.assertTrue(all(l.flag.endswith("_CompletedTime") for l in opp if l.rule == NONZERO))
        self.assertEqual(len(UNLOCK_FLAGS), 46)

    def test_every_final_activity_resolves(self):
        self.assertEqual(len(FINAL_ACTIVITIES), 46)
        for fa in FINAL_ACTIVITIES.values():
            self.assertIn(fa.item, ITEMS)
            self.assertIn(fa.location, LOCATIONS)
        self.assertEqual(LOCATIONS_BY_ID[1317009].name,
                         FINAL_ACTIVITIES["top_of_the_world"].location)
