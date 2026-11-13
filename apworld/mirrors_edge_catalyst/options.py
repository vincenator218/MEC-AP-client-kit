from __future__ import annotations

from dataclasses import dataclass

from Options import (Choice, DefaultOnToggle, OptionGroup, PerGameCommonOptions, Range,
                     StartInventoryPool, Toggle)

from .data import DEFAULT_FINAL_ACTIVITY, FINAL_ACTIVITIES


# ---------------------------------------------------------------------- goal
class DataShardsTotal(Range):
    """How many Data Shards are shuffled into the multiworld."""
    display_name = "Data Shards in Pool"
    range_start = 1
    range_end = 100
    default = 20


class DataShardsRequired(Range):
    """How many Data Shards unlock the final activity. Capped at the number in the pool."""
    display_name = "Data Shards Required"
    range_start = 1
    range_end = 100
    default = 15


def _final_activity_option() -> type[Choice]:
    keys = sorted(FINAL_ACTIVITIES)
    ns = {
        "__doc__": "The activity that ends the game. The client unlocks it in the replay menu "
                   "once you hold the required Data Shards; finishing it with the shards in hand "
                   "is the goal. Any side mission, grid node or Runs-menu opportunity can be "
                   "picked. Its normal check and its unlock item are removed from the pool.",
        "display_name": "Final Activity",
        "default": keys.index(DEFAULT_FINAL_ACTIVITY),
        "__module__": __name__,
    }
    ns.update({f"option_{k}": i for i, k in enumerate(keys)})
    return type("FinalActivity", (Choice,), ns)


FinalActivity = _final_activity_option()


# ----------------------------------------------------------------- locations
class SideMissions(DefaultOnToggle):
    """Side missions (and Birdman's Delivery) are checks."""
    display_name = "Side Missions"


class Opportunities(DefaultOnToggle):
    """The 40 OPPORTUNITY activities: covert and fragile deliveries, diversions and interventions."""
    display_name = "Opportunities"


class CountdownDeliveries(Toggle):
    """The 18 timed countdown deliveries (no Runs-menu entry) are checks."""
    display_name = "Countdown Deliveries"


class GridLeakBundleSize(Range):
    """Every this-many GridLeaks collected in a district sends one check. 0 turns GridLeaks off.
    With 1, every leak is a check (324 in total)."""
    display_name = "GridLeak Bundle Size"
    range_start = 0
    range_end = 87
    default = 5


class SecurityHubs(Toggle):
    """The 6 open-world security hubs are checks."""
    display_name = "Security Hubs"


class GridNodes(Toggle):
    """The 3 open-world grid nodes are checks."""
    display_name = "Grid Nodes"


class Billboards(Toggle):
    """The 12 billboard hacks are checks."""
    display_name = "Billboard Hacks"


class ElectronicParts(Toggle):
    """The 251 electronic parts are checks."""
    display_name = "Electronic Parts"


class SurveillanceRecordings(Toggle):
    """The 45 surveillance recordings are checks."""
    display_name = "Surveillance Recordings"


class Documents(Toggle):
    """The 42 documents are checks."""
    display_name = "Documents"


class SecretBags(Toggle):
    """The 40 secret bags are checks."""
    display_name = "Secret Bags"


class Dashes(Toggle):
    """The 22 dashes are checks: finishing one, at any speed. Needs the client's injected DLL
    (dll/ in the client kit), because dashes have no progression flag to read."""
    display_name = "Dashes"


class DashStars(Range):
    """With Dashes on: how many star tiers per dash are also checks. 3 = a check each for
    1, 2 and 3 stars (a 3-star run sends all three)."""
    display_name = "Dash Stars"
    range_start = 0
    range_end = 3
    default = 3


# --------------------------------------------------------------------- items
class TraversalItems(Choice):
    """randomized: Springboard, Climb Up, Ledge Hang, Wallrun and MAG Rope are taken away
    and shuffled into the pool. start_with: you start with all five.

    No per-activity ability data exists yet, so with 'randomized' the logic cannot know what
    an activity needs. Use start_with, or put moves in start_inventory, until it does."""
    display_name = "Traversal Items"
    option_randomized = 0
    option_start_with = 1
    default = 0


class RevertSkillTreePurchases(DefaultOnToggle):
    """The skill tree still sells abilities for XP. When on, the client takes back any
    randomized ability you own but have not received."""
    display_name = "Revert Skill Tree Purchases"


@dataclass
class MECOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    final_activity: FinalActivity
    data_shards_total: DataShardsTotal
    data_shards_required: DataShardsRequired
    side_missions: SideMissions
    opportunities: Opportunities
    countdown_deliveries: CountdownDeliveries
    gridleak_bundle_size: GridLeakBundleSize
    security_hubs: SecurityHubs
    grid_nodes: GridNodes
    billboards: Billboards
    electronic_parts: ElectronicParts
    surveillance_recordings: SurveillanceRecordings
    documents: Documents
    secret_bags: SecretBags
    dashes: Dashes
    dash_stars: DashStars
    traversal_items: TraversalItems
    revert_skill_tree_purchases: RevertSkillTreePurchases


OPTION_GROUPS = [
    OptionGroup("Goal", [FinalActivity, DataShardsTotal, DataShardsRequired]),
    OptionGroup("Locations", [SideMissions, Opportunities, CountdownDeliveries, GridLeakBundleSize,
                              SecurityHubs, GridNodes, Billboards, ElectronicParts,
                              SurveillanceRecordings, Documents, SecretBags, Dashes, DashStars]),
    OptionGroup("Items", [TraversalItems, RevertSkillTreePurchases]),
]
