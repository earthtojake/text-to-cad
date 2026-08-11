from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/sdf/scripts")

from sdf import cli


VALID_MODEL_SDF = """\
<?xml version="1.0"?>
<sdf version="1.12">
  <model name="box_bot">
    <link name="chassis">
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>0.01</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>0.01</iyy><iyz>0</iyz><izz>0.01</izz>
        </inertia>
      </inertial>
      <visual name="chassis_visual">
        <geometry><box><size>0.2 0.2 0.1</size></box></geometry>
      </visual>
      <collision name="chassis_collision">
        <geometry><box><size>0.2 0.2 0.1</size></box></geometry>
      </collision>
    </link>
  </model>
</sdf>
"""


VALID_WORLD_SDF = """\
<?xml version="1.0"?>
<sdf version="1.12">
  <world name="empty_lit_world">
    <light name="sun" type="directional">
      <pose relative_to="world">0 0 10 0 0 0</pose>
    </light>
  </world>
</sdf>
"""


class SdfValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-sdf-cli-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _write(self, name: str, body: str) -> Path:
        path = self.temp_root / name
        path.write_text(body, encoding="utf-8")
        return path

    def _run(self, *argv: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(list(argv))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_valid_model_passes_with_summary(self) -> None:
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        exit_code, stdout, _ = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout)
        self.assertIn("SDF 1.12", stdout)
        self.assertIn("box_bot", stdout)
        self.assertIn("1 links", stdout)

    def test_valid_world_only_document_passes(self) -> None:
        sdf_path = self._write("world.sdf", VALID_WORLD_SDF)
        exit_code, stdout, _ = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        self.assertIn("worlds ['empty_lit_world']", stdout)

    def test_invalid_xml_fails(self) -> None:
        sdf_path = self._write("broken.sdf", "<sdf version='1.12'><model></sdf>\n")
        exit_code, _, stderr = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL", stderr)

    def test_joint_referencing_missing_link_fails(self) -> None:
        sdf_path = self._write(
            "joint.sdf",
            """\
<?xml version="1.0"?>
<sdf version="1.12">
  <model name="broken_bot">
    <link name="base"/>
    <joint name="j1" type="revolute">
      <parent>base</parent>
      <child>missing_link</child>
      <axis><xyz>0 0 1</xyz></axis>
    </joint>
  </model>
</sdf>
""",
        )
        exit_code, _, stderr = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("missing_link", stderr)

    def test_strict_mode_promotes_warnings(self) -> None:
        sdf_path = self._write(
            "warned.sdf",
            """\
<?xml version="1.0"?>
<sdf version="1.12">
  <model name="warn_bot">
    <link name="base">
      <pose degrees="true">0 0 0 0 0 90</pose>
    </link>
  </model>
</sdf>
""",
        )
        exit_code, _, _ = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        strict_exit, _, strict_stderr = self._run(str(sdf_path), "--gz-check", "never", "--strict")
        self.assertEqual(strict_exit, 1)
        self.assertIn("FAIL", strict_stderr)

    def test_gz_check_required_fails_when_gz_missing(self) -> None:
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        exit_code, _, stderr = self._run(str(sdf_path), "--gz-check", "required")
        combined = stderr
        if exit_code == 0:
            self.skipTest("gz is installed in this environment")
        self.assertEqual(exit_code, 1)
        self.assertIn("gz", combined)

    def test_missing_file_fails(self) -> None:
        exit_code, _, stderr = self._run(str(self.temp_root / "absent.sdf"), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("file not found", stderr)

    def test_non_sdf_suffix_fails(self) -> None:
        path = self._write("model.xml", VALID_MODEL_SDF)
        exit_code, _, stderr = self._run(str(path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("must be a .sdf file", stderr)


if __name__ == "__main__":
    unittest.main()
