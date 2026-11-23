# Roadmap: from this kit to a full Archipelago

A design document and a bucket of ideas for whoever picks this up. What exists and works is in
the other docs; this page says where it could go next, in roughly the order it matters, and
labels every idea as **proven**, **partly tested** or **idea only**.

## Where things stand (2026-11-19)

Two playable worlds share one kit:

| | **Mirror's Edge Catalyst** (`apworld/mirrors_edge_catalyst/`) | **Mirror's Edge Catalyst Dashes** (`apworld/mirrors_edge_catalyst_dashes/`) |
|---|---|---|
| checks | side missions, opportunities, GridLeak bundles; optional: deliveries, hubs, grid nodes, billboards, collectibles, dashes | dashes (finish + 1/2/3 stars), GridLeak bundles up to a share of each district |
| items | abilities, 5 moves, side-mission and opportunity unlocks, Data Shards | abilities, 5 moves, 22 Dash Unlocks |
| goal | Data Shards unlock a final activity; finish it | N stars |
| needs the DLL | only for dashes and for immediate abilities | yes (dashes) |
| played in game | yes, first session 2026-10-29 (`apworld/README.md`) | yes, 2026-11-19 (soft lock, a dash finish) |

Both worlds use the same pieces underneath:

```
Archipelago server ── client (Python, one per world)
                        ├─ client/plan.py      what the game should look like (pure, unit-tested)
                        ├─ client/game.py      flag table read/write, movement volume (external memory access)
                        └─ client/dll_link.py  127.0.0.1:47910 ── mec_ap.dll (inside the game)
                                                                  ├─ challenge messages (dash finishes)
                                                                  └─ apply on the server tick (abilities now)
```

The Dashes world copies `logic.py`, `client/game.py`, `client/dll_link.py` and the data files from
the main world at build time (`tools/build_apworld.py`), so each exists once.

## What a full release still needs, in order

1. **Logic data.** The biggest missing piece, and it needs play, not code. Both
   `requirements.csv` files are nearly empty, so with randomized moves a seed can ask for
   something unreachable. Tools exist: `MEC_MoveToggles.pyw` (remove moves one by one) and
   `make_testing_save.py` (every activity selectable, XP to buy abilities). Each Dashes-world
   row needs the dash's finish and, where it differs, each star tier. OPEN_QUESTIONS #16.
2. **One-step setup for players.** Today a player builds the DLL (or gets it), runs the injector
   after every game start, and deletes the journal before each seed. Ideas, all untried:
   - a release zip with the prebuilt `mec_ap.dll` and injector, and the client telling the player
     what to run;
   - a `version.dll` proxy in the game folder so the DLL loads by itself, as MECMP does
     ([`DLL.md`](DLL.md) §3), chaining to MECMP's proxy if both are installed;
   - the client sending the seed name to the DLL, and the DLL keeping one journal per seed (no
     manual delete).
