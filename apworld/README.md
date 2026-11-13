# The Archipelago world and client

`mirrors_edge_catalyst/` is the apworld source. The game client lives inside it
(`client/`) and opens from the Archipelago Launcher.

```
python tools/build_apworld.py          # -> build/mirrors_edge_catalyst.apworld
```

The build copies in `data/items.json`, `data/locations.json` and `tools/client/mec_memory.py`,
so each of those keeps a single home in the kit.

## Layout

| file | what |
|---|---|
| `data.py` | item and location tables built from the kit's JSON; final-activity map |
| `logic.py` | requirement expressions and the requirements table loader |
| `data/requirements.csv` | **the logic**: one row per location or category. Empty for now |
| `data/aliases.json` | other names the requirements file may use for an item |
| `options.py`, `world.py` | options, item pool, rules, slot data |
| `client/plan.py` | pure: received items -> flags / blocked moves; location detection |
| `client/game.py` | memory side: flag table, the one flag-writing path, exclusion volume driver |
| `client/client.py` | CommonClient context and the 1-second game loop |
| `test/` | world generation, parser, client plan, flag table on fake memory |

## Decisions (asked and answered)

- **Goal:** Data Shards (MacGuffin) unlock a final activity. `final_activity` picks any of
  the 46 activities with a replay-menu unlock (14 side missions/grid nodes, 32 opportunities);
  the default is Top of the World, the side-mission unlock tested end to end (ITEMS.md).
  That activity's check and its unlock item leave the pool. The client writes its unlock
  flag once you hold the shards, and sends the goal when its completion appears while you
  hold them.
- **Default locations:** side missions (12), opportunities (40), GridLeaks bundled.
  `gridleak_bundle_size` (default 5) makes "N leaks in a district" checks: 66 at size 5,
  324 at size 1. Everything else is off by default.
- **Wallrun:** `Progressive Wallrun` x2. The first copy clears `ExcludeWallrun`, the second
  writes `Unlocks_DoubleWallrun`. The old `Wallrun` (1320113) and `DoubleWallrun` (1320006)
  items no longer exist; the progressive item is 1320115.
- **Apply hook:** none. Abilities are written to the table only and take effect at the next
  death or checkpoint restart (MEMORY.md §3 timing table). `client/game.py:Applier` is the
  seam for a game-thread hook later.
- **Dashes (2026-11-12):** options `dashes` (off by default) and `dash_stars` (0-3, default 3).
  - Each of the 22 dashes has a finish check and up to three star checks: 88 locations, ids
    `1330000 + 10 * ap_index + tier` (`ap_index` is the position in the in-game dash list, stored
    in `data/named_challenges.json`).
  - They are detected by the injected DLL (`dll/`), which forwards the game's "challenge
    finished" message; `client/dll_link.py` receives it and `plan.dash_checks` picks the checks.
    A time on a star threshold counts as earning it (unverified).
  - Dashes are not locked; the game has no per-dash lock (docs/DLL.md §11d).
  - A star location with no requirement row of its own needs what its dash needs.

## Other design choices to review

- **Opportunity detection changed.** LOCATIONS.md detects an opportunity by
  `MiscCompleted_<name> == 1`, but that is exactly the flag the opportunity's unlock item
  writes (ITEMS.md), so every unlock would have sent its own check. The 32 opportunities that
  have an unlock item are detected by `<name>_CompletedTime != 0` instead. ITEMS.md says
  the client never writes that and a real completion does (tested on one). The 8
  interventions keep `MiscCompleted_ == 1`. A test asserts no location is detected on any
  flag an item writes.
- **GridLeak IDs.** The per-GUID GridLeak locations (1310000-1310323) are not in the
  datapackage; the count locations are 1310500+n (Downtown), 1310600+n (Anchor),
  1310700+n (The View) and 1310800+n (Rezoning). All other location IDs are unchanged.
  Per-leak requirement rows still work: a count check is reachable when at least N of
  that district's leaks are.
- **Too many items.** With few locations on, useful items that do not fit are given at the
  start (opportunity unlocks first, then side-mission unlocks, then other abilities) and
  logged. If the progression items alone do not fit, generation fails with an OptionError.
- **Item classes.** Data Shards: progression (skip balancing). Traversal moves: always
  progression. Any other item becomes progression only when a requirement row names it.
  Everything else is useful. Filler is a no-op `Gridnet Static`, because XP is untested.
- **The final activity is not locked in the world.** Unlock items only control the replay
  menu (SAVE_FILE.md), so you could play the activity in the world early. Finishing it early
  completes the goal the moment you get the last shard.
