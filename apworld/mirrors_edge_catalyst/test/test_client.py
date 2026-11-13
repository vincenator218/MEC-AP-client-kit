"""Client logic that runs without the game: plans, detection, and the flag table on fake memory."""
import struct
import unittest

from ..client.game import FLAG_TABLE_PTR, FlagTable, Plan, ProgressionWriter
from ..client.mec_memory import djb2a
from ..client.plan import blocked_moves, build_plan, desired_flags, location_check, received_names
from ..data import (DOUBLE_WALLRUN_FLAG, ITEMS, LOCATIONS, MACGUFFIN_NAME,
                    PROGRESSIVE_WALLRUN_NAME, gridleak_location_name)


def ids(*names):
    return [ITEMS[n].id for n in names]


SLOT = {"final_unlock_item": "Side Mission Unlock - Top of the World",
        "data_shards_required": 2, "revert_skill_tree_purchases": False}


class TestPlan(unittest.TestCase):
    def test_flags_for_items(self):
        have = received_names(ids("Coil", "Side Mission Unlock - Drone Works"))
        flags = desired_flags(have, SLOT)
        self.assertEqual(flags["Unlocks_Coil"][0], 1)
        self.assertEqual(flags["SilverCompleted_Drone Works"][0], 1)
        self.assertNotIn("SilverCompleted_Top of the World", flags)
        self.assertNotIn(DOUBLE_WALLRUN_FLAG, flags)
        self.assertEqual(len(flags), 2)          # nothing it was not asked for

    def test_progressive_wallrun(self):
        one = received_names(ids(PROGRESSIVE_WALLRUN_NAME))
        two = received_names(ids(PROGRESSIVE_WALLRUN_NAME) * 2)
        self.assertFalse(blocked_moves(one)["wallrun"])
        self.assertNotIn(DOUBLE_WALLRUN_FLAG, desired_flags(one, SLOT))
        self.assertEqual(desired_flags(two, SLOT)[DOUBLE_WALLRUN_FLAG][0], 1)

    def test_shards_unlock_final(self):
        have = received_names(ids(MACGUFFIN_NAME) * 2)
        self.assertEqual(desired_flags(have, SLOT)["SilverCompleted_Top of the World"][0], 1)

    def test_revert(self):
        have = received_names(ids("Coil"))
        flags = desired_flags(have, dict(SLOT, revert_skill_tree_purchases=True))
        self.assertEqual(flags["Unlocks_Coil"][0], 1)
        self.assertEqual(flags["Unlocks_Shift"][0], 0)
        self.assertEqual(flags[DOUBLE_WALLRUN_FLAG][0], 0)
        self.assertNotIn("SilverCompleted_Drone Works", flags)   # revert is abilities only

    def test_blocked_moves(self):
        b = blocked_moves(received_names([]))
        self.assertTrue(all(b.values()))
        b = blocked_moves(received_names(ids("MAG Rope", "Springboard")))
        self.assertEqual({m for m, v in b.items() if not v}, {"mag_rope", "springboard"})

    def test_no_writes_until_allowed(self):
        p = build_plan(ids("Coil"), {}, SLOT, None, writes_allowed=False)
        self.assertEqual(p.flags, {})
        self.assertIsNone(p.blocked)


class TestDetection(unittest.TestCase):
    def test_rules(self):
        values = {}
        read = values.get
        sm = location_check(LOCATIONS["Side Mission - Drone Works"])
        self.assertFalse(sm(read))
        values["Drone Works_CompletedTime"] = 81234
        self.assertTrue(sm(read))

        opp = location_check(LOCATIONS["Opportunity - Stay Out of Sight"])
        values["MiscCompleted_OW Opp DtPh2 04"] = 1          # what the unlock item writes
        self.assertFalse(opp(read))
        values["OW Opp DtPh2 04_CompletedTime"] = 5000
        self.assertTrue(opp(read))

    def test_gridleak_count(self):
        loc = LOCATIONS[gridleak_location_name("Anchor", 3)]
        values = {f: 1 for f in loc.flags[:2]}
        check = location_check(loc)
        self.assertFalse(check(values.get))
        values[loc.flags[10]] = 1
        self.assertTrue(check(values.get))


