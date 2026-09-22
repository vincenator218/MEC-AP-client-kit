# The live interface

All offsets are relative to the base of `MirrorsEdgeCatalyst.exe`, and come
from the PC build the research used. They are build-specific: always
sanity-check them first (`ap_check()` in `reference/cheatengine/ap_live.lua`
does this).

| symbol | offset | what |
|---|---|---|
| `FLAG_TABLE` | `+0x257C9D8` | pointer to the progression flag hash table |
| `ENTITY_VTABLE` | `+0x1C7B168` | vtable of the flag-check entity class |
| `APPLY` | `+0x3A75790` | `void apply(Entity* e, int value, bool force)` |

## 1. Flag names and hashes

Every progression flag has a string name, such as `Unlocks_DoubleWallrun`,
`SilverCompleted_Drone Works` or `ElectronicPartsDtTd_Chip92Taken`. Names are
case-sensitive and may contain spaces and apostrophes. The key is **djb2a** over
the UTF-8 bytes, with no terminator:

```python
def djb2a(s: str) -> int:
    h = 5381
    for b in s.encode("utf-8"):
        h = ((h * 33) ^ b) & 0xFFFFFFFF
    return h
# djb2a("Unlocks_MoveEnemyBack") == 0x67800619
```

`data/flag_names.json` lists all 2376 known names with their hashes. The same
hash is the record key in the save file.

## 2. The flag table

```
table   = *(u64*)(base + 0x257C9D8)
buckets = *(u64*)(table + 0x20)        // array of node pointers
nbuck   = *(u32*)(table + 0x28)
node    = *(u64*)(buckets + (hash % nbuck) * 8)
while node:
    if *(u32*)(node + 0x00) == hash: found
    node = *(u64*)(node + 0x28)        // chain
```

| node offset | field |
|---|---|
| `+0x00` | u32 hash |
| `+0x10` | pointer that flag-check entities cache as their flag identity (see §3) |
| `+0x18` | **i32 value** (0/1 for booleans; counts and times for others) |
| `+0x28` | next node in the bucket chain |

- Every known flag already has a node, with value 0 if never set (about 2374 nodes).
  You never need to insert one.
- **Reading:** poll `node+0x18`. This is how locations are detected (see `LOCATIONS.md`).
  Cache the node addresses after the first lookup. Re-look them up if the node's hash field
  no longer matches.
- **Writing:** write `node+0x18`. The game's own autosave persists it. That was verified
  in both directions: 0→1 and 1→0 both survived a relaunch.
- A write alone changes the save, and anything that reads the flag later
  (menus built at load, respawn re-evaluation). For abilities it does **not**
  change the player immediately. That's what §3 is for.

## 3. Applying an ability now

Abilities are enforced by **flag-check entities**. They read the flag when they
are (re)evaluated, which happens at load and on every respawn. To apply a change
immediately, call the entity's own apply routine yourself.

```
apply(e, value, force=0)        // x64: rcx = e, edx = value, r8b = 0
```

What `APPLY` does (from disassembly):
1. It returns unless bit 3 (`0x8`) of `[e+0x18]` is set (the entity is enabled).
2. It compares `value` to `[e+0x78]` (the last applied value) and stores it. If the
   value is unchanged and `force == 0`, it returns (no-op). The game's own respawn path
   passes `force = 1`.
3. It pushes `value` to the entity's int output port (`e+0x68`) and `value > 0` to its bool port (`e+0x70`).
4. If `force == 0` and the entity's mode is 2 (`data->vtable[0x20]() == 2`), it fires the change event.
   Some abilities only react to the event (Switch Place), others to the ports (stamina).
   **Always pass `force = 0`.** (`force = 1` skips the event, so event-driven abilities don't switch until the next respawn.)

### Entity layout (class `ENTITY_VTABLE`)

| offset | field |
|---|---|
| `+0x00` | vtable = `base + 0x1C7B168` |
| `+0x18` | flags: `0x8` = enabled; `0x2000` = per-spawn ("live") instance. Seen as `0x321F` (live) and `0x121F` (persistent) |
| `+0x28` | `data`: the static per-ability definition |
| `+0x68` / `+0x70` | int / bool output ports |
| `+0x78` | last applied value |
| `+0x80` | cached flag identity = `node + 0x10` of the flag it checks |

### Finding the right entity

Scan writable memory for objects whose first qword is `base + 0x1C7B168` and
whose `[e+0x80] == node+0x10`. There are about 1100 such entities in total, and only a
few match any one flag. Then:

1. **If one has `[e+0x18] & 0x2000`** (the per-spawn instance), call `apply` on it.
   About 27 abilities have one. Tested on Switch Place, a stamina tier, Double Wallrun and
   MAG Rope Swing.
   - This entity is **replaced on every death and checkpoint restart**. It survives
     mission start and fast travel. It exists right after a normal load (no death needed).
   - So **re-scan (or re-validate) before every grant.**
2. **Otherwise, if the flag has only a few entities (≤ 3)**, call `apply` on the
   persistent ones whose `data` pointer is unique for that flag. Tested on
   `Unlocks_Focus` (2 entities).
3. **Otherwise, don't call anything.** Flags with many entities, such as
   `Unlocks_Disruptor_Overload` (10–24 seen, most sharing one `data` pointer), are also
   checked by **world objects** that stream in and out as you move. Calling `apply` on
   those crashed the game. The table write alone still applies at the next respawn.

### Timing summary

| method | when the player gets it |
|---|---|
| write + apply on the live entity | immediately |
| write + apply on a unique persistent entity | immediately (Focus) |
| write only | at the next death or checkpoint restart |
| `SilverCompleted_<mission>` write | in the Side Missions menu at the next load (checkpoint restart) |

Only the stamina bar updated live in testing. Other HUD elements, such as the Focus bar,
may appear only after a respawn even when the ability is active. The skill-tree
menu does not refresh from any of this (cosmetic).

## 4. Safety rules (learned the hard way)

- **Threading.** The prototype calls `apply` through Cheat Engine's `executeCodeEx`,
  which runs it on a new thread. That crashed the game twice over several dozen calls. A real
  client must make the call **on the game's thread**, for example by hooking a per-frame
  function and draining a queue of pending grants there. No hook point has been chosen yet.
- **Never broadcast `apply` to every matching entity** (see §3 rule 3).
- **The autosave can happen at any time**, not only at checkpoints. Any test value
  in the table can end up in the save. For a client that's the point. For testing, keep
  test windows short and re-check the save after each session.
- **Re-validate an entity before calling it**: check that the vtable, `[e+0x80]` and the `0x2000` bit still match.
- Writes are idempotent. On connect or reload, a client can simply re-apply every received item.
