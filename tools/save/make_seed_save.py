#!/usr/bin/env python3
"""
make_seed_save.py -- turn a story-complete PROF_SAVE into an Archipelago
starting save.

What it does, by default:
  * every `Unlocks_*` ability flag -> 0            (abilities become AP items)
  * MAG Rope uses -> 0                             (--keep-magrope to skip)
  * XP_Gained / XP_Used -> 0                       (--keep-xp to skip)
  * every location flag in data/locations.json -> 0 (use
    --default-locations-only for just the default-on ones), the mission-collectible
    and codex counters (--keep-codex to skip), plus every
    non-story completion flag (`SilverCompleted_`, `BronzeCompleted_`,
    `MiscCompleted_`) and the `_CompletedTime` / `_CompletedTimestampPart1/2`
    that go with them, so all the checks are available again
  * story state is NEVER touched: `GoldCompleted_*`, those missions' own times
    and timers, and every `CriticalPathProgression_*` except the rope. The city
    stays open.

It only changes values of records that already exist; nothing is inserted and the
file size never changes. Both CRC32 checksums are recomputed.

Usage:
    python make_seed_save.py PROF_SAVE --out PROF_SAVE_seed
    python make_seed_save.py PROF_SAVE --out seed.sav --keep-magrope --keep-xp
    python make_seed_save.py PROF_SAVE --out seed.sav --default-locations-only
    python make_seed_save.py PROF_SAVE --out seed.sav --dry-run

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
XP = ["XP_Gained", "XP_Used", "XP"]
MISSION_SUFFIXES = ["_CompletedTime", "_CompletedTimestampPart1", "_CompletedTimestampPart2"]


def targets(args):
    """Return {name: kind} for every flag the seed should clear."""
    names = json.load(open(os.path.join(DATA, "flag_names.json"), encoding="utf-8"))
    locs = json.load(open(os.path.join(DATA, "locations.json"), encoding="utf-8"))
    out = {}

    # story state is never touched: GoldCompleted_<m> and that mission's own
    # timers/timestamps, plus every CriticalPathProgression_* except the rope.
    story_bases = {n[len("GoldCompleted_"):] for n in names if n.startswith("GoldCompleted_")}
    def is_story(name):
        if name.startswith("GoldCompleted_"):
            return True
        for suf in MISSION_SUFFIXES + ["_Timer", "_Available"]:
            if name.endswith(suf) and name[: -len(suf)] in story_bases:
                return True
        return False

    def add(name, kind):
        if name in names and not is_story(name):
            out[name] = kind

    for n in names:
        if n.startswith("Unlocks_"):
            add(n, "ability")

    if not args.keep_magrope:
        for n in MAGROPE:
            add(n, "magrope")
    if not args.keep_xp:
        for n in XP:
            add(n, "xp")

    # every non-story completion flag: side missions, opportunities, deliveries,
    # security hubs, grid nodes, and the times that go with them
    for n in names:
        if n.startswith(("SilverCompleted_", "BronzeCompleted_", "MiscCompleted_")):
            add(n, "activity")
            base = n.split("_", 1)[1]
            for suf in MISSION_SUFFIXES:
                add(base + suf, "activity")

    # codex / story collectible counters (not AP locations, but a fresh seed
    # shouldn't show them as partly collected)
    if not args.keep_codex:
        for n in names:
            if n.startswith(("IntelCollectiblesWorld_", "IntelCollectiblesMission_",
                             "GreenCollectiblesStory_", "GreenCollectiblesMission_",
                             "RunnerBagsMission_")):
                add(n, "counter")
            # aggregate "x collected" totals the World Progression screen shows
            # (the matching Collectables_Total* capacities are left alone)
            if n.startswith("Collectables_") and n.endswith("Collected"):
                add(n, "counter")

    # the locations themselves (collectibles, hubs, nodes, billboards, ...)
    for loc in locs:
        if loc["default"] or not args.default_locations_only:
            flag = loc["flag"]
            add(flag, "location")
            if flag.endswith("_CompletedTime"):
                base = flag[: -len("_CompletedTime")]
                for suf in MISSION_SUFFIXES:
                    add(base + suf, "location")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-magrope", action="store_true", help="leave the grapple owned")
    ap.add_argument("--keep-xp", action="store_true", help="leave XP as it is")
    ap.add_argument("--default-locations-only", action="store_true",
                    help="only clear locations that are on by default (leaves mission collectibles as they are)")
    ap.add_argument("--keep-codex", action="store_true",
                    help="leave IntelCollectiblesWorld_* / GreenCollectiblesStory_* counters alone")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    a = ap.parse_args()

    want = targets(a)
    by_hash = {djb2a(n.encode("utf-8")): (n, kind) for n, kind in want.items()}
    print(f"{len(want)} flags targeted "
          f"({sum(1 for k in want.values() if k == 'ability')} abilities, "
          f"{sum(1 for k in want.values() if k == 'location')} locations, "
          f"{sum(1 for k in want.values() if k == 'activity')} activity completions, "
          f"{sum(1 for k in want.values() if k == 'counter')} counters, "
          f"{sum(1 for k in want.values() if k == 'magrope')} MAG Rope, "
          f"{sum(1 for k in want.values() if k == 'xp')} XP)")

    data = bytearray(open(a.save_file, "rb").read())
    size = len(data)
    changed_total = 0
    per_kind = {}

    for key, vstart, vallen in find_progression_sections(data):
        blob_off = vstart
        count = struct.unpack_from("<I", data, blob_off + 144)[0]
        changed = 0
        for i in range(count):
            off = blob_off + 148 + i * 8
            h, v = struct.unpack_from("<II", data, off)
            hit = by_hash.get(h)
            if hit and v != 0:
                if not a.dry_run:
                    struct.pack_into("<I", data, off + 4, 0)
                changed += 1
                per_kind[hit[1]] = per_kind.get(hit[1], 0) + 1
        print(f"  {key}: {count} records, {changed} cleared")
        changed_total += changed

    print("cleared by kind:", per_kind if per_kind else "(nothing)")
    if a.dry_run:
        print("dry run: nothing written")
        return 0

    recompute_checksums(data)
    assert len(data) == size, "file size changed -- refusing to write"
    open(a.out, "wb").write(data)
    print(f"wrote {a.out} ({len(data)} bytes, unchanged size). {changed_total} values set to 0. Checksums recomputed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
