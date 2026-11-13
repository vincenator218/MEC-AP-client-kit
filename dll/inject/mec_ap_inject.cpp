// mec_ap_inject: loads mec_ap.dll into the running game with LoadLibraryW, and says what it did.
//
//   mec_ap_inject.exe [path\to\mec_ap.dll]     (default: mec_ap.dll next to this exe)
//
// It can be started before the game. Starting the game runs MirrorsEdgeCatalyst.exe twice: the
// EA activation process first, then the game under the same name. Only the game loads the
// engine's modules, so a MirrorsEdgeCatalyst.exe counts as the game once
// Engine.BuildInfo_Win64_retail.dll is loaded in it and it has a visible window. This is the
// approach of MECMP's tools/inject/mecmp_inject.cpp (MIT). If the game runs as administrator,
// run this as administrator too.

#include <windows.h>
#include <tlhelp32.h>

#include <cstdio>
#include <cwchar>
#include <string>

namespace {

const wchar_t* kGame = L"MirrorsEdgeCatalyst.exe";
const wchar_t* kEngineModule = L"Engine.BuildInfo_Win64_retail.dll";
const wchar_t* kDll = L"mec_ap.dll";

bool hasModule(DWORD pid, const wchar_t* name, std::wstring* path = nullptr) {
    HANDLE snap = INVALID_HANDLE_VALUE;
    for (int i = 0; i < 10 && snap == INVALID_HANDLE_VALUE; ++i) {
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
        if (snap == INVALID_HANDLE_VALUE && GetLastError() != ERROR_BAD_LENGTH) return false;
    }
    if (snap == INVALID_HANDLE_VALUE) return false;
    MODULEENTRY32W me{sizeof(me)};
    bool found = false;
    for (BOOL ok = Module32FirstW(snap, &me); ok && !found; ok = Module32NextW(snap, &me)) {
        if (_wcsicmp(me.szModule, name) == 0) {
            found = true;
            if (path) *path = me.szExePath;
        }
    }
    CloseHandle(snap);
    return found;
}

struct WindowSearch { DWORD pid; bool found; };
BOOL CALLBACK onWindow(HWND w, LPARAM p) {
    auto* s = reinterpret_cast<WindowSearch*>(p);
    DWORD pid = 0;
    GetWindowThreadProcessId(w, &pid);
    if (pid == s->pid && IsWindowVisible(w)) {
        s->found = true;
        return FALSE;
    }
    return TRUE;
}

// The game's process id, or 0. `seenActivation` is set when only the activation process is up.
DWORD findGame(bool& seenActivation) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W pe{sizeof(pe)};
    DWORD game = 0;
    for (BOOL ok = Process32FirstW(snap, &pe); ok && !game; ok = Process32NextW(snap, &pe)) {
        if (_wcsicmp(pe.szExeFile, kGame) != 0) continue;
        WindowSearch s{pe.th32ProcessID, false};
        EnumWindows(&onWindow, reinterpret_cast<LPARAM>(&s));
        if (hasModule(pe.th32ProcessID, kEngineModule) && s.found) game = pe.th32ProcessID;
        else seenActivation = true;
    }
    CloseHandle(snap);
    return game;
}

int fail(const wchar_t* what) {
    wprintf(L"FAILED: %ls (error %lu).\n", what, GetLastError());
    if (GetLastError() == ERROR_ACCESS_DENIED) wprintf(L"The game may run as administrator: run this as administrator too.\n");
    wprintf(L"Press Enter to close.\n");
    getchar();
    return 1;
}

int inject(DWORD pid, const std::wstring& dll) {
    HANDLE proc = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION |
                                  PROCESS_VM_WRITE | PROCESS_VM_READ,
                              FALSE, pid);
    if (!proc) return fail(L"OpenProcess");
    const size_t bytes = (dll.size() + 1) * sizeof(wchar_t);
    void* remote = VirtualAllocEx(proc, nullptr, bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote) return fail(L"VirtualAllocEx");
    if (!WriteProcessMemory(proc, remote, dll.c_str(), bytes, nullptr)) return fail(L"WriteProcessMemory");
    // kernel32 is mapped at the same address in every process of a boot session.
    auto loadLib = reinterpret_cast<LPTHREAD_START_ROUTINE>(
        reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW")));
    HANDLE thread = CreateRemoteThread(proc, nullptr, 0, loadLib, remote, 0, nullptr);
    if (!thread) return fail(L"CreateRemoteThread");
    if (WaitForSingleObject(thread, 30000) != WAIT_OBJECT_0) {
        wprintf(L"FAILED: LoadLibraryW did not return within 30 s.\n");
        return 1;
    }
    CloseHandle(thread);
    VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
    CloseHandle(proc);
    // The thread's exit code is only the low 32 bits of the HMODULE: ask the game instead.
    if (!hasModule(pid, kDll)) {
        wprintf(L"FAILED: the game did not load %ls. Is the file there, and not blocked by an antivirus?\n", dll.c_str());
        return 1;
    }
    wprintf(L"Loaded %ls into the game (pid %lu).\nSee mec_ap.log next to the DLL; it says \"ready\" once the hooks are in.\n",
            dll.c_str(), pid);
    return 0;
}

} // namespace

int wmain(int argc, wchar_t** argv) {
    std::wstring dll;
    if (argc > 1) {
        dll = argv[1];
    } else {
        wchar_t self[MAX_PATH] = {};
        GetModuleFileNameW(nullptr, self, MAX_PATH);
        dll = self;
        dll = dll.substr(0, dll.find_last_of(L'\\') + 1) + kDll;
    }
    wchar_t full[MAX_PATH] = {};
    GetFullPathNameW(dll.c_str(), MAX_PATH, full, nullptr);
    dll = full;
    if (GetFileAttributesW(dll.c_str()) == INVALID_FILE_ATTRIBUTES) {
        wprintf(L"FAILED: %ls not found.\n", dll.c_str());
        return 1;
    }
    wprintf(L"Waiting for Mirror's Edge Catalyst...\n");
    bool saidActivation = false;
    DWORD pid = 0;
    for (;;) {
        bool activation = false;
        pid = findGame(activation);
        if (pid) break;
        if (activation && !saidActivation) {
            wprintf(L"The activation window is up; waiting for the game itself...\n");
            saidActivation = true;
        }
        Sleep(500);
    }
    if (hasModule(pid, kDll)) {
        wprintf(L"mec_ap.dll is already loaded in the game (pid %lu). Nothing to do.\n", pid);
        return 0;
    }
    Sleep(3000); // let the game finish starting; the DLL waits for the engine itself too
    const int rc = inject(pid, dll);
    if (rc == 0) Sleep(5000);
    return rc;
}
