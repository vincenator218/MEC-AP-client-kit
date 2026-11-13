"""
The Mirror's Edge Catalyst client: Archipelago on one side, the running game on the other.

Every second it builds a Plan from what the server has sent (client/plan.py), hands it to
the game worker thread (client/game.py), and acts on what the game reports back: send the
checks it saw, log the grants it verified, finish the goal.
"""
from __future__ import annotations

import asyncio
import logging

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled,
                          handle_url_arg, logger, server_loop)
from NetUtils import ClientStatus

from ..data import (DASH, DASHES_BY_CONTENT_ID, DOUBLE_WALLRUN_FLAG, GAME, ITEMS, LOCATIONS_BY_ID,
                    MACGUFFIN_NAME)
from .dll_link import DllLink
from .game import GameSession, TickResult
from .mec_memory import djb2a
from .plan import build_plan, dash_checks, desired_flags, received_names

TICK_SEC = 1.0
IDLE_SEC = 3.0
# More already-finished locations than this on the first look at a save means it is
# probably not this slot's seed save. Hold the checks and every write until /confirm_save.
FIRST_LOOK_LIMIT = 25

APPLIES_WHEN = {
    "live_entity": "takes effect at your next death or checkpoint restart",
    "persistent_entity": "takes effect at your next death or checkpoint restart",
    "table_write_reload": "appears in the replay menu after the next load (checkpoint restart)",
}
# Flags a flag-check entity enforces: mec_ap.dll can apply these immediately (docs/MEMORY.md §3).
APPLY_METHODS = ("live_entity", "persistent_entity")
# What an apply result means for the player. Anything not "now" falls back to the next respawn.
APPLY_NOW = ("applied", "already")
APPLY_RETRY = ("table_mismatch",)     # the game changed the flag first; the next tick writes again


def flag_label(flag: str) -> str:
    names = [n for n, i in ITEMS.items() if i.flag == flag]
    return names[0] if names else flag


def appliable(flag: str) -> bool:
    if flag == DOUBLE_WALLRUN_FLAG:   # no item of its own (Progressive Wallrun #2); a live entity
        return True
    return any(i.flag == flag and i.grant_method in APPLY_METHODS for i in ITEMS.values())


class MECCommandProcessor(ClientCommandProcessor):
    ctx: "MECContext"

    def _cmd_mec(self) -> bool:
        """Show the game connection, the moves and anything on hold."""
        self.ctx.report_status()
        return True

    def _cmd_confirm_save(self) -> bool:
        """This IS the right save: send the held checks and start applying items."""
        self.ctx.confirm_save()
        return True

    def _cmd_next_volume(self) -> bool:
        """Moves that should be blocked are not: drive a different movement volume."""
        self.ctx.reject_volume = True
        logger.info("Switching to another movement volume on the next tick.")
        return True


