from __future__ import annotations

from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, OptionGroup, PerGameCommonOptions, Range, StartInventoryPool


# ---------------------------------------------------------------------- goal
class StarsRequired(Range):
    """The goal: this many dash stars, counted from the star checks you have sent. A dash's
    stars count only once you hold its Dash Unlock. Capped at what the seed has
    (22 dashes x Dash Stars)."""
    display_name = "Stars Required"
    range_start = 1
    range_end = 66
    default = 40


# ----------------------------------------------------------------- locations
class DashStars(Range):
    """How many star tiers per dash are checks, besides finishing it. 3 = a check each for
    1, 2 and 3 stars (a 3-star run sends all three). The goal counts star checks, so it needs
    at least 1."""
    display_name = "Dash Stars"
    range_start = 1
    range_end = 3
    default = 3


class GridLeakBundleSize(Range):
    """Every this-many GridLeaks collected in a district sends one check, up to GridLeak Percent
    of the district, so you never need every leak. 0 turns GridLeaks off."""
    display_name = "GridLeak Bundle Size"
    range_start = 0
    range_end = 40
    default = 10


class GridLeakPercent(Range):
    """GridLeak checks stop at this share of each district's leaks; the rest are spare. With 60
    and bundles of 10: Downtown (87 leaks) has checks at 10 ... 50, The View (80) at 10 ... 40.
    The last leak of a district is never a check, whatever this is."""
    display_name = "GridLeak Percent"
    range_start = 10
    range_end = 99
    default = 60


# --------------------------------------------------------------------- items
class StartingDashes(Range):
    """How many Dash Unlocks you start with, picked at random. A dash's checks only count once
    you hold its unlock; you can still play a locked dash, but the run has to be done again
    after the unlock arrives."""
    display_name = "Starting Dashes"
    range_start = 1
    range_end = 22
    default = 3


class TraversalItems(Choice):
    """randomized: Springboard, Climb Up, Ledge Hang, Wallrun and MAG Rope are taken away and
    shuffled into the pool. start_with: you start with all five.

    Which moves each dash needs is not recorded yet (data/requirements.csv). Until it is, the
    logic assumes a dash needs only its unlock, so 'randomized' can ask for a dash you cannot
    finish without a move you do not have yet."""
    display_name = "Traversal Items"
    option_randomized = 0
    option_start_with = 1
    default = 0


class RevertSkillTreePurchases(DefaultOnToggle):
    """The skill tree still sells abilities for XP. When on, the client takes back any
    randomized ability you own but have not received."""
    display_name = "Revert Skill Tree Purchases"


@dataclass
class MECDashesOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    stars_required: StarsRequired
    dash_stars: DashStars
    gridleak_bundle_size: GridLeakBundleSize
    gridleak_percent: GridLeakPercent
    starting_dashes: StartingDashes
    traversal_items: TraversalItems
    revert_skill_tree_purchases: RevertSkillTreePurchases


OPTION_GROUPS = [
    OptionGroup("Goal", [StarsRequired]),
    OptionGroup("Locations", [DashStars, GridLeakBundleSize, GridLeakPercent]),
    OptionGroup("Items", [StartingDashes, TraversalItems, RevertSkillTreePurchases]),
]
