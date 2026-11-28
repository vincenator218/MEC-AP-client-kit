# Mirror's Edge Catalyst Dashes Setup Guide

## Requirements

- Mirror's Edge Catalyst for PC (the Steam build the offsets were taken from).
- Archipelago 0.6.4 or newer, with `mirrors_edge_catalyst_dashes.apworld` in `custom_worlds`.
- `mec_ap.dll` and `mec_ap_inject.exe` from the client kit (`dll/README.md`): dashes are only
  detected through it.
- A **story-complete** save of your own.

## Make the seed save

Connect the client to a new seed with the game **closed**. It says the save is not a seed save
yet and shows a **New seed save** button: press it. It copies
`Documents\Mirrors Edge Catalyst\settings\PROF_SAVE` to `PROF_SAVE.before_<seed>_<date>`, then
turns `PROF_SAVE` into a seed save: the story stays done, and every ability, GridLeak, dash lock
and activity completion is cleared so the checks can be earned again. It also moves
`mec_ap.dll`'s run journal from the last seed aside. The button only shows for a new run that
still needs it; `/new_save` does it at any time (to start over, say). It refuses while the game
is running, since the game writes its save when it exits.

Without the client, `python tools/save/make_seed_save.py PROF_SAVE --out PROF_SAVE_seed` from the
client kit does the same, and you put `PROF_SAVE_seed` in place as `PROF_SAVE` yourself.

## Play

1. Start the game and load `mec_ap.dll`: the client's **Launch game** or **Inject DLL** button
   (below), or run `mec_ap_inject.exe` yourself. `mec_ap.log` next to the DLL should say `ready`,
   `apply: check passed` and `reload: check passed`.
2. In the Archipelago Launcher pick **Mirror's Edge Catalyst Dashes Client** and connect.
3. The client says `Connected to mec_ap.dll ... Dash checks are on. Received abilities apply
   immediately.`

Locked dashes: once the client is connected and the world is loaded it says `Hard dash lock: 22
dashes are tied to their Dash Unlock.` The dashes you do not hold leave the map at the next
checkpoint reload, which the client does by itself (see **Automatic reload** below). When you close the client, every dash
comes back on the map (the lock lives in game memory; the unlocks you hold are in your save).

Other activities: the client also says `Hid 92 other activities`. The same reload clears the
opportunities, hubs, side missions and deliveries from the map (not the 6 Dead Drop
Deliveries). They come back when you close the client. Turn it off with
`hide_other_activities: false`.

Game and DLL buttons: the client's top bar has **Launch game** (starts the game through Steam
and loads `mec_ap.dll` once it is up) and **Inject DLL** (loads it into a game that is already
running), with the game and DLL state next to them. The first time, a file dialog asks for
`mec_ap.dll` (it must sit next to `mec_ap_inject.exe`); the folder is remembered. `/dll_folder`
opens the dialog again to change it, and `/dll_folder <folder>` types it instead. The DLL has to be
loaded again after every game start. `/launch` and `/inject` do the same as the buttons.

The client window has a **Dashes** tab: your stars against the goal, then every dash you hold an
unlock for (finished or not, stars out of the seed's star checks, and the time to beat for the
next star), with the locked dashes listed below them.

Client commands: `/mec` (stars, unlocked dashes, moves, DLL state), `/dashes` (which dashes are
unlocked), `/confirm_save`, `/next_volume` (a move that should be blocked still works),
`/reload` (reload the last checkpoint, as the pause menu does, without opening it; needs
`mec_ap.dll` 0.3.0 or later).

**Automatic reload:** a new Dash Unlock only shows on the map after a checkpoint reload. With
`mec_ap.dll` 0.3.0 or later, the client does that reload for you: when you leave a dash (quit
it, or after finishing it once you choose to leave the results screen; restarting from there
does not reload), if a Dash Unlock arrived since the last reload. With a DLL older than 0.3.2 it
reloads 6 seconds after the finish instead. It
also reloads once by itself a few seconds after you load into the city, when it puts the hard
lock and the hidden activities in place, so you no longer reload at every game launch. It never
reloads during a dash, and
a reload of your own (pause menu or `/reload`) counts too. `/auto_reload off` turns it off,
`/auto_reload on` back on, and `/auto_reload` says what is waiting to show.

Turning moves on and off by hand (a fail-safe, and a way to work out what each dash needs):
- `/moves` lists every traversal move and ability, what the server gave you, and any override.
- `/move <move> on` or `/move <move> off` overrides one move, received or not. Names ignore
  case and spaces, and a unique part is enough (`/move mag rope off`, `/move coil on`).
  Progressive Wallrun takes `0`, `1` (wallrun) or `2` (double wallrun).
- `/move <move> ap` gives the move back to the server; `/move reset` does it for all of them.
  An ability you turned on without holding it is taken back.

Overrides only change moves and abilities, never dash unlocks or checks. They are kept per seed
and slot across client restarts, and `/mec` reminds you while any are on. Abilities change at
once with `mec_ap.dll` (otherwise at the next respawn); traversal moves within a second.

## Logic

Which moves each dash and star tier needs is not recorded yet (`data/requirements.csv`). Until it
is, the logic assumes a dash needs only its unlock. With `traversal_items: randomized` a seed can
ask for a dash you cannot finish yet; `start_with` avoids that.
