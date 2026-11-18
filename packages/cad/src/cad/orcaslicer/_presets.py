"""OrcaSlicer's presets read where OrcaSlicer keeps them, each merged with every parent.

OrcaSlicer stores a preset as its differences from a parent (``inherits``), and its command line neither fills
the parent's settings in nor reads compatibility conditions: it slices with defaults, or refuses the process as
incompatible. What is here finds the presets (``roots``, ``index``), the one file a name means (``locate``) and a
preset merged with every parent (``merged``). It reads JSON files and nothing else. The standard library alone.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cad._internal.refused import ArgumentRefused

KINDS = ("machine", "process", "filament")
# The longest parent chain followed: a preset whose parents go on past it is refused, never looped over.
_DEEPEST = 20

#: Each preset's files by ``(kind, name)``, several where vendors ship a preset of one name.
Index = dict[tuple[str, str], list[Path]]


def roots(extra: list[str]) -> list[Path]:
    """Where presets live, most specific first: given folders, the user's own, Orca's copies, the app's."""
    home = Path.home()
    data_dirs = [home / "Library" / "Application Support" / "OrcaSlicer",
                 Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "OrcaSlicer"]
    if os.environ.get("APPDATA"):
        data_dirs.append(Path(os.environ["APPDATA"]) / "OrcaSlicer")
    # The Flathub build keeps its config under the sandbox's own XDG_CONFIG_HOME
    # (current app id, then the id it had before OrcaSlicer 2.3.2).
    for app_id in ("com.orcaslicer.OrcaSlicer", "io.github.softfever.OrcaSlicer"):
        data_dirs.append(home / ".var" / "app" / app_id / "config" / "OrcaSlicer")
    found = [Path(folder) for folder in extra]
    found += [data / "user" for data in data_dirs] + [data / "system" for data in data_dirs]
    found += app_profiles()
    return [root for root in found if root.is_dir()]


def app_profiles() -> list[Path]:
    """The profiles the app itself ships: in its macOS bundle, and its Windows install."""
    return [Path("/Applications/OrcaSlicer.app/Contents/Resources/profiles"),
            Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "OrcaSlicer" / "resources" / "profiles"]


def read(path: Path) -> dict:
    # Some vendors' files start with a UTF-8 byte-order mark (Snapmaker's fdm_process_common.json).
    return json.loads(path.read_text(encoding="utf-8-sig"))


def index(folders: list[Path]) -> tuple[Index, set[tuple[str, str]]]:
    """Every preset under ``folders`` by kind and name, and those a person can select (a parent alone, with
    ``instantiation`` false, is not). A file that fails to read is said on stderr and left out."""
    found: Index = {}
    selectable: set[tuple[str, str]] = set()
    for root in folders:
        for path in sorted(root.rglob("*.json")):
            try:
                data = read(path)
            except (OSError, ValueError) as error:
                # A file left out may be another preset's parent, which would then come from another vendor.
                print(f"Skipped {path}: {error}", file=sys.stderr)
                continue
            if isinstance(data, dict) and data.get("type") in KINDS and isinstance(data.get("name"), str):
                key = (data["type"], data["name"])
                found.setdefault(key, []).append(path)
                if data.get("instantiation") != "false":
                    selectable.add(key)
    return found, selectable


def shared_path_depth(a: Path, b: Path) -> int:
    """Compare resolved paths; different Windows drives have no shared parent."""
    try:
        return len(Path(os.path.commonpath([a.resolve(), b.resolve()])).parts)
    except ValueError:
        return 0


def locate(found: Index, kind: str, ref: str, printer: tuple[str, Path] | None = None) -> Path:
    """The file of a preset given by file or by name. Several vendors can ship a preset of one name
    (``Generic PETG``): with a printer (its name and file), take the one that lists it as compatible,
    else the one nearest its file."""
    path = Path(ref).expanduser()
    if path.is_file():
        return path
    if (kind, ref) not in found:
        raise ArgumentRefused(f"No {kind} preset named {ref!r}; list them with cad orcaslicer presets {kind}.")
    candidates = found[(kind, ref)]
    if printer is None or len(candidates) == 1:
        return candidates[0]
    name, printer_path = printer
    return max(candidates, key=lambda candidate: (name in (read(candidate).get("compatible_printers") or []),
                                                  shared_path_depth(candidate, printer_path)))


def merged(found: Index, kind: str, ref: str, printer: tuple[str, Path] | None = None) -> tuple[dict, str]:
    """The preset merged with every parent, and the selectable system preset it comes from."""
    path = locate(found, kind, ref, printer)
    chain = [read(path)]
    while chain[-1].get("inherits"):
        parents = found.get((kind, chain[-1]["inherits"]))
        if not parents or len(chain) > _DEEPEST:
            raise ArgumentRefused(f"Can't resolve parent {chain[-1]['inherits']!r} of {kind} preset "
                                  f"{chain[0].get('name')!r}.")
        # A parent of the same name can exist under several vendors: take the one nearest the child.
        path = max(parents, key=lambda parent: shared_path_depth(parent, path))
        chain.append(read(path))
    whole: dict = {}
    for layer in reversed(chain):
        whole.update(layer)
    system = next((layer["name"] for layer in chain
                   if layer.get("from") == "system" and layer.get("instantiation") == "true"), chain[0]["name"])
    return whole, system
