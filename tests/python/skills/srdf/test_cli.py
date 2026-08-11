from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/srdf/scripts")

from srdf import cli


SAMPLE_URDF = """\
<robot name="sample">
  <link name="base"/>
  <link name="shoulder_link"/>
  <link name="wrist"/>
  <link name="tool"/>
  <joint name="shoulder" type="revolute">
    <parent link="base"/>
    <child link="shoulder_link"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/>
  </joint>
  <joint name="elbow" type="revolute">
    <parent link="shoulder_link"/>
    <child link="wrist"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_tool" type="fixed">
    <parent link="wrist"/>
    <child link="tool"/>
  </joint>
</robot>
"""


SAMPLE_SRDF = """\
<robot name="sample">
  <group name="arm">
    <chain base_link="base" tip_link="wrist"/>
  </group>
  <group name="gripper">
    <link name="tool"/>
  </group>
  <end_effector name="tcp" parent_link="wrist" group="gripper" parent_group="arm"/>
  <group_state name="home" group="arm">
    <joint name="shoulder" value="0"/>
    <joint name="elbow" value="0"/>
  </group_state>
  <disable_collisions link1="base" link2="shoulder_link" reason="Adjacent"/>
</robot>
"""


class SrdfValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-srdf-cli-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _write(self, name: str, body: str) -> Path:
        path = self.temp_root / name
        path.write_text(body, encoding="utf-8")
        return path

    def _write_pair(self, srdf_body: str = SAMPLE_SRDF, urdf_body: str = SAMPLE_URDF) -> Path:
        self._write("robot.urdf", urdf_body)
        return self._write("robot.srdf", srdf_body)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(list(argv))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_valid_pair_passes_with_summary(self) -> None:
        srdf_path = self._write_pair()
        exit_code, stdout, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout)
        self.assertIn("robot 'sample'", stdout)
        self.assertIn("2 groups", stdout)
        self.assertIn("1 end effectors", stdout)
        self.assertEqual(stderr, "")

    def test_retired_urdf_link_element_warns_but_passes(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<robot name="sample">',
                '<robot name="sample" xmlns:tcad="https://text-to-cad.dev/srdf">\n  <tcad:urdf path="robot.urdf"/>',
            )
        )
        exit_code, stdout, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout)
        self.assertIn("deprecated_urdf_link", stderr)

    def test_missing_paired_urdf_fails(self) -> None:
        srdf_path = self._write("robot.srdf", SAMPLE_SRDF)
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("declares robot name", stderr)

    def test_robot_name_without_matching_urdf_fails(self) -> None:
        srdf_path = self._write_pair(SAMPLE_SRDF.replace('name="sample"', 'name="other"', 1))
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("no_paired_urdf", stderr)

    def test_ambiguous_paired_urdf_fails(self) -> None:
        srdf_path = self._write_pair()
        self._write("robot_copy.urdf", SAMPLE_URDF)
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("ambiguous_paired_urdf", stderr)

    def test_unknown_group_joint_fails(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<chain base_link="base" tip_link="wrist"/>',
                '<joint name="not_a_joint"/>',
            )
        )
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("not_a_joint", stderr)

    def test_chain_that_is_not_a_tree_path_fails(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<chain base_link="base" tip_link="wrist"/>',
                '<chain base_link="wrist" tip_link="base"/>',
            )
        )
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("not a parent-to-child path", stderr)

    def test_group_state_beyond_urdf_limits_fails(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace('<joint name="shoulder" value="0"/>', '<joint name="shoulder" value="2.5"/>')
        )
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("above its URDF upper limit", stderr)

    def test_disable_collisions_unknown_link_fails(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<disable_collisions link1="base" link2="shoulder_link" reason="Adjacent"/>',
                '<disable_collisions link1="base" link2="phantom" reason="Adjacent"/>',
            )
        )
        exit_code, _, stderr = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("phantom", stderr)

    def test_non_srdf_suffix_fails(self) -> None:
        path = self._write("robot.xml", SAMPLE_SRDF)
        exit_code, _, stderr = self._run(str(path))
        self.assertEqual(exit_code, 1)
        self.assertIn("must be a .srdf file", stderr)

    def test_missing_file_fails(self) -> None:
        exit_code, _, stderr = self._run(str(self.temp_root / "absent.srdf"))
        self.assertEqual(exit_code, 1)
        self.assertIn("file not found", stderr)


if __name__ == "__main__":
    unittest.main()
