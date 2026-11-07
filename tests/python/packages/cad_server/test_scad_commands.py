"""``cad scad <operation>``: the OpenSCAD document type's commands, and doctor's line for OpenSCAD.

The commands render the program with the person's OpenSCAD, headless, in their own process -- no extra, no
environment to make -- then hand the engine's mesh code the STL: ``inspect`` says what it renders to,
``export`` writes its mesh, a destination a mesh has no translation to is refused by name (exit 2), and a
computer with no OpenSCAD fails in one line with the install hint (exit 1), with ``--json`` and without.
The stand-in OpenSCAD renders (``tests/python/support/openscad_stub``); the real one in the openscad suite.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import openscad_stub

from cad_server.cli import doctor
from cad_server.cli.document_types import OPERATIONS, build_parser, type_main


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = type_main("scad", list(argv))
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class TheCommands(unittest.TestCase):
    def test_the_operations_and_their_parsers(self) -> None:
        self.assertEqual([name for kind, name in OPERATIONS if kind == "scad"], ["export", "snapshot", "inspect", "dfm"])
        self.assertIn("the .scad program", build_parser("scad", "inspect").format_help())
        self.assertNotIn("--tolerance", build_parser("scad", "export").format_help(), "a mesh is meshed by no one")
        self.assertIn("--camera", build_parser("scad", "snapshot").format_help())
        self.assertIn("--process", build_parser("scad", "dfm").format_help())

    def test_a_destination_with_no_mesh_translation_is_refused_before_openscad_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-scad-cli-") as folder, \
                mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(Path(folder) / "nowhere")}):
            program = Path(folder) / "part.scad"
            program.write_text("cube(1);\n", encoding="utf-8")
            code, out, err = _run("export", str(program), "part.step")
            self.assertEqual((code, out), (2, ""))
            self.assertIn("part.step: part.scad renders to a mesh, which has no B-rep, and no STEP is made from one", err)
            code, out, err = _run("export", str(program), "part.step", "--json")
            self.assertEqual((code, err), (2, ""))
            self.assertEqual(json.loads(out)["reason"], "invalid_argument")

    def test_no_openscad_is_one_line_with_the_install_hint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-scad-cli-") as folder, \
                mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(Path(folder) / "nowhere")}):
            program = Path(folder) / "part.scad"
            program.write_text("cube(1);\n", encoding="utf-8")
            for argv in (("inspect", str(program)), ("export", str(program), "part.stl"),
                         ("snapshot", str(program), str(Path(folder) / "part.png"))):
                with self.subTest(argv=argv):
                    code, out, err = _run(*argv, "--json")
                    self.assertEqual((code, err), (1, ""))
                    said = json.loads(out)
                    self.assertEqual(said["reason"], "failed")
                    self.assertIn("install OpenSCAD 2021.01 or newer", said["error"])
            code, out, err = _run("inspect", str(program))
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("cad scad inspect: CAD_OPENSCAD names"), err)


@unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
class TheStubRenders(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-scad-cli-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name).resolve()
        self.stub = openscad_stub.write_stub(self.root / "bin")
        patched = mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(self.stub)})
        patched.start()
        self.addCleanup(patched.stop)
        self.program = self.root / "part.scad"
        self.program.write_text("cube([20, 10, 5]);\n", encoding="utf-8")

    def test_inspect_says_what_the_program_renders_to(self) -> None:
        code, out, err = _run("inspect", str(self.program))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], f"{self.program}: OpenSCAD 2021.01, 12 triangles, 20 x 10 x 5 mm")
        self.assertEqual(lines[1:3], ["bounds: 0 to 20, 0 to 10, 0 to 5", "includes: none"])
        code, out, _ = _run("inspect", str(self.program), "--json")
        self.assertEqual((code, json.loads(out)["triangles"]), (0, 12))

    def test_export_writes_the_mesh_and_says_each_file(self) -> None:
        out = self.root / "out"
        code, said, _ = _run("export", str(self.program), str(out / "part.stl"), str(out / "part.3mf"))
        self.assertEqual(code, 0, said)
        self.assertRegex(said, r"wrote .*part\.stl \([\d.]+ ?[kKM]?B\) in [\d.]+s\nwrote .*part\.3mf \([\d.]+ ?[kKM]?B\)")
        code, said, _ = _run("export", str(self.program), str(out / "part.stl"), "--json")
        payload = json.loads(said)
        self.assertEqual((code, payload["ok"], [row["kind"] for row in payload["files"]]), (0, True, ["stl"]))
        self.assertFalse(payload["files"][0]["written"], "the same bytes already")

    def test_dfm_measures_the_rendered_mesh(self) -> None:
        code, out, _ = _run("dfm", str(self.program), "--process", "printing", "--json")
        payload = json.loads(out)
        self.assertEqual((code, payload["ok"]), (0, True))
        self.assertAlmostEqual(payload["measurements"]["mesh"]["volume_mm3"], 1000.0, delta=1.0)
        self.assertEqual(payload["path"], str(self.program))

    def test_doctor_says_where_openscad_is_and_its_version(self) -> None:
        lines = dict((line.split(" ", 1)[0], (status, line)) for status, line in doctor._integrations())  # noqa: SLF001
        status, line = lines["openscad"]
        self.assertEqual(status, doctor.OK)
        self.assertRegex(line, r"^openscad openscad 2021\.01 at .*bin[\\/]openscad$")
        with mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(self.root / "nowhere")}):
            status, line = dict((line.split(" ", 1)[0], (status, line)) for status, line in doctor._integrations())["openscad"]  # noqa: SLF001
        self.assertEqual(status, doctor.INFO)
        self.assertIn("install OpenSCAD 2021.01 or newer", line)


if __name__ == "__main__":
    unittest.main()
