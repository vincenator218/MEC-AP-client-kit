"""Client rules that run without the game or a server."""
import struct
import unittest

from ..client.activity_lock import M_COMPLETED, M_NAME, VT_MISSION, ActivityHideDriver
from ..client.dash_lock import (D_CONTENT_ID, D_UNLOCK_FLAG, DashesGameSession, DashLockDriver,
                                VT_SERVER_NAMED_CHALLENGE)
from ..client.game import FLAG_TABLE_PTR, LOADED_PROBE, FlagTable, ProgressionWriter
from ..client.mec_memory import djb2a
from ..client.plan import (blocked_moves, build_plan, dash_checks, dash_lock_pointers, dash_unlocked,
                           desired_flags, hidden_activities, received_names, stars_checked,
                           unlocked_dashes)
from ..data import (ACTIVITY_LOCK_FLAG, HIDE_ACTIVITIES, DASH_LOCKS, DASH_OF_LOCK_FLAG, DASHES, DASHES_BY_CONTENT_ID, DOUBLE_WALLRUN_FLAG,
                    ITEMS, PROGRESSIVE_WALLRUN_NAME, dash_location_name, dash_unlock_name)


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


# ------------------------------------------------------------------ hard dash lock
class LockFakeMem:
    """A flag table whose nodes point at flag definitions, plus one named-challenge entity and
    its data for each dash, laid out as docs/DLL.md 11e describes."""
    base = 0x140000000

    def __init__(self, flags: dict[str, int], nbuck: int = 31, missions: dict[str, str] | None = None):
        self.mem: dict[int, int] = {}
        self.writes = 0
        self.defs: dict[str, int] = {}
        self.data: dict[int, int] = {}
        self.missions: dict[str, int] = {}
        table, buckets, node_at, def_at = 0x10000, 0x20000, 0x30000, 0x80000
        self._put(self.base + FLAG_TABLE_PTR, struct.pack("<Q", table))
        self._put(table + 0x20, struct.pack("<Q", buckets))
        self._put(table + 0x28, struct.pack("<I", nbuck))
        heads: dict[int, int] = {}
        for i, (name, value) in enumerate(flags.items()):
            h, node, d = djb2a(name), node_at + i * 0x40, def_at + i * 0x40
            self._put(node, struct.pack("<I", h))
            self._put(node + 0x10, struct.pack("<Q", d))
            self._put(node + 0x18, struct.pack("<i", value))
            self._put(node + 0x28, struct.pack("<Q", heads.get(h % nbuck, 0)))
            self._put(d + 0x10, struct.pack("<I", h))
            heads[h % nbuck] = node
            self.defs[name] = d
        for b in range(nbuck):
            self._put(buckets + b * 8, struct.pack("<Q", heads.get(b, 0)))
        vt = VT_SERVER_NAMED_CHALLENGE
        for i, (cid, _flag) in enumerate(DASH_LOCKS.values()):
            ent, data = 0x200000 + i * 0x100, 0x400000 + i * 0x100
            self._put(ent, struct.pack("<Q", vt))
            self._put(ent + 0x80, struct.pack("<Q", data))
            self._put(data + D_UNLOCK_FLAG, struct.pack("<Q", 0))
            self._put(data + D_CONTENT_ID, struct.pack("<I", cid))
            self.data[cid] = data
        for i, (name, completed) in enumerate((missions or {}).items()):
            m, text = 0x600000 + i * 0x100, 0x700000 + i * 0x100
            self._put(text, name.encode("latin1") + b"\0")
            self._put(m, struct.pack("<Q", VT_MISSION))
            self._put(m + M_NAME, struct.pack("<Q", text))
            self._put(m + M_COMPLETED, struct.pack("<Q", self.defs[completed]))
            self.missions[name] = m

    def _put(self, addr, data):
        for i, b in enumerate(data):
            self.mem[addr + i] = b

    def read(self, addr, size):
        if all(addr + i in self.mem for i in range(size)):
            return bytes(self.mem[addr + i] for i in range(size))
        return None

    def read_partial(self, addr, size):
        out = bytearray()
        while len(out) < size and addr + len(out) in self.mem:
            out.append(self.mem[addr + len(out)])
        return bytes(out) or None

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

    def scan_pointers_to(self, target):
        return sorted(a for a in self.mem if a % 8 == 0 and self.read_u64(a) == target)


