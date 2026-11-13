#pragma once
// Every game address this DLL uses, as image VAs at base 0x140000000.
//
// All of them are in data/dll_addresses.json with the MECMP source line they were read from.
// The slots and TypeInfo were checked against our build on 2026-11-12 by
// tools/client/verify_dll_addresses.py (read-only, 24/24 strong checks). The functions and
// globals only got a weak check; build_check.cpp checks them again before anything is touched.

#include <cstddef>
#include <cstdint>

namespace mecap::addr {

// --- build check: TypeInfo (found by name in the engine's TypeInfo list) -----------------------
constexpr uintptr_t TypeInfoListHead = 0x14215D028; // first TypeInfo; next at +0x08
constexpr uintptr_t TI_PamReplayPlayerComponentData = 0x14286B890;
constexpr uintptr_t TI_ServerCharacterEntity = 0x1427FE1E0;
constexpr uintptr_t TI_ObjectBlueprint = 0x1427E7EB0;

// --- hooks: one vtable slot each, and the function it holds on this build -----------------------
// ServerGameWorld vtable +0x28, postUpdate: once per tick on the server game thread.
constexpr uintptr_t Slot_ServerWorldPostUpdate = 0x141B42D28;
constexpr uintptr_t Fn_ServerWorldPostUpdate = 0x143341EE0;
// Client replay updater vtable (0x141C49190) +0x10, updateAll: per frame on the client thread.
constexpr uintptr_t Slot_ClientReplayUpdateAll = 0x141C491A0;
constexpr uintptr_t Fn_ClientReplayUpdateAll = 0x14394DA40;

// --- the message system -------------------------------------------------------------------------
// MessageManager_registerListener(manager, category, listener, 0xff). Its first bytes, read on
// 2026-11-12: 48 8B 09 EB 0B (mov rcx,[rcx]; jmp +0x0B), a short thunk.
constexpr uintptr_t Fn_RegisterListener = 0x142A3AD40;
constexpr unsigned char kRegisterListenerHead[] = {0x48, 0x8B, 0x09, 0xEB, 0x0B};
constexpr uintptr_t ClientGameContext = 0x142401CB0; // *ptr + 0x10 = client message manager
constexpr uintptr_t ServerGameContext = 0x14253D670; // *ptr + 0x10 = server message manager
constexpr size_t Context_MessageManager = 0x10;

// --- messages (header: +0x08 category, +0x0C type; type = djb2a of the class name) --------------
constexpr size_t Msg_Category = 0x08, Msg_Type = 0x0C;
constexpr uint32_t kCategorySocialPlay = 0x54776FC6;     // PamSocialPlay*Message
constexpr uint32_t kTypeNamedChallengeFinished = 0xD71D027F;
constexpr uint32_t kTypeNamedChallengeStarted = 0xC164590C;
constexpr uint32_t kTypeNamedChallengeCancelled = 0x9A9A27C6;
constexpr uint32_t kTypeNamedChallengeActivated = 0xB7633230;
// NamedChallengeFinished fields (MECMP runs.cpp; seen in game 2026-11-12, docs/DLL.md §11a)
constexpr size_t Fin_ContentId = 0x48, Fin_Set = 0x4C, Fin_Delta = 0x50, Fin_HadRecord = 0x54,
                 Fin_Record = 0x58, Fin_NewRecord = 0x60;
constexpr size_t Msg_ContentId = 0x48; // Started, Cancelled, Activated: the same field

} // namespace mecap::addr
