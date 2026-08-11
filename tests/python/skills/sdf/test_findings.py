"""Adversarial edge-case coverage for the SDF validator.

Each case is a deliberately broken (or deliberately suspicious) SDFormat
snippet pinned to the finding code the validator must emit. This file is the
coverage contract for the validator: new checks land with a case here.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/sdf/scripts")

from sdf.validation import validate_sdf_xml


def _model(body: str, *, name: str = "edge_bot", version: str = "1.12") -> str:
    return f'<sdf version="{version}">\n<model name="{name}">\n{body}\n</model>\n</sdf>\n'


LINK = '<link name="base"/>'
TWO_LINKS = '<link name="base"/><link name="arm"/>'


def _joint(body: str, *, joint_type: str = "revolute", name: str = "j1") -> str:
    return (
        f"{TWO_LINKS}<joint name=\"{name}\" type=\"{joint_type}\">"
        f"<parent>base</parent><child>arm</child>{body}</joint>"
    )


AXIS = "<axis><xyz>0 0 1</xyz></axis>"

# (case name, sdf text, expected code, expected severity)
CASES = [
    # --- document shape ---
    ("invalid_xml", "<sdf version='1.12'><model></sdf>", "invalid_xml", "error"),
    ("invalid_root", "<xml version='1.12'/>", "invalid_root", "error"),
    ("missing_version", f"<sdf>{_model(LINK)[19:]}", "missing_version", "error"),
    ("unusual_version", _model(LINK, version="banana"), "unusual_version", "warning"),
    ("unknown_sdf_version", _model(LINK, version="2.0"), "unknown_sdf_version", "warning"),
    ("empty_document", '<sdf version="1.12"></sdf>', "empty_document", "error"),
    # --- names and scopes ---
    ("duplicate_link_names", _model('<link name="a"/><link name="a"/>'), "duplicate_names", "error"),
    (
        "link_frame_name_collision",
        _model('<link name="base"/><frame name="base" attached_to="base"/>'),
        "cross_type_name_collision",
        "error",
    ),
    (
        "link_joint_name_collision",
        _model(_joint(AXIS + '<axis><limit><lower>-1</lower><upper>1</upper></limit></axis>', name="arm")),
        "cross_type_name_collision",
        "error",
    ),
    ("empty_model", _model('<pose>0 0 1 0 0 0</pose>'), "empty_model", "error"),
    ("unknown_model_child", _model(f'{LINK}<links/>'), "unknown_element", "warning"),
    ("unknown_link_child", _model('<link name="base"><intertial/></link>'), "unknown_element", "warning"),
    ("unknown_joint_child", _model(_joint(AXIS + "<mimic/>")), "unknown_element", "warning"),
    (
        "unknown_visual_child",
        _model('<link name="base"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry><colour/></visual></link>'),
        "unknown_element",
        "warning",
    ),
    (
        "unknown_inertial_child",
        _model('<link name="base"><inertial><mass>1</mass><com>0</com></inertial></link>'),
        "unknown_element",
        "warning",
    ),
    # --- poses and frames ---
    ("nontrivial_link_pose_without_relative_to", _model('<link name="base"><pose>1 0 0 0 0 0</pose></link>'), "pose_missing_relative_to", "warning"),
    ("pose_unresolved_relative_to", _model('<link name="base"><pose relative_to="ghost">0 0 0 0 0 0</pose></link>'), "unresolved_reference", "error"),
    ("pose_wrong_arity", _model('<link name="base"><pose>1 0 0</pose></link>'), "invalid_numeric_vector", "error"),
    ("pose_degrees", _model('<link name="base"><pose degrees="true">0 0 0 0 0 90</pose></link>'), "pose_uses_degrees", "warning"),
    (
        "zero_quaternion",
        _model('<link name="base"><pose rotation_format="quat_xyzw">0 0 0 0 0 0 0</pose></link>'),
        "zero_quaternion",
        "error",
    ),
    (
        "non_unit_quaternion",
        _model('<link name="base"><pose rotation_format="quat_xyzw">0 0 0 0 0 0.5 1</pose></link>'),
        "non_unit_quaternion",
        "warning",
    ),
    (
        "unsupported_rotation_format",
        _model('<link name="base"><pose rotation_format="matrix">0 0 0 0 0 0</pose></link>'),
        "unsupported_rotation_format",
        "error",
    ),
    ("invalid_pose_degrees_attr", _model('<link name="base"><pose degrees="maybe">0 0 0 0 0 0</pose></link>'), "invalid_pose_degrees", "error"),
    (
        "frame_cycle",
        _model(f'{LINK}<frame name="f1" attached_to="f2"/><frame name="f2" attached_to="f1"/>'),
        "frame_cycle",
        "error",
    ),
    (
        "scoped_reference_unchecked",
        _model('<link name="base"><pose relative_to="nested::frame">1 0 0 0 0 0</pose></link>'),
        "scoped_reference_unchecked",
        "warning",
    ),
    (
        "malformed_scoped_reference",
        _model('<link name="base"><pose relative_to="nested::">1 0 0 0 0 0</pose></link>'),
        "invalid_scoped_reference",
        "error",
    ),
    # --- joints ---
    ("missing_joint_type", _model(f'{TWO_LINKS}<joint name="j1"><parent>base</parent><child>arm</child></joint>'), "missing_joint_type", "error"),
    ("unknown_joint_type", _model(_joint(AXIS, joint_type="twisty")), "unknown_joint_type", "error"),
    ("missing_joint_parent", _model(f'{TWO_LINKS}<joint name="j1" type="fixed"><child>arm</child></joint>'), "missing_child_text", "error"),
    ("world_as_child", _model(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent>base</parent><child>world</child></joint>'), "invalid_joint_child", "error"),
    ("missing_link_reference", _model(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent>base</parent><child>ghost</child></joint>'), "missing_link_reference", "error"),
    ("missing_axis", _model(_joint("")), "missing_joint_axis", "warning"),
    ("missing_axis_xyz", _model(_joint("<axis></axis>")), "missing_axis_xyz", "error"),
    ("zero_axis", _model(_joint("<axis><xyz>0 0 0</xyz></axis>")), "zero_axis", "error"),
    ("non_unit_axis", _model(_joint("<axis><xyz>0 0 2</xyz></axis>")), "non_unit_axis", "warning"),
    ("axis_unresolved_expressed_in", _model(_joint('<axis><xyz expressed_in="ghost">0 0 1</xyz></axis>')), "unresolved_reference", "error"),
    ("axis2_on_revolute", _model(_joint(AXIS + "<axis2><xyz>1 0 0</xyz></axis2>")), "unsupported_axis2", "error"),
    (
        "reversed_joint_limits",
        _model(_joint("<axis><xyz>0 0 1</xyz><limit><lower>1</lower><upper>-1</upper></limit></axis>")),
        "invalid_joint_limit",
        "error",
    ),
    (
        "negative_effort",
        _model(_joint("<axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper><effort>-5</effort></limit></axis>")),
        "negative_effort",
        "error",
    ),
    (
        "negative_velocity",
        _model(_joint("<axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper><velocity>-2</velocity></limit></axis>")),
        "negative_velocity",
        "error",
    ),
    (
        "negative_damping",
        _model(_joint("<axis><xyz>0 0 1</xyz><dynamics><damping>-0.5</damping></dynamics></axis>")),
        "negative_damping",
        "error",
    ),
    (
        "negative_friction",
        _model(_joint("<axis><xyz>0 0 1</xyz><dynamics><friction>-0.5</friction></dynamics></axis>")),
        "negative_friction",
        "error",
    ),
    (
        "continuous_with_limits",
        _model(_joint("<axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper></limit></axis>", joint_type="continuous")),
        "continuous_joint_limits",
        "warning",
    ),
    # --- geometry and meshes ---
    ("empty_geometry", _model('<link name="base"><visual name="v"><geometry/></visual></link>'), "invalid_geometry_shape", "error"),
    ("two_geometries", _model('<link name="base"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry><geometry><sphere><radius>1</radius></sphere></geometry></visual></link>'), "invalid_geometry_count", "error"),
    ("zero_box_size", _model('<link name="base"><visual name="v"><geometry><box><size>0 1 1</size></box></geometry></visual></link>'), "invalid_dimension", "error"),
    ("negative_sphere", _model('<link name="base"><collision name="c"><geometry><sphere><radius>-1</radius></sphere></geometry></collision></link>'), "invalid_dimension", "error"),
    ("zero_mesh_scale", _model('<link name="base"><visual name="v"><geometry><mesh><uri>m.stl</uri><scale>1 0 1</scale></mesh></geometry></visual></link>'), "zero_mesh_scale", "error"),
    ("negative_mesh_scale", _model('<link name="base"><visual name="v"><geometry><mesh><uri>m.stl</uri><scale>1 -1 1</scale></mesh></geometry></visual></link>'), "negative_mesh_scale", "warning"),
    ("missing_mesh_file", _model('<link name="base"><visual name="v"><geometry><mesh><uri>nowhere/m.stl</uri></mesh></geometry></visual></link>'), "missing_mesh_file", "error"),
    ("odd_mesh_scheme", _model('<link name="base"><visual name="v"><geometry><mesh><uri>ftp://x/m.stl</uri></mesh></geometry></visual></link>'), "unresolved_mesh_uri_scheme", "warning"),
    (
        "collision_reuses_visual_mesh",
        _model(
            '<link name="base">'
            '<visual name="v"><geometry><mesh><uri>m.stl</uri></mesh></geometry></visual>'
            '<collision name="c"><geometry><mesh><uri>m.stl</uri></mesh></geometry></collision>'
            "</link>"
        ),
        "collision_reuses_visual_mesh",
        "warning",
    ),
    # --- inertials ---
    ("nonpositive_mass", _model('<link name="base"><inertial><mass>0</mass><inertia><ixx>1</ixx><iyy>1</iyy><izz>1</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial></link>'), "invalid_mass", "error"),
    ("missing_inertia_matrix", _model('<link name="base"><inertial><mass>1</mass></inertial></link>'), "missing_inertia_matrix", "warning"),
    (
        "non_psd_inertia",
        _model('<link name="base"><inertial><mass>1</mass><inertia><ixx>0.001</ixx><iyy>0.001</iyy><izz>0.001</izz><ixy>0.01</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial></link>'),
        "invalid_inertia_matrix",
        "error",
    ),
    (
        "inertia_triangle_inequality",
        _model('<link name="base"><inertial><mass>1</mass><inertia><ixx>0.001</ixx><iyy>0.001</iyy><izz>1</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial></link>'),
        "inertia_triangle_inequality",
        "warning",
    ),
    (
        "dynamic_link_without_inertial",
        _model(
            '<link name="base"/><link name="arm"><collision name="c"><geometry><box><size>1 1 1</size></box></geometry></collision></link>'
            '<joint name="j1" type="revolute"><parent>base</parent><child>arm</child><axis><xyz>0 0 1</xyz></axis></joint>'
        ),
        "missing_inertial",
        "warning",
    ),
    # --- sensors, plugins, lights ---
    ("missing_sensor_type", _model('<link name="base"><sensor name="s"/></link>'), "missing_sensor_type", "error"),
    ("typo_sensor_type", _model('<link name="base"><sensor name="s" type="gpu-lidar"/></link>'), "unknown_sensor_type", "warning"),
    ("negative_update_rate", _model('<link name="base"><sensor name="s" type="imu"><update_rate>-10</update_rate></sensor></link>'), "invalid_sensor_update_rate", "error"),
    ("missing_plugin_filename", _model(f'{LINK}<plugin name="p"/>'), "missing_plugin_filename", "error"),
    ("anonymous_plugin", _model(f'{LINK}<plugin filename="libp.so"/>'), "missing_plugin_name", "warning"),
    (
        "missing_light_type",
        f'<sdf version="1.12"><world name="w"><light name="sun"/></world></sdf>',
        "missing_light_type",
        "error",
    ),
    (
        "unknown_light_type",
        f'<sdf version="1.12"><world name="w"><light name="sun" type="laser"/></world></sdf>',
        "unknown_light_type",
        "error",
    ),
    (
        "light_pose_unresolved",
        f'<sdf version="1.12"><world name="w"><light name="sun" type="directional"><pose relative_to="ghost">0 0 10 0 0 0</pose></light></world></sdf>',
        "unresolved_reference",
        "error",
    ),
    (
        "link_light_validated",
        _model('<link name="base"><light name="lamp" type="laser"/></link>'),
        "unknown_light_type",
        "error",
    ),
]


class SdfFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-sdf-findings-")
        self.temp_root = Path(self._tempdir.name)
        (self.temp_root / "m.stl").write_text("solid m\nendsolid m\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _codes(self, sdf_text: str) -> tuple[set[str], set[str]]:
        result = validate_sdf_xml(
            sdf_text,
            source_path=self.temp_root / "case.sdf",
            base_dir=self.temp_root,
        )
        return (
            {finding.code for finding in result.errors},
            {finding.code for finding in result.warnings},
        )

    def test_cases_emit_expected_codes(self) -> None:
        for name, sdf_text, expected_code, severity in CASES:
            with self.subTest(case=name):
                error_codes, warning_codes = self._codes(sdf_text)
                if severity == "error":
                    self.assertIn(expected_code, error_codes, f"{name}: errors were {error_codes}")
                else:
                    self.assertIn(expected_code, warning_codes, f"{name}: warnings were {warning_codes}")
                    self.assertFalse(error_codes, f"{name}: unexpected errors {error_codes}")

    def test_clean_model_has_no_findings(self) -> None:
        sdf_text = _model(
            '<link name="base">'
            "<inertial><mass>1</mass><inertia><ixx>0.01</ixx><iyy>0.01</iyy><izz>0.01</izz>"
            "<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>"
            '<visual name="v"><geometry><mesh><uri>m.stl</uri></mesh></geometry></visual>'
            '<collision name="c"><geometry><box><size>0.1 0.1 0.1</size></box></geometry></collision>'
            "</link>"
            '<link name="arm"><pose relative_to="j1">0 0 0 0 0 0</pose>'
            "<inertial><mass>0.5</mass><inertia><ixx>0.001</ixx><iyy>0.001</iyy><izz>0.001</izz>"
            "<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>"
            "</link>"
            '<joint name="j1" type="revolute"><pose relative_to="base">0 0 0.1 0 0 0</pose>'
            "<parent>base</parent><child>arm</child>"
            "<axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper>"
            "<effort>2</effort><velocity>1</velocity></limit></axis></joint>"
        )
        error_codes, warning_codes = self._codes(sdf_text)
        self.assertFalse(error_codes)
        self.assertFalse(warning_codes)

    def test_joint_is_a_valid_relative_to_target(self) -> None:
        # SDFormat >= 1.7: joints participate in the frame graph.
        sdf_text = _model(
            f"{TWO_LINKS}"
            '<joint name="j1" type="fixed"><parent>base</parent><child>arm</child></joint>'
            '<frame name="tcp" attached_to="j1"><pose relative_to="j1">0 0 0.1 0 0 0</pose></frame>'
        )
        error_codes, _ = self._codes(sdf_text)
        self.assertFalse(error_codes)

    def test_unlimited_effort_sentinel_allowed(self) -> None:
        sdf_text = _model(
            _joint("<axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper><effort>-1</effort></limit></axis>")
        )
        error_codes, _ = self._codes(sdf_text)
        self.assertNotIn("negative_effort", error_codes)

    def test_static_world_only_document_is_clean(self) -> None:
        sdf_text = (
            '<sdf version="1.12"><world name="w">'
            '<light name="sun" type="directional"><pose relative_to="world">0 0 10 0 0 0</pose></light>'
            "</world></sdf>"
        )
        error_codes, warning_codes = self._codes(sdf_text)
        self.assertFalse(error_codes)
        self.assertFalse(warning_codes)

    def test_multiple_errors_collected_in_one_pass(self) -> None:
        sdf_text = _model(
            '<link name="a"/><link name="a"/>'
            '<joint name="j1" type="twisty"><parent>a</parent><child>ghost</child></joint>'
        )
        error_codes, _ = self._codes(sdf_text)
        self.assertLessEqual(
            {"duplicate_names", "unknown_joint_type", "missing_link_reference"},
            error_codes,
        )


if __name__ == "__main__":
    unittest.main()
