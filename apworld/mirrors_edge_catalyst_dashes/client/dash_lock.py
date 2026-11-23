"""
The hard dash lock (docs/DLL.md section 11e), on top of the shared game.py.

Each dash's PamNamedChallengeData.UnlockFlag (+0x40) is null in the shipped game. Pointed at a
progression flag, that flag becomes the dash's unlock: while it is 0 the dash is off the map and
cannot be started; at 1 it is back. Both show only after a checkpoint reload (not fast travel,
not a death).

This module only writes the 22 pointers. The flags themselves are progression flags and go
through game.ProgressionWriter like every other flag (plan.desired_flags).

Rules followed (game.py header): every pointer is re-validated before it is written (the data
still holds its ContentId, the flag definition still holds its hash), each write is read back,
and only a pointer that is null or already ours is ever touched. On shutdown the pointers are
set back to null, so a save loaded afterwards in the same game shows every dash again.
"""
from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field

from .game import NODE_HASH, GameSession, Plan
from .mec_memory import MecMemory, djb2a

log = logging.getLogger("Client.MEC")

IMAGE_BASE = 0x140000000
VT_SERVER_NAMED_CHALLENGE = 0x141C7EC70      # PamServerNamedChallengeEntity
ENT_DATA = 0x80                              # entity -> PamNamedChallengeData
D_UNLOCK_FLAG, D_CONTENT_ID = 0x40, 0x98
NODE_DEFINITION = 0x10                       # flag table node -> PamProgressionFlag
F_NAME_HASH = 0x10
RESCAN_SEC = 30.0                            # a failed or partial scan is retried this often


@dataclass
class DashesPlan(Plan):
    dash_locks: dict | None = None           # content_id -> lock flag; None = leave the pointers alone


@dataclass
class LockState:
    locked: int = 0                          # pointers that hold our flag now
    written: int = 0                         # pointers written in the last ensure()
    missing: list = field(default_factory=list)   # content ids not found in memory
    foreign: list = field(default_factory=list)   # content ids whose pointer is someone else's


class DashLockDriver:
    def __init__(self, mem: MecMemory, table) -> None:
        self.mem, self.table = mem, table
        self.data: dict[int, int] = {}       # content_id -> PamNamedChallengeData address
        self.ours: dict[int, int] = {}       # content_id -> flag definition we wrote there
        self.state: LockState | None = None
        self._last_scan = 0.0

    def reset(self) -> None:
        """After a detach. Addresses are re-found, never trusted across attaches."""
        self.data.clear()
        self.ours.clear()
        self.state = None
        self._last_scan = 0.0

    # ------------------------------------------------------------- lookups
    def _definition(self, flag: str) -> int | None:
        h = djb2a(flag)
        node = self.table.node(h)
        if node is None or self.mem.read_u32(node + NODE_HASH) != h:
            return None
        d = self.mem.read_u64(node + NODE_DEFINITION)
        return d if d and self.mem.read_u32(d + F_NAME_HASH) == h else None

    def _valid(self, cid: int) -> bool:
        d = self.data.get(cid)
        return d is not None and self.mem.read_u32(d + D_CONTENT_ID) == cid

    def _scan(self, wanted: set[int]) -> None:
        self._last_scan = time.monotonic()
        vt = VT_SERVER_NAMED_CHALLENGE - IMAGE_BASE + self.mem.base
        found: dict[int, int] = {}
        for e in self.mem.scan_pointers_to(vt):
            d = self.mem.read_u64(e + ENT_DATA)
            cid = self.mem.read_u32(d + D_CONTENT_ID) if d else None
            if cid in wanted:
                found[cid] = d
        self.data = found
        log.debug("Dash lock: found %d of %d dashes in memory.", len(found), len(wanted))

    # -------------------------------------------------------------- writes
    def ensure(self, wanted: dict[int, str]) -> LockState:
        """Point every wanted dash's UnlockFlag at its lock flag. Cheap when all is in place:
        one memory scan per attach (or after a failure), then two reads per dash per tick."""
        s = LockState()
        if any(not self._valid(c) for c in wanted) and \
                (not self.data or time.monotonic() - self._last_scan >= RESCAN_SEC):
            self._scan(set(wanted))
        for cid, flag in wanted.items():
            if not self._valid(cid):
                s.missing.append(cid)
                continue
            d, want = self.data[cid], self._definition(flag)
            if want is None:
                s.missing.append(cid)
                continue
            cur = self.mem.read_u64(d + D_UNLOCK_FLAG)
            if cur == want:
                self.ours[cid] = want
                s.locked += 1
            elif cur == 0:
                if self.mem.write(d + D_UNLOCK_FLAG, struct.pack("<Q", want)) and \
                        self.mem.read_u64(d + D_UNLOCK_FLAG) == want:
                    self.ours[cid] = want
                    s.locked += 1
                    s.written += 1
                else:
                    s.missing.append(cid)
            else:
                s.foreign.append(cid)
        self.state = s
        return s

    def release(self) -> int:
        """Set every pointer we wrote back to null (only where it still holds ours)."""
        n = 0
        for cid, want in list(self.ours.items()):
            d = self.data.get(cid)
            if d is not None and self._valid(cid) and self.mem.read_u64(d + D_UNLOCK_FLAG) == want:
                if self.mem.write(d + D_UNLOCK_FLAG, struct.pack("<Q", 0)):
                    n += 1
        self.ours.clear()
        return n


class DashesGameSession(GameSession):
    """game.GameSession plus the dash lock pointers."""

    def __init__(self) -> None:
        super().__init__()
        self.locks = DashLockDriver(self.mem, self.table)

    def detach(self) -> None:
        super().detach()
        self.locks = DashLockDriver(self.mem, self.table)

    def _tick(self, plan: Plan):
        r = super()._tick(plan)
        wanted = getattr(plan, "dash_locks", None)
        if r.loaded and plan.writes_allowed and wanted:
            self.locks.ensure(wanted)
        return r

    def shutdown(self) -> None:
        """Dashes go back to normal before leaving, then game.GameSession gives the moves back."""
        with self.lock:
            try:
                if self.mem.attached:
                    n = self.locks.release()
                    if n:
                        log.info("Dash locks removed from %d dashes.", n)
            except Exception:                                    # noqa: BLE001
                log.exception("Could not remove the dash locks.")
        super().shutdown()
