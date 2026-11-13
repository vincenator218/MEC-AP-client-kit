#pragma once
// Two per-frame hooks, used only to register the listener from the game's own threads.

namespace mecap::hooks {

// Swaps the tick and client-updater slots. False: nothing was changed.
bool install();

} // namespace mecap::hooks
