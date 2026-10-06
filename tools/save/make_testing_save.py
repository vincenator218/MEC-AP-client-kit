#!/usr/bin/env python3
"""
make_testing_save.py -- build a PROF_SAVE for crowdsourcing ability logic.

The point of this save: a tester can replay **any** mission or activity from the
menu, starts with **no** abilities at all, and has a pile of XP, so they can buy
exactly the ability that unblocked them and report it back.

What it does:
  * every `SilverCompleted_` / `BronzeCompleted_` / `MiscCompleted_` -> 1
    (side missions, opportunities and deliveries all appear in their menus)
  * their `_CompletedTime` / `_CompletedTimestampPart1/2` -> 0
    (nothing shows as "done", so a real completion still records a real time)
  * every `Unlocks_*` -> 0 and all four MAG Rope flags -> 0 (no movement, no
    combat, no gear -- the starting 4 stamina bars only)
  * `XP_Gained` / `XP` -> --xp (default 500000), `XP_Used` -> 0
  * story state is never touched: `GoldCompleted_*`, their own times/timers and
    every other `CriticalPathProgression_*`. The city stays open and fast travel
    works, so a tester can reach anything.
  * `--clear-collectibles` also zeroes every collectible location and counter
    (use it when starting from a story-complete save rather than the AP seed).

Records that don't exist yet are inserted, and the same number of zero bytes is
trimmed from the end of the file, so the file size never changes. Both CRC32
checksums are recomputed.

Usage:
    python make_testing_save.py PROF_SAVE_seed --out PROF_SAVE_testing
    python make_testing_save.py PROF_SAVE --out PROF_SAVE_testing --clear-collectibles
    python make_testing_save.py PROF_SAVE --out x --xp 100000 --dry-run

The game must be fully closed while you write over a live save. Keep a backup.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from save_checksum import recompute_checksums          # noqa: E402
from set_flag import djb2a, find_progression_sections  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data")

MAGROPE = ["CriticalPathProgression_HasCollectedMagRopeSwing",
           "CriticalPathProgression_HasCollectedMagRopePullUp",
           "CriticalPathProgression_HasCollectedMagRopePullDown",
           "CriticalPathProgression_HasCollectedMagRopeLineConnector"]
TIME_SUFFIXES = ["_CompletedTime", "_CompletedTimestampPart1", "_CompletedTimestampPart2"]
ACTIVITY_PREFIXES = ("SilverCompleted_", "BronzeCompleted_", "MiscCompleted_")


def targets(args):
    """Return {name: (value, kind)} for everything this save should change."""
    names = json.load(open(os.path.join(DATA, "flag_names.json"), encoding="utf-8"))
    have = set(names)
    out = {}

    story_bases = {n[len("GoldCompleted_"):] for n in names if n.startswith("GoldCompleted_")}

    def is_story(name):
        if name.startswith("GoldCompleted_"):
            return True
        for suf in TIME_SUFFIXES + ["_Timer", "_Available"]:
            if name.endswith(suf) and name[: -len(suf)] in story_bases:
                return True
        return False

    def add(name, value, kind):
        if name in have and not is_story(name):
            out[name] = (value, kind)

    # 1. no abilities
    for n in names:
        if n.startswith("Unlocks_"):
            add(n, 0, "ability cleared")
    for n in MAGROPE:
        add(n, 0, "MAG Rope cleared")

    # 2. every activity unlocked in its menu, with no time recorded
    for n in names:
        if n.startswith(ACTIVITY_PREFIXES):
            add(n, 1, "activity unlocked")
            base = n.split("_", 1)[1]
            for suf in TIME_SUFFIXES:
                add(base + suf, 0, "time cleared")

    # 3. XP to spend
    add("XP_Gained", args.xp, "XP")
    add("XP", args.xp, "XP")
    add("XP_Used", 0, "XP")

    # 4. optional clean slate for collectibles
    if args.clear_collectibles:
        locs = json.load(open(os.path.join(DATA, "locations.json"), encoding="utf-8"))
        activity_cats = {"Side Mission", "Opportunity", "Opportunity (Delivery)",
                         "Story Mission", "Misc Activity"}
        for loc in locs:
            if loc["category"] in activity_cats:
                continue           # handled above; don't undo the unlocks
            add(loc["flag"], 0, "collectible cleared")
        for n in names:
            if n.startswith(("IntelCollectiblesWorld_", "IntelCollectiblesMission_",
                             "GreenCollectiblesStory_", "GreenCollectiblesMission_",
                             "RunnerBagsMission_")):
                add(n, 0, "counter cleared")
            if n.startswith("Collectables_") and n.endswith("Collected"):
                add(n, 0, "counter cleared")
    return out


def apply_all(data, want, dry_run=False):
    """Patch or insert every {name: (value, kind)}; keeps the file size constant."""
    by_hash = {djb2a(n.encode("utf-8")): (n, v) for n, (v, _k) in want.items()}
    sections = find_progression_sections(data)
    print(f"sections: {[s[0] for s in sections]}")
    patched = inserted = 0
    grown = 0

    for key, vstart, vallen in sorted(sections, key=lambda s: s[1], reverse=True):
        # work on one bytearray copy of the section and write it back once, so a
        # later insert can never overwrite an earlier in-place patch
        blob = bytearray(data[vstart:vstart + vallen])
        count = struct.unpack_from("<I", blob, 144)[0]
        seen = {}
        for i in range(count):
            h, _v = struct.unpack_from("<II", blob, 148 + i * 8)
            seen[h] = i

        sec_patched = 0
        to_insert = []
        for h, (_name, val) in by_hash.items():
            if h in seen:
                off = 148 + seen[h] * 8
                old = struct.unpack_from("<I", blob, off + 4)[0]
                if old != val:
                    struct.pack_into("<I", blob, off + 4, val)
                    sec_patched += 1
            else:
                to_insert.append((h, val))

        if to_insert:
            add_bytes = b"".join(struct.pack("<II", h, v) for h, v in to_insert)
            blob = (blob[:144] + struct.pack("<I", count + len(to_insert))
                    + blob[148:148 + count * 8] + add_bytes + blob[148 + count * 8:])

        if not dry_run:
            grown += len(blob) - vallen
            data[vstart:vstart + vallen] = blob
            struct.pack_into("<I", data, vstart - 4, len(blob))

        print(f"  {key}: {count} records, {sec_patched} patched, {len(to_insert)} inserted")
        patched += sec_patched
        inserted += len(to_insert)

    if grown:
        tail = bytes(data[-grown:])
        if any(b != 0 for b in tail):
            raise SystemExit("REFUSING: the bytes to trim off the end aren't all zero")
        del data[-grown:]
    return patched, inserted


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--xp", type=int, default=500_000, help="XP to hand the tester (default 500000)")
    ap.add_argument("--clear-collectibles", action="store_true",
                    help="also zero every collectible and counter (for a story-complete base save)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    want = targets(a)
    kinds = {}
    for _n, (_v, k) in want.items():
        kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(want)} flags targeted: " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))

    data = bytearray(open(a.save_file, "rb").read())
    size = len(data)
    patched, inserted = apply_all(data, want, a.dry_run)

    if a.dry_run:
        print(f"dry run: would patch {patched}, insert {inserted}. Nothing written.")
        return 0

    recompute_checksums(data)
    assert len(data) == size, "file size changed -- refusing to write"
    open(a.out, "wb").write(data)
    print(f"wrote {a.out} ({len(data)} bytes, unchanged size). "
          f"{patched} patched, {inserted} inserted. Checksums recomputed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
