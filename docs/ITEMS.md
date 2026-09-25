# Items

The full list is in `data/items.json` (109 items). Proposed item IDs start at
**1320000**. Location IDs are 1310000–1319999, so the two ranges don't overlap.

## Grant methods

See `MEMORY.md` for the mechanics.

| `grant_method` | what the client does | when the player gets it |
|---|---|---|
| `live_entity` | write the flag, then `apply` on the flag's per-spawn (`0x2000`) entity | immediately |
| `persistent_entity` | write the flag, then `apply` on its unique persistent entities (only if the flag has ≤ 3 entities) | immediately (tested on Focus); otherwise at the next respawn |
| `table_write_reload` | write the flag only | at the next load (checkpoint restart, relaunch) |
| `unknown` | nothing reliable yet | — |

## Test status (`live_status`)

- `tested`: granted and revoked in-game with this exact method.
- `expected`: same entity class, mode and setup as a tested flag, but not tried one by one.
- `untested`: the method is plausible but not tried. At worst, the table write still applies at the next respawn.

## Abilities and gear (`Unlocks_*`)

Grouped roughly by name. The in-game display names are mostly not mapped yet.
Known so far: `MoveEnemyBack` = Switch Place, and `IncreasedHealth0-4` = the
stamina tiers (+1 bar each).

| id | item | flag | hash | grant | status | note |
|---|---|---|---|---|---|---|
| 1320000 | Coil | `Unlocks_Coil` | `0xF996B210` | live_entity | expected |  |
| 1320001 | CombatRecovery | `Unlocks_CombatRecovery` | `0x37A952EC` | live_entity | expected |  |
| 1320002 | Disrupter_IncreaseRange | `Unlocks_Disrupter_IncreaseRange` | `0xFE47B0D7` | live_entity | expected |  |
| 1320003 | Disruptor_Overload | `Unlocks_Disruptor_Overload` | `0xB75C826E` | persistent_entity | untested | Calling its world-object entities crashed the game once; call only unique-data entities (docs/MEMORY.md). Live effect not yet confirmed. |
| 1320004 | Disruptor_StunHumans | `Unlocks_Disruptor_StunHumans` | `0x2B091FD6` | live_entity | expected |  |
| 1320005 | Disruptor_StunMech | `Unlocks_Disruptor_StunMech` | `0x38B355F9` | live_entity | expected |  |
| 1320006 | DoubleWallrun | `Unlocks_DoubleWallrun` | `0xF139B4B3` | live_entity | tested |  |
| 1320007 | ExtendedComboVulnerability | `Unlocks_ExtendedComboVulnerability` | `0x87156FC6` | persistent_entity | untested |  |
| 1320008 | ExtendedSlide | `Unlocks_ExtendedSlide` | `0x427FB289` | live_entity | expected |  |
| 1320009 | FastClimb | `Unlocks_FastClimb` | `0x6F18BEF0` | live_entity | expected |  |
| 1320010 | FlowAttack | `Unlocks_FlowAttack` | `0x06943543` | live_entity | expected |  |
| 1320011 | FlowAttack_PowerAttack | `Unlocks_FlowAttack_PowerAttack` | `0x710BF0CB` | live_entity | expected |  |
| 1320012 | FlowAttack_Special_PowerAttack | `Unlocks_FlowAttack_Special_PowerAttack` | `0x17EEE7F5` | live_entity | expected |  |
| 1320013 | Focus | `Unlocks_Focus` | `0x2C9CC1D5` | persistent_entity | tested | Table write alone applies at the next respawn; live grant/revoke proven by calling apply on its persistent entity. |
| 1320014 | Focus_FlowAttackFluency | `Unlocks_Focus_FlowAttackFluency` | `0x12B6DD5E` | persistent_entity | untested |  |
| 1320015 | Focus_ReachFlow_Increase | `Unlocks_Focus_ReachFlow_Increase` | `0xB4F7A73E` | persistent_entity | untested |  |
| 1320016 | Focus_ReachFlow_IncreaseExtra | `Unlocks_Focus_ReachFlow_IncreaseExtra` | `0x80E2C6E4` | persistent_entity | untested |  |
| 1320017 | Glove | `Unlocks_Glove` | `0x2CB07F0E` | persistent_entity | untested |  |
| 1320018 | HandToHandCombat | `Unlocks_HandToHandCombat` | `0x6EE99C14` | live_entity | expected |  |
| 1320019 | ImpactAttack_PowerAttack | `Unlocks_ImpactAttack_PowerAttack` | `0xB794DAFB` | live_entity | expected |  |
| 1320020 | ImpactAttack_Special_PowerAttack | `Unlocks_ImpactAttack_Special_PowerAttack` | `0x6AF13485` | live_entity | expected |  |
| 1320021 | IncreasedHealth0 | `Unlocks_IncreasedHealth0` | `0x848D8855` | live_entity | expected |  |
| 1320022 | IncreasedHealth1 | `Unlocks_IncreasedHealth1` | `0x848D8854` | live_entity | tested |  |
| 1320023 | IncreasedHealth2 | `Unlocks_IncreasedHealth2` | `0x848D8857` | live_entity | expected | Granted together with tiers 1/3/4 in testing. |
| 1320024 | IncreasedHealth3 | `Unlocks_IncreasedHealth3` | `0x848D8856` | live_entity | expected | Not bought in a normal playthrough, but has a live entity; granted (together with tiers 1-4) in testing: +1 stamina bar per tier. |
| 1320025 | IncreasedHealth4 | `Unlocks_IncreasedHealth4` | `0x848D8851` | live_entity | expected | Not bought in a normal playthrough, but has a live entity; granted (together with tiers 1-4) in testing: +1 stamina bar per tier. |
| 1320026 | LowerHealthEnforcer | `Unlocks_LowerHealthEnforcer` | `0x071FEB22` | persistent_entity | untested |  |
| 1320027 | LowerHealthProtector | `Unlocks_LowerHealthProtector` | `0xC0B346D0` | persistent_entity | untested |  |
| 1320028 | LowerHealthSentinel | `Unlocks_LowerHealthSentinel` | `0x243C4904` | persistent_entity | untested |  |
| 1320029 | LowerHealthShockProtector | `Unlocks_LowerHealthShockProtector` | `0x56E000EC` | persistent_entity | untested |  |
| 1320030 | MoveEnemyAttack | `Unlocks_MoveEnemyAttack` | `0x525F777A` | live_entity | expected |  |
| 1320031 | MoveEnemyBack | `Unlocks_MoveEnemyBack` | `0x67800619` | live_entity | tested | Switch Place |
| 1320032 | PositionalAdvantage | `Unlocks_PositionalAdvantage` | `0xEC427EC6` | persistent_entity | untested |  |
| 1320033 | QuickTurn | `Unlocks_QuickTurn` | `0x732EB4A1` | live_entity | expected |  |
| 1320034 | Shift | `Unlocks_Shift` | `0x2B48D119` | live_entity | expected |  |
| 1320035 | SkillWindowSkillRoll | `Unlocks_SkillWindowSkillRoll` | `0x92135F48` | live_entity | expected |  |

