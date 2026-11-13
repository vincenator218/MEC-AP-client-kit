#!/usr/bin/env python3
"""
Assemble and zip the Mirror's Edge Catalyst apworld.

    python tools/build_apworld.py                    # -> build/mirrors_edge_catalyst.apworld
    python tools/build_apworld.py --stage-only DIR   # unzipped package in DIR (for running tests)

The package source is apworld/mirrors_edge_catalyst/. Two things are copied in so they
keep a single home in the kit: data/items.json, data/locations.json, data/named_challenges.json, and
tools/client/mec_memory.py (the memory layer, shared with MEC_MoveToggles.pyw).
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "mirrors_edge_catalyst"
SRC = ROOT / "apworld" / PKG
COPIED = {
    ROOT / "data" / "items.json": Path("data") / "items.json",
    ROOT / "data" / "locations.json": Path("data") / "locations.json",
    ROOT / "data" / "named_challenges.json": Path("data") / "named_challenges.json",
    ROOT / "tools" / "client" / "mec_memory.py": Path("client") / "mec_memory.py",
}


def stage(dest_parent: Path) -> Path:
    dest = dest_parent / PKG
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for src, rel in COPIED.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--stage-only", metavar="DIR", type=Path,
                    help="write the unzipped package into DIR instead of building a zip")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / f"{PKG}.apworld")
    args = ap.parse_args()

    if args.stage_only:
        print(stage(args.stage_only))
        return
    tmp = ROOT / "build" / "stage"
    pkg = stage(tmp)
    # a zipped world's manifest also carries the container version, as AP's own
    # "Build APWorlds" tool writes it (worlds/Files.py, container_version = 7)
    manifest_path = pkg / "archipelago.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(version=7, compatible_version=7)
    manifest_path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(tmp).as_posix())
    shutil.rmtree(tmp)
    print(args.out)


if __name__ == "__main__":
    main()
