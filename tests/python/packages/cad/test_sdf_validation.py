"""The SDF validator's matrix: the documents it accepts, the code each malformed one is refused
with, and the code each doubtful one is warned with."""

import tempfile
import unittest
from pathlib import Path

from cad.sdf_validation import validate_sdf_xml


def model(body: str, pose: str = "") -> str:
    return f'<sdf version="1.12"><model name="sample">{pose}<link name="base_link" />{body}</model></sdf>'


def link(body: str) -> str:
    return f'<sdf version="1.12"><model name="sample"><link name="base_link">{body}</link></model></sdf>'


def joint(kind: str, child: str = "arm_link", axis: str = "") -> str:
    return model(f'<link name="arm_link" /><joint name="j" type="{kind}"><parent>base_link</parent>'
                 f'<child>{child}</child>{axis}</joint>')


ACCEPTED = {
    "a minimal model": model(""),
    "a world alone": '<sdf version="1.12"><world name="w"><include><uri>model://sun</uri></include>'
                     '<light name="key" type="directional" /></world></sdf>',
    "an external mesh": link('<visual name="v"><geometry><mesh><uri>package://sample/meshes/base.dae</uri></mesh>'
                             '</geometry></visual>'),
    # A plugin's contents are its own: static metadata, never a contract the validator reads.
    "a plugin's own contents": joint("fixed").replace(
        "</model>", '<plugin name="controller" filename="gz-sim-custom-controller-system"><custom_parameter>opaque'
                    '</custom_parameter><nested_block invalid_for_validator="but_plugin_owned" /></plugin></model>'),
}

ERRORS = [
    ("invalid_numeric_vector", model("", pose="<pose>1 2 3</pose>")),
    ("zero_quaternion", model("", pose='<pose rotation_format="quat_xyzw">0 0 0 0 0 0 0</pose>')),
    ("frame_cycle", model('<frame name="a" attached_to="b" /><frame name="b" attached_to="a" />')),
    ("unknown_joint_type", joint("hinge")),
    ("invalid_joint_child", joint("fixed", child="world")),
    ("zero_axis", joint("revolute", axis="<axis><xyz>0 0 0</xyz></axis>")),
    ("invalid_dimension", link('<visual name="v"><geometry><box><size>1 0 1</size></box></geometry></visual>')),
    ("invalid_geometry_count", link('<visual name="v" />')),
    ("missing_mesh_file", link('<visual name="v"><geometry><mesh><uri>meshes/missing.stl</uri></mesh></geometry></visual>')),
    ("invalid_mass", link("<inertial><mass>0</mass></inertial>")),
    ("invalid_inertia_matrix", link("<inertial><mass>1</mass><inertia><ixx>1</ixx><iyy>1</iyy><izz>-1</izz>"
                                    "<ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>")),
    ("missing_sensor_type", link('<sensor name="camera" />')),
    ("missing_plugin_filename", model('<plugin name="controller" />')),
    ("missing_child_text", model("<include />")),
]

WARNINGS = [
    ("non_unit_quaternion", model("", pose='<pose rotation_format="quat_xyzw">0 0 0 0 0 0 2</pose>')),
    ("pose_missing_relative_to", link("<pose>1 0 0 0 0 0</pose>")),
    ("non_unit_axis", joint("revolute", axis="<axis><xyz>0 0 2</xyz></axis>")),
]


class SdfValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="tmp-sdf-validation-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def validate(self, body: str):
        return validate_sdf_xml(body, source_path=self.root / "generated.sdf", base_dir=self.root)

    def test_well_formed_documents_pass(self) -> None:
        for what, body in ACCEPTED.items():
            with self.subTest(what):
                self.assertEqual([], self.validate(body).errors)

    def test_each_malformed_document_is_refused_with_its_code(self) -> None:
        for code, body in ERRORS:
            with self.subTest(code):
                self.assertIn(code, {finding.code for finding in self.validate(body).errors})

    def test_each_doubtful_document_is_warned_with_its_code(self) -> None:
        for code, body in WARNINGS:
            with self.subTest(code):
                self.assertIn(code, {finding.code for finding in self.validate(body).warnings})


if __name__ == "__main__":
    unittest.main()
