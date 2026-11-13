"""
Item and location tables, built from the kit's machine-readable data.

`items.json` and `locations.json` are copied into this package's `data/` folder by
`tools/build_apworld.py`, so the kit's `data/` stays the single source of truth.
Everything here is computed at import time from those files and never depends on
options: Archipelago needs the name -> id maps to be fixed for the whole datapackage.

Changes from the raw kit data, all deliberate (see apworld/README.md):

* `Wallrun` (ExcludeWallrun) and `DoubleWallrun` (Unlocks_DoubleWallrun) are merged into
  one `Progressive Wallrun`: the first copy lifts ExcludeWallrun, the second writes
  Unlocks_DoubleWallrun.
* The 324 per-GUID GridLeak locations are replaced by per-district *count* locations
  ("Downtown GridLeaks 5"), so the bundle size can be an option without IDs moving.
* The 32 opportunities that have an unlock item are detected by `<name>_CompletedTime`,
  not by `MiscCompleted_<name>`: the unlock item writes `MiscCompleted_<name>`, so
  detecting on it would send the check the moment the item arrived.
* The 22 dashes come from `named_challenges.json`, not from a flag: they have none. Each
  has a finish check and three star checks, detected from the "challenge finished" message
  that the injected DLL (dll/) forwards. Ids are 1330000 + 10 * ap_index + tier.
"""
from __future__ import annotations

import json
import pkgutil
import re
from dataclasses import dataclass, field

GAME = "Mirror's Edge Catalyst"


def _load_json(name: str):
    raw = pkgutil.get_data(__name__.rpartition(".")[0], f"data/{name}")
    if raw is None:
        raise FileNotFoundError(f"data/{name} is missing from the apworld")
    return json.loads(raw.decode("utf-8"))


RAW_ITEMS: list[dict] = _load_json("items.json")
RAW_LOCATIONS: list[dict] = _load_json("locations.json")
RAW_CHALLENGES: list[dict] = _load_json("named_challenges.json")["challenges"]

# ------------------------------------------------------------------------- items
# grant kinds the client understands
FLAG = "flag"                    # write a progression flag (grant_method says when it bites)
EXCLUSION = "exclusion"          # clear one Exclude* byte on a movement volume
PROGRESSIVE_WALLRUN = "progressive_wallrun"
MACGUFFIN = "macguffin"
FILLER = "filler"

PROGRESSIVE_WALLRUN_NAME = "Progressive Wallrun"
PROGRESSIVE_WALLRUN_ID = 1320115
DOUBLE_WALLRUN_FLAG = "Unlocks_DoubleWallrun"
MACGUFFIN_NAME = "Data Shard"
MACGUFFIN_ID = 1320400
FILLER_NAME = "Gridnet Static"
FILLER_ID = 1320401

# exclusion field -> mec_memory move key
EXCLUSION_MOVES = {
    "ExcludeVault": "springboard",
    "ExcludeHeaveUp": "climb_up",
    "ExcludeHang": "ledge_hang",
    "ExcludeWallrun": "wallrun",
    "ExcludeMagrope": "mag_rope",
}

_MERGED_INTO_PROGRESSIVE = {"ExcludeWallrun", DOUBLE_WALLRUN_FLAG}


@dataclass(frozen=True)
class ItemInfo:
    id: int
    name: str
    kind: str
    group: str
    flag: str = ""               # FLAG items: the progression flag; EXCLUSION: the field
    grant_method: str = ""       # table_write_reload / live_entity / persistent_entity / exclusion_volume
    live_status: str = ""
    count: int = 1               # copies in the pool


def _build_items() -> dict[str, ItemInfo]:
    out: dict[str, ItemInfo] = {}
    for r in RAW_ITEMS:
        if r["flag"] in _MERGED_INTO_PROGRESSIVE:
            continue
        if r["grant_method"] == "exclusion_volume":
            kind = EXCLUSION
        elif r["grant_method"] in ("table_write_reload", "live_entity", "persistent_entity"):
            kind = FLAG
        else:
            continue                              # "unknown": nothing reliable to do
        out[r["name"]] = ItemInfo(r["id"], r["name"], kind, r["group"], r["flag"],
                                  r["grant_method"], r["live_status"])
    out[PROGRESSIVE_WALLRUN_NAME] = ItemInfo(
        PROGRESSIVE_WALLRUN_ID, PROGRESSIVE_WALLRUN_NAME, PROGRESSIVE_WALLRUN,
        "traversal (exclusion volume)", "ExcludeWallrun", "exclusion_volume", "tested", count=2)
    out[MACGUFFIN_NAME] = ItemInfo(MACGUFFIN_ID, MACGUFFIN_NAME, MACGUFFIN, "goal")
    out[FILLER_NAME] = ItemInfo(FILLER_ID, FILLER_NAME, FILLER, "filler")
    return out


