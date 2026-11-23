"""Research tool for the hard dash lock (docs/DLL.md section 11e).

Points each dash's PamNamedChallengeData.UnlockFlag (+0x40, null in the shipped game) at the
PamProgressionFlag definition of its own flag, from data/dash_unlock_flags.json. While that flag
is 0 the dash is off the map and cannot be started; at 1 it is back. Both show at the next level
load (reload a checkpoint).

  python dash_unlock_probe.py plan                 read-only: each dash, its flag, value, pointer
  python dash_unlock_probe.py lock                 write the 22 pointers (only where still null)
  python dash_unlock_probe.py unlock <ap_index...> set those dashes' flags to 1
  python dash_unlock_probe.py relock <ap_index...> set those dashes' flags back to 0
  python dash_unlock_probe.py restore              pointers back to null, all 22 flags to 0

Pointers live in game memory only. Flags are written through the client's ProgressionWriter (its
one write path), and the game's autosave keeps them in the save: run `restore` before quitting a
test on a save you care about.
"""
from __future__ import annotations

import importlib.util
import json
import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))

IMAGE = 0x140000000
VT_SERVER_NAMED_CHALLENGE = 0x141C7EC70
ENT_DATA = 0x80
D_UNLOCK_FLAG, D_CONTENT_ID = 0x40, 0x98
NODE_DEFINITION = 0x10
F_NAME_HASH = 0x10


def _load_client():
    """Import mec_memory and the main world's client/game.py without installing the apworld."""
    pkg = types.ModuleType("_mec_client")
    pkg.__path__ = []
    sys.modules["_mec_client"] = pkg
    mods = {}
    for name, path in (("mec_memory", os.path.join(HERE, "mec_memory.py")),
                       ("game", os.path.join(KIT, "apworld", "mirrors_edge_catalyst", "client", "game.py"))):
        spec = importlib.util.spec_from_file_location("_mec_client." + name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_mec_client." + name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["mec_memory"], mods["game"]


def main() -> None:
    mm, game = _load_client()
    rows = json.load(open(os.path.join(KIT, "data", "dash_unlock_flags.json"), encoding="utf-8"))["dashes"]
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    picked = set(sys.argv[2:])

    m = mm.MecMemory()
    m.attach()
    table = game.FlagTable(m)
    writer = game.ProgressionWriter(table)

    def definition(flag: str) -> int:
        h = mm.djb2a(flag)
        node = table.node(h)
        d = m.read_u64(node + NODE_DEFINITION) if node else None
        if not d or m.read_u32(d + F_NAME_HASH) != h:
            sys.exit(f"{flag}: definition not found; nothing more written")
        return d

    data = {}
    if cmd in ("plan", "lock", "restore"):
        print("scanning for dashes...")
        vt = VT_SERVER_NAMED_CHALLENGE - IMAGE + m.base
        for e in m.scan_pointers_to(vt):
            d = m.read_u64(e + ENT_DATA)
            cid = m.read_u32(d + D_CONTENT_ID) if d else None
            if cid is not None:
                data[f"{cid:08x}"] = d
        missing = [r["name"] for r in rows if r["content_id"] not in data]
        if missing:
            sys.exit(f"dashes not found in memory: {missing}; nothing written")

    for r in rows:
        flag, name = r["unlock_flag"], r["name"]
        if cmd == "plan":
            ptr = m.read_u64(data[r["content_id"]] + D_UNLOCK_FLAG)
            state = "ours" if ptr == definition(flag) else ("null" if ptr == 0 else f"{ptr:#x}")
            print(f"{r['ap_index']:>2} {name:<24} {flag:<46} value {table.read(flag)} pointer {state}")
        elif cmd == "lock":
            dd, d = data[r["content_id"]], definition(flag)
            if m.read_u64(dd + D_UNLOCK_FLAG) == 0:
                m.write(dd + D_UNLOCK_FLAG, struct.pack("<Q", d))
            print(f"{name:<24} -> {flag}: {m.read_u64(dd + D_UNLOCK_FLAG) == d}")
        elif cmd in ("unlock", "relock") and str(r["ap_index"]) in picked:
            value = 1 if cmd == "unlock" else 0
            print(f"{name:<24} {flag} = {value}: {writer.set_flag_for_item(flag, value, 'dash lock test')}")
        elif cmd == "restore":
            dd = data[r["content_id"]]
            if m.read_u64(dd + D_UNLOCK_FLAG) == definition(flag):
                m.write(dd + D_UNLOCK_FLAG, struct.pack("<Q", 0))
            ok = writer.set_flag_for_item(flag, 0, "dash lock test restore")
            print(f"{name:<24} pointer {m.read_u64(dd + D_UNLOCK_FLAG):#x}, {flag} = 0: {ok}")


if __name__ == "__main__":
    main()
