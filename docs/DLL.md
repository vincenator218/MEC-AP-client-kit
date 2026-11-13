# An injected DLL: what it would add and everything needed to start one

This is the research package. **A first implementation exists since 2026-11-12: `dll/`**, dashes
only (finish + 1/2/3-star checks). It is written but not yet compiled or run; see
`dll/README.md`. The `apply` queue, `localize`, an overlay and dash locking are not part of it.

**Almost every address on this page comes from another project's source.** The source is MECMP,
a multiplayer mod for Catalyst: `github.com/CodeNameMeteor/mecmp`, MIT, version 0.9.0, commit
`7195f45` (2026-10-28). Its author is also credited for the `SDK/` RTTI dump this research used.

**Same build: checked 2026-11-12** (§12 step 1). `verify_dll_addresses.py` ran against the game,
loaded into the city, with mecmp not loaded. **All 24 strong checks passed**:
- the 13 vtable and creator slots hold the expected functions, including both hook points;
- the 7 function prologues mecmp checks match byte for byte;
- the 3 TypeInfo objects are where mecmp expects them, plus our own `EXCL_TYPEINFO` as a control.

The image size, `0x727B000`, is exactly the one mecmp hard-codes. The TypeInfo list had 9988
entries. The copy tested is the **Steam** release; mecmp's docs name the EA app build, and both match.

mecmp's own check agrees (§12 step 2). Its release `0.9.0-beta.3.1` logged on 2026-11-02 on this
PC: `startup: game build recognised (9988 types)`, `build check: 15 functions and vtable slots
match`, `hooks: all installed`, and `runs: listening for finished runs` on both the server and
the client message manager. So the listener registration ran without crashing.

**What that does not prove:**
- `MessageManager_registerListener`, `localize` and the globals only got a weak check (inside the
  image, readable). Their first bytes are recorded in the JSON for next time. They are very likely
  right on a matching build, but a likely address is not a tested call.
- **This project has not called or hooked anything.** Steps 3 to 8 are still open.

Every address is also in [`data/dll_addresses.json`](../data/dll_addresses.json), with the mecmp
file and line it was read from. `tools/client/verify_dll_addresses.py` checks that file against the
running game, read-only. Addresses are image VAs at base `0x140000000`; this kit's other docs use
offsets from the base (`rva = va - 0x140000000`).

The history is in FINDINGS §88 (`ME-AP/FINDINGS.md`).

## 1. Why a DLL

The external client (`apworld/mirrors_edge_catalyst/client/`, ctypes) works today. It can only
read and write memory. A hook and a message listener need code running **inside** the process.

| capability | external client (today) | injected DLL |
|---|---|---|
| location checks from flags | polling, works | the same, or events |
| the 5 traversal items (exclusion volumes) | works | the same |
| ability items | the flag write applies at the next death | **immediately**: `apply` on the game thread (MEMORY.md §3) |
| **dashes** as checks | impossible: no progression flag (FINDINGS §88a) | the "challenge finished" message |
| deliveries, grid nodes, billboards, MetaGrid | flag polling | also the message, with the time |
| final activity really locked | no: it can be finished in free roam before the unlock (`apworld/README.md`) | yes: count only a "finished" message that arrives after the unlock |
| real display names for hints | none | the game's own `localize` |
| in-game text (connection state, items received) | none | an overlay (§8) |

## 2. Architecture

**A. The Python client stays the Archipelago side, and the DLL is a thin game-side agent
(recommended).**
- The Python client keeps the slot, the plan, the logic, the tests and the Launcher integration.
  None of that is rewritten.
- The DLL does only what needs to be in-process: the tick hook, the `apply` queue, the event
  listener, `localize` and the overlay.
- The two talk over a local channel: a named pipe, or a localhost TCP socket that Python's
  `asyncio` supports directly.

**B. A full Archipelago client inside the DLL**, with one of the libraries in §9. Most C++ games
in Archipelago work this way, and the client lives in the game. Every piece of
`client/plan.py` and `client/client.py` would be ported to C++ and tested again.

The channel for A, sketched (JSON lines; nothing is fixed yet):

