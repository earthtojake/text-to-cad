from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from cadgen.findings import format_findings
from cadgen.srdf_source import parse_srdf_file


SAMPLE_SRDF = """\
<robot name="sample">
  <group name="arm">
    <joint name="shoulder"/>
    <joint name="elbow"/>
  </group>
  <group name="gripper">
    <link name="tool"/>
  </group>
  <end_effector name="tcp" parent_link="wrist" group="gripper" parent_group="arm"/>
  <group_state name="home" group="arm">
    <joint name="shoulder" value="0"/>
    <joint name="elbow" value="1.57"/>
  </group_state>
  <disable_collisions link1="base" link2="shoulder_link" reason="Adjacent"/>
</robot>
"""


class SrdfSourceTests(unittest.TestCase):
    def test_reads_moveit2_srdf_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text(SAMPLE_SRDF, encoding="utf-8")

            source, result = parse_srdf_file(srdf_path)

            self.assertEqual([], result.errors)
            self.assertEqual(source.robot_name, "sample")
            self.assertEqual(source.planning_groups[0].name, "arm")
            self.assertEqual(source.planning_groups[0].joint_names, ("shoulder", "elbow"))
            self.assertEqual(source.end_effectors[0].name, "tcp")
            self.assertEqual(source.group_states[0].joint_values_by_name["elbow"], 1.57)
            self.assertEqual(source.disabled_collision_pairs[0].reason, "Adjacent")

    def test_a_namespaced_extension_element_passes_through(self) -> None:
        legacy = SAMPLE_SRDF.replace(
            '<robot name="sample">',
            '<robot name="sample" xmlns:tcad="https://text-to-cad.dev/srdf">\n  <tcad:urdf path="robot.urdf"/>',
        )
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text(legacy, encoding="utf-8")

            source, result = parse_srdf_file(srdf_path)

            self.assertIsNotNone(source)
            # Namespaced extensions are not the SRDF contract's business: no
            # finding names them, retired or otherwise.
            self.assertEqual(set(), {finding.code for finding in result.warnings})

    def test_rejects_non_robot_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text("<sdf/>", encoding="utf-8")

            _source, result = parse_srdf_file(srdf_path)

            self.assertRegex(format_findings(result.errors), "root element must be <robot>")


if __name__ == "__main__":
    unittest.main()
