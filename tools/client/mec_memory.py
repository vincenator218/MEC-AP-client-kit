#!/usr/bin/env python3
"""
mec_memory.py -- read and write Mirror's Edge Catalyst's memory from Python.

Windows only, 64-bit Python only. Pure stdlib (ctypes), nothing to install.

This is the memory layer an Archipelago client needs. It covers:

  * attaching to the game and finding the module base
  * walking writable memory and finding instances of an SDK class by its vtable
  * the movement exclusion volumes -- the five traversal items (MEMORY.md §5)
  * READING the progression flag table -- location checks (MEMORY.md §1-2)

It deliberately does **not** write progression flags. Those are captured by the
game's autosave, so a write there changes the player's save file. That belongs in
the client, behind its own deliberate code path, not in a shared utility that a
tester tool imports. Exclusion volumes are safe by comparison: they are level
state, nothing is persisted, and a restart is always a clean slate.

Offsets come from the PC build the research used. Check them with
`MecMemory.sanity()` before trusting anything.

    from mec_memory import MecMemory
    m = MecMemory()
    m.attach()
    vols = m.find_exclusion_volumes()
    m.set_exclusions(vols[0], climb_up=True)      # remove the mantle
    print(m.read_flag("Unlocks_Coil"))            # 0 or 1
    m.release_exclusion(vols[0])
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import struct
import sys

# ---------------------------------------------------------------- build offsets
PROCESS_NAME = "MirrorsEdgeCatalyst.exe"

FLAG_TABLE_PTR = 0x257C9D8     # -> the progression flag hash table
EXCL_TYPEINFO  = 0x2878C00     # PamMovementExclusionEntityData type info
MODULE_SPAN    = 0x4000000     # anything within this of the base is module data

# PamMovementExclusionEntityData field offsets
OFF_EXTENTS  = 0x80            # Vec3 half-size
OFF_ENABLED  = 0x90
OFF_EXCLUDE  = {               # 1 = move removed, 0 = move available
    "springboard": 0xA0,       # ExcludeVault
    "climb_up":    0xA1,       # ExcludeHeaveUp
    "ledge_hang":  0xA2,       # ExcludeHang
    "wallrun":     0xA3,       # ExcludeWallrun
    "mag_rope":    0xA4,       # ExcludeMagrope
}
MOVES = tuple(OFF_EXCLUDE)

VOLUME_SIZE   = 20000.0        # 20000 works; 50000 is silently ignored
OURS_ABOVE    = 100.0          # authored extents are tiny (largest seen: 38.2)

# ------------------------------------------------------------------ win32 bits
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ           = 0x0010
PROCESS_VM_WRITE          = 0x0020
PROCESS_VM_OPERATION      = 0x0008
ACCESS = (PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
          | PROCESS_VM_WRITE | PROCESS_VM_OPERATION)

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE   = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

MEM_COMMIT = 0x1000
PAGE_READWRITE          = 0x04
PAGE_WRITECOPY          = 0x08
PAGE_EXECUTE_READWRITE  = 0x40
PAGE_EXECUTE_WRITECOPY  = 0x80
WRITABLE = (PAGE_READWRITE | PAGE_WRITECOPY
            | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)
PAGE_GUARD = 0x100


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("th32ModuleID", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("GlblcntUsage", wintypes.DWORD),
                ("ProccntUsage", wintypes.DWORD),
                ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", wintypes.DWORD),
                ("hModule", ctypes.c_void_p),
                ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong),
                ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wintypes.DWORD),
                ("__alignment1", wintypes.DWORD),
                ("RegionSize", ctypes.c_ulonglong),
                ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("__alignment2", wintypes.DWORD)]


if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:                                        # importable off Windows for tests
    _k32 = None


class MecError(RuntimeError):
    """Something went wrong that the caller should show to the user."""


def djb2a(name: str) -> int:
    """The progression flag hash: djb2a over UTF-8, seed 5381, no terminator."""
    h = 5381
    for b in name.encode("utf-8"):
        h = ((h * 33) ^ b) & 0xFFFFFFFF
    return h


class MecMemory:
    def __init__(self) -> None:
        self.handle = None
        self.pid = None
        self.base = None
        self.vtable = None          # shared vtable of exclusion volume instances
        self._buf = None            # reused scan buffer; allocating per chunk was slow
        self._ours: set[int] = set()  # volumes we have written, so releasing needs no scan

    # ------------------------------------------------------------- attaching
    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise MecError("This only works on Windows.")
        if struct.calcsize("P") != 8:
            raise MecError(
                "You are running 32-bit Python. The game is 64-bit, so a 32-bit "
                "Python cannot read its memory. Install 64-bit Python.")

    def find_pid(self) -> int | None:
        self._require_windows()
        snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            raise MecError("Could not list running processes.")
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                if entry.szExeFile.lower() == PROCESS_NAME.lower():
                    return entry.th32ProcessID
                ok = _k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            _k32.CloseHandle(snap)
        return None

    def _module_base(self, pid: int) -> int | None:
        flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
        for _ in range(3):                   # this call races process startup
            snap = _k32.CreateToolhelp32Snapshot(flags, pid)
            if snap != -1:
                try:
                    entry = MODULEENTRY32W()
                    entry.dwSize = ctypes.sizeof(entry)
                    ok = _k32.Module32FirstW(snap, ctypes.byref(entry))
                    while ok:
                        if entry.szModule.lower() == PROCESS_NAME.lower():
                            return int(entry.modBaseAddr or 0)
                        ok = _k32.Module32NextW(snap, ctypes.byref(entry))
                finally:
                    _k32.CloseHandle(snap)
        return None

    def attach(self) -> None:
        """Find the game and open it. Raises MecError with a readable message."""
        self._require_windows()
        pid = self.find_pid()
        if pid is None:
            raise MecError("Mirror's Edge Catalyst is not running.")
        handle = _k32.OpenProcess(ACCESS, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == 5:
                raise MecError(
                    "Access denied opening the game. Close this tool and run it "
                    "as administrator (right-click > Run as administrator).")
            raise MecError(f"Could not open the game process (error {err}).")
        base = self._module_base(pid)
        if not base:
            _k32.CloseHandle(handle)
            raise MecError("Found the game but could not locate its module base.")
        self.handle, self.pid, self.base = handle, pid, base
        self.vtable = None

    def detach(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
        self.handle = self.pid = self.base = self.vtable = None
        self._buf = None
        self._ours.clear()

    @property
    def attached(self) -> bool:
        return self.handle is not None and self.alive()

    def alive(self) -> bool:
        """Is the process still there? (the handle outlives the process)"""
        if not self.handle:
            return False
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            return False
        return code.value == 259            # STILL_ACTIVE

    # --------------------------------------------------------------- raw i/o
    def read(self, addr: int, size: int) -> bytes | None:
        """Exactly `size` bytes, or None. Use read_partial() when scanning."""
        data = self.read_partial(addr, size)
        return data if data is not None and len(data) == size else None

    def read_partial(self, addr: int, size: int) -> bytes | None:
        """As many bytes as the OS will give us, which may be fewer than asked.

        ReadProcessMemory fails for the whole call if any page in the range is
        unreadable, but it still reports how much it managed. Demanding the full
        size and discarding anything less silently skipped megabytes of heap --
        that is why an early version of the scanner found 3 volumes where Cheat
        Engine found 61.
        """
        if not self.handle or addr <= 0 or size <= 0:
            return None
        buf = (ctypes.c_char * size)()
        got = ctypes.c_size_t(0)
        _k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf,
                               ctypes.c_size_t(size), ctypes.byref(got))
        n = got.value
        if n <= 0:
            return None
        return bytes(buf[:n])

    def write(self, addr: int, data: bytes) -> bool:
        if not self.handle or addr <= 0:
            return False
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        put = ctypes.c_size_t(0)
        ok = _k32.WriteProcessMemory(self.handle, ctypes.c_void_p(addr), buf,
                                     ctypes.c_size_t(len(data)), ctypes.byref(put))
        return bool(ok) and put.value == len(data)

    def read_u64(self, addr):
        b = self.read(addr, 8)
        return struct.unpack("<Q", b)[0] if b else None

    def read_u32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<I", b)[0] if b else None

    def read_f32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<f", b)[0] if b else None

    def read_u8(self, addr):
        b = self.read(addr, 1)
        return b[0] if b else None

    def write_f32(self, addr, value) -> bool:
        return self.write(addr, struct.pack("<f", float(value)))

    def write_u8(self, addr, value) -> bool:
        return self.write(addr, bytes([int(value) & 0xFF]))

    # ------------------------------------------------------------ memory walk
    def writable_regions(self):
        """Yield (base, size) for every committed, writable, non-guard region."""
        info = MEMORY_BASIC_INFORMATION64()
        addr = 0
        limit = 0x7FFFFFFFFFFF
        while addr < limit:
            got = _k32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr),
                                      ctypes.byref(info), ctypes.sizeof(info))
            if not got:
                break
            size = int(info.RegionSize)
            if size <= 0:
                break
            if (info.State == MEM_COMMIT
                    and (info.Protect & WRITABLE)
                    and not (info.Protect & PAGE_GUARD)):
                yield int(info.BaseAddress), size
            addr = int(info.BaseAddress) + size

    PAGE = 0x1000
    CHUNK = 1 << 20

    def _chunk_buffer(self, size: int):
        """One buffer, reused. A fresh ctypes array per chunk meant Python
        zero-filled a megabyte for every megabyte read -- gigabytes of wasted
        work over a full scan."""
        if self._buf is None or len(self._buf) < size:
            self._buf = (ctypes.c_char * size)()
        return self._buf

    def _read_chunk(self, addr: int, size: int) -> bytes | None:
        """Read into the shared buffer and hand back exactly what arrived."""
        if not self.handle:
            return None
        buf = self._chunk_buffer(size)
        got = ctypes.c_size_t(0)
        _k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf,
                               ctypes.c_size_t(size), ctypes.byref(got))
        n = got.value
        if n <= 0:
            return None
        return ctypes.string_at(buf, n)       # the one unavoidable copy

    def _ordered_regions(self, prefer: int | None):
        """Writable regions, with the one containing `prefer` first.

        Volumes cluster in the same heaps, so when the one we were using is
        streamed out, its neighbours are the best place to look. This usually
        avoids touching the rest of memory at all.
        """
        regions = list(self.writable_regions())
        if prefer:
            for i, (rb, rs) in enumerate(regions):
                if rb <= prefer < rb + rs:
                    return [regions[i]] + regions[:i] + regions[i + 1:]
        return regions

    def scan_pointers_to(self, target: int, chunk: int | None = None,
                         progress=None, cancel=None,
                         limit: int | None = None,
                         prefer: int | None = None,
                         accept=None) -> list[int]:
        """Every 8-byte-aligned address holding `target` as a pointer.

        `accept(addr)` filters hits as they are found, so `limit` counts hits
        the caller actually wants. With accept + limit=1 the scan stops at the
        first usable one instead of finishing the sweep. `prefer` searches that
        address's own region first.

        Region bases are page-aligned and chunks are multiples of 8, so an
        aligned pointer can never straddle a chunk boundary.
        """
        chunk = chunk or self.CHUNK
        needle = struct.pack("<Q", target)
        hits: list[int] = []
        regions = self._ordered_regions(prefer)
        total = sum(s for _, s in regions) or 1
        done = 0
        for rbase, rsize in regions:
            off = 0
            while off < rsize:
                if cancel is not None and cancel():
                    return hits
                want = min(chunk, rsize - off)
                data = self._read_chunk(rbase + off, want)
                if data is None:
                    # nothing readable at all here: step one page and carry on
                    step = min(self.PAGE, want)
                    off += step
                    done += step
                    continue
                base = rbase + off
                i = data.find(needle)
                while i != -1:
                    a = base + i
                    if a % 8 == 0 and (accept is None or accept(a)):
                        hits.append(a)
                        if limit is not None and len(hits) >= limit:
                            return hits
                    i = data.find(needle, i + 1)
                # a short read means the rest of this chunk was unreadable;
                # skip past the page that stopped us rather than the whole chunk
                if len(data) < want:
                    advance = ((len(data) + self.PAGE) // self.PAGE) * self.PAGE
                    advance = min(max(advance, self.PAGE), want)
                else:
                    advance = want
                off += advance
                done += advance
                if progress:
                    progress(min(done / total, 1.0))
        return hits

    # --------------------------------------------------------- sanity / checks
    def sanity(self) -> dict:
        """Cheap checks that the offsets suit this build. All read-only."""
        out = {"base": self.base, "flag_table": None, "buckets": None,
               "class_name": None, "vtable": None, "loaded": False}
        tbl = self.read_u64(self.base + FLAG_TABLE_PTR)
        out["flag_table"] = tbl
        if tbl:
            out["buckets"] = self.read_u32(tbl + 0x28)
            out["loaded"] = bool(out["buckets"] and 16 < out["buckets"] < 100000)
        ti = self.base + EXCL_TYPEINFO
        namep = self.read_u64(ti)
        if namep:
            strp = self.read_u64(namep)
            if strp:
                raw = self.read(strp, 64)
                if raw:
                    out["class_name"] = raw.split(b"\x00")[0].decode(
                        "latin1", "replace")
        default_obj = self.read_u64(ti + 0x20)
        if default_obj:
            out["vtable"] = self.read_u64(default_obj)
        return out

    # ------------------------------------------------------ progression flags
    def read_flag(self, name: str) -> int | None:
        """A progression flag's value, by name. Absent reads as 0.

        Read-only on purpose -- see this module's docstring.
        """
        return self.read_flag_by_hash(djb2a(name))

    def read_flag_by_hash(self, h: int) -> int | None:
        tbl = self.read_u64(self.base + FLAG_TABLE_PTR)
        if not tbl:
            return None
        buckets = self.read_u64(tbl + 0x20)
        nbuck = self.read_u32(tbl + 0x28)
        if not buckets or not nbuck:
            return None
        node = self.read_u64(buckets + (h % nbuck) * 8)
        while node:
            if self.read_u32(node) == h:
                return self.read_u32(node + 0x18)
            node = self.read_u64(node + 0x28)
        return 0                      # no record means 0

    # ---------------------------------------------------- exclusion volumes
    def _exclusion_vtable(self) -> int | None:
        if self.vtable:
            return self.vtable
        default_obj = self.read_u64(self.base + EXCL_TYPEINFO + 0x20)
        if not default_obj:
            return None
        self.vtable = self.read_u64(default_obj)
        return self.vtable

    def is_volume(self, addr: int) -> bool:
        """Still a live volume? Addresses get recycled, so always re-check."""
        return bool(self.vtable) and self.read_u64(addr) == self.vtable

    def _plausible_volume(self, addr: int, default_obj: int | None) -> bool:
        if addr == default_obj:
            return False
        if self.base <= addr <= self.base + MODULE_SPAN:
            return False                         # the type tables, not instances
        e = self.read_f32(addr + OFF_EXTENTS)
        return e is not None and 0 <= e < 1e6

    def find_exclusion_volumes(self, progress=None, cancel=None,
                               prefer: int | None = None) -> list[int]:
        """Every exclusion volume in memory. Walks all writable memory, so it
        is the slow path -- prefer find_one_exclusion_volume() when one will do.
        """
        vt = self._exclusion_vtable()
        if not vt:
            return []
        default_obj = self.read_u64(self.base + EXCL_TYPEINFO + 0x20)
        return [a for a in self.scan_pointers_to(vt, progress=progress,
                                                 cancel=cancel, prefer=prefer)
                if self._plausible_volume(a, default_obj)]

    def find_one_exclusion_volume(self, prefer: int | None = None,
                                  skip: set[int] | None = None,
                                  progress=None, cancel=None) -> int | None:
        """The first usable volume, stopping as soon as one is found.

        Driving the five moves only needs a single volume, so enumerating all
        ~60 is wasted work. With `prefer` (a previous volume's address) this
        normally finds one in that same heap region and never touches the rest
        of memory.
        """
        vt = self._exclusion_vtable()
        if not vt:
            return None
        default_obj = self.read_u64(self.base + EXCL_TYPEINFO + 0x20)
        skip = skip or set()

        def usable(a: int) -> bool:
            return a not in skip and self._plausible_volume(a, default_obj)

        hits = self.scan_pointers_to(vt, limit=1, prefer=prefer, accept=usable,
                                     progress=progress, cancel=cancel)
        return hits[0] if hits else None

    def read_volume(self, addr: int) -> dict | None:
        if not self.is_volume(addr):
            return None
        d = {"addr": addr,
             "extents": tuple(self.read_f32(addr + OFF_EXTENTS + i * 4)
                              for i in range(3)),
             "enabled": self.read_u8(addr + OFF_ENABLED)}
        for move, off in OFF_EXCLUDE.items():
            d[move] = bool(self.read_u8(addr + off))
        return d

    def is_ours(self, addr: int) -> bool:
        """Did we write this volume? Authored extents are tiny."""
        e = self.read_f32(addr + OFF_EXTENTS)
        return e is not None and e > OURS_ABOVE

    def set_exclusions(self, addr: int, size: float = VOLUME_SIZE, **moves) -> bool:
        """Grow a volume to cover the map and set which moves it removes.

        set_exclusions(addr, climb_up=True, wallrun=False)
        Any move not named is set to 0 (available).
        """
        unknown = set(moves) - set(OFF_EXCLUDE)
        if unknown:
            raise ValueError(f"unknown move(s): {sorted(unknown)}")
        if not self.is_volume(addr):
            return False
        for i in range(3):
            self.write_f32(addr + OFF_EXTENTS + i * 4, size)
        self.write_u8(addr + OFF_ENABLED, 1)
        for move, off in OFF_EXCLUDE.items():
            self.write_u8(addr + off, 1 if moves.get(move) else 0)
        # Read it back. Reporting a write we did not verify is how this project
        # has fooled itself three times (FINDINGS §79, §84d, §86).
        got = self.read_volume(addr)
        if not got:
            return False
        if got["extents"][0] is None or abs(got["extents"][0] - size) > 0.5:
            return False
        for move in OFF_EXCLUDE:
            if bool(got[move]) != bool(moves.get(move)):
                return False
        self._ours.add(addr)
        return True

    def release_exclusion(self, addr: int, original: dict | None = None) -> bool:
        """Undo our changes to one volume.

        With `original` (from read_volume before you touched it) the real values
        go back. Without it, the volume is left a harmless 1-unit no-op: the
        level restores its real values next time it streams the volume in.
        """
        if not self.is_volume(addr):
            return False
        if original and original.get("extents") and original["extents"][0] is not None \
                and original["extents"][0] <= OURS_ABOVE:
            for i, v in enumerate(original["extents"]):
                self.write_f32(addr + OFF_EXTENTS + i * 4, v)
            if original.get("enabled") is not None:
                self.write_u8(addr + OFF_ENABLED, original["enabled"])
            for move, off in OFF_EXCLUDE.items():
                self.write_u8(addr + off, 1 if original.get(move) else 0)
        else:
            for off in OFF_EXCLUDE.values():
                self.write_u8(addr + off, 0)
            for i in range(3):
                self.write_f32(addr + OFF_EXTENTS + i * 4, 1.0)
        self._ours.discard(addr)
        return True

    def release_tracked(self) -> int:
        """Release the volumes we know we wrote. No scan, so this is instant.

        This is the normal path. It can miss a volume whose address was recycled
        while we were not looking, which is what release_all_ours() is for.
        """
        n = 0
        for a in list(self._ours):
            if self.is_volume(a) and self.is_ours(a):
                self.release_exclusion(a)
                n += 1
            else:
                self._ours.discard(a)       # gone, or no longer ours
        return n

    def release_all_ours(self, progress=None, cancel=None) -> int:
        """Sweep every volume still carrying our signature, tracked or not.

        Walks all of memory, so it is the slow path -- use release_tracked()
        unless you need the guarantee.
        """
        n = self.release_tracked()
        for a in self.find_exclusion_volumes(progress=progress, cancel=cancel):
            if self.is_ours(a):
                self.release_exclusion(a)
                n += 1
        return n


if __name__ == "__main__":
    m = MecMemory()
    try:
        m.attach()
    except MecError as e:
        print(e)
        raise SystemExit(1)
    s = m.sanity()
    print(f"base         0x{s['base']:X}")
    print(f"flag table   0x{(s['flag_table'] or 0):X}  buckets={s['buckets']}")
    print(f"class name   {s['class_name']!r}")
    print(f"vtable       0x{(s['vtable'] or 0):X}")
    print(f"world loaded {s['loaded']}")
    if s["loaded"]:
        print(f"Unlocks_Coil = {m.read_flag('Unlocks_Coil')}")
        vols = m.find_exclusion_volumes()
        print(f"{len(vols)} exclusion volume(s)")
        for a in vols[:5]:
            print("  ", m.read_volume(a))