def lock_flags(value=0):
    out = {LOADED_PROBE: 0}
    out.update({flag: value for _cid, flag in DASH_LOCKS.values()})
    return out


class TestHardLockPlan(unittest.TestCase):
    def test_data(self):
        self.assertEqual(len(DASH_LOCKS), 22)
        self.assertEqual(len(DASH_OF_LOCK_FLAG), 22)
        self.assertEqual({cid for cid, _ in DASH_LOCKS.values()}, set(DASHES_BY_CONTENT_ID))

    def test_flags_follow_the_unlocks(self):
        have = received_names(ids(dash_unlock_name("Quite a View")))
        flags = desired_flags(have, {"hard_dash_lock": True})
        quite_a_view = DASH_LOCKS["Quite a View"][1]
        self.assertEqual(flags[quite_a_view][0], 1)
        locked = [f for f, (v, _r) in flags.items() if f in DASH_OF_LOCK_FLAG and v == 0]
        self.assertEqual(len(locked), 21)

    def test_off_means_no_lock_flags_and_no_pointers(self):
        flags = desired_flags(received_names([]), {"hard_dash_lock": False})
        self.assertFalse(set(flags) & set(DASH_OF_LOCK_FLAG))
        self.assertIsNone(dash_lock_pointers({}))
        self.assertIsNone(build_plan([], {}, {"hard_dash_lock": False}, True).dash_locks)

    def test_pointers_only_when_writes_allowed(self):
        self.assertEqual(len(dash_lock_pointers({"hard_dash_lock": True})), 22)
        self.assertIsNone(build_plan([], {}, {"hard_dash_lock": True}, False).dash_locks)
        self.assertEqual(len(build_plan([], {}, {"hard_dash_lock": True}, True).dash_locks), 22)


class TestDashLockDriver(unittest.TestCase):
    def setUp(self):
        self.mem = LockFakeMem(lock_flags())
        self.driver = DashLockDriver(self.mem, FlagTable(self.mem))
        self.wanted = dash_lock_pointers({"hard_dash_lock": True})

    def pointer(self, dash):
        return self.mem.read_u64(self.mem.data[DASH_LOCKS[dash][0]] + D_UNLOCK_FLAG)

    def test_writes_each_pointer_once(self):
        s = self.driver.ensure(self.wanted)
        self.assertEqual((s.locked, s.written, s.missing, s.foreign), (22, 22, [], []))
        self.assertEqual(self.pointer("Caleb's Run"), self.mem.defs[DASH_LOCKS["Caleb's Run"][1]])
        n = self.mem.writes
        s = self.driver.ensure(self.wanted)
        self.assertEqual((s.locked, s.written), (22, 0))
        self.assertEqual(self.mem.writes, n)

    def test_someone_elses_pointer_is_left_alone(self):
        cid = DASH_LOCKS["Old Tunnels"][0]
        self.mem._put(self.mem.data[cid] + D_UNLOCK_FLAG, struct.pack("<Q", 0xABCDEF0))
        s = self.driver.ensure(self.wanted)
        self.assertEqual(s.foreign, [cid])
        self.assertEqual(self.pointer("Old Tunnels"), 0xABCDEF0)
        self.driver.release()
        self.assertEqual(self.pointer("Old Tunnels"), 0xABCDEF0)
        self.assertEqual(self.pointer("Caleb's Run"), 0)

    def test_moved_data_is_not_written(self):
        self.driver.ensure(self.wanted)
        cid = DASH_LOCKS["Birdman's Dash"][0]
        self.mem._put(self.mem.data[cid] + D_CONTENT_ID, struct.pack("<I", 0x1234))   # recycled
        s = self.driver.ensure(self.wanted)
        self.assertIn(cid, s.missing)
        self.assertEqual(s.locked, 21)

    def test_session_writes_flags_and_pointers(self):
        s = DashesGameSession()
        s.mem, s.table = self.mem, FlagTable(self.mem)
        s.writer = ProgressionWriter(s.table)
        s.locks = DashLockDriver(self.mem, s.table)
        s.ensure_attached = lambda: True
        s._build_checked = True
        slot = {"hard_dash_lock": True}
        quite_a_view = DASH_LOCKS["Quite a View"][1]
        plan = build_plan(ids(dash_unlock_name("Quite a View")), {}, slot, True)
        plan.blocked = None                                              # no movement volume here
        written = []
        for _ in range(3):                                               # settle, then write
            written += s.tick(plan).flags_written
        self.assertEqual(written, [quite_a_view])                        # the other 21 are 0 already
        self.assertEqual(s.table.read(quite_a_view), 1)
        self.assertEqual(s.table.read(DASH_LOCKS["Caleb's Run"][1]), 0)
        self.assertEqual(s.locks.state.locked, 22)
        self.mem.attached = True
        self.mem.detach = lambda: None
        s.moves.release = lambda: 0
        s.shutdown()
        self.assertEqual(self.pointer("Caleb's Run"), 0)


