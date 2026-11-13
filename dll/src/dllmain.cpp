// mec_ap.dll: the Archipelago agent inside Mirror's Edge Catalyst.
//
// It does two things for the Archipelago client (apworld client/, over 127.0.0.1):
//   * tells it when a dash or any other named challenge is started, cancelled or finished;
//   * when asked, applies an ability flag the client has just written, on the server game thread
//     (apply.cpp), so a received ability works now instead of at the next respawn.
// It writes no progression flags, calls no game functions except MessageManager_registerListener
// and the flag entity's apply, and changes game memory in exactly two places: the tick and
// client-updater vtable slots (hooks.cpp).
//
// Startup, on a thread of its own (never inside DllMain: loader lock):
//   1. wait for the engine's TypeInfo list (build_check.cpp);
//   2. check the build; on any mismatch hook nothing, but still answer the client, saying why;
//   3. install the two hooks, which register the listener from the game's own threads;
//   4. run the link (link.cpp).
// The DLL pins itself: it is never unloaded while the game runs, since the game calls into it.

#include <windows.h>

#include <string>

#include "apply.h"
#include "build_check.h"
#include "hooks.h"
#include "link.h"
#include "log.h"
#include "version.h"

namespace {

DWORD WINAPI start(void* module) {
    mecap::log::init(module); // fully qualified: a bare `log` could also mean the C math function
    LOG("mec_ap %s loaded", mecap::kVersion);
    std::string why;
    bool ok = mecap::build::waitForEngine();
    if (!ok) why = "the engine's type list never filled";
    if (ok) ok = mecap::build::check(why);
    if (ok && !mecap::hooks::install()) {
        ok = false;
        why = "the hooks could not be installed (see mec_ap.log)";
    }
    std::string applyWhy = "the DLL is inactive";
    if (!ok) LOG("inactive: %s. Nothing in the game was changed.", why.c_str());
    else LOG("ready. Dashes and other challenges are reported to the Archipelago client.");
    if (ok && !mecap::apply::check(applyWhy)) LOG("apply: off: %s. Abilities apply at the next respawn.", applyWhy.c_str());
    mecap::link::start(ok, why, applyWhy);
    return 0;
}

} // namespace

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        HMODULE pinned = nullptr;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                           reinterpret_cast<LPCWSTR>(&DllMain), &pinned);
        if (HANDLE t = CreateThread(nullptr, 0, &start, inst, 0, nullptr)) CloseHandle(t);
    }
    return TRUE;
}
