# mec_ap.dll: dash checks from inside the game

A small DLL that is loaded into Mirror's Edge Catalyst and tells the Archipelago client when a
**dash** (or any other named challenge) is started, cancelled or finished, with the run's time.
Dashes have no progression flag to read (docs/DLL.md §11), so this is the only way to detect
them. The client turns a finish into checks: the finish itself, and each star tier the time beats.

**Status: built and run in game once (2026-11-12, Steam build, with MECMP 0.9.0-beta.3.1 loaded
first).** It compiled cleanly with MSVC 19.44. In the game it passed its build check, found
both hook slots already taken by MECMP and chained in front of them, and registered on both
message managers. One dash finish (Too Close to the Sun, 57.16, a slower run than the 49.66
record) was logged and journaled once, with the right ContentId and run time.

**End to end, the same night, without MECMP:** a local seed with only dash locations, the real
Archipelago client connected to the DLL. Too Close to the Sun in 63.40 (stars at 68.00 / 59.00 /
55.00) sent exactly `Dash - Too Close to the Sun` and `... - 1 Star`; the server received both,
the client acknowledged seq 1, and the client logged the dash start too.

## What it does, and what it does not

- It **reads** the game's "challenge finished / started / cancelled" messages.
- It changes game memory in exactly **two places**: one pointer each in the vtables of the
  server tick and the client replay updater. That is how it gets onto the game's own threads to
  register its listener. No game code is patched.
- It writes **no progression flags**, no save data, and calls no game function except
  `MessageManager_registerListener`.
- It does **not** stop you from starting a dash (there is no per-dash lock in the game; §11d).
- Before touching anything it checks the game build (3 TypeInfo objects, the 2 hook slots, the
  listener function's first bytes). On any mismatch it hooks nothing and tells the client why.

## Build (once)

1. Install **Visual Studio 2022 Build Tools** (free, from Microsoft's Visual Studio download page:
   "Build Tools for Visual Studio 2022"). In the installer tick the workload
   **Desktop development with C++**. Its default components are enough: the MSVC x64 compiler,
   the Windows SDK and *C++ CMake tools for Windows*.
2. Open **x64 Native Tools Command Prompt for VS 2022** from the Start menu, then:

   ```
   cd "C:\not garbage\Archipelago\MEC-AP-client-kit\dll"
   cmake -B build -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
   cmake --build build
   ```

   (Or open the `dll` folder in Visual Studio 2022 with *File > Open > Folder* and build
   `x64-Release`.)
3. The results are `build\mec_ap.dll` and `build\mec_ap_inject.exe`. The DLL is linked with the
   static runtime, so nothing else needs installing on a player's PC.

## Use

1. Put `mec_ap.dll` and `mec_ap_inject.exe` in one folder (anywhere; not inside the game folder).
2. Start the Archipelago client from the Launcher and connect to your slot.
3. Start the game and run `mec_ap_inject.exe` (before or after the game starts; it waits out the
   EA activation window). If the game runs as administrator, run the injector as administrator.
4. `mec_ap.log` next to the DLL should say `ready`, and the client
   `Connected to mec_ap.dll 0.1.0. Dash checks are on.`
5. Load into free roam and run dashes. The client logs each start, cancel and finish.

**Run it again after every game restart**: the DLL lives only as long as the game process.

**With MECMP:** load MECMP first, then this. MECMP's tick hook only accepts the game's original
function, so if this DLL is loaded first, MECMP turns its own tick hook off. This DLL chains in
front of whatever is in the slot, so the order MECMP-then-mec_ap works for both (tested once:
both hooks chained; MECMP's own features were not checked).

## Files it writes, next to the DLL

| file | what |
|---|---|
| `mec_ap.log` / `mec_ap.prev.log` | this run's log and the previous one |
| `mec_ap_events.jsonl` | **the journal**: every finished run, one line each, with a sequence number |
| `mec_ap_acked.txt` | the last sequence number the client has dealt with |

A finish is written to the journal before it is sent, and sent again on every connection until
the client acknowledges it. The client acknowledges only once it has a slot. So a dash finished
while the client was closed, or before it connected, still counts. **Delete the journal and
`mec_ap_acked.txt` before starting a new seed**: otherwise runs from before the seed are sent to
it when the client first connects.

## Protocol

127.0.0.1 port 47910, one JSON object per line; see `src/link.h`. Only processes on the same PC
can connect.

## Layout

| file | what |
|---|---|
| `src/dllmain.cpp` | startup thread: wait, check, hook, link |
| `src/build_check.cpp` | the build check |
| `src/hooks.cpp` | the two vtable-slot hooks |
| `src/listener.cpp` | the message listener; turns messages into events |
| `src/link.cpp` | journal and TCP link to the client |
| `src/addresses.h` | every game address used (all are in `data/dll_addresses.json`) |
| `src/mem.h` | safe reads, the slot swap |
| `inject/mec_ap_inject.cpp` | the loader |

Credit: the hooking method, listener layout, message fields and addresses come from MECMP (MIT);
see `THIRD_PARTY_NOTICES.md`.

## Not verified yet

- `started` with MECMP loaded first: it was logged without MECMP (second run) but not in the first
  run, which had MECMP loaded; `cancelled` has not been seen yet;
- that a time exactly on a star threshold earns the star (the client counts it);
- that `Finished` fires with the PC offline (the dash type's `RequiresOnline` is 0);
