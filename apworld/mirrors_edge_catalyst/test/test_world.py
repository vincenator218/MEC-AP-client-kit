from unittest import mock

from .. import logic
from ..data import (FILLER_NAME, GRIDLEAKS_BY_DISTRICT, ITEMS, LOCATIONS, MACGUFFIN_NAME,
                    PROGRESSIVE_WALLRUN_NAME, TRAVERSAL_ITEMS, gridleak_location_name)
from . import MECTestBase


class TestDefaults(MECTestBase):
    def test_location_count(self):
        # 12 side missions + 40 opportunities - the final activity + 66 GridLeak bundles of 5
        world = self.multiworld.worlds[self.player]
        self.assertEqual(len(world.location_names), 12 + 40 - 1 + 18 + 17 + 16 + 15)

    def test_final_activity_is_not_a_check(self):
        world = self.multiworld.worlds[self.player]
        self.assertNotIn(world.final.location, world.location_names)
        pool = {i.name for i in self.multiworld.itempool}
        self.assertNotIn(world.final.item, pool)

    def test_shards_gate_the_goal(self):
        world = self.multiworld.worlds[self.player]
        self.collect_all_but(MACGUFFIN_NAME)
        self.assertFalse(self.can_reach_location(world.goal_location.name))
        self.collect(self.get_items_by_name(MACGUFFIN_NAME)[:world.shards_required])
        self.assertTrue(self.can_reach_location(world.goal_location.name))

    def test_last_partial_bundle_exists(self):
        # Downtown has 87 leaks: 5, 10, ..., 85, then 87
        self.assertIn(gridleak_location_name("Downtown", 87),
                      self.multiworld.worlds[self.player].location_names)

    def test_progressive_wallrun_has_two_copies(self):
        pool = [i.name for i in self.multiworld.itempool]
        self.assertEqual(pool.count(PROGRESSIVE_WALLRUN_NAME), 2)
        self.assertNotIn("Wallrun", ITEMS)
        self.assertNotIn("DoubleWallrun", ITEMS)


class TestActivitiesOnly(MECTestBase):
    """52 locations for ~107 items: the useful overflow goes to start inventory."""
    options = {"gridleak_bundle_size": 0}

    def test_overflow_is_precollected_not_lost(self):
        world = self.multiworld.worlds[self.player]
        pool = [i for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(len(pool), len(world.location_names))
        pre = [i.name for i in self.multiworld.precollected_items[self.player]]
        self.assertTrue(pre)
        self.assertTrue(all(not ITEMS[n].kind.startswith("macguffin") for n in pre))
        for name in TRAVERSAL_ITEMS + [MACGUFFIN_NAME]:
            self.assertNotIn(name, pre)


class TestTooFewLocations(MECTestBase):
    options = {"gridleak_bundle_size": 0, "side_missions": False, "opportunities": False,
               "billboards": True, "data_shards_total": 20}
    auto_construct = False

    def test_raises(self):
        from Options import OptionError
        with self.assertRaises(OptionError):
            self.world_setup()


class TestEverything(MECTestBase):
    options = {"gridleak_bundle_size": 1, "countdown_deliveries": True, "security_hubs": True,
               "grid_nodes": True, "billboards": True, "electronic_parts": True,
               "surveillance_recordings": True, "documents": True, "secret_bags": True,
               "dashes": True, "dash_stars": 3,
               "data_shards_total": 100, "data_shards_required": 100}

    def test_count(self):
        self.assertEqual(len(self.multiworld.worlds[self.player].location_names),
                         len(LOCATIONS) - 1)

    def test_filler_present(self):
        self.assertIn(FILLER_NAME, {i.name for i in self.multiworld.itempool})


class TestStartWithTraversal(MECTestBase):
    options = {"traversal_items": "start_with"}

    def test_precollected(self):
        pre = [i.name for i in self.multiworld.precollected_items[self.player]]
        for name in TRAVERSAL_ITEMS:
            self.assertEqual(pre.count(name), ITEMS[name].count)
        self.assertFalse(set(TRAVERSAL_ITEMS) & {i.name for i in self.multiworld.itempool})


class TestGridNodeFinal(MECTestBase):
    options = {"final_activity": "grid_node_downtown", "grid_nodes": True}

    def test_final(self):
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.final.location, "Grid Node - Downtown")
        self.assertNotIn("Grid Node - Downtown", world.location_names)


class TestOpportunityFinal(MECTestBase):
    options = {"final_activity": "stay_out_of_sight", "data_shards_required": 50,
               "data_shards_total": 10}

    def test_required_capped(self):
        self.assertEqual(self.multiworld.worlds[self.player].shards_required, 10)


_REQS = """location,requires,source,notes
Side Mission - Drone Works,"Wallrun & (Climb Up | Ledge Hang)",test,
category:Opportunity,MAG Rope,test,
Opportunity - Stay Out of Sight,nothing,test,
GridLeak - Downtown 001,Double Wallrun,test,
GridLeak - Downtown 002,Double Wallrun,test,
"""


class TestDataDrivenRules(MECTestBase):
    options = {"final_activity": "top_of_the_world"}

    def world_setup(self, *args, **kwargs):
        reqs = logic.load_requirements(_REQS)
        with mock.patch.object(logic, "load_requirements", return_value=reqs):
            super().world_setup(*args, **kwargs)

    def test_and_or(self):
        name = "Side Mission - Drone Works"
        self.assertFalse(self.can_reach_location(name))
        self.collect_by_name(["Ledge Hang"])
        self.assertFalse(self.can_reach_location(name))
        self.collect(self.get_item_by_name(PROGRESSIVE_WALLRUN_NAME))
        self.assertTrue(self.can_reach_location(name))

    def test_category_default_and_override(self):
        self.assertFalse(self.can_reach_location("Opportunity - Memento"))
        self.assertTrue(self.can_reach_location("Opportunity - Stay Out of Sight"))
        self.collect_by_name(["MAG Rope"])
        self.assertTrue(self.can_reach_location("Opportunity - Memento"))

    def test_gridleak_counts_use_per_leak_rules(self):
        total = len(GRIDLEAKS_BY_DISTRICT["Downtown"])
        last = gridleak_location_name("Downtown", total)
        self.assertTrue(self.can_reach_location(gridleak_location_name("Downtown", 85)))
        self.assertFalse(self.can_reach_location(last))
        self.collect(self.get_items_by_name(PROGRESSIVE_WALLRUN_NAME))
        self.assertTrue(self.can_reach_location(last))

    def test_rule_items_are_progression(self):
        world = self.multiworld.worlds[self.player]
        self.assertIn("MAG Rope", world.logic_items)
        self.assertTrue(world.create_item("MAG Rope").advancement)
        self.assertFalse(world.create_item("Coil").advancement)
