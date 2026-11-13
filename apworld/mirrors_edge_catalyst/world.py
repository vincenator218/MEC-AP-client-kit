from __future__ import annotations

import logging
import math
from typing import Any

from BaseClasses import CollectionState, Item, ItemClassification, Location, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from . import logic
from .data import (CATEGORIES, DASHES, FILLER, FILLER_NAME, FINAL_ACTIVITIES, GAME,
                   GRIDLEAK_CATEGORY, GRIDLEAKS_BY_DISTRICT, ITEMS, LOCATIONS, MACGUFFIN, MACGUFFIN_NAME,
                   OPPORTUNITY_UNLOCKS, SIDE_MISSION_UNLOCKS, TRAVERSAL_ITEMS,
                   gridleak_location_name)
from .options import OPTION_GROUPS, MECOptions

log = logging.getLogger(__name__)

VICTORY = "Victory"


class MECItem(Item):
    game = GAME


class MECLocation(Location):
    game = GAME


class MECWeb(WebWorld):
    theme = "partyTime"
    option_groups = OPTION_GROUPS
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "Setting up Mirror's Edge Catalyst for Archipelago.",
        "English", "setup_en.md", "setup/en", ["vincenator218"])]


class MECWorld(World):
    """Mirror's Edge Catalyst: run the open world of Glass City from a story-complete save,
    with your abilities, traversal moves and replay unlocks scattered across the multiworld."""
    game = GAME
    web = MECWeb()
    options_dataclass = MECOptions
    options: MECOptions
    topology_present = False

    item_name_to_id = {name: i.id for name, i in ITEMS.items()}
    location_name_to_id = {name: l.id for name, l in LOCATIONS.items()}
    item_name_groups = {
        "Traversal": set(TRAVERSAL_ITEMS),
        "Side Mission Unlocks": set(SIDE_MISSION_UNLOCKS),
        "Opportunity Unlocks": set(OPPORTUNITY_UNLOCKS),
    }
    location_name_groups = {"Dashes": set(DASHES)}

    def generate_early(self) -> None:
        o = self.options
        self.final = FINAL_ACTIVITIES[o.final_activity.current_key]
        self.shards_required = min(o.data_shards_required.value, o.data_shards_total.value)
        try:
            self.requirements = logic.load_requirements()
        except logic.RequirementError as e:
            raise OptionError(f"{GAME}: data/requirements.csv: {e}") from None
        self.location_names = self._chosen_locations()
        if not self.location_names:
            raise OptionError(f"{GAME}: player {self.player_name} turned every location off.")
        # needed by create_item, which core calls for start_inventory_from_pool before create_items
        self.logic_items = self._items_used_by_logic()

    def _chosen_locations(self) -> list[str]:
        on = {cat for key, cat in CATEGORIES.items() if getattr(self.options, key).value}
        names = [n for n, l in LOCATIONS.items()
                 if l.category in on and n != self.final.location]
        size = self.options.gridleak_bundle_size.value
        if size:
            for district, leaks in GRIDLEAKS_BY_DISTRICT.items():
                total = len(leaks)
                steps = list(range(size, total + 1, size))
                if not steps or steps[-1] != total:
                    steps.append(total)              # the last, partial bundle
                names += [gridleak_location_name(district, n) for n in steps]
        if self.options.dashes:
            names += [n for n, l in DASHES.items() if l.tier <= self.options.dash_stars.value]
        return names

    # ----------------------------------------------------------------- regions
    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        city = Region("Glass City", self.player, self.multiworld)
        menu.connect(city)
        city.add_locations({n: LOCATIONS[n].id for n in self.location_names}, MECLocation)
        goal = MECLocation(self.player, f"Final Activity - {self.final.location}", None, city)
        goal.place_locked_item(MECItem(VICTORY, ItemClassification.progression, None, self.player))
        city.locations.append(goal)
        self.goal_location = goal
        self.multiworld.regions += [menu, city]

    # ------------------------------------------------------------------- items
    def _classification(self, name: str) -> ItemClassification:
        info = ITEMS[name]
        if info.kind == MACGUFFIN:
            return ItemClassification.progression_skip_balancing
        if info.kind == FILLER:
            return ItemClassification.filler
        if name in getattr(self, "logic_items", ()) or name in TRAVERSAL_ITEMS:
            return ItemClassification.progression
        return ItemClassification.useful

    def create_item(self, name: str) -> MECItem:
        return MECItem(name, self._classification(name), ITEMS[name].id, self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_NAME

    def create_items(self) -> None:
        names: list[str] = []
        for name, info in ITEMS.items():
            if info.kind in (MACGUFFIN, FILLER) or name == self.final.item:
                continue           # the final activity's unlock is granted by the client
            names += [name] * info.count
        if self.options.traversal_items == self.options.traversal_items.option_start_with:
            for name in TRAVERSAL_ITEMS:
                for _ in range(ITEMS[name].count):
                    self.multiworld.push_precollected(self.create_item(name))
                names = [n for n in names if n != name]
        names += [MACGUFFIN_NAME] * self.options.data_shards_total.value

        # start_inventory_from_pool is handled by core afterwards: it swaps pooled copies for filler
        slots = len(self.location_names)
        items = [self.create_item(n) for n in names]
        if len(items) > slots:
            items = self._fit(items, slots)
        items += [self.create_item(FILLER_NAME) for _ in range(slots - len(items))]
        self.multiworld.itempool += items

    def _fit(self, items: list[MECItem], slots: int) -> list[MECItem]:
        """More items than locations: hand the least important ones out at the start.

        Order of who goes first: opportunity unlocks, side-mission unlocks, then other
        useful items. Progression never moves; if it alone does not fit, that is an error.
        """
        def rank(it: MECItem) -> int:
            if it.advancement:
                return 9
            if it.name in OPPORTUNITY_UNLOCKS:
                return 0
            if it.name in SIDE_MISSION_UNLOCKS:
                return 1
            return 2
        items.sort(key=rank)
        overflow = len(items) - slots
        moved, keep = items[:overflow], items[overflow:]
        if any(it.advancement for it in moved):
            raise OptionError(
                f"{GAME}: player {self.player_name} has {slots} locations but "
                f"{sum(it.advancement for it in items)} progression items. Turn on more "
                f"locations, lower the GridLeak bundle size, or use fewer Data Shards.")
        for it in moved:
            self.multiworld.push_precollected(it)
        log.info("%s: %s had %d more items than locations; gave them at the start: %s",
                 GAME, self.player_name, overflow, ", ".join(sorted(i.name for i in moved)))
        return keep

    # ------------------------------------------------------------------- rules
    def _items_used_by_logic(self) -> set[str]:
        used: set[str] = set()
        for n in self.location_names + [self.final.location]:
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
        expr = self.requirements.for_location(name)
        if expr == logic.NOTHING:
            return None
        return lambda state: logic.evaluate(expr, lambda item, n: state.has(item, player, n))

    def set_rules(self) -> None:
        for name in self.location_names:
            rule = self._rule(name)
            if rule:
                self.get_location(name).access_rule = rule
        final_rule = self._rule(self.final.location)
        shards, player = self.shards_required, self.player
        self.goal_location.access_rule = (
            lambda state: state.has(MACGUFFIN_NAME, player, shards)
            and (final_rule is None or final_rule(state)))
        self.multiworld.completion_condition[player] = lambda state: state.has(VICTORY, player)

    # --------------------------------------------------------------- slot data
    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "version": 1,
            "final_activity": self.final.key,
            "final_unlock_item": self.final.item,
            "final_location": LOCATIONS[self.final.location].id,
            "data_shards_required": self.shards_required,
            "revert_skill_tree_purchases": bool(self.options.revert_skill_tree_purchases.value),
            "gridleak_bundle_size": self.options.gridleak_bundle_size.value,
            "traversal_items": self.options.traversal_items.current_key,
            "dashes": bool(self.options.dashes.value),
            "dash_stars": self.options.dash_stars.value if self.options.dashes else 0,
        }
