#!/usr/bin/env python3
"""
clear_all_unlocks.py -- set every Unlocks_* ability flag that is 1 back to 0,
in every ProgressionManagerData* section. In-place value flips only: no
records are added or removed, file size and offsets are unchanged. Prints
every change it makes.

Use it to build a "no abilities" starting save for a randomizer. Tested: a
save cleared this way plays normally and nothing is re-granted by mission
state at load (see docs/SAVE_FILE.md).

Usage:
    python clear_all_unlocks.py PROF_SAVE --out PROF_SAVE.cleared

The game must be fully closed while you edit. Keep a backup.
"""
import argparse
import struct
import sys

from save_checksum import recompute_checksums

UNLOCKS_NAMES = [
    "Unlocks_BreachDoors", "Unlocks_CityAlertDisrupt", "Unlocks_CityAlertSafePositions",
    "Unlocks_Coil", "Unlocks_CombatFluency", "Unlocks_CombatRecovery", "Unlocks_CombatReticle",
    "Unlocks_CombatScavengeLevel", "Unlocks_Disrupter_IncreaseRange",
    "Unlocks_Disrupter_Increase_AngleOfEffect", "Unlocks_Disruptor_Extra_Battery",
    "Unlocks_Disruptor_Overload", "Unlocks_Disruptor_StunHumans", "Unlocks_Disruptor_StunMech",
    "Unlocks_DoubleWallrun", "Unlocks_ExtendedComboVulnerability", "Unlocks_ExtendedSlide",
    "Unlocks_FastClimb", "Unlocks_FlowAttack", "Unlocks_FlowAttack_PowerAttack",
    "Unlocks_FlowAttack_Special_PowerAttack", "Unlocks_Focus", "Unlocks_Focus_FlowAttackFluency",
    "Unlocks_Focus_ReachFlow_Increase", "Unlocks_Focus_ReachFlow_IncreaseExtra",
    "Unlocks_GetSpeedAttack", "Unlocks_Glove", "Unlocks_HandToHandCombat",
    "Unlocks_HardLandingLowDrain", "Unlocks_ImpactAttack_PowerAttack",
    "Unlocks_ImpactAttack_Special_PowerAttack", "Unlocks_ImpactMomentum",
    "Unlocks_IncreasedHealth0", "Unlocks_IncreasedHealth1", "Unlocks_IncreasedHealth2",
    "Unlocks_IncreasedHealth3", "Unlocks_IncreasedHealth4", "Unlocks_LowDrainAtLowSpeed",
    "Unlocks_LowDrainInFlow", "Unlocks_LowerHealthEnforcer", "Unlocks_LowerHealthProtector",
    "Unlocks_LowerHealthSentinel", "Unlocks_LowerHealthShockProtector", "Unlocks_MoveEnemyAttack",
    "Unlocks_MoveEnemyBack", "Unlocks_Placeholder", "Unlocks_PositionalAdvantage",
    "Unlocks_QuickTurn", "Unlocks_ScavengeLevel", "Unlocks_Shift", "Unlocks_ShiftFluency",
    "Unlocks_SkillMoveInvulnerabilityLevel0", "Unlocks_SkillMoveInvulnerabilityLevel1",
    "Unlocks_SkillMoveInvulnerabilityLevel2", "Unlocks_SkillWindowSkillRoll",
    "Unlocks_SkillWindowSpringboard", "Unlocks_SkillWindowWallClimb", "Unlocks_StartBoost",
]


def djb2a(data: bytes) -> int:
    h = 5381
    for b in data:
        h = ((h * 33) ^ b) & 0xFFFFFFFF
    return h


def read_u32(data, pos):
    return struct.unpack_from("<I", data, pos)[0]


def find_progression_sections_named(data, start_pos=46):
    n = len(data)
    pos = start_pos
    sections = []
    while pos < n - 4:
        count = read_u32(data, pos)
        if count == 0 or count > 5000:
            break
        bpos = pos + 4
        entries = []
        ok = True
        for _ in range(count):
            r = parse_kv_entry_named(data, bpos)
            if r is None:
                ok = False
                break
            key, vstart, vallen, newpos = r
            entries.append((key, vstart, vallen))
            bpos = newpos
        if not ok:
            break
        for key, vstart, vallen in entries:
            if key.startswith("ProgressionManagerData"):
                sections.append((key, vstart, vallen))
        pos = bpos
    return sections


def parse_kv_entry_named(data, pos):
    n = len(data)
    if pos + 8 > n:
        return None
    keylen = read_u32(data, pos + 4)
    if keylen == 0 or keylen > 256 or pos + 8 + keylen > n:
        return None
    key = data[pos + 8: pos + 8 + keylen]
    if not key.endswith(b"\x00") or not all(32 <= c < 127 for c in key[:-1]):
        return None
    keystr = key[:-1].decode("latin1")
    vpos = pos + 8 + keylen
    if vpos + 4 > n:
        return None
    vallen = read_u32(data, vpos)
    if vallen > 5_000_000 or vpos + 4 + vallen > n:
        return None
    return keystr, vpos + 4, vallen, vpos + 4 + vallen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save_file")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    target_hashes = {djb2a(n.encode("utf-8")): n for n in UNLOCKS_NAMES}

    data = bytearray(open(args.save_file, "rb").read())
    original_size = len(data)
    sections = find_progression_sections_named(data)
    print(f"found sections: {[s[0] for s in sections]}")

    total_cleared = 0
    for key, vstart, vallen in sections:
        blob = data[vstart:vstart + vallen]
        count = struct.unpack_from("<I", blob, 144)[0]
        cleared_here = []
        for i in range(count):
            off = 148 + i * 8
            h, v = struct.unpack_from("<II", blob, off)
            if h in target_hashes and v != 0:
                struct.pack_into("<I", data, vstart + off + 4, 0)
                cleared_here.append((target_hashes[h], v))
                total_cleared += 1
        if cleared_here:
            print(f"  {key}: cleared {len(cleared_here)} flag(s):")
            for name, old in sorted(cleared_here):
                print(f"      {name}: {old} -> 0")
        else:
            print(f"  {key}: none of the 58 Unlocks_* names found set here")

    if total_cleared == 0:
        print("NOTHING CLEARED anywhere -- not writing output.", file=sys.stderr)
        return 1

    assert len(data) == original_size, "file size changed -- aborting, something is wrong"
    recompute_checksums(data)
    open(args.out, "wb").write(data)
    print(f"\nwrote {args.out} ({original_size} bytes, unchanged size). "
          f"{total_cleared} Unlocks_* flag-instances cleared to 0 total. Header/body checksums recomputed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
