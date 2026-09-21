# Items

The full list is in `data/items.json` (51 items). Proposed item IDs start at
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
