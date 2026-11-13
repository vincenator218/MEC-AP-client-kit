"""Applying abilities now through mec_ap.dll: which flags qualify, and the link round trip."""
import asyncio
import json
import unittest

from ..client import dll_link
from ..client.client import appliable
from ..client.mec_memory import djb2a
from ..data import DOUBLE_WALLRUN_FLAG, ITEMS


class TestAppliable(unittest.TestCase):
    def test_only_entity_enforced_flags(self):
        by_method = {}
        for item in ITEMS.values():
            if item.flag:
                by_method.setdefault(item.grant_method, []).append(item.flag)
        for flag in by_method.get("live_entity", []) + by_method.get("persistent_entity", []):
            self.assertTrue(appliable(flag), flag)
        for flag in by_method.get("table_write_reload", []):   # side-mission / opportunity unlocks
            self.assertFalse(appliable(flag), flag)
        self.assertTrue(appliable(DOUBLE_WALLRUN_FLAG))         # Progressive Wallrun #2
        self.assertTrue(appliable("Unlocks_Coil"))
        self.assertFalse(appliable("SilverCompleted_Drone Works"))
        self.assertFalse(appliable("not a flag"))


class TestApplyLink(unittest.TestCase):
    """DllLink.apply against a fake DLL on a real localhost socket."""

    def test_round_trip(self):
        asyncio.run(self._run(apply_ok=True))

    def test_not_offered_without_apply(self):
        asyncio.run(self._run(apply_ok=False))

    async def _run(self, apply_ok: bool):
        got = []

        async def serve(reader, writer):
            hello = {"ev": "hello", "proto": 1, "dll": "test", "build_ok": True, "apply": apply_ok,
                     "apply_why": "" if apply_ok else "check failed", "acked": 0, "last": 0}
            writer.write((json.dumps(hello) + "\n").encode())
            await writer.drain()
            while True:
                line = await reader.readline()
                if not line:
                    return
                cmd = json.loads(line)
                got.append(cmd)
                if cmd.get("cmd") == "apply":
                    reply = {"ev": "applied", "id": cmd["id"], "hash": cmd["hash"], "value": cmd["value"],
                             "result": "applied", "matched": 1, "targets": 1, "live": True}
                    writer.write((json.dumps(reply) + "\n").encode())
                    await writer.drain()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        hellos, results = [], []

        async def on_finished(ev):
            return True

        old = dll_link.PORT
        dll_link.PORT = port
        stop = asyncio.Event()
        link = dll_link.DllLink(on_finished, on_applied=results.append, on_hello=hellos.append)
        task = asyncio.create_task(link.run(stop))
        try:
            for _ in range(50):
                await asyncio.sleep(0.05)
                if link.connected:
                    break
            self.assertTrue(link.connected)
            self.assertEqual(len(hellos), 1)
            self.assertEqual(link.can_apply, apply_ok)
            req = await link.apply(djb2a("Unlocks_MoveEnemyBack"), 1)
            if not apply_ok:
                self.assertIsNone(req)
                await asyncio.sleep(0.2)
                self.assertEqual(got, [])           # nothing is sent to a DLL that cannot apply
                return
            for _ in range(50):
                await asyncio.sleep(0.05)
                if results:
                    break
            # MEMORY.md §1: djb2a("Unlocks_MoveEnemyBack") == 0x67800619
            self.assertEqual(got, [{"cmd": "apply", "id": req, "hash": "67800619", "value": 1}])
            self.assertEqual(results[0]["id"], req)
            self.assertEqual(results[0]["result"], "applied")
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)
            dll_link.PORT = old
            server.close()
            await server.wait_closed()
