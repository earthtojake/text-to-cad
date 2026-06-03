import tempfile
import unittest
from pathlib import Path

from sdf.validation import validate_sdf_xml


class SdfValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-sdf-validation-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _validate(self, body: str):
        return validate_sdf_xml(
            body.strip(),
            source_path=self.temp_root / "generated.sdf",
            base_dir=self.temp_root,
        )

    def _error_codes(self, body: str) -> set[str]:
        return {finding.code for finding in self._validate(body).errors}

    def _warning_codes(self, body: str) -> set[str]:
        return {finding.code for finding in self._validate(body).warnings}

    def test_valid_minimal_model_passes(self) -> None:
        result = self._validate(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
              </model>
            </sdf>
            """
        )

        self.assertEqual([], result.errors)

    def test_valid_world_only_scene_passes(self) -> None:
        result = self._validate(
            """
            <sdf version="1.12">
              <world name="sample_world">
                <include><uri>model://sun</uri></include>
                <light name="key" type="directional" />
              </world>
            </sdf>
            """
        )

        self.assertEqual([], result.errors)

    def test_malformed_pose_length_fails(self) -> None:
        self.assertIn(
            "invalid_numeric_vector",
            self._error_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <pose>1 2 3</pose>
                    <link name="base_link" />
                  </model>
                </sdf>
                """
            ),
        )

    def test_quaternion_pose_zero_norm_fails_and_non_unit_warns(self) -> None:
        self.assertIn(
            "zero_quaternion",
            self._error_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <pose rotation_format="quat_xyzw">0 0 0 0 0 0 0</pose>
                    <link name="base_link" />
                  </model>
                </sdf>
                """
            ),
        )
        self.assertIn(
            "non_unit_quaternion",
            self._warning_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <pose rotation_format="quat_xyzw">0 0 0 0 0 0 2</pose>
                    <link name="base_link" />
                  </model>
                </sdf>
                """
            ),
        )

    def test_nontrivial_pose_without_relative_to_warns(self) -> None:
        self.assertIn(
            "pose_missing_relative_to",
            self._warning_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <link name="base_link">
                      <pose>1 0 0 0 0 0</pose>
                    </link>
                  </model>
                </sdf>
                """
            ),
        )

    def test_frame_cycle_fails(self) -> None:
        self.assertIn(
            "frame_cycle",
            self._error_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <frame name="a" attached_to="b" />
                    <frame name="b" attached_to="a" />
                    <link name="base_link" />
                  </model>
                </sdf>
                """
            ),
        )

    def test_joint_type_and_world_child_are_checked(self) -> None:
        illegal_type_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="arm_link" />
                <joint name="bad" type="hinge">
                  <parent>base_link</parent>
                  <child>arm_link</child>
                </joint>
              </model>
            </sdf>
            """
        )
        self.assertIn("unknown_joint_type", illegal_type_errors)

        world_child_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <joint name="bad" type="fixed">
                  <parent>base_link</parent>
                  <child>world</child>
                </joint>
              </model>
            </sdf>
            """
        )
        self.assertIn("invalid_joint_child", world_child_errors)

    def test_axis_zero_fails_and_non_unit_warns(self) -> None:
        zero_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="arm_link" />
                <joint name="bad" type="revolute">
                  <parent>base_link</parent>
                  <child>arm_link</child>
                  <axis><xyz>0 0 0</xyz></axis>
                </joint>
              </model>
            </sdf>
            """
        )
        self.assertIn("zero_axis", zero_errors)

        warnings = self._warning_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="arm_link" />
                <joint name="warns" type="revolute">
                  <parent>base_link</parent>
                  <child>arm_link</child>
                  <axis><xyz>0 0 2</xyz></axis>
                </joint>
              </model>
            </sdf>
            """
        )
        self.assertIn("non_unit_axis", warnings)

    def test_invalid_primitive_dimensions_fail(self) -> None:
        errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry><box><size>1 0 1</size></box></geometry>
                  </visual>
                </link>
              </model>
            </sdf>
            """
        )

        self.assertIn("invalid_dimension", errors)

    def test_visual_without_geometry_fails(self) -> None:
        self.assertIn(
            "invalid_geometry_count",
            self._error_codes(
                """
                <sdf version="1.12">
                  <model name="sample">
                    <link name="base_link">
                      <visual name="base_visual" />
                    </link>
                  </model>
                </sdf>
                """
            ),
        )

    def test_mesh_uri_resolution_distinguishes_local_and_external(self) -> None:
        local_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry><mesh><uri>meshes/missing.stl</uri></mesh></geometry>
                  </visual>
                </link>
              </model>
            </sdf>
            """
        )
        self.assertIn("missing_mesh_file", local_errors)

        external_result = self._validate(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <visual name="base_visual">
                    <geometry><mesh><uri>package://sample/meshes/base.dae</uri></mesh></geometry>
                  </visual>
                </link>
              </model>
            </sdf>
            """
        )
        self.assertEqual([], external_result.errors)

    def test_invalid_inertial_values_fail(self) -> None:
        mass_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <inertial><mass>0</mass></inertial>
                </link>
              </model>
            </sdf>
            """
        )
        self.assertIn("invalid_mass", mass_errors)

        inertia_errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <inertial>
                    <mass>1</mass>
                    <inertia>
                      <ixx>1</ixx><iyy>1</iyy><izz>-1</izz>
                      <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
                    </inertia>
                  </inertial>
                </link>
              </model>
            </sdf>
            """
        )
        self.assertIn("invalid_inertia_matrix", inertia_errors)

    def test_sensor_plugin_and_include_required_fields(self) -> None:
        errors = self._error_codes(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link">
                  <sensor name="camera" />
                </link>
                <plugin name="controller" />
                <include />
              </model>
            </sdf>
            """
        )

        self.assertIn("missing_sensor_type", errors)
        self.assertIn("missing_plugin_filename", errors)
        self.assertIn("missing_child_text", errors)

    def test_plugin_contents_are_static_metadata_not_motion_contracts(self) -> None:
        result = self._validate(
            """
            <sdf version="1.12">
              <model name="sample">
                <link name="base_link" />
                <link name="door_link" />
                <joint name="door_joint" type="fixed">
                  <parent>base_link</parent>
                  <child>door_link</child>
                </joint>
                <plugin name="controller" filename="gz-sim-custom-controller-system">
                  <custom_parameter>opaque</custom_parameter>
                  <nested_block invalid_for_validator="but_plugin_owned" />
                </plugin>
              </model>
            </sdf>
            """
        )

        self.assertEqual([], result.errors)


if __name__ == "__main__":
    unittest.main()
