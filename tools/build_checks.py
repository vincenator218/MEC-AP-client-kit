"""build_checks.py -- generate the Archipelago location list for Mirror's Edge Catalyst.

Input : data/flag_names.json (all 2376 progression flag names -> hash)
Output: data/locations.json, data/locations.csv

Every location is one save/live flag. Hash = djb2a(name) -- the same hash used as
the key in PROF_SAVE records and in the live flag table (docs/MEMORY.md).

Run:  python tools/build_checks.py
"""
import csv, json, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
GT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "flag_names.json")
OUT = os.path.join(HERE, "..", "data")

BASE_ID = 1_310_000   # proposed; per-game IDs only need to be unique inside this world

ZONES = {
    "RzRdz": ("Rezoning", "Rdz Development Zone"),
    "RzOt": ("Rezoning", "Omnistat Tunnels"),
    "DtTd": ("Downtown", "Triumvirate Drive"),
    "DtCh": ("Downtown", "Charter Hill"),
    "DtCy": ("Downtown", "Centurian Yards"),
    "DtCp": ("Downtown", "Concord Plaza"),
    "AcCv": ("Anchor", "Crystal Valley"),
    "AcSh": ("Anchor", "Shimmering Heights"),
    "AcEv": ("Anchor", "Eden Village"),
    "VwOp": ("The View", "Ocean Pier"),
    "VwRb": ("The View", "Regatta Bay"),
    "Trainstation": ("Zephyr Transit Hub", "Zephyr Transit Hub"),
    "TheShard": ("The Shard", "The Shard"),
    "GridLeaks": ("Special", "Grid Leak audio (Noah/Icarus)"),
}
GL_DISTRICT = {"Downtown": "Downtown", "Anchor": "Anchor", "TheView": "The View", "Construction": "Rezoning"}
ZONE_ORDER = list(ZONES)


def djb2a(s):
    h = 5381
    for b in s.encode("utf-8"):
        h = ((h * 33) ^ b) & 0xFFFFFFFF
    return h


