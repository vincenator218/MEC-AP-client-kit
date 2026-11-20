# Open questions

Research questions, numbered so other docs can point at them (`OPEN_QUESTIONS #10`). Settled
ones keep their number and move to the bottom with the answer. For the bigger picture (what a
full Archipelago still needs, and ideas not yet tried) see [`ROADMAP.md`](ROADMAP.md).

"FINDINGS §N" is the research log `ME-AP/FINDINGS.md`, which is **not in this repository**; every
result it holds that matters here is restated in these docs.

## Still open

### Client and DLL
2. **Entity lookup cost.** `mec_ap.dll` scans all writable memory (about 4.5 s, on its own
   thread) for every batch of applies. It could keep the flag entities it found and re-validate
   them (vtable, `[e+0x80]`, `0x2000` bit) before each call, re-scanning only when validation
   fails: deaths and checkpoint restarts replace the live entity.
12. **Applies not yet seen through the DLL** (`dll/README.md`): a persistent-entity ability
    (Focus, proven with Cheat Engine), taking an ability back (`revert_skill_tree_purchases`),
    and many applies in one session.
18. **DLL message coverage.** `NamedChallengeStarted` was not logged in the one run with MECMP
    loaded first, and was logged without it; `NamedChallengeCancelled` has been seen in dumps but
    never through the DLL. Neither affects checks (only the finish does).
19. **Offline.** Whether `NamedChallengeFinished` still fires with the PC offline. The dash type's
    `RequiresOnline` is 0, which suggests yes ([`DLL.md`](DLL.md) §11 question 4).
20. **Star thresholds.** Whether a time exactly on a star threshold earns the star. The client
    counts it.

### Items
5. **`live_entity` abilities marked `expected`** (ITEMS.md): same entity class and setup as the
   tested ones. With the DLL, each one received in a seed is a test: the client logs "is active
   now (read back from the game)".
6. **`persistent_entity` abilities marked `untested`**: only Focus is proven live. Disruptor
   Overload has world-object entities, so the DLL refuses it (more than 3 entities) and it applies
   at the next respawn.
7. `CriticalPathProgression_HasCollectedMagRopeLineConnector` has no check entity. It may be unused.
8. The 22 excluded `Unlocks_*` flags (ITEMS.md "Not items"): their persistent entities were not
   checked.
9. **Display names for abilities and collectibles.** Done for opportunities (FINDINGS §78,
   `data/opportunity_names.json`) and dashes (`data/named_challenges.json`). The game's own
   `localize` turned `ID_NC_DOWNTOWNCANYON` into `CONCRETE CANYON` in MECMP, so it works on this
   build ([`DLL.md`](DLL.md) §7); calling it from `mec_ap.dll` is not built.
10. Side missions: confirm a **live**-unlocked mission loads and plays correctly, and whether a
    death or fast travel also refreshes the replay menu.
11. Filler: is granting `XP` safe and useful?
11b. **District / world unlocks as items?** (FINDINGS §81) Untested, none in the pool:
    - **`Global_CityUnlockState` = 9** in a story-complete save. A numeric *stage*, not a
      boolean: if it stages map access it is a **progressive** item worth nine steps. The most
      promising untested flag.
    - `CriticalPathProgression_HasCollectedGridleakMapping` = 1: probably whether grid leaks show
      on the map.
    - `HasUnlockedDowntownSouth` = 1, `NomadMissionsUnlocked` = 1: area / content gates.
    - No record in a real save, so probably unused: `HasCollectedAlertRadar`,
      `HasEnteredAnchorForFirstTime`, `HasUnlockedTransitionConDt`.
    Test by live-writing each down on a backup save and watching the map, restoring before any
    autosave.
21. **Which side missions exist in free roam without their unlock**, and whether the rest unlock
    in a chain. Some could be started in free roam in the first live session (2026-10-29), which
    means a side mission picked as the main world's final activity may not be locked.

### Locations
13. **Real names or positions for collectibles**, for hints and for GridLeak sub-areas. Names:
    see #9. Positions: not started (each leak is only a GUID; numbering is alphabetical).
14a. Spot-check the finer zone codes (`RzRdz`, `DtTd`, ...) against the in-game map.
15. Identify the 8 "Misc Activity" `BronzeCompleted_` entries.
22. **Deliveries, grid nodes, billboards and the MetaGrid as DLL events.** They send the same
    challenge messages ([`DLL.md`](DLL.md) §6), but only dashes have been captured. Billboards and
    grid nodes are already flag-detected, so this matters mostly for the countdown deliveries.

### World / logic
16. **Which checks need which moves.** The logic files are where this goes:
    - main world: `apworld/mirrors_edge_catalyst/data/requirements.csv`, still empty;
    - Dashes world: `apworld/mirrors_edge_catalyst_dashes/data/requirements.csv`, two rows so far
      (2026-11-19: Caleb's Run needs MAG Rope; Out in the Open needs nothing).

    How to collect it: `tools/client/MEC_MoveToggles.pyw` removes moves one by one, and
    `tools/save/make_testing_save.py` makes a save with every activity selectable and enough XP
    to buy abilities (`tools/client/README.md`).
17. Whether removing MAG Rope uses from a finished-story save can soft-lock traversal. (Leaving
    the start and fast travel to every hideout work without it; SAVE_FILE.md.)

## Settled (kept for the record)

1. **Game-thread execution of `apply`.** Calls from a foreign thread (Cheat Engine
   `executeCodeEx`) crashed the game twice. **Solved by `mec_ap.dll` 0.2.1 (2026-11-13):** the
   flag-check entities are `PamServerProgressionFlagEntity` (server), so the DLL calls `apply`
   from its server tick hook. Coil and FastClimb applied live and read back; Coil worked in play
   at once. [`DLL.md`](DLL.md) §5.
1a. **Dashes as locations.** Done: the DLL hears `NamedChallengeFinished`, the client sends the
    finish and star checks (tested end to end 2026-11-12). The game has no per-dash lock
    ([`DLL.md`](DLL.md) §11c-d); the Dashes world uses a soft lock instead (`ROADMAP.md`).
3. **Reconnect / resync.** The client re-applies every received item after each load (writes
   are idempotent), and asks the DLL to re-check every ability when the DLL connects.
4. **The game's load state.** The client waits until the flag table pointer is set and
   `Unlocks_Coil` resolves, then one more tick before writing (`client/game.py`).
11a. **Opportunity unlocks work end to end** (tested on one): the completion flag puts the
    activity in the menu at the next load, it plays from there, and a real completion writes its
    `_CompletedTime`. `_Available` is not the gate. The 18 countdown deliveries and 8
    interventions never get a menu entry, so they are checks only (FINDINGS §78).
11c. **Five traversal items, with no flag and no mod** (FINDINGS §83/§84). One
    `PamMovementExclusionEntityData` instance, five booleans, each blocking one move; immediate,
    survives a death. The client drives one volume and re-asserts it every tick
    ([`MEMORY.md`](MEMORY.md) §5; volume size 20000 works, 50000 is ignored). The overlap with
    `Unlocks_DoubleWallrun` is resolved by **Progressive Wallrun**. Pipes and ladders are not
    covered by any of the five.
14. **`Ct` = Rezoning**: confirmed (§78: the localization Sids spell it `RZ`, and the Rezoning
    opportunities showed under Rezoning in game).
