from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/urdf/scripts")

from urdf import cli


VALID_URDF = """\
<?xml version="1.0"?>
<robot name="sample">
  <link name="base_link"/>
  <link name="arm_link">
    <inertial>
      <origin xyz="0 0 0.1"/>
      <mass value="0.5"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/>
    </inertial>
    <visual>
      <geometry>
        <box size="0.1 0.1 0.2"/>
      </geometry>
    </visual>
  </link>
  <joint name="shoulder" type="revolute">
    <parent link="base_link"/>
    <child link="arm_link"/>
    <origin xyz="0 0 0.05"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.5" upper="1.5" effort="2" velocity="1"/>
  </joint>
</robot>
"""


class UrdfValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-urdf-cli-")
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

    def test_valid_urdf_passes_with_summary(self) -> None:
        urdf_path = self._write("robot.urdf", VALID_URDF)
        exit_code, stdout, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout)
        self.assertIn("robot 'sample'", stdout)
        self.assertIn("2 links", stdout)
        self.assertIn("1 joints", stdout)
        self.assertEqual(stderr, "")

    def test_multiple_targets_validate_independently(self) -> None:
        first = self._write("a.urdf", VALID_URDF)
        second = self._write("b.urdf", VALID_URDF)
        exit_code, stdout, _ = self._run(str(first), str(second))
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.count("OK"), 2)

    def test_invalid_structure_fails(self) -> None:
        urdf_path = self._write(
            "broken.urdf",
            """\
<robot name="broken">
  <link name="base"/>
  <joint name="j1" type="revolute">
    <parent link="base"/>
    <child link="missing"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1" upper="1"/>
  </joint>
</robot>
""",
        )
        exit_code, stdout, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL", stderr)
        self.assertNotIn("OK", stdout)

    def test_one_failing_target_fails_run_but_validates_all(self) -> None:
        good = self._write("good.urdf", VALID_URDF)
        bad = self._write("bad.urdf", "<robot name='x'></robot>\n")
        exit_code, stdout, stderr = self._run(str(good), str(bad))
        self.assertEqual(exit_code, 1)
        self.assertIn("OK", stdout)
        self.assertIn("FAIL", stderr)

    def test_missing_file_fails(self) -> None:
        exit_code, _, stderr = self._run(str(self.temp_root / "absent.urdf"))
        self.assertEqual(exit_code, 1)
        self.assertIn("file not found", stderr)

    def test_non_urdf_suffix_fails(self) -> None:
        path = self._write("robot.xml", VALID_URDF)
        exit_code, _, stderr = self._run(str(path))
        self.assertEqual(exit_code, 1)
        self.assertIn("must be a .urdf file", stderr)

    def test_missing_local_mesh_fails(self) -> None:
        urdf_path = self._write(
            "meshy.urdf",
            """\
<robot name="meshy">
  <link name="base">
    <visual>
      <geometry>
        <mesh filename="meshes/base.stl" scale="0.001 0.001 0.001"/>
      </geometry>
    </visual>
  </link>
</robot>
""",
        )
        exit_code, _, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("missing mesh file", stderr)

    def test_package_mesh_uri_warns_but_passes(self) -> None:
        urdf_path = self._write(
            "pkg.urdf",
            """\
<robot name="pkg">
  <link name="base">
    <visual>
      <geometry>
        <mesh filename="package://robot_description/meshes/base.stl"/>
      </geometry>
    </visual>
  </link>
</robot>
""",
        )
        exit_code, stdout, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout)
        self.assertIn("WARN", stderr)

    def test_inertia_triangle_inequality_warns_and_strict_fails(self) -> None:
        urdf_path = self._write(
            "inertia.urdf",
            """\
<robot name="inertia">
  <link name="base">
    <inertial>
      <mass value="1"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="1.0"/>
    </inertial>
  </link>
</robot>
""",
        )
        exit_code, _, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("triangle inequalities", stderr)
        strict_exit, _, strict_stderr = self._run(str(urdf_path), "--strict")
        self.assertEqual(strict_exit, 1)
        self.assertIn("blocking finding", strict_stderr)

    def test_non_psd_inertia_fails(self) -> None:
        urdf_path = self._write(
            "psd.urdf",
            """\
<robot name="psd">
  <link name="base">
    <inertial>
      <mass value="1"/>
      <inertia ixx="0.001" ixy="0.01" ixz="0" iyy="0.001" iyz="0" izz="0.001"/>
    </inertial>
  </link>
</robot>
""",
        )
        exit_code, _, stderr = self._run(str(urdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("not positive semidefinite", stderr)


if __name__ == "__main__":
    unittest.main()
