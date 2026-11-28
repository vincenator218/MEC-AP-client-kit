"""
Pure functions that turn "what the server says" into "what the game should look like".

No memory access and no networking here, so all of it can be unit-tested offline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable

from ..data import (ABILITY_ITEMS, ACTIVITY_LOCK_FLAG, COUNT, DASH_LOCKS, DASH_NAMES, DASHES, HIDE_ACTIVITIES, DASH_UNLOCK, DASHES_BY_CONTENT_ID,
                    DOUBLE_WALLRUN_FLAG, EXCLUSION, EXCLUSION_MOVES, FLAG, ITEMS, ITEMS_BY_ID,
                    LOCATIONS_BY_ID, PROGRESSIVE_WALLRUN, PROGRESSIVE_WALLRUN_NAME, TRAVERSAL_ITEMS,
                    LocationInfo, dash_location_name, dash_unlock_name)
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


# ------------------------------------------------------------- the Dashes tab
@dataclass(frozen=True)
class DashRow:
    dash: str
    district: str
    unlocked: bool
    finished: bool | None        # None: the finish is not a check in this seed
    stars: int                   # star checks done
    star_checks: int             # star checks this seed has for the dash
    next_star_cs: int | None     # the time to beat for the lowest star still to get

    @property
    def done(self) -> bool:
        return self.finished is not False and self.stars == self.star_checks


def dash_board(have: Counter, checked: Iterable[int], missing: Iterable[int]) -> list[DashRow]:
    """One row per dash for the client's Dashes tab, in the game's dash order. `checked` and
    `missing` are the server's location lists: together they say which dash checks this seed has
    (dash_stars may leave out the higher tiers)."""
    checked, present = set(checked), set(checked) | set(missing)
    rows = []
    for dash in DASH_NAMES:
        tiers = [DASHES[dash_location_name(dash, t)] for t in range(4)
                 if dash_location_name(dash, t) in DASHES]
        here = [l for l in tiers if l.id in present]
        finish = next((l for l in here if l.tier == 0), None)
        stars = [l for l in here if l.tier > 0]
        todo = [l for l in stars if l.id not in checked]
        rows.append(DashRow(dash, tiers[0].district if tiers else "", dash_unlocked(have, dash),
                            None if finish is None else finish.id in checked,
                            len(stars) - len(todo), len(stars),
                            min(todo, key=lambda l: l.tier).max_cs if todo else None))
    return rows


def race_time(cs: int) -> str:
    """Hundredths of a second as the game shows a run: 1:05.30, or 45.92."""
    m, rest = divmod(cs, 6000)
    return f"{m}:{rest // 100:02d}.{rest % 100:02d}" if m else f"{rest // 100}.{rest % 100:02d}"


# ------------------------------------------------------------- manual move overrides
# /move <move> on|off|2|ap: a fail-safe while playing, and a way to try the logic out. An override
# replaces what the server gave for that one move until it is set back to "ap". Moves only: the
# abilities (flags) and the traversal moves (movement volume); never dash unlocks or checks.
OVERRIDABLE = list(TRAVERSAL_ITEMS) + list(ABILITY_ITEMS)


def max_level(name: str) -> int:
    return ITEMS[name].count if ITEMS[name].kind == PROGRESSIVE_WALLRUN else 1


def level_text(name: str, level: int) -> str:
    if max_level(name) > 1:
        return str(level)
    return "on" if level else "off"


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def find_move(text: str) -> tuple[str | None, list[str]]:
    """The move `text` names (case, spaces and underscores ignored; a unique prefix or part of
    a name is enough). Returns (name, []) or (None, candidates)."""
    key = _norm(text)
    if not key:
        return None, []
    exact = [n for n in OVERRIDABLE if _norm(n) == key or _norm(n) == "progressive" + key]
    if exact:
        return exact[0], []
    for test in (lambda n: _norm(n).startswith(key), lambda n: key in _norm(n)):
        hits = [n for n in OVERRIDABLE if test(n)]
        if len(hits) == 1:
            return hits[0], []
        if hits:
            return None, hits
    return None, []


def override_flags(name: str) -> list[tuple[str, int]]:
    """(flag, level needed for it to be 1) for the ability flags a move controls."""
    info = ITEMS[name]
    if info.kind == FLAG:
        return [(info.flag, 1)]
    if info.kind == PROGRESSIVE_WALLRUN:
        return [(DOUBLE_WALLRUN_FLAG, 2)]
    return []                                    # a traversal move: the movement volume


def with_overrides(have: Counter, overrides: dict[str, int] | None) -> Counter:
    eff = Counter(have)
    for name, level in (overrides or {}).items():
        eff[name] = level
    return +eff                                  # drops the moves set to 0


def desired_flags(have: Counter, slot_data: dict, overrides: dict[str, int] | None = None,
                  touched: Iterable[str] = ()) -> dict[str, tuple[int, str]]:
    """flag -> (value, reason) for every progression flag the client should hold.
    `overrides` (move -> level) come from /move; `touched` are moves overridden earlier and set
    back to "ap": an ability among them the slot does not hold is written back to 0."""
    overrides = overrides or {}
    real = have
    have = with_overrides(have, overrides)
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
    for name in set(touched) - set(overrides):
        for flag, _need in override_flags(name):
            out.setdefault(flag, (0, "not received (manual override removed)"))
    for name, level in overrides.items():
        for flag, need in override_flags(name):
            out[flag] = (int(level >= need), f"/move {name} {level_text(name, level)}")
    if slot_data.get("hard_dash_lock"):
        for dash, (_cid, flag) in DASH_LOCKS.items():
            name = dash_unlock_name(dash)
            out[flag] = (1, f"received {name}") if real[name] else (0, f"{dash} is locked")
    if slot_data.get("hide_other_activities"):
        out[ACTIVITY_LOCK_FLAG] = (1, "hide other activities")
    return out


def hidden_activities(slot_data: dict) -> dict[str, str] | None:
    """Activity name -> its own completion flag, when the slot hides the other activities."""
    return dict(HIDE_ACTIVITIES) if slot_data.get("hide_other_activities") else None


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
               writes_allowed: bool, overrides: dict[str, int] | None = None,
               touched: Iterable[str] = ()) -> DashesPlan:
    have = received_names(item_ids)
    plan = DashesPlan(watch={lid: location_check(loc) for lid, loc in watch.items()},
                      writes_allowed=writes_allowed)
    if writes_allowed:
        plan.flags = desired_flags(have, slot_data, overrides, touched)
        plan.blocked = blocked_moves(with_overrides(have, overrides))
        plan.dash_locks = dash_lock_pointers(slot_data)
        plan.hide_activities = hidden_activities(slot_data)
        plan.hide_lock_flag = ACTIVITY_LOCK_FLAG
    return plan