| direction | message | meaning |
|---|---|---|
| client to DLL | `grant {flag, value, reason}` | queue an `apply` for an ability whose flag the client has already written |
| DLL to client | `apply_result {flag, ok, last_applied}` | read back from the entity's `[e+0x78]`: report state, not intent |
| DLL to client | `challenge_finished {content_id, kind, stat_code, sid, name, ms, new_record}` | a check, or the goal |
| DLL to client | `challenge_started` / `challenge_cancelled` | optional, for the overlay |
| client to DLL | `overlay_text {lines}` | what to draw |
| both | `hello {protocol, build_ok}` | the DLL reports whether its build check (§4) passed |

The flag write itself can stay in the Python `ProgressionWriter`, its one deliberate code path.
The DLL only adds the `apply` call.

## 3. Loading the DLL

mecmp offers two routes (`tools/inject/mecmp_inject.cpp`, `tools/proxy/version_proxy.cpp`):

- **Injector.** It opens the game and calls `LoadLibraryW` on a remote thread
  (`VirtualAllocEx` + `CreateRemoteThread`). It can be started before the game: starting the game
  runs `MirrorsEdgeCatalyst.exe` twice, first the EA activation process and then the game under
  the same name. The injector waits until a `MirrorsEdgeCatalyst.exe` has
  `Engine.BuildInfo_Win64_retail.dll` loaded and a visible window, then waits 3 s more. If the
  game runs elevated, the injector must be too.
- **`version.dll` proxy**, placed in the game folder. It forwards every export to the real
  System32 `version.dll` and loads the mod from a thread, never from `DllMain` (loader lock). If
  another mod also ships a `version.dll`, it chains to it renamed as `version_next.dll`.

The DLL pins itself (it is never unloaded mid-game) and does nothing until the engine is up. mecmp
waits for the TypeInfo list (`0x14215D028`, next pointer at `+0x08`) to reach at least 9000
entries and stay stable, then runs its build check.

The existing Mirror's Edge Archipelago implementation also ships a DLL injected at launch
(AP_IMPLEMENTATION_PROMPT), so this is not an unusual thing to ask of players.

## 4. Build check before anything

mecmp writes nothing until all of these match. On any mismatch it stays inactive
(`src/app/mod.cpp`, `src/game/fingerprint.cpp`):

1. three TypeInfo objects are at the expected addresses, found by name in the TypeInfo list:
   `PamReplayPlayerComponentData`, `ServerCharacterEntity`, `ObjectBlueprint`;
2. eight vtable slots hold the expected functions, compared after rebasing;
3. seven functions start with the expected bytes. Only position-independent bytes are compared,
   so relocation does not matter.

All of them are in `dll_addresses.json` and the verify script checks them. A DLL for this project
should do the same and also include this kit's own verified addresses: `FLAG_TABLE`,
`ENTITY_VTABLE`, `APPLY` and `EXCL_TYPEINFO`.

## 5. The per-frame hook, and the apply queue

mecmp hooks by **swapping one pointer in a vtable or creator table**. No game code is patched, and
no detour library is used (`src/game/hooks.cpp`, `src/core/mem.h`):

1. Read the slot. **Refuse unless it holds the expected original.** For the tick hook mecmp
   compares exactly. For creator slots it accepts any executable pointer, so it can chain behind
   another mod's hook.
2. Store the original first, so a call that arrives mid-swap still reaches it.
3. `VirtualProtect` the slot RW, make one aligned 8-byte store (atomic on x64, so a concurrent
   call sees either the old or the new pointer), restore the protection, `FlushInstructionCache`.
4. Call the original from the hook.
5. Record every swap. If a later install fails, undo them all, newest first.

| hook | slot | expected original | thread |
|---|---|---|---|
| `ServerGameWorld` vtable `+0x28`, postUpdate (the tick) | `0x141B42D28` | `0x143341EE0` | server game thread |
| client replay updater `updateAll` (vtable `0x141C49190` `+0x10`) | `0x141C491A0` | `0x14394DA40` | client thread |

