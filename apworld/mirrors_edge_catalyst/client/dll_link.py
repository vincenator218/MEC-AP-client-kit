"""
The connection to mec_ap.dll, the agent injected into the game (dll/ in the client kit).

The DLL listens on 127.0.0.1:47910 and sends one JSON object per line (dll/src/link.h has the
whole protocol). Finished runs carry a sequence number and are kept in the DLL's journal until
this side acknowledges them, so a run finished while the client was closed, or before it had a
slot, is sent again on the next connection. A finish is acknowledged only after the handler has
dealt with it; the handler says when it could not yet (no slot), and the event is kept.

It also carries ability applies: after the client writes an ability flag it sends
{"cmd":"apply","id":N,"hash":"<djb2a hex>","value":V}, and the DLL calls the game's apply on the
server game thread and answers {"ev":"applied","id":N,"result":...} with what the game shows.
Only when the hello says "apply": true. Applies are live only; after a reconnect the client asks
again.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

log = logging.getLogger("Client.MEC")

HOST, PORT = "127.0.0.1", 47910
PROTOCOL = 1
RETRY_SEC = 3.0

FinishedHandler = Callable[[dict], Awaitable[bool]]   # True: handled, acknowledge it
EventHandler = Callable[[dict], None]


class DllLink:
    def __init__(self, on_finished: FinishedHandler, on_live: EventHandler | None = None,
                 on_applied: EventHandler | None = None, on_hello: EventHandler | None = None) -> None:
        self.on_finished = on_finished
        self.on_live = on_live or (lambda ev: None)
        self.on_applied = on_applied or (lambda ev: None)
        self.on_hello = on_hello or (lambda ev: None)
        self._next_id = 0
        self.hello: dict | None = None             # the DLL's last hello, None while not connected
        self.pending: dict[int, dict] = {}         # seq -> finish not yet acknowledged
        self._writer: asyncio.StreamWriter | None = None
        self._said_waiting = False

    @property
    def connected(self) -> bool:
        return self.hello is not None

    @property
    def can_apply(self) -> bool:
        """The DLL is active and says it can apply abilities on this build."""
        h = self.hello
        return bool(h and h.get("build_ok") and h.get("apply"))

    async def apply(self, flag_hash: int, value: int) -> int | None:
        """Ask the DLL to apply a flag the client has written. The request id, or None."""
        if not self.can_apply or self._writer is None:
            return None
        self._next_id += 1
        await self._send({"cmd": "apply", "id": self._next_id, "hash": f"{flag_hash:08x}",
                          "value": int(value)})
        return self._next_id

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                reader, writer = await asyncio.open_connection(HOST, PORT)
            except OSError:
                if not self._said_waiting:
                    self._said_waiting = True
                    log.info("Waiting for mec_ap.dll in the game (needed for dash checks). "
                             "Run mec_ap_inject.exe if you play with dashes on.")
                await self._sleep(stop, RETRY_SEC)
                continue
            self._said_waiting = False
            self._writer = writer
            try:
                await self._session(reader, stop)
            except (OSError, asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                self.hello, self._writer = None, None
                writer.close()
                log.info("Lost the connection to mec_ap.dll. Retrying...")
            await self._sleep(stop, RETRY_SEC)

    async def _session(self, reader: asyncio.StreamReader, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                await self.flush()                  # retry anything kept back (slot not ready)
                continue
            if not line:
                return                              # the DLL went away (game closed)
            try:
                ev = json.loads(line)
            except ValueError:
                log.debug("mec_ap.dll sent a line that is not JSON: %r", line[:200])
                continue
            await self.handle(ev)

    async def handle(self, ev: dict) -> None:
        kind = ev.get("ev")
        if kind == "hello":
            self.hello = ev
            if ev.get("proto") != PROTOCOL:
                log.warning("mec_ap.dll speaks protocol %r, this client %d: update both.",
                            ev.get("proto"), PROTOCOL)
            if ev.get("build_ok"):
                log.info("Connected to mec_ap.dll %s. Dash checks are on. %s", ev.get("dll"),
                         "Received abilities apply immediately." if ev.get("apply") else
                         f"Abilities still apply at the next respawn ({ev.get('apply_why') or 'no apply'}).")
            else:
                log.warning("mec_ap.dll %s is loaded but inactive: %s. Dashes will not be "
                            "detected.", ev.get("dll"), ev.get("why") or "unknown reason")
        elif kind == "finished" and isinstance(ev.get("seq"), int):
            self.pending[ev["seq"]] = ev
            await self.flush()
        elif kind in ("started", "cancelled"):
            self.on_live(ev)
        elif kind == "applied":
            self.on_applied(ev)
        if kind == "hello":
            self.on_hello(ev)

    async def flush(self) -> None:
        for seq in sorted(self.pending):
            if not await self.on_finished(self.pending[seq]):
                return                              # not ready: keep it and everything after it
            del self.pending[seq]
            await self._send({"cmd": "ack", "seq": seq})

    async def _send(self, msg: dict) -> None:
        if self._writer is not None:
            self._writer.write((json.dumps(msg) + "\n").encode())
            await self._writer.drain()

    @staticmethod
    async def _sleep(stop: asyncio.Event, sec: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass
