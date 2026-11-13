#include "log.h"

#include <windows.h>
#include <share.h>

#include <cstdarg>
#include <cstdio>
#include <mutex>

namespace mecap::log {
namespace {
std::wstring g_folder;
std::mutex g_m;
FILE* g_file = nullptr;
} // namespace

const std::wstring& dllFolder() { return g_folder; }

void init(void* dllModule) {
    wchar_t path[MAX_PATH] = {};
    GetModuleFileNameW(static_cast<HMODULE>(dllModule), path, MAX_PATH);
    g_folder = path;
    g_folder.resize(g_folder.find_last_of(L'\\') + 1);
    // Keep one previous log, as MECMP does: a crash report usually needs the run before.
    const std::wstring logPath = g_folder + L"mec_ap.log", prev = g_folder + L"mec_ap.prev.log";
    MoveFileExW(logPath.c_str(), prev.c_str(), MOVEFILE_REPLACE_EXISTING);
    g_file = _wfsopen(logPath.c_str(), L"w", _SH_DENYWR);
}

void write(const char* fmt, ...) {
    SYSTEMTIME t;
    GetLocalTime(&t);
    char line[1024];
    int n = snprintf(line, sizeof(line), "[%02d:%02d:%02d.%03d] ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_list args;
    va_start(args, fmt);
    vsnprintf(line + n, sizeof(line) - n, fmt, args);
    va_end(args);
    std::lock_guard<std::mutex> lock(g_m);
    if (!g_file) return;
    fputs(line, g_file);
    fputc('\n', g_file);
    fflush(g_file);
}

} // namespace mecap::log
