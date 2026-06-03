import tempfile
import unittest
from pathlib import Path

from sdf.source import SdfSourceError, parse_sdf_xml, read_sdf_source


class SdfSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-sdf-source-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _file_ref(self, name: str) -> str:
        return (self.temp_root / f"{name}.sdf").resolve().as_posix()

    def _write_mesh(self, name: str) -> Path:
        mesh_path = self.temp_root / "meshes" / name
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        mesh_path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")
        return mesh_path

    def _write_sdf(self, name: str, body: str) -> Path:
        sdf_path = self.temp_root / f"{name}.sdf"
        sdf_path.write_text(body.strip() + "\n", encoding="utf-8")
        return sdf_path

    def test_read_sdf_source_accepts_minimal_model(self) -> None:
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

        source = read_sdf_source(source_path)

        self.assertEqual(self._file_ref("robot"), source.file_ref)
        self.assertEqual("1.12", source.version)
        self.assertEqual(("sample",), source.model_names)
        self.assertEqual((), source.world_names)
        self.assertEqual(("base_link",), source.links)
        self.assertEqual(0, len(source.joints))

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

        self.assertEqual(output_path.resolve().as_posix(), source.file_ref)
        self.assertEqual(("sample",), source.model_names)
        self.assertFalse(output_path.exists())

    def test_read_sdf_source_accepts_local_mesh_references(self) -> None:
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

        source = read_sdf_source(source_path)

        self.assertEqual((mesh_path.resolve(), mesh_path.resolve()), source.mesh_paths)
        self.assertEqual((mesh_path.resolve(),), source.visual_mesh_paths)
        self.assertEqual((mesh_path.resolve(),), source.collision_mesh_paths)

    def test_read_sdf_source_accepts_external_mesh_uri_without_resolution(self) -> None:
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

        source = read_sdf_source(source_path)

        self.assertEqual((), source.mesh_paths)

    def test_read_sdf_source_accepts_world_models(self) -> None:
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

        source = read_sdf_source(source_path)

        self.assertEqual(("sample_world",), source.world_names)
        self.assertEqual(("sample",), source.model_names)

    def test_read_sdf_source_accepts_world_only_scene(self) -> None:
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

        source = read_sdf_source(source_path)

        self.assertEqual(("sample_world",), source.world_names)
        self.assertEqual((), source.model_names)

    def test_read_sdf_source_rejects_missing_root(self) -> None:
        source_path = self._write_sdf(
            "robot",
            """
            <model name="sample">
              <link name="base_link" />
            </model>
            """,
        )

        with self.assertRaisesRegex(SdfSourceError, "root element must be <sdf>"):
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_missing_version(self) -> None:
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
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_missing_model_name(self) -> None:
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
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_duplicate_links(self) -> None:
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
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_missing_joint_child_link(self) -> None:
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
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_duplicate_joints(self) -> None:
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
            read_sdf_source(source_path)

    def test_read_sdf_source_rejects_missing_local_mesh(self) -> None:
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
            read_sdf_source(source_path)


if __name__ == "__main__":
    unittest.main()
