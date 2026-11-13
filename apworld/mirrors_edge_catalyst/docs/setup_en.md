# Mirror's Edge Catalyst Setup Guide

## Requirements

- Mirror's Edge Catalyst for PC, the build the offsets were taken from. The client checks
  them when it attaches and warns if they do not match.
- Archipelago 0.6.4 or newer, with `mirrors_edge_catalyst.apworld` in `custom_worlds`.
- A **story-complete** save of your own.

## Make the seed save

The game must be fully closed. Back up `Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`
first, then build a starting save from your story-complete one:

```
python tools/save/make_seed_save.py PROF_SAVE --out PROF_SAVE_seed
```

Put `PROF_SAVE_seed` in place as `PROF_SAVE`. It has the story done, the city open, and
no abilities, collectibles or activity completions. Use one seed save per slot.

## Play

1. Start the game and load the seed save.
2. Open the Archipelago Launcher and pick **Mirror's Edge Catalyst Client**, then connect to
   your room. If it says access was denied, run the launcher as administrator.
3. The client finds the game by itself and survives the game closing and reopening.

### Dashes (optional, `dashes: true`)

Dashes have no save flag, so they need `mec_ap.dll` loaded into the game. Build it once (see
`dll/README.md` in the client kit), then after each game start run `mec_ap_inject.exe`. The client
says `Connected to mec_ap.dll ... Dash checks are on.` Finishing a dash sends its check, and each
star time you beat sends that star's check. Before a new seed, delete `mec_ap_events.jsonl` and
`mec_ap_acked.txt` next to the DLL, or older runs are sent to the new seed. Dashes are not locked:
you can play any of them at any time.

Client commands:

- `/mec`: game connection, Data Shards, which moves are blocked (as read back from the game).
- `/confirm_save`: see below.
- `/next_volume`: if a move that should be blocked still works, the client is driving a
  movement volume that does not reach you; this makes it pick another.

### "This save already has N finished locations"

When the first look at a save finds more than 25 finished locations the slot never sent,
the client assumes it is the wrong save. It sends nothing and writes nothing, so it cannot
alter a normal save by accident. If it is the right save, type `/confirm_save`.

## What the client changes in your save

Granted items are progression flags, and the game's autosave keeps them, so the seed save
carries your items. With `revert_skill_tree_purchases` on, the client also sets any
randomized ability you bought but did not receive back to 0. Traversal moves are never
saved: closing the client or the game gives them all back.
