#pragma once
// Applying an ability now: the game's own apply(entity, value, 0) on a PamServerProgressionFlagEntity,
// called on the server game thread (docs/MEMORY.md §3, docs/DLL.md §5).
//
// Who does what:
//   * The Python client writes the progression flag (its one write path), then asks for an apply.
//     This DLL never writes a progression flag.
//   * link.cpp (its own thread) finds candidate entities with a memory scan and queues a job.
//   * The server tick hook runs the jobs: it re-reads the flag table and re-validates each entity
//     right before the call, applies only by MEMORY.md §3's rules (never to every matching
//     entity), and reads [e+0x78] back. The result says what the game shows, not what was asked.

#include <cstdint>
#include <string>
#include <vector>

namespace mecap::apply {

// Checks the entity class and the apply function on this build. False: applying stays off
// (dashes are unaffected) and `why` says why.
bool check(std::string& why);
bool enabled();

struct Request {
    uint32_t id;
    uint32_t hash;   // djb2a of the flag name
    int32_t value;
};

struct Result {
    uint32_t id;
    uint32_t hash;
    int32_t value;
    const char* result;   // applied | already | no_flag | table_mismatch | no_entity | unsafe | failed
    int matched = 0;      // entities that check this flag
    int targets = 0;      // the ones apply was (or would have been) called on
    bool live = false;    // the targets are the per-spawn instance
};

// link thread: scan once for all of these, then queue them for the game thread.
void submit(const std::vector<Request>& requests);
// server game thread, once per tick: run the queued jobs. Never blocks.
void onServerTick();
// link thread: results since the last call.
std::vector<Result> drainResults();

} // namespace mecap::apply