class TestHideActivities(unittest.TestCase):
    MISSIONS = {"OW Opp DtPh2 02": "MiscCompleted_OW Opp DtPh2 02",
                "Exit Strategy": "SilverCompleted_Exit Strategy",
                "Security Hub Downtown 1": "BronzeCompleted_Security Hub Downtown 1"}

    def setUp(self):
        flags = {LOADED_PROBE: 0, ACTIVITY_LOCK_FLAG: 1, **{f: 0 for f in self.MISSIONS.values()}}
        self.mem = LockFakeMem(flags, missions=self.MISSIONS)
        self.driver = ActivityHideDriver(self.mem, FlagTable(self.mem))

    def completed(self, name):
        return self.mem.read_u64(self.mem.missions[name] + M_COMPLETED)

    def test_plan(self):
        self.assertEqual(len(HIDE_ACTIVITIES), 92)
        self.assertEqual(HIDE_ACTIVITIES["Exit Strategy"], "SilverCompleted_Exit Strategy")
        self.assertNotIn("The Shard", HIDE_ACTIVITIES)                   # story stays
        on = {"hide_other_activities": True}
        self.assertEqual(desired_flags(received_names([]), on)[ACTIVITY_LOCK_FLAG][0], 1)
        self.assertNotIn(ACTIVITY_LOCK_FLAG, desired_flags(received_names([]), {}))
        self.assertIsNone(hidden_activities({}))
        self.assertEqual(build_plan([], {}, on, True).hide_activities, HIDE_ACTIVITIES)
        self.assertIsNone(build_plan([], {}, on, False).hide_activities)

    def test_hide_and_put_back(self):
        s = self.driver.ensure(self.MISSIONS, ACTIVITY_LOCK_FLAG)
        self.assertEqual((s.hidden, s.written, s.missing), (3, 3, []))
        self.assertEqual(self.completed("Exit Strategy"), self.mem.defs[ACTIVITY_LOCK_FLAG])
        n = self.mem.writes
        self.assertEqual(self.driver.ensure(self.MISSIONS, ACTIVITY_LOCK_FLAG).written, 0)
        self.assertEqual(self.mem.writes, n)
        self.assertEqual(self.driver.release(ACTIVITY_LOCK_FLAG), 3)
        self.assertEqual(self.completed("Exit Strategy"), self.mem.defs["SilverCompleted_Exit Strategy"])

    def test_pointer_that_is_not_its_own_flag_is_left_alone(self):
        m = self.mem.missions["Exit Strategy"]
        self.mem._put(m + M_COMPLETED, struct.pack("<Q", 0xABCDEF0))
        s = self.driver.ensure(self.MISSIONS, ACTIVITY_LOCK_FLAG)
        self.assertEqual(s.missing, ["Exit Strategy"])
        self.assertEqual(self.completed("Exit Strategy"), 0xABCDEF0)

    def test_release_after_a_client_restart(self):
        self.driver.ensure(self.MISSIONS, ACTIVITY_LOCK_FLAG)
        fresh = ActivityHideDriver(self.mem, FlagTable(self.mem))      # a new client, same game
        self.assertEqual(fresh.ensure(self.MISSIONS, ACTIVITY_LOCK_FLAG).written, 0)
        self.assertEqual(fresh.release(ACTIVITY_LOCK_FLAG), 3)
        self.assertEqual(self.completed("OW Opp DtPh2 02"), self.mem.defs["MiscCompleted_OW Opp DtPh2 02"])
