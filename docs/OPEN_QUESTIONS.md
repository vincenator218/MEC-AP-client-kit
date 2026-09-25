# Open questions / work before a release

## Client engineering
1. **Game-thread execution of `apply`.** This is required. Calls from a foreign thread
   (Cheat Engine `executeCodeEx`) crashed the game twice. The plan: an injected DLL hooks a
   per-frame game function and applies queued grants from there. No hook point has been chosen yet.
2. **Entity lookup cost.** The prototype AOB-scans all writable memory per grant. A client
   should find entities once, keep them, and re-validate them (vtable, `[e+0x80]`, `0x2000` bit)
   before each call. It re-scans only when validation fails, because deaths and checkpoint restarts
   replace the live entity.
3. **Reconnect/resync.** Re-apply every received item on connect and after each load. Writes
   are idempotent.
4. **Detect the game's load state**, for example by waiting until the flag table pointer is non-null
   and `Unlocks_Coil` resolves, before reading or writing.

## Items
5. **23 `live_entity` abilities marked `expected`**: they have the same setup as the tested
   ones. Spot-check them, or test them all with a script.
6. **11 `persistent_entity` abilities marked `untested`**: only Focus is proven live.
   Disruptor Overload has world-object entities, so it gets a table write only (applies at the next respawn).
7. `CriticalPathProgression_HasCollectedMagRopeLineConnector` has no check entity. It may be unused.
8. The 22 excluded `Unlocks_*` flags (see `ITEMS.md`): their persistent entities weren't checked.
9. Map the internal names to in-game display names (skill-tree text / localization).
10. Side missions: confirm a **live**-unlocked mission loads and plays correctly, and whether a
    death or fast travel also refreshes the replay menu.
11. Filler: is granting `XP` safe and useful?
11a. **Opportunity unlocks work** (tested on one): the completion flag puts the activity in
    the menu at the next load, like a side mission. `_Available` is not the gate: the map
    ignores it and a reload restores it from the save. Still to check: that a
    menu-unlocked opportunity actually plays, and the same on a delivery.
11b. **District unlocks as items?** `CriticalPathProgression_HasUnlockedDowntownSouth`,
    `HasUnlockedTransitionConDt`, `HasEnteredAnchorForFirstTime` and
    `NomadMissionsUnlocked` look like map/area gates (the underground included).
    If they behave like other flags, each is a big item. Untested.
12. Skill-tree purchases set the same flags. Decide how the client treats abilities the
    player buys.

## Locations
13. Real names or positions for collectibles, for hints.
14. Verify `Ct` = Rezoning and spot-check the zone codes.
15. Identify the 8 "Misc Activity" `BronzeCompleted_` entries.

## World / logic
16. Which checks need which abilities (movement gating per collectible). Nothing has been done on this yet.
17. Whether removing MAG Rope uses from a finished-story save can soft-lock traversal.
