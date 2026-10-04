"""Standalone light files must receive the same checks as world/link lights."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cadgen import sdf


class SdfRootLightTests(unittest.TestCase):
    def validate(self, lights):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "light.sdf"
            path.write_text(f'<sdf version="1.12">{lights}</sdf>', encoding="utf-8")
            return sdf.validate(path, gz_check="never")

    def assert_code(self, lights, code):
        result = self.validate(lights)
        self.assertFalse(result.ok, result)
        self.assertIn(code, {issue.code for issue in result.issues})

    def test_missing_name(self):
        self.assert_code('<light type="point"/>', "missing_name")

    def test_missing_type(self):
        self.assert_code('<light name="sun"/>', "missing_light_type")

    def test_unknown_type(self):
        self.assert_code('<light name="sun" type="laser"/>', "unknown_light_type")

    def test_invalid_pose(self):
        self.assert_code('<light name="sun" type="point"><pose>1 2</pose></light>',
                         "invalid_numeric_vector")

    def test_duplicate_names(self):
        self.assert_code('<light name="sun" type="point"/><light name="sun" type="spot"/>',
                         "duplicate_names")

    def test_valid_supported_types(self):
        for kind in ("point", "spot", "directional"):
            with self.subTest(kind=kind):
                self.assertTrue(self.validate(f'<light name="sun" type="{kind}"/>').ok)

    def test_cli_reports_error_as_json_and_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "light.sdf"
            path.write_text('<sdf version="1.12"><light name="sun" type="laser"/></sdf>',
                            encoding="utf-8")
            process = subprocess.run([sys.executable, "-S", "-m", "cadgen.cli", "sdf", "validate",
                                      str(path), "--gz-check", "never", "--json"],
                                     capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 1, process.stderr)
            report = json.loads(process.stdout)
            self.assertFalse(report["ok"])
            self.assertIn("unknown_light_type", {issue["code"] for issue in report["issues"]})


if __name__ == "__main__":
    unittest.main()
