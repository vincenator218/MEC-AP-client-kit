#!/usr/bin/env python3
"""
read_save.py -- print progression flags from a PROF_SAVE, with names.

Names come from data/flag_names.json (all 2376 known flags). Records whose
hash isn't in that list are printed as hex.

Usage:
    python read_save.py PROF_SAVE                       # every record, every section
    python read_save.py PROF_SAVE --grep Unlocks_       # filter by name substring
    python read_save.py PROF_SAVE --name "SilverCompleted_Drone Works"
    python read_save.py PROF_SAVE --json out.json       # dump {section: {name_or_hash: value}}

A save has one ProgressionManagerData* section per linked platform account;
they can differ, and which one the game loads varies, so check all of them.
A flag with no record in the save reads as 0 in game ("absence = 0").
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from set_flag import djb2a, find_progression_sections  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = os.path.join(HERE, "..", "..", "data", "flag_names.json")


def load_names(path):
    table = json.load(open(path, encoding="utf-8"))
    return {int(h, 16): n for n, h in table.items()}


def read_sections(data):
    out = []
    for key, vstart, vallen in find_progression_sections(data):
        blob = data[vstart:vstart + vallen]
        count = struct.unpack_from("<I", blob, 144)[0]
        recs = [struct.unpack_from("<II", blob, 148 + i * 8) for i in range(count)]
        out.append((key, recs))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_file")
    ap.add_argument("--grep", default=None)
    ap.add_argument("--name", action="append", default=[])
    ap.add_argument("--json", default=None)
    ap.add_argument("--names", default=NAMES, help="flag_names.json path")
    a = ap.parse_args()

    names = load_names(a.names)
    data = open(a.save_file, "rb").read()
    sections = read_sections(data)
    if not sections:
        print("no ProgressionManagerData section found -- not a PROF_SAVE?")
        return 1

    dump = {}
    for idx, (key, recs) in enumerate(sections):
        vals = {h: v for h, v in recs}
        label = lambda h: names.get(h, f"0x{h:08X}")
        dump[key] = {label(h): v for h, v in recs}
        if a.json:
            continue
        print(f"== {key}: {len(recs)} records")
        if a.name:
            for n in a.name:
                h = djb2a(n.encode("utf-8"))
                print(f"  {n} (0x{h:08X}) = {vals.get(h, 0)}{'' if h in vals else '  (no record)'}")
            continue
        for h, v in sorted(recs, key=lambda r: label(r[0])):
            n = label(h)
            if a.grep is None or a.grep.lower() in n.lower():
                print(f"  {n} = {v}")

    if a.json:
        json.dump(dump, open(a.json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"wrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
