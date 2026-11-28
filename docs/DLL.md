# The injected DLL: research and design

The research behind `mec_ap.dll`, kept so the next steps (the hard dash lock, §11e; `localize`, an
overlay, auto-loading) can start from it. **An implementation exists: `dll/`** (see
`dll/README.md`).
- Dashes (finish + 1/2/3-star checks): built and tested end to end on 2026-11-12.
- The `apply` queue (§5): working in game since 2026-11-13. Coil and FastClimb, received from a
  dash, were applied on their live entities from the server tick and read back as 1. **Coil worked
  in play right away, with no death or reload** (FastClimb: the tester was "pretty certain" it also worked without a reload).
- `localize`, an overlay and dash locking are not part of it.

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

**Since then this project has hooked and called things itself** (`mec_ap.dll`, 2026-11-12/13):
both hooks, `MessageManager_registerListener` and `apply` all ran on this build. `localize` has
only been called by MECMP, not by this project (§12 step 6 is still open).

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

Built in `mec_ap.dll` so far: the **ability** and **dashes** rows. Not built: events for other
activities, the final-activity lock, `localize`, the overlay (`docs/ROADMAP.md`).

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

**A is what was built.** The channel as implemented (protocol 1, JSON lines on
127.0.0.1:47910; the exact format is in `dll/src/link.h`):

| direction | message | meaning |
|---|---|---|
| DLL to client | `hello {proto, dll, build_ok, why, apply, apply_why, acked, last}` | the DLL's checks (§4) and whether it can apply |
| DLL to client | `finished {seq, content_id, run_cs, record_cs, ...}` | a finished run, journaled to disk first, re-sent until acknowledged |
| client to DLL | `ack {seq}` | the client has dealt with that finish |
| DLL to client | `started` / `cancelled {content_id}` | live only, for the log |
| client to DLL | `apply {id, hash, value}` | apply a flag the client has already written |
| DLL to client | `applied {id, hash, value, result, matched, targets, live}` | what the game shows afterwards (`[e+0x78]` read back) |

The flag write stays in the Python `ProgressionWriter`, its one deliberate code path; the DLL
only adds the `apply` call. Not built: an `overlay_text` message (§8).

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

All of them are in `dll_addresses.json` and the verify script checks them. `mec_ap.dll` does the
same before anything else (`dll/src/build_check.cpp`): 3 TypeInfo names, the 2 hook slots and
`registerListener`'s first bytes. Its ability path has a check of its own (`apply.cpp`): the flag
entity's class name through its vtable, and `apply`'s first 24 bytes. On a mismatch it changes
nothing and tells the client why.

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

**Which thread: the server's (settled 2026-11-13, read-only).** Slot 0 of `ENTITY_VTABLE` is
`getType`, `lea rax,[0x1428641A0]; ret`, and that TypeInfo's name is
**`PamServerProgressionFlagEntity`**. The sender that triggers it at respawn (vtable `+0x1C3FCB0`,
FINDINGS §60) reads as **`PamServerCharacterEntity`**. Both are server entities, so `apply` runs in
the server tick hook. `dll/src/apply.cpp` implements this queue: the link thread scans for
candidates; the tick re-reads the flag table, re-validates each entity and calls; the result
reports `[e+0x78]` as read back. The `apply` function's first 24 bytes, read the same night, match
FINDINGS §63's disassembly and are part of the DLL's build check.

**Two mods on one slot.** mecmp's tick hook refuses a slot that does not hold the original.
`mec_ap.dll` instead chains in front of whatever executable code is there, so loading mecmp first
and then `mec_ap.dll` works for both (seen once, 2026-11-12). The other order turns mecmp's tick
hook off. Run the verify
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

`mec_ap.dll` is built with Visual Studio 2022 Build Tools (MSVC 19.44), CMake and NMake
(`dll/README.md`).

## 11. Dashes as locations: what had to be settled

Answers, as of 2026-11-19: 1 done (§11b), 2 done (§11a), 3 done (§11a), 4 **open**, 5 open (the
DLL never uploads anything itself; what the game uploads was not studied), 6 done (the DLL's
journal), 7 done (1330000 + 10 * `ap_index` + tier), 8 started (`requirements.csv` in each world).


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
  Birdman's Route is probably the story dash (there is a
  `CriticalPathProgression_HasCompletedBirdmanRunnersRoute` flag). Whether it is a location is a
  design choice.
