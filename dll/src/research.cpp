#include "research.h"

#include <windows.h>
#include <share.h>

#include <cstdio>
#include <cstring>
#include <cwchar>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "addresses.h"
#include "log.h"
#include "mem.h"
#include "research_names.h"

namespace mecap::research {
namespace {

constexpr int kFullCount = 8;          // the first occurrences of a type are all logged
constexpr DWORD kRepeatMs = 1000;      // after that, at most one line per type per second
constexpr size_t kPayload = 0x80;      // bytes copied from each logged message (read safely)
constexpr size_t kQueueMax = 20000;
constexpr int kFrames = 48;            // return addresses captured for the stack types below

constexpr uint32_t djb2a(const char* s) {
    uint32_t h = 5381;
    while (*s) h = (h * 33) ^ static_cast<uint8_t>(*s++);
    return h;
}

// The messages a checkpoint reload sends (docs/DLL.md §11g). Each one's call stack is logged, to
// find the game function the pause menu's "reload checkpoint" calls. They are rare, so every
// occurrence is logged (no rate limit). ServerLoadLevelMessageBase is not in research_names.h
// (its name does not end in "Message"); it was named through its vtable.
constexpr uint32_t kStackTypes[] = {
    djb2a("NetworkPamUINotificationResponseMessage"),
    djb2a("PamplonaGamePausedMessage"),
    djb2a("ServerRoundResetMessage"),
    djb2a("ServerLoadLevelMessageBase"),
    djb2a("ServerUnloadLevelMessage"),
};
static_assert(djb2a("ServerRoundResetMessage") == 0x4BB8DE5C, "djb2a");
static_assert(djb2a("ServerLoadLevelMessageBase") == 0xF8429A0E, "djb2a");

bool wantsStack(uint32_t type) {
    for (uint32_t t : kStackTypes)
        if (t == type) return true;
    return false;
}

bool g_on = false;
FILE* g_file = nullptr;

struct Listener {
    void* const* vtbl;
};
void onMessage(Listener* self, const void* message);
uint16_t priority(Listener*) { return 0; }
void* const g_vtbl[2] = {reinterpret_cast<void*>(&onMessage), reinterpret_cast<void*>(&priority)};
Listener g_client{g_vtbl}, g_server{g_vtbl};

struct Seen {
    uint64_t count = 0;
    uint64_t skipped = 0;              // not logged since the last line (rate limit)
    DWORD lastLogged = 0;
};
struct Record {
    DWORD tick;
    SYSTEMTIME time;
    char side;                         // 'C' client manager, 'S' server manager
    uint32_t category, type;
    uint64_t count, skipped;
    uint32_t got;                      // payload bytes read
    uint8_t payload[kPayload];
    DWORD thread;                      // the thread that dispatched it
    uint16_t frames;                   // stack entries captured (stack types only)
    void* stack[kFrames];
};

std::mutex g_m;
std::unordered_map<uint64_t, Seen> g_seen;   // (side, category, type) -> counts
std::vector<Record> g_queue;
uint64_t g_dropped = 0;

const char* nameOf(const Name* table, size_t n, uint32_t hash) {
    for (size_t i = 0; i < n; ++i)
        if (table[i].hash == hash) return table[i].name;
    return nullptr;
}

void onMessage(Listener* self, const void* message) {
    const auto m = reinterpret_cast<uintptr_t>(message);
    // The header is always there (the manager just read the category from it): copy it directly,
    // as listener.cpp does. Only the logged payload is read the safe (slower) way.
    uint32_t category = 0, type = 0;
    memcpy(&category, reinterpret_cast<const void*>(m + addr::Msg_Category), 4);
    memcpy(&type, reinterpret_cast<const void*>(m + addr::Msg_Type), 4);
    const char side = self == &g_client ? 'C' : 'S';
    const DWORD now = GetTickCount();
    const bool stack = wantsStack(type);
    uint64_t count = 0, skipped = 0;
    {
        std::lock_guard<std::mutex> lock(g_m);
        Seen& s = g_seen[(uint64_t(side) << 56) ^ (uint64_t(category) << 32) ^ type];
        count = ++s.count;
        if (!stack && count > kFullCount && now - s.lastLogged < kRepeatMs) {
            ++s.skipped;
            return;
        }
        skipped = s.skipped;
        s.skipped = 0;
        s.lastLogged = now;
        if (g_queue.size() >= kQueueMax) {
            ++g_dropped;
            return;
        }
    }
    Record r{};
    // Captured first; frame 0 is onMessage's caller (the manager's dispatch). Only return
    // addresses are kept: nothing is read through them.
    if (stack) r.frames = RtlCaptureStackBackTrace(1, kFrames, r.stack, nullptr);
    r.thread = GetCurrentThreadId();
    r.tick = now;
    GetLocalTime(&r.time);
    r.side = side;
    r.category = category;
    r.type = type;
    r.count = count;
    r.skipped = skipped;
    // A message can be smaller than kPayload: read in 16-byte steps and stop at the first failure.
    for (r.got = 0; r.got < kPayload && mem::read(m + r.got, r.payload + r.got, 16); r.got += 16) {}
    std::lock_guard<std::mutex> lock(g_m);
    g_queue.push_back(r);
}

// One return address: an image VA for the game exe (the same base as addresses.h), else
// module+offset.
void writeFrame(int i, void* p) {
    const auto a = reinterpret_cast<uintptr_t>(p);
    HMODULE mod = nullptr;
    if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(p), &mod) && mod) {
        const auto base = reinterpret_cast<uintptr_t>(mod);
        if (base == mem::moduleBase()) {
            fprintf(g_file, "    #%02d 0x%llX\n", i, static_cast<unsigned long long>(a - base + mem::kImageBase));
            return;
        }
        wchar_t path[MAX_PATH] = {};
        GetModuleFileNameW(mod, path, MAX_PATH);
        const wchar_t* name = wcsrchr(path, L'\\');
        fprintf(g_file, "    #%02d %ls+0x%llX\n", i, name ? name + 1 : path, static_cast<unsigned long long>(a - base));
        return;
    }
    fprintf(g_file, "    #%02d 0x%llX (no module)\n", i, static_cast<unsigned long long>(a));
}

