"""``cad.mjcf._source``: an MJCF read as the viewer and the stills take it, the standard library alone.

Each case writes a tiny model into a fresh temporary folder: includes, the compiler's angle and Euler
sequence, every orientation form, frames, default classes, geom groups, ``fromto``, materials, mesh
assets, joints and their limits, chains of joints, couplings, keyframes, and what is refused by name.
"""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_sources

add_sources()

from cad.engine.mjcf_source import axis_angle_matrix, euler_matrix  # noqa: E402
from cad.mjcf._source import articulate, is_mjcf_file, read_mjcf  # noqa: E402

RX90 = [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]
RY90 = [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]
RZ90 = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]


def _stl(path: Path) -> Path:
    """A one-triangle binary STL: 80 bytes of header, a uint32 count, 50 bytes per triangle."""
    triangle = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * 80 + struct.pack("<I", 1) + triangle)
    return path


def _rotation(matrix: list[list[float]]) -> list[list[float]]:
    return [row[:3] for row in matrix[:3]]


def _position(matrix: list[list[float]]) -> list[float]:
    return [matrix[row][3] for row in range(3)]


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, body: str, *, name: str = "robot.xml", head: str = ""):
        return read_mjcf(self.write(name, f'<mujoco model="m">{head}{body}</mujoco>'))

    def model(self, body: str, **kwargs):
        model, findings = self.read(body, **kwargs)
        self.assertEqual([], [finding.format() for finding in findings.errors])
        self.assertIsNotNone(model)
        return model, findings

    def codes(self, findings, severity: str = "errors") -> list[str]:
        return [finding.code for finding in getattr(findings, severity)]

    def assertMatrix(self, expected, actual, places: int = 6) -> None:  # noqa: N802 - unittest's spelling
        for row_expected, row_actual in zip(expected, actual, strict=True):
            for value_expected, value_actual in zip(row_expected, row_actual, strict=True):
                self.assertAlmostEqual(value_expected, value_actual, places=places)


class Includes(_Case):
    def test_an_include_is_spliced_relative_to_the_main_file(self) -> None:
        # parts/arm.xml includes parts/hand.xml by the MAIN file's folder, not its own.
        self.write("parts/arm.xml", '<mujoco><body name="arm"><geom size="0.1"/></body>'
                                    '<include file="parts/hand.xml"/></mujoco>')
        self.write("parts/hand.xml", '<mujoco><body name="hand"><geom size="0.1"/></body></mujoco>')
        model, _ = self.model('<worldbody><include file="parts/arm.xml"/></worldbody>')
        self.assertEqual(["world", "arm", "hand"], list(model.bodies))
        self.assertEqual("world", model.bodies["arm"].parent)
        self.assertEqual(["robot.xml", "arm.xml", "hand.xml"], [path.name for path in model.files])

    def test_an_include_given_twice_is_an_error(self) -> None:
        self.write("a.xml", '<mujoco><body name="a"/></mujoco>')
        model, findings = self.read('<worldbody><include file="a.xml"/><include file="a.xml"/></worldbody>')
        self.assertIsNone(model)
        self.assertIn("include_repeated", self.codes(findings))

    def test_an_include_that_is_not_there_is_an_error(self) -> None:
        model, findings = self.read('<worldbody><include file="missing.xml"/></worldbody>')
        self.assertIsNone(model)
        self.assertEqual(["include_not_found"], self.codes(findings))


class CompilerAngles(_Case):
    def test_degrees_unless_the_compiler_says_radians(self) -> None:
        body = '<worldbody><body name="b" euler="0 0 {}"><joint name="j" range="-{} {}"/></body></worldbody>'
        degrees, _ = self.model(body.format(90, 45, 45))
        radians, _ = self.model(body.format(math.pi / 2, math.pi / 4, math.pi / 4),
                                head='<compiler angle="radian"/>')
        for model in (degrees, radians):
            self.assertMatrix(RZ90, _rotation(model.bodies["b"].rest))
            low, high = model.joints[0].range
            self.assertAlmostEqual(-math.pi / 4, low)
            self.assertAlmostEqual(math.pi / 4, high)

    def test_an_unknown_angle_unit_is_an_error(self) -> None:
        _, findings = self.read('<worldbody/>', head='<compiler angle="gradian"/>')
        self.assertIn("bad_compiler_angle", self.codes(findings))


