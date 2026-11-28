# The Archipelago worlds and clients

Two worlds, each with its game client inside it (`client/`, opened from the Archipelago
Launcher):

- `mirrors_edge_catalyst/`: **Mirror's Edge Catalyst**, the whole open world. Most of this page.
- `mirrors_edge_catalyst_dashes/`: **Mirror's Edge Catalyst Dashes**, dashes and movement only.
  See "The Dashes world" at the end.

```
python tools/build_apworld.py                 # -> build/mirrors_edge_catalyst.apworld
python tools/build_apworld.py --world dashes  # -> build/mirrors_edge_catalyst_dashes.apworld
```

The build copies in `data/items.json`, `data/locations.json`, `data/named_challenges.json` and
`tools/client/mec_memory.py`, so each keeps a single home in the kit. The Dashes world also gets
the main world's `logic.py`, `data/aliases.json`, `client/game.py` and `client/dll_link.py`.

## Layout (main world)

| file | what |
|---|---|
| `data.py` | item and location tables built from the kit's JSON; final-activity map |
| `logic.py` | requirement expressions and the requirements table loader |
| `data/requirements.csv` | **the logic**: one row per location or category. Empty for now |
| `data/aliases.json` | other names the requirements file may use for an item |
| `options.py`, `world.py` | options, item pool, rules, slot data |
| `client/plan.py` | pure: received items -> flags / blocked moves; location detection |
| `client/game.py` | memory side: flag table, the one flag-writing path, exclusion volume driver |
| `client/dll_link.py` | the link to `mec_ap.dll`: dash finishes in (journaled, acknowledged), apply requests out |
| `client/client.py` | CommonClient context and the 1-second game loop |
| `test/` | world generation, parser, client plan, flag table on fake memory, dashes, the DLL link against a fake DLL |

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
- **Abilities:** the client writes the flag (its one write path), then asks `mec_ap.dll` to
  apply it on the game thread, so it works at once. Without the DLL, or if the DLL's own check
  fails, the ability takes effect at the next death or checkpoint restart (MEMORY.md §3). When
  the DLL connects after flags were written, the client asks it to re-check every ability.
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

- Unit tests (2026-11-19): main world 90, Dashes world 37, and AP 0.6.7's `test/general` suite
  with both installed (322; all worlds except `soe` and `zillion`, which need packages of their
  own) pass. Generation was also run with `Generate.py` on a 2-player multiworld (before dashes).
- Dashes: `test/test_dashes.py` checks the 88 locations, the star rule, generation with
  `dash_stars` 0 and 3, and `DllLink` against a fake DLL on a real localhost socket (a finish is
  kept, not acknowledged, until there is a slot). `test/test_apply.py` checks which flags are
  applied and the apply round trip.
