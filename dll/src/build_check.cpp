#include "build_check.h"

#include <windows.h>

#include <cstdio>
#include <cstring>

#include "addresses.h"
#include "log.h"
#include "mem.h"

namespace mecap::build {
namespace {

constexpr size_t kMaxTypes = 50000;

size_t typeCount() {
    uintptr_t ti = mem::readOr<uintptr_t>(mem::rva(addr::TypeInfoListHead));
    size_t n = 0;
    while (ti && n < kMaxTypes) {
        ++n;
        ti = mem::readOr<uintptr_t>(ti + 8);
    }
    return n;
}

// The class name of a TypeInfo: TypeInfo -> data -> name pointer -> string (as MECMP's
// core/typeinfo.cpp and our mec_memory.py read it).
std::string className(uintptr_t ti) {
    std::string s;
    const uintptr_t data = mem::readOr<uintptr_t>(ti);
    const uintptr_t name = data ? mem::readOr<uintptr_t>(data) : 0;
    if (name) mem::readCString(name, s);
    return s;
}

// A slot holds the expected function, or (another mod got there first) some other code we can
// chain in front of. Anything else is not this build.
bool slotOk(uintptr_t slotVa, uintptr_t fnVa, const char* what, std::string& why) {
    uintptr_t got = 0;
    if (!mem::read(mem::rva(slotVa), got)) {
        why = std::string(what) + ": slot not readable";
        return false;
    }
    if (got == mem::rva(fnVa)) return true;
    if (got && mem::isExecutable(got)) {
        LOG("build check: %s already redirected (to %p, not %p): another mod; will chain in front",
            what, reinterpret_cast<void*>(got), reinterpret_cast<void*>(mem::rva(fnVa)));
        return true;
    }
    char buf[160];
    snprintf(buf, sizeof(buf), "%s: slot holds %p, expected %p", what, reinterpret_cast<void*>(got),
             reinterpret_cast<void*>(mem::rva(fnVa)));
    why = buf;
    return false;
}

} // namespace

bool waitForEngine() {
    const DWORD start = GetTickCount();
    size_t last = 0;
    int stable = 0;
    while (GetTickCount() - start < 5 * 60 * 1000) {
        const size_t n = typeCount();
        stable = (n >= 9000 && n == last) ? stable + 1 : 0;
        if (stable >= 4) {
            LOG("engine up: %zu types", n);
            return true;
        }
        last = n;
        Sleep(250);
    }
    LOG("the engine's type list never filled (%zu types); unsupported game version?", last);
    return false;
}

bool check(std::string& why) {
    struct Ti { const char* name; uintptr_t va; };
    const Ti types[] = {{"PamReplayPlayerComponentData", addr::TI_PamReplayPlayerComponentData},
                        {"ServerCharacterEntity", addr::TI_ServerCharacterEntity},
                        {"ObjectBlueprint", addr::TI_ObjectBlueprint}};
    for (const Ti& t : types) {
        const std::string got = className(mem::rva(t.va));
        if (got != t.name) {
            why = std::string("TypeInfo ") + t.name + " reads as '" + got + "'";
            return false;
        }
    }
    if (!slotOk(addr::Slot_ServerWorldPostUpdate, addr::Fn_ServerWorldPostUpdate, "tick hook", why)) return false;
    if (!slotOk(addr::Slot_ClientReplayUpdateAll, addr::Fn_ClientReplayUpdateAll, "client updater hook", why))
        return false;
    unsigned char head[sizeof(addr::kRegisterListenerHead)] = {};
    if (!mem::read(mem::rva(addr::Fn_RegisterListener), head, sizeof(head)) ||
        memcmp(head, addr::kRegisterListenerHead, sizeof(head)) != 0) {
        why = "MessageManager_registerListener does not start with the expected bytes";
        return false;
    }
    LOG("build check: passed (3 TypeInfo, 2 hook slots, registerListener)");
    return true;
}

} // namespace mecap::build
