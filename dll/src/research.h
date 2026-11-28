#pragma once
// Research mode: log every engine message the DLL can hear, to find the one a checkpoint reload
// sends (docs/DLL.md §11g). Off unless a file named mec_ap_research.txt sits next to mec_ap.dll.
//
// It registers one more listener on every candidate category (research_names.h, generated from
// the game's message class names) on both message managers. onMessage only counts and copies a
// few bytes into a queue; the file is written from the link thread (flush). Each message type is
// logged in full for its first occurrences, then at most once a second, so a frequent message
// cannot flood the log, and a rare one (a reload) is never missed.
//
// It never sends a message or calls anything but MessageManager_registerListener.

#include <cstdint>

namespace mecap::research {

bool enabled();                 // the switch file was there at startup
void init();                    // reads the switch; opens mec_ap_messages.log when on
void registerOn(uintptr_t manager, const char* which);   // from listener::registerOn, game thread
void flush();                   // from the link thread, about 10 times a second

} // namespace mecap::research
