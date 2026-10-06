# Mirror's Edge Catalyst: Archipelago client kit

Everything needed to build an [Archipelago](https://archipelago.gg) client and
world for **Mirror's Edge Catalyst (PC)**: what the checks are, how to detect
them, what the items are, and how to give them to a running game.

This kit is distilled from a longer reverse-engineering log. Only results that
were tested in-game are presented as facts. Anything expected but not yet
tested is labeled that way.

## How it works, in one paragraph

All progression state (collectibles, missions, abilities, gear) lives in one
**flag table** in game memory. Each flag is a 32-bit value keyed by a hash of
its name. The same values are written to the save file by the game's autosave.
- **Detecting checks:** poll flags in that table.
- **Giving items:** write a flag, then (for abilities) call one game function
  so the change takes effect immediately instead of at the next respawn.
- **Persistence:** you get it for free from the autosave.

## Layout

| path | what |
|---|---|
| `docs/MEMORY.md` | **The live interface.** Addresses, table layout, hashing, how to read and write flags, how to apply an ability now, and the safety rules. Start here. |
| `docs/ITEMS.md` | The item pool (84): abilities, gear, MAG Rope, side-mission and opportunity unlocks, with how each is granted and how well tested it is. |
| `docs/LOCATIONS.md` | The 852 locations (792 on by default): categories, flag patterns and detection rules. |
| `docs/SAVE_FILE.md` | Offline save editing, for building a starting save or as a fallback. |
| `docs/OPEN_QUESTIONS.md` | What still needs work before a release. |
| `data/locations.json` / `.csv` | Every location: id, name, category, district, default, flag, hash, detection rule. |
| `data/items.json` | All 84 items: id, flag, hash, grant method, test status. |
| `data/flag_names.json` | All 2376 progression flag names and their hashes. |
| `tools/build_checks.py` | Regenerates `data/locations.*` from `flag_names.json`. |
| `tools/client/` | **`mec_memory.py`** — the client's memory layer (attach, scan for SDK class instances, drive the exclusion volumes, read flags). **`MEC_MoveToggles.pyw`** — a double-click GUI for testers to remove individual moves; see that folder's README. |
| `tools/save/` | PROF_SAVE tools: `make_seed_save.py` (Archipelago starting save), `make_testing_save.py` (playtest save: everything unlocked, no abilities, lots of XP), `read_save.py`, `set_flag.py`, `clear_all_unlocks.py`, `save_checksum.py`. |
| `reference/cheatengine/ap_live.lua` | A Cheat Engine prototype of the whole live interface (read, grant, unlock, watch). |
| `reference/cheatengine/setflag.lua` | A minimal flag get/set, handy for testing. |
| `reference/cheatengine/list_live_checks.lua` | Lists every flag-check entity in memory (read-only census). |

## Status at a glance

| capability | status |
|---|---|
| Read any flag live (location detection) | works |
| Write any flag live, persisted by autosave | works, verified on disk after relaunch |
| Traversal moves (springboard, climb up, hang, wallrun, MAG rope) gated live, no flag and no mod | works; one byte on a `PamMovementExclusionEntityData` instance, immediate, survives death (FINDINGS §83-§86) |
| Ability applied **immediately** (live entity + apply call) | tested on 4 flags (Switch Place, stamina tier, Double Wallrun, MAG Rope Swing); 23 more use the same setup |
| Ability applied immediately (persistent entity) | tested on Focus |
| Any ability, write only | applies at the next death or checkpoint restart |
| Side mission unlock | write `SilverCompleted_<mission>`; shows up in the replay menu at the next load (checkpoint restart tested) |
| Opportunity unlock | write the activity's completion flag; it shows up in the Runs menu at the next load with no completion time, plays from there, and a real completion writes the time (tested end to end on one opportunity). 32 of the 40 opportunities have a menu entry; the 18 countdown deliveries and 8 interventions never do, so they are checks only |
| Grants survive: fresh load, death, mission start, fast travel, checkpoint restart | tested |
| Game-thread hook for the apply call | **not done**. The prototype calls from a foreign thread, and that crashed the game twice in testing |

## Quick try (Cheat Engine)

1. Back up `Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`.
2. Launch the game and load in. Attach Cheat Engine to `MirrorsEdgeCatalyst.exe`.
3. Paste `reference/cheatengine/ap_live.lua` into the Lua window and execute it. `ap_check()` must report "plausible" and "found".
4. If you own Double Wallrun: `ap_grant("Unlocks_DoubleWallrun", 0)` and the double wall-run stops working; `ap_grant("Unlocks_DoubleWallrun", 1)` and it works again.
5. Put every flag you touched back before you die or wait for an autosave. See the safety rules in `docs/MEMORY.md`.
