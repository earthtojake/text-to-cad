from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from build123d import Box, Face, export_step

from cadgen.cli import step_validate as cli


class StepValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-step-validate-cli-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _export_box(self, name: str = "box.step", size: float = 10.0) -> Path:
        path = self.temp_root / name
        export_step(Box(size, size, size), str(path))
        return path

    def _run(self, *argv: str) -> tuple[int, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(list(argv))
        return exit_code, stdout.getvalue() + stderr.getvalue()

    def test_valid_step_passes_with_summary(self) -> None:
        step_path = self._export_box("cube.step", size=10.0)
        exit_code, output = self._run(str(step_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("1 solid", output)
        self.assertIn("6 faces", output)
        self.assertIn("volume 1000", output)

    def test_one_run_validates_one_file(self) -> None:
        first = self._export_box("a.step")
        second = self._export_box("b.step")
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self._run(str(first), str(second))
        self.assertEqual(2, cm.exception.code)

    def test_missing_file_fails(self) -> None:
        missing = self.temp_root / "missing.step"
        exit_code, output = self._run(str(missing))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("FAILED", output)
        self.assertIn("file not found", output)

    def test_empty_file_fails(self) -> None:
        empty = self.temp_root / "empty.step"
        empty.write_bytes(b"")
        exit_code, output = self._run(str(empty))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("empty_file", output)

    def test_invalid_suffix_fails(self) -> None:
        wrong = self.temp_root / "model.txt"
        wrong.write_text("not a step file", encoding="utf-8")
        exit_code, output = self._run(str(wrong))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("target must be a .step or .stp file", output)

    def test_json_output(self) -> None:
        step_path = self._export_box("cube_json.step", size=10.0)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main([str(step_path), "--json"])
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout.getvalue().strip())
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("issues"), [])
        self.assertIn("volume 1000", data.get("summary", ""))

    def test_corrupt_step_file_fails(self) -> None:
        corrupt = self.temp_root / "corrupt.step"
        corrupt.write_text("ISO-10303-21;\nHEADER;\nCORRUPT DATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        exit_code, output = self._run(str(corrupt))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("FAILED", output)
