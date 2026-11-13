#pragma once
// Our message listener: told by the game's message managers about every PamSocialPlay* message,
// it turns named-challenge Started / Cancelled / Finished into events for link.cpp.
//
// onMessage runs on whichever game thread dispatches (client or server). It only copies a few
// fields and queues them; no I/O, no waiting on anything slow.

#include <cstdint>
#include <vector>

namespace mecap::listener {

enum class Kind : uint8_t { Started, Cancelled, Finished };

struct Event {
    Kind kind;
    uint32_t contentId;
    int64_t runCs = 0;      // Finished: this run's time, hundredths of a second
    int64_t recordCs = 0;   // Finished: the record field as sent
    int32_t deltaCs = 0;
    uint32_t set = 0;
    bool hadRecord = false, newRecord = false;
};

// Called from the hooks on each game thread: registers with that thread's message manager once
// its context exists. Cheap once registered.
void registerClient();
void registerServer();

// Everything queued since the last call (called from link.cpp's thread).
std::vector<Event> drain();

} // namespace mecap::listener
