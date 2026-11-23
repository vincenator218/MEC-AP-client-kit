"""
Pure functions that turn "what the server says" into "what the game should look like".

No memory access and no networking here, so all of it can be unit-tested offline.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Iterable

from ..data import (ABILITY_ITEMS, COUNT, DASH_LOCKS, DASH_UNLOCK, DASHES_BY_CONTENT_ID,
                    DOUBLE_WALLRUN_FLAG, EXCLUSION, EXCLUSION_MOVES, FLAG, ITEMS, ITEMS_BY_ID,
                    LOCATIONS_BY_ID, PROGRESSIVE_WALLRUN_NAME, LocationInfo, dash_unlock_name)
from .dash_lock import DashesPlan

Reader = Callable[[str], "int | None"]
ALL_MOVES = tuple(EXCLUSION_MOVES.values())


def location_check(loc: LocationInfo) -> Callable[[Reader], bool]:
    """A function that says, given a flag reader, whether `loc` is done (GridLeak counts)."""
    if loc.rule == COUNT:
        return lambda read: sum((read(f) or 0) >= 1 for f in loc.flags) >= loc.at_least
    raise ValueError(f"unknown rule {loc.rule!r} for {loc.name}")


def received_names(item_ids: Iterable[int]) -> Counter:
    return Counter(ITEMS_BY_ID[i].name for i in item_ids if i in ITEMS_BY_ID)


def dash_unlocked(have: Counter, dash: str) -> bool:
    return have[dash_unlock_name(dash)] > 0


def unlocked_dashes(have: Counter) -> list[str]:
    return [ITEMS[n].dash for n in have if ITEMS[n].kind == DASH_UNLOCK]


def dash_checks(content_id: int, run_cs: int) -> set[int]:
    """Location ids one finished run earns: the dash's finish check, plus every star tier whose
    time it beat. A time exactly on the threshold is counted (not verified in game).
    Whether the dash is unlocked is the caller's question (client.on_dash_finished)."""
    return {l.id for l in DASHES_BY_CONTENT_ID.get(content_id, ())
            if l.tier == 0 or run_cs <= l.max_cs}


def stars_checked(location_ids: Iterable[int]) -> int:
    """How many star checks are among these: the goal counts them."""
    return sum(1 for i in location_ids if i in LOCATIONS_BY_ID and LOCATIONS_BY_ID[i].tier > 0)


def desired_flags(have: Counter, slot_data: dict) -> dict[str, tuple[int, str]]:
    """flag -> (value, reason) for every progression flag the client should hold."""
    out: dict[str, tuple[int, str]] = {}
    for name in have:
        info = ITEMS[name]
        if info.kind == FLAG:
            out[info.flag] = (1, f"received {name}")
    if have[PROGRESSIVE_WALLRUN_NAME] >= 2:
        out[DOUBLE_WALLRUN_FLAG] = (1, f"received {PROGRESSIVE_WALLRUN_NAME} x2")
    if slot_data.get("revert_skill_tree_purchases"):
        for flag in [ITEMS[n].flag for n in ABILITY_ITEMS] + [DOUBLE_WALLRUN_FLAG]:
            out.setdefault(flag, (0, "not received yet (bought from the skill tree?)"))
    if slot_data.get("hard_dash_lock"):
        for dash, (_cid, flag) in DASH_LOCKS.items():
            name = dash_unlock_name(dash)
            out[flag] = (1, f"received {name}") if have[name] else (0, f"{dash} is locked")
    return out


def dash_lock_pointers(slot_data: dict) -> dict[int, str] | None:
    """ContentId -> lock flag for every dash, when the slot uses the hard lock."""
    if not slot_data.get("hard_dash_lock"):
        return None
    return {cid: flag for cid, flag in DASH_LOCKS.values()}


def blocked_moves(have: Counter) -> dict[str, bool]:
    """move -> True while its item has not been received."""
    blocked = {m: True for m in ALL_MOVES}
    for name in have:
        info = ITEMS[name]
        if info.kind == EXCLUSION:
            blocked[EXCLUSION_MOVES[info.flag]] = False
    if have[PROGRESSIVE_WALLRUN_NAME] >= 1:
        blocked["wallrun"] = False
    return blocked


def build_plan(item_ids: Iterable[int], watch: dict[int, LocationInfo], slot_data: dict,
               writes_allowed: bool) -> DashesPlan:
    have = received_names(item_ids)
    plan = DashesPlan(watch={lid: location_check(loc) for lid, loc in watch.items()},
                      writes_allowed=writes_allowed)
    if writes_allowed:
        plan.flags = desired_flags(have, slot_data)
        plan.blocked = blocked_moves(have)
        plan.dash_locks = dash_lock_pointers(slot_data)
    return plan
