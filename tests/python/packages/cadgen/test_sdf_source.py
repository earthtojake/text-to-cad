import unittest
from pathlib import Path

from tests.python.support.tmp_root import generated_cad_directory

from cadgen.sdf_source import SdfSource, SdfSourceError, parse_sdf_xml


class SdfSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = generated_cad_directory(prefix="tmp-sdf-source-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _file_ref(self, name: str) -> Path:
        return (self.temp_root / f"{name}.sdf").resolve()

    def _write_mesh(self, name: str) -> Path:
        mesh_path = self.temp_root / "meshes" / name
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        mesh_path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")
        return mesh_path

    def _write_sdf(self, name: str, body: str) -> Path:
        sdf_path = self.temp_root / f"{name}.sdf"
        sdf_path.write_text(body.strip() + "\n", encoding="utf-8")
        return sdf_path

    def _parse(self, path: Path) -> SdfSource:
        """The file at ``path`` parsed as ``cadgen sdf validate`` parses it."""
        return parse_sdf_xml(path.read_text(encoding="utf-8"), source_path=path, base_dir=path.parent)

    def test_accepts_minimal_model(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
              </model>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual(self._file_ref("robot"), Path(source.file_ref).resolve())
        self.assertEqual("1.12", source.version)
        self.assertEqual(("sample",), source.model_names)
        self.assertEqual((), source.world_names)
        self.assertEqual(("base_link",), source.links)
        self.assertEqual(0, len(source.joints))

    def test_reads_nested_models_under_scoped_names(self) -> None:
        source_path = self._write_sdf(
            "nested",
            """
            <sdf version="1.9">
              <model name="rig">
                <link name="base" />
                <model name="arm">
                  <link name="upper" />
                  <link name="lower" />
                  <joint name="elbow" type="revolute"><parent>upper</parent><child>lower</child></joint>
                  <model name="hand"><link name="palm" /></model>
                </model>
                <joint name="shoulder" type="revolute"><parent>base</parent><child>arm::upper</child></joint>
              </model>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual(("rig",), source.model_names)
        self.assertEqual(("base", "arm::upper", "arm::lower", "arm::hand::palm"), source.links)
        self.assertEqual(
            [("shoulder", "base", "arm::upper"), ("arm::elbow", "arm::upper", "arm::lower")],
            [(joint.name, joint.parent_link, joint.child_link) for joint in source.joints],
        )

    def test_parse_sdf_xml_validates_without_existing_output_file(self) -> None:
        output_path = self.temp_root / "generated" / "robot.sdf"

        source = parse_sdf_xml(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
              </model>
            </sdf>
            """,
            source_path=output_path,
            base_dir=output_path.parent,
        )

        self.assertEqual(output_path.resolve(), Path(source.file_ref).resolve())
        self.assertEqual(("sample",), source.model_names)
        self.assertFalse(output_path.exists())

    def test_accepts_local_mesh_references(self) -> None:
        mesh_path = self._write_mesh("base.stl")
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry>
                      <mesh>
                        <uri>meshes/base.stl</uri>
                      </mesh>
                    </geometry>
                  </visual>
                  <collision name="base_collision">
                    <geometry>
                      <mesh>
                        <uri>meshes/base.stl</uri>
                      </mesh>
                    </geometry>
                  </collision>
                </link>
              </model>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual((mesh_path.resolve(), mesh_path.resolve()), source.mesh_paths)
        self.assertEqual((mesh_path.resolve(),), source.visual_mesh_paths)
        self.assertEqual((mesh_path.resolve(),), source.collision_mesh_paths)

    def test_accepts_external_mesh_uri_without_resolution(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry>
                      <mesh>
                        <uri>model://sample/meshes/base.dae</uri>
                      </mesh>
                    </geometry>
                  </visual>
                </link>
              </model>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual((), source.mesh_paths)

    def test_accepts_world_models(self) -> None:
        source_path = self._write_sdf(
            "world",
            """
            <sdf version="1.12">
              <world name="sample_world">
                <model name="sample">
                  <link name="base_link" />
                </model>
              </world>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual(("sample_world",), source.world_names)
        self.assertEqual(("sample",), source.model_names)

    def test_accepts_world_only_scene(self) -> None:
        source_path = self._write_sdf(
            "world_only",
            """
            <sdf version="1.12">
              <world name="sample_world">
                <include>
                  <uri>model://sun</uri>
                </include>
              </world>
            </sdf>
            """,
        )

        source = self._parse(source_path)

        self.assertEqual(("sample_world",), source.world_names)
        self.assertEqual((), source.model_names)

    def test_rejects_missing_root(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <model name="sample">
              <link name="base_link" />
            </model>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "root element must be <sdf>"):
            self._parse(source_path)

    def test_rejects_missing_version(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf>
              <model name="sample">
                <link name="base_link" />
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "version is required"):
            self._parse(source_path)

    def test_rejects_missing_model_name(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model>
                <link name="base_link" />
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "model name is required"):
            self._parse(source_path)

    def test_rejects_duplicate_links(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="base_link" />
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "duplicates"):
            self._parse(source_path)

    def test_rejects_missing_joint_child_link(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="arm_link" />
                <joint name="base_to_arm" type="revolute">
                  <parent>base_link</parent>
                  <child>missing_link</child>
                </joint>
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "missing link"):
            self._parse(source_path)

    def test_empty_required_text_is_missing_not_the_name_none(self) -> None:
        # An empty element's text is None. The validator rejects it before this reader
        # runs (missing_child_text), so the reader's own check is called directly.
        import xml.etree.ElementTree as ET

        from cadgen.sdf_source import _required_child_text

        for joint in ("<joint><child/></joint>", "<joint><child></child></joint>", "<joint><child> </child></joint>"):
            with self.subTest(joint=joint), self.assertRaisesRegex(SdfSourceError, "joint child is required"):
                _required_child_text(ET.fromstring(joint), "child", source_path=self._file_ref("robot"), label="joint child")
        self.assertEqual(
            _required_child_text(
                ET.fromstring("<joint><child> arm </child></joint>"), "child",
                source_path=self._file_ref("robot"), label="joint child",
            ),
            "arm",
        )

    def test_rejects_duplicate_joints(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="arm_link" />
                <joint name="base_to_arm" type="fixed">
                  <parent>base_link</parent>
                  <child>arm_link</child>
                </joint>
                <joint name="base_to_arm" type="fixed">
                  <parent>base_link</parent>
                  <child>arm_link</child>
                </joint>
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "duplicates"):
            self._parse(source_path)

    def test_rejects_missing_local_mesh(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry>
                      <mesh>
                        <uri>meshes/missing.stl</uri>
                      </mesh>
                    </geometry>
                  </visual>
                </link>
              </model>
            </sdf>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "missing mesh file"):
            self._parse(source_path)


if __name__ == "__main__":
    unittest.main()
