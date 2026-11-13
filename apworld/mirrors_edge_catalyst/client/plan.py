"""
Pure functions that turn "what the server says" into "what the game should look like".

No memory access and no networking here, so all of it can be unit-tested offline.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Iterable

from ..data import (ABILITY_ITEMS, COUNT, DASHES_BY_CONTENT_ID, DOUBLE_WALLRUN_FLAG, EQ1,
                    EXCLUSION, EXCLUSION_MOVES, FLAG, GE1, ITEMS, ITEMS_BY_ID, MACGUFFIN_NAME,
                    NONZERO, PROGRESSIVE_WALLRUN_NAME, LocationInfo)
from .game import Plan

Reader = Callable[[str], "int | None"]
ALL_MOVES = tuple(EXCLUSION_MOVES.values())


def location_check(loc: LocationInfo) -> Callable[[Reader], bool]:
    """A function that says, given a flag reader, whether `loc` is done."""
    if loc.rule == GE1:
        return lambda read: (read(loc.flag) or 0) >= 1
    if loc.rule == EQ1:
        return lambda read: read(loc.flag) == 1
    if loc.rule == NONZERO:
        return lambda read: (read(loc.flag) or 0) != 0
    if loc.rule == COUNT:
        return lambda read: sum((read(f) or 0) >= 1 for f in loc.flags) >= loc.at_least
    raise ValueError(f"unknown rule {loc.rule!r} for {loc.name}")


def dash_checks(content_id: int, run_cs: int) -> set[int]:
    """Location ids one finished run earns: the dash's finish check, plus every star tier whose
    time it beat. Whether a time exactly on the threshold earns the star is not verified in
    game; this counts it. Not a dash (a delivery, a billboard...): nothing."""
    return {l.id for l in DASHES_BY_CONTENT_ID.get(content_id, ())
            if l.tier == 0 or run_cs <= l.max_cs}


def received_names(item_ids: Iterable[int]) -> Counter:
    return Counter(ITEMS_BY_ID[i].name for i in item_ids if i in ITEMS_BY_ID)


def desired_flags(have: Counter, slot_data: dict) -> dict[str, tuple[int, str]]:
    """flag -> (value, reason) for every progression flag the client should hold."""
    out: dict[str, tuple[int, str]] = {}
    for name in have:
        info = ITEMS[name]
        if info.kind == FLAG:
            out[info.flag] = (1, f"received {name}")
    if have[PROGRESSIVE_WALLRUN_NAME] >= 2:
        out[DOUBLE_WALLRUN_FLAG] = (1, f"received {PROGRESSIVE_WALLRUN_NAME} x2")
    final_item = slot_data.get("final_unlock_item")
    if final_item and have[MACGUFFIN_NAME] >= slot_data.get("data_shards_required", 0):
        out[ITEMS[final_item].flag] = (1, f"{MACGUFFIN_NAME}s collected: final activity unlocked")
    if slot_data.get("revert_skill_tree_purchases"):
        for flag in [ITEMS[n].flag for n in ABILITY_ITEMS] + [DOUBLE_WALLRUN_FLAG]:
            out.setdefault(flag, (0, "not received yet (bought from the skill tree?)"))
    return out


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
               final: LocationInfo | None, writes_allowed: bool) -> Plan:
    have = received_names(item_ids)
    plan = Plan(watch={lid: location_check(loc) for lid, loc in watch.items()},
                writes_allowed=writes_allowed)
    if final is not None:
        plan.final_check = location_check(final)
    if writes_allowed:
        plan.flags = desired_flags(have, slot_data)
        plan.blocked = blocked_moves(have)
    return plan
