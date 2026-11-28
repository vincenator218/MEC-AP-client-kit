# Mirror's Edge Catalyst Dashes

## What is randomized?

- **Dash Unlocks**: one per dash (22). You start with a few. A dash you have no unlock for is
  taken off the map and cannot be started (option `hard_dash_lock`, on by default). When an
  unlock arrives, **reload a checkpoint** to see the dash; fast travel or a death is not enough.
  With `mec_ap.dll` 0.3.0+ the client reloads by itself when you next leave a dash (`/auto_reload`).
  With `hard_dash_lock` off, every dash can be run, but a run of a locked dash does not count.
- **Moves**: Springboard, Climb Up, Ledge Hang, Wallrun (two Progressive Wallruns: the second is
  Double Wallrun) and MAG Rope are taken away and must be found.
- **Abilities**: every skill-tree ability. With `mec_ap.dll` loaded they work the moment you
  receive them; without it, at your next death or checkpoint restart.

## What are the checks?

- **Dashes**: finishing each of the 22 dashes, plus a check for each star tier you beat
  (1, 2 and 3 stars). A 3-star run sends all four checks at once.
- **GridLeaks**: one check every 10 leaks collected in a district, up to 60% of the district
  (both are options). The rest of each district's leaks are spare, so you never need them all.

## What is the goal?

Earn the number of dash stars set in your options (default 40 of the 66).

## What is not in this game?

Side missions, opportunities (Runs), deliveries and the story. For those, play the
**Mirror's Edge Catalyst** world. With `hide_other_activities` (on by default) they are taken
off the map while the client runs, so the dashes stand out; only the 6 Dead Drop Deliveries
stay, because the game always offers one per story phase.
