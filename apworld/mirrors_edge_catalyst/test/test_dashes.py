"""Dash locations: the data, the star rule, generation, and the link to mec_ap.dll."""
import asyncio
import json
import unittest

from .. import logic
from ..client import dll_link
from ..client.plan import dash_checks
from ..data import DASHES, DASHES_BY_CONTENT_ID, LOCATIONS, dash_location_name
from . import MECTestBase

CANYON = 0x353FF992          # Concrete Canyon: stars at 46.00 / 38.00 / 32.50 s


class TestDashData(unittest.TestCase):
    def test_counts_and_ids(self):
        self.assertEqual(len(DASHES), 22 * 4)
        self.assertEqual(len(DASHES_BY_CONTENT_ID), 22)
        finish = LOCATIONS[dash_location_name("Birdman's Dash")]
        self.assertEqual(finish.id, 1330000)                     # ap_index 0
        self.assertEqual(LOCATIONS[dash_location_name("Old Tunnels", 3)].id, 1330213)
        self.assertEqual(LOCATIONS[dash_location_name("Concrete Canyon", 2)].max_cs, 3800)

    def test_star_rule(self):
        ids = lambda *t: {LOCATIONS[dash_location_name("Concrete Canyon", k)].id for k in t}  # noqa: E731
        self.assertEqual(dash_checks(CANYON, 9999), ids(0))      # slow: the finish only
        self.assertEqual(dash_checks(CANYON, 4000), ids(0, 1))
        self.assertEqual(dash_checks(CANYON, 3800), ids(0, 1, 2))  # on the line counts
        self.assertEqual(dash_checks(CANYON, 3026), ids(0, 1, 2, 3))
        self.assertEqual(dash_checks(0x12345678, 100), set())   # not a dash

    def test_stars_share_the_dash_requirement(self):
        r = logic.load_requirements("location,requires\nDash - Concrete Canyon,MAG Rope\n")
        self.assertEqual(r.for_location("Dash - Concrete Canyon - 3 Stars"), logic.Has("MAG Rope"))
        r = logic.load_requirements("location,requires\nDash - Concrete Canyon,MAG Rope\n"
                                    "Dash - Concrete Canyon - 3 Stars,Coil\n")
        self.assertEqual(r.for_location("Dash - Concrete Canyon - 3 Stars"), logic.Has("Coil"))


class TestDashesOff(MECTestBase):
    def test_no_dashes_by_default(self):
        names = self.multiworld.worlds[self.player].location_names
        self.assertFalse(any(n.startswith("Dash - ") for n in names))


class TestDashesOn(MECTestBase):
    options = {"dashes": True, "dash_stars": 3}

    def test_all_88(self):
        names = self.multiworld.worlds[self.player].location_names
        self.assertEqual(sum(n.startswith("Dash - ") for n in names), 88)
        self.assertTrue(self.multiworld.worlds[self.player].fill_slot_data()["dashes"])


class TestDashesNoStars(MECTestBase):
    options = {"dashes": True, "dash_stars": 0}

    def test_finish_only(self):
        names = self.multiworld.worlds[self.player].location_names
        self.assertEqual(sum(n.startswith("Dash - ") for n in names), 22)
        self.assertFalse(any("Star" in n for n in names))


class TestDllLink(unittest.TestCase):
    """DllLink against a fake DLL on a real localhost socket."""

    def test_ack_only_after_handled(self):
        asyncio.run(self._run())

    async def _run(self):
        acks, ready, handled = [], [False], []

        async def serve(reader, writer):
            for ev in ({"ev": "hello", "proto": 1, "dll": "test", "build_ok": True, "acked": 0, "last": 1},
                       {"ev": "finished", "seq": 1, "content_id": "353ff992", "run_cs": 3026}):
                writer.write((json.dumps(ev) + "\n").encode())
            await writer.drain()
            while True:
                line = await reader.readline()
                if not line:
                    return
                acks.append(json.loads(line))

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        async def on_finished(ev):
            if not ready[0]:
                return False                     # no slot yet: keep it
            handled.append(ev["seq"])
            return True

        old = dll_link.PORT
        dll_link.PORT = port
        stop = asyncio.Event()
        link = dll_link.DllLink(on_finished)
        task = asyncio.create_task(link.run(stop))
        try:
            for _ in range(50):
                await asyncio.sleep(0.05)
                if link.pending:
                    break
            self.assertTrue(link.connected)
            self.assertEqual(list(link.pending), [1])
            self.assertEqual(acks, [])            # not handled, so not acknowledged
            ready[0] = True                       # the slot connects
            for _ in range(60):                   # the link retries kept events every second
                await asyncio.sleep(0.05)
                if acks:
                    break
            self.assertEqual(handled, [1])
            self.assertEqual(acks, [{"cmd": "ack", "seq": 1}])
            self.assertEqual(link.pending, {})
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)
            dll_link.PORT = old
            server.close()
            await server.wait_closed()
