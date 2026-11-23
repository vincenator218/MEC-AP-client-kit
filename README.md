# Mirror's Edge Catalyst: Archipelago client kit

Everything found so far for building an [Archipelago](https://archipelago.gg) randomizer for
**Mirror's Edge Catalyst (PC, Steam build)**: what the checks are, how to detect them, what the
items are, how to give them to a running game, and two working worlds built on that.

This is meant to be picked up later. It is a design document and a bucket of ideas as much as
code. Only results tested in game are stated as facts; each says how and when it was tested.
Everything else is labeled expected, untested or idea.

## Start here

1. **This page**: how it works and what works.
2. [`docs/ROADMAP.md`](docs/ROADMAP.md): where it could go next, the idea bucket, how to test in
   game, and the rules learned the hard way.
3. [`docs/MEMORY.md`](docs/MEMORY.md): the live interface (flag table, abilities, movement volumes).
4. [`docs/DLL.md`](docs/DLL.md) and [`dll/README.md`](dll/README.md): the injected DLL.
5. [`apworld/README.md`](apworld/README.md): the two worlds' design decisions and what was verified.
6. [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md): what is still unknown.

"FINDINGS §N" refers to the original reverse-engineering log (`ME-AP/FINDINGS.md`), which is
**not in this repository**. The results that matter are restated here.

## How it works, in one paragraph

All progression state (collectibles, missions, abilities, gear) lives in one **flag table** in
game memory: 32-bit values keyed by a hash of each flag's name, saved by the game's autosave.
- **Detecting checks:** poll flags in that table. Dashes have no flag: an injected DLL hears the
  game's "challenge finished" message instead.
- **Giving items:** write the flag. For an ability to work *now* rather than at the next respawn,
  the game's own `apply` must run on its game thread, which the DLL does.
- **Five basic moves** (springboard, climb up, ledge hang, wallrun, MAG rope) have no flag: the
  client blocks them through a movement volume, one byte each.
- **Persistence:** flags reach the save through the autosave; moves are never saved.

## Status

| capability | status |
|---|---|
| Read any flag live (location detection) | works (both clients) |
| Write any flag live, kept by the autosave | works, verified on disk after a relaunch |
| Block / give the 5 moves live, no flag, no mod | works (FINDINGS §83-§86); the clients drive it, `MEC_MoveToggles.pyw` too |
| Ability at the next respawn (table write alone) | works (Coil 2026-10-29, QuickTurn 2026-11-13) |
| Ability **immediately** | works through `mec_ap.dll` 0.2.1 (2026-11-13: Coil and FastClimb, read back; Coil worked in play at once). Proven earlier with Cheat Engine on Switch Place, a stamina tier, Double Wallrun, MAG Rope Swing and Focus, but those foreign-thread calls crashed the game twice |
| Dashes as checks (finish + 1/2/3 stars) | works through the DLL, end to end to a server (2026-11-12) |
| Dash Unlocks (Dashes world) | hard lock built (`hard_dash_lock`, default on): a locked dash is off the map and cannot be started; the lock itself tested in game 2026-11-22 (DLL.md §11e). Soft lock as a fallback |
| Side mission unlock | write `SilverCompleted_<mission>`; in the replay menu at the next load (checkpoint restart tested) |
| Opportunity unlock | write its completion flag; in the Runs menu at the next load, plays from there, a real completion writes the time (one tested end to end). 32 of 40 have a menu entry |
| Grants survive: fresh load, death, mission start, fast travel, checkpoint restart | tested |
| Which activity needs which move (logic) | barely started: 2 rows (Dashes world) |

## Layout

| path | what |
|---|---|
| `apworld/mirrors_edge_catalyst/` | **The main world**: the open world from a story-complete save. Checks: side missions, opportunities, GridLeaks and optional categories, optional dashes. Items: abilities, moves, replay-menu unlocks, Data Shards. `python tools/build_apworld.py`. |
| `apworld/mirrors_edge_catalyst_dashes/` | **The Dashes world**: dashes (finish + stars) and GridLeak bundles; items are moves, abilities and Dash Unlocks; goal N stars. `python tools/build_apworld.py --world dashes`. Shares the game-side client code with the main world (copied in at build). |
| `apworld/README.md` | both worlds' design decisions, ids, what was verified, known gaps |
| `dll/` | **`mec_ap.dll`** (dash events, immediate ability applies) and `mec_ap_inject.exe`. C++17, CMake, Visual Studio 2022 Build Tools. Credits MECMP (MIT). |
| `docs/ROADMAP.md` | the path to a full release, ideas, test playbook, hard-won rules |
| `docs/MEMORY.md` | **the live interface**: addresses, the flag table, hashing, `apply`, movement volumes, safety rules |
| `docs/DLL.md` | the DLL research: hooks, the challenge messages, `apply` on the game thread, dash data, `localize`, overlay, C++ AP libraries, verification order. Addresses from MECMP, checked on our build |
| `docs/ITEMS.md` | the 87 items, their ids, how each is granted and how well tested |
| `docs/LOCATIONS.md` | the 853 flag locations (793 on by default) and the 22 dashes: categories, flags, detection |
| `docs/SAVE_FILE.md` | offline save editing: the format, seed saves, playtest saves |
| `docs/OPEN_QUESTIONS.md` | what is still unknown, numbered |
| `data/items.json`, `data/locations.json` / `.csv` | every item and flag location: id, flag, hash, grant method / detection, test status |
| `data/named_challenges.json` | the 22 dashes (ContentId, Sid, stat code, district, display name, star times, list order) and the billboards seen so far |
| `data/dash_unlock_flags.json` | the hard dash lock: each dash's own unlock flag, tested in game (`docs/DLL.md` §11e) |
| `data/missions.json` | all 152 missions (opportunities, deliveries, hubs, side and story missions) with their completed and available flags (`docs/DLL.md` §11f) |
| `data/flag_names.json` | all 2376 progression flag names and hashes |
| `data/opportunity_names.json` | the 32 Runs-menu opportunities' in-game names |
| `data/dll_addresses.json` | every address in `docs/DLL.md`, with the MECMP file and line it came from |
| `tools/build_apworld.py` | builds either world's `.apworld`, or stages it for tests |
| `tools/build_checks.py` | regenerates `data/locations.*` from `flag_names.json` |
| `tools/client/` | `mec_memory.py` (the memory layer), `MEC_MoveToggles.pyw` (a GUI for testers to remove moves; see its README), `verify_dll_addresses.py` (read-only address check), `dash_unlock_probe.py` and `activity_lock_probe.py` (lock and unlock dashes and other activities by hand, DLL.md §11e-f) |
| `tools/save/` | PROF_SAVE tools: `make_seed_save.py`, `make_testing_save.py`, `read_save.py`, `set_flag.py`, `clear_all_unlocks.py`, `save_checksum.py` |
| `reference/cheatengine/` | the Cheat Engine prototypes the research used: `ap_live.lua` (read, grant, unlock, watch), `setflag.lua`, `list_live_checks.lua` |

## Quick try without Archipelago (Cheat Engine)

1. Back up `Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`.
2. Launch the game and load in. Attach Cheat Engine to `MirrorsEdgeCatalyst.exe`.
3. Paste `reference/cheatengine/ap_live.lua` into the Lua window and execute it. `ap_check()` must report "plausible" and "found".
4. If you own Double Wallrun: `ap_grant("Unlocks_DoubleWallrun", 0)` and the double wall-run stops working; `ap_grant("Unlocks_DoubleWallrun", 1)` and it works again.
5. Put every flag you touched back before you die or wait for an autosave. See the safety rules in `docs/MEMORY.md`.

Cheat Engine calls `apply` from its own thread, which crashed the game twice in the research.
Keep such tests short; the clients use the DLL instead.