def main():
    src = json.load(open(GT, encoding="utf-8"))
    names = sorted(src.keys() if isinstance(src, dict) and "flags" not in src else {f["name"] for f in src["flags"]})
    have = set(names)
    locs = []

    def add(block, cat, name, flag, district, area, rule, default, note=""):
        assert flag in have, flag
        locs.append(dict(block=block, category=cat, name=name, flag=flag,
                         hash=f"0x{djb2a(flag):08X}", district=district, area=area,
                         detection=rule, default=default, note=note))

    COLLECT = "record present with value >= 1 (any ProgressionManagerData section)"

    # ---- GridLeaks (324) -------------------------------------------------
    for pre, dist in GL_DISTRICT.items():
        fl = [n for n in names if n.startswith(pre + "GridLeaks_")]
        for i, n in enumerate(fl, 1):
            add(0, "GridLeak", f"GridLeak - {dist} {i:03d}", n, dist, "", COLLECT, True)

    # ---- zone-prefixed collectibles -------------------------------------
    def zoned(block, cat, label, rx):
        per = {}
        for n in names:
            m = re.match(rx, n)
            if m:
                per.setdefault(m.group(1), []).append(n)
        for z in ZONE_ORDER:
            for i, n in enumerate(per.pop(z, []), 1):
                d, a = ZONES[z]
                chip = re.search(r"_Chip(\d+)Taken$", n)
                tag = f"Chip {chip.group(1)}" if chip else f"{i:02d}"
                add(block, cat, f"{label} - {a} {tag}", n, d, a, COLLECT, True)
        assert not per, per

    zoned(1000, "Electronic Part", "Electronic Part", r"ElectronicParts([A-Za-z]+)_Chip\d+Taken$")
    zoned(2000, "Surveillance Recording", "Recording", r"AudioPickup([A-Za-z]+)_")
    zoned(3000, "Document", "Document",
          r"Intel(?!Collectibles)([A-Za-z]+)_")   # excludes IntelCollectiblesWorld/Mission
    zoned(4000, "Secret Bag", "Secret Bag", r"SecretBag([A-Za-z]+)_")

    # ---- Security hubs (8) ----------------------------------------------
    HUB = {"Anchor2": ("Anchor", True), "Anchor3": ("Anchor", True),
           "Downtown1": ("Downtown", True), "Downtown3": ("Downtown", True),
           "Downtown4": ("Downtown", True), "TheView1": ("The View", True),
           "MischiefMaker": ("", False), "Payback": ("", False)}   # district unknown
    for key, (dist, on) in HUB.items():
        add(5000, "Security Hub", f"Security Hub - {key}", f"SecurityHubsCompleted_SecHub{key}",
            dist, "", "value == 1", on,
            "" if on else "cleared inside a story mission; pre-completed if the seed save finishes the story")

    # ---- Grid nodes (4) -------------------------------------------------
    for key, dist, on in [("Rezoning", "Rezoning", True), ("Dt", "Downtown", True),
                          ("View", "The View", True), ("Anc", "Anchor", False)]:
        add(5100, "Grid Node", f"Grid Node - {dist}", f"GridNodes_{key}Completed", dist, "",
            "value == 1", on,
            "" if on else "Grid Node Anchor is a story (Gold) mission")

    # ---- Billboard hacks (12) --------------------------------------------
    BB = {"anc": "Anchor", "dt": "Downtown", "rz": "Rezoning", "tvbb": "The View"}
    for n in names:
        m = re.match(r"HackableBillboards_([a-z]+?)(\d+)$", n)
        if m:
            d = BB[m.group(1)]
            add(5200, "Billboard Hack", f"Billboard - {d} {int(m.group(2)):02d}", n, d, "",
                "value == 1", True)

    # ---- Opportunity missions (40) ---------------------------------------
    OPP = {"Anc": "Anchor", "Dt": "Downtown", "Ct": "Rezoning", "Vw": "The View"}
    for n in names:
        m = re.match(r"MiscCompleted_OW Opp (Anc|Dt|Ct|Vw)Ph(\d) (\d\d)$", n)
        if m:
            d = OPP[m.group(1)]
            add(6000, "Opportunity Mission", f"Opportunity - {d} Ph{m.group(2)} #{m.group(3)}", n, d, "",
                "value == 1 (also sets '<name>_CompletedTime')", True,
                "Ct assumed = Construction/Rezoning (unverified)" if m.group(1) == "Ct" else "")

    MISSION_RULE = "'<mission>_CompletedTime' changes from 0 to non-zero (the client never writes it)"

    # ---- Side missions (Silver) -----------------------------------------
    SIDE = ["An Ear to the Ground", "Birdman's Delivery", "Break And Entry", "Caught in the Web",
            "Complete Coverage", "Drone Works", "Exit Strategy", "Finger on the Pulse",
            "The Meta Grid", "Top of the World", "Two Pigeons With One Stone"]
    for m in SIDE:
        add(7000, "Side Mission", f"Side Mission - {m}", f"{m}_CompletedTime", "", "",
            MISSION_RULE, True, f"unlock/replay flag: SilverCompleted_{m}")

    # ---- Deliveries (Bronze, 18) ----------------------------------------
    for ph in range(2, 8):
        for k in range(1, 4):
            m = f"OWPh{ph}Delivery0{k}"
            add(8000, "Delivery", f"Delivery - Phase {ph} #{k}", f"{m}_CompletedTime", "", "",
                MISSION_RULE, True, f"also BronzeCompleted_{m}")

    # ---- Other Bronze (tutorial / intro opportunity content) -------------
    for m in ["OPPDT01Delivery", "OPPDT02_Delivery", "OPPANC01Delivery", "Dt02Delivery01",
              "OPPDT01OpportunityMissions", "OPPDT02RunnerBeatdown", "Anc01Opportunity", "OWPh3OppMiss02"]:
        add(8100, "Misc Activity", f"Activity - {m}", f"{m}_CompletedTime", "", "",
            MISSION_RULE, False, "in-game name/where unknown; verify before enabling")

    # ---- Story missions (Gold, main only) -------------------------------
    STORY = ["Back in the Game", "Be Like Water", "Benefactor", "Birdman's Route", "Encroachment",
             "Family Matters", "Fly Trap", "Grid Node Anchor", "Kingdom", "Mischief Maker",
             "Old Friends", "Payback", "Prisoner X", "Release", "Reunion", "Sanctuary",
             "Savant Extraordinaire", "The Shard", "Tickets, Please", "Vive La Resistance"]
    for m in STORY:
        add(9000, "Story Mission", f"Story - {m}", f"{m}_CompletedTime", "", "",
            MISSION_RULE, False, "only usable if the story is NOT pre-completed in the seed save")

    # ---- Mission-internal collectibles (count flags, not per-item) --------
    for n in names:
        for pre, cat in [("GreenCollectiblesStory_", "Story Collectible Set"),
                         ("GreenCollectiblesMission_", "Mission Green Orbs"),
                         ("RunnerBagsMission_", "Mission Runner Bag"),
                         ("IntelCollectiblesMission_", "Mission Document")]:
            if n.startswith(pre):
                add(9500, cat, f"{cat} - {n[len(pre):]}", n, "", "",
                    "value is a COUNT; decide threshold (e.g. >= 1) before enabling", False,
                    "inside story missions; replay-only if story pre-completed")

    # ---- assign IDs ------------------------------------------------------
    nxt = Counter()
    for L in locs:
        L["id"] = BASE_ID + L["block"] + nxt[L["block"]]
        nxt[L["block"]] += 1
    assert len({L["id"] for L in locs}) == len(locs)
    assert len({L["name"] for L in locs}) == len(locs)
    assert len({L["hash"] for L in locs}) == len(locs), "hash collision"

    cols = ["id", "name", "category", "district", "area", "default", "flag", "hash", "detection", "note"]
    with open(os.path.join(OUT, "locations.json"), "w", encoding="utf-8") as f:
        json.dump([{c: L[c] for c in cols} for L in locs], f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "locations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(locs)

    by = Counter((L["category"], L["default"]) for L in locs)
    for (c, d), k in sorted(by.items(), key=lambda x: x[0][0]):
        print(f"{c:25s} {'ON ' if d else 'off'} {k}")
    print("total", len(locs), " default-on", sum(L["default"] for L in locs))


if __name__ == "__main__":
    main()
