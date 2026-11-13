"""
Everything the client does to the game, on top of mec_memory.MecMemory.

All of it is blocking memory I/O, so the asyncio client runs it on one worker thread.
Nothing in here knows about Archipelago; it is handed "these flags should hold these
values, these moves should be blocked" and reports what the game actually shows.

Rules from docs/MEMORY.md this module follows:

* Re-validate before every write. Flag nodes are re-checked against their hash and the
  table pointer; the exclusion volume against its vtable. Nothing is keyed by address
  beyond one tick.
* Report state, not intent. Every write is read back and compared.
* Progression flags are written in exactly one place: ProgressionWriter.set_flag_for_item.
  mec_memory itself never writes them.
* No `apply` calls. Abilities written here take effect at the next death or checkpoint
  restart; see the Applier class for where a game-thread hook would plug in.
"""
from __future__ import annotations

import logging
import struct
import threading
from dataclasses import dataclass, field

from .mec_memory import MecError, MecMemory, djb2a

log = logging.getLogger("Client.MEC")       # a child of CommonClient's logger, so the GUI shows it

FLAG_TABLE_PTR = 0x257C9D8
NODE_HASH, NODE_VALUE, NODE_NEXT = 0x00, 0x18, 0x28
LOADED_PROBE = "Unlocks_Coil"          # OPEN_QUESTIONS.md #4: resolves once the world is up
SETTLE_TICKS = 2                       # loaded ticks before the first write after a load


class FlagTable:
    """Read access to the progression flag table (MEMORY.md §2), with node caching.

    A cached node is trusted only while the table pointer is unchanged and the node's
    own hash field still matches; otherwise the bucket chain is walked again.
    """

    def __init__(self, mem: MecMemory) -> None:
        self.mem = mem
        self._table: int | None = None
        self._nodes: dict[int, int] = {}

    def table(self) -> int | None:
        t = self.mem.read_u64(self.mem.base + FLAG_TABLE_PTR)
        if t != self._table:
            self._table = t
            self._nodes.clear()
        return t or None

    def loaded(self) -> bool:
        t = self.table()
        if not t:
            return False
        nbuck = self.mem.read_u32(t + 0x28)
        if not nbuck or not 16 < nbuck < 100000:
            return False
        return self.node(djb2a(LOADED_PROBE)) is not None

    def node(self, h: int) -> int | None:
        t = self.table()
        if not t:
            return None
        n = self._nodes.get(h)
        if n is not None and self.mem.read_u32(n + NODE_HASH) == h:
            return n
        buckets = self.mem.read_u64(t + 0x20)
        nbuck = self.mem.read_u32(t + 0x28)
        if not buckets or not nbuck:
            return None
        n = self.mem.read_u64(buckets + (h % nbuck) * 8)
        steps = 0
        while n and steps < 10000:
            if self.mem.read_u32(n + NODE_HASH) == h:
                self._nodes[h] = n
                return n
            n = self.mem.read_u64(n + NODE_NEXT)
            steps += 1
        self._nodes.pop(h, None)
        return None

    def read(self, name: str) -> int | None:
        """The flag's i32 value; None when the table or the node is not there."""
        n = self.node(djb2a(name))
        if n is None:
            return None
        raw = self.mem.read(n + NODE_VALUE, 4)
        return struct.unpack("<i", raw)[0] if raw else None


class ProgressionWriter:
    """The one code path that writes progression flags.

    A flag written here is captured by the game's autosave, so it changes the player's
    save file. Call it only to grant a received item, or to take back an ability the
    player bought but did not receive (the revert_skill_tree_purchases option).
    """

    def __init__(self, table: FlagTable) -> None:
        self.table = table

    def set_flag_for_item(self, flag: str, value: int, reason: str) -> bool:
        """Write `flag` = `value` and confirm it by reading it back."""
        n = self.table.node(djb2a(flag))
        if n is None:
            log.warning("Flag %s is not in the table; cannot apply %s.", flag, reason)
            return False
        if self.table.read(flag) == value:
            return True
        if not self.table.mem.write(n + NODE_VALUE, struct.pack("<i", int(value))):
            return False
        got = self.table.read(flag)
        if got != value:
            log.warning("Wrote %s=%d for %s but the game reads %r.", flag, value, reason, got)
            return False
        log.debug("Wrote %s=%d (%s).", flag, value, reason)
        return True


