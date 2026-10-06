#!/usr/bin/env python3
"""
MEC_MoveToggles.pyw -- remove individual movement moves in Mirror's Edge Catalyst.

For the Archipelago randomizer project: we need to know which missions and
activities are impossible without which moves.

HOW TO USE
  1. Start the game and load a save (free roam is fine).
  2. Double-click this file. If Windows asks what to open it with, pick Python.
  3. Click a move to remove it. Go try a mission. Click it again to get it back.

Keep this file next to mec_memory.py.

IS IT SAFE?  Your save file is never touched. These moves are controlled by
invisible volumes the designers placed to stop you climbing certain surfaces,
and this borrows one of them. Nothing is written to disk; closing the window
or restarting the game puts everything back.

CANNOT be removed: pipes, ladders, and ordinary jumping.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from mec_memory import MecMemory, MecError, MOVES
except ImportError:
    import tkinter.messagebox as mb
    _r = tk.Tk(); _r.withdraw()
    mb.showerror("Missing file",
                 "mec_memory.py must be in the same folder as this program.\n\n"
                 "Download both files and keep them together.")
    raise SystemExit(1)

PRETTY = {
    "springboard": "Springboard / Vault",
    "climb_up":    "Climb Up (mantle)",
    "ledge_hang":  "Ledge Hang",
    "wallrun":     "Wallrun",
    "mag_rope":    "MAG Rope",
}

REASSERT_SEC = 1.5          # volumes stream out; keep re-writing the chosen one


class App:
    """UI thread only touches `self.desired` and the log queue.

    One worker thread owns every memory access. The UI never waits for it and
    never drops a click: it records what the user wants and wakes the worker,
    which always applies the LATEST wanted state. An earlier version refused
    work while busy, so clicks silently did nothing while the log claimed
    success -- the exact mistake FINDINGS §86 is about.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.mem = MecMemory()

        self.desired = {m: False for m in MOVES}      # written by the UI
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.events: queue.Queue = queue.Queue()

        self.volume = None            # the volume we drive
        self.last_region_hint = None  # where we found one last time
        self.rejected: set[int] = set()   # volumes the user said did nothing
        self.applied_sig = None       # last state we verified, to avoid log spam
        self.full_sweep = False       # set by "Reset everything"
        self.want_count = False       # set by Reconnect: do the slow full count once
        self.volume_count = None      # only known after a full scan

        root.title("Mirror's Edge Catalyst - Movement Toggles")
        root.resizable(False, False)
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()
        self._pump()

    # ------------------------------------------------------------------- ui
    def _build(self) -> None:
        ttk.Label(self.root, text="Click a move to remove it. Click again to give it back.",
                  font=("Segoe UI", 10, "bold")
                  ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 2))
        ttk.Label(self.root,
                  text="Your save file is never touched. Closing this window undoes everything."
                  ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        box = ttk.Frame(self.root)
        box.grid(row=2, column=0, sticky="nw", padx=12)
        self.buttons = {}
        for i, m in enumerate(MOVES):
            b = tk.Button(box, width=34, anchor="w", justify="left",
                          command=lambda mm=m: self.toggle(mm))
            b.grid(row=i, column=0, pady=2, sticky="w")
            self.buttons[m] = b

        side = ttk.Frame(self.root)
        side.grid(row=2, column=1, sticky="nw", padx=(4, 12))
        for i, (label, fn) in enumerate([
            ("Remove ALL moves",    self.remove_all),
            ("Give back ALL moves", self.restore_all),
            ("Try another volume",  self.next_volume),
            ("Reconnect / rescan",  self.reconnect),
            ("Reset everything",    self.reset_all),
        ]):
            ttk.Button(side, text=label, width=22, command=fn).grid(row=i, column=0, pady=2)

        self.status = ttk.Label(self.root, text="Looking for the game...", foreground="#555")
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        self.detail = ttk.Label(self.root, text="", foreground="#777")
        self.detail.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        rep = ttk.LabelFrame(self.root, text="Report")
        rep.grid(row=5, column=0, columnspan=2, sticky="we", padx=12, pady=(4, 6))
        ttk.Label(rep, text="What were you playing?").grid(row=0, column=0, sticky="w",
                                                           padx=8, pady=(6, 0))
        self.activity = ttk.Entry(rep, width=44)
        self.activity.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Button(rep, text="Copy a report line", command=self.copy_report
                   ).grid(row=1, column=1, padx=8, pady=(0, 8))

        ttk.Label(self.root, text="Log:").grid(row=6, column=0, sticky="w", padx=12)
        wrap = ttk.Frame(self.root)
        wrap.grid(row=7, column=0, columnspan=2, padx=12, pady=(0, 12))
        self.log_box = tk.Text(wrap, width=76, height=11, wrap="word",
                               state="disabled", font=("Consolas", 9))
        self.log_box.grid(row=0, column=0)
        sb = ttk.Scrollbar(wrap, command=self.log_box.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_box["yscrollcommand"] = sb.set

        self.refresh()

    def log(self, msg: str) -> None:
        self.log_box["state"] = "normal"
        self.log_box.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
        self.log_box.see("end")
        self.log_box["state"] = "disabled"

    def refresh(self) -> None:
        with self.lock:
            want = dict(self.desired)
        for m in MOVES:
            gone = want[m]
            self.buttons[m].configure(
                text=("[X]  " if gone else "[ ]  ") + PRETTY[m] + ("    REMOVED" if gone else ""),
                bg="#f4cccc" if gone else "SystemButtonFace",
                relief="sunken" if gone else "raised")

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "status":
                    self.status.configure(text=payload[0], foreground=payload[1])
                elif kind == "detail":
                    self.detail.configure(text=payload)
                elif kind == "refresh":
                    self.refresh()
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _say(self, msg): self.events.put(("log", msg))
    def _status(self, msg, colour="#555"): self.events.put(("status", (msg, colour)))
    def _detail(self, msg): self.events.put(("detail", msg))

    # -------------------------------------------------------------- the worker
    def _worker(self) -> None:
        while not self.stopping.is_set():
            woken = self.wake.wait(REASSERT_SEC)
            self.wake.clear()
            try:
                self._sync(user_asked=woken)
            except MecError as e:
                self._status(str(e), "#a00")
            except Exception as e:                                  # noqa: BLE001
                self._say(f"Unexpected problem: {e!r}")

    def _ensure_attached(self) -> bool:
        if self.mem.attached:
            return True
        self.mem.detach()
        self.mem.attach()
        s = self.mem.sanity()
        if s["class_name"] != "PamMovementExclusionEntityData":
            self._say("Warning: this does not look like the game build this tool was made "
                      f"for (found {s['class_name']!r}). It may not work.")
        if not s["loaded"]:
            self._status("Game found, but you are not in the world yet. "
                         "Load a save, then press Reconnect.", "#a60")
            return False
        self._say(f"Connected to the game (base 0x{s['base']:X}).")
        return True

    def _count_all(self) -> None:
        """Full enumeration. Only for the count shown on Reconnect."""
        self._status("Scanning memory for movement volumes...", "#555")
        vols = self.mem.find_exclusion_volumes()
        self.volume_count = len(vols)
        self._say(f"Found {len(vols)} movement volume(s).")
        if 0 < len(vols) < 20:
            self._say("Fewer than expected (~60). If the toggles do not bite, "
                      "press 'Try another volume'.")

    def _choose(self) -> bool:
        """Get a volume to drive -- one is enough, so stop at the first.

        Searches the heap region where we last found one before looking
        anywhere else, which usually means no full memory scan at all.
        """
        if self.volume is not None and self.mem.is_volume(self.volume):
            return True
        if self.volume is not None:
            self.last_region_hint = self.volume    # it died; its neighbours will do
        self.volume = None
        a = self.mem.find_one_exclusion_volume(prefer=self.last_region_hint,
                                               skip=self.rejected)
        if a is None and self.rejected:
            # nothing left that the user has not rejected; start over
            self._say("Tried every volume we found. Starting the list again.")
            self.rejected.clear()
            a = self.mem.find_one_exclusion_volume(prefer=self.last_region_hint)
        if a is None:
            return False
        self.volume = a
        self.last_region_hint = a
        return True

    def _sync(self, user_asked: bool) -> None:
        """Make the game match `desired`. Idempotent; latest state always wins."""
        with self.lock:
            want = dict(self.desired)
        sig = tuple(want[m] for m in MOVES)
        any_removed = any(sig)

        if not self._ensure_attached():
            return
        if not self.mem.alive():
            self._status("The game has closed.", "#a00")
            return
        if self.want_count:
            self.want_count = False
            self._count_all()

        if not any_removed:
            sweep = self.full_sweep
            if self.applied_sig in (None, sig) and not user_asked and not sweep:
                return
            if sweep:
                self.full_sweep = False
                self._status("Checking every volume...", "#555")
                n = self.mem.release_all_ours()
            else:
                n = self.mem.release_tracked()       # no scan: instant
            self.volume = None
            self.applied_sig = sig
            self._say(f"Released {n} volume(s). Every move is back."
                      if n else "Nothing was modified; every move is available.")
            self._status("All moves available. The game is unmodified.", "#070")
            self._detail("")
            return

        if not self._choose():
            self._status("Could not find a volume to use. Press Reconnect.", "#a00")
            return

        ok = self.mem.set_exclusions(self.volume, **want)
        gone = [PRETTY[m] for m in MOVES if want[m]]
        if not ok:
            self._say(f"Write to volume 0x{self.volume:X} did NOT verify. Trying another.")
            self.volume = None
            self._status("Retrying on a different volume...", "#a60")
            self.wake.set()
            return

        self._status("Removed: " + ", ".join(gone), "#a00")
        self._detail(f"using volume 0x{self.volume:X}"
                     + (f" of {self.volume_count} found" if self.volume_count else ""))
        if sig != self.applied_sig:
            self.applied_sig = sig
            self._say(f"Applied and verified on volume 0x{self.volume:X}: "
                      + ", ".join(gone) + " removed.")

    # ------------------------------------------------------------- ui actions
    def _request(self, **changes) -> None:
        with self.lock:
            self.desired.update(changes)
        self.refresh()
        self.wake.set()

    def toggle(self, move: str) -> None:
        with self.lock:
            new = not self.desired[move]
        self.log(f"{PRETTY[move]} -> {'REMOVED' if new else 'available'}")
        self._request(**{move: new})

    def remove_all(self) -> None:
        self.log("Removing every move.")
        self._request(**{m: True for m in MOVES})

    def restore_all(self) -> None:
        self.log("Giving every move back.")
        self._request(**{m: False for m in MOVES})

    def next_volume(self) -> None:
        """The current volume did nothing for the user, so never pick it again."""
        if self.volume is not None:
            self.rejected.add(self.volume)
            self.log(f"Volume 0x{self.volume:X} did nothing; trying a different one.")
        else:
            self.log("Looking for another volume.")
        self.volume = None
        self.applied_sig = None
        self.wake.set()

    def reconnect(self) -> None:
        self.log("Reconnecting and rescanning.")
        self.mem.detach()
        self.volume = None
        self.last_region_hint = None
        self.rejected.clear()
        self.applied_sig = None
        self.volume_count = None
        self.want_count = True
        self.wake.set()

    def reset_all(self) -> None:
        self.log("Reset: giving every move back and checking every volume.")
        self.volume = None
        self.last_region_hint = None
        self.rejected.clear()
        self.applied_sig = None
        self.full_sweep = True          # the thorough path, worth the wait here
        self._request(**{m: False for m in MOVES})

    def copy_report(self) -> None:
        name = self.activity.get().strip() or "(unnamed activity)"
        with self.lock:
            want = dict(self.desired)
        gone = [PRETTY[m] for m in MOVES if want[m]]
        have = [PRETTY[m] for m in MOVES if not want[m]]
        line = (f"{name} | removed: {', '.join(gone) if gone else 'nothing'} "
                f"| still had: {', '.join(have) if have else 'nothing'}")
        self.root.clipboard_clear()
        self.root.clipboard_append(line)
        self.log("Copied: " + line)

    def on_close(self) -> None:
        self.stopping.set()
        self.wake.set()
        try:
            with self.lock:
                self.desired = {m: False for m in MOVES}
            if self.mem.attached:
                n = self.mem.release_tracked()
                print(f"released {n} volume(s) on exit")
        except Exception:                                            # noqa: BLE001
            pass
        try:
            self.mem.detach()
        finally:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