- **Display names:**
  - **All 22 are confirmed** by mecmp's in-game `localize`. The tester started each dash and quit
    a few seconds after the timer began, and mecmp logged the ContentId with its name. Every
    ContentId matched the memory scan, and every name matched the tester's in-game list of 22.
  - The one difference: the game's own text for `ID_NC_BIRDMANS_ROUTE` is "BIRDMAN'S ROUTE",
    while the tester's list said "Birdman's Dash". The map shows "BIRDMAN'S ROUTE" too (player
    screenshot, 2026-11-25), so the AP name is Birdman's Route since 2026-11-27. Its location and
    item ids did not change.
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

Other ways to stop a locked dash, as listed on 2026-11-12. **Superseded by §11e**: the
`UnlockFlag` field above works as a per-dash lock.
1. **The native property above**, if its store can be found.
2. **A DLL hook that refuses the start.** Swap the `PamServerNamedChallengeEntity`'s message or
   event handler slot, and drop the activation for a locked ContentId. mecmp does the same kind of
   thing to the replay-download listener (`replay_check.cpp`): it changes a message as it passes,
   so the game takes its own failure path. Which slot handles the start is unknown; it needs
   reverse engineering.
3. **Let it run, but don't count it.** On Started for a locked dash, warn; ignore its Finished.
   **This is what the Dashes world does** (the "soft lock", working in game 2026-11-19), with the
   warning in the client's log instead of an overlay.
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
- Per-dash locking: **found, §11e** (`UnlockFlag`). The type property above is not needed for it.
- Whether Finished fires offline. The "upload" messages suggest the game talks to the stats
  backend at the end of every run, which is question 4 and question 5 together.
- A level reload without a restart (question 2 covers restarts only so far).

### 11e. The hard lock: each dash's `UnlockFlag` (in game, 2026-11-22)

`PamNamedChallengeData.UnlockFlag` (`+0x40`, a `PamProgressionFlag*`) is null on all 22 dashes
(§11c). **Pointing it at a progression flag makes that flag the dash's unlock.** First tested on
Out in the Open (Steam build, no DLL loaded):

| step | result |
|---|---|
| point `+0x40` at the `PamProgressionFlag` object of `Unlocks_Placeholder` (value 0) | nothing visible yet |
| reload a checkpoint | **the dash is gone from the map, and its start does nothing on foot** |
| set `Unlocks_Placeholder` = 1 through the client's `ProgressionWriter` | nothing visible yet |
| reload a checkpoint | **the dash is back on the map and playable** |
| set `+0x40` back to null, `Unlocks_Placeholder` back to 0 | restored; the game kept running throughout |

How the flag object was found: the name string `Unlocks_Placeholder`, then a pointer to it at
`object + 0x18` (`Name`) with `object + 0x10` (`NameHash`) = djb2a of the name. Exactly one object
matched. (`PamProgressionFlag`: `+0x10` NameHash, `+0x18` Name, `+0x20` MaxValue; SDK dump.)

**Then on all 22 dashes, each with its own flag** (same day, `tools/client/dash_unlock_probe.py`,
the table in [`data/dash_unlock_flags.json`](../data/dash_unlock_flags.json)):
- all 22 pointers written, flags 0, reload: **all 22 gone from the map**;
- 3 flags set to 1, reload: only Birdman's Route and Old Tunnels came back. Consumer Mayhem's flag,
  `ExampleMission3_Objective1`, read 0 again: **the game resets flags that belong to a mission**
  (`PamProgressionFlag` `+0x14` MissionIndex not 0). The 5 mission flags in the first pick were
  replaced;
- 2 more (High Roller Avenue, Donkey in an Oven) and the 5 replaced ones at 1, reload: **exactly
  those 9 back**, the other 13 hidden;
- the last 13 at 1, reload: **all 22 back, nothing else noticed in play**;
- `restore`: 22 pointers null, 22 flags 0.