class EulerSequences(_Case):
    def test_lowercase_turns_about_the_moving_axes_uppercase_about_the_fixed(self) -> None:
        quarter = [math.pi / 2, math.pi / 2, 0.0]
        # Intrinsic x then y: Rx(90) Ry(90). Extrinsic X then Y: Ry(90) Rx(90).
        self.assertMatrix([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], euler_matrix(quarter, "xyz"))
        self.assertMatrix([[0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [-1.0, 0.0, 0.0]], euler_matrix(quarter, "XYZ"))
        self.assertMatrix(RX90, euler_matrix([math.pi / 2, 0.0, 0.0], "xyz"))
        with self.assertRaises(ValueError):
            euler_matrix([0.0, 0.0, 0.0], "xyw")

    def test_the_compilers_sequence_is_the_files(self) -> None:
        body = '<worldbody><body name="b" euler="90 90 0"/></worldbody>'
        intrinsic, _ = self.model(body)
        extrinsic, _ = self.model(body, head='<compiler eulerseq="XYZ"/>')
        self.assertMatrix(euler_matrix([math.pi / 2, math.pi / 2, 0.0], "xyz"), _rotation(intrinsic.bodies["b"].rest))
        self.assertMatrix(euler_matrix([math.pi / 2, math.pi / 2, 0.0], "XYZ"), _rotation(extrinsic.bodies["b"].rest))
        _, findings = self.read('<worldbody/>', head='<compiler eulerseq="xy"/>')
        self.assertIn("bad_compiler_eulerseq", self.codes(findings))


class Orientations(_Case):
    def test_each_form_of_a_quarter_turn_about_z(self) -> None:
        for form in ('quat="0.7071068 0 0 0.7071068"', 'quat="2 0 0 2"', 'axisangle="0 0 1 90"',
                     'xyaxes="0 1 0 -1 0 0"', 'euler="0 0 90"'):
            with self.subTest(form=form):
                model, _ = self.model(f'<worldbody><body name="b" {form}/></worldbody>')
                self.assertMatrix(RZ90, _rotation(model.bodies["b"].rest))

    def test_zaxis_is_the_least_turn_taking_z_there(self) -> None:
        model, _ = self.model('<worldbody><body name="b" zaxis="1 0 0"/></worldbody>')
        self.assertMatrix(RY90, _rotation(model.bodies["b"].rest))
        self.assertMatrix(axis_angle_matrix([0, 1, 0], math.pi / 2), RY90)

    def test_two_orientations_and_a_wrong_count_are_errors(self) -> None:
        _, findings = self.read('<worldbody><body name="b" quat="1 0 0 0" euler="0 0 0"/></worldbody>')
        self.assertIn("several_orientations", self.codes(findings))
        _, findings = self.read('<worldbody><body name="b" quat="1 0 0"/></worldbody>')
        self.assertIn("bad_number_count", self.codes(findings))


class Frames(_Case):
    def test_a_frame_places_what_it_holds(self) -> None:
        model, _ = self.model('<worldbody><frame pos="1 0 0" euler="0 0 90"><body name="b" pos="1 0 0">'
                              '<frame pos="0 0 1"><geom name="g" size="0.1"/></frame></body></frame></worldbody>')
        body = model.bodies["b"]
        self.assertEqual("world", body.parent)
        for expected, actual in zip([1.0, 1.0, 0.0], _position(body.rest), strict=True):
            self.assertAlmostEqual(expected, actual)
        self.assertMatrix(RZ90, _rotation(body.rest))
        self.assertEqual([0.0, 0.0, 1.0], _position(body.geoms[0].local))


class Defaults(_Case):
    HEAD = ('<default><geom rgba="1 0 0 1"/><joint range="-10 10"/>'
            '<default class="blue"><geom rgba="0 0 1 1"/></default>'
            '<default class="slider"><joint type="slide" range="0 0.2"/></default></default>')

    def test_classes_inherit_and_an_elements_class_overrides_the_childclass(self) -> None:
        model, _ = self.model(
            '<worldbody><body name="a"><joint name="ja"/><geom name="plain" size="0.1"/></body>'
            '<body name="b" childclass="blue"><geom name="child" size="0.1"/><geom name="own" class="main" size="0.1"/>'
            '<body name="c"><geom name="inherited" size="0.1"/><joint name="jc" class="slider"/></body></body>'
            '</worldbody>', head=self.HEAD)
        colours = {geom.name: geom.rgba for geom in model.geoms}
        self.assertEqual({"plain": (1.0, 0.0, 0.0, 1.0), "child": (0.0, 0.0, 1.0, 1.0), "own": (1.0, 0.0, 0.0, 1.0),
                          "inherited": (0.0, 0.0, 1.0, 1.0)}, colours)
        joints = {joint.name: joint for joint in model.joints}
        self.assertEqual("hinge", joints["ja"].type)
        self.assertAlmostEqual(math.radians(10), joints["ja"].range[1])
        self.assertEqual(("slide", (0.0, 0.2)), (joints["jc"].type, joints["jc"].range))

    def test_an_unknown_class_is_an_error(self) -> None:
        _, findings = self.read('<worldbody><body name="a"><geom class="nope" size="0.1"/></body></worldbody>')
        self.assertIn("unknown_default_class", self.codes(findings))


class Geoms(_Case):
    def test_groups_three_and_up_are_not_drawn(self) -> None:
        model, _ = self.model('<worldbody><body name="b"><geom name="seen" size="0.1" group="2"/>'
                              '<geom name="collision" size="0.1" group="3"/></body></worldbody>')
        drawn = {geom.name: geom.drawn for geom in model.geoms}
        self.assertEqual({"seen": True, "collision": False}, drawn)
        self.assertEqual(["seen"], [visual.label for visual in articulate(model).visuals["b"]])

    def test_fromto_places_a_capsule_on_its_segment(self) -> None:
        model, _ = self.model('<worldbody><body name="b"><geom name="c" type="capsule" size="0.05" '
                              'fromto="0 0 0 0 0 1"/></body></worldbody>')
        geom = model.geoms[0]
        self.assertEqual([0.05, 0.5], geom.size)
        self.assertEqual([0.0, 0.0, 0.5], _position(geom.local))
        self.assertEqual(("capsule", {"radius": 0.05, "length": 1.0}), geom.visual())
        _, findings = self.read('<worldbody><body name="b"><geom type="capsule" size="0.05" fromto="0 0 1 0 0 1"/>'
                                '</body></worldbody>')
        self.assertIn("fromto_degenerate", self.codes(findings))

    def test_a_material_colours_a_geom_unless_the_geom_gives_its_own_rgba(self) -> None:
        model, _ = self.model(
            '<asset><material name="red" rgba="1 0 0 1"/></asset>'
            '<worldbody><body name="b"><geom name="material" material="red" size="0.1"/>'
            '<geom name="both" material="red" rgba="0 1 0 1" size="0.1"/>'
            '<geom name="defaulted" class="green" material="red" size="0.1"/>'
            '<geom name="none" size="0.1"/></body></worldbody>',
            head='<default><default class="green"><geom rgba="0 1 0 1"/></default></default>')
        colours = {geom.name: geom.rgba for geom in model.geoms}
        self.assertEqual({"material": (1.0, 0.0, 0.0, 1.0), "both": (0.0, 1.0, 0.0, 1.0),
                          "defaulted": (1.0, 0.0, 0.0, 1.0), "none": (0.5, 0.5, 0.5, 1.0)}, colours)
        _, findings = self.read('<worldbody><body name="b"><geom material="nope" size="0.1"/></body></worldbody>')
        self.assertIn("material_unknown", self.codes(findings))


class MeshAssets(_Case):
    def test_meshdir_and_the_name_from_the_files_stem(self) -> None:
        part = _stl(self.folder / "meshes" / "part.stl")
        model, _ = self.model('<asset><mesh file="part.stl" scale="2 2 2"/></asset>'
                              '<worldbody><body name="b"><geom type="mesh" mesh="part"/></body></worldbody>',
                              head='<compiler meshdir="meshes"/>')
        self.assertEqual(part.resolve(), model.meshes["part"].file)
        self.assertEqual([part.resolve()], model.mesh_files())
        visual = articulate(model).visuals["b"][0]
        self.assertEqual(("file", part.resolve(), (2.0, 2.0, 2.0)), visual.shape)

    def test_strippath_keeps_the_files_name_alone(self) -> None:
        part = _stl(self.folder / "meshes" / "part.stl")
        model, _ = self.model('<asset><mesh name="p" file="elsewhere/deep/part.stl"/></asset>'
                              '<worldbody><body name="b"><geom type="mesh" mesh="p"/></body></worldbody>',
                              head='<compiler meshdir="meshes" strippath="true"/>')
        self.assertEqual(part.resolve(), model.meshes["p"].file)

    def test_a_missing_file_and_an_unknown_format_are_errors_an_msh_a_warning(self) -> None:
        _, findings = self.read('<asset><mesh file="gone.stl"/></asset><worldbody/>')
        self.assertEqual(["mesh_file_not_found"], self.codes(findings))
        self.write("part.ply", "ply\n")
        _, findings = self.read('<asset><mesh file="part.ply"/></asset><worldbody/>')
        self.assertEqual(["mesh_format_unknown"], self.codes(findings))
        (self.folder / "part.msh").write_bytes(b"\0" * 16)
        model, findings = self.model('<asset><mesh file="part.msh"/></asset>'
                                     '<worldbody><body name="b"><geom type="mesh" mesh="part"/></body></worldbody>')
        self.assertIn("mesh_not_drawn", self.codes(findings, "warnings"))
        self.assertEqual([], articulate(model).visuals["b"])

    def test_a_geom_naming_no_asset_is_an_error(self) -> None:
        _, findings = self.read('<worldbody><body name="b"><geom type="mesh" mesh="nope"/></body></worldbody>')
        self.assertEqual(["mesh_asset_unknown"], self.codes(findings))


class Joints(_Case):
    def joints(self, body: str, **kwargs):
        model, findings = self.model(f'<worldbody>{body}</worldbody>', **kwargs)
        return {joint.name: joint for joint in articulate(model).joints}, findings

    def test_each_kind_as_the_viewer_poses_it(self) -> None:
        joints, findings = self.joints(
            '<body name="a"><joint name="hinge" range="-90 90"/><geom size="0.1"/></body>'
            '<body name="b"><joint name="spin" axis="1 0 0"/><geom size="0.1"/></body>'
            '<body name="c"><joint name="slide" type="slide" range="0 0.5"/><geom size="0.1"/></body>'
            '<body name="d"><joint name="ball" type="ball"/><geom size="0.1"/></body>'
            '<body name="e"><freejoint name="free"/><geom size="0.1"/></body>'
            '<body name="f"><geom size="0.1"/></body>')
        kinds = {name: joint.type for name, joint in joints.items()}
        self.assertEqual({"hinge": "revolute", "spin": "continuous", "slide": "prismatic", "ball": "fixed",
                          "free": "fixed", "f": "fixed"}, kinds)
        self.assertAlmostEqual(-math.pi / 2, joints["hinge"].lower)
        self.assertAlmostEqual(math.pi / 2, joints["hinge"].upper)
        self.assertEqual((None, None), (joints["spin"].lower, joints["spin"].upper))
        self.assertEqual([1.0, 0.0, 0.0], joints["spin"].axis)
        self.assertEqual((0.0, 0.5), (joints["slide"].lower, joints["slide"].upper))
        # A ball and a free joint are said (a warning or an info), never passed over in silence.
        said = [finding.path for finding in findings.all_findings() if finding.code == "joint_not_posable"]
        self.assertEqual(2, len(said))
        self.assertTrue(any("'d'" in where for where in said) and any("'e'" in where for where in said), said)

    def test_ref_is_the_zero_a_range_is_around(self) -> None:
        joints, _ = self.joints('<body name="a"><joint name="j" range="-90 90" ref="30"/></body>')
        self.assertAlmostEqual(math.radians(-120), joints["j"].lower)
        self.assertAlmostEqual(math.radians(60), joints["j"].upper)

    def test_limited_and_autolimits(self) -> None:
        joints, _ = self.joints('<body name="a"><joint name="off" limited="false" range="-1 1"/></body>'
                                '<body name="b"><joint name="on" limited="true" range="-1 1"/></body>')
        self.assertEqual("continuous", joints["off"].type)
        self.assertEqual("revolute", joints["on"].type)
        joints, findings = self.joints('<body name="a"><joint name="auto" range="-1 1"/></body>'
                                       '<body name="b"><joint name="on" limited="true" range="-1 1"/></body>',
                                       head='<compiler autolimits="false"/>')
        self.assertEqual("continuous", joints["auto"].type)
        self.assertEqual("revolute", joints["on"].type)
        self.assertIn("range_unlimited", self.codes(findings, "warnings"))
        _, findings = self.read('<worldbody><body name="a"><joint limited="true"/></body></worldbody>')
        self.assertIn("limited_without_range", self.codes(findings))
        _, findings = self.read('<worldbody><body name="a"><joint range="10 -10"/></body></worldbody>')
        self.assertIn("range_inverted", self.codes(findings))
        _, findings = self.read('<worldbody><body name="a"><joint axis="0 0 0"/></body></worldbody>')
        self.assertIn("axis_zero", self.codes(findings))

    def test_a_body_with_several_joints_is_a_chain_of_links(self) -> None:
        model, _ = self.model('<worldbody><body name="b" pos="0 0 1"><joint name="j1" axis="1 0 0"/>'
                              '<joint name="j2" axis="0 1 0"/><geom size="0.1"/></body></worldbody>')
        articulation = articulate(model)
        chain = [(joint.name, joint.parent, joint.child) for joint in articulation.joints]
        self.assertEqual([("j1", "world", "b/j1"), ("j2", "b/j1", "b")], chain)
        self.assertEqual([0.0, 0.0, 1.0], _position(articulation.links["b/j1"]))
        self.assertEqual([], articulation.visuals["b/j1"])
        self.assertEqual(1, len(articulation.visuals["b"]))


class Equalities(_Case):
    BODIES = ('<worldbody><body name="a"><joint name="leader" range="-90 90"/></body>'
              '<body name="b"><joint name="follower" range="-90 90"/></body></worldbody>')

    def test_a_linear_polycoef_is_a_mimic(self) -> None:
        model, _ = self.model(self.BODIES + '<equality><joint joint1="follower" joint2="leader" '
                                            'polycoef="0.1 2 0 0 0"/></equality>')
        self.assertEqual([("follower", "leader", 2.0, 0.1)], model.couplings)
        joints = {joint.name: joint for joint in articulate(model).joints}
        self.assertEqual(("leader", 2.0, 0.1), joints["follower"].mimic)

    def test_a_polynomial_is_an_info_and_an_unknown_joint_an_error(self) -> None:
        model, findings = self.model(self.BODIES + '<equality><joint joint1="follower" joint2="leader" '
                                                   'polycoef="0 1 1 0 0"/></equality>')
        self.assertEqual([], model.couplings)
        self.assertIn("equality_not_linear", self.codes(findings, "infos"))
        _, findings = self.read(self.BODIES + '<equality><joint joint1="follower" joint2="nope"/></equality>')
        self.assertIn("equality_unknown_joint", self.codes(findings))


class Keyframes(_Case):
    BODIES = ('<worldbody><body name="base"><freejoint/><body name="a"><joint name="turn" ref="10"/>'
              '<body name="b"><joint name="push" type="slide"/></body></body></body></worldbody>')

    def test_a_key_is_a_pose_in_degrees_and_metres_around_ref(self) -> None:
        model, _ = self.model(self.BODIES + '<keyframe><key name="up" qpos="0 0 0 1 0 0 0 0.5 0.25"/></keyframe>')
        self.assertEqual({"up": {"turn": 0.5, "push": 0.25}}, model.keyframes)
        pose = articulate(model).poses["up"]
        self.assertAlmostEqual(math.degrees(0.5) - 10.0, pose["turn"])
        self.assertAlmostEqual(0.25, pose["push"])

    def test_a_key_of_the_wrong_length_is_a_warning_and_no_pose(self) -> None:
        model, findings = self.model(self.BODIES + '<keyframe><key name="short" qpos="0.5 0.25"/></keyframe>')
        self.assertEqual({}, model.keyframes)
        self.assertIn("keyframe_length", self.codes(findings, "warnings"))


class Refusals(_Case):
    def test_duplicate_names_are_errors(self) -> None:
        for body, code in (('<body name="a"/><body name="a"/>', "duplicate_body_name"),
                           ('<body name="a"><joint name="j"/></body><body name="b"><joint name="j"/></body>',
                            "duplicate_joint_name"),
                           ('<body name="a"><geom name="g" size="0.1"/><geom name="g" size="0.1"/></body>',
                            "duplicate_geom_name")):
            with self.subTest(code=code):
                model, findings = self.read(f"<worldbody>{body}</worldbody>")
                self.assertIsNone(model)
                self.assertIn(code, self.codes(findings))

    def test_a_root_that_is_not_mujoco_and_no_worldbody(self) -> None:
        model, findings = read_mjcf(self.write("robot.xml", '<robot name="r"><link name="a"/></robot>'))
        self.assertIsNone(model)
        self.assertEqual(["not_mjcf"], self.codes(findings))
        model, findings = self.read("")
        self.assertIsNone(model)
        self.assertEqual(["missing_worldbody"], self.codes(findings))


class IsMjcfFile(_Case):
    def test_an_xml_by_its_root_and_an_mjcf_by_its_suffix(self) -> None:
        mujoco = self.write("scene.xml", '<?xml version="1.0"?>\n<!-- a scene -->\n<mujoco model="s"/>')
        other = self.write("robot.xml", '<?xml version="1.0"?><robot name="r"/>')
        self.assertTrue(is_mjcf_file(mujoco))
        self.assertFalse(is_mjcf_file(other))
        self.assertFalse(is_mjcf_file(self.folder / "missing.xml"))
        self.assertTrue(is_mjcf_file(self.folder / "anything.mjcf"))
        self.assertFalse(is_mjcf_file(self.write("robot.urdf", "<mujoco/>")))


if __name__ == "__main__":
    unittest.main()
