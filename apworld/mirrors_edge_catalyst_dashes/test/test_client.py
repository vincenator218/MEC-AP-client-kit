"""Client rules that run without the game or a server."""
import asyncio
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
        cid = DASH_LOCKS["Birdman's Route"][0]
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


class TestLauncher(unittest.TestCase):
    def test_folder_without_the_dll_is_refused(self):
        import tempfile
        from ..client.launcher import set_dll_folder
        with tempfile.TemporaryDirectory() as d:
            err = set_dll_folder(d)
            self.assertIn("mec_ap_inject.exe", err)
            self.assertIn("mec_ap.dll", err)


# ------------------------------------------------------------------ /move overrides
class TestMoveOverrides(unittest.TestCase):
    def test_find_move(self):
        from ..client.plan import find_move
        self.assertEqual(find_move("springboard"), ("Springboard", []))
        self.assertEqual(find_move("mag rope"), ("MAG Rope", []))
        self.assertEqual(find_move("wallrun"), (PROGRESSIVE_WALLRUN_NAME, []))
        self.assertEqual(find_move("coil"), ("Coil", []))
        name, cands = find_move("Focus")
        self.assertEqual(name, "Focus")                      # exact beats the Focus_* prefixes
        name, cands = find_move("IncreasedHealth")
        self.assertIsNone(name)
        self.assertEqual(len(cands), 5)
        self.assertEqual(find_move(dash_unlock_name("Quite a View")), (None, []))   # not a move

    def test_on_gives_a_move_not_received(self):
        plan = build_plan([], {}, {}, True, {"Coil": 1, "Springboard": 1})
        self.assertEqual(plan.flags["Unlocks_Coil"], (1, "/move Coil on"))
        self.assertFalse(plan.blocked["springboard"])
        self.assertTrue(plan.blocked["climb_up"])

    def test_off_takes_a_received_move_away(self):
        plan = build_plan(ids("Coil", "Springboard"), {}, {}, True, {"Coil": 0, "Springboard": 0})
        self.assertEqual(plan.flags["Unlocks_Coil"], (0, "/move Coil off"))
        self.assertTrue(plan.blocked["springboard"])

    def test_wallrun_levels(self):
        one = build_plan([], {}, {}, True, {PROGRESSIVE_WALLRUN_NAME: 1})
        self.assertFalse(one.blocked["wallrun"])
        self.assertEqual(one.flags[DOUBLE_WALLRUN_FLAG][0], 0)
        two = build_plan([], {}, {}, True, {PROGRESSIVE_WALLRUN_NAME: 2})
        self.assertEqual(two.flags[DOUBLE_WALLRUN_FLAG][0], 1)
        none = build_plan(ids(PROGRESSIVE_WALLRUN_NAME, PROGRESSIVE_WALLRUN_NAME), {}, {}, True,
                          {PROGRESSIVE_WALLRUN_NAME: 0})
        self.assertTrue(none.blocked["wallrun"])
        self.assertEqual(none.flags[DOUBLE_WALLRUN_FLAG][0], 0)

    def test_removed_override_writes_the_flag_back(self):
        flags = desired_flags(received_names([]), {}, {}, touched={"Coil"})
        self.assertEqual(flags["Unlocks_Coil"][0], 0)
        held = desired_flags(received_names(ids("Coil")), {}, {}, touched={"Coil"})
        self.assertEqual(held["Unlocks_Coil"], (1, "received Coil"))

    def test_no_writes_before_the_save_is_checked(self):
        plan = build_plan([], {}, {}, False, {"Coil": 1})
        self.assertEqual(plan.flags, {})
        self.assertIsNone(plan.blocked)

    def test_overrides_never_touch_dash_locks(self):
        slot = {"hard_dash_lock": True}
        plan = build_plan([], {}, slot, True, {"Coil": 1})
        self.assertTrue(all(plan.flags[f][0] == 0 for f in DASH_OF_LOCK_FLAG))