mecmp calls the original postUpdate first, then acts only when `world` equals
`*0x1425469E0` (`ServerGameWorld*`, null between levels). `dt` is a float at `updateInfo + 0x10`.

**The apply queue.** The Python client writes the flag as it does now. The DLL drains queued
`apply` calls inside the tick hook, following MEMORY.md §3 and §4:
- find the entity whose vtable is `ENTITY_VTABLE` and whose `[e+0x80]` is `node + 0x10`;
- prefer the `0x2000` (per-spawn) instance;
- never broadcast;
- re-validate the vtable, `[e+0x80]` and the `0x2000` bit right before the call;
- call with `force = 0`;
- confirm `[e+0x78]` changed before reporting success.

**Open:** which thread owns the flag-check entities. The tick hook runs on the *server* game
thread. If those entities belong to the client world, `apply` belongs in the client hook instead.
Settle this before the first call, not by trial.

**Two mods on one slot.** mecmp's tick hook refuses a slot that does not hold the original. Ours
should too. So mecmp and an AP DLL that both hook postUpdate cannot run together: whichever loads
second backs off. Either pick another tick point or document "not with mecmp". Run the verify
script **without** mecmp loaded: its hooks would show up as mismatches.

## 6. Event-driven checks: the challenge messages

Dashes have no progression flag. Their records live in the game's stats system, and completion is
a **message** (FINDINGS §88a-b). mecmp subscribes to it (`src/game/runs.cpp`).

**Subscribing.** `MessageManager_registerListener` at `0x142A3AD40`, called as
`(manager, category, listener, 0xff)`.
- The managers are `*0x142401CB0 + 0x10` (client) and `*0x14253D670 + 0x10` (server).
- mecmp registers on both, each once its context exists: the client one from the client
  `updateAll` hook, the server one every 30 ticks from the tick hook until it succeeds.
- A listener is any object whose vtable has two slots: `onMessage(self, message)` and
  `priority(self)`. mecmp's priority returns 0.
- Message header: `+0x08` category, `+0x0C` type. Type ids are the djb2-xor hash of the message
  class name.

Category `0x54776FC6` (`PamSocialPlay*Message`):

| type | message | fields |
|---|---|---|
| `0xC164590C` | NamedChallengeStarted | `+0x48` u32 ContentId |
| `0xD71D027F` | **NamedChallengeFinished** | `+0x48` u32 ContentId, `+0x4C` u32 stat set, `+0x50` i32 difference, `+0x54` u8 had a record, `+0x58` i64 record, `+0x60` u8 new record |
| `0x9A9A27C6` | NamedChallengeCancelled | left or failed the run. `+0x48` u32 ContentId (seen in game 2026-11-12, 3 of 3 dumps) |
| `0xB7633230` | NamedChallengeActivated | the dash's start is selected, before the countdown. `+0x48` u32 ContentId (seen in game 2026-11-12, 2 of the 4 dumps; the other 2 had other bytes there). **Started comes only once the timer runs**: backing out at the countdown sends Activated, then Cancelled, and no Started |
| `0x9B35497C` | ChallengeFinished (a **player-made** time trial) | `+0x48` 24-byte trial id, `+0x60` u32 time in hundredths |
| `0x1CCA484E` / `0x72F865F9` | StartChallenge / RestartChallenge (time trials) | `+0x48` trial id |

