#pragma once
// Safe memory access inside the game process, and the one way this DLL changes game memory.
//
// Reads go through ReadProcessMemory on our own process, so a bad pointer is a failed read, not
// a crash (the same approach as MECMP's src/core/mem.h). The only writes are vtable slot swaps
// (patchPointer); no game code is ever changed.

#include <windows.h>

#include <cstddef>
#include <cstdint>
#include <string>

namespace mecap::mem {

constexpr uintptr_t kImageBase = 0x140000000; // every address in addresses.h is a VA at this base

inline uintptr_t moduleBase() {
    static const uintptr_t base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    return base;
}

// An image VA (as in addresses.h and data/dll_addresses.json) -> its address in the running game.
inline uintptr_t rva(uintptr_t va) { return va - kImageBase + moduleBase(); }

inline bool read(uintptr_t addr, void* out, size_t size) {
    if (addr < 0x10000) return false;
    SIZE_T got = 0;
    return ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<LPCVOID>(addr), out, size, &got) && got == size;
}

template <class T> inline bool read(uintptr_t addr, T& out) { return read(addr, &out, sizeof(T)); }

template <class T> inline T readOr(uintptr_t addr, T fallback = T{}) {
    T v{};
    return read(addr, v) ? v : fallback;
}

// A NUL-terminated string of at most `max` bytes.
inline bool readCString(uintptr_t addr, std::string& out, size_t max = 96) {
    out.clear();
    char c = 0;
    for (size_t i = 0; i < max; ++i) {
        if (!read(addr + i, c)) return false;
        if (!c) return true;
        out.push_back(c);
    }
    return true;
}

inline bool isExecutable(uintptr_t addr) {
    MEMORY_BASIC_INFORMATION mbi{};
    if (!VirtualQuery(reinterpret_cast<void*>(addr), &mbi, sizeof(mbi))) return false;
    return mbi.State == MEM_COMMIT &&
           (mbi.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY));
}

// Swap one pointer-sized slot (a vtable entry). One aligned 8-byte store: on x64 a concurrent call
// through the slot sees either the old or the new pointer, never half of each.
inline bool patchPointer(uintptr_t slot, uintptr_t value) {
    DWORD prot = 0;
    if (!VirtualProtect(reinterpret_cast<void*>(slot), sizeof(uintptr_t), PAGE_READWRITE, &prot)) return false;
    *reinterpret_cast<volatile uintptr_t*>(slot) = value;
    DWORD tmp = 0;
    VirtualProtect(reinterpret_cast<void*>(slot), sizeof(uintptr_t), prot, &tmp);
    FlushInstructionCache(GetCurrentProcess(), nullptr, 0);
    return true;
}

} // namespace mecap::mem
