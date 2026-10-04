"""URDF allows many visual/collision owners, each with exactly one geometry."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cadgen import urdf

SPHERE = '<geometry><sphere radius="0.1"/></geometry>'
BOX = '<geometry><box size="0.1 0.1 0.1"/></geometry>'


class UrdfGeometryCountTests(unittest.TestCase):
    def validate(self, body):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "arm.urdf"
            path.write_text(f'<robot name="arm"><link name="base">{body}</link></robot>', encoding="utf-8")
            return urdf.validate(path)

    def test_each_owner_rejects_multiple_geometry_elements(self):
        for kind in ("visual", "collision"):
            with self.subTest(kind=kind):
                result = self.validate(f'<{kind}>{SPHERE}{BOX}</{kind}>')
                self.assertFalse(result.ok, result)
                self.assertIn("duplicate_geometry", {item.code for item in result.issues})

    def test_invalid_second_geometry_is_not_silently_ignored(self):
        result = self.validate(f'<visual>{SPHERE}<geometry><sphere radius="-1"/></geometry></visual>')
        self.assertFalse(result.ok)
        self.assertIn("duplicate_geometry", {item.code for item in result.issues})

    def test_multiple_separate_owners_remain_valid(self):
        result = self.validate(f'<visual>{SPHERE}</visual><visual>{BOX}</visual>'
                               f'<collision>{SPHERE}</collision><collision>{BOX}</collision>')
        self.assertTrue(result.ok, result)

    def test_missing_geometry_keeps_existing_diagnostic(self):
        result = self.validate('<visual/>')
        self.assertFalse(result.ok)
        self.assertIn("missing_geometry", {item.code for item in result.issues})

    def test_child_cli_reports_duplicate_as_structured_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "arm.urdf"
            path.write_text(f'<robot name="arm"><link name="base"><visual>{SPHERE}{BOX}'
                            '</visual></link></robot>', encoding="utf-8")
            process = subprocess.run([sys.executable, "-S", "-m", "cadgen.cli", "urdf", "validate",
                                      str(path), "--json"], capture_output=True, text=True, check=False)
            self.assertEqual(1, process.returncode, process.stderr)
            report = json.loads(process.stdout)
            self.assertFalse(report["ok"])
            self.assertIn("duplicate_geometry", {item["code"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
