#!/usr/bin/env python3
"""
package_dashes.py -- build a player package for the Mirror's Edge Catalyst Dashes world.

    python tools/package_dashes.py

Builds the apworld (tools/build_apworld.py --world dashes), then puts into
build/MEC_Dashes_AP/ and build/MEC_Dashes_AP.zip everything a player needs:

    README.txt                              quick start (written here)
    mirrors_edge_catalyst_dashes.apworld    -> Archipelago's custom_worlds
    MEC Dashes.yaml                         player options, to edit
    Setup Guide.md                          the world's setup guide
    mec_ap/mec_ap.dll, mec_ap_inject.exe    the in-game agent (built from dll/, see dll/README.md)

The seed save is made by the client (its New seed save button, or /new_save), so no Python or
save tool is needed. The DLL is taken from dll/build as it is: build it first. Research mode,
logs, journals and old DLL copies are never included.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "MEC_Dashes_AP"
WORLD = ROOT / "apworld" / "mirrors_edge_catalyst_dashes"

YAML = """\
# Mirror's Edge Catalyst Dashes: player options. Put this file in Archipelago's Players folder
# (or upload it to a room), with your own name below.
name: Player
game: Mirror's Edge Catalyst Dashes
Mirror's Edge Catalyst Dashes:
  stars_required: 40            # the goal: this many dash stars (22 dashes x dash_stars at most)
  dash_stars: 3                 # star checks per dash, 0-3
  gridleak_bundle_size: 10      # a GridLeak check every this many leaks in a district
  gridleak_percent: 60          # GridLeak checks stop at this share of a district's leaks
  starting_dashes: 3            # Dash Unlocks you start with
  traversal_items: randomized   # moves (wallrun, MAG Rope...) are items
  revert_skill_tree_purchases: true
  hard_dash_lock: true          # dashes you do not hold leave the map
  hide_other_activities: true   # opportunities, hubs, side missions and deliveries leave the map
"""

README = r"""Mirror's Edge Catalyst Dashes for Archipelago
=============================================

Get 40 dash stars (your YAML sets the number). Each dash needs its Dash Unlock, which you find
as an Archipelago item; a dash's star checks are sent when your run beats that star's time.

What you need
-------------
- Mirror's Edge Catalyst on Steam (the DLL is made for the Steam build).
- Archipelago 0.6.4 or newer.
- A save where the story is finished.

Install
-------
1. Copy mirrors_edge_catalyst_dashes.apworld into Archipelago's custom_worlds folder
   (or double-click it with Archipelago installed).
2. Put the mec_ap folder anywhere you like and keep its two files together.

Play
----
1. Edit "MEC Dashes.yaml" (your name, options), generate and host the seed as usual.
2. In the Archipelago Launcher open "Mirror's Edge Catalyst Dashes Client" and connect to the
   server with your slot name, with the game closed.
3. New seed: the client shows a "New seed save" button. Press it: it backs up your save
   (Documents\Mirrors Edge Catalyst\settings\PROF_SAVE.before_...) and turns it into a seed
   save. The story stays done; abilities, GridLeaks and dash locks are cleared so they can be
   earned again. /new_save does the same at any time.
4. Press "Launch game" (or start the game yourself and press "Inject DLL"). The first time, pick
   mec_ap.dll in the file dialog. The DLL must be loaded again after every game start.
5. Load into the city.

About a minute after you load in, the client reloads the checkpoint once by itself: the dashes
you do not hold and the other activities leave the map. It reloads again when you leave a dash
after a Dash Unlock arrived, so the new dash shows. /auto_reload off turns that off; /reload
reloads by hand.

The client's Dashes tab shows your stars, your unlocked dashes, their stars and the time to beat
for the next one. /moves and /move <move> on|off|ap let you turn moves on or off by hand.

Each new seed: connect with the game closed and press New seed save (it also clears
mec_ap.dll's run journal from the last seed).

More: "Setup Guide.md".
"""


def main() -> None:
    dll_dir = ROOT / "dll" / "build"
    for name in ("mec_ap.dll", "mec_ap_inject.exe"):
        if not (dll_dir / name).is_file():
            sys.exit(f"{dll_dir / name} is missing: build the DLL first (dll/README.md).")
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_apworld.py"), "--world", "dashes"],
                   check=True, stdout=subprocess.DEVNULL)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "mec_ap").mkdir(parents=True)

    shutil.copy2(ROOT / "build" / "mirrors_edge_catalyst_dashes.apworld", OUT)
    for name in ("mec_ap.dll", "mec_ap_inject.exe"):
        shutil.copy2(dll_dir / name, OUT / "mec_ap" / name)
    shutil.copy2(WORLD / "docs" / "setup_en.md", OUT / "Setup Guide.md")
    (OUT / "MEC Dashes.yaml").write_text(YAML, encoding="utf-8", newline="\r\n")
    (OUT / "README.txt").write_text(README, encoding="utf-8", newline="\r\n")

    zip_base = OUT.parent / OUT.name
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", OUT.parent, OUT.name))
    print(f"{OUT}\n{zip_path}")


if __name__ == "__main__":
    main()
