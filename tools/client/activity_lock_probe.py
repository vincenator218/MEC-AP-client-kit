"""Research tool for the activity lock (docs/DLL.md section 11f).

Every activity (opportunity, delivery, security hub, side mission, story mission) is a
PamProgressionMission. Its CompletedFlag pointer (+0x48) normally leads to its real completion
flag (MiscCompleted_*, BronzeCompleted_*, SilverCompleted_*, ...). Pointing it at a flag that is 1
makes the game treat the activity as done at the next checkpoint reload: Available 0 and off the
map (an opportunity also could not be started on foot). Its real completion flag is not touched.
Putting the pointer back and reloading unlocks it. One shared lock flag serves every locked
activity. Exception: the Dead Drop Deliveries (OWPh<N>Delivery01-03) always offer one per phase,
so locking one only moves the marker to the next.

  python activity_lock_probe.py show "<mission name>"   read-only: its two flags and values
  python activity_lock_probe.py lock "<mission name>"... point CompletedFlag at the lock flag (set to 1)
  python activity_lock_probe.py unlock "<mission name>"... put those pointers back
  python activity_lock_probe.py restore                 every pointer back, lock flag to 0

Mission names are the internal ones in data/missions.json (for example "OW Opp DtPh2 02").
Pointers live in game memory only; the lock flag is a save flag (written through the client's
ProgressionWriter), so run `restore` before you stop.
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
SAVED = os.path.join(os.environ.get("TEMP", HERE), "mec_activity_lock_probe.json")

LOCK_FLAG = "Example_ExampleMission3Part1Completed"  # 0 in play, nothing reads it (DLL.md 11e census)
IMAGE = 0x140000000
VT_MISSION = 0x141C8E658
M_NAME, M_COMPLETED, M_AVAILABLE = 0x10, 0x48, 0x50
F_NAME_HASH, F_NAME = 0x10, 0x18


def _load_client():
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
    m = mm.MecMemory()
    m.attach()
    table = game.FlagTable(m)
    writer = game.ProgressionWriter(table)

    def cstr(p):
        b = m.read_partial(p, 96) if p else None
        return b.split(b"\0")[0].decode("latin1") if b else None

    def flag_name(d):
        return cstr(m.read_u64(d + F_NAME)) if d else None

    def definition(flag):
        h = mm.djb2a(flag)
        node = table.node(h)
        d = m.read_u64(node + 0x10) if node else None
        if not d or m.read_u32(d + F_NAME_HASH) != h:
            sys.exit(f"{flag}: definition not found; nothing written")
        return d

    def missions(names):
        vt = VT_MISSION - IMAGE + m.base
        found = {}
        for o in m.scan_pointers_to(vt):
            n = cstr(m.read_u64(o + M_NAME))
            if n in names:
                found.setdefault(n, []).append(o)
        for n in names:
            if len(found.get(n, [])) != 1:
                sys.exit(f"{n}: found {len(found.get(n, []))} missions, need 1; nothing written")
        return {n: v[0] for n, v in found.items()}

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "show":
        for name, o in missions(sys.argv[2:]).items():
            for label, off in (("completed", M_COMPLETED), ("available", M_AVAILABLE)):
                f = flag_name(m.read_u64(o + off))
                print(f"{name}: {label} -> {f} = {table.read(f)}")
    elif cmd == "lock":
        lock = definition(LOCK_FLAG)
        if not writer.set_flag_for_item(LOCK_FLAG, 1, "activity lock"):
            sys.exit("could not set the lock flag; nothing written")
        saved = json.load(open(SAVED)) if os.path.exists(SAVED) else {}
        for name, o in missions(sys.argv[2:]).items():
            cur = m.read_u64(o + M_COMPLETED)
            if cur != lock:
                saved[name] = {"mission": o, "original": cur}
                json.dump(saved, open(SAVED, "w"))
                m.write(o + M_COMPLETED, struct.pack("<Q", lock))
            print(f"{name}: completed -> {flag_name(m.read_u64(o + M_COMPLETED))}")
    elif cmd == "unlock":
        lock = definition(LOCK_FLAG)
        saved = json.load(open(SAVED)) if os.path.exists(SAVED) else {}
        for name in sys.argv[2:]:
            s = saved.pop(name, None)
            if s is None:
                print(f"{name}: not locked by this tool")
                continue
            if m.read_u64(s["mission"] + M_COMPLETED) == lock:
                m.write(s["mission"] + M_COMPLETED, struct.pack("<Q", s["original"]))
            print(f"{name}: completed -> {flag_name(m.read_u64(s['mission'] + M_COMPLETED))}")
        json.dump(saved, open(SAVED, "w"))
    elif cmd == "restore":
        lock = definition(LOCK_FLAG)
        saved = json.load(open(SAVED)) if os.path.exists(SAVED) else {}
        for name, s in saved.items():
            if m.read_u64(s["mission"] + M_COMPLETED) == lock:
                m.write(s["mission"] + M_COMPLETED, struct.pack("<Q", s["original"]))
            print(f"{name}: completed -> {flag_name(m.read_u64(s['mission'] + M_COMPLETED))}")
        print(f"{LOCK_FLAG} = 0: {writer.set_flag_for_item(LOCK_FLAG, 0, 'activity lock restore')}")
        if os.path.exists(SAVED):
            os.remove(SAVED)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
