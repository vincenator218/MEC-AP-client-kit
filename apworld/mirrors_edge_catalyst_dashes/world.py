from __future__ import annotations

import logging
from typing import Any

from BaseClasses import CollectionState, Item, ItemClassification, Location, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from . import logic
from .data import (DASH_UNLOCK, DASH_UNLOCKS, DASHES, FILLER, FILLER_NAME, GAME, GRIDLEAK_CATEGORY,
                   GRIDLEAKS_BY_DISTRICT, ITEMS, LOCATIONS, TRAVERSAL_ITEMS, dash_location_name, dash_unlock_name,
                   gridleak_location_name, gridleak_steps)
from .options import OPTION_GROUPS, MECDashesOptions

log = logging.getLogger(__name__)

STAR = "Star"            # event: one per star check, the goal counts them
VICTORY = "Victory"


class MECDItem(Item):
    game = GAME


class MECDLocation(Location):
    game = GAME


class MECDWeb(WebWorld):
    theme = "partyTime"
    option_groups = OPTION_GROUPS
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "Setting up Mirror's Edge Catalyst Dashes for Archipelago.",
        "English", "setup_en.md", "setup/en", ["vincenator218"])]


class MECDashesWorld(World):
    """Mirror's Edge Catalyst Dashes: the 22 dashes of Glass City and its GridLeaks, with your
    moves, abilities and the dashes themselves scattered across the multiworld. Earn enough
    stars to win."""
    game = GAME
    web = MECDWeb()
    options_dataclass = MECDashesOptions
    options: MECDashesOptions
    topology_present = False

    item_name_to_id = {name: i.id for name, i in ITEMS.items()}
    location_name_to_id = {name: l.id for name, l in LOCATIONS.items()}
    item_name_groups = {
        "Traversal": set(TRAVERSAL_ITEMS),
        "Dash Unlocks": set(DASH_UNLOCKS),
    }
    location_name_groups = {"Dashes": set(DASHES)}

    def generate_early(self) -> None:
        o = self.options
        try:
            self.requirements = logic.load_requirements()
        except logic.RequirementError as e:
            raise OptionError(f"{GAME}: data/requirements.csv: {e}") from None
        self.location_names = self._chosen_locations()
        self.star_locations = [n for n in self.location_names if LOCATIONS[n].tier > 0]
        self.stars_required = min(o.stars_required.value, len(self.star_locations))
        self.starting_dashes = self._pick_starting_dashes(o.starting_dashes.value)
        self.logic_items = self._items_used_by_logic()

    def _pick_starting_dashes(self, n: int) -> list[str]:
        """n random Dash Unlocks, at least one of them for a dash whose finish needs no move
        (requirements.csv): otherwise every starting dash could need a move that is only found
        on another dash, and nothing would be reachable."""
        free = [u for u in DASH_UNLOCKS
                if self.requirements.for_location(dash_location_name(ITEMS[u].dash)) == logic.NOTHING]
        if not free:
            raise OptionError(f"{GAME}: data/requirements.csv gives every dash a requirement; "
                              f"at least one must need nothing to start a seed.")
        first = self.random.choice(free)
        rest = self.random.sample([u for u in DASH_UNLOCKS if u != first], n - 1)
        return sorted([first] + rest)

    def _chosen_locations(self) -> list[str]:
        names = [n for n, l in DASHES.items() if l.tier <= self.options.dash_stars.value]
        size, pct = self.options.gridleak_bundle_size.value, self.options.gridleak_percent.value
        for district, leaks in GRIDLEAKS_BY_DISTRICT.items():
            names += [gridleak_location_name(district, n) for n in gridleak_steps(len(leaks), size, pct)]
        return names

    # ----------------------------------------------------------------- regions
    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        city = Region("Glass City", self.player, self.multiworld)
        menu.connect(city)
        city.add_locations({n: LOCATIONS[n].id for n in self.location_names}, MECDLocation)
        # one event per star check, with the same rule: the goal is "this many of them"
        for n in self.star_locations:
            ev = MECDLocation(self.player, f"{n} (star)", None, city)
            ev.place_locked_item(MECDItem(STAR, ItemClassification.progression, None, self.player))
            city.locations.append(ev)
        goal = MECDLocation(self.player, "Enough Stars", None, city)
        goal.place_locked_item(MECDItem(VICTORY, ItemClassification.progression, None, self.player))
        city.locations.append(goal)
        self.goal_location = goal
        self.multiworld.regions += [menu, city]

    # ------------------------------------------------------------------- items
    def _classification(self, name: str) -> ItemClassification:
        info = ITEMS[name]
        if info.kind == FILLER:
            return ItemClassification.filler
        if info.kind == DASH_UNLOCK or name in TRAVERSAL_ITEMS or name in getattr(self, "logic_items", ()):
            return ItemClassification.progression
        return ItemClassification.useful

    def create_item(self, name: str) -> MECDItem:
        return MECDItem(name, self._classification(name), ITEMS[name].id, self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_NAME

    def create_items(self) -> None:
        names: list[str] = []
        for name, info in ITEMS.items():
            if info.kind != FILLER and name not in self.starting_dashes:
                names += [name] * info.count
        for name in self.starting_dashes:
            self.multiworld.push_precollected(self.create_item(name))
        if self.options.traversal_items == self.options.traversal_items.option_start_with:
            for name in TRAVERSAL_ITEMS:
                for _ in range(ITEMS[name].count):
                    self.multiworld.push_precollected(self.create_item(name))
            names = [n for n in names if n not in TRAVERSAL_ITEMS]

        slots = len(self.location_names)
        items = [self.create_item(n) for n in names]
        if len(items) > slots:
            items = self._fit(items, slots)
        items += [self.create_item(FILLER_NAME) for _ in range(slots - len(items))]
        self.multiworld.itempool += items

    def _fit(self, items: list[MECDItem], slots: int) -> list[MECDItem]:
        """More items than locations: the least important (useful abilities) go to the start
        inventory. Progression never moves; if it alone does not fit, that is an error."""
        items.sort(key=lambda it: it.advancement)
        overflow = len(items) - slots
        moved, keep = items[:overflow], items[overflow:]
        if any(it.advancement for it in moved):
            raise OptionError(
                f"{GAME}: player {self.player_name} has {slots} locations but "
                f"{sum(it.advancement for it in items)} progression items. Use more Dash Stars, "
                f"a smaller GridLeak bundle size, or more Starting Dashes.")
        for it in moved:
            self.multiworld.push_precollected(it)
        log.info("%s: %s had %d more items than locations; gave them at the start: %s",
                 GAME, self.player_name, overflow, ", ".join(sorted(i.name for i in moved)))
        return keep

    # ------------------------------------------------------------------- rules
    def _items_used_by_logic(self) -> set[str]:
        used: set[str] = set()
        for n in self.location_names:
            loc = LOCATIONS[n]
            if loc.category == GRIDLEAK_CATEGORY:
                for e, _ in self.requirements.gridleak_groups(loc.district):
                    used |= logic.items_in(e)
            else:
                used |= logic.items_in(self.requirements.for_location(n))
        return used

    def _rule(self, name: str):
        player = self.player
        loc = LOCATIONS[name]
        if loc.category == GRIDLEAK_CATEGORY:
            groups = self.requirements.gridleak_groups(loc.district)
            need = loc.at_least
            if sum(k for e, k in groups if e == logic.NOTHING) >= need:
                return None

            def count_rule(state: CollectionState) -> bool:
                have = lambda item, n: state.has(item, player, n)  # noqa: E731
                return sum(k for e, k in groups if logic.evaluate(e, have)) >= need
            return count_rule
        unlock = dash_unlock_name(loc.dash)
        expr = self.requirements.for_location(name)
        if expr == logic.NOTHING:
            return lambda state: state.has(unlock, player)
        return lambda state: state.has(unlock, player) and logic.evaluate(
            expr, lambda item, n: state.has(item, player, n))

    def set_rules(self) -> None:
        for name in self.location_names:
            rule = self._rule(name)
            if rule:
                self.get_location(name).access_rule = rule
        for name in self.star_locations:
            rule = self._rule(name)
            if rule:
                self.get_location(f"{name} (star)").access_rule = rule
        need, player = self.stars_required, self.player
        self.goal_location.access_rule = lambda state: state.has(STAR, player, need)
        self.multiworld.completion_condition[player] = lambda state: state.has(VICTORY, player)

    # --------------------------------------------------------------- slot data
    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "version": 1,
            "stars_required": self.stars_required,
            "dash_stars": self.options.dash_stars.value,
            "gridleak_bundle_size": self.options.gridleak_bundle_size.value,
            "gridleak_percent": self.options.gridleak_percent.value,
            "traversal_items": self.options.traversal_items.current_key,
            "revert_skill_tree_purchases": bool(self.options.revert_skill_tree_purchases.value),
            "hard_dash_lock": bool(self.options.hard_dash_lock.value),
            "hide_other_activities": bool(self.options.hide_other_activities.value),
        }
