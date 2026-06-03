from __future__ import annotations

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
<robot name="sample" xmlns:tcad="https://text-to-cad.dev/srdf">
  <tcad:urdf path="robot.urdf"/>
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
    <joint name="elbow" value="0"/>
  </group_state>
  <disable_collisions link1="wrist" link2="tool" reason="Adjacent"/>
</robot>
"""


def write_source(path: Path, payload: object | None = None, *, function_name: str = "gen_srdf") -> None:
    if payload is None:
        payload = {"xml": SAMPLE_SRDF, "urdf": "robot.urdf"}
    path.write_text(
        f"def {function_name}():\n"
        f"    return {payload!r}\n",
        encoding="utf-8",
    )


class SrdfCliTests(unittest.TestCase):
    def test_writes_sibling_srdf_without_hidden_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "robot_srdf.py"
            write_source(source_path)

            self.assertEqual(0, cli.generate_srdf_targets([str(source_path)]))

            output_path = root / "robot_srdf.srdf"
            self.assertTrue(output_path.is_file())
            output_text = output_path.read_text(encoding="utf-8")
            self.assertIn("tcad:urdf", output_text)
            self.assertIn("path=\"robot.urdf\"", output_text)
            self.assertIn("<group name=\"arm\">", output_text)
            self.assertFalse((root / ".robot.urdf").exists())

    def test_injects_tcad_urdf_link(self) -> None:
        srdf = """\
        <robot name="sample">
          <group name="arm">
            <chain base_link="base" tip_link="tool"/>
          </group>
        </robot>
        """
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "robot_srdf.py"
            write_source(source_path, {"xml": srdf, "urdf": "robot.urdf"})

            self.assertEqual(0, cli.generate_srdf_targets([str(source_path)]))

            output_text = (root / "robot_srdf.srdf").read_text(encoding="utf-8")
            self.assertIn("tcad:urdf", output_text)
            self.assertIn("path=\"robot.urdf\"", output_text)

    def test_updates_legacy_explorer_urdf_link(self) -> None:
        legacy_srdf = SAMPLE_SRDF.replace(
            'xmlns:tcad="https://text-to-cad.dev/srdf"',
            'xmlns:explorer="https://text-to-cad.dev/explorer"',
        ).replace("tcad:urdf", "explorer:urdf")
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "robot_srdf.py"
            write_source(source_path, {"xml": legacy_srdf, "urdf": "robot.urdf"})

            self.assertEqual(0, cli.generate_srdf_targets([str(source_path)]))

            output_text = (root / "robot_srdf.srdf").read_text(encoding="utf-8")
            self.assertIn("tcad:urdf", output_text)
            self.assertNotIn("explorer:urdf", output_text)
            self.assertIn("path=\"robot.urdf\"", output_text)

    def test_writes_srdf_from_element_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "robot_srdf.py"
            source_path.write_text(
                "\n".join(
                    [
                        "import xml.etree.ElementTree as ET",
                        "",
                        "def gen_srdf():",
                        "    robot = ET.Element('robot', {'name': 'sample'})",
                        "    group = ET.SubElement(robot, 'group', {'name': 'arm'})",
                        "    ET.SubElement(group, 'joint', {'name': 'shoulder'})",
                        "    ET.SubElement(group, 'joint', {'name': 'elbow'})",
                        "    return {'xml': robot, 'urdf': 'robot.urdf'}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, cli.generate_srdf_targets([str(source_path)]))

            output_text = (root / "robot_srdf.srdf").read_text(encoding="utf-8")
            self.assertTrue(output_text.startswith('<?xml version="1.0"?>\n'))
            self.assertIn("tcad:urdf", output_text)
            self.assertIn("<group name=\"arm\">", output_text)
            self.assertIn("<joint name=\"shoulder\" />", output_text)

    def test_supports_output_option(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            output_path = root / "out" / "robot.srdf"
            write_source(source_path)

            self.assertEqual(0, cli.generate_srdf_targets([str(source_path)], output=str(output_path)))

            self.assertTrue(output_path.is_file())

    def test_supports_source_output_pairs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            output_path = root / "out" / "robot.srdf"
            write_source(source_path)

            self.assertEqual(0, cli.generate_srdf_targets([f"{source_path}={output_path}"]))

            self.assertTrue(output_path.is_file())

    def test_rejects_missing_gen_srdf(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            write_source(source_path, function_name="gen_urdf")

            with self.assertRaisesRegex(RuntimeError, "gen_srdf"):
                cli.generate_srdf_targets([str(source_path)])

    def test_rejects_missing_xml_or_urdf(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            source_path = root / "source.py"
            write_source(source_path, {"xml": SAMPLE_SRDF})

            with self.assertRaisesRegex(TypeError, "urdf"):
                cli.generate_srdf_targets([str(source_path)])

            write_source(source_path, {"urdf": "robot.urdf"})
            with self.assertRaisesRegex(TypeError, "xml"):
                cli.generate_srdf_targets([str(source_path)])

    def test_rejects_invalid_xml_or_urdf_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            write_source(source_path, {"xml": "<sdf/>", "urdf": "robot.urdf"})

            with self.assertRaisesRegex(Exception, "root element must be <robot>"):
                cli.generate_srdf_targets([str(source_path)])

            write_source(source_path, {"xml": SAMPLE_SRDF, "urdf": "missing.urdf"})
            with self.assertRaisesRegex(FileNotFoundError, "urdf file does not exist"):
                cli.generate_srdf_targets([str(source_path)])

    def test_rejects_group_state_values_outside_group_or_limits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            write_source(
                source_path,
                {
                    "xml": SAMPLE_SRDF.replace('<joint name="shoulder" value="0"/>', '<joint name="shoulder" value="2"/>'),
                    "urdf": "robot.urdf",
                },
            )

            with self.assertRaisesRegex(Exception, "above its URDF upper limit"):
                cli.generate_srdf_targets([str(source_path)])

            write_source(
                source_path,
                {
                    "xml": SAMPLE_SRDF.replace('<joint name="shoulder" value="0"/>', '<joint name="wrist_tool" value="0"/>'),
                    "urdf": "robot.urdf",
                },
            )
            with self.assertRaisesRegex(Exception, "not in group"):
                cli.generate_srdf_targets([str(source_path)])

    def test_rejects_overlapping_end_effector_group(self) -> None:
        srdf = SAMPLE_SRDF.replace('<link name="tool"/>', '<link name="wrist"/>')
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            write_source(source_path, {"xml": srdf, "urdf": "robot.urdf"})

            with self.assertRaisesRegex(Exception, "shares link"):
                cli.generate_srdf_targets([str(source_path)])

    def test_rejects_disabled_collision_without_reason(self) -> None:
        srdf = SAMPLE_SRDF.replace(' reason="Adjacent"', "")
        with tempfile.TemporaryDirectory(prefix="tmp-gen-srdf-") as tempdir:
            root = Path(tempdir)
            (root / "robot.urdf").write_text(SAMPLE_URDF, encoding="utf-8")
            source_path = root / "source.py"
            write_source(source_path, {"xml": srdf, "urdf": "robot.urdf"})

            with self.assertRaisesRegex(Exception, "requires a reason"):
                cli.generate_srdf_targets([str(source_path)])

    def test_output_must_be_srdf(self) -> None:
        with self.assertRaisesRegex(ValueError, "must end in .srdf"):
            cli.generate_srdf_targets(["source.py=out.xml"])


if __name__ == "__main__":
    unittest.main()
