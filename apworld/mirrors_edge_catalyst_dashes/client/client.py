"""
The Mirror's Edge Catalyst Dashes client: Archipelago on one side, the running game on the other.

* Dashes: mec_ap.dll reports each finished run (dll_link.py). A run counts only if its Dash
  Unlock has been received (the soft lock); it then sends the finish check and every star tier
  the time beat. A locked run is dropped and must be redone.
* Hard dash lock (option hard_dash_lock, dash_lock.py): each dash's UnlockFlag pointer is aimed at
  its own lock flag, which the client holds at 0 until the Dash Unlock arrives. A locked dash is
  then off the map and cannot be started. Changes show after a checkpoint reload.
* Hide other activities (option hide_other_activities, activity_lock.py): opportunities, hubs,
  side missions and deliveries are made to look done, so they leave the map. Put back on close.
* GridLeaks: polled from the progression flags, as count checks per district.
* Items: moves are blocked or freed through a movement volume; abilities are written to the flag
  table (game.ProgressionWriter, the one write path) and applied at once through the DLL when it
  is there, otherwise at the next respawn. A Dash Unlock sets its lock flag to 1 (hard lock).
* Goal: enough star checks sent.
"""
from __future__ import annotations

import asyncio
import logging

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled,
                          handle_url_arg, logger, server_loop)
from NetUtils import ClientStatus

from ..data import (ABILITY_ITEMS, ACTIVITY_LOCK_FLAG, DASH_LOCKS, DASH_OF_LOCK_FLAG, DASHES_BY_CONTENT_ID,
                    DOUBLE_WALLRUN_FLAG, FLAG, GAME, ITEMS, LOCATIONS_BY_ID, GRIDLEAK_CATEGORY,
                    TRAVERSAL_ITEMS, dash_unlock_name)
from .dash_lock import DashesGameSession, LockState
from .auto_reload import AutoReload
from .dll_link import DllLink
from . import new_save
from .launcher import Launcher, dll_folder, pick_dll_folder, set_dll_folder
from .game import TickResult
from .mec_memory import djb2a
from .plan import (OVERRIDABLE, build_plan, dash_checks, dash_unlocked, desired_flags, find_move,
                   level_text, max_level, override_flags, received_names, stars_checked,
                   unlocked_dashes)

TICK_SEC = 1.0
IDLE_SEC = 3.0
# More already-collected GridLeak checks than this on the first look at a save means it is
# probably not this slot's seed save. Hold the checks and every write until /confirm_save.
FIRST_LOOK_LIMIT = 10

APPLY_METHODS = ("live_entity", "persistent_entity")
OVERRIDE_CATEGORY, OVERRIDE_STORE = "mec_ap", "move_overrides"     # Utils.persistent_store
REMOVED_OVERRIDE = "not received (manual override removed)"        # plan.desired_flags


def flag_label(flag: str) -> str:
    names = [n for n, i in ITEMS.items() if i.flag == flag]
    return names[0] if names else flag


def appliable(flag: str) -> bool:
    if flag == DOUBLE_WALLRUN_FLAG:   # no item of its own (Progressive Wallrun #2); a live entity
        return True
    return any(i.flag == flag and i.grant_method in APPLY_METHODS for i in ITEMS.values())


RELOAD_RESULTS = {
    "started": "The game is reloading the last checkpoint (it sent its round reset).",
    "nothing": "The game's reload ran but did not restart the level (no checkpoint to go back to?).",
    "not_in_level": "Not reloaded: no level is loaded (main menu or a loading screen).",
    "no_checkpoint": "Not reloaded: the game has no checkpoint set up yet. Nothing was called.",
    "busy": "Not reloaded: a reload started less than 20 seconds ago.",
    "disabled": "Not reloaded: reloading is off in mec_ap.dll (see mec_ap.log).",
    "fault": "mec_ap.dll hit an error inside the game's reload and turned /reload off until the game restarts.",
}


