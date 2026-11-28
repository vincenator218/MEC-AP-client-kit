"""
Making the seed save from the client: the "New seed save" button and /new_save.

It does what tools/save/make_seed_save.py does (that file is copied into this package at build
time, with the three data files it reads), in place on the game's own save:
  * refuses while Mirror's Edge Catalyst is running (the game writes PROF_SAVE when it exits);
  * copies PROF_SAVE to PROF_SAVE.before_<seed>_<date time> first; nothing is ever deleted;
  * writes the seed save to a temporary file next to it, then replaces PROF_SAVE with it;
  * reads it back: a second pass must find nothing left to clear;
  * moves mec_ap.dll's run journal (mec_ap_events.jsonl, mec_ap_acked.txt) aside, so runs from
    the last seed are not sent to this one;
  * records the seed and slot in Archipelago's persistent storage (mec_ap / seed_saves).

The button shows only when it is needed: connected to a slot that has sent no checks yet, this
seed and slot never prepared here, and the save still holds something a seed save clears. /new_save
does it at any time.
"""
from __future__ import annotations

import ctypes
import json
import os
import pkgutil
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .make_seed_save import clear, seed_save_bytes, targets

STORE_CATEGORY, STORE_KEY = "mec_ap", "seed_saves"
SAVE_NAME = "PROF_SAVE"
JOURNAL_FILES = ("mec_ap_events.jsonl", "mec_ap_acked.txt")

_want: dict[str, str] | None = None


def _data(name: str):
    raw = pkgutil.get_data(__name__.rpartition(".")[0].rpartition(".")[0], f"data/{name}")
    if raw is None:
        raise FileNotFoundError(f"data/{name} is missing from the apworld")
    return json.loads(raw.decode("utf-8"))


def wanted() -> dict[str, str]:
    """The flags a seed save clears, as make_seed_save.py's defaults choose them."""
    global _want
    if _want is None:
        _want = targets(_data("flag_names.json"), _data("locations.json"), _data("dash_unlock_flags.json"))
    return _want


def documents() -> Path:
    """The user's Documents folder, also when Windows moved it (OneDrive, another drive)."""
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                            ("d", ctypes.c_ubyte * 8)]
            # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:                                        # noqa: BLE001
            pass
    return Path.home() / "Documents"


def save_path() -> Path:
    return documents() / "Mirrors Edge Catalyst" / "settings" / SAVE_NAME


def leftover(path: Path | None = None) -> int | None:
    """How many values a seed save would still clear in the current save (0: already a fresh seed
    save). None when there is no save to read."""
    path = path or save_path()
    try:
        data = bytearray(path.read_bytes())
    except OSError:
        return None
    return clear(data, wanted(), dry_run=True)[0]


def game_running() -> bool:
    try:
        from .mec_memory import MecMemory
        return MecMemory().find_pid() is not None
    except Exception:                                            # noqa: BLE001
        return False


def _key(seed: str | None, slot: int | None) -> str | None:
    return f"{seed}:{slot}" if seed and slot is not None else None


def prepared(seed: str | None, slot: int | None) -> bool:
    key = _key(seed, slot)
    if key is None:
        return False
    try:
        import Utils
        return key in (Utils.persistent_load().get(STORE_CATEGORY, {}).get(STORE_KEY, {}) or {})
    except Exception:                                            # noqa: BLE001
        return False


def _remember(seed: str | None, slot: int | None, backup: str) -> None:
    key = _key(seed, slot)
    if key is None:
        return
    import Utils
    store = dict(Utils.persistent_load().get(STORE_CATEGORY, {}).get(STORE_KEY, {}) or {})
    store[key] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "backup": backup}
    Utils.persistent_store(STORE_CATEGORY, STORE_KEY, store)


@dataclass
class Result:
    ok: bool
    message: str
    changed: int = 0
    backup: str = ""


def make(seed: str | None, slot: int | None, dll_folder: str | None, path: Path | None = None) -> Result:
    """Replace the game's save with a seed save (backup first). Never raises."""
    if game_running():
        return Result(False, "Close Mirror's Edge Catalyst first: the game writes its save when it "
                             "exits and would undo the new one.")
    path = path or save_path()
    if not path.is_file():
        return Result(False, f"No save found at {path}. Play the game once (the story must be "
                             "finished), then try again.")
    try:
        original = path.read_bytes()
        new, changed, per_kind = seed_save_bytes(original, wanted())
        stamp = time.strftime("%Y%m%d_%H%M%S")
        tag = "".join(c for c in (seed or "seed") if c.isalnum())[-12:]
        backup = path.with_name(f"{path.name}.before_{tag}_{stamp}")
        shutil.copy2(path, backup)
        tmp = path.with_name(path.name + ".ap_new")
        tmp.write_bytes(new)
        os.replace(tmp, path)
        left = leftover(path)
        if left != 0:
            return Result(False, f"The new save did not read back clean ({left} values left); your "
                                 f"old save is in {backup.name}. Put it back before playing.",
                          changed, backup.name)
    except Exception as e:                                       # noqa: BLE001
        return Result(False, f"Could not make the seed save: {e}. Your save was not replaced if no "
                             "backup is named here.")
    moved = []
    if dll_folder:
        for name in JOURNAL_FILES:
            f = Path(dll_folder) / name
            if f.is_file():
                try:
                    os.replace(f, f.with_name(f"{name}.before_{tag}_{stamp}"))
                    moved.append(name)
                except OSError:
                    pass
    _remember(seed, slot, backup.name)
    kinds = ", ".join(f"{n} {k}" for k, n in sorted(per_kind.items(), key=lambda kv: -kv[1]))
    msg = (f"Seed save ready: {changed} values reset ({kinds or 'nothing to reset'}). Your previous "
           f"save is {backup.name}, next to it.")
    if moved:
        msg += " mec_ap.dll's run journal from the last seed was moved aside."
    return Result(True, msg, changed, backup.name)