class MECContext(CommonContext):
    game = GAME
    items_handling = 0b111              # everything, including our own and start inventory
    command_processor = MECCommandProcessor

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.session = GameSession()
        self.slot_data: dict | None = None
        self.first_look_done = False
        self.save_confirmed = False
        self.held: set[int] = set()
        self.goal_sent = False
        self.reject_volume = False
        self.warned: set[str] = set()
        self.last: TickResult = TickResult()
        self.dll = DllLink(self.on_dash_finished, self.on_dash_live, self.on_applied, self.on_dll_hello)
        self.applying: dict[int, tuple[str, int, bool]] = {}   # request id -> (flag, value, quiet)
        self.dll_reapply = False          # the DLL just connected: apply what is already written

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
            logger.info("Load your Archipelago seed save in the game. Items are applied once "
                        "the client has looked at it.")

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = None
        await super().disconnect(allow_autoreconnect)

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago Mirror's Edge Catalyst Client"
        return ui

    async def shutdown(self):
        await super().shutdown()
        await asyncio.to_thread(self.session.shutdown)

    # ------------------------------------------------------------------ plan
    def writes_allowed(self) -> bool:
        return (self.slot_data is not None and self.first_look_done
                and (not self.held or self.save_confirmed))

    def make_plan(self):
        if self.slot_data is None:
            return build_plan([], {}, {}, None, False)
        watch = {lid: LOCATIONS_BY_ID[lid] for lid in self.missing_locations - self.held
                 if lid in LOCATIONS_BY_ID and LOCATIONS_BY_ID[lid].rule != DASH}  # dashes: dll_link
        final = None if self.goal_sent else LOCATIONS_BY_ID.get(self.slot_data.get("final_location"))
        plan = build_plan([i.item for i in self.items_received], watch, self.slot_data,
                          final, self.writes_allowed())
        plan.reject_volume, self.reject_volume = self.reject_volume, False
        return plan

    # ---------------------------------------------------------------- results
    async def handle(self, r: TickResult) -> None:
        if self.last.attached and not r.attached:
            logger.info("Lost the game. Waiting for it to come back...")
            self.first_look_done = False
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
                    "This save already has %d finished locations this slot has never sent. It "
                    "may not be your seed save. Nothing has been sent and nothing will be "
                    "written. If this is the right save, type /confirm_save.", len(new))
                return
        if new:
            await self.check_locations(new)
            for lid in sorted(new):
                logger.info("Check: %s", self.location_names.lookup_in_game(lid))

        for flag in r.flags_written:
            value = r.values.get(flag, 1)
            now = appliable(flag) and await self.request_apply(flag, value, quiet=False)
            self.log_grant(flag, r.reasons.get(flag, ""), applying=now)
        if self.dll_reapply and self.dll.can_apply and self.writes_allowed():
            await self.reapply_all()
        for flag in r.flags_failed:
            self.warn_once(f"flag:{flag}", f"Could not set {flag}; will keep trying.")
        if r.moves_ok is False:
            self.warn_once("moves", "Could not find a movement volume to hold the blocked moves "
                                    "yet. Retrying.")
        elif r.moves_ok:
            self.warned.discard("moves")

        await self.check_goal(r)

    def log_grant(self, flag: str, reason: str, applying: bool = False) -> None:
        label = flag_label(flag)
        if reason.startswith("not received"):
            logger.info("Took back %s: %s%s", label, reason,
                        " (applying now through mec_ap.dll)" if applying else "")
            return
        if applying:
            logger.info("Applied %s (%s): applying now through mec_ap.dll.", label, reason or flag)
            return
        # Unlocks_DoubleWallrun has no item of its own (Progressive Wallrun #2); it is a live entity
        method = ITEMS[label].grant_method if label in ITEMS else "live_entity"
        when = APPLIES_WHEN.get(method, "")
        logger.info("Applied %s (%s)%s", label, reason or flag, f": {when}." if when else ".")

    # ---------------------------------------------------------- applying now
    async def request_apply(self, flag: str, value: int, quiet: bool) -> bool:
        """Ask mec_ap.dll to apply a flag already written. False when it cannot."""
        if not self.dll.can_apply:
            return False
        req = await self.dll.apply(djb2a(flag), value)
        if req is None:
            return False
        self.applying[req] = (flag, value, quiet)
        return True

    async def reapply_all(self) -> None:
        """The DLL connected after the flags were written: the entities may still hold the old
        value until a respawn. Ask for every ability flag the slot holds; the DLL answers
        "already" for the ones that are fine, and only real changes are logged."""
        self.dll_reapply = False
        have = received_names(i.item for i in self.items_received)
        n = 0
        for flag, (value, _reason) in desired_flags(have, self.slot_data or {}).items():
            if appliable(flag) and await self.request_apply(flag, value, quiet=True):
                n += 1
        if n:
            logger.info("mec_ap.dll connected: checking %d abilities in game.", n)

    def on_dll_hello(self, ev: dict) -> None:
        self.applying.clear()             # results for an old connection never come
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
        elif result in APPLY_RETRY:
            logger.debug("Apply %s: the game changed the flag first; writing it again.", label)
        elif result == "fault":
            self.warn_once("apply_fault", "mec_ap.dll hit an error inside the game while applying "
                                          f"{label} and stopped applying. Abilities now take effect "
                                          "at the next respawn; restart the game to try again.")
        elif not quiet:                   # a re-check only reports what it changed
            logger.info("%s takes effect at your next death or checkpoint restart (mec_ap.dll: %s).",
                        label, result)

    def warn_once(self, key: str, msg: str) -> None:
        if key not in self.warned:
            self.warned.add(key)
            logger.warning(msg)

    async def check_goal(self, r: TickResult) -> None:
        if self.goal_sent or not r.final_done or self.slot is None:
            return
        have = received_names(i.item for i in self.items_received)
        need = self.slot_data.get("data_shards_required", 0)
        if have[MACGUFFIN_NAME] < need:
            self.warn_once("early_final", f"The final activity is done, but you hold "
                                          f"{have[MACGUFFIN_NAME]}/{need} {MACGUFFIN_NAME}s. The "
                                          f"goal completes as soon as you have them all.")
            return
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        self.goal_sent = self.finished_game = True
        logger.info("Final activity complete. Goal sent!")

    # ----------------------------------------------------------------- dashes
    @staticmethod
    def dash_name(content_id: str) -> str | None:
        try:
            locs = DASHES_BY_CONTENT_ID.get(int(content_id, 16))
        except (TypeError, ValueError):
            return None
        return locs[0].name.removeprefix("Dash - ") if locs else None

    async def on_dash_finished(self, ev: dict) -> bool:
        """A finished run from the DLL. False keeps it for later (no slot yet)."""
        if self.slot_data is None or self.slot is None:
            return False
        name = self.dash_name(ev.get("content_id"))
        if name is None:
            return True                       # a delivery, billboard...: not a check here (yet)
        run = int(ev.get("run_cs", 0))
        logger.info("Dash finished: %s in %d.%02d s.", name, run // 100, run % 100)
        new = dash_checks(int(ev["content_id"], 16), run) & self.missing_locations
        if new:
            await self.check_locations(new)
            for lid in sorted(new):
                logger.info("Check: %s", self.location_names.lookup_in_game(lid))
        return True

    def on_dash_live(self, ev: dict) -> None:
        name = self.dash_name(ev.get("content_id"))
        if name:
            logger.info("Dash %s: %s.", ev.get("ev"), name)

    # --------------------------------------------------------------- commands
    def confirm_save(self) -> None:
        self.save_confirmed = True
        if self.held:
            held, self.held = self.held, set()
            asyncio.create_task(self.check_locations(held))
            logger.info("Sending %d held checks; items will now be applied.", len(held))
        else:
            logger.info("Nothing was on hold.")

    def report_status(self) -> None:
        r = self.last
        logger.info("Game: %s, world %s.", "attached" if r.attached else "not found",
                    "loaded" if r.loaded else "not loaded")
        if self.slot_data is None:
            logger.info("Not connected to a slot: nothing is read or written for the slot.")
            return
        have = received_names(i.item for i in self.items_received)
        logger.info("%s: %d/%d.", MACGUFFIN_NAME, have[MACGUFFIN_NAME],
                    self.slot_data.get("data_shards_required", 0))
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
                        "apply immediately" if self.dll.can_apply else
                        f"apply at the next respawn ({h.get('apply_why') or 'not supported'})")
        elif self.slot_data.get("dashes"):
            logger.info("mec_ap.dll: not connected. Dashes are not detected until it is.")
        if self.dll.pending:
            logger.info("%d finished runs from the DLL are waiting to be sent.", len(self.dll.pending))
        if self.held:
            logger.info("%d checks on hold until /confirm_save.", len(self.held))
        elif not self.writes_allowed():
            logger.info("Not writing yet: waiting for the first look at the save.")


async def game_loop(ctx: MECContext) -> None:
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
    ctx = MECContext(args.connect, args.password)
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
    Utils.init_logging("MECClient", exception_logger="Client")
    parser = get_base_parser(description="Mirror's Edge Catalyst Archipelago client.")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = handle_url_arg(parser.parse_args(args), parser=parser)
    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main(args))
    colorama.deinit()
