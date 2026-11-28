#!/usr/bin/env python3
"""
make_seed_save.py -- turn a story-complete PROF_SAVE into an Archipelago
starting save.

What it does, by default:
  * every `Unlocks_*` ability flag -> 0            (abilities become AP items)
  * MAG Rope uses are KEPT by default (--clear-magrope to zero them). The rope is
    gated at runtime by the exclusion volume's ExcludeMagrope byte now, not by the
    save -- see docs/MEMORY.md §5. Clearing it here would double-gate it.
  * XP_Gained / XP_Used -> 0                       (--keep-xp to skip)
  * the 22 hard dash lock flags (data/dash_unlock_flags.json) -> 0, so every dash
    starts locked for the Dashes world (they are never set in normal play)
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
    python make_seed_save.py PROF_SAVE --out seed.sav --clear-magrope --keep-xp
    python make_seed_save.py PROF_SAVE --out seed.sav --default-locations-only
    python make_seed_save.py PROF_SAVE --out seed.sav --dry-run

The game must be fully closed while you write over a live save. Keep a backup.
"""
import argparse
import json
import os
import struct
import sys

try:                                   # inside the Dashes apworld's client package (client/new_save.py)
    from .save_checksum import recompute_checksums
    from .set_flag import djb2a, find_progression_sections
except ImportError:                    # run as a script from tools/save
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


def load_data():
    """The three data files, read from the kit's data/ folder (the client passes its own copies)."""
    def load(name):
        return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    return load("flag_names.json"), load("locations.json"), load("dash_unlock_flags.json")


def targets(names, locs, locks, clear_magrope=False, keep_xp=False, default_locations_only=False,
            keep_codex=False):
    """Return {name: kind} for every flag the seed should clear."""
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

    # the Dashes world's hard dash lock: each dash's own lock flag (docs/DLL.md 11e)
    for row in locks["dashes"]:
        add(row["unlock_flag"], "dash lock")

    # The rope is kept by default: the client gates it live via ExcludeMagrope
    # (MEMORY.md §5), so clearing it in the save would gate it twice.
    if clear_magrope:
        for n in MAGROPE:
            add(n, "magrope")
    if not keep_xp:
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
    if not keep_codex:
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
        if loc["default"] or not default_locations_only:
            flag = loc["flag"]
            add(flag, "location")
            if flag.endswith("_CompletedTime"):
                base = flag[: -len("_CompletedTime")]
                for suf in MISSION_SUFFIXES:
                    add(base + suf, "location")
    return out


def clear(data, want, dry_run=False):
    """Set every targeted flag that is not 0 to 0 in `data` (a bytearray of a PROF_SAVE), in every
    ProgressionManagerData section. Returns (values changed, {kind: count}, [(section, records,
    changed)]). Checksums are not recomputed here (see write_seed_save)."""
    by_hash = {djb2a(n.encode("utf-8")): (n, kind) for n, kind in want.items()}
    changed_total, per_kind, sections = 0, {}, []
    for key, vstart, vallen in find_progression_sections(data):
        count = struct.unpack_from("<I", data, vstart + 144)[0]
        changed = 0
        for i in range(count):
            off = vstart + 148 + i * 8
            h, v = struct.unpack_from("<II", data, off)
            hit = by_hash.get(h)
            if hit and v != 0:
                if not dry_run:
                    struct.pack_into("<I", data, off + 4, 0)
                changed += 1
                per_kind[hit[1]] = per_kind.get(hit[1], 0) + 1
        sections.append((key, count, changed))
        changed_total += changed
    return changed_total, per_kind, sections


def seed_save_bytes(data, want):
    """A seed save made from `data` (bytes of a PROF_SAVE): (new bytes, values changed, per kind).
    The size never changes and both checksums are recomputed."""
    out = bytearray(data)
    changed, per_kind, _ = clear(out, want)
    recompute_checksums(out)
    if len(out) != len(data):
        raise ValueError("file size changed -- refusing to write")
    return bytes(out), changed, per_kind


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--clear-magrope", action="store_true",
                    help="also zero the MAG Rope flags (default: keep the rope owned, "
                         "because the client gates it live via ExcludeMagrope)")
    ap.add_argument("--keep-xp", action="store_true", help="leave XP as it is")
    ap.add_argument("--default-locations-only", action="store_true",
                    help="only clear locations that are on by default (leaves mission collectibles as they are)")
    ap.add_argument("--keep-codex", action="store_true",
                    help="leave IntelCollectiblesWorld_* / GreenCollectiblesStory_* counters alone")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    a = ap.parse_args()

    want = targets(*load_data(), clear_magrope=a.clear_magrope, keep_xp=a.keep_xp,
                   default_locations_only=a.default_locations_only, keep_codex=a.keep_codex)
    print(f"{len(want)} flags targeted "
          f"({sum(1 for k in want.values() if k == 'ability')} abilities, "
          f"{sum(1 for k in want.values() if k == 'location')} locations, "
          f"{sum(1 for k in want.values() if k == 'activity')} activity completions, "
          f"{sum(1 for k in want.values() if k == 'counter')} counters, "
          f"{sum(1 for k in want.values() if k == 'magrope')} MAG Rope, "
          f"{sum(1 for k in want.values() if k == 'xp')} XP)")

    data = bytearray(open(a.save_file, "rb").read())
    size = len(data)
    changed_total, per_kind, sections = clear(data, want, a.dry_run)
    for key, count, changed in sections:
        print(f"  {key}: {count} records, {changed} cleared")

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
