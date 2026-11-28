"""A KiCad board and a KiCad schematic shared by ``cad share`` to the share service itself, run on this computer
(``apps/share/serve.mjs``: the real Worker, ``tests/python/support/share_service.py``), then imported by ``cad import`` as
another computer imports a share.

What a share of each holds, as its manifest says once unsealed: the file itself and what an import needs to open it and
work on it -- of a board, its project file, its custom rules, its project's footprint and symbol libraries and the 3D
model files its footprints name in the project (a VRML name with the STEP beside it, which the viewer's 3D draws); of
a schematic, every sheet of its hierarchy, its project file and its project's symbol libraries -- each at its path
under the files' root, which a checkout's root caps; never a file of the folder that neither names (a note, the
person's local settings, a sheet no sheet draws), nor a library of KiCad's. A file outside the root, and one named and
gone, is left out and said. Its view is the one the engine wrote into the file's folder of cad's cache: the board's
plot alone, in 2D, whatever models its project holds; a schematic's sheets, a page each, and its hierarchy's index. An import writes every file byte for byte, and says which is the file the share is of: the board, or
the root of the hierarchy, whichever of its sheets was shared, since its root draws the same pages.

An engine of this file's own writes each view; no KiCad runs (the board is drawn as saved, as where its refill is
off). The fixtures are made in a temporary folder: the KiCad suite's board and schematic, and STEPs build123d writes.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon, share_service
from tests.python.support.kicad_board import BOARD, MODELS, write_board
from tests.python.support.kicad_schematic import write_schematic, write_symbol_libraries
from tests.python.support.paths import SOURCE_PATH, add_sources

add_sources()

NO_PROXY = {"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
_PLACED = "(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))"
# The board's resistor stands on a model of a folder beside its project's, which a checkout's root leaves out; its LED
# on the project's own, on a lens named by its VRML (the STEP beside it is what the view draws), and on one gone.
SHARED_BOARD = BOARD.replace(MODELS["R1"], f'(model "${{KIPRJMOD}}/../vendor/res.step" {_PLACED}').replace(
    MODELS["D1"], f'{MODELS["D1"]}\n  (model "${{KIPRJMOD}}/models/lens.wrl" {_PLACED}\n'
                  f'  (model "${{KIPRJMOD}}/models/gone.step" {_PLACED}')
FOOTPRINTS = ('(fp_lib_table (version 7)\n'
              '  (lib (name "blinky")(type "KiCad")(uri "${KIPRJMOD}/lib/blinky.pretty")(options "")(descr ""))\n'
              '  (lib (name "Resistor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Resistor_SMD.pretty")(options "")'
              '(descr ""))\n)\n')


def _symbols(*names: str) -> str:
    """A project's ``sym-lib-table`` listing its own libraries ``names`` (``${KIPRJMOD}/lib/<name>.kicad_sym``) and
    one of KiCad's."""
    rows = "".join(f'  (lib (name "{name}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{name}.kicad_sym")(options "")'
                   '(descr ""))\n' for name in names)
    return (f'(sym_lib_table (version 7)\n{rows}  (lib (name "Device_KiCad")(type "KiCad")'
            '(uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym")(options "")(descr ""))\n)\n')