class Applier:
    """Where an immediate `apply` (MEMORY.md §3) would go.

    It must run on the game's thread: calling it from a foreign thread crashed the game
    twice, and no per-frame hook point has been chosen (OPEN_QUESTIONS.md #1). Until one
    exists this does nothing and the ability takes effect at the next death or
    checkpoint restart. A hook-backed implementation should return True only when it has
    confirmed the entity's last-applied value ([e+0x78]) changed.
    """

    def apply_now(self, flag: str, value: int) -> bool:
        return False


class ExclusionDriver:
    """Keeps one movement exclusion volume asserting the blocked moves (MEMORY.md §5).

    Same pattern as MEC_MoveToggles.pyw: drive a single volume, re-assert it every tick,
    and when its vtable stops matching (streamed out) pick another, searching near the
    old one first.
    """

    def __init__(self, mem: MecMemory) -> None:
        self.mem = mem
        self.volume: int | None = None
        self.hint: int | None = None
        self.rejected: set[int] = set()                # volumes the player said did nothing
        self.verified: dict[str, bool] | None = None   # last state read back from the game

    def reset(self) -> None:
        self.volume = self.hint = None
        self.verified = None
        self.rejected.clear()

    def reject_current(self) -> None:
        """Not every volume affects the player (tools/client/README.md); try another."""
        if self.volume is not None:
            self.rejected.add(self.volume)
            self.mem.release_exclusion(self.volume)
        self.volume = None
        self.verified = None

    def assert_blocked(self, blocked: dict[str, bool]) -> bool:
        if not any(blocked.values()):
            if self.verified is None or any(self.verified.values()):
                self.mem.release_tracked()
            self.volume = None
            self.verified = dict(blocked)
            return True
        if self.volume is not None and not self.mem.is_volume(self.volume):
            self.hint = self.volume
            self.volume = None
            log.info("The movement volume unloaded; picking another.")
        if self.volume is None:
            self.volume = self.mem.find_one_exclusion_volume(prefer=self.hint, skip=self.rejected)
            if self.volume is None and self.rejected:
                log.info("Tried every volume found; starting the list again.")
                self.rejected.clear()
                self.volume = self.mem.find_one_exclusion_volume(prefer=self.hint)
            if self.volume is None:
                self.verified = None
                return False
            self.hint = self.volume
        if self.mem.set_exclusions(self.volume, **blocked):
            self.verified = dict(blocked)
            return True
        log.info("Volume 0x%X did not verify; trying another.", self.volume)
        self.volume = None
        self.verified = None
        return False

    def release(self) -> int:
        n = self.mem.release_tracked()
        self.reset()
        return n


@dataclass
class TickResult:
    attached: bool = False
    loaded: bool = False
    just_loaded: bool = False          # the world came up (first attach, or after a load)
    detected: set[int] = field(default_factory=set)
    flags_written: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)   # flag -> why it was written
    flags_failed: list[str] = field(default_factory=list)
    moves_ok: bool | None = None
    final_done: bool = False


