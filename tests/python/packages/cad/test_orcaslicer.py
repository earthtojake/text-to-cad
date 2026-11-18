"""``cad.orcaslicer``: complete OrcaSlicer presets for its command line.

OrcaSlicer's command line slices with defaults when a preset only holds its differences from a parent, and
refuses a process whose ``compatible_printers`` doesn't name the printer (it ignores compatibility conditions).
These tests build a tiny profile tree of their own, shaped like Orca's, and never read this computer's own
OrcaSlicer folders: the home, the app's profiles and the variables that name config folders are the test's.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad import orcaslicer  # noqa: E402
from cad._internal.refused import ArgumentRefused  # noqa: E402
from cad.orcaslicer import _presets  # noqa: E402


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


class OrcaSlicerPresets(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.home = self.root / "home"
        self.home.mkdir()
        # Nothing of this computer's OrcaSlicer: its home, its config variables and the app's own profiles are ours.
        environ = {key: value for key, value in os.environ.items()
                   if key not in ("APPDATA", "XDG_CONFIG_HOME", "ProgramFiles")}
        for patch in (mock.patch.dict(os.environ, environ, clear=True),
                      mock.patch.object(Path, "home", classmethod(lambda cls: self.home)),
                      mock.patch.object(_presets, "app_profiles", lambda: [])):
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_saved_preset_is_merged_with_every_parent(self) -> None:
        profile_tree(self.root)
        found, _ = _presets.index([self.root])
        process, system = _presets.merged(found, "process", "My 0.20mm")
        self.assertEqual((process["layer_height"], process["wall_loops"]), ("0.2", "3"))
        self.assertEqual(system, "0.20mm @Acme")

    def inside(self) -> None:
        """The test's folder made the current one, so a relative path to it is on its drive (Windows: the checkout
        and the temporary folder can be on two drives, which no relative path joins); the folder before put back
        first, before the folder goes."""
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.home)

    def test_relative_preset_file_resolves_an_absolute_index(self) -> None:
        profile_tree(self.root)
        self.inside()
        found, _ = _presets.index([self.root])
        relative = os.path.relpath(self.root / "user/default/process/mine.json")
        process, system = _presets.merged(found, "process", relative)
        self.assertEqual((process["layer_height"], process["wall_loops"]), ("0.2", "3"))
        self.assertEqual(system, "0.20mm @Acme")

    def test_absolute_preset_file_resolves_a_relative_index(self) -> None:
        profile_tree(self.root)
        self.inside()
        found, _ = _presets.index([Path(os.path.relpath(self.root))])
        process, _ = _presets.merged(found, "process", str(self.root / "user/default/process/mine.json"))
        self.assertEqual(process["layer_height"], "0.2")

    def test_the_listing_shows_only_selectable_presets(self) -> None:
        profile_tree(self.root)
        listed = orcaslicer.presets("machine", profiles=(str(self.root),))
        self.assertEqual(("machine", ("Acme One 0.4 nozzle",)), (listed.kind, listed.names))
        self.assertEqual(("0.20mm @Acme", "My 0.20mm"), orcaslicer.presets("process", profiles=(str(self.root),)).names)
        self.assertEqual(("My 0.20mm",), orcaslicer.presets("process", match="my", profiles=(str(self.root),)).names)

    def test_written_presets_are_complete_and_name_the_printer(self) -> None:
        profile_tree(self.root / "profiles")
        written = orcaslicer.complete(printer="Acme One 0.4 nozzle", process="My 0.20mm", filament=("Generic PLA",),
                                      out=self.root / "out", profiles=(str(self.root / "profiles"),))
        out = (self.root / "out").resolve()
        self.assertEqual((out / "printer.json", out / "process.json", (out / "filament-1.json",)),
                         (written.printer, written.process, written.filaments))
        read = lambda path: json.loads(path.read_text(encoding="utf-8"))
        printer, process, filament = read(written.printer), read(written.process), read(written.filaments[0])
        self.assertEqual((printer["bed_shape"], printer["inherits"], printer["from"]),
                         ("0x0,200x200", "Acme One 0.4 nozzle", "User"))
        self.assertEqual((process["compatible_printers"], process["inherits"], process["wall_loops"]),
                         (["Acme One 0.4 nozzle"], "0.20mm @Acme", "3"))
        self.assertEqual((filament["compatible_printers"], filament["nozzle_temperature"]),
                         (["Acme One 0.4 nozzle"], ["210"]))

    def test_lists_presets_of_the_flatpak_build(self) -> None:
        profile_tree(self.home / ".var/app/com.orcaslicer.OrcaSlicer/config/OrcaSlicer/system")
        self.assertEqual(("Acme One 0.4 nozzle",), orcaslicer.presets("machine").names)

    def test_an_unknown_preset_name_is_refused_with_a_hint_and_nothing_is_written(self) -> None:
        profile_tree(self.root)
        found, _ = _presets.index([self.root])
        with self.assertRaises(ArgumentRefused) as raised:
            _presets.merged(found, "machine", "No Such Printer")
        self.assertIn("cad orcaslicer presets machine", str(raised.exception))
        with self.assertRaisesRegex(ArgumentRefused, "No filament preset named 'No Such PLA'"):
            orcaslicer.complete(printer="Acme One 0.4 nozzle", process="0.20mm @Acme", filament=("No Such PLA",),
                                out=self.root / "out", profiles=(str(self.root),))
        self.assertFalse((self.root / "out").exists(), "every preset is resolved before a file is written")

    def test_a_parent_chain_that_never_ends_is_refused(self) -> None:
        write(self.root, "Loop/process/loop.json", {"type": "process", "name": "Loop", "inherits": "Loop"})
        found, _ = _presets.index([self.root])
        with self.assertRaisesRegex(ArgumentRefused, "Can't resolve parent 'Loop' of process preset 'Loop'"):
            _presets.merged(found, "process", "Loop")

    def test_presets_with_a_byte_order_mark_are_read(self) -> None:
        # Snapmaker ships its fdm_process_common.json so, and other vendors ship a parent of that name.
        profile_tree(self.root)
        write(self.root, "Other/process/common.json", {"type": "process", "name": "acme_process",
                                                       "instantiation": "false", "wall_loops": "5"})
        for relative in ("Acme/process/common.json", "Acme/process/fine.json"):
            path = self.root / relative
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
        found, selectable = _presets.index([self.root])
        self.assertIn(("process", "0.20mm @Acme"), selectable)
        process, _ = _presets.merged(found, "process", "0.20mm @Acme")
        self.assertEqual(process["wall_loops"], "2")

    def test_a_preset_file_that_fails_to_parse_is_named(self) -> None:
        profile_tree(self.root)
        (self.root / "Acme/process/broken.json").write_text("{", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            _presets.index([self.root])
        self.assertIn("broken.json", stderr.getvalue())

    def test_a_filament_several_vendors_ship_is_the_one_listing_the_printer(self) -> None:
        # Bambu Lab and Snapmaker both ship `Generic PETG`, each for its own printers. "Able" sorts first.
        profile_tree(self.root / "profiles")
        for vendor, printer in (("Able", "Able Two 0.4 nozzle"), ("Acme", "Acme One 0.4 nozzle")):
            write(self.root / "profiles", f"{vendor}/filament/petg.json",
                  {"type": "filament", "name": "Generic PETG", "from": "system", "instantiation": "true",
                   "compatible_printers": [printer], "filament_vendor": [vendor]})
        written = orcaslicer.complete(printer="Acme One 0.4 nozzle", process="0.20mm @Acme", filament=("Generic PETG",),
                                      out=self.root / "out", profiles=(str(self.root / "profiles"),))
        filament = json.loads(written.filaments[0].read_text(encoding="utf-8"))
        self.assertEqual(filament["filament_vendor"], ["Acme"])

    def test_a_preset_several_vendors_ship_and_none_lists_the_printer_is_the_nearest(self) -> None:
        profile_tree(self.root)
        for vendor in ("Able", "Acme"):
            write(self.root, f"{vendor}/filament/petg.json", {"type": "filament", "name": "Generic PETG"})
        found, _ = _presets.index([self.root])
        printer = ("Acme One 0.4 nozzle", self.root / "Acme/machine/acme.json")
        self.assertEqual(_presets.locate(found, "filament", "Generic PETG", printer),
                         self.root / "Acme/filament/petg.json")


if __name__ == "__main__":
    unittest.main()