3. **A hard dash lock** (Dashes world). The soft lock works (2026-11-19) but you can still run a
   locked dash for nothing. **The game's own lock was found on 2026-11-22** ([`DLL.md`](DLL.md)
   §11e): point a dash's `UnlockFlag` at a progression flag that is 0, and after a reload the
   dash is off the map and cannot be started; set the flag to 1 and after a reload it is back.
   Tested on all 22 dashes with 22 flags of their own (`data/dash_unlock_flags.json`).
   **Built** into the Dashes client (option `hard_dash_lock`, on by default,
   `client/dash_lock.py`): it writes the 22 pointers once the world is loaded, holds each lock
   flag at 0 until the Dash Unlock arrives (the one write path), clears them in the seed save,
   and tells the player to reload a checkpoint. The soft lock stays as a fallback. Left: writing
   the pointers before the first load, so no reload is needed after starting (OPEN_QUESTIONS #23).
3b. **Locking opportunities, security hubs and side missions** (main world). Found 2026-11-22
   ([`DLL.md`](DLL.md) §11f): point an activity's `CompletedFlag` at a flag that is 1 and, after a
   checkpoint reload, the game treats it as done (off the map, cannot be started) while its real
   completion flag, the check, stays 0. This would make every on-foot activity an item-gated
   location, not only the side missions. Same build steps as 3, with one shared lock flag.
   Locking everything at once left only the 6 Dead Drop Deliveries: the game always offers one
   per phase, so they need another way (DLL.md §11f).
4. **A locked final activity** (main world). The final activity can be finished early in the
   world. With the DLL, the goal could count only a completion message that arrives after the
   unlock ([`DLL.md`](DLL.md) §1); activities other than dashes send the same messages, but only
   dashes have been captured (OPEN_QUESTIONS #22).
5. **Names for hints.** The game's `localize` gives real names from Sids ([`DLL.md`](DLL.md) §7);
   collectibles additionally need positions (OPEN_QUESTIONS #13).
6. **In-game text.** An overlay (MECMP draws Dear ImGui on the D3D11 swap chain, [`DLL.md`](DLL.md)
   §8) for "item received", "this dash is locked", stars and shards.
7. **Speed and robustness of applies.** Cache flag entities instead of scanning per batch
   (OPEN_QUESTIONS #2); test Focus-type abilities and take-backs (OPEN_QUESTIONS #12).

## Idea bucket

None of these is built. Each says what is already known that makes it plausible.

**Items**
- **Random Dash Unlock** (Dashes world filler): unlocks one dash you do not hold, chosen by the
  client when it arrives. Logic cannot plan on it, so it is a bonus on top of the 22 real ones.
- **Progressive Dash Unlock**: one item that unlocks dashes in a fixed order, replacing the 22.
- **Star items**: filler that counts toward the star goal, for players who cannot 3-star.
- **"Dashes" as one feature item**: the dash *type* has an unlocked property, apparently
  per-type, not per-dash ([`DLL.md`](DLL.md) §11d). Writing it was never tried; at best it switches
  every dash on or off.
- **`Global_CityUnlockState` as a progressive map item** (OPEN_QUESTIONS #11b). Untested.
- **Traps through the movement volume**: "lose wallrun for 30 seconds" is one byte on the volume
  the client already drives, with no save change. Proven mechanism, idea-only as a trap.
- **XP as filler**: untested whether granting XP is safe (OPEN_QUESTIONS #11).
- **Finer MAG Rope**: the three rope-use flags still exist and work (ITEMS.md), if one switch
  turns out too coarse.

**Checks**
- **GridLeak sub-areas** ("10 of the 15 in the Underground"): needs leak positions
  (OPEN_QUESTIONS #13). Districts work today.
- **Dashes without the DLL**: the best time per dash is in the save's stats block as text
  ([`DLL.md`](DLL.md) §11d). A first finish on a reset record would be visible by polling. Untested:
  whether memory updates at the end of the run, and whether online stats undo a reset.
- **Countdown deliveries, MetaGrid, assaults** as DLL events (OPEN_QUESTIONS #22).
- **Billboards** are already flag-detected; their hack time is in the stats block too.

**Multiworld features**
- **DeathLink**: needs a reliable "Faith died" signal. Not researched.
- **Combining the worlds**: the main world already has `dashes` as an option; the Dashes world is
  separate so it stays small and has its own goal. Merging them later means one item list with
  both Dash Unlocks and activity unlocks, and a goal choice.

## How to test a change in game

1. **Save:** game closed. Back up `Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`, then
   `python tools/save/make_seed_save.py PROF_SAVE --out PROF_SAVE_seed` and put that in place.
   `tools/save/read_save.py PROF_SAVE --grep Unlocks_` shows what it holds.
2. **Build:** `python tools/build_apworld.py` (main) or `--world dashes`, copy the `.apworld` into
   Archipelago's `custom_worlds`. The DLL: `dll/README.md` (CMake, Visual Studio 2022 Build Tools).
3. **Seed:** a yaml in its own folder, then
   `ArchipelagoGenerate.exe --player_files_path <folder>` and
   `ArchipelagoServer.exe --host 127.0.0.1 output/<seed>.zip`.
4. **Game:** start it, load in, run `mec_ap_inject.exe` (from a terminal, so its output stays).
   Clear the DLL journal before a new seed (`dll/README.md`).
5. **Client:** from the Launcher, connect to `127.0.0.1:38281`. `/mec` shows what the client
   believes; `mec_ap.log` next to the DLL shows what the DLL did.
6. **Unit tests:** stage a world into an Archipelago checkout
   (`tools/build_apworld.py --stage-only <ap>/worlds`) and run
   `python -m pytest worlds/mirrors_edge_catalyst/test` (and `_dashes`). Last run: main 90, Dashes
   37, Archipelago's `test/general` 322, all passing.

## Rules this project learned the hard way

- **Never call game code from a foreign thread.** Cheat Engine's calls crashed the game twice;
  the DLL calls `apply` on the server tick.
- **Never apply to every matching entity.** Flags with many entities are world objects; calling
  those crashed the game (MEMORY.md §3).
- **Re-validate before every write or call.** Entities and volumes are replaced at deaths, loads
  and streaming.
- **Report state, not intent.** Read the value back. Three bugs in this project were a write path
  reporting success the game did not show (FINDINGS §79, §84d, §86), and a fourth was the DLL
  matching entities by the wrong field (fixed in 0.2.1).
- **One code path writes progression flags** (`client/game.py:ProgressionWriter`). They reach the
  save through the autosave.
- **Location and item ids never move** once published; new things get new ids.
- **Say how you know.** Every result in these docs names its test and date, or says "untested".
