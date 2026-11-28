#include "reload.h"

#include <windows.h>

#include <atomic>
#include <cstring>
#include <mutex>

#include "addresses.h"
#include "listener.h"
#include "log.h"
#include "mem.h"

namespace mecap::reload {
namespace {

// First bytes of both functions, read from the running game on 2026-11-25 (docs/DLL.md §11g).
// ReloadCheckpoint: mov [rsp+8],rbx; push rdi; sub rsp,30h; mov rbx,[rip+..] (the global below);
// test rbx,rbx; jnz.
constexpr unsigned char kReloadHead[] = {0x48, 0x89, 0x5C, 0x24, 0x08, 0x57, 0x48, 0x83, 0xEC, 0x30, 0x48, 0x8B,
                                         0x1D, 0xF7, 0xC5, 0xB9, 0xFE, 0x48, 0x85, 0xDB, 0x75, 0x1D, 0x48, 0x8B};
// RestartLevel(const char* startPoint): push rbx; sub rsp,80h; mov qword [rsp+20h],-2.
constexpr unsigned char kRestartHead[] = {0x53, 0x48, 0x81, 0xEC, 0x80, 0x00, 0x00, 0x00,
                                          0x48, 0xC7, 0x44, 0x24, 0x20, 0xFE, 0xFF, 0xFF};
constexpr DWORD kMinGapMs = 20000;

std::atomic<bool> g_enabled{false};
std::atomic<uint32_t> g_pendingId{0};
std::atomic<bool> g_pending{false};
std::atomic<DWORD> g_requestAt{0};
constexpr DWORD kWaitMs = 5000;      // no main server world for this long: not in a level
DWORD g_lastStart = 0;
bool g_started = false;

std::mutex g_resultsM;
std::vector<Result> g_results;

void report(uint32_t id, const char* result, unsigned long thread = 0) {
    std::lock_guard<std::mutex> lock(g_resultsM);
    g_results.push_back({id, result, thread});
}

std::string className(uintptr_t ti) {
    std::string s;
    const uintptr_t data = mem::readOr<uintptr_t>(ti);
    const uintptr_t name = data ? mem::readOr<uintptr_t>(data) : 0;
    if (name) mem::readCString(name, s);
    return s;
}

bool headIs(uintptr_t va, const unsigned char* want, size_t n) {
    unsigned char got[32] = {};
    return n <= sizeof(got) && mem::read(mem::rva(va), got, n) && memcmp(got, want, n) == 0;
}

// What ReloadCheckpoint reads before its first check, read safely: its global (it would create
// the object if missing; we refuse instead), the three pointers under it, the flag table and the
// server game context.
bool pointersReady() {
    const uintptr_t g = mem::readOr<uintptr_t>(mem::rva(addr::ReloadGlobal));
    const uintptr_t a = g ? mem::readOr<uintptr_t>(g + 0x20) : 0;
    const uintptr_t b = a ? mem::readOr<uintptr_t>(a + 0x28) : 0;
    const uintptr_t c = b ? mem::readOr<uintptr_t>(b + 0x20) : 0;
    uintptr_t probe = 0;
    return c && mem::read(c + 8, probe) && mem::readOr<uintptr_t>(mem::rva(addr::FlagTable)) &&
           mem::readOr<uintptr_t>(mem::rva(addr::ServerGameContext));
}

bool callReload() {
    __try {
        reinterpret_cast<void (*)()>(mem::rva(addr::Fn_ReloadCheckpoint))();
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

} // namespace

bool check(std::string& why) {
    // The handler's vtable: slot 0 is getType (`lea rax,[rip+rel32]; ret`) -> the class's TypeInfo.
    const uintptr_t getType = mem::readOr<uintptr_t>(mem::rva(addr::VT_MissionManagerEntity));
    unsigned char code[8] = {};
    if (!getType || !mem::read(getType, code, sizeof(code)) || code[0] != 0x48 || code[1] != 0x8D ||
        code[2] != 0x05 || code[7] != 0xC3) {
        why = "the mission manager's vtable does not start with getType";
        return false;
    }
    int32_t rel = 0;
    memcpy(&rel, code + 3, 4);
    const uintptr_t ti = getType + 7 + static_cast<intptr_t>(rel);
    const std::string name = className(ti);
    if (ti != mem::rva(addr::TI_PamServerMissionManagerEntity) || name != "PamServerMissionManagerEntity") {
        why = "the mission manager's class reads as '" + name + "'";
        return false;
    }
    if (mem::readOr<uintptr_t>(mem::rva(addr::VT_MissionManagerEntity + addr::VT_EventSlot)) !=
        mem::rva(addr::Fn_MissionManagerOnEvent)) {
        why = "the mission manager's event handler is not where it was";
        return false;
    }
    if (!headIs(addr::Fn_ReloadCheckpoint, kReloadHead, sizeof(kReloadHead)) ||
        !headIs(addr::Fn_RestartLevel, kRestartHead, sizeof(kRestartHead))) {
        why = "the reload functions do not start with the expected bytes";
        return false;
    }
    g_enabled = true;
    LOG("reload: check passed (PamServerMissionManagerEntity, reload and restart functions)");
    return true;
}

bool enabled() { return g_enabled; }

void request(uint32_t id) {
    if (!g_enabled) {
        report(id, "disabled");
        return;
    }
    if (g_pending.exchange(true)) {   // one already waiting for the tick
        report(id, "busy");
        return;
    }
    g_pendingId = id;
    g_requestAt = GetTickCount();
}

void onServerTick(void* world) {
    if (!g_pending.load(std::memory_order_acquire)) return;
    // Only for the main server world (MECMP's rule: *ServerGameWorld, null between levels). The
    // request waits while there is none: a reload asked for during a loading screen runs after it.
    const uintptr_t main = mem::readOr<uintptr_t>(mem::rva(addr::ServerGameWorld));
    if (!main || reinterpret_cast<uintptr_t>(world) != main) return;
    if (!g_pending.exchange(false)) return;   // the link thread timed it out meanwhile
    const uint32_t id = g_pendingId.load();
    const DWORD now = GetTickCount();
    if (g_started && now - g_lastStart < kMinGapMs) {
        report(id, "busy");
        return;
    }
    if (!pointersReady()) {
        report(id, "no_checkpoint");
        return;
    }
    const uint32_t before = listener::roundResets();
    const unsigned long tid = GetCurrentThreadId();
    if (!callReload()) {
        g_enabled = false;   // an exception inside the game's function: never again this session
        LOG("reload: the call raised an exception (thread %lu); reload is off until the game restarts", tid);
        report(id, "fault", tid);
        return;
    }
    const bool started = listener::roundResets() != before;
    if (started) {
        g_started = true;
        g_lastStart = now;
    }
    LOG("reload: called on thread %lu: %s", tid,
        started ? "ServerRoundResetMessage dispatched, the level reloads" : "no round reset (nothing happened)");
    report(id, started ? "started" : "nothing", tid);
}

std::vector<Result> drainResults() {
    // No tick for the main world within kWaitMs (main menu, a long load): answer instead of waiting.
    if (g_pending.load() && GetTickCount() - g_requestAt.load() > kWaitMs && g_pending.exchange(false))
        report(g_pendingId.load(), "not_in_level");
    std::lock_guard<std::mutex> lock(g_resultsM);
    std::vector<Result> out;
    out.swap(g_results);
    return out;
}

} // namespace mecap::reload
