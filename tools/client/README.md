# Movement Toggles (for testers)

A small tool that removes individual movement moves in Mirror's Edge Catalyst, so
we can work out **which missions and activities are impossible without which moves**.
That list is what an Archipelago randomizer needs: without it, a seed can hand
someone a mission they physically cannot finish.

## What you need

- **Windows**
- **64-bit Python 3.8+** — [python.org/downloads](https://www.python.org/downloads/).
  Tick "Add Python to PATH" in the installer. Nothing else to install; the tool
  uses only what comes with Python.

## Running it

1. Put **`MEC_MoveToggles.pyw`** and **`mec_memory.py`** in the same folder.
2. Start the game and load a save. Free roam is fine.
3. Double-click `MEC_MoveToggles.pyw`.

If it says **access denied**, right-click it and choose *Run as administrator*.

If double-clicking opens a text editor instead, right-click → *Open with* → Python.

## Using it

Click a move to remove it; click again to give it back. Then go play something.

The suggested way to test an activity:

1. **Remove ALL moves**, then start the activity.
2. When you get stuck, give back whichever move you need and carry on.
3. The moves you had to give back are that activity's requirements.

Type the activity's name in the Report box and press **Copy a report line** — it puts
a line like this on your clipboard, ready to paste:

```
Drone Works | removed: Springboard / Vault, Ledge Hang | still had: Climb Up, Wallrun, MAG Rope
```

Paste it with any notes about *where* it blocked you. The log pane is selectable if you
want to copy that too.

## Things worth knowing

- **Your save file is never touched.** These moves are controlled by invisible volumes
  the level designers placed to stop you climbing certain surfaces, and the tool borrows
  one of them. Nothing is written to disk. Closing the window, or restarting the game,
  puts everything back.
- **Pipes, ladders and ordinary jumping cannot be removed.** An activity that only needs
  those will always be completable, so "nothing needed" is a real and useful answer.
- **"Springboard / Vault" is one switch, not two.** Jumping off a low object, vaulting a
  railing and the built springboard spots all go together.
- The log will sometimes say *"the volume we were using unloaded, switched to another"*.
  That is normal — the game streams these objects in and out as you move, and the tool
  follows along.
- **If a toggle does not seem to do anything, press "Try another volume".** The game has
  about 60 of these volumes and not all of them affect you, so the tool may need a couple
  of goes to find one that does. The line under the status text shows which one it is using.
- The status line only says "Removed: ..." once the change has been **written and read back**
  from the game, so if it says that, it really is applied.
- **Speed:** the first toggle after loading has to search the game's memory, so it can take
  a few seconds. After that it remembers where it found one and reuses it, so toggling and
  giving moves back are instant. Two buttons are deliberately slow because they are thorough:
  **Reconnect / rescan** counts every volume, and **Reset everything** checks all of them.
- If something looks wrong, press **Reset everything**. If it still looks wrong, restart
  the game; that always clears it.

## Please report

- Anything a move made **impossible** rather than just harder.
- Anything you finished with **no moves at all**.
- Anything where you expected to be blocked and weren't.
- Any error message the tool shows.

## For developers

`mec_memory.py` is a standalone library — attach to the game, walk writable memory, find
instances of an SDK class by its vtable, drive the exclusion volumes, and read the
progression flag table. It is the memory layer an Archipelago client needs.

```python
from mec_memory import MecMemory
m = MecMemory(); m.attach()
print(m.sanity())                       # check the offsets suit this build
print(m.read_flag("Unlocks_Coil"))
vols = m.find_exclusion_volumes()
m.set_exclusions(vols[0], climb_up=True)
m.release_all_ours()
```

Run `python mec_memory.py` on its own for a quick dump of the offsets and the first
few volumes.

It **reads** progression flags but deliberately does not write them: those are captured
by the game's autosave, so writing one changes the player's save. That belongs in the
client behind its own deliberate code path. Exclusion volumes are safe by comparison —
level state, never persisted. See `docs/MEMORY.md` for the mechanics and the safety rules.
