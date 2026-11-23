# Mirror's Edge Catalyst Dashes Setup Guide

## Requirements

- Mirror's Edge Catalyst for PC (the Steam build the offsets were taken from).
- Archipelago 0.6.4 or newer, with `mirrors_edge_catalyst_dashes.apworld` in `custom_worlds`.
- `mec_ap.dll` and `mec_ap_inject.exe` from the client kit (`dll/README.md`): dashes are only
  detected through it.
- A **story-complete** save of your own.

## Make the seed save

With the game closed, back up `Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`, then:

```
python tools/save/make_seed_save.py PROF_SAVE --out PROF_SAVE_seed
```

and put `PROF_SAVE_seed` in place as `PROF_SAVE`. It keeps the story and clears every ability
and every GridLeak, so the checks can be earned again.

## Play

1. Start the game, load in, and run `mec_ap_inject.exe`. `mec_ap.log` next to the DLL should say
   `ready` and `apply: check passed`.
2. In the Archipelago Launcher pick **Mirror's Edge Catalyst Dashes Client** and connect.
3. The client says `Connected to mec_ap.dll ... Dash checks are on. Received abilities apply
   immediately.`
4. Before a new seed, delete `mec_ap_events.jsonl` and `mec_ap_acked.txt` next to the DLL, or
   runs from before the seed are sent to it.

Locked dashes: once the client is connected and the world is loaded it says `Hard dash lock: 22
dashes are tied to their Dash Unlock.` Reload a checkpoint once so the dashes you do not hold
leave the map, and again each time a Dash Unlock arrives. When you close the client, every dash
comes back on the map (the lock lives in game memory; the unlocks you hold are in your save).

Client commands: `/mec` (stars, unlocked dashes, moves, DLL state), `/dashes` (which dashes are
unlocked), `/confirm_save`, `/next_volume` (a move that should be blocked still works).

## Logic

Which moves each dash and star tier needs is not recorded yet (`data/requirements.csv`). Until it
is, the logic assumes a dash needs only its unlock. With `traversal_items: randomized` a seed can
ask for a dash you cannot finish yet; `start_with` avoids that.
