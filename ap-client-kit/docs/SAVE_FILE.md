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
python read_save.py PROF_SAVE --grep Unlocks_
python read_save.py PROF_SAVE --name "SilverCompleted_Drone Works"
python set_flag.py PROF_SAVE --set "SilverCompleted_Drone Works=1" --out PROF_SAVE.new
python clear_all_unlocks.py PROF_SAVE --out PROF_SAVE.new
```

`read_save.py` resolves names through `data/flag_names.json`.

## Building a starting save (tested pieces)

- `clear_all_unlocks.py` sets every owned `Unlocks_*` flag to 0. Tested: the save loads and
  plays through real missions, and no ability is re-granted from mission state.
- `SilverCompleted_<mission> = 1` puts a side mission in the replay menu. With a save edit,
  the mission loaded and played correctly, and a real completion overwrote the values.
- Story missions form a strict linear chain. Skipping ahead in the main story is not
  supported. The intended design starts from a save with the story already finished.
