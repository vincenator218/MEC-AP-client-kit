"""
Starting the game and loading mec_ap.dll from the client (the "Launch game" / "Inject DLL"
buttons, and /launch, /inject, /dll_folder).

The DLL and its injector are built by the player (dll/README.md), so the client needs to know
where they are: the folder holding mec_ap.dll and mec_ap_inject.exe is remembered in
Archipelago's persistent storage once picked (a file dialog for mec_ap.dll opens the first time
Launch game / Inject DLL needs it, or on /dll_folder) or typed (/dll_folder <folder>).

The injector waits for the game by itself (it also waits out the EA activation window), so
"Launch game" starts the game through Steam and runs the injector straight away.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys

log = logging.getLogger("Client")

STEAM_APP_ID = 1233570                      # Mirror's Edge Catalyst on Steam (appmanifest_1233570.acf)
INJECTOR, DLL = "mec_ap_inject.exe", "mec_ap.dll"
STORE_CATEGORY, STORE_KEY = "mec_ap", "dll_folder"
INJECT_TIMEOUT_SEC = 600                    # the injector waits for the game; give up after this


def dll_folder() -> str | None:
    try:
        import Utils
        folder = Utils.persistent_load().get(STORE_CATEGORY, {}).get(STORE_KEY)
    except Exception:                                            # noqa: BLE001
        folder = None
    return folder if folder and os.path.isdir(folder) else None


def set_dll_folder(folder: str) -> str | None:
    """Remember `folder` (or the folder of a file inside it). Returns an error, or None."""
    folder = os.path.abspath(os.path.expandvars(folder.strip().strip('"')))
    if os.path.isfile(folder):
        folder = os.path.dirname(folder)
    missing = [n for n in (INJECTOR, DLL) if not os.path.isfile(os.path.join(folder, n))]
    if missing:
        return f"{folder} does not contain {' and '.join(missing)}."
    import Utils
    Utils.persistent_store(STORE_CATEGORY, STORE_KEY, folder)
    return None


def pick_dll_folder() -> str | None:
    """Ask for mec_ap.dll with a file dialog and remember its folder. Returns the folder, or None
    (cancelled, or the folder lacks the injector)."""
    try:
        import Utils
        path = Utils.open_filename("Select mec_ap.dll (next to mec_ap_inject.exe)",
                                   (("mec_ap.dll", (".dll",)),), suggest=dll_folder() or "")
    except Exception as e:                                       # noqa: BLE001
        log.warning("Could not open a file dialog (%s). Type /dll_folder <folder> instead.", e)
        return None
    if not path:
        log.info("No file picked; the DLL folder is unchanged.")
        return None
    err = set_dll_folder(path)
    if err:
        log.warning(err)
        return None
    log.info("DLL folder set to %s.", dll_folder())
    return dll_folder()


class Launcher:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    def launch_game(self, game_running: bool, dll_connected: bool) -> None:
        if game_running:
            log.info("The game is already running.")
        else:
            if sys.platform != "win32":
                log.warning("Launching the game is only supported on Windows.")
                return
            log.info("Starting Mirror's Edge Catalyst through Steam...")
            os.startfile(f"steam://rungameid/{STEAM_APP_ID}")    # noqa: S606
        if not dll_connected:
            self.inject(dll_connected=False)

    def inject(self, dll_connected: bool) -> None:
        if dll_connected:
            log.info("mec_ap.dll is already loaded and connected.")
            return
        if self.busy:
            log.info("Already waiting for the game to load mec_ap.dll.")
            return
        folder = dll_folder() or pick_dll_folder()
        if folder is None:
            log.warning("The client needs to know where mec_ap.dll and mec_ap_inject.exe are: "
                        "press Inject DLL again to pick mec_ap.dll, or /dll_folder <folder>.")
            return
        self.task = asyncio.create_task(self._run(folder), name="mec_ap inject")

    async def _run(self, folder: str) -> None:
        exe, dll = os.path.join(folder, INJECTOR), os.path.join(folder, DLL)
        log.info("Loading mec_ap.dll into the game (waiting for it to start if needed)...")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = await asyncio.create_subprocess_exec(exe, dll, cwd=folder, creationflags=flags,
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            log.warning("Could not run %s: %s", exe, e)
            return
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), INJECT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            proc.kill()
            log.warning("The game did not start within %d minutes; stopped waiting. Press Inject "
                        "DLL once it is running.", INJECT_TIMEOUT_SEC // 60)
            return
        except asyncio.CancelledError:
            proc.kill()
            raise
        for line in out.decode("utf-8", "replace").splitlines():
            if line.strip() and not line.startswith("Waiting"):
                log.info("injector: %s", line.strip())
        if proc.returncode == 0:
            log.info("mec_ap.dll is loading; the client connects to it within a few seconds.")
        else:
            log.warning("The injector failed (exit code %s). If the game runs as administrator, "
                        "run the client as administrator too.", proc.returncode)

    def cancel(self) -> None:
        if self.busy:
            self.task.cancel()
