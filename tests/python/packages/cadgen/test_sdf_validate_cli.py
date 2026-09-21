from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("skills/sdf/scripts")

from cadgen.cli import sdf_validate as cli


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

    def _run(self, *argv: str) -> tuple[int, str]:
        """The command's exit code and EVERYTHING it printed.

        Findings now ride the ValidationResult's human lines on stdout rather
        than being printed to stderr as a side effect, so what a caller reads is
        one stream; the tests assert on both together and stay indifferent to
        which one a given line lands on.
        """
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(list(argv))
        return exit_code, stdout.getvalue() + stderr.getvalue()

    def test_valid_model_passes_with_summary(self) -> None:
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        exit_code, output = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("SDF 1.12", output)
        self.assertIn("box_bot", output)
        self.assertIn("1 links", output)

    def test_valid_world_only_document_passes(self) -> None:
        sdf_path = self._write("world.sdf", VALID_WORLD_SDF)
        exit_code, output = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        self.assertIn("worlds ['empty_lit_world']", output)

    def test_invalid_xml_fails(self) -> None:
        sdf_path = self._write("broken.sdf", "<sdf version='1.12'><model></sdf>\n")
        exit_code, output = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL", output)

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
        exit_code, output = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("missing_link", output)

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
        exit_code, _ = self._run(str(sdf_path), "--gz-check", "never")
        self.assertEqual(exit_code, 0)
        strict_exit, strict_output = self._run(str(sdf_path), "--gz-check", "never", "--strict")
        self.assertEqual(strict_exit, 1)
        self.assertIn("FAIL", strict_output)

    def _without_gz_on_path(self):
        """An empty PATH, so `shutil.which("gz")` misses on any machine."""
        empty = self.temp_root / "empty-bin"
        empty.mkdir(exist_ok=True)
        return mock.patch.dict(os.environ, {"PATH": str(empty)})

    def test_auto_gz_check_passes_a_clean_file_without_gz(self) -> None:
        # `auto` means "run gz if it is here". A machine without Gazebo must not
        # fail a document that is fine -- the note says the check did not run.
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        with self._without_gz_on_path():
            exit_code, output = self._run(str(sdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("info: gz_check_unavailable", output)

    def test_strict_does_not_promote_an_absent_gz(self) -> None:
        # `--strict` promotes WARNINGS, and an absent optional tool is not one:
        # it says nothing about the file being validated.
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        with self._without_gz_on_path():
            exit_code, output = self._run(str(sdf_path), "--strict")
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)

    def test_required_gz_check_is_how_you_demand_the_tool(self) -> None:
        sdf_path = self._write("model.sdf", VALID_MODEL_SDF)
        with self._without_gz_on_path():
            exit_code, output = self._run(str(sdf_path), "--gz-check", "required")
        self.assertEqual(exit_code, 1)
        self.assertIn("error: gz_check_unavailable", output)

    def test_missing_file_fails(self) -> None:
        exit_code, output = self._run(str(self.temp_root / "absent.sdf"), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("file not found", output)

    def test_non_sdf_suffix_fails(self) -> None:
        path = self._write("model.xml", VALID_MODEL_SDF)
        exit_code, output = self._run(str(path), "--gz-check", "never")
        self.assertEqual(exit_code, 1)
        self.assertIn("must be a .sdf file", output)


if __name__ == "__main__":
    unittest.main()
