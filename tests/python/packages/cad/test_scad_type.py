"""``cad.scad``: the OpenSCAD document type's functions, on the stand-in OpenSCAD.

A ``.scad`` is authored: no decorator, no edit. Its reader is the program as mesh data, its export the
rendered STL byte for byte and the engine's mesh translations, its summary what the program renders to; a
file of another type and a destination with no mesh translation are refused by name before OpenSCAD runs.
The stand-in renders a box of the program's ``cube`` (``tests/python/support/openscad_stub``); the real
OpenSCAD renders in the openscad suite.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import openscad_stub

from cad import scad
from cad._internal.document_type import DocumentType


class TheType(unittest.TestCase):
    def test_a_program_is_authored_and_its_functions_are_its_own(self) -> None:
        self.assertIsInstance(scad, DocumentType)
        self.assertEqual(scad.entry.operation_names, ("export", "snapshot", "inspect", "dfm"))
        self.assertTrue(scad.entry.reader and not scad.entry.decorator and scad.entry.edit is None)
        with self.assertRaisesRegex(TypeError, "cad.scad has no decorator: a OpenSCAD is authored"):
            scad("part.scad")
        for name in ("read", "export", "snapshot", "inspect"):
            self.assertIs(getattr(scad, name), scad.__dict__[name], f"{name} is the type's own function")
        self.assertEqual(scad.dfm.__module__, "cad.scad")

    def test_a_file_of_another_type_is_refused_by_name_before_openscad_runs(self) -> None:
        with mock.patch.dict(os.environ, {"CAD_OPENSCAD": "/nowhere/openscad"}):
            for call in (lambda: scad.read("part.stl"), lambda: scad.inspect("part.stl"),
                         lambda: scad.export("part.stl", "out.glb")):
                with self.assertRaisesRegex(ValueError, "part.stl is a stl, not a scad: use cad.stl"):
                    call()
            with self.assertRaisesRegex(ValueError, "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab is a model's document id"):
                scad.inspect("0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab")


@unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
class TheFunctions(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-scad-type-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name).resolve()
        stub = openscad_stub.write_stub(self.root / "bin")
        patched = mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(stub)})
        patched.start()
        self.addCleanup(patched.stop)
        (self.root / "lib.scad").write_text("module post() {}\n", encoding="utf-8")
        self.program = self.root / "part.scad"
        self.program.write_text('include <lib.scad>\necho(version=1);\ncube([20, 10, 5]);\n', encoding="utf-8")

    def test_read_is_the_program_as_mesh_data(self) -> None:
        mesh = scad.read(self.program)
        self.assertEqual((len(mesh.vertices), len(mesh.triangles), mesh.name), (8, 12, "part"))
        self.assertEqual(tuple(round(value, 6) for value in mesh.bounding_box().size), (20.0, 10.0, 5.0))
        with self.assertRaisesRegex(FileNotFoundError, "no such file"):
            scad.read(self.root / "gone.scad")

    def test_inspect_says_what_the_program_renders_to(self) -> None:
        found = scad.inspect(self.program)
        self.assertEqual((found["file"], found["openscad"], found["triangles"]), (str(self.program), "2021.01", 12))
        self.assertEqual(found["includes"], [str(self.root / "lib.scad")])
        self.assertEqual(found["bounds"], {"min": [0.0, 0.0, 0.0], "max": [20.0, 10.0, 5.0], "size": [20.0, 10.0, 5.0]})
        self.assertEqual(found["said"], ["ECHO: version=1"])

    def test_export_copies_the_stl_translates_the_rest_and_refuses_what_a_mesh_has_no_translation_to(self) -> None:
        out = self.root / "out"
        for destination, label in ((out / "part.step", "STEP"), (out / "part.xbf", "xbf"), (out / "part.dxf", "DXF")):
            with self.subTest(destination=destination.name), mock.patch.dict(os.environ, {"CAD_OPENSCAD": "/nowhere/openscad"}):
                with self.assertRaisesRegex(ValueError, rf"{destination.name}: part\.scad renders to a mesh, which has no "
                                                        rf"B-rep, and no {label} is made from one; export \.stl, \.3mf or \.glb"):
                    scad.export(self.program, destination)
        with self.assertRaisesRegex(ValueError, "export names at least one destination"):
            scad.export(self.program)
        written = scad.export(self.program, out / "part.glb", out / "part.stl", out / "part.3mf", daemon=False)
        self.assertEqual([(row.kind, row.path.name, row.written) for row in written],
                         [("glb", "part.glb", True), ("stl", "part.stl", True), ("threemf", "part.3mf", True)])
        self.assertEqual((out / "part.stl").read_bytes()[:14], b"OpenSCAD Model", "the rendered file itself")
        self.assertGreater((out / "part.glb").stat().st_size, 100)
        again = scad.export(self.program, out / "part.stl", daemon=False)
        self.assertEqual([(row.kind, row.written) for row in again], [("stl", False)], "the same bytes: left as it was")

    def test_a_snapshot_of_a_program_counts_as_a_programs_not_an_stls(self) -> None:
        """The engine's snapshot is handed the rendered STL, and tells its observers it read a ``scad``
        (``api.read_as``), so telemetry counts the program's format, never the temporary STL's."""
        from cad.engine import api

        stl = self.root / "render.stl"
        stl.write_bytes(b"x")
        drawn = api.Drawn(path=self.root / "out.png", width=1, height=1, report={})
        facts = api._facts("snapshot", (stl, self.root / "out.png"), {}, {}, drawn, None, 0.1)  # noqa: SLF001
        self.assertEqual(facts["source"], "stl")
        with api.read_as("scad"):
            facts = api._facts("snapshot", (stl, self.root / "out.png"), {}, {}, drawn, None, 0.1)  # noqa: SLF001
        self.assertEqual((facts["source"], facts["found"]), ("scad", True))
        self.assertEqual(api._facts("snapshot", (stl, self.root / "out.png"), {}, {}, drawn, None, 0.1)["source"], "stl")  # noqa: SLF001

    def test_dfm_measures_the_rendered_mesh(self) -> None:
        result = scad.dfm(self.program, process="printing")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        self.assertAlmostEqual(result.measurements["mesh"]["volume_mm3"], 1000.0, delta=1.0)
        with self.assertRaisesRegex(ValueError, "an OpenSCAD program's numbers are millimetres"):
            scad.dfm(self.program, process="printing", units="in")


if __name__ == "__main__":
    unittest.main()