class MECDCommandProcessor(ClientCommandProcessor):
    ctx: "MECDContext"

    def __call__(self, raw: str):
        # The base class splits with shlex, which eats the backslashes of a Windows path
        # ("C:\not garbage\..." came out as "C:not garbage..."): take /dll_folder's text as typed.
        head, _sep, rest = (raw or "").strip().partition(" ")
        if head.lower() == "/dll_folder":
            return self._cmd_dll_folder(rest) if rest.strip() else self._cmd_dll_folder()
        return super().__call__(raw)

    def _cmd_mec(self) -> bool:
        """Show the game connection, stars, unlocked dashes, moves and anything on hold."""
        self.ctx.report_status()
        return True

    def _cmd_dashes(self) -> bool:
        """List the dashes you hold an unlock for."""
        self.ctx.report_dashes()
        return True

    def _cmd_confirm_save(self) -> bool:
        """This IS the right save: send the held checks and start applying items."""
        self.ctx.confirm_save()
        return True

    def _cmd_launch(self) -> bool:
        """Start the game through Steam and load mec_ap.dll into it."""
        self.ctx.launch_game()
        return True

    def _cmd_inject(self) -> bool:
        """Load mec_ap.dll into the running game (waits for the game if it is starting)."""
        self.ctx.inject_dll()
        return True

    def _cmd_dll_folder(self, *folder: str) -> bool:
        """Pick mec_ap.dll in a file dialog, or /dll_folder <folder> to type it."""
        if not folder:
            logger.info("DLL folder now: %s. Pick mec_ap.dll in the dialog to change it.",
                        dll_folder() or "not set")
            return pick_dll_folder() is not None
        err = set_dll_folder(" ".join(folder))
        if err:
            logger.warning(err)
            return False
        logger.info("DLL folder set to %s.", dll_folder())
        return True

    def _cmd_move(self, *args: str) -> bool:
        """Turn a move on or off by hand: /move <move> on|off|ap (Wallrun: 0|1|2). "ap" gives it
        back to the server. /move reset puts every move back. /moves lists them."""
        if not args:
            logger.info("Usage: /move <move> on|off|ap (Progressive Wallrun: 0, 1 or 2). "
                        "/move reset, /moves.")
            return False
        if len(args) == 1 and args[0].lower() == "reset":
            return self.ctx.reset_overrides()
        if len(args) < 2:
            logger.info("Say what to do with it: /move %s on|off|ap.", args[0])
            return False
        return self.ctx.set_override(" ".join(args[:-1]), args[-1])

    def _cmd_moves(self) -> bool:
        """List every move and ability: received from the server, and any /move override."""
        self.ctx.report_moves()
        return True

    def _cmd_reload(self) -> bool:
        """Reload the last checkpoint through mec_ap.dll (the pause menu's reload, without the menu)."""
        asyncio.create_task(self.ctx.request_reload())
        return True

    def _cmd_auto_reload(self, state: str = "") -> bool:
        """/auto_reload on|off: reload the checkpoint by itself when you leave a dash and a Dash
        Unlock arrived since the last reload (so it shows on the map)."""
        a = self.ctx.auto_reload
        if state.lower() in ("on", "off"):
            a.set_enabled(state.lower() == "on")
        elif state:
            logger.info("Usage: /auto_reload on|off.")
            return False
        logger.info("Automatic checkpoint reload after a dash: %s.%s", "on" if a.enabled else "off",
                    f" Waiting to show: {', '.join(a.missing)}." if a.missing else "")
        return True

    def _cmd_new_save(self) -> bool:
        """Replace the game's save with a fresh seed save (game closed; the old one is backed up)."""
        asyncio.create_task(self.ctx.make_seed_save())
        return True

    def _cmd_next_volume(self) -> bool:
        """Moves that should be blocked are not: drive a different movement volume."""
        self.ctx.reject_volume = True
        logger.info("Switching to another movement volume on the next tick.")
        return True