## MAG Rope (grapple)

The story normally grants these (Savant Extraordinaire, "Getting Magrope"), not the skill
tree. Each use of the rope is its own flag, so they work as separate or progressive items.
If you randomize them, world logic has to account for rope-only traversal.

| id | item | flag | hash | grant | status | note |
|---|---|---|---|---|---|---|
| 1320100 | MagRopeSwing | `CriticalPathProgression_HasCollectedMagRopeSwing` | `0xE77600AB` | live_entity | tested | Revoked and granted live in testing. |
| 1320101 | MagRopePullUp | `CriticalPathProgression_HasCollectedMagRopePullUp` | `0xE17601CF` | live_entity | expected | Live entity present; same mechanism as Swing. |
| 1320102 | MagRopePullDown | `CriticalPathProgression_HasCollectedMagRopePullDown` | `0x16F58B58` | live_entity | expected | Live entity present; same mechanism as Swing. |
| 1320103 | MagRopeLineConnector | `CriticalPathProgression_HasCollectedMagRopeLineConnector` | `0xD68DA442` | unknown | untested | No check entity found in a full scan; may be unused. Not recommended as an item yet. |

## Side mission unlocks

Writing `SilverCompleted_<mission> = 1` puts the mission in **Missions → Side Missions**
at the next load. The client never writes `<mission>_CompletedTime`, so that value
going from 0 to non-zero is the matching location check (see `LOCATIONS.md`).

