#include "listener.h"

#include <windows.h>

#include <atomic>
#include <cstring>
#include <mutex>

#include "addresses.h"
#include "log.h"
#include "mem.h"

namespace mecap::listener {
namespace {

// A listener is any object whose vtable the message manager calls: slot 0 onMessage(self, msg),
// slot 1 priority(self), asked once at registration (MECMP runs.cpp, the same layout).
struct Listener {
    void* const* vtbl;
};
void onMessage(Listener* self, const void* message);
uint16_t priority(Listener*) { return 0; }
void* const g_vtbl[2] = {reinterpret_cast<void*>(&onMessage), reinterpret_cast<void*>(&priority)};
Listener g_client{g_vtbl}, g_server{g_vtbl};
std::atomic<uintptr_t> g_clientManager{0}, g_serverManager{0}; // the manager each is registered with

std::mutex g_m;
std::vector<Event> g_queue;
// The last finish queued: one run sends one Finished per stat set, and both managers may dispatch
// it, so the same content and time again within 5 s is a repeat (MECMP's rule).
struct Recent { uint32_t content; int64_t runCs; DWORD at; } g_recent{0, 0, 0};
// Started / Cancelled can also arrive twice, once per manager.
struct RecentSimple { Kind kind; uint32_t content; DWORD at; } g_recentSimple{Kind::Started, 0, 0};

void push(const Event& e) {
    std::lock_guard<std::mutex> lock(g_m);
    if (g_queue.size() < 4096) g_queue.push_back(e);
}

void onFinished(const uint8_t* m) {
    Event e{Kind::Finished, 0};
    uint8_t had = 0, rec = 0;
    memcpy(&e.contentId, m + addr::Fin_ContentId, 4);
    memcpy(&e.set, m + addr::Fin_Set, 4);
    memcpy(&e.deltaCs, m + addr::Fin_Delta, 4);
    memcpy(&had, m + addr::Fin_HadRecord, 1);
    memcpy(&e.recordCs, m + addr::Fin_Record, 8);
    memcpy(&rec, m + addr::Fin_NewRecord, 1);
    e.hadRecord = had != 0;
    e.newRecord = rec != 0;
    // With a new record, or no record before, the record field is already this run's time;
    // otherwise the run is record + difference (seen in game: 2663 + 690 = a 33.53 s run).
    e.runCs = (e.newRecord || !e.hadRecord) ? e.recordCs : e.recordCs + e.deltaCs;
    if (e.runCs <= 0) return;
    {
        std::lock_guard<std::mutex> lock(g_m);
        const DWORD now = GetTickCount();
        if (g_recent.content == e.contentId && g_recent.runCs == e.runCs && now - g_recent.at < 5000) return;
        g_recent = {e.contentId, e.runCs, now};
    }
    push(e);
}

void onSimple(const uint8_t* m, Kind kind) {
    Event e{kind, 0};
    memcpy(&e.contentId, m + addr::Msg_ContentId, 4);
    {
        std::lock_guard<std::mutex> lock(g_m);
        const DWORD now = GetTickCount();
        if (g_recentSimple.kind == kind && g_recentSimple.content == e.contentId && now - g_recentSimple.at < 1000)
            return;
        g_recentSimple = {kind, e.contentId, now};
    }
    push(e);
}

void onMessage(Listener*, const void* message) {
    const auto* m = static_cast<const uint8_t*>(message);
    uint32_t category = 0, type = 0;
    memcpy(&category, m + addr::Msg_Category, 4);
    if (category != addr::kCategorySocialPlay) return;
    memcpy(&type, m + addr::Msg_Type, 4);
    if (type == addr::kTypeNamedChallengeFinished) onFinished(m);
    else if (type == addr::kTypeNamedChallengeStarted) onSimple(m, Kind::Started);
    else if (type == addr::kTypeNamedChallengeCancelled) onSimple(m, Kind::Cancelled);
}

void registerOn(uintptr_t contextVa, Listener& l, std::atomic<uintptr_t>& done, const char* which) {
    const uintptr_t ctx = mem::readOr<uintptr_t>(mem::rva(contextVa));
    if (!ctx) return;                                  // not in a level yet
    const uintptr_t manager = ctx + addr::Context_MessageManager;
    if (done.load() == manager) return;                // already registered with this one
    using RegisterFn = char (*)(uintptr_t manager, uint32_t category, Listener* listener, uint32_t filter);
    reinterpret_cast<RegisterFn>(mem::rva(addr::Fn_RegisterListener))(manager, addr::kCategorySocialPlay, &l, 0xff);
    done = manager;
    LOG("listening for challenge messages on the %s message manager (%p)", which, reinterpret_cast<void*>(manager));
}

} // namespace

void registerClient() { registerOn(addr::ClientGameContext, g_client, g_clientManager, "client"); }
void registerServer() { registerOn(addr::ServerGameContext, g_server, g_serverManager, "server"); }

std::vector<Event> drain() {
    std::lock_guard<std::mutex> lock(g_m);
    std::vector<Event> out;
    out.swap(g_queue);
    return out;
}

} // namespace mecap::listener
