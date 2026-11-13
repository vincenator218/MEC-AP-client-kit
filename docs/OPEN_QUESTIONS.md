# Open questions / work before a release

## Client engineering
1. **Game-thread execution of `apply`.** Calls from a foreign thread (Cheat Engine
   `executeCodeEx`) crashed the game twice. Two candidate hook points are known from MECMP
   (FINDINGS §88): the `ServerGameWorld` tick (slot `0x141B42D28`) and the client replay
   updater (`0x141C491A0`). They need an injected DLL. On 2026-11-12 both slots held the expected
   originals on our build, and so did all 24 strong checks (`tools/client/verify_dll_addresses.py`,
   read-only). Nothing has been hooked or called yet. Everything needed to start, including the
   apply queue, is in [`DLL.md`](DLL.md) §5. Still open there: which thread owns the flag-check
   entities.
1a. **Event-driven checks instead of polling, and dashes as locations.** A message listener hears
   every finished named challenge (dash, delivery, grid node, billboard, MetaGrid) with its
   ContentId and time. Needs the DLL. Untested. See [`DLL.md`](DLL.md) §6 for the messages and
   §11 for what must be settled before dashes can be locations.
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
    **Done for opportunities** (FINDINGS §78): the 32 with a Runs-menu entry are named in
    `data/opportunity_names.json`. Still open for **abilities** (skill-tree text) and
    collectibles.
10. Side missions: confirm a **live**-unlocked mission loads and plays correctly, and whether a
    death or fast travel also refreshes the replay menu.
11. Filler: is granting `XP` safe and useful?
11a. **Opportunity unlocks work end to end** (tested on one): the completion flag puts the
    activity in the menu at the next load, it plays from there, and a real completion writes
    its `_CompletedTime`. `_Available` is not the gate. **Settled for deliveries**: the 18
    `BronzeCompleted_OWPh<N>Delivery<NN>` countdown deliveries and 8 interventions never get
    a menu entry at all, so they are checks only and are no longer items (§78).
11b. **District / world unlocks as items?** (FINDINGS §81) Untested, none in the pool:
    - **`Global_CityUnlockState` = 9** in a story-complete save. A numeric *stage*, not a
      boolean — if it stages map access it is a **progressive** item worth nine steps, and
      it is the single most promising untested flag we have.
    - `CriticalPathProgression_HasCollectedGridleakMapping` = 1 — probably whether grid
      leaks show on the map. Would also settle whether collectible visibility is gateable.
    - `HasUnlockedDowntownSouth` = 1, `NomadMissionsUnlocked` = 1 — area / content gates.
    - No record in a real save, so probably unused: `HasCollectedAlertRadar`,
      `HasEnteredAnchorForFirstTime`, `HasUnlockedTransitionConDt`.
    Test by live-writing each down on a backup save and watching the map, restoring before
    any autosave.
11c. **Five traversal items confirmed working, with no flag and no mod** — FINDINGS §83/§84.
    `PamMovementExclusionVolume` is a live object; each of five booleans blocks exactly one move,
    verified one at a time in game:

    | flag | offset | move | grant |
    |---|---|---|---|
    | `ExcludeVault` | `0xA0` | vault | write 0 to allow, 1 to block |
    | `ExcludeHeaveUp` | `0xA1` | mantle / pull up over a ledge | same |
    | `ExcludeHang` | `0xA2` | hang from a ledge | same |
    | `ExcludeWallrun` | `0xA3` | wallrun (vertical and horizontal) | same |
    | `ExcludeMagrope` | `0xA4` | MAG rope | same |

    Also on the object: `HalfExtents` (`Vec3`, `0x80`) and `Enabled` (`0x90`). Find instances by
    reading the class default at `typeinfo+0x20` (typeinfo = `Module+0x2878C00`), taking its
    first qword as the vtable, and scanning writable memory for 8-byte-aligned pointers to it.

    Effect is immediate, needs no `apply` call or game-thread hook, and survives a death.
    **Before using:** `HalfExtents` has an unmeasured ceiling — 2000 works, 50000 is ignored
    entirely. Volumes stream (61-62 in one session), so re-scan and re-apply after each load.
    Writing all instances overwrites the designers' per-surface volumes, so the level's own
    movement restrictions cannot be relied on while active. Pipes and ladders are not covered by
    any of the five. Resolve the overlap with the existing `Unlocks_DoubleWallrun` item.

## Locations
13. Real names or positions for collectibles, for hints. **Likely solved cheaply**: the game's
    own `localize` (`0x1436A8D40`) turns a Sid into display text. Needs in-process code. Grade it
    against an `ID_OPP_*_LABEL` Sid from §78 first ([`DLL.md`](DLL.md) §7).
14. ~~Verify `Ct` = Rezoning~~ — **confirmed** (§78: the localization SIDs spell it `RZ`,
    and the Rezoning opportunities showed under Rezoning in game). Still spot-check the
    finer zone codes (`RzRdz`, `DtTd`, …).
15. Identify the 8 "Misc Activity" `BronzeCompleted_` entries.

## World / logic
16. Which checks need which abilities (movement gating per collectible). Nothing has been done on this yet.
17. Whether removing MAG Rope uses from a finished-story save can soft-lock traversal.
