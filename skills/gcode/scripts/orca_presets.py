#!/usr/bin/env python3
"""Make complete OrcaSlicer presets for its command line.

OrcaSlicer stores a preset as its differences from a parent (`inherits`), and
its command line neither fills the parent's settings in nor reads compatibility
conditions: it slices with defaults, or refuses the process as incompatible.
This writes each chosen preset complete, with the process and filaments naming
the printer as compatible, ready for `--load-settings` and `--load-filaments`.
It reads and writes JSON files and nothing else.

    python orca_presets.py --list machine --match "MK4S 0.4"
    python orca_presets.py --printer "Prusa MK4S 0.4 nozzle" \\
        --process "0.20mm SPEED @MK4S 0.4" --filament "Prusa Generic PLA @MK4S" --out presets
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

KINDS = ("machine", "process", "filament")


def profile_roots(extra: list[str]) -> list[Path]:
    """Where presets live, most specific first: given folders, the user's own, Orca's copies, the app's."""
    home = Path.home()
    data_dirs = [home / "Library" / "Application Support" / "OrcaSlicer",
                 Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "OrcaSlicer"]
    if os.environ.get("APPDATA"):
        data_dirs.append(Path(os.environ["APPDATA"]) / "OrcaSlicer")
    roots = [Path(folder) for folder in extra]
    roots += [data / "user" for data in data_dirs] + [data / "system" for data in data_dirs]
    roots.append(Path("/Applications/OrcaSlicer.app/Contents/Resources/profiles"))
    roots.append(Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "OrcaSlicer" / "resources" / "profiles")
    return [root for root in roots if root.is_dir()]


def index_presets(roots: list[Path]) -> tuple[dict[tuple[str, str], list[Path]], set[tuple[str, str]]]:
    found: dict[tuple[str, str], list[Path]] = {}
    selectable: set[tuple[str, str]] = set()
    for root in roots:
        for path in sorted(root.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("type") in KINDS and isinstance(data.get("name"), str):
                key = (data["type"], data["name"])
                found.setdefault(key, []).append(path)
                if data.get("instantiation") != "false":
                    selectable.add(key)
    return found, selectable


def complete(index: dict[tuple[str, str], list[Path]], kind: str, ref: str) -> tuple[dict, str]:
    """The preset merged with every parent, and the selectable system preset it comes from."""
    path = Path(ref).expanduser()
    if not path.is_file():
        if (kind, ref) not in index:
            sys.exit(f"No {kind} preset named {ref!r}; list them with --list {kind}.")
        path = index[(kind, ref)][0]
    chain = [json.loads(path.read_text(encoding="utf-8"))]
    while chain[-1].get("inherits"):
        parents = index.get((kind, chain[-1]["inherits"]))
        if not parents or len(chain) > 20:
            sys.exit(f"Can't resolve parent {chain[-1]['inherits']!r} of {kind} preset {chain[0].get('name')!r}.")
        # A parent of the same name can exist under several vendors: take the one nearest the child.
        path = max(parents, key=lambda parent: len(os.path.commonpath([parent, path])))
        chain.append(json.loads(path.read_text(encoding="utf-8")))
    merged: dict = {}
    for layer in reversed(chain):
        merged.update(layer)
    system = next((layer["name"] for layer in chain
                   if layer.get("from") == "system" and layer.get("instantiation") == "true"), chain[0]["name"])
    return merged, system


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", choices=KINDS, help="print the selectable presets of one kind")
    parser.add_argument("--match", default="", help="with --list, only names containing this text")
    parser.add_argument("--printer", help="printer preset name, or a preset JSON file")
    parser.add_argument("--process", help="process preset name, or a preset JSON file")
    parser.add_argument("--filament", action="append", default=[], help="filament preset name or file; once per material")
    parser.add_argument("--profiles", action="append", default=[], help="another folder of OrcaSlicer presets to search")
    parser.add_argument("--out", default="presets", help="folder for the complete presets")
    args = parser.parse_args()

    index, selectable = index_presets(profile_roots(args.profiles))
    if args.list:
        for kind, name in sorted(selectable):
            if kind == args.list and args.match.lower() in name.lower():
                print(name)
        return 0
    if not (args.printer and args.process and args.filament):
        parser.error("give --printer, --process and at least one --filament, or --list")

    printer, printer_system = complete(index, "machine", args.printer)
    printer.update({"from": "User", "inherits": printer_system})
    process, process_system = complete(index, "process", args.process)
    process.update({"from": "User", "inherits": process_system, "compatible_printers": [printer_system]})
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    written = {"printer": out / "printer.json", "process": out / "process.json", "filaments": []}
    written["printer"].write_text(json.dumps(printer, indent=1), encoding="utf-8")
    written["process"].write_text(json.dumps(process, indent=1), encoding="utf-8")
    for number, ref in enumerate(args.filament, start=1):
        filament, filament_system = complete(index, "filament", ref)
        filament.update({"from": "User", "inherits": filament_system, "compatible_printers": [printer_system]})
        path = out / f"filament-{number}.json"
        path.write_text(json.dumps(filament, indent=1), encoding="utf-8")
        written["filaments"].append(path)
    print(json.dumps({key: [str(p) for p in value] if isinstance(value, list) else str(value)
                      for key, value in written.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
