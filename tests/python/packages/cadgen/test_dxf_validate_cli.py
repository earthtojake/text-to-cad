from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import ezdxf

from cadgen.cli import dxf_validate as cli


class DxfValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-dxf-validate-cli-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _write_valid_dxf(self, name: str = "box.dxf") -> Path:
        doc = ezdxf.new()
        doc.units = ezdxf.units.MM
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
        path = self.temp_root / name
        doc.saveas(str(path))
        return path

    def _run(self, *argv: str) -> tuple[int, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(list(argv))
        return exit_code, stdout.getvalue() + stderr.getvalue()

    def test_valid_cut_layout_passes(self) -> None:
        dxf_path = self._write_valid_dxf("valid.dxf")
        exit_code, output = self._run(str(dxf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("cut layout", output)

    def test_one_run_validates_one_file(self) -> None:
        first = self._write_valid_dxf("a.dxf")
        second = self._write_valid_dxf("b.dxf")
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self._run(str(first), str(second))
        self.assertEqual(2, cm.exception.code)

    def test_missing_file_fails(self) -> None:
        missing = self.temp_root / "missing.dxf"
        exit_code, output = self._run(str(missing))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("FAILED", output)
        self.assertIn("file not found", output)

    def test_empty_file_fails(self) -> None:
        empty = self.temp_root / "empty.dxf"
        empty.write_bytes(b"")
        exit_code, output = self._run(str(empty))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("empty_file", output)

    def test_invalid_suffix_fails(self) -> None:
        wrong = self.temp_root / "drawing.dwg"
        wrong.write_text("not dxf", encoding="utf-8")
        exit_code, output = self._run(str(wrong))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("target must be a .dxf file", output)

    def test_open_cut_profile_fails(self) -> None:
        doc = ezdxf.new()
        doc.units = ezdxf.units.MM
        msp = doc.modelspace()
        # Open polyline on cut layer
        msp.add_lwpolyline([(0, 0), (20, 0), (20, 10)], close=False)
        path = self.temp_root / "open.dxf"
        doc.saveas(str(path))

        exit_code, output = self._run(str(path))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("open_cut_profile", output)

    def test_units_not_set_fails(self) -> None:
        doc = ezdxf.new()
        # Explicitly set $INSUNITS to 0 (unitless)
        doc.header["$INSUNITS"] = 0
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
        path = self.temp_root / "no_units.dxf"
        doc.saveas(str(path))

        exit_code, output = self._run(str(path))
        self.assertNotEqual(exit_code, 0)
        self.assertIn("units_not_set", output)

    def test_json_output(self) -> None:
        dxf_path = self._write_valid_dxf("json_test.dxf")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main([str(dxf_path), "--json"])
        self.assertEqual(exit_code, 0)
        data = json.loads(stdout.getvalue().strip())
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("issues"), [])
        self.assertIn("cut layout", data.get("summary", ""))

    def test_dimensioned_drawing_treated_as_drawing(self) -> None:
        doc = ezdxf.new()
        doc.units = ezdxf.units.MM
        msp = doc.modelspace()
        # open line (normally rejected on cut layer)
        msp.add_line((0, 0), (10, 0))
        # add a dimension entity
        dim = msp.add_linear_dim(base=(5, 5), p1=(0, 0), p2=(10, 0))
        dim.render()
        path = self.temp_root / "dimensioned.dxf"
        doc.saveas(str(path))

        exit_code, output = self._run(str(path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("drawing", output)
