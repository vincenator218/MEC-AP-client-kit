#pragma once
// Waits for the engine, then checks this is the game build the addresses were made for.
// Nothing is hooked unless every check passes.

#include <string>

namespace mecap::build {

// Blocks until the engine's TypeInfo list has filled (up to 5 minutes). False: it never did.
bool waitForEngine();
// True when every check passes; `why` names the first one that did not.
bool check(std::string& why);

} // namespace mecap::build
