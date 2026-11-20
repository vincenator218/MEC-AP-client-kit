from ..data import (ABILITY_ITEMS, DASH_UNLOCKS, DASHES, GRIDLEAKS_BY_DISTRICT, ITEMS, LOCATIONS,
                    PROGRESSIVE_WALLRUN_NAME, TRAVERSAL_ITEMS, dash_location_name, dash_unlock_name,
                    gridleak_location_name, gridleak_steps)
from . import MECDTestBase


class TestData(MECDTestBase):
    def test_no_activity_items(self):
        for name, info in ITEMS.items():
            self.assertFalse(name.startswith(("Side Mission Unlock", "Opportunity Unlock")), name)
        self.assertEqual(len(DASH_UNLOCKS), 22)
        self.assertEqual(len(ABILITY_ITEMS), 35)          # 36 abilities; Double Wallrun is Progressive Wallrun #2
        self.assertEqual(len(TRAVERSAL_ITEMS), 5)         # 4 moves + Progressive Wallrun

    def test_ids_unique(self):
        self.assertEqual(len({i.id for i in ITEMS.values()}), len(ITEMS))
        self.assertEqual(len({l.id for l in LOCATIONS.values()}), len(LOCATIONS))

    def test_gridleak_steps_stop_below_the_total(self):
        self.assertEqual(gridleak_steps(87, 10), [10, 20, 30, 40, 50, 60, 70, 80])
        self.assertEqual(gridleak_steps(80, 10), [10, 20, 30, 40, 50, 60, 70])   # never all 80
        self.assertEqual(gridleak_steps(74, 10), [10, 20, 30, 40, 50, 60, 70])
        self.assertEqual(gridleak_steps(80, 5)[-1], 75)
        self.assertEqual(gridleak_steps(80, 0), [])

    def test_gridleak_percent(self):
        self.assertEqual(gridleak_steps(87, 10, 60), [10, 20, 30, 40, 50])
        self.assertEqual(gridleak_steps(80, 10, 60), [10, 20, 30, 40])
        self.assertEqual(gridleak_steps(74, 10, 60), [10, 20, 30, 40])
        self.assertEqual(gridleak_steps(80, 10, 99), [10, 20, 30, 40, 50, 60, 70])  # never all 80
        self.assertEqual(gridleak_steps(15, 5, 70), [5, 10])


class TestDefaults(MECDTestBase):
    def test_location_count(self):
        world = self.multiworld.worlds[self.player]
        # 22 dashes x (finish + 3 stars) + GridLeaks every 10, up to 60% of each district
        leaks = sum(len(gridleak_steps(len(v), 10, 60)) for v in GRIDLEAKS_BY_DISTRICT.values())
        self.assertEqual(leaks, 5 + 4 + 4 + 4)
        self.assertEqual(len(world.location_names), 88 + leaks)
        self.assertIn(gridleak_location_name("Downtown", 50), world.location_names)
        self.assertNotIn(gridleak_location_name("Downtown", 60), world.location_names)

    def test_starting_dashes(self):
        world = self.multiworld.worlds[self.player]
        self.assertEqual(len(world.starting_dashes), 3)
        start = {i.name for i in self.multiworld.precollected_items[self.player]}
        pool = [i.name for i in self.multiworld.itempool]
        for name in world.starting_dashes:
            self.assertIn(name, start)
            self.assertNotIn(name, pool)
        self.assertEqual(sum(n in pool for n in DASH_UNLOCKS), 19)

    def test_dash_needs_its_unlock(self):
        world = self.multiworld.worlds[self.player]
        locked = next(n for n in DASH_UNLOCKS if n not in world.starting_dashes)
        dash = ITEMS[locked].dash
        self.collect_all_but(locked)
        for tier in range(4):
            self.assertFalse(self.can_reach_location(dash_location_name(dash, tier)))
        self.collect_by_name(locked)
        for tier in range(4):
            self.assertTrue(self.can_reach_location(dash_location_name(dash, tier)))

    def test_goal_counts_stars(self):
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.stars_required, 40)
        self.assertEqual(len(world.star_locations), 66)

    def test_moves_in_pool(self):
        pool = [i.name for i in self.multiworld.itempool]
        self.assertEqual(pool.count(PROGRESSIVE_WALLRUN_NAME), 2)
        for name in ("Springboard", "Climb Up", "Ledge Hang", "MAG Rope"):
            self.assertIn(name, pool)


class TestRequirements(MECDTestBase):
    def test_calebs_run_needs_mag_rope(self):
        world = self.multiworld.worlds[self.player]
        unlock = dash_unlock_name("Caleb's Run")
        if unlock not in world.starting_dashes:
            self.collect_by_name(unlock)
        self.collect_all_but("MAG Rope")
        for tier in range(4):                    # the stars inherit the finish's row
            self.assertFalse(self.can_reach_location(dash_location_name("Caleb's Run", tier)))
        self.collect_by_name("MAG Rope")
        self.assertTrue(self.can_reach_location(dash_location_name("Caleb's Run", 3)))

    def test_a_starting_dash_needs_nothing(self):
        world = self.multiworld.worlds[self.player]
        for _ in range(50):
            self.assertNotEqual(world._pick_starting_dashes(1), [dash_unlock_name("Caleb's Run")])


class TestSmall(MECDTestBase):
    """Few locations: useful abilities go to the start inventory, progression still fits."""
    options = {"dash_stars": 1, "gridleak_bundle_size": 0, "stars_required": 66, "starting_dashes": 1}

    def test_fits(self):
        world = self.multiworld.worlds[self.player]
        self.assertEqual(len(world.location_names), 44)
        self.assertEqual(world.stars_required, 22)        # capped at the 22 one-star checks
        pool = [i.name for i in self.multiworld.itempool]
        self.assertEqual(len(pool), 44)
        for name in DASH_UNLOCKS:
            self.assertTrue(name in pool or name in world.starting_dashes, name)


class TestStartWithMoves(MECDTestBase):
    options = {"traversal_items": "start_with"}

    def test_moves_precollected(self):
        start = [i.name for i in self.multiworld.precollected_items[self.player]]
        pool = [i.name for i in self.multiworld.itempool]
        self.assertEqual(start.count(PROGRESSIVE_WALLRUN_NAME), 2)
        for name in TRAVERSAL_ITEMS:
            self.assertNotIn(name, pool)