- **With the real DLL, in game:** a dash finish sent exactly its finish and 1-star checks to a
  local server (2026-11-12); Coil and FastClimb received from a dash were applied at once and
  read back, and Coil worked in play with no respawn (2026-11-13). Details in `dll/README.md`.
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
- **Not yet verified in game (main world):** the exclusion driver inside the main client
  (moves were all given at the start; the Dashes client drove it on 2026-11-19, and the tester
  could not finish Caleb's Run without MAG Rope, but blocking was not checked move by move),
  which side missions are in free roam and whether the rest unlock in a chain, the skill-tree
  revert, side-mission unlocks from the client, the final activity and goal, the wrong-save
  guard, and surviving a game restart.

## Known gaps

- The final activity is not locked in the world (see above). With the DLL, the goal could count
  only a completion message made after the unlock (`docs/ROADMAP.md`).
- Ability requirements: `requirements.csv` is empty. With `traversal_items: randomized`, a
  seed can hand out a location you cannot physically reach.
- Most abilities are `expected` / `untested` for the live apply (ITEMS.md). If the DLL cannot
  apply one, it still takes effect at the next respawn.
- Pipes and ladders cannot be blocked, so "no Climb Up" is not "no vertical traversal".
- `Global_CityUnlockState` as a progressive item: not used, completely untested.
- Whether a live-unlocked side mission plays correctly from the menu (OPEN_QUESTIONS.md #10).

## The Dashes world

`mirrors_edge_catalyst_dashes/`, game **Mirror's Edge Catalyst Dashes**. Dashes and movement
only: no side missions, no opportunities. Built 2026-11-13, first played 2026-11-19.

- **Checks:** each dash's finish and its 1/2/3-star tiers (`dash_stars`, 1-3), detected through
  `mec_ap.dll`; GridLeaks every `gridleak_bundle_size` (default 10) in a district, up to
  `gridleak_percent` (default 60) of it and always below its total, so no district needs every
  leak. Default: 88 + 17 = 105 checks.
- **Items:** the 5 moves (Wallrun as 2 Progressive Wallruns), the 35 abilities, 22 **Dash
  Unlocks** (1320500 + `ap_index`), filler `Gridnet Static`. `starting_dashes` (default 3) are
  given at the start, at least one of them a dash that needs no move by `requirements.csv`, so a
  seed can always start. Useful abilities that do not fit go to the start inventory.
- **Hard lock** (`hard_dash_lock`, on by default; `client/dash_lock.py`): the client points each
  dash's `UnlockFlag` at its own lock flag (`data/dash_unlock_flags.json`, docs/DLL.md §11e) and
  holds that flag at 0 until the Dash Unlock arrives, through the one write path. A locked dash is
  off the map and cannot be started; changes show after a checkpoint reload. The pointers are
  re-validated every tick and set back to null when the client closes. `make_seed_save.py`
  clears the 22 flags.
- **Hide other activities** (`hide_other_activities`, on by default; `client/activity_lock.py`):
  the 92 opportunities, deliveries, security hubs and side missions (`data/missions.json` types
  1-3) get their `CompletedFlag` pointed at one shared flag held at 1, so the game treats them as
  done and takes them off the map (docs/DLL.md §11f). Their real completion flags are never
  touched, and every pointer is put back when the client closes. The 6 Dead Drop Deliveries
  cannot be hidden this way.
- **Soft lock** (always, and all there is with `hard_dash_lock` off): the client sends a dash's
  checks only if you hold its unlock. A locked run is logged ("does not count; run it again
  once the unlock arrives") and dropped. Seen working in game on 2026-11-19.
- **Goal:** `stars_required` (default 40, capped at what the seed has). Each star check has a
  hidden "Star" event with the same rule, so the generator proves the goal is reachable. The
  client sends the goal when enough star checks have been sent.
- **Logic:** its own `data/requirements.csv`, same format; a star tier inherits its dash's row.
  Two rows from play (2026-11-19): Caleb's Run needs MAG Rope; Out in the Open needs nothing.
- **Ids:** shared things keep the main world's ids (abilities, moves, dash checks 1330000+,
  GridLeak counts), so the shared client code is identical.
- **Dashes tab:** `client/dash_tab.py` (Kivy) shows `plan.dash_board` (pure, tested): per dash
  unlocked, finished, stars done / star checks in this seed (from the server's checked + missing
  lists), and the next star's time; rebuilt only when that changes.
- **Client commands:** `/mec` (also shows the hard lock), `/dashes`, `/confirm_save`, `/next_volume`,
  `/launch`, `/inject`, `/dll_folder`, `/move`, `/moves`, `/reload`. `/reload` asks mec_ap.dll
  (0.3.0+, hello `"reload": true`) to call the game's own checkpoint reload; the answer says what
  the game did (`started` only when it sent its round reset). Worked in the city 2026-11-25.
  `client/auto_reload.py` reloads by itself when the player leaves a dash (cancel: 2 s, finish:
  6 s; also when an unlock arrives within 20 s of leaving, which is how an unlock earned by the
  dash just finished arrives; not for a finish replayed from the journal; cancelled by a new
  dash) if something was
  written that only a reload shows: a Dash Unlock, the first hard lock, the activity hiding. Any
  checkpoint reload clears that list (DLL 0.3.1 sends `round_reset` for each). At a game launch,
  writing the hard lock / activity hiding reloads once by itself, 3 s after both are complete
  (the dashes stream in over about a minute; 90 s fallback if they never are; once per DLL hello). `/auto_reload
  on|off`, kept in persistent storage (`mec_ap` / `auto_reload`). After a finish: not tried in game.
  `/move <move> on|off|ap` overrides
  one move or ability by hand (`plan.desired_flags` / `blocked_moves` take the overrides; the
  writes still go through `ProgressionWriter` and the movement volume). Overrides are kept per
  seed and slot in persistent storage (`mec_ap` / `move_overrides`). Not tried in game yet. The GUI's top bar has **Launch game** and **Inject DLL**
  buttons and a game / DLL status (`client/launcher.py`): Launch starts Steam app 1233570 and
  runs the injector, which waits for the game; the DLL folder is kept in Archipelago's
  persistent storage.
- **Seen in game, 2026-11-22** (a `hard_dash_lock` seed, local server, `mec_ap.dll` loaded): the
  client locked all 22 dashes and after a checkpoint reload only the 3 starting ones were on the
  map; two GridLeak bundle checks were sent; a 37.56 s Birdman's Route sent its finish and all 3
  star checks; the Dash Unlocks for Caleb's Run and Feature Creep arrived from them and both
  dashes were on the map after a reload; FlowAttack from the 3-star check was applied live
  through the DLL and read back.
- **`hide_other_activities` seen in game, 2026-11-22:** with a new seed and the client
  reconnected, a checkpoint reload left only the dashes held and the 6 Dead Drop Deliveries.
- **Not yet seen in game:** the goal.