**How the 22 flags were chosen.** A census of all 2374 flags in the table counted every pointer
in writable memory to each flag's definition (not counting the table node's own). Every flag sits
in two lists, so a flag that nothing else uses has exactly 2; `Unlocks_Placeholder`, the first
one tested, has 2. Kept: value 0, MissionIndex 0, 2 references, so no
`PamServerProgressionFlagEntity` and no mission on it. That gives 10 `Unlocks_*` flags (12 of the 22 never-set
ones were dropped: a flag entity watches them), 5 `ExampleBronzeMission_*` / `ExampleMission3_*`
result flags from two developer test missions, and 4 `Demo_*` flags. `SyncToOnline` and
`Clamp` differ among them and do not matter. "Nothing reads it" is limited to what was loaded in
memory then; a flag read by its hash alone would not show.

What this means:
- **The game has a real per-dash lock, driven by an ordinary progression flag.** A Dash Unlock
  item can be a flag write through the one write path, like an ability. The Dashes world's
  client does this (option `hard_dash_lock`, `client/dash_lock.py`).
- Both directions need a **checkpoint reload**. **Neither fast travel nor a death refreshes it**
  (tested 2026-11-22). A received unlock shows at the next checkpoint reload unless a live refresh
  is found.
- Turning on the developer test missions themselves (`ExampleMission3_Available`,
  `ExampleBronzeMission_Available` = 1, then a reload) showed nothing new in the menus or on the
  map (2026-11-22; set back to 0). So nothing is expected to write their result flags in play.
  There is also a template flag `Example_Example_NamedChallengeUnlock`, which suggests the
  designers meant `UnlockFlag` for exactly this.
- The pointer is in game memory, not the save: it has to be written at every game start, before
  the player can reach a dash. The flag value *is* in the save (autosave), which is what a
  Dash Unlock should be.

