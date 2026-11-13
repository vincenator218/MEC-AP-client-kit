"""Client rules that run without the game or a server."""
import unittest

from ..client.plan import (blocked_moves, dash_checks, dash_unlocked, desired_flags, received_names,
                           stars_checked, unlocked_dashes)
from ..data import (DASHES, DASHES_BY_CONTENT_ID, DOUBLE_WALLRUN_FLAG, ITEMS, PROGRESSIVE_WALLRUN_NAME,
                    dash_location_name, dash_unlock_name)


def ids(*names):
    return [ITEMS[n].id for n in names]


class TestDashRules(unittest.TestCase):
    def setUp(self):
        self.loc = DASHES[dash_location_name("Quite a View")]
        self.cid = self.loc.content_id

    def test_soft_lock(self):
        have = received_names(ids(dash_unlock_name("Quite a View")))
        self.assertTrue(dash_unlocked(have, "Quite a View"))
        self.assertFalse(dash_unlocked(have, "Too Close to the Sun"))
        self.assertEqual(unlocked_dashes(have), ["Quite a View"])

    def test_stars_from_time(self):
        stars = {l.tier: l for l in DASHES_BY_CONTENT_ID[self.cid]}
        slow = stars[1].max_cs + 1
        self.assertEqual(dash_checks(self.cid, slow), {stars[0].id})
        self.assertEqual(dash_checks(self.cid, stars[2].max_cs), {stars[0].id, stars[1].id, stars[2].id})
        self.assertEqual(len(dash_checks(self.cid, 1)), 4)
        self.assertEqual(dash_checks(0x12345678, 100), set())   # not a dash

    def test_stars_checked_counts_only_stars(self):
        stars = {l.tier: l.id for l in DASHES_BY_CONTENT_ID[self.cid]}
        self.assertEqual(stars_checked({stars[0], stars[1], stars[3], 999}), 2)


class TestGrants(unittest.TestCase):
    def test_abilities_and_double_wallrun(self):
        have = received_names(ids("Coil", PROGRESSIVE_WALLRUN_NAME, PROGRESSIVE_WALLRUN_NAME,
                                  dash_unlock_name("Quite a View")))
        flags = desired_flags(have, {"revert_skill_tree_purchases": False})
        self.assertEqual(flags, {"Unlocks_Coil": (1, "received Coil"),
                                 DOUBLE_WALLRUN_FLAG: (1, f"received {PROGRESSIVE_WALLRUN_NAME} x2")})

    def test_revert(self):
        flags = desired_flags(received_names([]), {"revert_skill_tree_purchases": True})
        self.assertEqual(flags["Unlocks_Coil"][0], 0)
        self.assertEqual(flags[DOUBLE_WALLRUN_FLAG][0], 0)

    def test_moves(self):
        self.assertTrue(all(blocked_moves(received_names([])).values()))
        free = blocked_moves(received_names(ids("Springboard", PROGRESSIVE_WALLRUN_NAME)))
        self.assertFalse(free["springboard"])
        self.assertFalse(free["wallrun"])
        self.assertTrue(free["mag_rope"])
