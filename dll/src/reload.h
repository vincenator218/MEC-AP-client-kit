#pragma once
// Reloading the last checkpoint on request (the client's /reload), with the game's own function:
// the one the pause menu's "reload checkpoint" ends in (docs/DLL.md §11g).
//
// The chain, disassembled from our build on 2026-11-25: the pause menu's confirm raises an event
// on PamServerMissionManagerEntity (vtable 0x141C7ADD0, event handler at +0x20 = 0x143A74BF0).
// For event 0xC6551D27 the handler calls ReloadCheckpoint (0x1439E0590). That function takes no
// argument: it finds the current checkpoint's start point and calls the restart function
// (0x1439E07E0), which dispatches ServerRoundResetMessage and starts the level reload.
//
// Rules:
//   * Off unless the build check passes: the handler's vtable, class name and slot, and the first
//     bytes of both functions.
//   * Called only on the server game thread, from the tick hook, for the main server world, after
//     the game's own postUpdate. Every pointer the function reads first is checked with safe reads
//     right before the call.
//   * The result reports what the game did: "started" only when ServerRoundResetMessage was
//     dispatched during the call (the listener counts them).
//   * At most one reload per 20 s; nothing is retried.

#include <cstdint>
#include <string>
#include <vector>

namespace mecap::reload {

bool check(std::string& why);   // after the build check; false keeps /reload off
bool enabled();

struct Result {
    uint32_t id;
    const char* result;   // started | nothing | not_in_level | no_checkpoint | busy | disabled | fault
    unsigned long thread; // the thread the call ran on (0 when it did not run)
};

void request(uint32_t id);                // link thread
void onServerTick(void* world);           // server game thread, after the original postUpdate
std::vector<Result> drainResults();       // link thread

} // namespace mecap::reload
