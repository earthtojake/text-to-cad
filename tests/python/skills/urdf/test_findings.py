"""Adversarial edge-case coverage for the URDF validator.

Each case is a deliberately broken (or deliberately suspicious) URDF snippet
pinned to the finding code the validator must emit. This file is the coverage
contract for the validator: new checks land with a case here.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/urdf/scripts")

from urdf.source import symmetric_inertia_eigenvalues, validate_urdf_file


def _wrap(body: str, name: str = "edge") -> str:
    return f'<robot name="{name}">\n{body}\n</robot>\n'


TWO_LINKS = '<link name="base"/>\n<link name="arm"/>'


def _joint(body: str = "", *, joint_type: str = "revolute", limit: str = '<limit lower="-1" upper="1" effort="1" velocity="1"/>') -> str:
    return (
        f'{TWO_LINKS}\n<joint name="j1" type="{joint_type}">'
        f'<parent link="base"/><child link="arm"/><axis xyz="0 0 1"/>{limit}{body}</joint>'
    )


# (case name, xml text, expected finding code, expected severity)
ERROR_CASES = [
    ("invalid_xml", "<robot name='x'><link></robot>", "invalid_xml"),
    ("invalid_root", "<router name='x'/>", "invalid_root"),
    ("missing_robot_name", '<robot><link name="base"/></robot>', "missing_robot_name"),
    ("missing_link_name", _wrap("<link/>"), "missing_link_name"),
    ("no_links", '<robot name="x"></robot>', "no_links"),
    ("duplicate_link_name", _wrap('<link name="base"/><link name="base"/>'), "duplicate_link_name"),
    (
        "duplicate_inertial",
        _wrap(
            '<link name="base">'
            '<inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>'
            '<inertial><mass value="2"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>'
            "</link>"
        ),
        "duplicate_inertial",
    ),
    ("missing_mass", _wrap('<link name="base"><inertial><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "missing_mass"),
    ("zero_mass", _wrap('<link name="base"><inertial><mass value="0"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "nonpositive_mass"),
    ("negative_mass", _wrap('<link name="base"><inertial><mass value="-0.5"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "nonpositive_mass"),
    ("missing_inertia", _wrap('<link name="base"><inertial><mass value="1"/></inertial></link>'), "missing_inertia"),
    ("missing_inertia_component", _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0"/></inertial></link>'), "missing_attribute"),
    ("nonnumeric_inertia", _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="abc" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "invalid_number"),
    ("infinite_mass", _wrap('<link name="base"><inertial><mass value="inf"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "nonfinite_number"),
    ("negative_inertia_diagonal", _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="-1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'), "nonpositive_inertia_diagonal"),
    ("non_psd_inertia", _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="0.001" ixy="0.01" ixz="0" iyy="0.001" iyz="0" izz="0.001"/></inertial></link>'), "inertia_not_psd"),
    ("missing_geometry", _wrap('<link name="base"><visual></visual></link>'), "missing_geometry"),
    ("empty_geometry", _wrap('<link name="base"><visual><geometry></geometry></visual></link>'), "invalid_geometry_count"),
    (
        "two_geometry_children",
        _wrap('<link name="base"><visual><geometry><box size="1 1 1"/><sphere radius="1"/></geometry></visual></link>'),
        "invalid_geometry_count",
    ),
    ("capsule_geometry", _wrap('<link name="base"><visual><geometry><capsule radius="1" length="1"/></geometry></visual></link>'), "unsupported_geometry"),
    ("zero_box_size", _wrap('<link name="base"><visual><geometry><box size="0 1 1"/></geometry></visual></link>'), "nonpositive_dimension"),
    ("negative_cylinder_radius", _wrap('<link name="base"><collision><geometry><cylinder radius="-1" length="1"/></geometry></collision></link>'), "nonpositive_dimension"),
    ("zero_sphere_radius", _wrap('<link name="base"><visual><geometry><sphere radius="0"/></geometry></visual></link>'), "nonpositive_dimension"),
    ("missing_mesh_filename", _wrap('<link name="base"><visual><geometry><mesh/></geometry></visual></link>'), "missing_mesh_filename"),
    ("invalid_package_uri", _wrap('<link name="base"><visual><geometry><mesh filename="package://"/></geometry></visual></link>'), "invalid_mesh_uri"),
    ("zero_mesh_scale", _wrap('<link name="base"><visual><geometry><mesh filename="m.stl" scale="1 0 1"/></geometry></visual></link>'), "zero_mesh_scale"),
    ("missing_mesh_file", _wrap('<link name="base"><visual><geometry><mesh filename="nowhere/m.stl"/></geometry></visual></link>'), "missing_mesh_file"),
    ("missing_joint_name", _wrap(f'{TWO_LINKS}<joint type="fixed"><parent link="base"/><child link="arm"/></joint>'), "missing_joint_name"),
    ("planar_joint", _wrap(_joint(joint_type="planar", limit="")), "unsupported_joint_type"),
    ("floating_joint", _wrap(_joint(joint_type="floating", limit="")), "unsupported_joint_type"),
    ("missing_parent_child", _wrap(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent link="base"/></joint>'), "missing_joint_parent_child"),
    ("missing_parent_link", _wrap(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent link="ghost"/><child link="arm"/></joint>'), "missing_parent_link"),
    ("missing_child_link", _wrap(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent link="base"/><child link="ghost"/></joint>'), "missing_child_link"),
    (
        "multiple_parents",
        _wrap(
            '<link name="a"/><link name="b"/><link name="c"/>'
            '<joint name="j1" type="fixed"><parent link="a"/><child link="c"/></joint>'
            '<joint name="j2" type="fixed"><parent link="b"/><child link="c"/></joint>'
        ),
        "multiple_parents",
    ),
    ("missing_limit", _wrap(_joint(limit="")), "missing_joint_limit"),
    ("missing_limit_bounds", _wrap(_joint(limit='<limit effort="1" velocity="1"/>')), "missing_limit_bounds"),
    ("nonnumeric_limits", _wrap(_joint(limit='<limit lower="a" upper="1"/>')), "invalid_limit_bounds"),
    ("infinite_limits", _wrap(_joint(limit='<limit lower="-inf" upper="inf"/>')), "nonfinite_limit_bounds"),
    ("reversed_limits", _wrap(_joint(limit='<limit lower="1" upper="-1"/>')), "reversed_limit_bounds"),
    ("negative_effort", _wrap(_joint(limit='<limit lower="-1" upper="1" effort="-5" velocity="1"/>')), "negative_effort"),
    ("negative_velocity", _wrap(_joint(limit='<limit lower="-1" upper="1" effort="1" velocity="-2"/>')), "negative_velocity"),
    ("negative_damping", _wrap(_joint('<dynamics damping="-0.1"/>')), "negative_damping"),
    ("negative_friction", _wrap(_joint('<dynamics friction="-0.1"/>')), "negative_friction"),
    ("mimic_without_joint", _wrap(_joint("<mimic/>")), "missing_mimic_joint"),
    ("self_mimic", _wrap(_joint('<mimic joint="j1"/>')), "self_mimic"),
    ("mimic_missing_target", _wrap(_joint('<mimic joint="ghost"/>')), "missing_mimic_target"),
    (
        "mimic_of_fixed_joint",
        _wrap(
            '<link name="a"/><link name="b"/><link name="c"/>'
            '<joint name="jf" type="fixed"><parent link="a"/><child link="b"/></joint>'
            '<joint name="jr" type="revolute"><parent link="b"/><child link="c"/><axis xyz="0 0 1"/>'
            '<limit lower="-1" upper="1" effort="1" velocity="1"/><mimic joint="jf"/></joint>'
        ),
        "mimic_of_fixed_joint",
    ),
    (
        "mimic_cycle",
        _wrap(
            '<link name="a"/><link name="b"/><link name="c"/>'
            '<joint name="j1" type="revolute"><parent link="a"/><child link="b"/><axis xyz="0 0 1"/>'
            '<limit lower="-1" upper="1" effort="1" velocity="1"/><mimic joint="j2"/></joint>'
            '<joint name="j2" type="revolute"><parent link="b"/><child link="c"/><axis xyz="0 0 1"/>'
            '<limit lower="-1" upper="1" effort="1" velocity="1"/><mimic joint="j1"/></joint>'
        ),
        "mimic_cycle",
    ),
    ("zero_axis", _wrap(_joint().replace('xyz="0 0 1"', 'xyz="0 0 0"')), "zero_joint_axis"),
    ("short_axis_vector", _wrap(_joint().replace('xyz="0 0 1"', 'xyz="0 1"')), "wrong_vector_size"),
    ("bad_origin_vector", _wrap(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent link="base"/><child link="arm"/><origin xyz="0 0"/></joint>'), "wrong_vector_size"),
    ("duplicate_joint_name", _wrap(
        '<link name="a"/><link name="b"/><link name="c"/>'
        '<joint name="j" type="fixed"><parent link="a"/><child link="b"/></joint>'
        '<joint name="j" type="fixed"><parent link="b"/><child link="c"/></joint>'
    ), "duplicate_joint_name"),
    ("two_roots", _wrap('<link name="a"/><link name="b"/><link name="c"/><joint name="j1" type="fixed"><parent link="a"/><child link="b"/></joint>'), "not_a_tree"),
]

WARNING_CASES = [
    ("unknown_robot_child", _wrap('<link name="base"/><lnik name="typo"/>'), "unknown_element"),
    ("unknown_link_child", _wrap('<link name="base"><intertial/></link>'), "unknown_element"),
    ("unknown_joint_child", _wrap(_joint("<mimics/>")), "unknown_element"),
    ("unknown_visual_child", _wrap('<link name="base"><visual><geometry><box size="1 1 1"/></geometry><colour/></visual></link>'), "unknown_element"),
    ("unknown_inertial_child", _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/><com/></inertial></link>'), "unknown_element"),
    ("dangling_material", _wrap('<link name="base"><visual><geometry><box size="1 1 1"/></geometry><material name="steel"/></visual></link>'), "dangling_material"),
    ("negative_mesh_scale", _wrap('<link name="base"><visual><geometry><mesh filename="m.stl" scale="1 -1 1"/></geometry></visual></link>'), "negative_mesh_scale"),
    ("unknown_mesh_extension", _wrap('<link name="base"><visual><geometry><mesh filename="m.step"/></geometry></visual></link>'), "unknown_mesh_extension"),
    ("package_mesh_unresolved", _wrap('<link name="base"><visual><geometry><mesh filename="package://pkg/m.stl"/></geometry></visual></link>'), "unresolved_mesh_uri"),
    ("remote_mesh_unresolved", _wrap('<link name="base"><visual><geometry><mesh filename="https://x.test/m.stl"/></geometry></visual></link>'), "unresolved_mesh_uri"),
    ("implicit_axis", _wrap(f'{TWO_LINKS}<joint name="j1" type="revolute"><parent link="base"/><child link="arm"/><limit lower="-1" upper="1" effort="1" velocity="1"/></joint>'), "implicit_joint_axis"),
    ("non_unit_axis", _wrap(_joint().replace('xyz="0 0 1"', 'xyz="0 0 2"')), "non_unit_joint_axis"),
    ("fixed_joint_with_limit", _wrap(f'{TWO_LINKS}<joint name="j1" type="fixed"><parent link="base"/><child link="arm"/><limit lower="0" upper="0"/></joint>'), "fixed_joint_limits"),
    (
        "continuous_position_limits",
        _wrap(f'{TWO_LINKS}<joint name="j1" type="continuous"><parent link="base"/><child link="arm"/><axis xyz="0 0 1"/><limit lower="-1" upper="1"/></joint>'),
        "continuous_position_limits",
    ),
    ("missing_effort", _wrap(_joint(limit='<limit lower="-1" upper="1" velocity="1"/>')), "missing_effort"),
    ("missing_velocity", _wrap(_joint(limit='<limit lower="-1" upper="1" effort="1"/>')), "missing_velocity"),
    (
        "inertia_triangle_inequality",
        _wrap('<link name="base"><inertial><mass value="1"/><inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="1"/></inertial></link>'),
        "inertia_triangle_inequality",
    ),
    (
        "joint_link_name_collision",
        _wrap(
            '<link name="base"/><link name="pivot"/>'
            '<joint name="pivot" type="fixed"><parent link="base"/><child link="pivot"/></joint>'
        ),
        "joint_link_name_collision",
    ),
    (
        "movable_link_without_inertial",
        _wrap(
            '<link name="base"/><link name="arm"><visual><geometry><box size="1 1 1"/></geometry></visual></link>'
            '<joint name="j1" type="revolute"><parent link="base"/><child link="arm"/><axis xyz="0 0 1"/>'
            '<limit lower="-1" upper="1" effort="1" velocity="1"/></joint>'
        ),
        "missing_inertial",
    ),
]


CLEAN_URDF = """\
<robot name="clean">
  <material name="steel"><color rgba="0.5 0.5 0.5 1"/></material>
  <link name="base">
    <inertial>
      <origin xyz="0 0 0.05"/>
      <mass value="1.0"/>
      <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>
    </inertial>
    <visual>
      <geometry><box size="0.1 0.1 0.1"/></geometry>
      <material name="steel"/>
    </visual>
    <collision>
      <geometry><box size="0.1 0.1 0.1"/></geometry>
    </collision>
  </link>
  <link name="arm">
    <inertial>
      <mass value="0.5"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/>
    </inertial>
    <visual>
      <geometry><cylinder radius="0.02" length="0.2"/></geometry>
    </visual>
  </link>
  <joint name="shoulder" type="revolute">
    <parent link="base"/>
    <child link="arm"/>
    <origin xyz="0 0 0.1"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.5" upper="1.5" effort="2" velocity="1"/>
  </joint>
  <gazebo reference="base"><selfCollide>false</selfCollide></gazebo>
  <transmission name="shoulder_trans"><type>t</type></transmission>
