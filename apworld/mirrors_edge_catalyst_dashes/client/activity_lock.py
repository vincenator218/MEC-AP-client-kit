"""
Hiding the activities that are not dashes (option hide_other_activities, docs/DLL.md section 11f).

Every opportunity, delivery, security hub and side mission is a PamProgressionMission. Its
CompletedFlag pointer (+0x48) normally leads to its real completion flag. Pointed at a flag that
is 1, the game treats the activity as done at the next checkpoint reload: off the map, cannot be
started. The real completion flag is never touched. One shared lock flag (data.ACTIVITY_LOCK_FLAG)
serves every hidden activity; the client holds it at 1 through game.ProgressionWriter.

Not hidden by this: the Dead Drop Deliveries (OWPh<N>Delivery01-03). The game always offers one
per phase, so locking one only moves the marker to the next.

Same rules as dash_lock.py: re-validate before each write (the mission's name, the current
pointer is the activity's own completion flag or already ours), read every write back, and put
every original pointer back when the client closes.
"""
from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field

from .mec_memory import MecMemory, djb2a

log = logging.getLogger("Client.MEC")

IMAGE_BASE = 0x140000000
VT_MISSION = 0x141C8E658                     # PamProgressionMission
M_NAME, M_COMPLETED = 0x10, 0x48
NODE_HASH, NODE_DEFINITION = 0x00, 0x10
F_NAME_HASH = 0x10
RESCAN_SEC = 30.0


@dataclass
class HideState:
    hidden: int = 0                          # pointers that lead to the lock flag now
    written: int = 0                         # pointers written in the last ensure()
    missing: list = field(default_factory=list)   # activities not found or not safe to touch


class ActivityHideDriver:
    def __init__(self, mem: MecMemory, table) -> None:
        self.mem, self.table = mem, table
        self.missions: dict[str, int] = {}   # name -> PamProgressionMission address
        self.original: dict[str, int] = {}   # name -> its own completion flag definition
        self.state: HideState | None = None
        self._last_scan = 0.0

    def _definition(self, flag: str) -> int | None:
        h = djb2a(flag)
        node = self.table.node(h)
        if node is None or self.mem.read_u32(node + NODE_HASH) != h:
            return None
        d = self.mem.read_u64(node + NODE_DEFINITION)
        return d if d and self.mem.read_u32(d + F_NAME_HASH) == h else None

    def _name(self, m: int) -> str | None:
        p = self.mem.read_u64(m + M_NAME)
        raw = self.mem.read_partial(p, 96) if p else None     # a name can end near a page edge
        return raw.split(b"\0")[0].decode("latin1") if raw else None

    def _valid(self, name: str) -> bool:
        m = self.missions.get(name)
        return m is not None and self._name(m) == name

    def _scan(self, wanted: set[str]) -> None:
        self._last_scan = time.monotonic()
        vt = VT_MISSION - IMAGE_BASE + self.mem.base
        found: dict[str, int] = {}
        for m in self.mem.scan_pointers_to(vt):
            n = self._name(m)
            if n in wanted:
                found[n] = m
        self.missions = found
        log.debug("Activity hide: found %d of %d activities in memory.", len(found), len(wanted))

    def ensure(self, wanted: dict[str, str], lock_flag: str) -> HideState:
        """wanted: activity name -> its own completion flag. Points each one's CompletedFlag at
        `lock_flag`, only where it still leads to that activity's own completion flag."""
        s = HideState()
        lock = self._definition(lock_flag)
        if lock is None:
            s.missing = list(wanted)
            self.state = s
            return s
        if any(not self._valid(n) for n in wanted) and \
                (not self.missions or time.monotonic() - self._last_scan >= RESCAN_SEC):
            self._scan(set(wanted))
        for name, own_flag in wanted.items():
            if not self._valid(name):
                s.missing.append(name)
                continue
            m = self.missions[name]
            cur = self.mem.read_u64(m + M_COMPLETED)
            own = self._definition(own_flag)
            if cur == lock:
                if own is not None:
                    self.original[name] = own      # also after a client restart: release finds it
                s.hidden += 1
                continue
            if own is None or cur != own:
                s.missing.append(name)
                continue
            if self.mem.write(m + M_COMPLETED, struct.pack("<Q", lock)) and \
                    self.mem.read_u64(m + M_COMPLETED) == lock:
                self.original[name] = own
                s.hidden += 1
                s.written += 1
            else:
                s.missing.append(name)
        self.state = s
        return s

    def release(self, lock_flag: str) -> int:
        """Put back every original pointer that still leads to the lock flag."""
        lock = self._definition(lock_flag)
        n = 0
        for name, own in list(self.original.items()):
            m = self.missions.get(name)
            if m is not None and self._valid(name) and lock is not None and \
                    self.mem.read_u64(m + M_COMPLETED) == lock:
                if self.mem.write(m + M_COMPLETED, struct.pack("<Q", own)):
                    n += 1
        self.original.clear()
        return n