void writeRecord(const Record& r) {
    const char* cat = nameOf(kCategories, std::size(kCategories), r.category);
    const char* typ = nameOf(kTypes, std::size(kTypes), r.type);
    fprintf(g_file, "[%02d:%02d:%02d.%03d] %c %-28s %-52s #%llu", r.time.wHour, r.time.wMinute,
            r.time.wSecond, r.time.wMilliseconds, r.side, cat ? cat : "?", typ ? typ : "?",
            static_cast<unsigned long long>(r.count));
    if (!cat) fprintf(g_file, " cat=%08X", r.category);
    if (!typ) fprintf(g_file, " type=%08X", r.type);
    if (r.skipped) fprintf(g_file, " (+%llu not logged)", static_cast<unsigned long long>(r.skipped));
    fprintf(g_file, " tid=%lu\n", r.thread);
    for (uint32_t off = 0; off < r.got; off += 16) {
        fprintf(g_file, "    +%02X ", off);
        for (int i = 0; i < 16; ++i) fprintf(g_file, "%02X ", r.payload[off + i]);
        fputc(' ', g_file);
        for (int i = 0; i < 16; ++i) {
            const uint8_t c = r.payload[off + i];
            fputc(c >= 0x20 && c < 0x7F ? c : '.', g_file);
        }
        fputc('\n', g_file);
    }
    if (r.frames) {
        fprintf(g_file, "  stack (%u frames):\n", r.frames);
        for (int i = 0; i < r.frames; ++i) writeFrame(i, r.stack[i]);
    }
}

} // namespace

bool enabled() { return g_on; }

void init() {
    const std::wstring folder = log::dllFolder();
    g_on = GetFileAttributesW((folder + L"mec_ap_research.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (!g_on) return;
    const std::wstring path = folder + L"mec_ap_messages.log", prev = folder + L"mec_ap_messages.prev.log";
    MoveFileExW(path.c_str(), prev.c_str(), MOVEFILE_REPLACE_EXISTING);
    g_file = _wfsopen(path.c_str(), L"w", _SH_DENYWR);
    LOG("research: on (mec_ap_research.txt found): logging every message to mec_ap_messages.log, "
        "with call stacks for the checkpoint-reload messages");
}

void registerOn(uintptr_t manager, const char* which) {
    if (!g_on || !g_file) return;
    Listener* l = which[0] == 'c' ? &g_client : &g_server;
    using RegisterFn = char (*)(uintptr_t manager, uint32_t category, Listener* listener, uint32_t filter);
    const auto fn = reinterpret_cast<RegisterFn>(mem::rva(addr::Fn_RegisterListener));
    for (const Name& c : kCategories) fn(manager, c.hash, l, 0xff);
    LOG("research: listening on %zu candidate categories on the %s message manager", std::size(kCategories), which);
}

void flush() {
    if (!g_on || !g_file) return;
    std::vector<Record> batch;
    uint64_t dropped = 0;
    {
        std::lock_guard<std::mutex> lock(g_m);
        batch.swap(g_queue);
        dropped = g_dropped;
        g_dropped = 0;
    }
    for (const Record& r : batch) writeRecord(r);
    if (dropped) fprintf(g_file, "(%llu messages dropped: queue full)\n", static_cast<unsigned long long>(dropped));
    if (!batch.empty() || dropped) fflush(g_file);
}

} // namespace mecap::research