class TestMoveCommands(unittest.IsolatedAsyncioTestCase):
    """The client's /move handling, with Archipelago's persistent storage faked."""

    async def asyncSetUp(self):
        from unittest import mock
        import Utils
        from ..client.client import MECDContext
        self.store = {}
        patches = [mock.patch.object(Utils, "persistent_load", lambda: self.store),
                   mock.patch.object(Utils, "persistent_store",
                                     lambda c, k, v: self.store.setdefault(c, {}).__setitem__(k, v))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.ctx = MECDContext(None, None)
        self.ctx.slot_data, self.ctx.seed_name, self.ctx.slot = {}, "S1", 1

    async def asyncTearDown(self):
        await self.ctx.shutdown()

    def test_set_saved_and_reset(self):
        c = self.ctx
        self.assertTrue(c.set_override("coil", "on"))
        self.assertTrue(c.set_override("wallrun", "2"))
        self.assertFalse(c.set_override("springboard", "2"))           # only on/off
        self.assertFalse(c.set_override("nothing at all", "on"))
        self.assertEqual(c.overrides, {"Coil": 1, PROGRESSIVE_WALLRUN_NAME: 2})
        saved = self.store["mec_ap"]["move_overrides"]["S1:1"]
        self.assertEqual(saved["levels"], {"Coil": 1, PROGRESSIVE_WALLRUN_NAME: 2})
        c.overrides = {}
        c.load_overrides()                                               # a client restart
        self.assertEqual(c.overrides, {"Coil": 1, PROGRESSIVE_WALLRUN_NAME: 2})
        self.assertTrue(c.reset_overrides())
        self.assertEqual(c.overrides, {})
        # Coil and the double wallrun were raised and are not held: hold them at 0 until written
        self.assertEqual(c.touched, {"Coil", PROGRESSIVE_WALLRUN_NAME})
        c.forget_touched("Unlocks_Coil", "not received (manual override removed)")
        self.assertEqual(c.touched, {PROGRESSIVE_WALLRUN_NAME})

    def test_off_then_ap_leaves_nothing_to_undo(self):
        c = self.ctx
        c.set_override("Springboard", "off")
        c.set_override("Coil", "off")
        c.set_override("Springboard", "ap")
        c.set_override("Coil", "ap")
        self.assertEqual((c.overrides, c.touched), ({}, set()))
        self.assertNotIn("S1:1", self.store["mec_ap"]["move_overrides"])

    def test_kept_per_slot(self):
        c = self.ctx
        c.set_override("Coil", "on")
        c.slot = 2
        c.load_overrides()
        self.assertEqual(c.overrides, {})

    def test_needs_a_slot(self):
        self.ctx.slot_data = None
        self.assertFalse(self.ctx.set_override("Coil", "on"))


class TestDllFolderCommand(unittest.IsolatedAsyncioTestCase):
    async def test_backslashes_and_spaces_survive(self):
        import os
        import tempfile
        from unittest import mock
        import Utils
        from ..client.client import MECDContext
        store = {}
        with mock.patch.object(Utils, "persistent_load", lambda: store), \
                mock.patch.object(Utils, "persistent_store",
                                  lambda c, k, v: store.setdefault(c, {}).__setitem__(k, v)):
            ctx = MECDContext(None, None)
            try:
                with tempfile.TemporaryDirectory(prefix="with space ") as d:
                    for n in ("mec_ap.dll", "mec_ap_inject.exe"):
                        open(os.path.join(d, n), "wb").close()
                    win = d.replace("/", "\\")
                    self.assertTrue(ctx.command_processor(ctx)(f"/dll_folder {win}"))
                    self.assertEqual(os.path.normcase(store["mec_ap"]["dll_folder"]), os.path.normcase(win))
                    self.assertTrue(ctx.command_processor(ctx)(f'/dll_folder "{win}"'))
            finally:
                await ctx.shutdown()

    def test_picker_remembers_the_folder_of_the_picked_dll(self):
        import os
        import tempfile
        from unittest import mock
        import Utils
        from ..client.launcher import pick_dll_folder
        store = {}
        with tempfile.TemporaryDirectory() as d:
            for n in ("mec_ap.dll", "mec_ap_inject.exe"):
                open(os.path.join(d, n), "wb").close()
            with mock.patch.object(Utils, "persistent_load", lambda: store), \
                    mock.patch.object(Utils, "persistent_store",
                                      lambda c, k, v: store.setdefault(c, {}).__setitem__(k, v)), \
                    mock.patch.object(Utils, "open_filename", lambda *a, **k: os.path.join(d, "mec_ap.dll")):
                self.assertEqual(os.path.normcase(pick_dll_folder()), os.path.normcase(d))
            with mock.patch.object(Utils, "persistent_load", lambda: {}), \
                    mock.patch.object(Utils, "open_filename", lambda *a, **k: None):
                self.assertIsNone(pick_dll_folder())                   # cancelled


class TestReloadCommand(unittest.IsolatedAsyncioTestCase):
    """/reload: refused without a DLL that offers it; every DLL answer gets a message."""

    async def asyncSetUp(self):
        from ..client.client import MECDContext
        self.ctx = MECDContext(None, None)

    async def asyncTearDown(self):
        await self.ctx.shutdown()

    async def test_needs_the_dll(self):
        self.assertFalse(await self.ctx.request_reload())            # not connected
        self.ctx.dll.hello = {"build_ok": True, "dll": "0.2.3"}      # an older DLL: no "reload"
        with self.assertLogs("Client", "INFO") as logs:
            self.assertFalse(await self.ctx.request_reload())
        self.assertIn("needs 0.3.0", "\n".join(logs.output))

    async def test_sends_when_offered(self):
        sent = []

        async def fake_reload():
            sent.append(1)
            return 7
        self.ctx.dll.hello = {"build_ok": True, "reload": True}
        self.ctx.dll.reload = fake_reload
        self.assertTrue(await self.ctx.request_reload())
        self.assertEqual(sent, [1])

    def test_every_result_has_a_message(self):
        from ..client.client import RELOAD_RESULTS
        # reload.h's list of results
        for r in ("started", "nothing", "not_in_level", "no_checkpoint", "busy", "disabled", "fault"):
            self.assertIn(r, RELOAD_RESULTS)
        with self.assertLogs("Client", "INFO") as logs:
            self.ctx.on_reloaded({"ev": "reloaded", "id": 1, "result": "started"})
            self.ctx.on_reloaded({"ev": "reloaded", "id": 2, "result": "something new"})
        self.assertIn("reloading", logs.output[0])
        self.assertIn("something new", logs.output[1])


class TestAutoReload(unittest.IsolatedAsyncioTestCase):
    """Reload once when leaving a dash, only when the map is missing something."""

    async def asyncSetUp(self):
        from unittest import mock
        import Utils
        from ..client import auto_reload
        self.store = {}
        for p in (mock.patch.object(Utils, "persistent_load", lambda: self.store),
                  mock.patch.object(Utils, "persistent_store",
                                    lambda c, k, v: self.store.setdefault(c, {}).__setitem__(k, v)),
                  mock.patch.object(auto_reload, "AFTER_CANCEL_SEC", 0.01),
                  mock.patch.object(auto_reload, "AFTER_FINISH_SEC", 0.02),
                  mock.patch.object(auto_reload, "SETUP_DELAY_SEC", 0.01)):
            p.start()
            self.addCleanup(p.stop)
        self.calls = []
        self.can = True

        async def reload():
            self.calls.append(1)
            return True
        self.a = auto_reload.AutoReload(reload, lambda: self.can)

    async def settle(self):
        await asyncio.sleep(0.08)

    async def test_nothing_missing_no_reload(self):
        self.a.on_dash_left(finished=False)
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_cancel_and_finish_reload_once(self):
        import time
        self.a.note("Ramp Up")
        self.a.on_dash_left(finished=False)
        await self.settle()
        self.assertEqual(self.calls, [1])
        self.a.on_round_reset()                       # the reload happened: nothing missing
        self.a.on_dash_left(finished=True, finish_time=time.time())
        await self.settle()
        self.assertEqual(self.calls, [1])
        self.a.note("Clockwork")
        self.a.on_dash_left(finished=True, finish_time=time.time())
        await self.settle()
        self.assertEqual(self.calls, [1, 1])

    async def test_old_finish_from_the_journal_is_ignored(self):
        self.a.note("Ramp Up")
        self.a.on_dash_left(finished=True, finish_time=1.0)
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_new_dash_cancels_and_off_stays_off(self):
        self.a.note("Ramp Up")
        self.a.on_dash_left(finished=True, finish_time=None)
        self.a.on_dash_started()                       # straight into another dash
        await self.settle()
        self.assertEqual(self.calls, [])
        self.a.set_enabled(False)
        self.assertFalse(self.store["mec_ap"]["auto_reload"])
        self.a.on_dash_left(finished=False)
        self.can = True
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_unlock_from_the_finished_dash_still_reloads(self):
        # Seen in game: the finish arrives first, the unlock it earned 0.6 s later.
        import time
        self.a.on_dash_left(finished=True, finish_time=time.time())
        await asyncio.sleep(0.005)
        self.a.note("Birdman's Route")
        await self.settle()
        self.assertEqual(self.calls, [1])

    async def test_late_unlock_long_after_no_reload_until_next_exit(self):
        from unittest import mock
        from ..client import auto_reload
        self.a.on_dash_left(finished=False)
        with mock.patch.object(auto_reload, "LATE_UNLOCK_SEC", 0.0):
            await asyncio.sleep(0.01)
            self.a.note("Ramp Up")
        await self.settle()
        self.assertEqual(self.calls, [])
        self.a.on_dash_started()
        self.a.on_dash_left(finished=False)
        await self.settle()
        self.assertEqual(self.calls, [1])

    async def test_launch_setup_reloads_once_per_game(self):
        self.a.note_setup("the hard dash lock")
        self.a.note_setup("the hidden activities")      # same tick: the one reload covers both
        await self.settle()
        self.assertEqual(self.calls, [1])
        self.a.on_round_reset()
        self.a.note_setup("the hard dash lock")          # written again after that reload: no loop
        await self.settle()
        self.assertEqual(self.calls, [1])
        self.a.on_game_connected()                       # the next game launch
        self.a.note_setup("the hard dash lock")
        await self.settle()
        self.assertEqual(self.calls, [1, 1])

    async def test_launch_waits_for_every_dash(self):
        # Seen 2026-11-27: 5, then 14, then 22 dashes found; the reload must follow the last.
        from unittest import mock
        from ..client import auto_reload
        with mock.patch.object(auto_reload, "SETUP_PARTIAL_WAIT_SEC", 0.2):
            self.a.note_setup("the hard dash lock", complete=False)
            self.a.note_setup("the hidden activities", complete=False)
            await asyncio.sleep(0.05)
            self.assertEqual(self.calls, [])                   # still waiting for the rest
            self.a.note_setup("the hard dash lock", complete=True)
            await self.settle()
            self.assertEqual(self.calls, [1])                  # once complete, at once
            await asyncio.sleep(0.25)
            self.assertEqual(self.calls, [1])                  # the fallback was replaced

    async def test_launch_fallback_then_complete(self):
        from unittest import mock
        from ..client import auto_reload
        with mock.patch.object(auto_reload, "SETUP_PARTIAL_WAIT_SEC", 0.01):
            self.a.note_setup("the hard dash lock", complete=False)
            await self.settle()
            self.assertEqual(self.calls, [1])                  # never completed: reload anyway
            self.a.on_round_reset()
            self.a.note_setup("the hard dash lock", complete=False)
            await self.settle()
            self.assertEqual(self.calls, [1])                  # one fallback per launch
            self.a.note_setup("the hard dash lock", complete=True)
            await self.settle()
            self.assertEqual(self.calls, [1, 1])               # completed later: once more
            self.a.on_round_reset()
            self.a.note_setup("the hard dash lock", complete=True)
            await self.settle()
            self.assertEqual(self.calls, [1, 1])               # and never again this launch

    async def test_launch_setup_waits_for_the_dash(self):
        self.a.on_dash_started()
        self.a.note_setup("the hard dash lock")
        await self.settle()
        self.assertEqual(self.calls, [])
        self.a.on_dash_left(finished=False)              # leaving the dash reloads instead
        await self.settle()
        self.assertEqual(self.calls, [1])

    async def test_waits_for_the_results_screen_to_close(self):
        # DLL 0.3.2+: no reload while the results are up; one when the player leaves them.
        import time
        self.a._exit_events = lambda: True
        self.a.on_dash_left(finished=True, finish_time=time.time())
        self.a.note("Birdman's Route")                   # earned by that run, 0.6 s later
        await self.settle()
        self.assertEqual(self.calls, [])
        self.a.on_activity_ended()
        await asyncio.sleep(0.03)
        self.assertEqual(self.calls, [])                 # AFTER_EXIT_SEC is 1 s
        self.a.task.cancel()
        self.a.awaiting_exit = True
        from unittest import mock
        from ..client import auto_reload
        with mock.patch.object(auto_reload, "AFTER_EXIT_SEC", 0.01):
            self.a.on_activity_ended()
            await self.settle()
        self.assertEqual(self.calls, [1])

    async def test_retry_from_the_results_screen_does_not_reload(self):
        import time
        self.a._exit_events = lambda: True
        self.a.note("Ramp Up")
        self.a.on_dash_left(finished=True, finish_time=time.time())
        self.a.on_dash_started()                          # retry: no activity_ended comes
        self.a.on_activity_ended()                        # (and a stray one is ignored)
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_needs_a_dll_that_can_reload(self):
        self.can = False
        self.a.note("Ramp Up")
        self.a.on_dash_left(finished=False)
        await self.settle()
        self.assertEqual(self.calls, [])


class TestDashBoard(unittest.TestCase):
    """The Dashes tab's rows."""

    def test_rows(self):
        from collections import Counter
        from ..client.plan import dash_board, race_time
        from ..data import DASH_NAMES, DASHES, dash_location_name, dash_unlock_name
        d = "Concrete Canyon"
        lid = lambda t: DASHES[dash_location_name(d, t)].id
        have = Counter({dash_unlock_name(d): 1})
        # a seed with 2 star tiers: the finish and 1 star done, 2 stars to do
        rows = {r.dash: r for r in dash_board(have, {lid(0), lid(1)}, {lid(2)})}
        self.assertEqual(len(rows), len(DASH_NAMES))
        r = rows[d]
        self.assertTrue(r.unlocked)
        self.assertTrue(r.finished)
        self.assertEqual((r.stars, r.star_checks), (1, 2))
        self.assertEqual(r.next_star_cs, DASHES[dash_location_name(d, 2)].max_cs)
        self.assertFalse(r.done)
        other = rows["High Roller Avenue"]
        self.assertFalse(other.unlocked)
        self.assertIsNone(other.finished)            # not in this seed's location lists
        self.assertEqual(other.star_checks, 0)
        done = {r.dash: r for r in dash_board(have, {lid(0), lid(1), lid(2)}, set())}[d]
        self.assertTrue(done.done)
        self.assertIsNone(done.next_star_cs)

    def test_race_time(self):
        from ..client.plan import race_time
        self.assertEqual(race_time(4592), "45.92")
        self.assertEqual(race_time(6530), "1:05.30")
        self.assertEqual(race_time(5), "0.05")
