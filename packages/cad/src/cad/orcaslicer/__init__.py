"""``cad.orcaslicer``: the orcaslicer integration -- complete OrcaSlicer presets for its command line.

OrcaSlicer stores a preset as its differences from a parent (``inherits``), and its command line neither fills
the parent's settings in nor reads compatibility conditions: given a preset as OrcaSlicer saved it, it slices with
defaults, and it refuses a process whose ``compatible_printers`` does not name the printer. That is what is missing
without us, and all this integration adds:

- ``presets(kind, match=...)`` lists the presets a person can select, of one kind (``machine``, ``process`` or
  ``filament``), from their own OrcaSlicer folders and the app's built-in profiles: ``cad orcaslicer presets``.
- ``complete(printer=..., process=..., filament=(...), out=...)`` writes a printer, a process and each filament
  complete into a folder -- every parent merged in, the process and filaments naming the printer as compatible,
  each saved as a user preset that ``inherits`` its system preset -- as ``printer.json``, ``process.json`` and
  ``filament-N.json``, ready for OrcaSlicer's ``--load-settings`` and ``--load-filaments``: ``cad orcaslicer
  complete``.

Everything else is OrcaSlicer's own: the slice is its command line, run as it is, and its app opens a model for
the person. Nothing here runs OrcaSlicer, needs the engine or the CAD kernel, or reaches the network: it reads
and writes JSON files, with the standard library alone, so the integration has no extra.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = ["Completed", "Presets", "complete", "presets"]


@dataclass(frozen=True)
class Presets:
    """The selectable presets of one kind, by name, sorted."""

    kind: str
    names: tuple[str, ...]

    def human_lines(self) -> list[str]:
        return list(self.names)


@dataclass(frozen=True)
class Completed:
    """The complete presets written: the printer's, the process's and each filament's file, in order."""

    printer: Path
    process: Path
    filaments: tuple[Path, ...]

    def human_lines(self) -> list[str]:
        return json.dumps({"printer": str(self.printer), "process": str(self.process),
                           "filaments": [str(path) for path in self.filaments]}, indent=1).splitlines()


def presets(kind: Literal["machine", "process", "filament"], *, match: str = "",
            profiles: tuple[str, ...] = ()) -> Presets:
    """List the OrcaSlicer presets of one kind a person can select.

    They are searched in the folders given first, then the person's own OrcaSlicer presets, then the app's
    built-in profiles (macOS, Windows, Linux and the Flathub build's folders).

    kind: machine (a printer), process or filament.
    match: only names containing this text, in any case.
    profiles: another folder of OrcaSlicer presets to search first; once per folder.
    """
    from cad.orcaslicer import _presets

    _found, selectable = _presets.index(_presets.roots(list(profiles)))
    return Presets(kind, tuple(name for found_kind, name in sorted(selectable)
                               if found_kind == kind and match.lower() in name.lower()))


def complete(*, printer: str, process: str, filament: tuple[str, ...] = (), out: Path = Path("presets"),
             profiles: tuple[str, ...] = ()) -> Completed:
    """Write a printer, a process and filaments complete, for OrcaSlicer's command line.

    Each is merged with every parent it inherits from, the process and each filament name the printer as
    compatible, and each is saved as a user preset of the system preset it comes from: printer.json,
    process.json and filament-N.json in the folder. Where several vendors ship a preset of one name, the one
    that lists the printer, else the one nearest it, is taken.

    printer: the printer (machine) preset's name, or a preset JSON file.
    process: the process preset's name, or a preset JSON file.
    filament: a filament preset's name or file; once per material, in the printer's filament order.
    out: the folder the complete presets are written into.
    profiles: another folder of OrcaSlicer presets to search first; once per folder.
    """
    from cad._internal.refused import ArgumentRefused
    from cad.orcaslicer import _presets

    if not filament:
        raise ArgumentRefused("give at least one --filament")
    found, _selectable = _presets.index(_presets.roots(list(profiles)))
    printer_path = _presets.locate(found, "machine", printer)
    machine, printer_system = _presets.merged(found, "machine", str(printer_path))
    machine.update({"from": "User", "inherits": printer_system})
    made_for = (printer_system, printer_path)
    settings, process_system = _presets.merged(found, "process", process, made_for)
    settings.update({"from": "User", "inherits": process_system, "compatible_printers": [printer_system]})
    materials = []
    for ref in filament:
        material, filament_system = _presets.merged(found, "filament", ref, made_for)
        material.update({"from": "User", "inherits": filament_system, "compatible_printers": [printer_system]})
        materials.append(material)
    # Every preset is resolved before any file is written: a name that fails leaves the folder as it was.
    folder = Path(out).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    written = {"printer.json": machine, "process.json": settings,
               **{f"filament-{number}.json": material for number, material in enumerate(materials, start=1)}}
    for name, preset in written.items():
        (folder / name).write_text(json.dumps(preset, indent=1), encoding="utf-8")
    return Completed(folder / "printer.json", folder / "process.json",
                     tuple(folder / f"filament-{number}.json" for number in range(1, len(materials) + 1)))