class KiCadShare(unittest.TestCase):
    """The commands, run as a person runs them, with an engine, a state and a cache of this file's own, and the share
    service running beside them."""

    @classmethod
    def setUpClass(cls) -> None:
        from build123d import Box, export_step

        cls.given = engine_daemon.isolate(cls.addClassCleanup)
        cls.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="share-kicad-")))
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.origin = share_service.start(cls.addClassCleanup)
        patch = mock.patch.dict(os.environ, NO_PROXY)
        patch.start()
        cls.addClassCleanup(patch.stop)
        cls.cache = Path(cls.given["CAD_CACHE_DIR"])

        # The board's project, a checkout of its own: its root caps the share's files' root.
        cls.board = cls.base / "workspace" / "blinky"
        (cls.board / ".git").mkdir(parents=True)
        (cls.board / "models").mkdir()
        write_board(cls.board).write_text(SHARED_BOARD, encoding="utf-8")
        export_step(Box(1.6, 0.8, 0.6), str(cls.board / "models" / "led.step"))
        export_step(Box(1, 1, 1), str(cls.board / "models" / "lens.step"))
        (cls.board / "models" / "lens.wrl").write_text("#VRML V2.0 utf8\n", encoding="utf-8")
        (cls.base / "workspace" / "vendor").mkdir()
        shutil.copyfile(cls.board / "models" / "lens.step", cls.base / "workspace" / "vendor" / "res.step")
        (cls.board / "blinky.kicad_pro").write_text(json.dumps({"meta": {"filename": "blinky.kicad_pro", "version": 3}}),
                                                     encoding="utf-8")
        (cls.board / "blinky.kicad_dru").write_text('(version 1)\n(rule "wide" (constraint track_width (min 0.2mm)))\n',
                                                     encoding="utf-8")
        (cls.board / "fp-lib-table").write_text(FOOTPRINTS, encoding="utf-8")
        (cls.board / "sym-lib-table").write_text(_symbols("blinky"), encoding="utf-8")
        (cls.board / "lib" / "blinky.pretty").mkdir(parents=True)
        for name in ("R_0603", "LED_0603"):
            (cls.board / "lib" / "blinky.pretty" / f"{name}.kicad_mod").write_text(f'(footprint "{name}")\n',
                                                                                  encoding="utf-8")
        (cls.board / "lib" / "blinky.kicad_sym").write_text(
            '(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor"))\n', encoding="utf-8")
        # What a share leaves: a note, the person's own settings of the project.
        (cls.board / "notes.txt").write_text("mine\n", encoding="utf-8")
        (cls.board / "blinky.kicad_prl").write_text("{}\n", encoding="utf-8")

        # The schematic's project: two sheets, its symbol libraries, a sheet no sheet draws and a note.
        cls.schematic = cls.base / "divider"
        write_schematic(cls.schematic)
        libraries = write_symbol_libraries(cls.schematic / "lib")
        (cls.schematic / "sym-lib-table").write_text(_symbols(*libraries), encoding="utf-8")
        shutil.copyfile(cls.schematic / "load.kicad_sch", cls.schematic / "stray.kicad_sch")
        (cls.schematic / "notes.txt").write_text("mine\n", encoding="utf-8")
        cls.libraries = sorted(f"lib/{name}.kicad_sym" for name in libraries)

    def env(self, **more: str) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.origin, "CAD_TELEMETRY": "0",
                "CAD_UPDATE_CHECK": "0", **NO_PROXY, **more}

    def shared(self, target: str, cwd: Path) -> dict[str, Any]:
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "share", target, "--yes", "--json"],
                                 env=self.env(), cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return json.loads(done.stdout)

    def imported(self, link: str) -> tuple[dict[str, Any], Path]:
        """``cad import`` of ``link`` on another computer, with a state, a cache and an engine folder of its own: what it
        said, and the folder it wrote."""
        other = Path(tempfile.mkdtemp(prefix="elsewhere-", dir=self.base))
        folder = other / "imported"
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "import", link, str(folder), "--json"],
                                 env=self.env(CAD_STATE_DIR=str(other / "state"), CAD_CACHE_DIR=str(other / "cache"),
                                              CAD_ENGINE_DIR=str(other / "engine")), cwd=other)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return json.loads(done.stdout), folder

    def view_of(self, path: Path) -> set[str]:
        """The files of the view bundle the engine wrote into ``path``'s folder of cad's cache, a share's view."""
        from cad.engine.ids import file_id

        folder = self.cache / "documents" / file_id(path) / "view"
        return {*json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["files"], "manifest.json"}

    def same_files(self, folder: Path, root: Path, expected: list[str]) -> None:
        """``folder`` holds ``expected`` and nothing else, each byte for byte the file at its path under ``root``."""
        self.assertEqual(sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()),
                         expected)
        for path in expected:
            self.assertEqual((folder / path).read_bytes(), (root / path).read_bytes(), path)

    def unplaced(self, found: dict[str, Any]) -> None:
        """The share's view, as a page reads it, names no place of this computer's: no folder of it, and not the id
        this computer names the file by (a digest of its path), but the share's own for it (``document_of``)."""
        from cad.engine.ids import file_id
        from cad_server import sharing

        view = share_service.view(self.origin, found["id"])
        local = file_id(found["document"]["path"])
        for path, data in view.items():
            self.assertNotIn(str(self.base).encode(), data, path)
            self.assertNotIn(local.encode(), data, path)
        named = sharing.document_of(sharing.Share(self.origin, found["id"], "", ""))
        self.assertEqual(json.loads(view["manifest.json"])["document"]["id"], named)

    def test_a_board_shares_its_project_and_its_view_and_imports_back_byte_for_byte(self) -> None:
        found = self.shared("blinky.kicad_pcb", self.board)
        manifest = share_service.manifest(self.origin, found["id"])
        expected = ["blinky.kicad_dru", "blinky.kicad_pcb", "blinky.kicad_pro", "fp-lib-table",
                    "lib/blinky.kicad_sym", "lib/blinky.pretty/LED_0603.kicad_mod", "lib/blinky.pretty/R_0603.kicad_mod",
                    "models/led.step", "models/lens.step", "models/lens.wrl", "sym-lib-table"]
        self.assertEqual((manifest["name"], manifest["entry"], manifest["made"], sorted(manifest["files"])),
                         ("blinky.kicad_pcb", None, None, expected))
        # The model beside the checkout's root is outside it, and the one named and gone is gone: each said.
        left = {(row["path"], row["reason"]) for row in found["files"]["left_out"]}
        self.assertEqual(left, {(str(self.base / "workspace" / "vendor" / "res.step"), "outside"),
                                (str(self.board / "models" / "gone.step"), "gone")})
        self.assertEqual((found["document"]["kind"], found["files"]["file"], found["files"]["count"]),
                         ("kicad_pcb", "blinky.kicad_pcb", len(expected)))
        # Its view is the bundle the engine wrote, but the picture a page kept: the board's plot alone, in 2D, though
        # its project holds the LED's and the lens's STEPs, which went among its files.
        view = set(manifest["view"])
        self.assertEqual(view, self.view_of(self.board / "blinky.kicad_pcb") - {"thumbnail.png"})
        self.assertEqual(view, {"manifest.json", "plot.json"})
        self.assertIn("its view (its layers, in 2D)", found["sent"]["what"])
        self.assertIsNone(found["sent"]["parts"])
        self.unplaced(found)

        imported, folder = self.imported(found["view"])
        self.assertEqual((imported["file"], imported["entry"], imported["files"]["count"]), ("blinky.kicad_pcb", None,
                                                                                        len(expected)))
        self.assertEqual(imported["next"], [f"cad viewer {folder / 'blinky.kicad_pcb'}"])
        self.same_files(folder, self.board, expected)

    def test_a_schematic_shares_every_sheet_of_its_hierarchy_and_a_import_opens_its_root(self) -> None:
        expected = sorted(["divider.kicad_pro", "divider.kicad_sch", "load.kicad_sch", "sym-lib-table",
                           *self.libraries])
        pages = {"sheets/~2F.json", "sheets/~2FLoad~2F.json"}
        links = set()
        # Its root sheet, and the sheet it draws, shared on its own: each its own share of the same files and pages.
        for shared in ("divider.kicad_sch", "load.kicad_sch"):
            with self.subTest(shared=shared):
                found = self.shared(shared, self.schematic)
                links.add(found["view"])
                manifest = share_service.manifest(self.origin, found["id"])
                self.assertEqual((manifest["name"], manifest["entry"], sorted(manifest["files"])),
                                 (shared, None, expected))
                self.assertEqual((found["files"]["file"], found["files"]["left_out"]), (shared, []))
                self.assertEqual(set(manifest["view"]), {"manifest.json", "schematic.json", *pages})
                self.assertIn("its view (2 sheets)", found["sent"]["what"])
                self.unplaced(found)
                # An import finds the root the hierarchy is drawn from, which draws the same pages.
                imported, folder = self.imported(found["view"])
                self.assertEqual(imported["file"], "divider.kicad_sch")
                self.same_files(folder, self.schematic, expected)
        self.assertEqual(len(links), 2)



if __name__ == "__main__":
    unittest.main()