class FakeMem:
    """A tiny address space with a flag table laid out as MEMORY.md §2 describes."""
    base = 0x140000000

    def __init__(self, flags: dict[str, int], nbuck: int = 31):
        self.mem: dict[int, int] = {}          # byte address -> byte
        self.writes = 0
        table, buckets, node_at = 0x10000, 0x20000, 0x30000
        self._put(self.base + FLAG_TABLE_PTR, struct.pack("<Q", table))
        self._put(table + 0x20, struct.pack("<Q", buckets))
        self._put(table + 0x28, struct.pack("<I", nbuck))
        heads: dict[int, int] = {}
        for i, (name, value) in enumerate(flags.items()):
            h = djb2a(name)
            node = node_at + i * 0x40
            self._put(node, struct.pack("<I", h))
            self._put(node + 0x18, struct.pack("<i", value))
            self._put(node + 0x28, struct.pack("<Q", heads.get(h % nbuck, 0)))
            heads[h % nbuck] = node
        for b in range(nbuck):
            self._put(buckets + b * 8, struct.pack("<Q", heads.get(b, 0)))

    def _put(self, addr, data):
        for i, b in enumerate(data):
            self.mem[addr + i] = b

    def read(self, addr, size):
        if all(addr + i in self.mem for i in range(size)):
            return bytes(self.mem[addr + i] for i in range(size))
        return None

    def read_u64(self, a):
        b = self.read(a, 8)
        return struct.unpack("<Q", b)[0] if b else None

    def read_u32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def write(self, addr, data):
        self.writes += 1
        self._put(addr, data)
        return True


class TestFlagTable(unittest.TestCase):
    def setUp(self):
        self.mem = FakeMem({"Unlocks_Coil": 0, "Unlocks_Shift": 1, "Drone Works_CompletedTime": 0,
                            "SilverCompleted_Drone Works": 0})
        self.table = FlagTable(self.mem)

    def test_read(self):
        self.assertTrue(self.table.loaded())
        self.assertEqual(self.table.read("Unlocks_Shift"), 1)
        self.assertEqual(self.table.read("Unlocks_Coil"), 0)
        self.assertIsNone(self.table.read("Not_A_Flag"))

    def test_write_is_verified_and_idempotent(self):
        w = ProgressionWriter(self.table)
        self.assertTrue(w.set_flag_for_item("Unlocks_Coil", 1, "test"))
        self.assertEqual(self.table.read("Unlocks_Coil"), 1)
        n = self.mem.writes
        self.assertTrue(w.set_flag_for_item("Unlocks_Coil", 1, "test"))
        self.assertEqual(self.mem.writes, n)                      # already right: no write
        self.assertFalse(w.set_flag_for_item("Not_A_Flag", 1, "test"))

    def test_write_that_does_not_stick_is_reported(self):
        self.mem.write = lambda addr, data: True                  # claims success, does nothing
        self.assertFalse(ProgressionWriter(self.table).set_flag_for_item("Unlocks_Coil", 1, "t"))

    def test_stale_node_is_rewalked(self):
        self.table.read("Unlocks_Coil")
        node = self.table._nodes[djb2a("Unlocks_Coil")]
        self.mem._put(node, struct.pack("<I", 0xDEADBEEF))       # address recycled
        self.assertIsNone(self.table.read("Unlocks_Coil"))

    def test_session_tick_writes_only_when_allowed(self):
        from ..client.game import GameSession
        s = GameSession()
        s.mem, s.table = self.mem, self.table
        s.writer = ProgressionWriter(self.table)
        s.ensure_attached = lambda: True
        s._build_checked = True                                  # FakeMem has no type info
        plan = Plan(watch={1317005: location_check(LOCATIONS["Side Mission - Drone Works"])},
                    flags={"Unlocks_Coil": (1, "t")}, writes_allowed=False)
        r = s.tick(plan)
        self.assertTrue(r.loaded and r.just_loaded)
        self.assertEqual(self.table.read("Unlocks_Coil"), 0)
        plan.writes_allowed = True
        r = s.tick(plan)
        self.assertEqual(r.flags_written, ["Unlocks_Coil"])
        self.assertEqual(r.reasons, {"Unlocks_Coil": "t"})
        self.assertFalse(r.just_loaded)
        self.assertEqual(r.detected, set())

    def test_no_write_on_the_first_tick_after_a_load(self):
        from ..client.game import GameSession
        s = GameSession()
        s.mem, s.table = self.mem, self.table
        s.writer = ProgressionWriter(self.table)
        s.ensure_attached = lambda: True
        s._build_checked = True
        plan = Plan(flags={"Unlocks_Coil": (1, "t")}, writes_allowed=True)
        r = s.tick(plan)
        self.assertTrue(r.just_loaded)
        self.assertEqual(r.flags_written, [])                    # table may still be filling
        self.assertEqual(s.tick(plan).flags_written, ["Unlocks_Coil"])
