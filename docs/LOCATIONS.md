# Locations

The full list is in `data/locations.json` / `data/locations.csv`, one row per location:
`id, name, category, district, area, default, flag, hash, detection, note`.
To regenerate it, run `python tools/build_checks.py`. Once a world is published, freeze
the file so IDs never shift. IDs are assigned in name order inside each block.

**853 flag locations, 793 on by default**, plus the **22 dashes** (below), which have no flag.

The worlds do not use every row as-is: both replace the 324 per-leak GridLeak rows with
per-district *count* checks (ids 1310500+n Downtown, 1310600+n Anchor, 1310700+n The View,
1310800+n Rezoning), and the main world turns most categories into options
(`apworld/README.md`).

## Detecting a check

Every location in `locations.json` is one progression flag. Poll its value in the live flag
table (`MEMORY.md` §2), or read it from the save file (`SAVE_FILE.md`). A location counts as
checked when:

| rule | used by |
|---|---|
| value ≥ 1 | collectibles (GridLeak, Electronic Part, Recording, Document, Secret Bag) |
| value == 1 | Security Hub, Grid Node, Billboard Hack, Opportunity |
| `<mission>_CompletedTime` goes from 0 to non-zero | Side Mission, delivery Opportunity, other missions |

Missions are detected through `_CompletedTime`, **not** through `SilverCompleted_` /
`BronzeCompleted_`. The client writes `SilverCompleted_<m>` to unlock a side mission
(an item, see `ITEMS.md`), but never writes `_CompletedTime`. So a completion time
appearing means the player really finished it.

Verified:
- The GridLeak hashes match the ones used by an earlier save-polling proof of concept,
  which sent real checks to an Archipelago server.
- Every category's hashes resolve against a real save.
- Collectible totals match the in-game World Progression screen.

## On by default (793)

| ID block (1310000 +) | category | count | flag pattern |
|---|---|---|---|
| +0000 | GridLeak | 324 | `<District>GridLeaks_<District>CompulsionOrb<GUID>` (Construction = Rezoning) |
| +1000 | Electronic Part | 251 | `ElectronicParts<Zone>_ChipNNTaken` |
| +2000 | Surveillance Recording | 45 | `AudioPickup<Zone>_…` |
| +3000 | Document | 42 | `Intel<Zone>_…` (not `IntelCollectiblesWorld/Mission`) |
| +4000 | Secret Bag | 40 | `SecretBag<Zone>_…` |
| +5000 | Security Hub | 6 | `SecurityHubsCompleted_SecHub<X>` |
| +5100 | Grid Node | 3 | `GridNodes_{Rezoning,Dt,View}Completed` |
| +5200 | Billboard Hack | 12 | `HackableBillboards_<x>NN` |
| +6000 | Opportunity | 40 | `MiscCompleted_OW Opp <Dist>Ph<N> NN` |
| +7000 | Side Mission | 12 | `<Mission>_CompletedTime` (11 replayable missions + Birdman's Delivery) |
| +8000 | Opportunity (Delivery) | 18 | `OWPh<2-7>Delivery0<1-3>_CompletedTime` |

### Opportunity names

The 40 `MiscCompleted_OW Opp …` activities are the world's **OPPORTUNITY** markers.
**32 of them appear in the Runs tab of the replay menu and their in-game names are
known** (decoded in game by writing a unique `_CompletedTime` to each and reading the
menu back -- FINDINGS §78). `locations.json` uses those names, with the type
(fragile delivery / covert delivery / diversion) in the `note` column;
`data/opportunity_names.json` is the raw map.

The remaining 8 are **interventions**: they exist in the world but never get a Runs
entry, so they keep an internal label. The 18 `OWPh<N>Delivery<NN>` deliveries are
**countdown** runs -- no time is recorded and they are not listed in the menu either --
but all 26 still write their completion flags, so they are ordinary checks.

Zone codes:

| code | zone | district |
|---|---|---|
| RzRdz | Rdz Development Zone | Rezoning |
| RzOt | Omnistat Tunnels | Rezoning |
| DtTd | Triumvirate Drive | Downtown |
| DtCh | Charter Hill | Downtown |
| DtCy | Centurian Yards | Downtown |
| DtCp | Concord Plaza | Downtown |
| AcCv | Crystal Valley | Anchor |
| AcSh | Shimmering Heights | Anchor |
| AcEv | Eden Village | Anchor |
| VwOp | Ocean Pier | The View |
| VwRb | Regatta Bay | The View |
| Trainstation | Zephyr Transit Hub | — |
| TheShard | The Shard | — |

## Dashes (no flag; 1330000+)

The 22 dashes are not in `locations.json`: a dash has no progression flag. They are in
`data/named_challenges.json` (ContentId, Sid, stat code, district, display name, star times,
`ap_index` = position in the in-game dash list). A finish is detected by `mec_ap.dll`, which hears
the game's "challenge finished" message (`docs/DLL.md` §6). Each dash has a finish check and
three star checks, ids `1330000 + 10 * ap_index + tier` (tier 0 = finished, 1-3 = stars); a run
earns every star whose time it beats (a time exactly on a threshold is counted; unverified).

The best time per dash is also in the save's stats block, as text (`docs/DLL.md` §11d): a
possible no-DLL detection path, untested.

## Included but off by default (60)

| category | count | why it's off |
|---|---|---|
| Story Mission | 20 | Only usable if the starting save doesn't finish the story. |
| Security Hub: MischiefMaker, Payback | 2 | Cleared inside story missions. |
| Grid Node: Anchor | 1 | It's a story mission. |
| Misc Activity | 8 | Other `BronzeCompleted_` content with no known in-game name (probably intro/tutorial). |
| Mission collectibles | 29 | GreenCollectiblesStory 9, GreenCollectiblesMission 8, RunnerBagsMission 8, IntelCollectiblesMission 4. These are inside story missions, and the value is a **count**, so a threshold must be chosen. |

## Deliberately excluded

- `SecurityCameras_*Destroyed` (194), `Doors_*`, `FastTravel_Discovered*`, `LairPhotoLocations_*`,
  `CriticalPathProgression_*` (story state), `IntelCollectiblesWorld` (a counter) and `Collectables_*` totals.
- Player-made time trials (user content, not stable). Dashes are covered above.

## Known gaps

1. **Collectible names are placeholders.** "GridLeak - Anchor 017" is one specific GUID, but the
   numbering is alphabetical by GUID, not by map position. Electronic parts keep their real chip
   numbers. Useful hints would need world positions from the level data.
2. ~~`Ct` = Rezoning~~: confirmed (the localization Sids spell it `RZ`, and the Rezoning
   opportunities showed under Rezoning in game; FINDINGS §78).
3. Spot-check one zone code per district against the in-game map.
   The in-game marker calls these activities **OPPORTUNITY**, and deliveries are one
   kind of opportunity, which is why both blocks are named that way. Rezoning
   couldn't be checked on a fresh save: its district may not be on the map yet.
4. **Balance:** 793 locations against about 50 items needs filler, or fewer locations. Both
   worlds solve it with options: the main world has a toggle per category and GridLeak bundles;
   the Dashes world has star tiers and GridLeak bundles capped at a share of each district.
5. **GridLeak sub-areas.** A leak is known only by its district and a GUID. Grouping leaks by
   smaller areas ("15 in the Underground") needs each leak's world position, read from memory or
   the level data. Not started.