ITEMS: dict[str, ItemInfo] = _build_items()
ITEMS_BY_ID: dict[int, ItemInfo] = {i.id: i for i in ITEMS.values()}

TRAVERSAL_ITEMS = [n for n, i in ITEMS.items() if i.kind in (EXCLUSION, PROGRESSIVE_WALLRUN)]
SIDE_MISSION_UNLOCKS = [n for n, i in ITEMS.items() if i.group == "side mission"]
OPPORTUNITY_UNLOCKS = [n for n, i in ITEMS.items() if i.group.startswith("opportunity")]
ABILITY_ITEMS = [n for n, i in ITEMS.items()
                 if i.kind == FLAG and i.flag.startswith("Unlocks_")]

# ----------------------------------------------------------------------- locations
# detection rules the client understands
GE1 = "ge1"                      # value >= 1
EQ1 = "eq1"                      # value == 1
NONZERO = "nonzero"              # a _CompletedTime went from 0 to anything
COUNT = "count"                  # at least N of `flags` are >= 1
DASH = "dash"                    # a "challenge finished" event from the DLL, not a flag


@dataclass(frozen=True)
class LocationInfo:
    id: int
    name: str
    category: str
    district: str
    rule: str
    flag: str = ""
    flags: tuple[str, ...] = ()  # COUNT only
    at_least: int = 0            # COUNT only
    content_id: int = 0          # DASH only: the challenge's ContentId
    tier: int = 0                # DASH only: 0 = finished, 1-3 = stars
    max_cs: int = 0              # DASH stars: a run this fast or faster (hundredths of a second)
    parent: str = ""             # DASH stars: the finish location, whose requirements it shares


# option key -> kit category. Only these are ever created; story missions and the
# mission collectibles need a save that has not finished the story.
CATEGORIES = {
    "side_missions": "Side Mission",
    "opportunities": "Opportunity",
    "countdown_deliveries": "Opportunity (Delivery)",
    "security_hubs": "Security Hub",
    "grid_nodes": "Grid Node",
    "billboards": "Billboard Hack",
    "electronic_parts": "Electronic Part",
    "surveillance_recordings": "Surveillance Recording",
    "documents": "Document",
    "secret_bags": "Secret Bag",
}

GRIDLEAK_CATEGORY = "GridLeak"
GRIDLEAK_BASE_IDS = {           # + n, n = 1..(leaks in that district)
    "Downtown": 1310500,
    "Anchor": 1310600,
    "The View": 1310700,
    "Rezoning": 1310800,
}

_RULES = {
    "value == 1": EQ1,
    "record present with value >= 1 (any ProgressionManagerData section)": GE1,
    "'<mission>_CompletedTime' changes from 0 to non-zero (the client never writes it)": NONZERO,
}

# every flag an unlock item writes; a location must never be detected on one of these
UNLOCK_FLAGS = {ITEMS[n].flag for n in SIDE_MISSION_UNLOCKS + OPPORTUNITY_UNLOCKS}


def _detection(r: dict) -> tuple[str, str]:
    det = r["detection"]
    if det.startswith("value == 1 (also sets"):          # opportunities
        if r["flag"] in UNLOCK_FLAGS:
            return NONZERO, r["flag"].removeprefix("MiscCompleted_") + "_CompletedTime"
        return EQ1, r["flag"]                              # interventions: no unlock item
    return _RULES[det], r["flag"]


