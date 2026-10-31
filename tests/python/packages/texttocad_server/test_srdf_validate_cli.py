from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest


from cad_server.cli import srdf_validate as cli


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

    def test_valid_pair_passes_with_summary(self) -> None:
        srdf_path = self._write_pair()
        exit_code, output = self._run(str(srdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertIn("robot 'sample'", output)
        self.assertIn("2 groups", output)
        self.assertIn("1 end effectors", output)

    def test_a_namespaced_extension_element_passes(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<robot name="sample">',
                '<robot name="sample" xmlns:tcad="https://text-to-cad.dev/srdf">\n  <tcad:urdf path="robot.urdf"/>',
            )
        )
        exit_code, output = self._run(str(srdf_path))
        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertNotIn("deprecated", output)

    # The validator's findings are test_srdf_findings.py's table; the command's part is that one fails it.
    def test_a_refused_pair_fails_with_its_finding(self) -> None:
        srdf_path = self._write_pair(
            SAMPLE_SRDF.replace(
                '<chain base_link="base" tip_link="wrist"/>',
                '<chain base_link="wrist" tip_link="base"/>',
            )
        )
        exit_code, output = self._run(str(srdf_path))
        self.assertEqual(exit_code, 1)
        self.assertIn("not a parent-to-child path", output)

    def test_non_srdf_suffix_fails(self) -> None:
        path = self._write("robot.xml", SAMPLE_SRDF)
        exit_code, output = self._run(str(path))
        self.assertEqual(exit_code, 1)
        self.assertIn("must be a .srdf file", output)

    def test_missing_file_fails(self) -> None:
        exit_code, output = self._run(str(self.temp_root / "absent.srdf"))
        self.assertEqual(exit_code, 1)
        self.assertIn("file not found", output)


if __name__ == "__main__":
    unittest.main()