**Reading a finish** (mecmp's notes, seen in game):
- One run sends **one Finished message per stat set**. Set 0, the player's own best, is the one
  shown.
- The same finish can also arrive through both managers. mecmp drops a repeat with the same
  ContentId and value within 5 s.
- Times are in hundredths of a second: `run = record` if this is a new record or there was no
  record; otherwise `run = record + difference`. In the example, 2386 + 1177 = a 35.63 s run.
- Billboards and assaults also send Finished, but their value is a timestamp or a score, not a
  run time. mecmp skips every stat code without `_time`.

**What a ContentId is.** mecmp hooks the `PamServerNamedChallengeEntity` creator
(slot `0x141C7EE00`, expected `0x143A834B0`) and keeps the live entities, checked by vtable
`0x141C7EC70`. Entity `+0x80` points to `PamNamedChallengeData`:
- `+0x10` Sid (a localisation id; `char*`);
- `+0x58` main stat code (`char*`);
- `+0x98` u32 ContentId.

The stat-code prefix names the kind. Four of them are existing check categories:

| prefix | kind |
|---|---|
| `ch_rrt_` | Dash (Runner's Route), e.g. `ch_rrt_tv2_time` |
| `ch_dlvry_` | Delivery |
| `ch_gnd_` | Grid Node |
| `ch_hbb_` | Billboard hack |
| `ch_mgd_` | MetaGrid |
| `ch_aslt_` | Assault |

Player-made time trials:
- the marker is `PamServerChallengeMarkerEntity` (vtable `0x141C7E3E8`, creator slot `0x141C7E9F0`);
- `+0x80` is the 24-byte content id and `+0xB8` the author's trial name;
- its data (`+0x28`) has `+0x68` CheckpointOrder and `+0x6C` Time;
- a "ReachThis" / Beat L.E. marker has no checkpoints and is not timed.

These are user-generated content, so they are almost certainly not Archipelago locations.

All 35 `PamSocialPlay*Message` type ids, for a research log (from mecmp's `kMessageNames`):

```
a390e6be RunnerKitOpened            85ebbf13 EchoCustomizationChanged   9a0dfb2b RemoveSharedContent
aa327a65 InventoryChanged           d71d027f NamedChallengeFinished     855bb873 OnShowMap
5b61f030 OnHideMap                  fc61a69a PinSharedContent           a3118cf7 PermissionRequest
5a464701 UnpinSharedContent         36154959 FireEvent                  f1c3cee5 PermissionResponse
33d42557 SocialTeleport             e7d40012 BlockedListUpdated         606b598c NamedChallengeTeleport
fc74c3ca Control                    052d5907 BlockedUsers               a64f89ee NamedChallengeStatsUploaded
a78a38f4 NamedChallengeBookmarkStatusRequest                            1846085d UgcFilterOptionChanged
9b35497c ChallengeFinished          e6fd16cc NamedChallengeBookmarkStatusResult
68f236ee FriendsList                924d6bd9 DownloadSharedContent      1cca484e StartChallenge
b7633230 NamedChallengeActivated    72f865f9 RestartChallenge           57d92a5d RequestHackableBillboardLeader
320071b1 MapMarkerUpdates           82ad8c5d RefreshHackableBillboardLeaderCache
c164590c NamedChallengeStarted      f33d51ff HackableBillboardsLeader   9a9a27c6 NamedChallengeCancelled
d089d3e2 FetchSharedContents        955f5cbd NamedChallengeUploadReplay
```

## 7. Display names: `localize`

At `0x1436A8D40`: `bool localize(char* out, uint32_t capacity, const char* sid, void* args)`.
- mecmp passes a pointer to a null pointer as `args` and a 512-byte buffer.
- It treats the result as good only if the call returned true, the text is printable, and the
  text differs from the Sid.
- Otherwise it falls back to the Sid with `ID_NC_`, `ID_BILLBOARD_` or `ID_` cut off.

This would give real names for every check and for hints (OPEN_QUESTIONS #9, #13). **Grade it
first** against a Sid whose answer is already known: §78 decoded the 32 opportunity names by
hand, so one `ID_OPP_*_LABEL` Sid has a known right answer.

## 8. Overlay

mecmp draws Dear ImGui 1.91.9 (MIT, vendored in `third_party/imgui`) on the game's own D3D11 swap
chain (`src/ui/overlay.cpp`):
- It creates a throwaway device and swap chain on a hidden window only to find DXGI's
  swap-chain vtable.
- It swaps `Present` (index 8) and `ResizeBuffers` (index 13) there.
- It subclasses the game window's `WNDPROC` for input.
- It opens on a key (`INSERT` by default, configurable) or with both sticks on a gamepad.
  While it is open, the game does not see the gamepad.
- Menus pause the simulation. mecmp watches the `PamUISystem` update (slot `0x141CB64F0`,
  expected `0x143B16C50`; the pause controller is at `UISystem + 0x8C8`, counts at `+0x08`/`+0x0C`)
  to know when a game menu is open.

For Archipelago: connection state, items received, checks sent, and "N / M Data Shards". Text
alone can be much smaller than mecmp's menu.

## 9. C++ Archipelago client libraries

Only needed for architecture B, but worth knowing. Both READMEs were read on 2026-11-12.

| | **apclientpp** (`github.com/black-sliver/apclientpp`) | **APCpp** (`github.com/N00byKing/APCpp`) |
|---|---|---|
| license | MIT | **LGPL-2.1**: a closed or static link has obligations; a separate DLL is the easy way to comply |
| shape | header-only `apclient.hpp`; you call `poll()` once per frame and set `set_*_handler` callbacks | a compiled library with a flat API: `AP_Init(ip, game, slot, password)`, `AP_SetItemRecvCallback`, `AP_SetLocationCheckedCallback`, `AP_Start()`, `AP_SendItem(location_id)` (it sends a check), `AP_StoryComplete()`, plus messages, DeathLink, data storage and gifting |
| dependencies | nlohmann/json, valijson (optional: `AP_NO_SCHEMA`), wswrap, websocketpp and asio for desktop; OpenSSL and `crypt32` for `wss://` (or `WSWRAP_NO_SSL`) | IXWebSocket, jsoncpp and zlib as git submodules, plus a bundled mbedtls (clone recursively) |
| Windows build | MSVC v14.1+ or gcc6+, C++14; README has a Visual Studio section (`/Zc:__cplusplus`, `_WIN32_WINNT=0x0600`, `WIN32_LEAN_AND_MEAN`) | `cmake .. -DWIN32=1` (add `-DMINGW=1` on MinGW) |
| used by | its README lists The Witness randomizer (VS2019) and the Dark Souls III client (VS2022), among others | — |
| also | shares the Archipelago data-package cache in `%LocalAppData%\Archipelago\Cache` | `AP_Init(file)` plays a generated single-player game from a file |

## 10. Toolchain

The same as mecmp: CMake, C++17, x64.
- **Visual Studio 2022** (or its Build Tools): *Open Folder*, `x64-Release`.
- Or **llvm-mingw**:
  `cmake -B build -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-clang++ ...`.

The research PC has no C++ compiler installed (checked 2026-10-30).

## 11. Dashes as locations: what must be settled first

1. **The census.** Which named challenges exist, with their ContentId, Sid and stat code. None of
   it is in the exe's strings (`ME-AP/strings.txt` has no `ch_rrt_` at all); it lives in the game's
   data. The zero-code route: mecmp itself logs every finish, always on, not just in verbose mode:
   `runs: finished content %08x ('<sid>', stat '<code>'), set ...`. Run mecmp offline (its
   default), finish runs, and read `mecmp.log`. A timed run's start is logged by name too
   (`runs: started the ...`); the ContentId of a start, and every message type seen, only with
   `[debug] verbose=1`. The other route: extract `PamNamedChallengeData` from the game's EBX
   (`ME-AP/ebx_parser.py`).
2. **Is the ContentId stable** across game restarts and level reloads? A location id must map to
   it forever. Finish one dash in two sessions and compare.
3. **Does a slower replay still send Finished?** The message has a separate "new record" byte,
   which suggests yes. This decides the event-based goal (§1).
4. **Does it fire offline?** The records are online stats; the gateway backend messages are in
   the exe. mecmp never touches the online services, so its logs don't settle this.
5. **Leaderboards and anti-cheat.** `PF_L_RunnersRouteAntiCheat` is in the game data. With
   traversal moves removed and abilities changed, a dash time is not a normal run. Find out what
   gets uploaded, and whether to stay offline.
6. **Missed events.** An event that fires while the client is not running is gone. Unlike a flag,
   it cannot be re-read later. The DLL should append every finish to a journal file that the
   client sends on reconnect. Dashes can be replayed as a fallback.
7. **Location ids.** Every 1000-block from 1310000 to 1319xxx is in use. New ids for dashes
   don't touch the existing ones, but the new block is a design decision (for example 1330000).
8. **Logic.** Which moves each dash needs goes into the same crowdsourced worksheet as the other
   activities (`apworld/.../data/requirements.csv`).

### 11a. First census results (2026-11-12, mecmp 0.9.0-beta.3.1, Steam build)

One dash, **Concrete Canyon**, finished three times over two game sessions with a full quit
and relaunch between them. Read from `mecmp.log` and `mecmp.prev.log`:

| session | time | Finished sent | ContentId | Sid | stat code | record | difference | new record |
|---|---|---|---|---|---|---|---|---|
| 1 | 33.53 | yes | `353ff992` | `ID_NC_DOWNTOWNCANYON` | `ch_rrt_dt2_time` | 2663 | 690 | 0 |
| 1 | 39.60 | yes | `353ff992` | same | same | 2663 | 1297 | 0 |
| 2 (after restart) | 30.26 | yes | `353ff992` | same | same | 2663 | 363 | 0 |

What this settles:
- **The ContentId is stable across a game restart** (question 2). It is a usable key for a location.
- **A run slower than the record still sends Finished** (question 3), every time, with
  `new record` 0. So "finished after the unlock" can be detected for any finish, not only new bests.
- **The time formula holds:** record + difference, in hundredths. For example 2663 + 690 = 33.53 s,
  exactly what mecmp showed.
- **`localize` works on this build.** mecmp turned `ID_NC_DOWNTOWNCANYON` into `CONCRETE CANYON`
  through the game's own function. This was not the §12 step 6 test on a known opportunity Sid,
  but it was a real call with a real Sid and a sensible result.

What one run also showed, the message order for a dash started from the map:
`NamedChallengeTeleport`, `NamedChallengeActivated`, `NamedChallengeStarted`, then at the end
`NamedChallengeUploadReplay`, `NamedChallengeFinished`, `NamedChallengeStatsUploaded`.

### 11b. All 22 dashes, from memory (2026-11-12)

A read-only scan for `PamServerNamedChallengeEntity` instances (vtable `0x141C7EC70`, then `+0x80`
to the data: `+0x10` Sid, `+0x58` stat code, `+0x98` ContentId) found **22 dashes**. That is the
in-game count. The list is in [`data/named_challenges.json`](../data/named_challenges.json).

- The scan found Concrete Canyon as `353ff992`, the same ContentId mecmp logged, so it reads the
  same data the game sends in its messages.
- The same 22 were loaded both times, with the player in two different districts, while the
  billboards changed between scans. Dashes appear to load city-wide; billboards stream in and out
  with position.
- By stat code: Anchor 6, Downtown 6, Rezoning 4, The View 5, plus `ch_rrt_bm1` Birdman's Route.
  Birdman's Dash is probably the story dash (there is a
  `CriticalPathProgression_HasCompletedBirdmanRunnersRoute` flag). Whether it is a location is a
  design choice.
- **Display names:**
  - **All 22 are confirmed** by mecmp's in-game `localize`. The tester started each dash and quit
    a few seconds after the timer began, and mecmp logged the ContentId with its name. Every
    ContentId matched the memory scan, and every name matched the tester's in-game list of 22.
  - The one difference: the game's own text for `ID_NC_BIRDMANS_ROUTE` is "BIRDMAN'S ROUTE",
    while the dash list shows "Birdman's Dash". Both are kept in the file (`localized`, `name`).
  - Three Sids would have been misleading guesses:
    - `ID_NC_CONSTR03` is Rezoning Dash, not a "construction" one;
    - `ID_NC_ANCHOR04` is Quite a View;
    - `ID_NC_THEVIEW04` is Don't Fall Down.
    That is the same lesson as FINDINGS §87g.
- **Mapping the rest needs no full runs:** with mecmp loaded, *start* each dash and quit it.
  mecmp logs `runs: started the Dash '<name>'` with the ContentId on the line before.
- Deliveries and grid nodes never appeared in either scan. They may use another class, or exist
  only while active.

**`list.csv` is keyed by something else.** The localisation dump has `E80845C3,"CONCRETE CANYON"`,
so `ID_NC_DOWNTOWNCANYON` is now a known Sid/key pair, the first one. Tried against it, with no
match:
- 19 hash functions: djb2/djb2a with seeds 0 and 5381, FNV-1/1a in 32 and 64 bit (both halves),
  CRC32, Adler-32, sdbm, Jenkins one-at-a-time, MD5 and SHA-1 prefixes;
- the Sid in upper and lower case, with and without the `ID_` / `ID_NC_` prefix and
  `_NAME` / `_LABEL` / `_TITLE` suffixes;
- UTF-8 and UTF-16, with and without a terminator, both byte orders.

So the key is not a plain hash of the Sid, consistent with FINDINGS §9.

### 11c. How a dash could be locked (read 2026-11-12, read-only; nothing written)

The SDK dump gives `PamNamedChallengeData` an `UnlockFlag` (`+0x40`, a `PamProgressionFlag*`) and
a `GeneratedFlagNameHash` (`+0x48`). `PamNamedChallengeTypeData` has `HasUnlock` (`+0x9E`) and
`UnlockedPropertyHash` (`+0x50`). Read live on all 22 dashes and 3 billboards:

| | dashes (type `RunnersRoute`) | billboards (type `HackableBillboard`) |
|---|---|---|
| `UnlockFlag` | null on all 22 | null |
| `GeneratedFlagNameHash` | 0 on all 22: no progression flag | `HackableBillboards_tvbb0N`, a flag already in `flag_names.json` |
| type `HasUnlock` | **1** | 1 |
| type `UnlockedPropertyHash` | `0xF0494AF4` | `0xA40512B4` |
| type `RequiresOnline` | **0** | 0 |
| type `AllowTeleport` | 1 | 0 |
| `HideInMap` | 0 on all 22 | 0 |
| star thresholds `+0x18/+0x1C/+0x20`, cancel `+0x24` | set: hundredths of a second, now in `named_challenges.json` | 0 |

What it means:
- **The game has a native "unlocked" concept for dashes, but it is not a progression flag.** It
  is a named-challenge *property* (`UnlockedPropertyHash`), probably set when a dash is discovered
  in the world. Where that property's per-dash value is stored has not been found. Writing it to 0
  could lock a dash natively. This is the best lead, and it is untested.
- `RequiresOnline` is 0 for dashes. That suggests (does not prove) they work offline; §11
  question 4 is still a test to run.
- The star times allow extra checks: 1, 2 and 3 stars per dash, judged from the time in the
  Finished message. Concrete Canyon is 46.00 / 38.00 / 32.50 s.
- Billboards are flag-detectable already (`HackableBillboards_*`), with no DLL needed.

Other ways to stop a locked dash, in order of preference:
1. **The native property above**, if its store can be found.
2. **A DLL hook that refuses the start.** Swap the `PamServerNamedChallengeEntity`'s message or
   event handler slot, and drop the activation for a locked ContentId. mecmp does the same kind of
   thing to the replay-download listener (`replay_check.cpp`): it changes a message as it passes,
   so the game takes its own failure path. Which slot handles the start is unknown; it needs
   reverse engineering.
3. **Let it run, but don't count it.** On Started for a locked dash, the overlay says so, and its
   Finished is ignored. This works with only the pieces already verified.
4. `HideInMap` (`+0x9C`) might hide the map icon. It is static data shared by the level, not saved,
   and is untested.

### 11d. Looking for the "unlocked" store (2026-11-12, read-only)

**The unlock is per type, not per dash.**
- A full scan of writable memory found the dash type's `UnlockedPropertyHash` `0xF0494AF4` only
  **7 times**, not 22, and never next to a dash ContentId.
- Where the context is readable, it sits in `{u32 key, u32 property hash, u32 value}` triples next
  to the billboard type's `0xA40512B4`. For example, `24E3553F F0494AF4 1` then
  `159BE6FF A40512B4 1`, and in another copy `DAC49151 F0494AF4 3` then `50D43991 A40512B4 3`.
- The property is also on `PamNamedChallengeTypeData`, not on each dash's data.
- So the game's own lock is most likely "dashes as a feature" (unlocked by the story), with no
  per-dash lock to reuse.
- Writing it was not tried. At best it would switch *every* dash off or on: a possible
  "Dashes" item, not a per-dash one.
- None of the 6 property names tried, in 1006 spellings (`Unlocked`, `Discovered`, `Available` and
  others, with and without the type prefixes), djb2a-hashes to `0xF0494AF4`. djb2a is the hash
  the message type ids use.

**Dash records are in the save and in memory, as text.** `PROF_SAVE`'s first block holds 289
key/value stats as strings.
- **Per dash:** `ch_rrt_<code>_time_<uid>` is the best time in hundredths: `ch_rrt_dt2_time_2411670393`
  = `2663`, the record mecmp logged. The unsuffixed `ch_rrt_dt2_time` is the default `9999999`.
- The same file also has per-dash distances (total, walk, wallrun, max per frame), and
  `total_stars_<uid>` = `66` (22 × 3).
- **Billboards:** `ch_hbb_*_tstamp_<uid>` holds the hack time.
- The same serialized text is in game memory: two copies of the blob, plus the key strings.
  `<uid>` is this player's number.
- There is no `unlock` key, and the property hash does not appear as text.

What that opens up: **dash checks could be polled without a DLL.** On a seed save with each dash's
record reset to the default, the first finish writes a time, and a time under a star threshold
is a star check. Slower replays would not show, but a first finish always does. Untested:
- whether the in-memory copy updates the moment a run ends, or only at save time;
- whether the game re-downloads records from EA's stats servers when online, which would undo the
  reset;
- editing the stats block (`tools/save/` only handles the progression block today).

**Still open:**
- Deliveries, grid nodes, and the full billboard list.
- Per-dash locking: no native lock exists, so it needs a DLL hook that refuses the start (§11c
  option 2), or "runs but doesn't count".
- Whether Finished fires offline. The "upload" messages suggest the game talks to the stats
  backend at the end of every run, which is question 4 and question 5 together.
- A level reload without a restart (question 2 covers restarts only so far).

## 12. Verification order

Each step has a pass condition known in advance. Do them in order: each one is cheap, and it
protects the next.

| # | what | how | pass |
|---|---|---|---|
| 1 | the addresses suit our build | `python tools/client/verify_dll_addresses.py`, game loaded into the city, **mecmp not loaded** | every strong check passes; our own four entries pass too, as a control. **Done 2026-11-12: 24/24** |
| 2 | mecmp's view agrees | run mecmp; `mecmp.log` | "build check: N functions and vtable slots match" and "hooks: all installed". **Done 2026-11-02 log: 15 match, all installed, listener registered on both managers** |
| 3 | the census | play dashes, deliveries, grid nodes; read `mecmp.log` | a `finished content` line per run, with a `ch_*` stat code. **Dashes: done, all 22 ids and names (§11b). Deliveries, grid nodes, billboards: not yet** |
| 4 | ContentId stable | the same dash in two sessions | the same ContentId. **Done 2026-11-12: across a full game restart** |
| 5 | a slower replay fires | replay a dash, slower than the best | a Finished line with new record 0. **Done 2026-11-12: three slower runs, each sent Finished** |
| 6 | `localize` is right | call it on a known `ID_OPP_*_LABEL` | the menu text from §78 |
| 7 | which thread owns flag-check entities | read where they are created before calling anything | a definite answer |
| 8 | `apply` from the hook | one `live_entity` ability, one call, `force = 0` | `[e+0x78]` changes and the ability works with no death |

Steps 1 to 5 need no code from this project. Step 1 uses the script that ships here, and steps 2
to 5 use mecmp's release.

## 13. License and credit

- mecmp is MIT, so its code may be copied or adapted with its copyright notice kept.
- Dear ImGui is MIT.
- apclientpp is MIT.
- APCpp is LGPL-2.1.

Credit mecmp in any DLL that uses its addresses, since finding them was the hard part.
