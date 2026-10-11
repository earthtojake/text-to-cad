"""A bending tube as a glTF skin (`tube_skin`): where its joints stand, how its
vertices bind to them, and that skinning them as a glTF player does puts the wall
where the authored centerline says -- pinned on shapes whose answer is known in
closed form: a tube at rest, stretched, twisted, and curled into a quarter circle.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from tests.python.support.paths import add_repo_path
from tests.python.support.tube_skins import view_skin

add_repo_path("packages/cadgen/src")

from cadgen._internal import tube_deformation as td  # noqa: E402
from cadgen._internal import tube_skin, tube_skin_payload  # noqa: E402

NORMAL = [0.0, 0.0, 1.0]


def _line(length: float) -> dict:
    return {"normal": NORMAL, "segments": [{"kind": "line", "start": [0.0, 0.0, 0.0], "end": [length, 0.0, 0.0]}]}


def _quarter_circle(radius: float) -> dict:
    """A quarter circle from the origin, leaving along +X and turning toward +Y."""
    return {"normal": NORMAL, "segments": [{"kind": "arc", "center": [0.0, radius, 0.0], "axis": [0.0, 0.0, 1.0],
                                             "start": [0.0, 0.0, 0.0], "sweepDeg": 90.0}]}


def _tube(length: float, radius: float, rings: int = 41, around: int = 16) -> td.RestMesh:
    """A tube of ``radius`` along +X from the origin: rings of ``around`` points."""
    xs = np.linspace(0.0, length, rings)
    angles = np.linspace(0.0, 2 * math.pi, around, endpoint=False)
    y, z = np.cos(angles), np.sin(angles)
    positions = np.array([[x, radius * a, radius * b] for x in xs for a, b in zip(y, z)], dtype=np.float32)
    normals = np.array([[0.0, a, b] for _ in xs for a, b in zip(y, z)], dtype=np.float32)
    indices = []
    for ring in range(rings - 1):
        for k in range(around):
            a0, a1 = ring * around + k, ring * around + (k + 1) % around
            indices += [a0, a0 + around, a1, a1, a0 + around, a1 + around]
    return td.RestMesh(positions, normals, np.array(indices, dtype=np.uint32))


def _rotate(quaternions: np.ndarray, vector) -> np.ndarray:
    """Each unit quaternion (xyzw) applied to ``vector``."""
    q, w = quaternions[:, :3], quaternions[:, 3:4]
    v = np.broadcast_to(np.asarray(vector, dtype=np.float64), q.shape)
    t = 2.0 * np.cross(q, v)
    return v + w * t + np.cross(q, t)


class Posed:
    """A tube of ``length`` at rest along +X, bound with joints ``spacing`` mm apart,
    and skinned to ``key``."""

    def __init__(self, length: float, radius: float, key: dict | None, spacing: float = 1.0):
        rest_spec = _line(length)
        self.rest = tube_skin.compile_rest(rest_spec)
        self.fractions = tube_skin.joint_fractions(self.rest, spacing)
        self.tube = tube_skin.bind(_tube(length, radius), self.rest, spacing, self.fractions)
        self.rest_joints = tube_skin.joints_on(self.rest, self.fractions)
        self.joints = tube_skin.key_joints(key, rest_spec, self.rest, self.fractions)
        self.positions = tube_skin.skin(self.joints, self.rest_joints, self.tube)


class TheJoints(unittest.TestCase):
    def test_joints_stand_at_both_ends_and_never_further_apart_than_asked(self):
        rest = tube_skin.compile_rest(_line(10.0))
        fractions = tube_skin.joint_fractions(rest, 3.0)
        self.assertEqual([0.0, 0.25, 0.5, 0.75, 1.0], fractions.tolist())
        # Past the ceiling they spread out evenly rather than fail.
        self.assertEqual(tube_skin.MAX_JOINTS, len(tube_skin.joint_fractions(tube_skin.compile_rest(_line(10_000.0)), 1.0)))

    def test_a_joint_stands_on_the_centerline_with_its_x_axis_along_the_tangent(self):
        radius = 10.0
        path = tube_skin.compile_rest(_quarter_circle(radius))
        fractions = np.linspace(0.0, 1.0, 7)
        joints = tube_skin.joints_on(path, fractions)
        angle = fractions * math.pi / 2
        np.testing.assert_allclose(np.column_stack([radius * np.sin(angle), radius * (1 - np.cos(angle)), 0 * angle]),
                                   joints.translations, atol=1e-9)
        np.testing.assert_allclose(np.column_stack([np.cos(angle), np.sin(angle), 0 * angle]),
                                   _rotate(joints.rotations, [1.0, 0.0, 0.0]), atol=1e-9)
        np.testing.assert_allclose(1.0, np.linalg.norm(joints.rotations, axis=1), atol=1e-12)

    def test_each_inverse_bind_undoes_its_rest_frame(self):
        joints = tube_skin.joints_on(tube_skin.compile_rest(_quarter_circle(10.0)), np.linspace(0.0, 1.0, 5))
        inverse = np.transpose(tube_skin.inverse_binds(joints), (0, 2, 1))  # stored column-major
        for k, origin in enumerate(joints.translations):
            np.testing.assert_allclose([0.0, 0.0, 0.0, 1.0], inverse[k] @ [*origin, 1.0], atol=1e-9)
            np.testing.assert_allclose([1.0, 0.0, 0.0], inverse[k, :3, :3] @ _rotate(joints.rotations[k:k + 1], [1, 0, 0])[0],
                                       atol=1e-9)

    def test_a_player_turns_each_joint_the_short_way_between_keys(self):
        quarter = [0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)]
        a = tube_skin.Joints(np.zeros((1, 3)), np.array([[0.0, 0.0, 0.0, 1.0]]))
        b = tube_skin.Joints(np.ones((1, 3)), -np.array([quarter]))  # the same turn, written the long way round
        a, b = tube_skin.continuous([a, b])
        self.assertGreater(float(np.sum(a.rotations * b.rotations)), 0.0)
        half = tube_skin.between(a, b, 0.5)
        np.testing.assert_allclose([[0.5, 0.5, 0.5]], half.translations)
        np.testing.assert_allclose([[0.0, 0.0, math.sin(math.pi / 16), math.cos(math.pi / 16)]], half.rotations, atol=1e-12)
        self.assertEqual((0.0, 0.0), tube_skin.joint_error(half, half))
        moved, turned = tube_skin.joint_error(a, b)
        self.assertAlmostEqual(math.sqrt(3.0), moved)
        self.assertAlmostEqual(45.0, turned, places=9)


class TheBinding(unittest.TestCase):
    def test_every_vertex_rides_the_two_joints_either_side_of_it(self):
        posed = Posed(10.0, 1.0, None)
        tube = posed.tube
        self.assertEqual(11, len(posed.fractions))
        np.testing.assert_array_equal(tube.joints[:, 0] + 1, tube.joints[:, 1])
        np.testing.assert_array_equal(0, tube.joints[:, 2:])
        np.testing.assert_allclose(1.0, tube.weights.sum(axis=1), atol=1e-6)
        # Weighted by where it falls between them: a vertex at x mm sits x mm along a
        # tube jointed every millimetre.
        along = tube.joints[:, 0] + tube.weights[:, 1]
        np.testing.assert_allclose(tube.positions[:, 0], along, atol=1e-5)
        # Its braid coordinates: rest arc length in mm, and its offset across the tube
        # along the frame's normal (+Z) and binormal (tangent x normal, -Y).
        x, y, z = tube.positions.T
        np.testing.assert_allclose(np.column_stack([x, z, -y]), tube.material, atol=1e-5)

    def test_at_rest_the_skin_is_the_mesh(self):
        posed = Posed(10.0, 1.0, None)
        np.testing.assert_allclose(posed.tube.positions, posed.positions, atol=1e-5)


class ThePose(unittest.TestCase):
    def test_a_lengthened_tube_stretches_evenly(self):
        posed = Posed(10.0, 1.0, {"path": _line(20.0)})
        rest = posed.tube.positions
        np.testing.assert_allclose(2.0 * rest[:, 0], posed.positions[:, 0], atol=1e-5)
        np.testing.assert_allclose(rest[:, 1:], posed.positions[:, 1:], atol=1e-5)

    def test_a_twist_turns_every_cross_section_about_the_tangent(self):
        posed = Posed(10.0, 1.0, {"path": _line(10.0), "twistDeg": 90.0})
        rest = posed.tube.positions
        # A quarter turn about +X takes (y, z) to (-z, y) and leaves x alone.
        np.testing.assert_allclose(rest[:, 0], posed.positions[:, 0], atol=1e-5)
        np.testing.assert_allclose(np.column_stack([-rest[:, 2], rest[:, 1]]), posed.positions[:, 1:], atol=1e-5)

    def test_a_tube_curled_into_a_quarter_circle_keeps_its_wall_on_the_arc(self):
        length, radius = 20.0, 0.8
        bend = length / (math.pi / 2)
        posed = Posed(length, radius, {"path": _quarter_circle(bend)})
        p = posed.positions
        # Every vertex stays the tube's radius from the arc, to within what two joints
        # a millimetre apart can blend: a hundredth of a millimetre on this bend.
        from_axis = np.hypot(np.hypot(p[:, 0], p[:, 1] - bend) - bend, p[:, 2])
        self.assertLessEqual(float(np.max(np.abs(from_axis - radius))), 0.02)
        # And as far along it as it was along the tube.
        along = np.arctan2(p[:, 0], bend - p[:, 1]) * bend
        np.testing.assert_allclose(posed.tube.positions[:, 0], along, atol=0.02)
        far = p[np.isclose(posed.tube.positions[:, 0], length)]
        np.testing.assert_allclose([bend, bend], far[:, :2].mean(axis=0), atol=1e-5)


class Component:
    """A stored mesh's arrays (``store.meshes.decode_payload``): a tube along +X with
    one straight edge polyline down its side, as one edge table row."""

    def __init__(self, length: float, radius: float):
        mesh = _tube(length, radius)
        self.positions, self.normals, self.indices = mesh.positions, mesh.normals, mesh.indices
        self.edge_points = np.array([[0.0, 0.0, radius], [length, 0.0, radius]], dtype=np.float32)
        self.edges = np.array([[7, 0, 2, 1]], dtype=np.uint32)  # ordinal 7, two points, class "feature"


class TheViewBinding(unittest.TestCase):
    def test_a_reflected_occurrence_binds_in_its_components_frame_and_winding(self):
        length = 10.0
        rest = tube_skin.compile_rest(_line(length))
        fractions = tube_skin.joint_fractions(rest, 1.0)
        # Mirrored in x and moved 10 mm: the rest centerline runs over the placed tube.
        placement = [-1.0, 0, 0, 10.0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        component = Component(length, 1.0)
        bound = tube_skin.bind_occurrence(component, placement, rest, 1.0, fractions)
        # Every refined vertex is a point of the component's own tube, in its frame.
        np.testing.assert_allclose(1.0, np.hypot(bound.positions[:, 1], bound.positions[:, 2]), atol=1e-5)
        # The rest arc length is measured in the document: the component's x = 0 is 10 mm along.
        np.testing.assert_allclose(10.0 - bound.positions[:, 0], bound.along, atol=1e-5)
        # Each refined triangle keeps the winding of the component triangle it refines.
        source = component.indices.reshape(-1, 3)[bound.source_triangles]
        a, b, c = (component.positions[source[:, k]].astype(np.float64) for k in range(3))
        p, q, r = (bound.positions[bound.indices.reshape(-1, 3)[:, k]].astype(np.float64) for k in range(3))
        self.assertTrue(np.all(np.einsum("ij,ij->i", np.cross(b - a, c - a), np.cross(q - p, r - p)) > 0))

    def test_an_edge_is_split_where_it_crosses_a_band(self):
        rest = tube_skin.compile_rest(_line(10.0))
        bound = tube_skin.bind_occurrence(Component(10.0, 1.0), None, rest, 2.5, tube_skin.joint_fractions(rest, 2.5))
        self.assertEqual(4, len(bound.edge_ordinals))
        self.assertEqual({7}, set(bound.edge_ordinals.tolist()))
        self.assertEqual({1}, set(bound.edge_classes.tolist()))
        np.testing.assert_allclose([0, 2.5, 2.5, 5, 5, 7.5, 7.5, 10], bound.edge_positions[:, 0], atol=1e-6)
        np.testing.assert_allclose(bound.edge_positions[:, 0] / 2.5, bound.edge_along, atol=1e-6)


class ThePayload(unittest.TestCase):
    def test_a_view_skinning_the_payload_curls_the_tube_where_the_clip_does(self):
        length, radius = 20.0, 0.8
        bend = length / (math.pi / 2)
        moved = [1.0, 0, 0, 5.0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]  # the component starts at x = -5
        component = Component(length, radius)
        component.positions = component.positions - np.float32([5.0, 0.0, 0.0])
        component.edge_points = component.edge_points - np.float32([5.0, 0.0, 0.0])
        descriptor = {"occurrences": [{"id": "o1.2", "component": "c1", "transform": moved}]}
        track = {"targets": ["o1.2"], "times": [0.0, 1.0], "rest": _line(length), "maxSegmentLength": 1.0,
                 "tube": [None, {"path": _quarter_circle(bend), "twistDeg": 0.0}]}
        animation = {"clips": [{"id": "curl", "label": "Curl", "duration": 1.0, "loop": False, "tracks": [
            {"targets": ["o1.1"], "times": [0.0], "opacity": [0.5]}, track]}]}
        skins = tube_skin_payload.decode_tube_skins(
            tube_skin_payload.build_tube_skins(descriptor, {"c1": component}, animation))
        self.assertEqual(1, skins["schemaVersion"])
        (binding,) = skins["bindings"]
        (entry,) = skins["tracks"]
        self.assertEqual(("curl", 1, [0], "o1.2", 21), (entry["clip"], entry["track"], entry["bindings"],
                                                         binding["occurrence"], binding["joints"]))
        rest = binding["rest"].reshape(-1, 7)
        keys = entry["keys"].reshape(2, -1, 7)
        placement = np.asarray(moved, dtype=np.float64).reshape(4, 4)
        local = binding["positions"].reshape(-1, 3).astype(np.float64)
        # The first key is the rest: the view draws the component where it always does.
        np.testing.assert_allclose(local @ placement[:3, :3].T + placement[:3, 3],
                                   view_skin(local, binding["along"], rest, keys[0], placement), atol=1e-4)
        # The last curls it: every wall vertex and every edge point stays on the tube.
        for points, along in ((local, binding["along"]),
                              (binding["edgePositions"].reshape(-1, 3).astype(np.float64), binding["edgeAlong"])):
            p = view_skin(points, along, rest, keys[1], placement)
            from_axis = np.hypot(np.hypot(p[:, 0], p[:, 1] - bend) - bend, p[:, 2])
            self.assertLessEqual(float(np.max(np.abs(from_axis - radius))), 0.02)
        self.assertEqual(len(binding["sourceTriangles"]), len(binding["indices"]) // 3)
        self.assertEqual(len(binding["edgeOrdinals"]) * 2, len(binding["edgeAlong"]))

    def test_an_animation_that_bends_no_tube_has_no_payload(self):
        self.assertIsNone(tube_skin_payload.tube_skins_bytes(tree="0" * 64, document_hash="0" * 64, animation={
            "clips": [{"id": "fade", "tracks": [{"targets": ["o1.1"], "times": [0.0], "opacity": [0.5]}]}]}))


if __name__ == "__main__":
    unittest.main()
