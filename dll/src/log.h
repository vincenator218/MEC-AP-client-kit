#pragma once
// mec_ap.log next to the DLL. Thread-safe; each line is flushed so a crash keeps the log.

#include <string>

namespace mecap::log {

// The folder mec_ap.dll was loaded from, with a trailing backslash.
const std::wstring& dllFolder();
void init(void* dllModule);
void write(const char* fmt, ...);

} // namespace mecap::log

#define LOG(...) ::mecap::log::write(__VA_ARGS__)