</robot>
"""


class UrdfFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-urdf-findings-")
        self.temp_root = Path(self._tempdir.name)
        (self.temp_root / "m.stl").write_text("solid m\nendsolid m\n", encoding="utf-8")
        (self.temp_root / "m.step").write_text("ISO-10303-21;\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _codes(self, xml_text: str) -> tuple[set[str], set[str]]:
        path = self.temp_root / "case.urdf"
        path.write_text(xml_text, encoding="utf-8")
        _, result = validate_urdf_file(path)
        return (
            {finding.code for finding in result.errors},
            {finding.code for finding in result.warnings},
        )

    def test_error_cases_emit_expected_codes(self) -> None:
        for name, xml_text, expected_code in ERROR_CASES:
            with self.subTest(case=name):
                error_codes, _ = self._codes(xml_text)
                self.assertIn(expected_code, error_codes, f"{name}: errors were {error_codes}")

    def test_warning_cases_emit_expected_codes_and_do_not_error(self) -> None:
        for name, xml_text, expected_code in WARNING_CASES:
            with self.subTest(case=name):
                error_codes, warning_codes = self._codes(xml_text)
                self.assertIn(expected_code, warning_codes, f"{name}: warnings were {warning_codes}")
                self.assertFalse(error_codes, f"{name}: unexpected errors {error_codes}")

    def test_clean_urdf_has_no_findings(self) -> None:
        path = self.temp_root / "clean.urdf"
        path.write_text(CLEAN_URDF, encoding="utf-8")
        source, result = validate_urdf_file(path)
        self.assertEqual([], result.all_findings(), [f.format() for f in result.all_findings()])
        self.assertIsNotNone(source)
        self.assertEqual("clean", source.robot_name)
        self.assertEqual(1.5, source.total_mass)
        self.assertEqual((-1.5, 1.5), (source.joints[0].lower, source.joints[0].upper))

    def test_multiple_errors_collected_in_one_pass(self) -> None:
        xml_text = _wrap(
            '<link name="base"/><link name="base"/>'
            '<link name="arm"><inertial><mass value="-1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>'
            '<joint name="j1" type="twisty"><parent link="ghost"/><child link="arm"/></joint>'
        )
        error_codes, _ = self._codes(xml_text)
        self.assertLessEqual(
            {"duplicate_link_name", "nonpositive_mass", "unsupported_joint_type", "missing_parent_link"},
            error_codes,
        )

    def test_namespaced_extensions_are_not_unknown_elements(self) -> None:
        xml_text = CLEAN_URDF.replace(
            "<gazebo reference=",
            '<tcad:extra xmlns:tcad="https://text-to-cad.dev/srdf"/><gazebo reference=',
        )
        _, warning_codes = self._codes(xml_text)
        self.assertNotIn("unknown_element", warning_codes)

    def test_continuous_joint_without_limits_is_clean(self) -> None:
        xml_text = _wrap(
            f'{TWO_LINKS}<joint name="j1" type="continuous">'
            '<parent link="base"/><child link="arm"/><axis xyz="0 0 1"/></joint>'
        )
        error_codes, warning_codes = self._codes(xml_text)
        self.assertFalse(error_codes)
        self.assertFalse(warning_codes)

    def test_unlimited_effort_convention_not_flagged(self) -> None:
        # effort="0" means "unlimited" to some consumers; only negatives are errors.
        xml_text = _wrap(_joint(limit='<limit lower="-1" upper="1" effort="0" velocity="0"/>'))
        error_codes, _ = self._codes(xml_text)
        self.assertFalse(error_codes)

    def test_eigenvalues_match_diagonal_for_diagonal_tensor(self) -> None:
        eigenvalues = sorted(
            symmetric_inertia_eigenvalues({"ixx": 3.0, "iyy": 1.0, "izz": 2.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0})
        )
        self.assertEqual([1.0, 2.0, 3.0], eigenvalues)

    def test_eigenvalues_handle_off_diagonal_terms(self) -> None:
        # [[2,1,0],[1,2,0],[0,0,3]] has eigenvalues 1, 3, 3.
        eigenvalues = sorted(
            symmetric_inertia_eigenvalues({"ixx": 2.0, "iyy": 2.0, "izz": 3.0, "ixy": 1.0, "ixz": 0.0, "iyz": 0.0})
        )
        for expected, actual in zip([1.0, 3.0, 3.0], eigenvalues, strict=True):
            self.assertAlmostEqual(expected, actual, places=6)


if __name__ == "__main__":
    unittest.main()
