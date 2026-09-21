# Locations

The full list is in `data/locations.json` / `data/locations.csv`, one row per location:
`id, name, category, district, area, default, flag, hash, detection, note`.
To regenerate it, run `python tools/build_checks.py`. Once a world is published, freeze
the file so IDs never shift. IDs are assigned in name order inside each block.

**852 locations, 792 on by default.**

## Detecting a check

Every location is one progression flag. Poll its value in the live flag table
(`MEMORY.md` §2), or read it from the save file (`SAVE_FILE.md`). A location
counts as checked when:

| rule | used by |
|---|---|
| value ≥ 1 | collectibles (GridLeak, Electronic Part, Recording, Document, Secret Bag) |
| value == 1 | Security Hub, Grid Node, Billboard Hack, Opportunity Mission |
| `<mission>_CompletedTime` goes from 0 to non-zero | Side Mission, Delivery, other missions |

Missions are detected through `_CompletedTime`, **not** through `SilverCompleted_` /
`BronzeCompleted_`. The client writes `SilverCompleted_<m>` to unlock a side mission
(an item, see `ITEMS.md`), but never writes `_CompletedTime`. So a completion time
appearing means the player really finished it.

Verified:
- The GridLeak hashes match the ones used by an earlier save-polling proof of concept,
  which sent real checks to an Archipelago server.
- Every category's hashes resolve against a real save.
- Collectible totals match the in-game World Progression screen.

## On by default (792)

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
| +6000 | Opportunity Mission | 40 | `MiscCompleted_OW Opp <Dist>Ph<N> NN` |
| +7000 | Side Mission | 11 | `<Mission>_CompletedTime` |
| +8000 | Delivery | 18 | `OWPh<2-7>Delivery0<1-3>_CompletedTime` |

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
- Dashes / time trials: their results are not in the save or the flag table.

## Known gaps

1. **Collectible names are placeholders.** "GridLeak - Anchor 017" is one specific GUID, but the
   numbering is alphabetical by GUID, not by map position. Electronic parts keep their real chip
   numbers. Useful hints would need world positions from the level data.
2. `Ct` in the opportunity names (CtPh6) is assumed to be Rezoning. Unverified.
3. Spot-check one zone code per district against the in-game map.
4. **Balance:** 792 locations against about 50 items needs filler, or fewer default
   locations. A natural option set is a toggle per collectible category, plus side missions,
   opportunities, deliveries, hubs, nodes and billboards.