class GameSession:
    """Attach, detect loads, and carry out one tick of the client's plan."""

    def __init__(self) -> None:
        self.mem = MecMemory()
        self.table = FlagTable(self.mem)
        self.writer = ProgressionWriter(self.table)
        self.applier = Applier()
        self.moves = ExclusionDriver(self.mem)
        self._was_loaded = False
        self._last_table: int | None = None
        self.warned_build = False
        self._build_checked = False
        self._settle = 0                    # loaded ticks since the last load began
        self._attach_error = ""
        self.lock = threading.Lock()        # tick() and shutdown() never overlap

    # -------------------------------------------------------------- lifecycle
    def ensure_attached(self) -> bool:
        if self.mem.attached:
            return True
        if self.mem.handle:
            log.info("The game closed.")
        self.detach()
        try:
            self.mem.attach()
        except MecError as e:
            if str(e) != self._attach_error:
                self._attach_error = str(e)
                log.info("%s Waiting...", e)
            return False
        self._attach_error = ""
        log.info("Attached to the game (base 0x%X).", self.mem.base)
        return True

    def _check_build(self) -> None:
        """Once per attach, after the world is up. Checking at attach time raced the game's
        startup: the type info was not filled in yet and read as class None."""
        if self._build_checked:
            return
        self._build_checked = True
        s = self.mem.sanity()
        if s["class_name"] != "PamMovementExclusionEntityData" and not self.warned_build:
            self.warned_build = True
            log.warning("Offsets do not match this game build (found class %r). "
                        "Reading and writing may not work.", s["class_name"])

    def detach(self) -> None:
        self.mem.detach()
        self.table = FlagTable(self.mem)
        self.writer = ProgressionWriter(self.table)
        self.moves = ExclusionDriver(self.mem)
        self._was_loaded = False
        self._last_table = None
        self._build_checked = False
        self._settle = 0

    def shutdown(self) -> None:
        """Give every move back before leaving. Flags stay: they are the player's items."""
        with self.lock:
            try:
                if self.mem.attached:
                    self.moves.release()
            finally:
                self.mem.detach()

    # ------------------------------------------------------------------- tick
    def tick(self, plan: "Plan") -> TickResult:
        with self.lock:
            return self._tick(plan)

    def _tick(self, plan: "Plan") -> TickResult:
        r = TickResult()
        if not self.ensure_attached():
            return r
        r.attached = True
        r.loaded = self.table.loaded()
        table = self.table.table()
        if not r.loaded:
            if self._was_loaded:
                log.info("Loading...")
                self.moves.reset()
            self._was_loaded = False
            return r
        if not self._was_loaded or table != self._last_table:
            r.just_loaded = True
            self.moves.reset()
            self._settle = 0
        self._was_loaded, self._last_table = True, table
        self._settle += 1
        self._check_build()

        seen: dict[str, int | None] = {}        # one read per flag per tick

        def read(flag: str) -> int | None:
            if flag not in seen:
                seen[flag] = self.table.read(flag)
            return seen[flag]

        for loc_id, check in plan.watch.items():
            if check(read):
                r.detected.add(loc_id)
        if plan.final_check is not None:
            r.final_done = plan.final_check(read)
        if plan.reject_volume:
            self.moves.reject_current()

        # Right after a load the game is still filling the table from the save: in the first
        # live test a write landed, was overwritten, and had to be made three times. Wait one
        # more tick so a write is made once, onto settled values.
        if plan.writes_allowed and self._settle >= SETTLE_TICKS:
            for flag, (value, reason) in plan.flags.items():
                current = self.table.read(flag)
                if current is None or current == value:
                    continue
                if self.writer.set_flag_for_item(flag, value, reason):
                    r.flags_written.append(flag)
                    r.reasons[flag] = reason
                    self.applier.apply_now(flag, value)
                else:
                    r.flags_failed.append(flag)
            if plan.blocked is not None:
                r.moves_ok = self.moves.assert_blocked(plan.blocked)
        return r


@dataclass
class Plan:
    """What the client wants this tick. Built on the event loop, consumed on the worker."""
    watch: dict = field(default_factory=dict)          # location id -> check(read) -> bool
    final_check: object = None                         # check(read) -> bool, or None
    flags: dict = field(default_factory=dict)          # flag -> (value, reason)
    blocked: dict | None = None                        # move -> True to block; None = leave alone
    writes_allowed: bool = False
    reject_volume: bool = False                        # /next_volume was typed