| id | item | flag | hash | grant | status | note |
|---|---|---|---|---|---|---|
| 1320200 | Side Mission Unlock - An Ear to the Ground | `SilverCompleted_An Ear to the Ground` | `0x46B3EE1E` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320201 | Side Mission Unlock - Birdman's Delivery | `SilverCompleted_Birdman's Delivery` | `0xACB87237` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320202 | Side Mission Unlock - Break And Entry | `SilverCompleted_Break And Entry` | `0xF3FD4240` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320203 | Side Mission Unlock - Caught in the Web | `SilverCompleted_Caught in the Web` | `0x8AFF1902` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320204 | Side Mission Unlock - Complete Coverage | `SilverCompleted_Complete Coverage` | `0xF2AB7D67` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320205 | Side Mission Unlock - Drone Works | `SilverCompleted_Drone Works` | `0x02966440` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320206 | Side Mission Unlock - Exit Strategy | `SilverCompleted_Exit Strategy` | `0xFB8B721B` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320207 | Side Mission Unlock - Finger on the Pulse | `SilverCompleted_Finger on the Pulse` | `0x896C9E36` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320208 | Side Mission Unlock - The Meta Grid | `SilverCompleted_The Meta Grid` | `0x2483D2FC` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320209 | Side Mission Unlock - Top of the World | `SilverCompleted_Top of the World` | `0xFB1C79F9` | table_write_reload | tested | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |
| 1320210 | Side Mission Unlock - Two Pigeons With One Stone | `SilverCompleted_Two Pigeons With One Stone` | `0x09F7D060` | table_write_reload | expected | Appears in Missions > Side Missions at the next load (checkpoint restart proven). |

Not yet verified: that a live-unlocked mission loads and plays correctly (a save-edit
unlock did), and whether a death or fast travel also refreshes the menu.

## Opportunity unlocks (open-world activities)

The in-game marker calls these **OPPORTUNITY**; deliveries are one kind. Writing an
activity's completion flag (`MiscCompleted_<name>` / `BronzeCompleted_<name>`) puts it in
the Runs/Opportunities menu at the next load, **without** touching its
`_CompletedTime`. Tested end to end on `OW Opp DtPh2 04`: written live, it appeared in the menu after a
checkpoint restart with no completion time, it played from the menu, and the real
completion time was saved.

The client never writes `_CompletedTime`, so that value going from 0 to a real time is
the matching location check (see `LOCATIONS.md`). `_Available` is not involved: the map
ignores it and a reload restores it from the save.

| id | item | flag | hash | grant | status | note |
|---|---|---|---|---|---|---|
| 1320300 | Opportunity Unlock - Anchor Ph4 #01 | `MiscCompleted_OW Opp AncPh4 01` | `0xD49DACF5` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320301 | Opportunity Unlock - Anchor Ph4 #02 | `MiscCompleted_OW Opp AncPh4 02` | `0xD49DACF6` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320302 | Opportunity Unlock - Anchor Ph4 #03 | `MiscCompleted_OW Opp AncPh4 03` | `0xD49DACF7` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320303 | Opportunity Unlock - Anchor Ph4 #04 | `MiscCompleted_OW Opp AncPh4 04` | `0xD49DACF0` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320304 | Opportunity Unlock - Anchor Ph4 #05 | `MiscCompleted_OW Opp AncPh4 05` | `0xD49DACF1` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320305 | Opportunity Unlock - Anchor Ph4 #06 | `MiscCompleted_OW Opp AncPh4 06` | `0xD49DACF2` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320306 | Opportunity Unlock - Anchor Ph4 #07 | `MiscCompleted_OW Opp AncPh4 07` | `0xD49DACF3` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320307 | Opportunity Unlock - Anchor Ph4 #08 | `MiscCompleted_OW Opp AncPh4 08` | `0xD49DACFC` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320308 | Opportunity Unlock - Anchor Ph5 #01 | `MiscCompleted_OW Opp AncPh5 01` | `0xD49D28D4` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320309 | Opportunity Unlock - Anchor Ph5 #02 | `MiscCompleted_OW Opp AncPh5 02` | `0xD49D28D7` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320310 | Opportunity Unlock - Anchor Ph5 #03 | `MiscCompleted_OW Opp AncPh5 03` | `0xD49D28D6` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320311 | Opportunity Unlock - Anchor Ph5 #04 | `MiscCompleted_OW Opp AncPh5 04` | `0xD49D28D1` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320312 | Opportunity Unlock - Anchor Ph5 #05 | `MiscCompleted_OW Opp AncPh5 05` | `0xD49D28D0` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320313 | Opportunity Unlock - Anchor Ph5 #06 | `MiscCompleted_OW Opp AncPh5 06` | `0xD49D28D3` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320314 | Opportunity Unlock - Rezoning Ph6 #01 | `MiscCompleted_OW Opp CtPh6 01` | `0x08B3012C` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320315 | Opportunity Unlock - Rezoning Ph6 #02 | `MiscCompleted_OW Opp CtPh6 02` | `0x08B3012F` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320316 | Opportunity Unlock - Rezoning Ph6 #03 | `MiscCompleted_OW Opp CtPh6 03` | `0x08B3012E` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320317 | Opportunity Unlock - Rezoning Ph6 #04 | `MiscCompleted_OW Opp CtPh6 04` | `0x08B30129` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320318 | Opportunity Unlock - Rezoning Ph6 #05 | `MiscCompleted_OW Opp CtPh6 05` | `0x08B30128` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320319 | Opportunity Unlock - Rezoning Ph6 #06 | `MiscCompleted_OW Opp CtPh6 06` | `0x08B3012B` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320320 | Opportunity Unlock - Downtown Ph2 #01 | `MiscCompleted_OW Opp DtPh2 01` | `0xB1DE750F` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320321 | Opportunity Unlock - Downtown Ph2 #02 | `MiscCompleted_OW Opp DtPh2 02` | `0xB1DE750C` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320322 | Opportunity Unlock - Downtown Ph2 #03 | `MiscCompleted_OW Opp DtPh2 03` | `0xB1DE750D` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320323 | Opportunity Unlock - Downtown Ph2 #04 | `MiscCompleted_OW Opp DtPh2 04` | `0xB1DE750A` | table_write_reload | tested | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320324 | Opportunity Unlock - Downtown Ph2 #05 | `MiscCompleted_OW Opp DtPh2 05` | `0xB1DE750B` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320325 | Opportunity Unlock - Downtown Ph2 #06 | `MiscCompleted_OW Opp DtPh2 06` | `0xB1DE7508` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320326 | Opportunity Unlock - Downtown Ph3 #01 | `MiscCompleted_OW Opp DtPh3 01` | `0xB1E011EE` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320327 | Opportunity Unlock - Downtown Ph3 #02 | `MiscCompleted_OW Opp DtPh3 02` | `0xB1E011ED` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320328 | Opportunity Unlock - Downtown Ph3 #03 | `MiscCompleted_OW Opp DtPh3 03` | `0xB1E011EC` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320329 | Opportunity Unlock - Downtown Ph3 #04 | `MiscCompleted_OW Opp DtPh3 04` | `0xB1E011EB` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320330 | Opportunity Unlock - Downtown Ph3 #05 | `MiscCompleted_OW Opp DtPh3 05` | `0xB1E011EA` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320331 | Opportunity Unlock - Downtown Ph3 #06 | `MiscCompleted_OW Opp DtPh3 06` | `0xB1E011E9` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320332 | Opportunity Unlock - Downtown Ph3 #07 | `MiscCompleted_OW Opp DtPh3 07` | `0xB1E011E8` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320333 | Opportunity Unlock - Downtown Ph3 #08 | `MiscCompleted_OW Opp DtPh3 08` | `0xB1E011E7` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320334 | Opportunity Unlock - The View Ph7 #01 | `MiscCompleted_OW Opp VwPh7 01` | `0x50BB71BB` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320335 | Opportunity Unlock - The View Ph7 #02 | `MiscCompleted_OW Opp VwPh7 02` | `0x50BB71B8` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320336 | Opportunity Unlock - The View Ph7 #03 | `MiscCompleted_OW Opp VwPh7 03` | `0x50BB71B9` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320337 | Opportunity Unlock - The View Ph7 #04 | `MiscCompleted_OW Opp VwPh7 04` | `0x50BB71BE` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320338 | Opportunity Unlock - The View Ph7 #05 | `MiscCompleted_OW Opp VwPh7 05` | `0x50BB71BF` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320339 | Opportunity Unlock - The View Ph7 #06 | `MiscCompleted_OW Opp VwPh7 06` | `0x50BB71BC` | table_write_reload | expected | Appears in the Runs/Opportunities menu at the next load (checkpoint restart proven). Its _CompletedTime stays 0 until the player really finishes it. |
| 1320400 | Opportunity Unlock - Delivery Ph2 #1 | `BronzeCompleted_OWPh2Delivery01` | `0xAE8D25F6` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320401 | Opportunity Unlock - Delivery Ph2 #2 | `BronzeCompleted_OWPh2Delivery02` | `0xAE8D25F5` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320402 | Opportunity Unlock - Delivery Ph2 #3 | `BronzeCompleted_OWPh2Delivery03` | `0xAE8D25F4` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320403 | Opportunity Unlock - Delivery Ph3 #1 | `BronzeCompleted_OWPh3Delivery01` | `0x415A60B7` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320404 | Opportunity Unlock - Delivery Ph3 #2 | `BronzeCompleted_OWPh3Delivery02` | `0x415A60B4` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320405 | Opportunity Unlock - Delivery Ph3 #3 | `BronzeCompleted_OWPh3Delivery03` | `0x415A60B5` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320406 | Opportunity Unlock - Delivery Ph4 #1 | `BronzeCompleted_OWPh4Delivery01` | `0x04DE1A70` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320407 | Opportunity Unlock - Delivery Ph4 #2 | `BronzeCompleted_OWPh4Delivery02` | `0x04DE1A73` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320408 | Opportunity Unlock - Delivery Ph4 #3 | `BronzeCompleted_OWPh4Delivery03` | `0x04DE1A72` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320409 | Opportunity Unlock - Delivery Ph5 #1 | `BronzeCompleted_OWPh5Delivery01` | `0x97AB5531` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320410 | Opportunity Unlock - Delivery Ph5 #2 | `BronzeCompleted_OWPh5Delivery02` | `0x97AB5532` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320411 | Opportunity Unlock - Delivery Ph5 #3 | `BronzeCompleted_OWPh5Delivery03` | `0x97AB5533` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320412 | Opportunity Unlock - Delivery Ph6 #1 | `BronzeCompleted_OWPh6Delivery01` | `0xF798D3F2` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320413 | Opportunity Unlock - Delivery Ph6 #2 | `BronzeCompleted_OWPh6Delivery02` | `0xF798D3F1` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320414 | Opportunity Unlock - Delivery Ph6 #3 | `BronzeCompleted_OWPh6Delivery03` | `0xF798D3F0` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320415 | Opportunity Unlock - Delivery Ph7 #1 | `BronzeCompleted_OWPh7Delivery01` | `0x8A660EB3` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320416 | Opportunity Unlock - Delivery Ph7 #2 | `BronzeCompleted_OWPh7Delivery02` | `0x8A660EB0` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |
| 1320417 | Opportunity Unlock - Delivery Ph7 #3 | `BronzeCompleted_OWPh7Delivery03` | `0x8A660EB1` | table_write_reload | expected | Same mechanism as the opportunities; not tested on a delivery specifically. |

## Not items

- **Basic moves** (climb, vault, basic wallrun, roll and so on) have no flag at all. No flag-check
  entity or flag name exists for them. They are hard-wired and can't be taken away.
- **22 other `Unlocks_*` flags** are never set in a normal playthrough and have
  no per-spawn entity. Their persistent entities were not checked. Leave them out
  until tested: `Unlocks_BreachDoors`, `Unlocks_CityAlertDisrupt`, `Unlocks_CityAlertSafePositions`, `Unlocks_CombatFluency`, `Unlocks_CombatReticle`, `Unlocks_CombatScavengeLevel`, `Unlocks_Disrupter_Increase_AngleOfEffect`, `Unlocks_Disruptor_Extra_Battery`, `Unlocks_GetSpeedAttack`, `Unlocks_HardLandingLowDrain`, `Unlocks_ImpactMomentum`, `Unlocks_LowDrainAtLowSpeed`, `Unlocks_LowDrainInFlow`, `Unlocks_Placeholder`, `Unlocks_ScavengeLevel`, `Unlocks_ShiftFluency`, `Unlocks_SkillMoveInvulnerabilityLevel0`, `Unlocks_SkillMoveInvulnerabilityLevel1`, `Unlocks_SkillMoveInvulnerabilityLevel2`, `Unlocks_SkillWindowSpringboard`, `Unlocks_SkillWindowWallClimb`, `Unlocks_StartBoost`.
- **XP** (`XP`, `XP_Gained`, `XP_Used`): granting it as filler is untested.

## Design notes

- The skill-tree menu still lets the player **buy** abilities with XP, and buying sets
  the same flag. Decide whether the client reverts unearned purchases, or whether the
  starting save gives no XP.
- A starting save with every ability cleared can be made with
  `tools/save/clear_all_unlocks.py`. Tested: nothing is re-granted from mission state at load.