Still to settle before building it (OPEN_QUESTIONS #23):
1. ~~One flag per dash~~: done, `data/dash_unlock_flags.json`. Not yet checked: that the 22 stay
   at their value over a game restart and in other districts' loads (only reloads were tried),
   and that a seed save made by `make_seed_save.py` has them all at 0.
2. **When to write the pointers.** Before the city level loads, or right after, followed by one
   forced reload. In the DLL this could run before the first server tick.
3. **A live refresh** instead of a reload, if the dash entity has an "unlock changed" path.
4. Whether a run already in progress is affected. (Fast travel and death do not count as a
   reload.)
5. Whether a game restart really drops the pointer (expected: it is level data in memory).

### 11f. Locking every other activity: the mission's `CompletedFlag` (in game, 2026-11-22)

Every activity the player starts on foot (the 40 opportunities, deliveries, security hubs, side
missions, story missions) is a **`PamProgressionMission`**: vtable `0x141C8E658`, `+0x10` name,
`+0x40` MissionIndex, `+0x48` `CompletedFlag`, `+0x50` `AvailableFlag`, `+0xB0` MissionType. All
152 are listed in [`data/missions.json`](../data/missions.json) (type 1 opportunity, 2 bronze:
deliveries, security hubs and a few others, 3 side mission, 4 story, 0 completion flag
`DebugGenerated_*`: mostly test or cut content).

`<mission>_Available` means "offered now": 1 for an activity you can start, 0 once it is done.
**The game computes it at every checkpoint reload and writes it through the `+0x50` pointer:**
- writing `_Available` = 0 (The Vial, Exit Strategy): both read 1 again after the reload, nothing
  hidden;
- pointing The Vial's `+0x50` at an unused flag (0): after the reload that flag read **1**, The Vial
  still there.

**What works: make the game think the activity is done.** Point `+0x48` (`CompletedFlag`) at a flag
that is 1. Tested with `tools/client/activity_lock_probe.py`:

| activity | kind | result after a checkpoint reload |
|---|---|---|
| The Vial (`OW Opp DtPh2 02`) | opportunity | **off the map, cannot be started on foot**; `_Available` 0 |
| Exit Strategy | side mission | off the map; `_Available` 0 |
| Security Hub Downtown 1 | security hub | off the map; `_Available` 0 |
| OWPh2Delivery01 | delivery | `_Available` 0, but the game then offered OWPh2Delivery02 in its place (see below) |

- The real completion flag (`MiscCompleted_`, `SilverCompleted_`, `BronzeCompleted_`,
  `_CompletedTime`) stayed 0 in every case, so **no check is sent by the lock**.
- **Unlock: put the pointer back and reload.** The Vial came back and was playable.
- **One shared lock flag** (1) serves every locked activity, since unlocking changes the pointer,
  not the flag. The test used `Example_ExampleMission3Part1Completed` (§11e census: nothing reads it).
- Like the dash lock: pointers live in memory and need writing at every game start; only a
  checkpoint reload refreshes (not fast travel, not death).

The Dashes world uses this to clear its map (option `hide_other_activities`,
`client/activity_lock.py`), since none of these activities are checks there.

**Everything at once** (same day): all 22 dashes and all 92 type 1-3 activities locked, then a
reload. **Everything was gone except 6 "Dead Drop Delivery" markers**: the countdown deliveries
`OWPh<2-7>Delivery01`, whose `_Available` read 1.

**Dead Drop Deliveries are a chain per phase (01, 02, 03) and are not locked by this:**
- with only 01 locked, 02 became available (Available 1), so the chain moves on to the next one.
  Repeated on all 6 phases: 6 markers still on the map, and they were the 02s (each phase's
  `Delivery02_Available` 1, the 01s and 03s 0). The single-delivery test with the hub earlier was
  the same thing: its marker moved to 02;
- with all three locked, the game made 01 available again: a finished chain restarts;
- with 01's `+0x50` pointed at a dummy and the real `…Delivery01_Available` set to 0, the dummy
  read 1 after the reload and the markers stayed;
- with the dummy's `MaxValue` set to 0 (it has `Clamp`), the dummy stayed 0 and the markers
  **still** stayed (the 02/03 flags were not re-read in this run). So once a chain is finished,
  the replayed 01 marker does not come from 01's Available pointer;
- no delivery named challenge (`ch_dlvry_`) was loaded, so they are not dash-like either.

What they do read is not found yet. Likely a level script that reads the real `BronzeCompleted_`
or `_CompletedTime` flags by hash (which a pointer change cannot touch), or the live mission
object found next to their flags (heap, holding `BronzeCompleted_`, `Generated_ActiveMission`,
`Generated_AllMissionsDisabled`, the timestamps and `_Available`). Options for later: the global
`Generated_AllMissionsDisabled`, or a DLL hook on the delivery start point
(`PamMissionStartPointEntityData`, `+0x48` Mission).

Not yet checked: on foot for the side mission and the hub (only the map, and the flags); whether
locking a side mission's briefing blocks the mission after it; what the game does with a "done"
activity's rewards (none seen); story missions (not tried: locking one may block the story); a
game restart.

### 11g. Finding the checkpoint reload's message (research mode, mec_ap 0.2.2 and 0.2.3)

Goal: reload the checkpoint from the DLL after a dash ends, but only when a Dash Unlock arrived,
so the player never has to reload by hand (§11e: only a checkpoint reload refreshes the map).
Nothing in the kit says yet how the pause menu's reload is carried out.

**What is known (read 2026-11-25):**
- Both ids in a message header are djb2a hashes of names: the category is the class name's
  prefix, the type the whole class name. Checked: `PamSocialPlay` = 0x54776FC6, `ServerPlayer` =
  0xF3C93DD3, `PamSocialPlayNamedChallengeFinishedMessage` = 0xD71D027F (MECMP runs.cpp).
- The exe holds 675 `*Message` class names (`tools/client/gen_message_names.py`). Ones that
  could be a reload: `ServerGameManagerRestartLevelRequestMessage`, `ServerLoadGameMessage`,
  `LoadGameBeginLoadMessage`, `PamplonaRestartGameMessage`, `ServerPlayerRespawnMessage`,
  `ServerGameplayCheckpointActivatedMessage` / `...TriggeredMessage`,
  `PamTelemetryStoryCheckpointMessage`, `CoreReadSaveGameMessage`.

**Research mode** (`dll/src/research.cpp`): with a file `mec_ap_research.txt` next to the DLL, it
registers one more listener on every candidate category (963: every CamelCase prefix of a class
name) on both message managers, and writes `mec_ap_messages.log`: time, manager (C/S), category,
type and the first 0x80 bytes. A type is logged in full for its first 8 messages, then once a
second at most (with a count of the skipped ones). It sends nothing and calls nothing else.

**The session:** reload a checkpoint by hand a few times, with a death and a fast travel in
between as controls (neither refreshes the map). The message that shows only at the reloads is
the candidate. Then: whether posting it (on the game thread) reloads, and whether a reload right
after a dash's results screen is safe.

**First session (2026-11-25, 0.2.2, `mec_ap_messages.log`):** research mode ran without trouble
(963 categories on both managers, no stutter reported). Two checkpoint reloads (00:32:20,
00:33:01) and one death (00:32:45) were logged. **A checkpoint reload is a full level reload**,
the same path as loading the city from the main menu (00:30:52):

| time after the confirm | manager | message |
|---|---|---|
| 0 | C, then S | `NetworkPamUINotificationResponseMessage` (the confirm dialog's answer) |
| +0.0 | C, S | `PamplonaGamePausedMessage` (unpause) |
| +0.6 s | S | `ServerRoundResetMessage` (0x4BB8DE5C) |
| +1.2 s | S | type 0xF8429A0E = **`ServerLoadLevelMessageBase`** (not in the exe's strings; named through its vtable `0x141B42F10`, slot 0 = getType, TypeInfo `0x142804478`) |
| +1.2 s | S | `ServerUnloadLevelMessage`, then `ServerPeerLoadLevelMessage`, `ClientLoadLevelMessage` |
| +7 s / +16 s | S, C | `ServerLevelLoadedMessage` / `NetworkOnPlayerSpawnedMessage` |

The death has none of these (`PamTelemetryDeathMessage`, `ClientPlayerKilledMessage`, then a
spawn). No fast travel was logged. A message's vtable slot 0 is its getType (`lea rax,[TypeInfo];
ret`), which names any message the string table misses.

Building a `ServerLoadLevelMessageBase` by hand is not an option: its payload holds pointers and
counters whose meaning is unknown. Next: capture the call stack when `ServerRoundResetMessage`
and `ServerLoadLevelMessageBase` are dispatched, to find the function the pause menu's reload
calls (if dispatch is immediate; a queued message only shows the dispatch loop).

**Second session (2026-11-25, 0.2.3):** research mode also logs the call stack (up to 48 return
addresses from `RtlCaptureStackBackTrace`, as image VAs) and the thread id of the reload
messages. Two checkpoint reloads (14:41:38/39, 14:42:00/02) were logged; the stacks were the same
both times:

- Two threads: the client manager dispatches on one (the UI thread, tid 4476), the server
  manager on another (tid 26420). A client message reaches the server manager through a
  network-receive path (`0x14347C5AB … 0x14349ACF1`, then the server pump `0x14334460B` /
  `0x143345275` under `0x142A305B4 … 0x142C7895B`).
- The confirm answer (`NetworkPamUINotificationResponseMessage`) is sent from UI code in
  `fn 0x1431A2B50` (return `0x1431A2D2B`), through `fn 0x142A397A0`, and is dispatched at once.
- **`ServerRoundResetMessage` is dispatched synchronously** (no queue) on the server thread,
  about 0.5 s after the confirm, from `fn 0x1439E07E0` ← `fn 0x143A74BF0` ← `fn 0x14314E4A0` ←
  `fn 0x143364BA0` (a listener) ← the dispatcher `fn 0x142A394A0` ← the network-receive path. So
  it is a reaction to some client-to-server message that none of the 963 candidate categories
  heard (not the confirm answer: that one arrived 0.5 s earlier). `fn 0x143A74BF0` /
  `fn 0x1439E07E0` are the candidates for "restart from the checkpoint".
- `ServerLoadLevelMessageBase` and `ServerUnloadLevelMessage` come straight from the server pump
  (`fn 0x143345090`, `fn 0x143344D90`): the level reload is a later step the round reset starts.
- The first `ServerRoundResetMessage` of the session (the load from the main menu, 14:41:06)
  came by another path (`fn 0x14338A790` ← `fn 0x143383090` ← `fn 0x14314A5D0` …).

The exe on disk is packed: its code section (`.sbss`, 0x14292A000) is encrypted and only
decrypted in memory. The functions were disassembled (capstone) from a read-only copy of the
running game's code (`ReadProcessMemory` through `mec_memory`, 2026-11-25), with function bounds
from the exe's `.pdata`.

**The reload chain (disassembled 2026-11-25, our build; nothing called yet):**

1. `fn 0x143364BA0` is a server listener for `EventSyncReachedClientMessage` (type 0x458F8B20,
   checked against research_names.h): an entity event raised on the client, replayed on the
   server. It finds the target entity in a map keyed by the message's +0x50 / +0x48 / +0x60 and
   fires the event there (`0x14314E8A0`, event id 0x0B87DF4B = djb2a("Out")). That message is
   frequent, so the rate limit hid the one that mattered in the log.
2. The event reaches slot 4 (+0x20, the event handler) of the vtable `0x141C7ADD0`, whose slot 0
   returns the TypeInfo `0x142864380` = **`PamServerMissionManagerEntity`** (read live). The
   handler `fn 0x143A74BF0` switches on the event id at `[event+8]`. Event ids are not in the
   exe's strings, so they stay unnamed:
   - **0xC6551D27 → `0x1439E0590()`**: the reload taken by both checkpoint reloads.
   - 0x37BB9BFC → `0x1439E07E0(nullptr)` unless `0x1439D9510(...)` says no.
   - 0x41EE0DA7 → `0x1439E0720(...)`.
3. **`fn 0x1439E0590` (reload from the checkpoint) takes no arguments**: rcx is never read. It
   gets a lazily created global (`[0x14257CB98]`) and looks up the current checkpoint in the
   progression flag table (`[0x14257C9D8]`, FlagTable in addresses.h; `0x1439DA880`). It then
   finds the `PamServerMissionStartPointEntity` (TypeInfo `0x142863D40`) with that id in the
   server world (`[0x1425469E0]`) and tail-calls `0x1439E07E0([entry+0x18])`, or else
   `0x1439E0720(...)`, which ends in `0x1439E07E0` too.
4. **`fn 0x1439E07E0(const char* name)` does the restart**. It returns at once if
   `0x143343260([0x14253D670])` gives null. Otherwise it builds a `ServerRoundResetMessage`
   (`0x144676180`) and dispatches it at once on the server message manager (`[0x14253D670]+0x10`,
   the global in addresses.h, through `0x142A39770` → dispatcher `0x142A394A0`). Then it calls
   `0x143341D40(level info copied from +0x118, 1, 0)`, which starts the level unload and load. A
   null `name` uses an empty string. Its only callers are `0x1439E0590` (jmp), `0x1439E0720`
   (jmp) and the handler above.

So "reload the checkpoint" from the DLL is one call to `0x1439E0590()` on the server thread,
the thread both reloads ran on (tid 26420). It skips the pause menu's fade and confirm; the level
still unloads and loads, with the usual loading screen.

**`/reload` (mec_ap 0.3.0, `dll/src/reload.cpp`).** The client sends
`{"cmd":"reload","id":N}`. The DLL then:
- **Build check at startup.** It checks the mission manager's vtable slot 0 (getType) against
  that TypeInfo and its name, slot +0x20 against the handler, and the first bytes of both
  functions. On a mismatch `/reload` stays off and the hello says why.
- **The call.** It makes the call in the tick hook, after the game's own postUpdate, only for the
  main server world (`world == [0x1425469E0]`), and inside `__try`. An exception turns reload off
  for the session.
- **Pointer checks first.** Right before the call, it checks with safe reads the pointers the
  function reads before its first check: the global, its three pointers, the flag table and the
  server context. If one is missing the answer is `no_checkpoint` and nothing is called. No main
  world within 5 s gives `not_in_level`.
- **The answer.** `started` only when a `ServerRoundResetMessage` was dispatched during the call;
  the listener counts them on category `ServerRound`, and the dispatch is synchronous. Otherwise
  the answer is `nothing`. A second reload within 20 s is `busy`. The log line gives the thread
  id, to compare with the 26420 seen in the research log.

**First try (2026-11-25 18:26, mec_ap.log and mec_ap_messages.log):** build check passed;
one `/reload` in the city answered `started`. The call ran on thread 23244, the thread every
server-manager message of that session was dispatched on. The research log shows the same
sequence as the pause menu's reload: `ServerRoundResetMessage` (from `0x1439E08A0`, called from
mec_ap.dll's tick hook), `ServerLoadLevelMessageBase` +0.6 s, `ServerUnloadLevelMessage`,
`ServerLevelLoadedMessage` +5.9 s, `NetworkOnPlayerSpawnedMessage` +11.9 s. The game kept running.

Tried the same day: at the main menu it answered `not_in_level`, as intended; 5 s after
cancelling a dash (Ramp, 18:29:00) it answered `started`, and the level was loaded 6 s later and
Faith spawned at +12 s.

**Automatic reload (client `auto_reload.py`, DLL 0.3.1).** The client remembers what only a reload
shows: each Dash Unlock written, and the first hard lock and activity hiding. When the player
leaves a dash (2 s after a cancel, 6 s after a finish, unless a new dash starts), it sends one
`reload`. Every `ServerRoundResetMessage` clears the list; the DLL reports each one as
`{"ev":"round_reset"}`, the pause menu's too. A finish replayed from the journal (older than
30 s) never triggers it. First try (2026-11-25 18:41): no reload, because the unlock earned by
the dash (Quite a View's 1 Star) arrived 0.6 s after the finish, when the list was still empty.
Now an unlock noted within 20 s of leaving a dash schedules the reload too. At a game launch the
hard lock and the activity hiding are written after the level loads (about 45 s after "World
loaded" in the 18:37 client log), so they too need a reload: the client now does one 3 s after
they are written, at most once per DLL hello. 2026-11-27: the dashes stream into memory over
about a minute after a launch (the client found 5 at 20:15:15, 14 at 20:16:01, 22 at 20:16:31);
the reload followed the first partial write and 17 dashes stayed on the map. The launch reload
now waits until the lock and the hiding are complete (or 90 s, then once more on completion).

**Leaving a dash (DLL 0.3.2).** The 6 s timer after a finish reloaded while the results screen
(restart or leave) was still up (18:53:25 finish, reset at 18:53:31.99). The research logs of
2026-11-25 show the pattern, client message manager:
- teleport to a dash: `ServerInputDeactivateInputRestrictionMessage`,
  `PamOnlineBeginSocialActivityMessage` (0x20EC5D8C), `PamTelemetryTeleportMessage`, then Started;
- a retry: input restriction and teleport, then Started; no Begin / End;
- finish: Finished, `PamTelemetryEndSocialFeatureMessage`, `PamUISystemCameraChangedMessage` (the
  results camera);
- leaving the results (18:41:40, 9 s after that finish): a second camera change, input
  restriction, **`PamOnlineEndSocialActivityMessage`** (0x64B0D004, the only one that session),
  teleport.
The DLL listens on category `PamOnline` (0x39191416) and sends `activity_began` /
`activity_ended`; hello says `"activity_events": true`. After a finish the client waits for
`activity_ended`, then reloads 1 s later; a retry starts the dash again and cancels it. Seen
once; whether a cancel also sends End is not known (a cancel keeps its 2 s timer). Not yet tried in game: the reload 6 s after a finish, while the results
screen is up.

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
| 7 | which thread owns flag-check entities | read where they are created before calling anything | a definite answer. **Done 2026-11-13: server (`PamServerProgressionFlagEntity`), §5** |
| 8 | `apply` from the hook | one `live_entity` ability, one call, `force = 0` | `[e+0x78]` changes and the ability works with no death. **Done 2026-11-13: Coil and FastClimb applied live (`[e+0x78]` read back 1, no crash). The first try (0.2.0) found no entity: it compared `[e+0x80]` with the address `node+0x10` instead of the pointer stored there; fixed in 0.2.1, see MEMORY.md §3** |

Steps 1 to 5 need no code from this project. Step 1 uses the script that ships here, and steps 2
to 5 use mecmp's release.

## 13. License and credit

- mecmp is MIT, so its code may be copied or adapted with its copyright notice kept.
- Dear ImGui is MIT.
- apclientpp is MIT.
- APCpp is LGPL-2.1.

Credit mecmp in any DLL that uses its addresses, since finding them was the hard part.
