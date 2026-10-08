"""skills/gcode/scripts/orca_presets.py: complete OrcaSlicer presets for its command line.

OrcaSlicer's command line slices with defaults when a preset only holds its
differences from a parent, and refuses a process whose `compatible_printers`
list doesn't name the printer (it ignores compatibility conditions). These
tests build a tiny profile tree of their own, shaped like Orca's.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.python.support.paths import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "skills/gcode/scripts"))
import orca_presets  # noqa: E402

SCRIPT = REPO_ROOT / "skills/gcode/scripts/orca_presets.py"


def write(root: Path, relative: str, data: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def profile_tree(root: Path) -> None:
    system = {"from": "system", "instantiation": "true"}
    write(root, "Acme/machine/common.json", {"type": "machine", "name": "acme_common", "instantiation": "false",
                                             "bed_shape": "0x0,200x200", "printer_notes": "ACME"})
    write(root, "Acme/machine/acme.json", {"type": "machine", "name": "Acme One 0.4 nozzle", "inherits": "acme_common",
                                           "nozzle_diameter": ["0.4"], **system})
    write(root, "Acme/process/common.json", {"type": "process", "name": "acme_process", "instantiation": "false",
                                             "wall_loops": "2", "compatible_printers_condition": "printer_notes=~/.*ACME.*/"})
    write(root, "Acme/process/fine.json", {"type": "process", "name": "0.20mm @Acme", "inherits": "acme_process",
                                           "layer_height": "0.2", "compatible_printers": [], **system})
    write(root, "Library/filament/pla.json", {"type": "filament", "name": "Generic PLA", "nozzle_temperature": ["210"], **system})
    # A user's saved preset: only its differences, and the system preset it comes from.
    write(root, "user/default/process/mine.json", {"type": "process", "name": "My 0.20mm", "from": "User",
                                                   "inherits": "0.20mm @Acme", "wall_loops": "3"})


class OrcaPresetsTests(unittest.TestCase):
    def test_a_saved_preset_is_merged_with_every_parent(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            profile_tree(Path(scratch))
            index, _ = orca_presets.index_presets([Path(scratch)])
            process, system = orca_presets.complete(index, "process", "My 0.20mm")
            self.assertEqual((process["layer_height"], process["wall_loops"]), ("0.2", "3"))
            self.assertEqual(system, "0.20mm @Acme")

    def test_relative_preset_file_resolves_an_absolute_index(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            profile_tree(root)
            index, _ = orca_presets.index_presets([root])
            relative = os.path.relpath(root / "user/default/process/mine.json")
            process, system = orca_presets.complete(index, "process", relative)
            self.assertEqual((process["layer_height"], process["wall_loops"]), ("0.2", "3"))
            self.assertEqual(system, "0.20mm @Acme")

    def test_absolute_preset_file_resolves_a_relative_index(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            profile_tree(root)
            index, _ = orca_presets.index_presets([Path(os.path.relpath(root))])
            process, _ = orca_presets.complete(index, "process", str(root / "user/default/process/mine.json"))
            self.assertEqual(process["layer_height"], "0.2")

    def test_list_shows_only_selectable_presets(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            profile_tree(Path(scratch))
            _, selectable = orca_presets.index_presets([Path(scratch)])
            self.assertIn(("machine", "Acme One 0.4 nozzle"), selectable)
            self.assertNotIn(("machine", "acme_common"), selectable)

    def test_written_presets_are_complete_and_name_the_printer(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            profile_tree(root / "profiles")
            subprocess.run([sys.executable, str(SCRIPT), "--profiles", str(root / "profiles"),
                            "--printer", "Acme One 0.4 nozzle", "--process", "My 0.20mm",
                            "--filament", "Generic PLA", "--out", str(root / "out")],
                           check=True, capture_output=True, env={"HOME": str(root), "PATH": ""})
            read = lambda name: json.loads((root / "out" / name).read_text(encoding="utf-8"))
            printer, process, filament = read("printer.json"), read("process.json"), read("filament-1.json")
            self.assertEqual((printer["bed_shape"], printer["inherits"]), ("0x0,200x200", "Acme One 0.4 nozzle"))
            self.assertEqual(process["compatible_printers"], ["Acme One 0.4 nozzle"])
            self.assertEqual(filament["compatible_printers"], ["Acme One 0.4 nozzle"])
            self.assertEqual(filament["nozzle_temperature"], ["210"])

    def test_an_unknown_preset_name_fails_with_a_hint(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            profile_tree(Path(scratch))
            index, _ = orca_presets.index_presets([Path(scratch)])
            with self.assertRaises(SystemExit) as raised:
                orca_presets.complete(index, "machine", "No Such Printer")
            self.assertIn("--list machine", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
