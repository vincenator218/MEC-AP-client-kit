#include "apply.h"

#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cstring>
#include <mutex>

#include "addresses.h"
#include "log.h"
#include "mem.h"

namespace mecap::apply {
namespace {

// The apply function's first bytes, read from the running game on 2026-11-13. They match the
// disassembly in FINDINGS §63: save registers, then `mov eax,[rcx+18]; shr eax,3` (the enabled bit).
constexpr unsigned char kApplyHead[] = {0x48, 0x89, 0x5C, 0x24, 0x10, 0x57, 0x48, 0x83, 0xEC, 0x20, 0x8B, 0x41,
                                        0x18, 0x41, 0x0F, 0xB6, 0xF8, 0x48, 0x89, 0xCB, 0xC1, 0xE8, 0x03, 0xA8};

std::atomic<bool> g_enabled{false};
std::atomic<bool> g_pending{false};

struct Job {
    Request req;
    std::vector<uintptr_t> candidates; // entities of the class that checked this flag at scan time
};
std::mutex g_jobsM, g_resultsM;
std::vector<Job> g_jobs;
std::vector<Result> g_results;

// --------------------------------------------------------------------------- reading the game
// Every read is a safe read (mem.h): a freed entity is a failed check, never a crash.

uintptr_t findNode(uint32_t hash) {
    const uintptr_t table = mem::readOr<uintptr_t>(mem::rva(addr::FlagTable));
    if (!table) return 0;
    const uintptr_t buckets = mem::readOr<uintptr_t>(table + addr::Table_Buckets);
    const uint32_t count = mem::readOr<uint32_t>(table + addr::Table_Count);
    if (!buckets || count <= 16 || count >= 100000) return 0;
    uintptr_t n = mem::readOr<uintptr_t>(buckets + (hash % count) * 8);
    for (int steps = 0; n && steps < 10000; ++steps) {
        if (mem::readOr<uint32_t>(n + addr::Node_Hash, ~hash) == hash) return n;
        n = mem::readOr<uintptr_t>(n + addr::Node_Next);
    }
    return 0;
}

uintptr_t entityVtable() { return mem::rva(addr::VT_ProgressionFlagEntity); }

// Every 8-aligned qword in the game's private read-write memory that holds the entity vtable.
// About 1100 hits in a level (MEMORY.md §3). The scan buffer itself is skipped: it holds copies.
std::vector<uintptr_t> scanEntities() {
    const uintptr_t vt = entityVtable();
    constexpr size_t kChunk = 1 << 20;
    std::vector<uint64_t> buf(kChunk / 8);
    const uintptr_t bufLo = reinterpret_cast<uintptr_t>(buf.data()), bufHi = bufLo + kChunk;
    std::vector<uintptr_t> out;
    SYSTEM_INFO si{};
    GetSystemInfo(&si);
    uintptr_t a = reinterpret_cast<uintptr_t>(si.lpMinimumApplicationAddress);
    const uintptr_t end = reinterpret_cast<uintptr_t>(si.lpMaximumApplicationAddress);
    MEMORY_BASIC_INFORMATION mbi{};
    while (a < end && VirtualQuery(reinterpret_cast<void*>(a), &mbi, sizeof(mbi))) {
        const uintptr_t base = reinterpret_cast<uintptr_t>(mbi.BaseAddress), top = base + mbi.RegionSize;
        if (mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE && (mbi.Protect & 0xFF) == PAGE_READWRITE &&
            !(mbi.Protect & PAGE_GUARD)) {
            for (uintptr_t p = base; p < top;) {
                const size_t want = static_cast<size_t>(std::min<uintptr_t>(kChunk, top - p));
                SIZE_T got = 0;
                ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<LPCVOID>(p), buf.data(), want, &got);
                for (size_t i = 0; i < got / 8; ++i) {
                    const uintptr_t at = p + i * 8;
                    if (buf[i] == vt && !(at >= bufLo && at < bufHi)) out.push_back(at);
                }
                // A short read stopped at an unreadable page: step past that page, not the chunk.
                p += (got == want) ? want : (got & ~static_cast<SIZE_T>(0xFFF)) + 0x1000;
            }
        }
        a = top;
    }
    return out;
}

struct Entity {
    uintptr_t at;
    uint32_t flags;
    uintptr_t data;
};

// Still an entity of the class, still checking this flag. Called again right before each call.
bool readEntity(uintptr_t e, uintptr_t identity, Entity& out) {
    if (mem::readOr<uintptr_t>(e) != entityVtable()) return false;
    if (mem::readOr<uintptr_t>(e + addr::Ent_Identity) != identity) return false;
    out.at = e;
    if (!mem::read(e + addr::Ent_Flags, out.flags)) return false;
    out.data = mem::readOr<uintptr_t>(e + addr::Ent_Data);
    return true;
}

// ---------------------------------------------------------------------------- the call itself
using ApplyFn = void (*)(uintptr_t entity, int32_t value, bool force);

// No C++ objects in here, so structured exception handling is allowed. A fault inside the game's
// apply is caught so the game keeps running, and applying is switched off for this session.
bool callApply(uintptr_t entity, int32_t value) {
    __try {
        reinterpret_cast<ApplyFn>(mem::rva(addr::Fn_Apply))(entity, value, false);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// One job, on the server game thread.
Result run(const Job& j) {
    Result r{j.req.id, j.req.hash, j.req.value, "failed"};
    const uintptr_t node = findNode(j.req.hash);
    if (!node) {
        r.result = "no_flag";
        return r;
    }
    int32_t tableValue = 0;
    if (!mem::read(node + addr::Node_Value, tableValue)) return r;
    if (tableValue != j.req.value) { // the client writes first; if the game disagrees, do nothing
        r.result = "table_mismatch";
        return r;
    }
    // The pointer stored in the node, not the node's address (the CE prototype's readQword(n+0x10)).
    const uintptr_t identity = mem::readOr<uintptr_t>(node + addr::Node_Identity);
    if (!identity) {
        r.result = "no_flag";
        return r;
    }
    std::vector<Entity> matched;
    for (uintptr_t c : j.candidates) {
        Entity e{};
        if (readEntity(c, identity, e)) matched.push_back(e);
    }
    r.matched = static_cast<int>(matched.size());

    // MEMORY.md §3: (1) the per-spawn instance if there is one; (2) otherwise, with at most 3
    // entities, the enabled ones whose data pointer no other entity of this flag shares;
    // (3) otherwise nothing: many entities means world objects, and calling those crashed the game.
    std::vector<Entity> targets;
    for (const Entity& e : matched)
        if ((e.flags & addr::kEntLive) && (e.flags & addr::kEntEnabled)) targets.push_back(e);
    r.live = !targets.empty();
    if (targets.empty() && matched.size() <= 3) {
        for (const Entity& e : matched) {
            const auto same = std::count_if(matched.begin(), matched.end(),
                                            [&](const Entity& o) { return o.data == e.data; });
            if ((e.flags & addr::kEntEnabled) && same == 1) targets.push_back(e);
        }
    }
    if (targets.empty() || targets.size() > 3) {
        r.result = matched.empty() ? "no_entity" : "unsafe";
        return r;
    }
    r.targets = static_cast<int>(targets.size());

    int ok = 0, changed = 0;
    for (const Entity& t : targets) {
        Entity again{};
        if (!readEntity(t.at, identity, again)) continue; // gone since the census: count as failed
        int32_t last = 0;
        if (!mem::read(t.at + addr::Ent_LastValue, last)) continue;
        if (last == j.req.value) { // the entity already holds it (it re-read the flag at a respawn)
            ++ok;
            continue;
        }
        if (!callApply(t.at, j.req.value)) {
            g_enabled = false;
            r.result = "fault";
            return r;
        }
        if (mem::readOr<int32_t>(t.at + addr::Ent_LastValue, ~j.req.value) == j.req.value) {
            ++ok;
            ++changed;
        }
    }
    r.result = ok != static_cast<int>(targets.size()) ? "failed" : changed ? "applied" : "already";
    return r;
}

std::string className(uintptr_t ti) {
    std::string s;
    const uintptr_t data = mem::readOr<uintptr_t>(ti);
    const uintptr_t name = data ? mem::readOr<uintptr_t>(data) : 0;
    if (name) mem::readCString(name, s);
    return s;
}

} // namespace

bool check(std::string& why) {
    // The vtable's slot 0 is getType: `lea rax,[rip+rel32]; ret` -> the class's TypeInfo.
    const uintptr_t getType = mem::readOr<uintptr_t>(entityVtable());
    unsigned char code[8] = {};
    if (!getType || !mem::read(getType, code, sizeof(code)) || code[0] != 0x48 || code[1] != 0x8D ||
        code[2] != 0x05 || code[7] != 0xC3) {
        why = "the progression flag entity's vtable does not start with getType";
        return false;
    }
    int32_t rel = 0;
    memcpy(&rel, code + 3, 4);
    const uintptr_t ti = getType + 7 + static_cast<intptr_t>(rel);
    const std::string name = className(ti);
    if (ti != mem::rva(addr::TI_PamServerProgressionFlagEntity) || name != "PamServerProgressionFlagEntity") {
        why = "the progression flag entity's class reads as '" + name + "'";
        return false;
    }
    unsigned char head[sizeof(kApplyHead)] = {};
    if (!mem::read(mem::rva(addr::Fn_Apply), head, sizeof(head)) || memcmp(head, kApplyHead, sizeof(head)) != 0) {
        why = "the apply function does not start with the expected bytes";
        return false;
    }
    g_enabled = true;
    LOG("apply: check passed (PamServerProgressionFlagEntity, apply function)");
    return true;
}

bool enabled() { return g_enabled; }

void submit(const std::vector<Request>& requests) {
    if (requests.empty()) return;
    if (!g_enabled) {
        std::lock_guard<std::mutex> lock(g_resultsM);
        for (const Request& q : requests) g_results.push_back({q.id, q.hash, q.value, "disabled"});
        return;
    }
    const DWORD t0 = GetTickCount();
    const std::vector<uintptr_t> all = scanEntities();
    std::vector<Job> jobs;
    for (const Request& q : requests) {
        Job j{q, {}};
        if (const uintptr_t node = findNode(q.hash)) {
            const uintptr_t identity = mem::readOr<uintptr_t>(node + addr::Node_Identity);
            for (uintptr_t e : all)
                if (identity && mem::readOr<uintptr_t>(e + addr::Ent_Identity) == identity) j.candidates.push_back(e);
        }
        jobs.push_back(std::move(j));
    }
    LOG("apply: scanned %zu flag entities in %lu ms for %zu request(s)", all.size(), GetTickCount() - t0,
        requests.size());
    std::lock_guard<std::mutex> lock(g_jobsM);
    for (Job& j : jobs) g_jobs.push_back(std::move(j));
    g_pending = true;
}

void onServerTick() {
    if (!g_pending.load(std::memory_order_relaxed)) return;
    std::vector<Job> jobs;
    {
        std::unique_lock<std::mutex> lock(g_jobsM, std::try_to_lock); // never wait on the game thread
        if (!lock.owns_lock()) return;
        jobs.swap(g_jobs);
        g_pending = false;
    }
    std::vector<Result> results;
    for (const Job& j : jobs) results.push_back(g_enabled ? run(j) : Result{j.req.id, j.req.hash, j.req.value, "disabled"});
    std::lock_guard<std::mutex> lock(g_resultsM);
    for (const Result& r : results) g_results.push_back(r);
}

std::vector<Result> drainResults() {
    std::lock_guard<std::mutex> lock(g_resultsM);
    std::vector<Result> out;
    out.swap(g_results);
    return out;
}

} // namespace mecap::apply
