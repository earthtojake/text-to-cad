"""A board's 3D models (``cad.engine.formats.kicad.models3d``): which STEP on this computer each model a footprint
names is, or why none is -- read only in the board's folder and the 3D libraries named, every real path inside
them -- and what the plot payload carries of them (each part's models as written, the board's thickness).

Every tree here is written fresh in a temporary folder: a project folder, a library folder (standing in for
KiCad's installed 3D library) and a folder outside both.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import MODELS, write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad import models3d  # noqa: E402
from cad.engine.formats.kicad.board_index import read_board, read_index  # noqa: E402
from cad.engine.formats.kicad.models3d import library_roots, model_names, resolve_models  # noqa: E402
from cad.engine.formats.kicad.plot import build_plot  # noqa: E402


def touch(path: Path, text: str = "ISO-10303-21;\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Resolve(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(os.path.realpath(self._tmp.name))
        self.project, self.library, self.outside = base / "project", base / "library", base / "outside"
        self.board = touch(self.project / "board.kicad_pcb", "(kicad_pcb)")
        touch(self.project / "models" / "own.step")
        touch(self.project / "fp.3dshapes" / "plug.wrl", "#VRML V2.0 utf8\n")
        touch(self.library / "Resistor_SMD.3dshapes" / "R_0603.step")
        touch(self.library / "Package_SO.3dshapes" / "SOIC-8.stp")
        touch(self.library / "rel.3dshapes" / "x.step")
        touch(self.outside / "secret.step")
        touch(self.project / "notes.igs")

    def resolve(self, *names: str) -> dict:
        return {name: (answer.path, answer.reason) for name, answer in
                resolve_models(self.board, names, libraries=[str(self.library)]).items()}

    def test_each_variable_and_spelling_reads_its_folder(self) -> None:
        found = self.resolve("${KIPRJMOD}/models/own.step", "$(KIPRJMOD)/models/own.step",
                             "${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603.wrl",
                             "${KICAD6_3DMODEL_DIR}/Package_SO.3dshapes/SOIC-8.wrl", "$(KISYS3DMOD)/Resistor_SMD.3dshapes/R_0603.step",
                             "rel.3dshapes/x.wrl", "models/own.step")
        own = str(self.project / "models" / "own.step")
        self.assertEqual(found["${KIPRJMOD}/models/own.step"], (own, None))
        self.assertEqual(found["$(KIPRJMOD)/models/own.step"], (own, None))
        # A VRML name is the STEP beside it, .step or .stp; a relative name the project's, then the library's.
        self.assertEqual(found["${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603.wrl"][0],
                         str(self.library / "Resistor_SMD.3dshapes" / "R_0603.step"))
        self.assertEqual(found["${KICAD6_3DMODEL_DIR}/Package_SO.3dshapes/SOIC-8.wrl"][0],
                         str(self.library / "Package_SO.3dshapes" / "SOIC-8.stp"))
        self.assertIsNotNone(found["$(KISYS3DMOD)/Resistor_SMD.3dshapes/R_0603.step"][0])
        self.assertEqual(found["rel.3dshapes/x.wrl"][0], str(self.library / "rel.3dshapes" / "x.step"))
        self.assertEqual(found["models/own.step"], (own, None))
        answer = resolve_models(self.board, ["${KIPRJMOD}/models/own.step"], libraries=[])["${KIPRJMOD}/models/own.step"]
        info = os.stat(own)
        self.assertEqual((answer.file, answer.stamp), ("own.step", f"{info.st_mtime_ns}-{info.st_size}"))

    def test_a_project_text_variable_names_a_folder(self) -> None:
        self.board.with_suffix(".kicad_pro").write_text('{"text_variables": {"MINE": "models"}}', encoding="utf-8")
        self.assertEqual(self.resolve("${KIPRJMOD}/${MINE}/own.step")["${KIPRJMOD}/${MINE}/own.step"][1], None)
        # A variable nobody defines (the person's own, in their KiCad settings) names nothing.
        self.assertEqual(self.resolve("${MY_LIBRARY}/own.step")["${MY_LIBRARY}/own.step"], (None, "not-found"))

    def test_what_is_missing_says_why(self) -> None:
        found = self.resolve("${KIPRJMOD}/fp.3dshapes/plug.wrl", "${KICAD9_3DMODEL_DIR}/Nowhere.3dshapes/none.wrl",
                             "${KIPRJMOD}/notes.igs", "kicad-embed://part.step", "model.obj")
        self.assertEqual(found["${KIPRJMOD}/fp.3dshapes/plug.wrl"], (None, "vrml-only"))
        self.assertEqual(found["${KICAD9_3DMODEL_DIR}/Nowhere.3dshapes/none.wrl"], (None, "not-found"))
        self.assertEqual(found["${KIPRJMOD}/notes.igs"], (None, "not-step"))
        self.assertEqual(found["kicad-embed://part.step"], (None, "embedded"))
        self.assertEqual(found["model.obj"], (None, "not-step"))

    def test_nothing_outside_the_board_folder_and_the_libraries_is_read(self) -> None:
        link = self.project / "models" / "link.step"
        try:
            link.symlink_to(self.outside / "secret.step")
        except (OSError, NotImplementedError):
            link = None
        (self.project / "models" / "fake.step").mkdir()
        names = [str(self.outside / "secret.step"), "${KIPRJMOD}/../outside/secret.step", "../outside/secret.step",
                 "/etc/passwd", "${KIPRJMOD}/models/fake.step", "${KICAD9_3DMODEL_DIR}/../outside/secret.step"]
        if link is not None:
            names.append("${KIPRJMOD}/models/link.step")
        found = self.resolve(*names)
        for name in names:
            self.assertIsNone(found[name][0], name)
        self.assertEqual(found[str(self.outside / "secret.step")][1], "outside")
        self.assertEqual(found["${KIPRJMOD}/../outside/secret.step"][1], "outside")
        self.assertEqual(found["/etc/passwd"][1], "not-step")
        self.assertEqual(found["${KIPRJMOD}/models/fake.step"][1], "not-found")  # a folder is no model
        if link is not None:
            self.assertEqual(found["${KIPRJMOD}/models/link.step"][1], "outside")  # the real path is outside

    def test_a_share_a_device_or_a_drive_relative_name_is_outside_and_never_touched(self) -> None:
        # Windows opens \\server\share by connecting to the server with the person's credentials: such a
        # name, written by the board or made by a project variable, is refused before any file system call.
        self.board.with_suffix(".kicad_pro").write_text(
            '{"text_variables": {"SHARE": "\\\\\\\\evil.example\\\\share", "DEVICE": "\\\\\\\\?\\\\C:\\\\x"}}',
            encoding="utf-8")
        names = ["\\\\evil.example\\share\\a.step", "//evil.example/share/a.step", "\\\\?\\C:\\x\\a.step",
                 "\\\\.\\pipe\\a.step", "//?/UNC/evil.example/share/a.step", "C:a.step", "c:models\\own.step",
                 "${SHARE}/a.step", "$(SHARE)\\a.wrl", "${DEVICE}/a.step", "${KIPRJMOD}/../../../../evil/a.step"]
        touched: list[str] = []

        def recording(real):
            def call(path, *args, **kwargs):
                touched.append(os.fspath(path))
                return real(path, *args, **kwargs)
            return call

        roots = [str(self.project), str(self.library)]
        with mock.patch("os.stat", recording(os.stat)), mock.patch("os.lstat", recording(os.lstat)), \
                mock.patch("os.path.realpath", recording(os.path.realpath)), \
                mock.patch("os.path.isfile", recording(os.path.isfile)), \
                mock.patch("os.path.exists", recording(os.path.exists)):
            found = {name: (answer.path, answer.reason) for name, answer in
                     resolve_models(self.board, names, libraries=roots).items()}
        for name in names:
            self.assertEqual(found[name], (None, "outside"), name)
        # The only places touched are the board's folder and the libraries (resolving them), never a name's.
        for path in touched:
            self.assertTrue(any(root.startswith(path) for root in roots), path)
        self.assertFalse([path for path in touched if "evil" in path or "a.step" in path or "pipe" in path])

    def test_the_caps(self) -> None:
        with mock.patch.object(models3d, "MAX_BYTES", 4):
            self.assertEqual(self.resolve("${KIPRJMOD}/models/own.step")["${KIPRJMOD}/models/own.step"], (None, "too-large"))
        with mock.patch.object(models3d, "MAX_MODELS", 1):
            found = self.resolve("models/own.step", "rel.3dshapes/x.step")
        self.assertEqual((found["models/own.step"][1], found["rel.3dshapes/x.step"][1]), (None, "too-many"))
        # The files a board's models come to, each counted once, are capped in all: the next one is too many.
        size = (self.project / "models" / "own.step").stat().st_size
        with mock.patch.object(models3d, "MAX_TOTAL_BYTES", 2 * size):
            found = self.resolve("models/own.step", "${KIPRJMOD}/models/own.step", "rel.3dshapes/x.step",
                                 "${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603.step")
        self.assertEqual([found[name][1] for name in found], [None, None, None, "too-many"])

    def test_the_libraries_are_the_named_folders_and_kicads_install(self) -> None:
        named = os.pathsep.join([str(self.library), str(self.outside / "none")])
        self.assertEqual(library_roots({"CAD_KICAD_3DMODELS": named}, platform="none")[0], str(self.library))
        self.assertNotIn(str(self.outside / "none"), library_roots({"CAD_KICAD_3DMODELS": named}, platform="none"))

    def test_the_newest_installation_of_kicad_is_read_first(self) -> None:
        # Windows keeps one folder a version, side by side: KiCad 10's is read before KiCad 9's.
        programs = Path(self._tmp.name) / "Program Files"
        for version in ("9.0", "10.0", "8.0"):
            (programs / "KiCad" / version / "share" / "kicad" / "3dmodels").mkdir(parents=True)
        found = models3d.standard_libraries("win32", {"ProgramFiles": str(programs)})
        self.assertEqual([Path(library).parts[-4] for library in found], ["10.0", "9.0", "8.0"])

    def test_the_names_a_board_writes_are_the_ones_its_parts_carry(self) -> None:
        # The table is keyed by these names and the plot payload's parts by the parser's: KiCad 5's bare
        # name, a spaced "( model", and a quoted name's escapes (\n, \\, \") read the same on both sides.
        text = r'''(kicad_pcb (version 20171130)
 (module R_0603 (layer F.Cu) (at 10 10) (fp_text reference R1 (at 0 0) (layer F.SilkS))
  (model ${KISYS3DMOD}/Resistor_SMD.3dshapes/R_0603.wrl (at (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))
 (footprint "LED" (layer "F.Cu") (at 20 10) (property "Reference" "D1" (at 0 0) (layer "F.SilkS"))
  (model "${KIPRJMOD}/models\new\\led \"x\".step" (offset (xyz 0 0 0))) ( model "b.step") (model "b.step")))'''
        parsed = [model.name for part in read_index(text).parts for model in part.models]
        self.assertEqual(sorted(model_names(text)), sorted(set(parsed)))
        self.assertEqual(len(model_names(text)), 3)


class Payload(unittest.TestCase):
    def test_a_parts_models_and_the_boards_thickness_ride_in_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            board = write_board(Path(folder))
            payload = build_plot(board)
            index = read_board(board)
        parts = {part["ref"]: part for part in payload["board"]["parts"]}
        self.assertEqual(payload["board"]["thickness"], 1.6)
        self.assertEqual(parts["R1"]["models"], [{"name": "${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl"}])
        self.assertEqual(parts["D1"]["models"], [{"name": "${KIPRJMOD}/models/led.step", "offset": [0.1, 0.0, 0.0],
                                                  "rotate": [0.0, 0.0, 90.0]}])
        self.assertNotIn("models", parts["J1"])
        self.assertIn("led.step", MODELS["D1"])
        self.assertEqual(index.part("D1").models[0].rotate, (0.0, 0.0, 90.0))

    def test_a_kicad_5_offset_is_inches_and_a_hidden_model_says_so(self) -> None:
        from cad.engine.formats.kicad import sexpr
        from cad.engine.formats.kicad.board_index import _read_model

        old = _read_model(sexpr.parse('(model "a.wrl" (at (xyz 0.1 0 0)) (scale (xyz 2 2 2)) (rotate (xyz -90 0 0)) hide)'))
        self.assertEqual((old.offset, old.scale, old.rotate, old.hidden), ((2.54, 0.0, 0.0), (2.0, 2.0, 2.0), (-90.0, 0.0, 0.0), True))
        new = _read_model(sexpr.parse('(model "b.step" (hide yes) (opacity 0.5) (offset (xyz 0 0 1)))'))
        self.assertEqual((new.offset, new.hidden, new.opacity), ((0.0, 0.0, 1.0), True, 0.5))
        self.assertFalse(_read_model(sexpr.parse('(model "c.step" (hide no))')).hidden)


if __name__ == "__main__":
    unittest.main()