- **Wrong-save guard.** On its first look at a save, if more than 25 locations are already
  finished that the slot never sent, the client holds them and writes nothing until
  `/confirm_save`.

## The logic file

`data/requirements.csv` has the columns `location,requires,source,notes`. `location` is a
name or id from `data/locations.json` (any row, including single GridLeaks),
`category:<Category>`, or `*`. `requires` uses `&` or `,` for AND, `|` for OR, parentheses,
and `Item:N`. The most specific row wins. A name the parser does not know is an error at
generation, never a free location.

The crowdsourced worksheet (`activity_logic_worksheet.csv`) has an `id` column and an
`abilities_i_had_to_unlock` column, so its rows translate directly: `id` -> `location`, the
ability list -> `requires`, with skill-tree names added to `aliases.json` as they appear.

## What is verified, and how

- 87 apworld tests (2026-11-12, with the dash ones) and AP 0.6.7's `test/general` suite (319
  tests, all worlds except `soe` and `zillion`, which need packages of their own) pass.
  Generation was also run with `Generate.py` on a 2-player multiworld (before dashes).
- Dashes: `test/test_dashes.py` checks the 88 locations, the star rule, generation with
  `dash_stars` 0 and 3, and `DllLink` against a fake DLL on a real localhost socket (a finish is
  kept, not acknowledged, until there is a slot). **The DLL itself has not been compiled or run
  yet.**
- The client ran against a real 0.6.7 server with a **simulated** game memory (the
  FakeMem table in `test/test_client.py`). Verified there: received items written and read
  back, the 2nd Progressive Wallrun writing Double Wallrun, a skill-tree purchase reverted,
  the final unlock at the shard count, the blocked-move set, a side-mission completion
  sent as a check, the goal sent, and the wrong-save guard holding everything until
  `/confirm_save`.
- **In game, first live session (2026-10-29)**, seed save from `make_seed_save.py`,
  `traversal_items: start_with`:
  - attach, world-load detection and slot connect worked;
  - a flag write held: `Unlocks_DoubleWallrun` from the two starting Progressive Wallruns,
    confirmed by a separate read-only memory read. Right after the load it had to be
    written three times; the client now waits one extra loaded tick before writing;
  - **GridLeak bundles:** the 5th leak in a district sent the check;
  - **opportunity unlock + detection:** the received unlock put the run in the Runs tab
    after a refresh **without** sending its check, and finishing the run sent the check.
    This confirms the `_CompletedTime` detection change above;
  - **ability grant at respawn:** `/send` Coil (a `live_entity` ability marked `expected`
    in ITEMS.md): absent until the next death, then working. This is the client's
    write-only path, not the `apply` call ITEMS.md's status refers to;
  - **a run found in free roam, never unlocked**, sent its check when finished. So runs
    exist in the world without their unlock item, as SAVE_FILE.md said: opportunity
    unlocks are convenience (useful), never logic, and an opportunity picked as
    `final_activity` is not really locked;
  - **some side missions can be started in free roam** without their unlock. The tester's
    guess (unverified) is that the rest appear as those are completed. So a side mission
    picked as `final_activity` may not be locked either;
  - replaying the story Grid Node Run sent nothing, as designed (it is not a location);
  - at attach the build check read `class None`; a later read found the right class. It
    was a startup race, and the check now runs only once the world is loaded.
- **Not yet verified in game:** the exclusion driver inside the client (moves were all
  given at the start), which side missions are in free roam and whether the rest unlock
  in a chain, the 2nd Progressive Wallrun, the skill-tree revert,
  side-mission unlocks, the final activity and goal, the wrong-save guard, and surviving a
  game restart.

## Known gaps

- Game-thread hook for `apply` (OPEN_QUESTIONS.md #1). An injected DLL would fix this, and
  would also let the goal count only a completion made after the shard unlock. It would make
  dashes possible checks too. What's needed to start one is in `docs/DLL.md`.
- Ability requirements: `requirements.csv` is empty. With `traversal_items: randomized`, a
  seed can hand out a location you cannot physically reach.
- 23 `live_entity` and 11 `persistent_entity` abilities are expected/untested (ITEMS.md).
  Here they only get the table write, which applies at the next respawn.
- Pipes and ladders cannot be blocked, so "no Climb Up" is not "no vertical traversal".
- `Global_CityUnlockState` as a progressive item: not used, completely untested.
- Whether a live-unlocked side mission plays correctly from the menu (OPEN_QUESTIONS.md #10).
