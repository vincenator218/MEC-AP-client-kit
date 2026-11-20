"""
Item and location tables for Mirror's Edge Catalyst Dashes: the dashes, the GridLeaks, and the
moves and abilities that unlock them. No side missions, no opportunities.

The kit's `data/items.json`, `data/locations.json` and `data/named_challenges.json` are copied
into this package's `data/` folder by `tools/build_apworld.py`. Everything is computed at import
time and never depends on options, so the name -> id maps are fixed for the whole datapackage.

Ids: this is its own game, so its ids only have to be unique inside it. Shared things keep the
ids they have in the Mirror's Edge Catalyst world, so the client code is the same for both:
  * abilities 1320000-1320035 and the movement items 1320110-1320115 (items.json);
  * dash checks 1330000 + 10 * ap_index + tier (tier 0 = finished, 1-3 = stars);
  * GridLeak count checks: a district base + n ("Downtown GridLeaks 10").
New here: the Dash Unlock items, 1320500 + ap_index.
"""
from __future__ import annotations

import json
import pkgutil
from dataclasses import dataclass

GAME = "Mirror's Edge Catalyst Dashes"


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
FLAG = "flag"                    # write a progression flag (an ability), then apply it through the DLL
EXCLUSION = "exclusion"          # clear one Exclude* byte on a movement volume
PROGRESSIVE_WALLRUN = "progressive_wallrun"
DASH_UNLOCK = "dash_unlock"      # nothing in the game: the client counts that dash's checks
FILLER = "filler"

PROGRESSIVE_WALLRUN_NAME = "Progressive Wallrun"
PROGRESSIVE_WALLRUN_ID = 1320115
DOUBLE_WALLRUN_FLAG = "Unlocks_DoubleWallrun"
FILLER_NAME = "Gridnet Static"
FILLER_ID = 1320401
DASH_UNLOCK_BASE_ID = 1320500

# exclusion field -> mec_memory move key
EXCLUSION_MOVES = {
    "ExcludeVault": "springboard",
    "ExcludeHeaveUp": "climb_up",
    "ExcludeHang": "ledge_hang",
    "ExcludeWallrun": "wallrun",
    "ExcludeMagrope": "mag_rope",
}
_MERGED_INTO_PROGRESSIVE = {"ExcludeWallrun", DOUBLE_WALLRUN_FLAG}
# items.json groups that are abilities or moves; everything else (side-mission and
# opportunity unlocks) belongs to the other world
_ABILITY_METHODS = ("live_entity", "persistent_entity")


@dataclass(frozen=True)
class ItemInfo:
    id: int
    name: str
    kind: str
    group: str
    flag: str = ""               # FLAG: the progression flag; EXCLUSION: the volume field
    grant_method: str = ""       # live_entity / persistent_entity / exclusion_volume
    count: int = 1               # copies in the pool
    dash: str = ""               # DASH_UNLOCK: the dash's display name


def dash_unlock_name(dash: str) -> str:
    return f"Dash Unlock - {dash}"


def _dashes_in_order() -> list[dict]:
    return sorted((c for c in RAW_CHALLENGES if c["kind"] == "dash"), key=lambda c: c["ap_index"])


def _build_items() -> dict[str, ItemInfo]:
    out: dict[str, ItemInfo] = {}
    for r in RAW_ITEMS:
        if r["flag"] in _MERGED_INTO_PROGRESSIVE:
            continue
        if r["grant_method"] == "exclusion_volume":
            out[r["name"]] = ItemInfo(r["id"], r["name"], EXCLUSION, r["group"], r["flag"], r["grant_method"])
        elif r["grant_method"] in _ABILITY_METHODS and r["flag"].startswith("Unlocks_"):
            out[r["name"]] = ItemInfo(r["id"], r["name"], FLAG, r["group"], r["flag"], r["grant_method"])
    out[PROGRESSIVE_WALLRUN_NAME] = ItemInfo(
        PROGRESSIVE_WALLRUN_ID, PROGRESSIVE_WALLRUN_NAME, PROGRESSIVE_WALLRUN,
        "traversal (exclusion volume)", "ExcludeWallrun", "exclusion_volume", count=2)
    for c in _dashes_in_order():
        name = dash_unlock_name(c["name"])
        out[name] = ItemInfo(DASH_UNLOCK_BASE_ID + c["ap_index"], name, DASH_UNLOCK, "dash unlock",
                             dash=c["name"])
    out[FILLER_NAME] = ItemInfo(FILLER_ID, FILLER_NAME, FILLER, "filler")
    return out


