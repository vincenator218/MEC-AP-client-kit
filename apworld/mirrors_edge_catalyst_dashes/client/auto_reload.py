"""
Reloading the checkpoint by itself, so a new Dash Unlock shows on the map (docs/DLL.md §11e: only a
checkpoint reload refreshes it, not fast travel or a death).

What the map is missing is remembered: each Dash Unlock written since the last checkpoint reload,
and the first time the hard lock or the activity hiding was put in place. When the player leaves a
dash (cancels it, or finishes it), and something is missing, the client asks mec_ap.dll for one
reload (DllLink.reload: the game's own "reload checkpoint", docs/DLL.md §11g). Any checkpoint
reload clears the list, the pause menu's too: the DLL reports every ServerRoundResetMessage
("round_reset", DLL 0.3.1+).

Timing: after a cancel the player is back in the city. After a finish the results screen is up:
with DLL 0.3.2+ the reload waits until the player leaves it (activity_ended,
PamOnlineEndSocialActivityMessage; a retry from the results screen sends none and starts the dash
again, which cancels the reload); with an older DLL it comes AFTER_FINISH_SEC after the finish. An unlock earned by the dash just
finished arrives after the finish (the check goes to the server and the item comes back), so
something noted within LATE_UNLOCK_SEC of leaving a dash schedules the reload too (seen in game
2026-11-25: Quite a View's 1 Star gave Birdman's unlock 0.6 s after the finish, and no reload
came). A dash started meanwhile cancels the reload. A finish replayed from the DLL's journal (an old run) never triggers one.

After a game launch: the hard lock and the activity hiding are put in place once the level has
loaded, so they only show after a reload. The dashes stream into memory over a minute or so
(2026-11-27: 5, then 14, then 22 of 22 found), so the reload waits until both are complete, then
comes SETUP_DELAY_SEC later. If they stay incomplete, it reloads anyway SETUP_PARTIAL_WAIT_SEC
after the first write, and once more if they complete after that. Never during a dash. Each of
the two is done at most once per connection to the DLL (a game launch), so a write the reload
itself causes cannot loop. (Before this, the first partial write used the one reload and 17
dashes stayed on the map.)

On by default; /auto_reload off|on, kept in Archipelago's persistent storage.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

log = logging.getLogger("Client")

STORE_CATEGORY, STORE_KEY = "mec_ap", "auto_reload"
AFTER_CANCEL_SEC = 2.0
AFTER_FINISH_SEC = 6.0
FRESH_FINISH_SEC = 30          # a finish older than this came from the journal: no reload
LATE_UNLOCK_SEC = 20           # an unlock this soon after leaving a dash still reloads
SETUP_DELAY_SEC = 3.0          # after the hard lock / hiding are complete at a game launch
SETUP_PARTIAL_WAIT_SEC = 90.0  # incomplete that long after the first write: reload anyway
AFTER_EXIT_SEC = 1.0           # after leaving a finished dash's results screen (DLL 0.3.2+)


def load_enabled() -> bool:
    try:
        import Utils
        return bool(Utils.persistent_load().get(STORE_CATEGORY, {}).get(STORE_KEY, True))
    except Exception:                                            # noqa: BLE001
        return True


def store_enabled(on: bool) -> None:
    import Utils
    Utils.persistent_store(STORE_CATEGORY, STORE_KEY, bool(on))


class AutoReload:
    def __init__(self, reload: Callable[[], Awaitable[bool]], can_reload: Callable[[], bool],
                 exit_events: Callable[[], bool] = lambda: False) -> None:
        self._reload = reload
        self._can_reload = can_reload
        self._exit_events = exit_events         # the DLL says when the player leaves a dash
        self.awaiting_exit = False              # finished a dash; the results screen is up
        self.enabled = load_enabled()
        self.missing: list[str] = []          # what the map does not show yet, in order received
        self.task: asyncio.Task | None = None
        self.in_dash = False
        self.left_at: float | None = None       # monotonic time the player last left a dash
        self.left_delay = AFTER_CANCEL_SEC      # the wait that applies to that exit
        self.setup_complete_done = False        # since the DLL connected: the reload once complete
        self.setup_partial_done = False         # ... and the fallback while still incomplete

    # ------------------------------------------------------------ what the map lacks
    def note(self, what: str) -> None:
        if what not in self.missing:
            self.missing.append(what)
        # Earned by the dash just left (or arrived right after): reload now rather than at the
        # next dash, keeping the wait that exit asked for.
        if self.awaiting_exit:
            return                                       # reload when the results screen closes
        if self.left_at is not None and not self.in_dash and (self.task is None or self.task.done()):
            since = time.monotonic() - self.left_at
            if since <= LATE_UNLOCK_SEC:
                self._schedule(max(0.0, self.left_delay - since))

    def note_setup(self, what: str, complete: bool = True) -> None:
        """The hard lock or the activity hiding was just written (a game launch). `complete`: both
        are fully in place (every dash and activity found). Reload once they are, or after a
        while if they never are."""
        if what not in self.missing:
            self.missing.append(what)
        if self.in_dash:
            return                                   # leaving the dash reloads instead
        if complete:
            if not self.setup_complete_done and self._schedule(SETUP_DELAY_SEC):
                self.setup_complete_done = True      # replaces a pending fallback
            return
        if self.setup_partial_done or (self.task is not None and not self.task.done()):
            return
        if self._schedule(SETUP_PARTIAL_WAIT_SEC):
            self.setup_partial_done = True

    def on_game_connected(self) -> None:
        """mec_ap.dll said hello: a new game launch (or the client reconnected)."""
        self.setup_complete_done = self.setup_partial_done = False

    def on_round_reset(self) -> None:
        """Any checkpoint reload: the map is up to date."""
        if self.missing:
            log.debug("Checkpoint reloaded: the map now shows %s.", ", ".join(self.missing))
        self.missing.clear()
        self.cancel()

    # ------------------------------------------------------------ dash events
    def on_dash_started(self) -> None:
        self.in_dash = True
        self.awaiting_exit = False
        self.left_at = None
        self.cancel()

    def on_dash_left(self, finished: bool, finish_time: float | None = None) -> None:
        self.in_dash = False
        if finished and finish_time is not None and time.time() - finish_time > FRESH_FINISH_SEC:
            return                                   # an old run sent again from the journal
        if finished and self._exit_events():
            self.awaiting_exit = True                    # wait for activity_ended
            self.left_at = None
            self.cancel()
            return
        self.left_at = time.monotonic()
        self.left_delay = AFTER_FINISH_SEC if finished else AFTER_CANCEL_SEC
        if self.missing:
            self._schedule(self.left_delay)

    def on_activity_ended(self) -> None:
        """The player left the activity (after a finish: closed the results screen)."""
        if not self.awaiting_exit:
            return
        self.awaiting_exit = False
        self.left_at = time.monotonic()
        self.left_delay = AFTER_EXIT_SEC
        if self.missing:
            self._schedule(AFTER_EXIT_SEC)

    def _schedule(self, delay: float) -> bool:
        if not (self.enabled and self.missing and self._can_reload()):
            return False
        self.cancel()
        self.task = asyncio.create_task(self._after(delay), name="mec_ap auto reload")
        return True

    async def _after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if self.in_dash or not self.missing or not self.enabled:
            return
        log.info("Reloading the checkpoint so the map shows: %s. (/auto_reload off to stop this.)",
                 ", ".join(self.missing))
        self.left_at = None
        await self._reload()

    def cancel(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = None

    # ------------------------------------------------------------ the command
    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        store_enabled(on)
        if not on:
            self.cancel()
