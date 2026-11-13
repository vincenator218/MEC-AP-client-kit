#!/usr/bin/env python3
"""
verify_dll_addresses.py -- check data/dll_addresses.json against the running game. READ-ONLY.

The addresses an injected DLL would use (docs/DLL.md) come mostly from mecmp's source and have
not been confirmed on this project's build. This reads each one from the running game and says
whether it is what the source says it should be. It never writes to the game: there is no write
call anywhere in this file, only MecMemory.read.

    python tools/client/verify_dll_addresses.py            # game running, ideally loaded into the city
    python tools/client/verify_dll_addresses.py --bytes    # also print the first bytes of each function

What each kind of entry is checked against:

  slot      the 8 bytes at the slot equal the expected function (both rebased)   strong
  code      the bytes at the function equal mecmp's build-check bytes            strong
  typeinfo  the TypeInfo's class name reads back as the expected name            strong
  vtable    its first entry points inside the game image                         weak
  function  the address is inside the game image                                 weak
  global    the pointer is readable (some are null outside a level)              weak

A "strong" pass is evidence the build matches. A "weak" pass only says nothing is obviously wrong.
Exit code: 0 every strong check passed, 1 a check failed, 2 the game could not be read.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

from mec_memory import MecError, MecMemory

IMAGE_BASE = 0x140000000
HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE.parent.parent / "data" / "dll_addresses.json"
STRONG = {"slot", "code", "typeinfo"}


def image_size(m: MecMemory) -> int | None:
    """SizeOfImage from the PE header of the running module."""
    e_lfanew = m.read_u32(m.base + 0x3C)
    if not e_lfanew:
        return None
    return m.read_u32(m.base + e_lfanew + 0x50)


def class_name(m: MecMemory, ti: int) -> str | None:
    """TypeInfo -> data -> name pointer -> string (as mecmp's typeinfo.cpp and MecMemory.sanity read it)."""
    data = m.read_u64(ti)
    namep = m.read_u64(data) if data else None
    raw = m.read_partial(namep, 64) if namep else None      # a short name may end near a page edge
    return raw.split(b"\x00")[0].decode("latin1", "replace") if raw else None


def typeinfo_count(m: MecMemory, head: int, limit: int = 50000) -> int:
    ti, n = m.read_u64(head), 0
    while ti and n < limit:
        n += 1
        ti = m.read_u64(ti + 8)
    return n


def hexs(b: bytes | None) -> str:
    return " ".join(f"{x:02X}" for x in b) if b else "(unreadable)"


def check(m: MecMemory, e: dict, size: int, show_bytes: bool) -> tuple[str, str]:
    """(PASS | FAIL | weak | info, detail) for one entry."""
    kind = e["kind"]
    if kind == "constant":
        return "info", f"value {e['value']} (not an address)"
    delta = m.base - IMAGE_BASE
    addr = int(e["va"], 16) + delta

    def inside(a: int | None) -> bool:
        return a is not None and m.base <= a < m.base + size

    if kind == "slot":
        got, want = m.read_u64(addr), int(e["expected"], 16) + delta
        if got == want:
            return "PASS", f"holds {e['expected']}"
        if got is None:
            shown = "unreadable"
        elif inside(got):
            shown = f"0x{got - delta:X}"                          # as an image VA, comparable to expected
        else:
            shown = f"0x{got:X} (outside the image: another mod's hook?)"
        return "FAIL", f"holds {shown}, expected {e['expected']}"
    if kind == "code":
        want = bytes.fromhex(e["bytes"])
        got = m.read(addr + e.get("skip", 0), len(want))
        return ("PASS", "bytes match") if got == want else ("FAIL", f"starts {hexs(got)}, expected {e['bytes']}")
    if kind == "typeinfo":
        got = class_name(m, addr)
        if got == e["class_name"]:
            return "PASS", f"class {got}"
        return "FAIL", f"class {got!r}, expected {e['class_name']!r}"
    if kind == "vtable":
        first = m.read_u64(addr)
        return ("weak", "first entry is in the image") if inside(first) else ("FAIL", "first entry is not in the image")
    if kind == "function":
        if not inside(addr):
            return "FAIL", "not in the image"
        detail = "in the image"
        if show_bytes:
            detail += f"; starts {hexs(m.read(addr, 16))}"
        return "weak", detail
    if kind == "global":
        v = m.read_u64(addr)
        if v is None:
            return "FAIL", "unreadable"
        return "weak", "null (fine outside a level)" if v == 0 else "set"
    return "info", f"unknown kind {kind!r}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check the DLL addresses against the running game (read-only).")
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON, help="address file (default: data/dll_addresses.json)")
    ap.add_argument("--bytes", action="store_true", help="print the first 16 bytes of each function")
    args = ap.parse_args(argv)

    doc = json.loads(args.json.read_text(encoding="utf-8"))
    m = MecMemory()
    try:
        m.attach()
    except MecError as e:
        print(e)
        return 2
    try:
        size = image_size(m)
        if not size:
            print("Could not read the game's PE header.")
            return 2
        print(f"Game base 0x{m.base:X}, image size 0x{size:X}, mecmp commit {doc['mecmp']['commit'][:7]}\n")
        head = next((e for e in doc["entries"] if e["name"] == "TypeInfo list head"), None)
        if head:
            n = typeinfo_count(m, int(head["va"], 16) - IMAGE_BASE + m.base)
            print(f"TypeInfo list: {n} entries (mecmp waits for >= 9000 before checking)\n")

        failed = strong_passed = 0
        for e in doc["entries"]:
            status, detail = check(m, e, size, args.bytes)
            tag = e.get("origin", "")
            print(f"{status:5} {e['kind']:9} {e.get('va', ''):12} {e['name'][:46]:46} [{tag}] {detail}")
            failed += status == "FAIL"
            strong_passed += status == "PASS" and e["kind"] in STRONG
        strong_total = sum(e["kind"] in STRONG for e in doc["entries"])
        print(f"\n{strong_passed}/{strong_total} strong checks passed, {failed} failed.")
        if failed:
            print("A failure means this build differs from the one mecmp was made for, or the game "
                  "is not fully started. Load into the city and run it again before concluding.")
        return 1 if failed else 0
    finally:
        m.detach()


if __name__ == "__main__":
    sys.exit(main())