class MECDContext(CommonContext):
    game = GAME
    items_handling = 0b111              # everything, including our own and start inventory
    command_processor = MECDCommandProcessor

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.session = DashesGameSession()
        self.slot_data: dict | None = None
        self.first_look_done = False
        self.save_confirmed = False
        self.held: set[int] = set()
        self.goal_sent = False
        self.reject_volume = False
        self.warned: set[str] = set()
        self.last: TickResult = TickResult()
        self.sent: set[int] = set()       # checks sent this session (before the server echoes them)
        self.dll = DllLink(self.on_dash_finished, self.on_dash_live, self.on_applied, self.on_dll_hello,
                           self.on_reloaded, lambda ev: self.auto_reload.on_round_reset())
        self.auto_reload = AutoReload(self.request_reload, lambda: self.dll.can_reload,
                                      lambda: bool((self.dll.hello or {}).get("activity_events")))
        self.applying: dict[int, tuple[str, int, bool]] = {}   # request id -> (flag, value, quiet)
        self.dll_reapply = False
        self.lock_state: LockState | None = None
        self.locks_announced = False
        self.hide_state = None
        self.hide_announced = False
        self.launcher = Launcher()
        self.overrides: dict[str, int] = {}    # /move: move -> level, for this seed and slot
        self.touched: set[str] = set()         # moves ever overridden here (to undo on "ap")
        self.save_needed = False               # show the New seed save button

    # ---------------------------------------------------------- move overrides
    def _override_key(self) -> str | None:
        return f"{self.seed_name}:{self.slot}" if self.seed_name and self.slot is not None else None

    def load_overrides(self) -> None:
        key = self._override_key()
        saved = (Utils.persistent_load().get(OVERRIDE_CATEGORY, {}).get(OVERRIDE_STORE, {}) or {}).get(key, {}) \
            if key else {}
        self.overrides = {n: int(v) for n, v in saved.get("levels", {}).items() if n in OVERRIDABLE}
        self.touched = {n for n in saved.get("touched", []) if n in OVERRIDABLE} | set(self.overrides)
        if self.overrides:
            logger.warning("Manual move overrides from earlier are on for this slot: %s. "
                           "/move reset gives them back to the server.", self.overrides_text())

    def save_overrides(self) -> None:
        key = self._override_key()
        if key is None:
            return
        store = dict(Utils.persistent_load().get(OVERRIDE_CATEGORY, {}).get(OVERRIDE_STORE, {}) or {})
        if self.overrides or self.touched:
            store[key] = {"levels": dict(self.overrides), "touched": sorted(self.touched)}
        else:
            store.pop(key, None)
        Utils.persistent_store(OVERRIDE_CATEGORY, OVERRIDE_STORE, store)

    def overrides_text(self) -> str:
        return ", ".join(f"{n} {level_text(n, v)}" for n, v in sorted(self.overrides.items())) or "none"

    def set_override(self, text: str, state: str) -> bool:
        if self.slot_data is None:
            logger.info("Connect to your slot first: overrides are kept per slot.")
            return False
        name, candidates = find_move(text)
        if name is None:
            logger.info("%s: %s", text, f"which one? {', '.join(candidates)}" if candidates
                        else "not a move or ability (/moves lists them).")
            return False
        top, state = max_level(name), state.lower()
        if state == "ap":
            prior = self.overrides.pop(name, None)
            if prior is None:
                logger.info("%s already follows the server.", name)
                return True
            self.settle_removed(name, prior)
        else:
            level = {"on": top, "off": 0}.get(state)
            if level is None and state.isdigit() and int(state) <= top:
                level = int(state)
            if level is None:
                logger.info("%s can be set to %s, or ap.", name,
                            "0, 1 or 2" if top > 1 else "on or off")
                return False
            self.overrides[name] = level
            self.touched.add(name)
        self.save_overrides()
        got = self.have()[name]
        if name in self.overrides:
            logger.info("Override: %s is %s by hand (the server gave you %s). %s", name,
                        level_text(name, self.overrides[name]), level_text(name, min(got, top)),
                        self.override_effect(name))
        else:
            logger.info("%s follows the server again: %s. %s", name, level_text(name, min(got, top)),
                        self.override_effect(name))
        if not self.writes_allowed():
            logger.info("Nothing is written to the game yet (no save loaded or checked); it applies "
                        "once it is.")
        return True

    def settle_removed(self, name: str, prior: int) -> None:
        """An override is removed. Its flags only need writing back to 0 if it raised one the
        slot does not hold; otherwise there is nothing to undo."""
        have = self.have()[name]
        if all(prior < need or have >= need for _f, need in override_flags(name)):
            self.touched.discard(name)

    def forget_touched(self, flag: str, reason: str) -> None:
        """An override that was removed has been written back: stop holding that flag at 0."""
        if reason != REMOVED_OVERRIDE:
            return
        done = {n for n in self.touched - set(self.overrides) if any(f == flag for f, _ in override_flags(n))}
        if done:
            self.touched -= done
            self.save_overrides()

    def override_effect(self, name: str) -> str:
        if ITEMS[name].kind == FLAG:
            return "Applied now through mec_ap.dll if it is connected, otherwise at your next respawn."
        return "Takes effect within a second (movement volume)."

    def reset_overrides(self) -> bool:
        if not self.overrides:
            logger.info("No move overrides are on.")
            return True
        names, old, self.overrides = sorted(self.overrides), self.overrides, {}
        for n, prior in old.items():
            self.settle_removed(n, prior)
        self.save_overrides()
        logger.info("Every move follows the server again (%s).", ", ".join(names))
        return True

    def report_moves(self) -> None:
        if self.slot_data is None:
            logger.info("Not connected to a slot.")
            return
        have = self.have()
        for title, names in (("Traversal moves", TRAVERSAL_ITEMS), ("Abilities", ABILITY_ITEMS)):
            parts = []
            for n in names:
                got = level_text(n, min(have[n], max_level(n)))
                if n in self.overrides:
                    parts.append(f"{n}: {level_text(n, self.overrides[n])} [override, server {got}]")
                else:
                    parts.append(f"{n}: {got}")
            logger.info("%s: %s", title, "; ".join(parts))
        logger.info("Overrides: %s. Change with /move <move> on|off|ap, /move reset.",
                    self.overrides_text())

    # ----------------------------------------------------- game and DLL buttons
    def launch_game(self) -> None:
        try:
            running = self.last.attached or self.session.mem.find_pid() is not None
        except Exception:                                        # noqa: BLE001
            running = False
        self.launcher.launch_game(game_running=running, dll_connected=self.dll.connected)

    # -------------------------------------------------------------- seed save
    async def check_seed_save(self) -> None:
        """Whether this slot needs a seed save: a new run (no checks sent), never prepared here,
        and the game's save still holds something a seed save resets."""
        if self.slot_data is None or self.checked_locations or self.sent                 or new_save.prepared(self.seed_name, self.slot):
            self.save_needed = False
            return
        left = await asyncio.to_thread(new_save.leftover)
        self.save_needed = bool(left)
        if self.save_needed:
            logger.warning("This is a new seed and your save is not a seed save yet (%d values to "
                           "reset). Close the game if it is open, then press New seed save (or "
                           "/new_save). Your current save is backed up first.", left)

    async def make_seed_save(self) -> bool:
        r = await asyncio.to_thread(new_save.make, self.seed_name, self.slot, dll_folder())
        (logger.info if r.ok else logger.warning)(r.message)
        if r.ok:
            self.save_needed = False
            self.first_look_done = False
        return r.ok

    def inject_dll(self) -> None:
        self.launcher.inject(dll_connected=self.dll.connected)

    def status_text(self) -> str:
        """The short state shown next to the buttons."""
        if not self.last.attached:
            game = "Game: not running"
        else:
            game = "Game: loaded" if self.last.loaded else "Game: loading"
        if self.dll.connected:
            dll = f"DLL {self.dll.hello.get('dll', '')}: " + ("ok" if self.dll.hello.get("build_ok") else "inactive")
        elif self.launcher.busy:
            dll = "DLL: loading..."
        else:
            dll = "DLL: not loaded"
        return f"{game} | {dll}"

    def hard_lock(self) -> bool:
        return bool(self.slot_data and self.slot_data.get("hard_dash_lock"))

    # ---------------------------------------------------------------- server
    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self.slot_data = args.get("slot_data") or {}
            self.goal_sent = self.finished_game
            self.first_look_done = False
            self.load_overrides()
            logger.info("Load your seed save in the game. Items are applied once the client has "
                        "looked at it. Dashes need mec_ap.dll; you need %d stars to win.",
                        self.slot_data.get("stars_required", 0))
            asyncio.create_task(self.check_goal())
            asyncio.create_task(self.check_seed_save())

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = None
        self.save_needed = False
        await super().disconnect(allow_autoreconnect)

    def make_gui(self):
        base = super().make_gui()
        ctx = self

        class MECDManager(base):
            base_title = "Archipelago Mirror's Edge Catalyst Dashes Client"

            def build(self):
                layout = super().build()
                from kivy.clock import Clock
                from kivy.metrics import dp
                from kivymd.uix.button import MDButton, MDButtonText
                from kivymd.uix.label import MDLabel

                self.mec_status = MDLabel(text=ctx.status_text(), size_hint_x=None, width=dp(230),
                                          halign="center")
                self.connect_layout.add_widget(self.mec_status)
                def make_button(text, action, width=dp(120)):
                    button = MDButton(MDButtonText(text=text), style="filled", size=(width, dp(70)),
                                      size_hint_x=None, size_hint_y=None, radius=5,
                                      pos_hint={"center_y": 0.55},
                                      on_press=lambda _b, a=action: a())
                    button.height = self.server_connect_bar.height
                    return button

                for text, action in (("Launch game", ctx.launch_game), ("Inject DLL", ctx.inject_dll)):
                    self.connect_layout.add_widget(make_button(text, action))
                # Shown only while this slot needs a seed save (ctx.save_needed); /new_save always works.
                self.new_save_button = make_button(
                    "New seed save", lambda: asyncio.create_task(ctx.make_seed_save()), dp(150))

                def tick(_dt):
                    self.mec_status.text = ctx.status_text()
                    shown = self.new_save_button.parent is not None
                    if ctx.save_needed and not shown:
                        self.connect_layout.add_widget(self.new_save_button)
                    elif not ctx.save_needed and shown:
                        self.connect_layout.remove_widget(self.new_save_button)
                Clock.schedule_interval(tick, 1)
                from .dash_tab import DashTab
                self.add_client_tab("Dashes", DashTab(ctx))
                return layout

        return MECDManager

    async def shutdown(self):
        self.launcher.cancel()
        self.auto_reload.cancel()
        await super().shutdown()
        await asyncio.to_thread(self.session.shutdown)

    def have(self):
        return received_names(i.item for i in self.items_received)

    # ------------------------------------------------------------------ plan
    def writes_allowed(self) -> bool:
        return (self.slot_data is not None and self.first_look_done
                and (not self.held or self.save_confirmed))

    def make_plan(self):
        if self.slot_data is None:
            return build_plan([], {}, {}, False)
        watch = {lid: LOCATIONS_BY_ID[lid] for lid in self.missing_locations - self.held
                 if lid in LOCATIONS_BY_ID and LOCATIONS_BY_ID[lid].category == GRIDLEAK_CATEGORY}
        plan = build_plan([i.item for i in self.items_received], watch, self.slot_data,
                          self.writes_allowed(), self.overrides, self.touched)
        plan.reject_volume, self.reject_volume = self.reject_volume, False
        return plan

    # ---------------------------------------------------------------- results
    async def send_checks(self, ids: set[int]) -> None:
        if not ids:
            return
        self.sent |= ids
        await self.check_locations(ids)
        for lid in sorted(ids):
            logger.info("Check: %s", self.location_names.lookup_in_game(lid))
        await self.check_goal()

    async def handle(self, r: TickResult) -> None:
        if self.last.attached and not r.attached:
            logger.info("Lost the game. Waiting for it to come back...")
            self.first_look_done = False
            self.locks_announced = False
            self.hide_announced = False
        if r.just_loaded:
            logger.info("World loaded. Re-applying every received item.")
        self.last = r
        if not r.loaded or self.slot_data is None:
            return

        new = r.detected & self.missing_locations
        if not self.first_look_done:
            self.first_look_done = True
            if len(new) > FIRST_LOOK_LIMIT and not self.save_confirmed:
                self.held = set(new)
                logger.warning(
                    "This save already has %d GridLeak checks this slot has never sent. It may not "
                    "be your seed save. Nothing has been sent and nothing will be written. If this "
                    "is the right save, type /confirm_save.", len(new))
                return
        await self.send_checks(new)

        self.report_locks()
        for flag in r.flags_written:
            value = r.values.get(flag, 1)
            if flag == ACTIVITY_LOCK_FLAG:
                continue                         # reported by report_locks
            if flag in DASH_OF_LOCK_FLAG:
                if value == 1:
                    self.auto_reload.note(DASH_OF_LOCK_FLAG[flag])
                    logger.info("Received %s: %s", dash_unlock_name(DASH_OF_LOCK_FLAG[flag]),
                                self.refresh_hint("the dash appears on the map"))
                else:
                    logger.debug("Locked %s (%s = 0).", DASH_OF_LOCK_FLAG[flag], flag)
                continue
            reason = r.reasons.get(flag, "")
            now = appliable(flag) and await self.request_apply(flag, value, quiet=False)
            if reason.startswith("/move") or reason == REMOVED_OVERRIDE:
                self.forget_touched(flag, reason)
                logger.info("%s set to %d in the save (%s)%s.", flag_label(flag), value, reason,
                            "; applying now through mec_ap.dll" if now else "")
                continue
            self.log_grant(flag, reason, applying=now)
        for flag in r.flags_failed:
            self.warn_once(f"flag:{flag}", f"Could not set {flag}; will keep trying.")
        if self.dll_reapply and self.dll.can_apply and self.writes_allowed():
            await self.reapply_all()
        if r.moves_ok is False:
            self.warn_once("moves", "Could not find a movement volume to hold the blocked moves "
                                    "yet. Retrying.")
        elif r.moves_ok:
            self.warned.discard("moves")

    def report_locks(self) -> None:
        """After a tick: say once when the dash lock pointers are in place, and warn about any
        dash that could not be locked (its runs still do not count: the soft lock)."""
        s = self.session.locks.state
        if s is None or s is self.lock_state:
            return
        self.lock_state = s
        if s.locked and (s.written or not self.locks_announced):
            self.locks_announced = True
            if s.written:
                self.auto_reload.note_setup("the hard dash lock", self.setup_complete())
            logger.info("Hard dash lock: %d dashes are tied to their Dash Unlock. %s", s.locked,
                        self.refresh_hint("the dashes you do not hold leave the map", now=True))
        bad = s.missing + s.foreign
        if bad:
            names = [d for d, (cid, _f) in DASH_LOCKS.items() if cid in bad]
            self.warn_once("locks", f"Could not hard-lock {len(names)} dashes ({', '.join(sorted(names))}). "
                                    "They stay on the map, but their runs still count only once "
                                    "you hold the unlock. Retrying.")
        else:
            self.warned.discard("locks")

        h = self.session.hide.state
        if h is not None and h is not self.hide_state:
            self.hide_state = h
            if h.hidden and (h.written or not self.hide_announced):
                self.hide_announced = True
                if h.written:
                    self.auto_reload.note_setup("the hidden activities", self.setup_complete())
                logger.info("Hid %d other activities (opportunities, hubs, side missions, deliveries). "
                            "%s The 6 Dead Drop Deliveries stay.", h.hidden,
                            self.refresh_hint("they leave the map", now=True))
            if h.missing:
                logger.debug("Could not hide: %s", ", ".join(sorted(h.missing)))

    def setup_complete(self) -> bool:
        """The hard lock and the activity hiding (each when its option is on) cover everything."""
        s, h = self.session.locks.state, self.session.hide.state
        if self.hard_lock() and (s is None or s.missing or s.foreign):
            return False
        if self.slot_data and self.slot_data.get("hide_other_activities") and (h is None or h.missing):
            return False
        return True

    def refresh_hint(self, what: str, now: bool = False) -> str:
        """How the player gets the map refreshed: by itself (now, or after the next dash), or by hand."""
        if self.auto_reload.enabled and self.dll.can_reload:
            if now and self.auto_reload.task is not None and not self.auto_reload.task.done():
                return (f"{what[0].upper()}{what[1:]} after the checkpoint reload the client does "
                        + ("in a few seconds." if self.setup_complete() else "once every dash is found."))
            return (f"{what[0].upper()}{what[1:]} after the checkpoint reload the client does when "
                    "you next leave a dash (or reload a checkpoint now).")
        return f"Reload a checkpoint and {what} (fast travel or a death is not enough)."

    def log_grant(self, flag: str, reason: str, applying: bool = False) -> None:
        label = flag_label(flag)
        if reason.startswith("not received"):
            logger.info("Took back %s: %s%s", label, reason,
                        " (applying now through mec_ap.dll)" if applying else "")
        elif applying:
            logger.info("Received %s: applying now through mec_ap.dll.", label)
        else:
            logger.info("Received %s: takes effect at your next death or checkpoint restart "
                        "(mec_ap.dll is not connected).", label)

    def warn_once(self, key: str, msg: str) -> None:
        if key not in self.warned:
            self.warned.add(key)
            logger.warning(msg)

    async def check_goal(self) -> None:
        if self.goal_sent or self.slot_data is None or self.slot is None:
            return
        need = self.slot_data.get("stars_required", 0)
        if need and stars_checked(self.checked_locations | self.sent) >= need:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.goal_sent = self.finished_game = True
            logger.info("%d stars: goal complete!", need)

    # ---------------------------------------------------------- applying now
    async def request_apply(self, flag: str, value: int, quiet: bool) -> bool:
        if not self.dll.can_apply:
            return False
        req = await self.dll.apply(djb2a(flag), value)
        if req is None:
            return False
        self.applying[req] = (flag, value, quiet)
        return True

    async def reapply_all(self) -> None:
        """The DLL connected after the flags were written: ask for every ability flag the slot
        holds; it answers "already" for the ones that are fine, and only real changes are logged."""
        self.dll_reapply = False
        for flag, (value, _reason) in desired_flags(self.have(), self.slot_data or {}, self.overrides,
                                                    self.touched).items():
            if appliable(flag):
                await self.request_apply(flag, value, quiet=True)

    def on_dll_hello(self, ev: dict) -> None:
        self.applying.clear()
        self.auto_reload.on_game_connected()
        self.dll_reapply = bool(ev.get("build_ok") and ev.get("apply"))

    def on_applied(self, ev: dict) -> None:
        req = self.applying.pop(ev.get("id"), None)
        if req is None:
            return
        flag, value, quiet = req
        label, result = flag_label(flag), ev.get("result")
        what = "taken back" if value == 0 else "active"
        if result == "applied":
            logger.info("%s is %s now (read back from the game).", label, what)
        elif result == "already":
            if not quiet:
                logger.info("%s was already %s in game.", label, what)
        elif result == "table_mismatch":
            logger.debug("Apply %s: the game changed the flag first; writing it again.", label)
        elif result == "fault":
            self.warn_once("apply_fault", "mec_ap.dll hit an error inside the game while applying "
                                          f"{label} and stopped applying. Abilities now take effect "
                                          "at the next respawn; restart the game to try again.")
        elif not quiet:
            logger.info("%s takes effect at your next death or checkpoint restart (mec_ap.dll: %s).",
                        label, result)

    # ---------------------------------------------------------- checkpoint reload
    async def request_reload(self) -> bool:
        if not self.dll.connected:
            logger.info("/reload needs mec_ap.dll: it is not connected.")
            return False
        if not self.dll.can_reload:
            h = self.dll.hello or {}
            logger.info("mec_ap.dll %s cannot reload the checkpoint: %s.", h.get("dll"),
                        h.get("reload_why") or ("it is inactive" if not h.get("build_ok") else "needs 0.3.0 or later"))
            return False
        if await self.dll.reload() is None:
            return False
        logger.info("Asking the game to reload the last checkpoint...")
        return True

    def on_reloaded(self, ev: dict) -> None:
        result = ev.get("result")
        text = RELOAD_RESULTS.get(result, f"mec_ap.dll answered {result!r}.")
        (logger.warning if result == "fault" else logger.info)(text)
        if result == "started":
            self.auto_reload.on_round_reset()     # also for a DLL without round_reset events (0.3.0)

    # ----------------------------------------------------------------- dashes
    @staticmethod
    def dash_of(content_id: str) -> str | None:
        try:
            locs = DASHES_BY_CONTENT_ID.get(int(content_id, 16))
        except (TypeError, ValueError):
            return None
        return locs[0].dash if locs else None

    async def on_dash_finished(self, ev: dict) -> bool:
        """A finished run from the DLL. False keeps it for later (no slot yet)."""
        if self.slot_data is None or self.slot is None:
            return False
        dash = self.dash_of(ev.get("content_id"))
        if dash is None:
            return True                       # a delivery, billboard...: not a check here
        run = int(ev.get("run_cs", 0))
        self.auto_reload.on_dash_left(finished=True, finish_time=ev.get("time"))
        if not dash_unlocked(self.have(), dash):
            logger.info("Dash finished: %s in %d.%02d s, but you do not hold its Dash Unlock yet. "
                        "This run does not count; run it again once the unlock arrives.",
                        dash, run // 100, run % 100)
            return True
        logger.info("Dash finished: %s in %d.%02d s.", dash, run // 100, run % 100)
        await self.send_checks(dash_checks(int(ev["content_id"], 16), run) & self.missing_locations)
        return True

    def on_dash_live(self, ev: dict) -> None:
        if ev.get("ev") == "activity_ended":
            self.auto_reload.on_activity_ended()
            return
        if ev.get("ev") == "activity_began":
            return
        dash = self.dash_of(ev.get("content_id"))
        if dash:
            if ev.get("ev") == "started":
                self.auto_reload.on_dash_started()
            else:
                self.auto_reload.on_dash_left(finished=False)
            locked = ""
            if self.slot_data is not None and not dash_unlocked(self.have(), dash):
                locked = " (locked: this run will not count" + \
                    ("; reload a checkpoint so it leaves the map)" if self.hard_lock() else ")")
            logger.info("Dash %s: %s%s.", ev.get("ev"), dash, locked)

    # --------------------------------------------------------------- commands
    def confirm_save(self) -> None:
        self.save_confirmed = True
        if self.held:
            held, self.held = self.held, set()
            asyncio.create_task(self.send_checks(held))
            logger.info("Sending %d held checks; items will now be applied.", len(held))
        else:
            logger.info("Nothing was on hold.")

    def report_dashes(self) -> None:
        if self.slot_data is None:
            logger.info("Not connected to a slot.")
            return
        dashes = sorted(unlocked_dashes(self.have()))
        logger.info("Unlocked dashes (%d/22): %s", len(dashes), ", ".join(dashes) or "none")

    def report_status(self) -> None:
        r = self.last
        logger.info("Game: %s, world %s.", "attached" if r.attached else "not found",
                    "loaded" if r.loaded else "not loaded")
        if self.slot_data is None:
            logger.info("Not connected to a slot: nothing is read or written for the slot.")
            return
        logger.info("Stars: %d/%d. Unlocked dashes: %d/22 (/dashes lists them).",
                    stars_checked(self.checked_locations | self.sent),
                    self.slot_data.get("stars_required", 0), len(unlocked_dashes(self.have())))
        if self.hard_lock():
            s = self.lock_state
            if s is None:
                logger.info("Hard dash lock: not in place yet (needs the world loaded and items allowed).")
            else:
                logger.info("Hard dash lock: %d/22 dashes tied to their unlock%s. Changes show after "
                            "a checkpoint reload.", s.locked,
                            f", {len(s.missing) + len(s.foreign)} could not be" if s.missing or s.foreign else "")
        else:
            logger.info("Hard dash lock: off for this slot (a locked dash can be run, but does not count).")
        if self.slot_data and self.slot_data.get("hide_other_activities"):
            h = self.hide_state
            logger.info("Other activities: %s.", f"{h.hidden} hidden" if h else "not hidden yet")
        v = self.session.moves.verified
        if v is None:
            logger.info("Moves: not verified in game yet.")
        else:
            gone = [m for m, b in v.items() if b]
            logger.info("Moves blocked (read back from the game): %s", ", ".join(gone) or "none")
        if self.dll.connected:
            h = self.dll.hello
            logger.info("mec_ap.dll %s: %s; abilities %s.", h.get("dll"),
                        "active" if h.get("build_ok") else f"inactive ({h.get('why')})",
                        "apply immediately" if self.dll.can_apply else "apply at the next respawn")
        else:
            logger.info("mec_ap.dll: not connected. Dashes are not detected until it is.")
        if self.dll.pending:
            logger.info("%d finished runs from the DLL are waiting to be sent.", len(self.dll.pending))
        if self.held:
            logger.info("%d checks on hold until /confirm_save.", len(self.held))
        if self.overrides:
            logger.info("Manual move overrides: %s (/moves).", self.overrides_text())


async def game_loop(ctx: MECDContext) -> None:
    while not ctx.exit_event.is_set():
        plan = ctx.make_plan()
        try:
            r = await asyncio.to_thread(ctx.session.tick, plan)
        except Exception:                                        # noqa: BLE001
            logger.exception("Game interface error; reattaching.")
            ctx.session.detach()
            await asyncio.sleep(IDLE_SEC)
            continue
        await ctx.handle(r)
        await asyncio.sleep(TICK_SEC if r.loaded else IDLE_SEC)


async def main(args) -> None:
    ctx = MECDContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()
    game_task = asyncio.create_task(game_loop(ctx), name="game loop")
    dll_task = asyncio.create_task(ctx.dll.run(ctx.exit_event), name="dll link")
    await ctx.exit_event.wait()
    ctx.server_address = None
    game_task.cancel()
    dll_task.cancel()
    await ctx.shutdown()


def launch(*args: str) -> None:
    Utils.init_logging("MECDashesClient", exception_logger="Client")
    parser = get_base_parser(description="Mirror's Edge Catalyst Dashes Archipelago client.")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = handle_url_arg(parser.parse_args(args), parser=parser)
    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()
