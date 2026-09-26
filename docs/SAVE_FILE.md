# Save file (offline editing)

The live interface in `MEMORY.md` is the main path. Use save editing to build a
**starting save** for a seed, or as a fallback that needs the game closed.

## Where it is

`Documents\Mirrors Edge Catalyst\settings\PROF_SAVE`. The same folder also has
`PROF_SAVE_backup`, `PROF_SAVE_profile` and `PROF_SAVE_backup_profile`. Every successful edit
so far touched only `PROF_SAVE`.

## Rules

- **The game must be fully closed** while you edit. A running game overwrites the file
  with its own in-memory state.
- **Keep a backup** of the untouched file.
- Setting Steam to offline mode was used as a precaution against cloud sync. Cloud sync was never
  actually seen interfering.
- After editing, launch the game. The edit loads normally.

## Format (summary)

```
0   "FBCHUNKS" magic, version, sizes, 2 CRC32 fields (see tools/save/save_checksum.py)
30  a sequence of blocks: u32 count, then count x { u32 type, u32 keylen, key\0, u32 vallen, value }
```

The blocks with key `ProgressionManagerData`, `ProgressionManagerData_<id>`, … (one per
linked platform account) hold the progression state:

```
144 bytes   player transform/session data
u32         N
N x { u32 hash, u32 value }      hash = djb2a(flag name), same as the live table
```

- **A flag with no record reads as 0.** A fresh save has no `Unlocks_*` records at all.
  `set_flag.py` inserts records when needed and keeps the file size constant by trimming the
  zero padding at the end.
- The sections can differ from each other, and which one the game loads varies. The tools
  edit all of them the same way.
- Both CRC32 fields are recomputed by every write tool (standard CRC-32 seeded with `0x12345678`).
  The game has not been seen rejecting a stale checksum, but the tools keep it correct.

## Tools (`tools/save/`)

```
python make_seed_save.py PROF_SAVE --out PROF_SAVE_seed    # build a starting save
python read_save.py PROF_SAVE --grep Unlocks_
python read_save.py PROF_SAVE --name "SilverCompleted_Drone Works"
python set_flag.py PROF_SAVE --set "SilverCompleted_Drone Works=1" --out PROF_SAVE.new
python clear_all_unlocks.py PROF_SAVE --out PROF_SAVE.new
```

`read_save.py` resolves names through `data/flag_names.json`.

## Building a starting save

`make_seed_save.py` takes a **story-complete** save and clears everything a
randomizer hands out or checks off. It only changes values of records that already
exist, so the file size never changes, and it recomputes both checksums.

| cleared | kept |
|---|---|
| every `Unlocks_*` ability | `GoldCompleted_*` and those missions' own times/timers |
| MAG Rope uses (`--keep-magrope` to skip) | every other `CriticalPathProgression_*` (district unlocks, story state) |
| `XP_Gained` / `XP_Used` (`--keep-xp` to skip) | anything not listed as a location or completion |
| every location flag, plus the mission-collectible and codex counters (`--default-locations-only`, `--keep-codex` to narrow) | `Collectables_Total*` capacities |
| every `SilverCompleted_` / `BronzeCompleted_` / `MiscCompleted_` and its `_CompletedTime` / timestamps | |

Example run on a story-complete community save: **593 values cleared**, story intact
(37 `GoldCompleted_` and their times), 0 abilities, 0 XP, no rope, every collectible and
activity reset. Verified in-game: all menus and counters read empty, the city is open.

Two things stay by design: **Grid Node Anchor** is a story mission, so it remains in the
Side Missions list, and the Runs tab is empty while the runs still exist in the world.

Traversal from this seed was checked in-game: you can leave the starting area **without
the MAG Rope**, and fast travel reaches **every hideout**. So the rope is safe to
randomize, and world logic doesn't need to model district routing.

Note what a story-complete seed means for design: the whole city is open, so
**abilities are the only real gate**. Side-mission and opportunity unlock items
control the replay menu, not whether the activity exists in the world.

## Earlier tested pieces

- `clear_all_unlocks.py` sets every owned `Unlocks_*` flag to 0. Tested: the save loads and
  plays through real missions, and no ability is re-granted from mission state.
- `SilverCompleted_<mission> = 1` puts a side mission in the replay menu. With a save edit,
  the mission loaded and played correctly, and a real completion overwrote the values.
- Story missions form a strict linear chain. Skipping ahead in the main story is not
  supported. The intended design starts from a save with the story already finished.
