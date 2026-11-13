#include "hooks.h"

#include <windows.h>

#include <atomic>
#include <cstdint>

#include "addresses.h"
#include "apply.h"
#include "listener.h"
#include "log.h"
#include "mem.h"

// The method is MECMP's (src/game/hooks.cpp, MIT): read the slot, store what it holds, swap one
// pointer, call the stored function first from the hook. No game code is patched.
//
// One difference: MECMP's tick hook refuses a slot that does not hold the game's own function.
// This one also accepts code another mod put there and chains in front of it, so it can run
// together with MECMP when MECMP is loaded first. (Loaded the other way round, MECMP's tick hook
// refuses and MECMP stays off: load MECMP first.)

namespace mecap::hooks {
namespace {

using PostUpdateFn = void (*)(void* world, void* updateInfo);
using UpdateAllFn = void (*)(void* self, void* info);
PostUpdateFn g_origPostUpdate = nullptr;
UpdateAllFn g_origUpdateAll = nullptr;
std::atomic<uint32_t> g_ticks{0};

// Server game thread, once per tick, for every server world.
void postUpdate(void* world, void* updateInfo) {
    g_origPostUpdate(world, updateInfo);
    if (g_ticks.fetch_add(1) % 30 == 0) listener::registerServer(); // about once a second
    apply::onServerTick(); // the flag-check entities are server entities: this is their thread
}

// Client thread, per frame (one call per updater object).
void updateAll(void* self, void* info) {
    listener::registerClient(); // a pointer compare once registered
    g_origUpdateAll(self, info);
}

// Stores the slot's current function in `orig`, then points the slot at `hook`.
template <class Fn> bool swap(uintptr_t slotVa, Fn hook, Fn& orig, const char* what) {
    const uintptr_t slot = mem::rva(slotVa);
    uintptr_t current = 0;
    if (!mem::read(slot, current) || !current || !mem::isExecutable(current)) {
        LOG("hook %s: slot does not hold code; not hooking", what);
        return false;
    }
    orig = reinterpret_cast<Fn>(current); // before the swap: a call that gets in between must reach it
    if (!mem::patchPointer(slot, reinterpret_cast<uintptr_t>(hook))) {
        LOG("hook %s: VirtualProtect failed (%lu)", what, GetLastError());
        return false;
    }
    LOG("hook %s: installed", what);
    return true;
}

} // namespace

bool install() {
    // The client hook first: if the tick hook then fails, the client one is taken out again,
    // so a failed start leaves the game as it was.
    if (!swap(addr::Slot_ClientReplayUpdateAll, &updateAll, g_origUpdateAll, "client updater")) return false;
    if (!swap(addr::Slot_ServerWorldPostUpdate, &postUpdate, g_origPostUpdate, "tick")) {
        mem::patchPointer(mem::rva(addr::Slot_ClientReplayUpdateAll), reinterpret_cast<uintptr_t>(g_origUpdateAll));
        LOG("hooks: tick hook failed; client hook removed again");
        return false;
    }
    return true;
}

} // namespace mecap::hooks