def _build_locations():
    by_name: dict[str, LocationInfo] = {}
    leaks: dict[str, list[dict]] = {}
    # every kit row, created or not, so requirement rows can name any of them
    kit_rows: dict[str, dict] = {}
    for r in RAW_LOCATIONS:
        kit_rows[r["name"]] = r
        if r["category"] == GRIDLEAK_CATEGORY:
            leaks.setdefault(r["district"], []).append(r)
            continue
        if r["category"] not in CATEGORIES.values() or not r["default"]:
            continue                       # story-only content: never created
        rule, flag = _detection(r)
        assert flag not in UNLOCK_FLAGS, r["name"]
        by_name[r["name"]] = LocationInfo(r["id"], r["name"], r["category"],
                                          r["district"], rule, flag)
    for district, rows in leaks.items():
        rows.sort(key=lambda x: x["id"])
        flags = tuple(x["flag"] for x in rows)
        for n in range(1, len(rows) + 1):
            name = gridleak_location_name(district, n)
            by_name[name] = LocationInfo(GRIDLEAK_BASE_IDS[district] + n, name,
                                         GRIDLEAK_CATEGORY, district, COUNT,
                                         flags=flags, at_least=n)
    return by_name, leaks, kit_rows


def gridleak_location_name(district: str, n: int) -> str:
    return f"{district} GridLeaks {n}"


DASH_CATEGORY = "Dash"
DASH_BASE_ID = 1330000
DASH_TIERS = 3


def dash_location_name(dash: str, tier: int = 0) -> str:
    if tier == 0:
        return f"Dash - {dash}"
    return f"Dash - {dash} - {tier} Star{'s' if tier > 1 else ''}"


def _build_dashes() -> dict[str, LocationInfo]:
    out: dict[str, LocationInfo] = {}
    for c in RAW_CHALLENGES:
        if c["kind"] != "dash":
            continue
        cid, base = int(c["content_id"], 16), DASH_BASE_ID + 10 * c["ap_index"]
        finish = dash_location_name(c["name"])
        out[finish] = LocationInfo(base, finish, DASH_CATEGORY, c["district"] or "", DASH,
                                   content_id=cid)
        for tier in range(1, DASH_TIERS + 1):
            name = dash_location_name(c["name"], tier)
            out[name] = LocationInfo(base + tier, name, DASH_CATEGORY, c["district"] or "", DASH,
                                     content_id=cid, tier=tier,
                                     max_cs=c["star_thresholds_cs"][str(tier)], parent=finish)
    return out


LOCATIONS, GRIDLEAKS_BY_DISTRICT, KIT_LOCATION_ROWS = _build_locations()
DASHES: dict[str, LocationInfo] = _build_dashes()
LOCATIONS.update(DASHES)
LOCATIONS_BY_ID: dict[int, LocationInfo] = {l.id: l for l in LOCATIONS.values()}
DASHES_BY_CONTENT_ID: dict[int, list[LocationInfo]] = {}
for _l in DASHES.values():
    DASHES_BY_CONTENT_ID.setdefault(_l.content_id, []).append(_l)

# ------------------------------------------------------------- final activity map
@dataclass(frozen=True)
class FinalActivity:
    key: str                     # option value
    item: str                    # its unlock item (taken out of the pool)
    location: str                # its check (becomes the goal event instead)


_GRID_NODE_LOCATIONS = {          # side-mission unlock flag -> grid node check (ITEMS.md)
    "SilverCompleted_Grid Node Downtown": "Grid Node - Downtown",
    "SilverCompleted_Grid Node Construction": "Grid Node - Rezoning",
    "SilverCompleted_Grid Node The View": "Grid Node - The View",
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _build_final_activities() -> dict[str, FinalActivity]:
    by_flag = {l.flag: l.name for l in LOCATIONS.values()}
    out: dict[str, FinalActivity] = {}
    for name in SIDE_MISSION_UNLOCKS + OPPORTUNITY_UNLOCKS:
        flag = ITEMS[name].flag
        if flag in _GRID_NODE_LOCATIONS:
            loc = _GRID_NODE_LOCATIONS[flag]
        elif flag.startswith("SilverCompleted_"):
            loc = by_flag[flag.removeprefix("SilverCompleted_") + "_CompletedTime"]
        else:
            loc = by_flag[flag.removeprefix("MiscCompleted_") + "_CompletedTime"]
        key = _slug(name.split(" - ", 1)[1])
        assert key not in out, key
        out[key] = FinalActivity(key, name, loc)
    return out


FINAL_ACTIVITIES: dict[str, FinalActivity] = _build_final_activities()
DEFAULT_FINAL_ACTIVITY = "top_of_the_world"   # the one side-mission unlock tested end to end
