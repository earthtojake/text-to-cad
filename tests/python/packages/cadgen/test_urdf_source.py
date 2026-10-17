import unittest
from pathlib import Path

from tests.python.support.tmp_root import generated_cad_directory

from cadgen.findings import format_findings
from cadgen.urdf_source import (
    MeshUriKind,
    UrdfSource,
    classify_mesh_uri,
    resolve_mesh_uri,
    validate_urdf_file,
)


class UrdfSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = generated_cad_directory(prefix="tmp-urdf-source-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _file_ref(self, name: str) -> Path:
        return (self.temp_root / f"{name}.urdf").resolve()

    def _write_mesh(self, name: str) -> Path:
        mesh_path = self.temp_root / name if Path(name).suffix else self.temp_root / f"{name}.stl"
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        mesh_path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")
        return mesh_path

    def _write_urdf(self, name: str, body: str) -> Path:
        urdf_path = self.temp_root / f"{name}.urdf"
        urdf_path.write_text(body.strip() + "\n", encoding="utf-8")
        return urdf_path

    def validated(self, path: Path, **options) -> tuple[UrdfSource, list[str]]:
        """The validator's source for a URDF it accepts, and its warnings' messages."""
        source, result = validate_urdf_file(path, **options)
        self.assertEqual([], result.errors, format_findings(result.errors))
        return source, [finding.message for finding in result.warnings]

    def assertRefused(self, path: Path, message: str) -> None:
        """The validator refuses the URDF at ``path`` with an error that says ``message``."""
        _source, result = validate_urdf_file(path)
        self.assertRegex(format_findings(result.errors), message)

    def test_accepts_valid_mesh_robot(self) -> None:
        mesh_path = self._write_mesh("base")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{mesh_path.name}" scale="0.001 0.001 0.001" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual(self._file_ref("robot"), Path(source.file_ref).resolve())
        self.assertEqual("sample-robot", source.robot_name)
        self.assertEqual("base_link", source.root_link)
        self.assertEqual(("base_link",), source.links)
        self.assertEqual(0, len(source.joints))
        self.assertEqual((mesh_path.resolve(),), source.mesh_paths)
        self.assertEqual((mesh_path.resolve(),), source.visual_mesh_paths)
        self.assertEqual((), source.collision_mesh_paths)

    def test_accepts_collision_meshes(self) -> None:
        visual_mesh_path = self._write_mesh("visual")
        collision_mesh_path = self._write_mesh("collision")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{visual_mesh_path.name}" />
                  </geometry>
                </visual>
                <collision>
                  <origin xyz="0 0 0" rpy="0 0 0" />
                  <geometry>
                    <mesh filename="{collision_mesh_path.name}" />
                  </geometry>
                </collision>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual(
            (visual_mesh_path.resolve(), collision_mesh_path.resolve()),
            source.mesh_paths,
        )
        self.assertEqual((visual_mesh_path.resolve(),), source.visual_mesh_paths)
        self.assertEqual((collision_mesh_path.resolve(),), source.collision_mesh_paths)

    def test_accepts_primitive_collision_geometry(self) -> None:
        visual_mesh_path = self._write_mesh("visual")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{visual_mesh_path.name}" />
                  </geometry>
                </visual>
                <collision>
                  <geometry>
                    <box size="0.1 0.2 0.3" />
                  </geometry>
                </collision>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual((visual_mesh_path.resolve(),), source.mesh_paths)
        self.assertEqual((), source.collision_mesh_paths)

    def test_accepts_primitive_visual_geometry(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <box size="0.1 0.2 0.3" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual(("base_link",), source.links)
        self.assertEqual((), source.mesh_paths)

    def test_accepts_non_stl_mesh_formats(self) -> None:
        visual_mesh_path = self._write_mesh("meshes/base.dae")
        collision_mesh_path = self._write_mesh("meshes/base_collision.obj")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{visual_mesh_path.relative_to(self.temp_root).as_posix()}" />
                  </geometry>
                </visual>
                <collision>
                  <geometry>
                    <mesh filename="{collision_mesh_path.relative_to(self.temp_root).as_posix()}" />
                  </geometry>
                </collision>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual((visual_mesh_path.resolve(), collision_mesh_path.resolve()), source.mesh_paths)

    def test_classifies_mesh_uris(self) -> None:
        package_ref = classify_mesh_uri("package://robot_description/meshes/base.stl")
        self.assertEqual(MeshUriKind.PACKAGE, package_ref.kind)
        self.assertEqual("robot_description", package_ref.package_name)
        self.assertEqual("meshes/base.stl", package_ref.package_path.as_posix())

        self.assertEqual(MeshUriKind.REMOTE, classify_mesh_uri("https://example.com/base.stl").kind)
        self.assertEqual(MeshUriKind.LOCAL_ABSOLUTE, classify_mesh_uri("/tmp/base.stl").kind)
        self.assertEqual(MeshUriKind.LOCAL_RELATIVE, classify_mesh_uri("meshes/base.stl").kind)

    def test_resolves_package_mesh_uri_with_package_map(self) -> None:
        package_root = self.temp_root / "robot_description"
        mesh_path = package_root / "meshes" / "base.stl"
        mesh_path.parent.mkdir(parents=True)
        mesh_path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")

        self.assertEqual(
            mesh_path.resolve(),
            resolve_mesh_uri(
                "package://robot_description/meshes/base.stl",
                package_map={"robot_description": package_root},
            ),
        )

    def test_accepts_unresolved_package_mesh_with_warning(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="package://robot_description/meshes/base.stl" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        source, warnings = self.validated(source_path)

        self.assertEqual((), source.mesh_paths)
        self.assertTrue(any("syntax is valid but was not resolved" in message for message in warnings))

    def test_accepts_unresolved_remote_mesh_with_warning(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="https://example.com/meshes/base.glb" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        source, warnings = self.validated(source_path)

        self.assertEqual((), source.mesh_paths)
        self.assertTrue(any("is not a local mesh URI and was not resolved" in message for message in warnings))

    def test_resolves_package_mesh_with_package_map(self) -> None:
        package_root = self.temp_root / "robot_description"
        mesh_path = package_root / "meshes" / "base.stl"
        mesh_path.parent.mkdir(parents=True)
        mesh_path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="package://robot_description/meshes/base.stl" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path, package_map={"robot_description": package_root})

        self.assertEqual((mesh_path.resolve(),), source.mesh_paths)

    def test_accepts_valid_inertial(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <origin xyz="0 0 0" rpy="0 0 0" />
                  <mass value="1.2" />
                  <inertia ixx="0.1" ixy="0" ixz="0" iyy="0.1" iyz="0" izz="0.1" />
                </inertial>
              </link>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual(("base_link",), source.links)

    def test_rejects_nonpositive_inertial_mass(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <mass value="0" />
                  <inertia ixx="0.1" ixy="0" ixz="0" iyy="0.1" iyz="0" izz="0.1" />
                </inertial>
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "mass must be positive")

    def test_warns_on_invalid_inertia_triangle(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <mass value="1" />
                  <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="1" />
                </inertial>
              </link>
            </robot>
            """,
        )

        _, warnings = self.validated(source_path)
        self.assertTrue(any("triangle" in message for message in warnings))

    def test_warns_on_inertia_magnitude_implausible_for_box(self) -> None:
        # references/inertials.md's own "Sanity Gate" example: a 0.5 kg,
        # 10 cm box with ixx = 2.0 kg*m^2 is wrong by ~1000x.
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <mass value="0.5" />
                  <inertia ixx="2.0" ixy="0" ixz="0" iyy="2.0" iyz="0" izz="2.0" />
                </inertial>
                <visual>
                  <geometry><box size="0.1 0.1 0.1" /></geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        _, warnings = self.validated(source_path)
        self.assertTrue(any("more than 10x off" in message for message in warnings))

    def test_accepts_inertia_matching_box_geometry(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <mass value="0.5" />
                  <inertia ixx="0.000833" ixy="0" ixz="0" iyy="0.000833" iyz="0" izz="0.000833" />
                </inertial>
                <visual>
                  <geometry><box size="0.1 0.1 0.1" /></geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        _, warnings = self.validated(source_path)
        self.assertFalse(any("more than 10x off" in message for message in warnings))

    def test_skips_magnitude_check_for_mesh_geometry(self) -> None:
        # No independent size is available for a mesh without loading the
        # file, so the magnitude check should not fire here even though this
        # inertia is just as implausible as the box case above.
        mesh_path = self._write_mesh("base")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <inertial>
                  <mass value="0.5" />
                  <inertia ixx="2.0" ixy="0" ixz="0" iyy="2.0" iyz="0" izz="2.0" />
                </inertial>
                <visual>
                  <geometry><mesh filename="{mesh_path.as_posix()}" /></geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        _, warnings = self.validated(source_path)
        self.assertFalse(any("more than 10x off" in message for message in warnings))

    def test_rejects_invalid_origin_vector(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link" />
              <link name="arm_link" />
              <joint name="base_to_arm" type="fixed">
                <origin xyz="0 0" />
                <parent link="base_link" />
                <child link="arm_link" />
              </joint>
            </robot>
            """,
        )

        self.assertRefused(source_path, "origin xyz must have 3 values")

    def test_rejects_zero_joint_axis(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link" />
              <link name="arm_link" />
              <joint name="base_to_arm" type="revolute">
                <parent link="base_link" />
                <child link="arm_link" />
                <axis xyz="0 0 0" />
                <limit lower="-1" upper="1" />
              </joint>
            </robot>
            """,
        )

        self.assertRefused(source_path, "axis must be nonzero")

    def test_rejects_invalid_mesh_scale(self) -> None:
        mesh_path = self._write_mesh("base.obj")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{mesh_path.name}" scale="1 0 1" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "scale values must be nonzero")

    def test_rejects_invalid_primitive_dimensions(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <collision>
                  <geometry>
                    <sphere radius="0" />
                  </geometry>
                </collision>
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "sphere radius must be positive")

    def test_rejects_missing_geometry_element(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual />
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "visual requires <geometry>")

    def test_rejects_duplicate_links(self) -> None:
        mesh_path = self._write_mesh("base")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{mesh_path.name}" />
                  </geometry>
                </visual>
              </link>
              <link name="base_link" />
            </robot>
            """,
        )

        self.assertRefused(source_path, "duplicates")

    def test_rejects_missing_mesh(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="does-not-exist.stl" />
                  </geometry>
                </visual>
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "missing mesh file")

    def test_rejects_missing_collision_mesh(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link">
                <collision>
                  <geometry>
                    <mesh filename="does-not-exist.stl" />
                  </geometry>
                </collision>
              </link>
            </robot>
            """,
        )

        self.assertRefused(source_path, "missing mesh file")

    def test_accepts_prismatic_joint_with_limits(self) -> None:
        mesh_path = self._write_mesh("base")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{mesh_path.name}" />
                  </geometry>
                </visual>
              </link>
              <link name="arm_link" />
              <joint name="base_to_arm" type="prismatic">
                <parent link="base_link" />
                <child link="arm_link" />
                <limit lower="0" upper="0.05" effort="1" velocity="1" />
              </joint>
            </robot>
            """,
        )

        source, _ = self.validated(source_path)

        self.assertEqual("prismatic", source.joints[0].joint_type)
        self.assertEqual(0.0, source.joints[0].lower)
        self.assertEqual(0.05, source.joints[0].upper)

    def test_rejects_reversed_joint_limits(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link" />
              <link name="arm_link" />
              <joint name="base_to_arm" type="prismatic">
                <parent link="base_link" />
                <child link="arm_link" />
                <limit lower="1" upper="0" />
              </joint>
            </robot>
            """,
        )

        self.assertRefused(source_path, "lower limit exceeds upper limit")

    def test_rejects_unsupported_joint_type(self) -> None:
        mesh_path = self._write_mesh("base")
        source_path = self._write_urdf(
            "robot",
            f"""
            <robot name="sample-robot">
              <link name="base_link">
                <visual>
                  <geometry>
                    <mesh filename="{mesh_path.name}" />
                  </geometry>
                </visual>
              </link>
              <link name="arm_link" />
              <joint name="base_to_arm" type="planar">
                <parent link="base_link" />
                <child link="arm_link" />
              </joint>
            </robot>
            """,
        )

        self.assertRefused(source_path, "unsupported type")

    def test_file_ref_ignores_neighbor_step_toml(self) -> None:
        source_path = self._write_urdf(
            "robot",
            """
            <robot name="sample-robot">
              <link name="base_link" />
            </robot>
            """,
        )
        stale_path = self.temp_root / "robot.step.toml"
        stale_path.write_text(
            "\n".join(
                [
                    'kind = "part"',
                    'source = "robot.urdf"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        source, _ = self.validated(source_path)

        self.assertEqual(source_path.resolve(), Path(source.file_ref).resolve())


if __name__ == "__main__":
    unittest.main()