ITEMS: dict[str, ItemInfo] = _build_items()
ITEMS_BY_ID: dict[int, ItemInfo] = {i.id: i for i in ITEMS.values()}

TRAVERSAL_ITEMS = [n for n, i in ITEMS.items() if i.kind in (EXCLUSION, PROGRESSIVE_WALLRUN)]
ABILITY_ITEMS = [n for n, i in ITEMS.items() if i.kind == FLAG]
DASH_UNLOCKS = [n for n, i in ITEMS.items() if i.kind == DASH_UNLOCK]
# abilities that change how Faith moves; the rest are combat, Focus and gear
MOVEMENT_ABILITIES = [n for n in ABILITY_ITEMS if ITEMS[n].group == "movement"]

# ----------------------------------------------------------------------- locations
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
    dash: str = ""               # DASH only: the dash's display name


GRIDLEAK_CATEGORY = "GridLeak"
GRIDLEAK_BASE_IDS = {           # + n, n = 1..(leaks in that district), as in the other world
    "Downtown": 1310500,
    "Anchor": 1310600,
    "The View": 1310700,
    "Rezoning": 1310800,
}


def gridleak_location_name(district: str, n: int) -> str:
    return f"{district} GridLeaks {n}"


def gridleak_steps(total: int, size: int, percent: int = 99) -> list[int]:
    """The counts that are checks in a district of `total` leaks: every `size` leaks, up to
    `percent` of the district and always below the total, so no district ever needs every last
    leak (a leak that is hard to reach or missed cannot block the seed)."""
    if size <= 0:
        return []
    cap = min(total - 1, total * percent // 100)
    return list(range(size, cap + 1, size))


def _build_gridleaks():
    by_name: dict[str, LocationInfo] = {}
    leaks: dict[str, list[dict]] = {}
    kit_rows: dict[str, dict] = {}
    for r in RAW_LOCATIONS:
        if r["category"] != GRIDLEAK_CATEGORY:
            continue
        kit_rows[r["name"]] = r
        leaks.setdefault(r["district"], []).append(r)
    for district, rows in leaks.items():
        rows.sort(key=lambda x: x["id"])
        flags = tuple(x["flag"] for x in rows)
        for n in range(1, len(rows) + 1):
            name = gridleak_location_name(district, n)
            by_name[name] = LocationInfo(GRIDLEAK_BASE_IDS[district] + n, name, GRIDLEAK_CATEGORY,
                                         district, COUNT, flags=flags, at_least=n)
    return by_name, leaks, kit_rows


DASH_CATEGORY = "Dash"
DASH_BASE_ID = 1330000
DASH_TIERS = 3


def dash_location_name(dash: str, tier: int = 0) -> str:
    if tier == 0:
        return f"Dash - {dash}"
    return f"Dash - {dash} - {tier} Star{'s' if tier > 1 else ''}"


def _build_dashes() -> dict[str, LocationInfo]:
    out: dict[str, LocationInfo] = {}
    for c in _dashes_in_order():
        cid, base = int(c["content_id"], 16), DASH_BASE_ID + 10 * c["ap_index"]
        finish = dash_location_name(c["name"])
        out[finish] = LocationInfo(base, finish, DASH_CATEGORY, c["district"] or "", DASH,
                                   content_id=cid, dash=c["name"])
        for tier in range(1, DASH_TIERS + 1):
            name = dash_location_name(c["name"], tier)
            out[name] = LocationInfo(base + tier, name, DASH_CATEGORY, c["district"] or "", DASH,
                                     content_id=cid, tier=tier,
                                     max_cs=c["star_thresholds_cs"][str(tier)], parent=finish,
                                     dash=c["name"])
    return out


LOCATIONS, GRIDLEAKS_BY_DISTRICT, KIT_LOCATION_ROWS = _build_gridleaks()
DASHES: dict[str, LocationInfo] = _build_dashes()
LOCATIONS.update(DASHES)
LOCATIONS_BY_ID: dict[int, LocationInfo] = {l.id: l for l in LOCATIONS.values()}
DASHES_BY_CONTENT_ID: dict[int, list[LocationInfo]] = {}
for _l in DASHES.values():
    DASHES_BY_CONTENT_ID.setdefault(_l.content_id, []).append(_l)
DASH_NAMES: list[str] = [c["name"] for c in _dashes_in_order()]
