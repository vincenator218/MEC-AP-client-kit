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

from ..data import (ACTIVITY_LOCK_FLAG, DASH_LOCKS, DASH_OF_LOCK_FLAG, DASHES_BY_CONTENT_ID, DOUBLE_WALLRUN_FLAG, GAME,
                    ITEMS, LOCATIONS_BY_ID, GRIDLEAK_CATEGORY, dash_unlock_name)
from .dash_lock import DashesGameSession, LockState
from .dll_link import DllLink
from .launcher import Launcher, dll_folder, set_dll_folder
from .game import TickResult
from .mec_memory import djb2a
from .plan import (build_plan, dash_checks, dash_unlocked, desired_flags, received_names,
                   stars_checked, unlocked_dashes)

TICK_SEC = 1.0
IDLE_SEC = 3.0
# More already-collected GridLeak checks than this on the first look at a save means it is
# probably not this slot's seed save. Hold the checks and every write until /confirm_save.
FIRST_LOOK_LIMIT = 10

APPLY_METHODS = ("live_entity", "persistent_entity")


def flag_label(flag: str) -> str:
    names = [n for n, i in ITEMS.items() if i.flag == flag]
    return names[0] if names else flag


def appliable(flag: str) -> bool:
    if flag == DOUBLE_WALLRUN_FLAG:   # no item of its own (Progressive Wallrun #2); a live entity
        return True
    return any(i.flag == flag and i.grant_method in APPLY_METHODS for i in ITEMS.values())


class MECDCommandProcessor(ClientCommandProcessor):
    ctx: "MECDContext"

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
        """Set or show the folder that holds mec_ap.dll and mec_ap_inject.exe."""
        if not folder:
            logger.info("DLL folder: %s", dll_folder() or "not set (/dll_folder <folder>)")
            return True
        err = set_dll_folder(" ".join(folder))
        if err:
            logger.warning(err)
            return False
        logger.info("DLL folder set to %s.", dll_folder())
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
        self.dll = DllLink(self.on_dash_finished, self.on_dash_live, self.on_applied, self.on_dll_hello)
        self.applying: dict[int, tuple[str, int, bool]] = {}   # request id -> (flag, value, quiet)
        self.dll_reapply = False
        self.lock_state: LockState | None = None
        self.locks_announced = False
        self.hide_state = None
        self.hide_announced = False
        self.launcher = Launcher()

    # ----------------------------------------------------- game and DLL buttons
    def launch_game(self) -> None:
        try:
            running = self.last.attached or self.session.mem.find_pid() is not None
        except Exception:                                        # noqa: BLE001
            running = False
        self.launcher.launch_game(game_running=running, dll_connected=self.dll.connected)

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
            logger.info("Load your seed save in the game. Items are applied once the client has "
                        "looked at it. Dashes need mec_ap.dll; you need %d stars to win.",
                        self.slot_data.get("stars_required", 0))
            asyncio.create_task(self.check_goal())

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = None
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
                for text, action in (("Launch game", ctx.launch_game), ("Inject DLL", ctx.inject_dll)):
                    button = MDButton(MDButtonText(text=text), style="filled", size=(dp(120), dp(70)),
                                      size_hint_x=None, size_hint_y=None, radius=5,
                                      pos_hint={"center_y": 0.55},
                                      on_press=lambda _b, a=action: a())
                    button.height = self.server_connect_bar.height
                    self.connect_layout.add_widget(button)
                Clock.schedule_interval(lambda _dt: setattr(self.mec_status, "text", ctx.status_text()), 1)
                return layout

        return MECDManager

    async def shutdown(self):
        self.launcher.cancel()
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
                          self.writes_allowed())
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
                    logger.info("Received %s: reload a checkpoint to see the dash on the map (fast "
                                "travel or a death is not enough).",
                                dash_unlock_name(DASH_OF_LOCK_FLAG[flag]))
                else:
                    logger.debug("Locked %s (%s = 0).", DASH_OF_LOCK_FLAG[flag], flag)
                continue
            now = appliable(flag) and await self.request_apply(flag, value, quiet=False)
            self.log_grant(flag, r.reasons.get(flag, ""), applying=now)
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
            logger.info("Hard dash lock: %d dashes are tied to their Dash Unlock. Reload a checkpoint "
                        "once so the dashes you do not hold leave the map.", s.locked)
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
                logger.info("Hid %d other activities (opportunities, hubs, side missions, deliveries). "
                            "Reload a checkpoint to clear them from the map; the 6 Dead Drop "
                            "Deliveries stay.", h.hidden)
            if h.missing:
                logger.debug("Could not hide: %s", ", ".join(sorted(h.missing)))

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
        for flag, (value, _reason) in desired_flags(self.have(), self.slot_data or {}).items():
            if appliable(flag):
                await self.request_apply(flag, value, quiet=True)

    def on_dll_hello(self, ev: dict) -> None:
        self.applying.clear()
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
        if not dash_unlocked(self.have(), dash):
            logger.info("Dash finished: %s in %d.%02d s, but you do not hold its Dash Unlock yet. "
                        "This run does not count; run it again once the unlock arrives.",
                        dash, run // 100, run % 100)
            return True
        logger.info("Dash finished: %s in %d.%02d s.", dash, run // 100, run % 100)
        await self.send_checks(dash_checks(int(ev["content_id"], 16), run) & self.missing_locations)
        return True

    def on_dash_live(self, ev: dict) -> None:
        dash = self.dash_of(ev.get("content_id"))
        if dash:
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
