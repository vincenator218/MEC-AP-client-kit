#!/usr/bin/env python3
"""
Assemble and zip a Mirror's Edge Catalyst apworld.

    python tools/build_apworld.py                          # -> build/mirrors_edge_catalyst.apworld
    python tools/build_apworld.py --world dashes           # -> build/mirrors_edge_catalyst_dashes.apworld
    python tools/build_apworld.py --stage-only DIR         # unzipped package in DIR (for running tests)

Two worlds share this kit:
  * main   (apworld/mirrors_edge_catalyst/): the whole open world;
  * dashes (apworld/mirrors_edge_catalyst_dashes/): dashes, GridLeaks, moves and abilities only.

Some files are copied in so they keep a single home in the kit: the data files
(data/items.json, locations.json, named_challenges.json) and tools/client/mec_memory.py (the
memory layer, shared with MEC_MoveToggles.pyw). The dashes world also takes the main world's
requirement parser (logic.py, data/aliases.json) and its game-side client modules (game.py,
dll_link.py), so the memory, movement-volume and ability-apply code exists once.
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "apworld" / "mirrors_edge_catalyst"
DATA = {
    ROOT / "data" / "items.json": Path("data") / "items.json",
    ROOT / "data" / "locations.json": Path("data") / "locations.json",
    ROOT / "data" / "named_challenges.json": Path("data") / "named_challenges.json",
    ROOT / "tools" / "client" / "mec_memory.py": Path("client") / "mec_memory.py",
}
WORLDS = {
    "main": ("mirrors_edge_catalyst", DATA),
    "dashes": ("mirrors_edge_catalyst_dashes", {
        **DATA,
        MAIN / "logic.py": Path("logic.py"),
        MAIN / "data" / "aliases.json": Path("data") / "aliases.json",
        MAIN / "client" / "game.py": Path("client") / "game.py",
        MAIN / "client" / "dll_link.py": Path("client") / "dll_link.py",
        ROOT / "data" / "dash_unlock_flags.json": Path("data") / "dash_unlock_flags.json",
        ROOT / "data" / "missions.json": Path("data") / "missions.json",
        # the seed save, made by the client (client/new_save.py)
        ROOT / "data" / "flag_names.json": Path("data") / "flag_names.json",
        ROOT / "tools" / "save" / "make_seed_save.py": Path("client") / "make_seed_save.py",
        ROOT / "tools" / "save" / "save_checksum.py": Path("client") / "save_checksum.py",
        ROOT / "tools" / "save" / "set_flag.py": Path("client") / "set_flag.py",
    }),
}


def stage(dest_parent: Path, world: str = "main") -> Path:
    pkg, copied = WORLDS[world]
    dest = dest_parent / pkg
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT / "apworld" / pkg, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for src, rel in copied.items():
        if (ROOT / "apworld" / pkg / rel).exists():
            raise SystemExit(f"{pkg}/{rel} exists in the source but is copied from {src}: delete one")
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--world", choices=sorted(WORLDS), default="main")
    ap.add_argument("--stage-only", metavar="DIR", type=Path,
                    help="write the unzipped package into DIR instead of building a zip")
    ap.add_argument("--out", type=Path, help="default: build/<package>.apworld")
    args = ap.parse_args()
    pkg_name = WORLDS[args.world][0]

    if args.stage_only:
        print(stage(args.stage_only, args.world))
        return
    out = args.out or ROOT / "build" / f"{pkg_name}.apworld"
    tmp = ROOT / "build" / "stage"
    pkg = stage(tmp, args.world)
    # a zipped world's manifest also carries the container version, as AP's own
    # "Build APWorlds" tool writes it (worlds/Files.py, container_version = 7)
    manifest_path = pkg / "archipelago.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(version=7, compatible_version=7)
    manifest_path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(tmp).as_posix())
    shutil.rmtree(tmp)
    print(out)


if __name__ == "__main__":
    main()
