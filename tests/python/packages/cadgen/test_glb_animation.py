"""A baked clip as glTF animation (`cadgen glb build --animation`).

The bake's keys are glTF's own, so the export writes them as they stand. These pin
the window a request cuts (its edges, and a loop's seam), a transform track as a
pivot in glTF's Y-up metres, a tube track as a skin, the effects glTF cannot
animate refused or baked by name -- and one real document exported end to end:
its pivot playing the sidecar's own keys, and its cord, still or carried by a
turn, its joints under one skeleton, posed by them onto the bend the clip authored.
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import numpy as np  # noqa: E402

from cadgen._internal import tube_skin, tube_skin_payload  # noqa: E402
from cadgen._internal.animation_bake import LENGTH_FLOOR, _apply_point, _pose_at  # noqa: E402
from cadgen._internal.glb_animation import (  # noqa: E402
    _transform_mix,
    Window,
    clip_to_gltf,
    find_clip,
    gltf_point,
    resolve_window,
    restrict_to_nodes,
    windowed,
)
from cadgen._internal.mesh_animation import MAX_LOOP_REPEATS  # noqa: E402
from tests.python.support.tube_skins import view_skin  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
SQRT_HALF = math.sqrt(0.5)
CURL_RADIUS = 20 / (math.pi / 2)  # the real document's 20 mm cord curled into a quarter circle


def turn_key(degrees: float, rate: float = 0.0) -> list[float]:
    """A transform key turned ``degrees`` about +Z, its pivot unmoved, turning on at
    ``rate`` degrees a second: [d, q, d', q']."""
    half, turning = math.radians(degrees) / 2, math.radians(rate) / 2
    return [0.0, 0.0, 0.0, 0.0, 0.0, math.sin(half), math.cos(half),
            0.0, 0.0, 0.0, 0.0, 0.0, math.cos(half) * turning, -math.sin(half) * turning]


def spin_clip(*, duration: int = 4, loop: bool = True, pivot=(0.0, 0.0, 0.0), targets=("o1.2",), extra=()) -> dict:
    """``targets`` spin about +Z at 90 degrees a second, keyed every second."""
    track = {"targets": list(targets), "times": list(range(duration + 1)), "pivot": list(pivot),
             "transform": [turn_key(90 * second, 90) for second in range(duration + 1)]}
    return {"id": "spin", "label": "Spin", "duration": duration, "loop": loop, "tracks": [track, *extra]}


def line(end_y: float) -> dict:
    return {"normal": [0.0, 0.0, 1.0], "segments": [{"kind": "line", "start": [0.0, 0.0, 0.0], "end": [10.0, end_y, 0.0]}]}


def tube_track(keys: list, times: list, *, targets=("o1.3",), braid=None) -> dict:
    track = {"targets": list(targets), "times": times, "tube": keys, "rest": line(0.0), "maxSegmentLength": 1.0}
    if braid:
        track["braid"] = braid
    return track


def whole(clip: dict) -> Window:
    return resolve_window({}, clip)


class TheWindow(unittest.TestCase):
    def test_a_clip_supplies_the_span_a_request_leaves_out(self):
        self.assertEqual((0.0, 4.0), (whole(spin_clip()).start, whole(spin_clip()).seconds))
        late = resolve_window({"start": 1}, spin_clip(loop=False))
        self.assertEqual((1.0, 3.0), (late.start, late.seconds))

    def test_a_span_the_clip_cannot_fill_is_refused_or_named(self):
        with self.assertRaisesRegex(ValueError, "start 4s is at or past the end of a 4s clip"):
            resolve_window({"start": 4}, spin_clip())
        with self.assertRaisesRegex(ValueError, "seconds must be a positive number"):
            resolve_window({"seconds": 0}, spin_clip())
        with self.assertRaisesRegex(ValueError, f"past {MAX_LOOP_REPEATS} times"):
            resolve_window({"seconds": 4 * MAX_LOOP_REPEATS + 4}, spin_clip())
        (warning,) = resolve_window({"seconds": 6}, spin_clip(loop=False)).warnings
        self.assertIn("clip that does not loop: past its end the file holds its final pose", warning)

    def test_the_window_cuts_each_track_at_its_edges(self):
        clip = {"duration": 2, "loop": False}
        times, values = windowed([0, 1, 2], [0.0, 10.0, 20.0], resolve_window({"start": 0.5, "seconds": 1}, clip),
                                 lambda a, b, u, span: a + (b - a) * u)
        self.assertEqual(([0.0, 0.5, 1.0], [5.0, 10.0, 15.0]), (times, values))

    def test_a_transform_cut_between_keys_is_the_curve_there_with_its_rate(self):
        # A slide at a constant 10 mm/s while turning at 90 degrees a second: glTF's
        # cubic curve through these keys is the motion, and so is a key cut from it.
        keys = [[10.0 * t, 0.0, 0.0, *turn_key(90 * t, 90)[3:7], 10.0, 0.0, 0.0, *turn_key(90 * t, 90)[10:]]
                for t in (0, 1)]
        clip = {"duration": 1, "loop": False}
        _, (start, end) = windowed([0, 1], keys, resolve_window({"start": 0.5, "seconds": 0.5}, clip), _transform_mix)
        np.testing.assert_allclose(5.0, start[0], atol=1e-12)
        np.testing.assert_allclose(10.0, start[7], atol=1e-12)
        np.testing.assert_allclose(1.0, np.linalg.norm(start[3:7]), atol=1e-12)
        # Its rate is the curve's, perpendicular to the unit quaternion it moves.
        self.assertAlmostEqual(0.0, float(np.dot(start[3:7], start[10:14])), places=12)
        np.testing.assert_allclose(keys[1], end, atol=1e-12)

    def test_a_loop_repeats_its_keys_and_a_short_track_holds_to_the_seam(self):
        lerp = lambda a, b, u, span: a + (b - a) * u  # noqa: E731
        clip = {"duration": 2, "loop": True}
        window = resolve_window({"seconds": 4}, clip)
        # Keyed to its end: one cycle's last key IS the next one's first.
        self.assertEqual(([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 10.0, 0.0, 10.0, 0.0]),
                         windowed([0, 1, 2], [0.0, 10.0, 0.0], window, lerp))
        # Stopping short: it holds its last value up to the seam, then starts again.
        times, values = windowed([0, 1], [0.0, 10.0], window, lerp)
        self.assertEqual([0.0, 10.0, 10.0, 0.0, 10.0, 10.0], values)
        self.assertEqual([0.0, 1.0, 2.0, 3.0, 4.0], [round(t, 4) for t in times[:2] + times[3:]])
        self.assertLess(times[2], 2.0)


class Pivots(unittest.TestCase):
    def test_a_transform_track_is_a_pivot_in_gltf_space(self):
        (pivot,) = clip_to_gltf(spin_clip(pivot=(10.0, 0.0, 0.0)), whole(spin_clip())).pivots
        self.assertEqual(("o1.2",), pivot.members)
        self.assertEqual([0.0, 1.0, 2.0, 3.0, 4.0], pivot.times)
        # The node sits on the pivot, 10 mm along CAD +X: glTF +X, in metres; its child undoes it.
        self.assertEqual([0.01, 0.0, -0.0], pivot.rest_translation)
        self.assertEqual([-0.01, 0.0, -0.0], pivot.child_translation)
        # A quarter turn about CAD +Z is a quarter turn about glTF +Y, and its rate maps alike;
        # the rates go in to and out of every key alike, there being no hold.
        np.testing.assert_allclose([0.0, SQRT_HALF, 0.0, SQRT_HALF], pivot.rotations[4:8], atol=1e-12)
        rate = math.pi / 4
        np.testing.assert_allclose([0.0, SQRT_HALF * rate, 0.0, -SQRT_HALF * rate], pivot.rotations_out[4:8], atol=1e-12)
        self.assertEqual(pivot.rotations_in, pivot.rotations_out)
        self.assertEqual([0.0] * 15, pivot.translations_in)

    def test_every_key_stays_in_the_hemisphere_of_the_one_before(self):
        clip = spin_clip(duration=1, loop=False)
        flipped = turn_key(90, 90)
        clip["tracks"][0]["transform"][1] = flipped[:3] + [-c for c in flipped[3:7]] + flipped[7:10] + [
            -c for c in flipped[10:]]  # the same turn and rate, the far sign
        (pivot,) = clip_to_gltf(clip, whole(clip)).pivots
        first, second = pivot.rotations[0:4], pivot.rotations[4:8]
        self.assertGreater(sum(a * b for a, b in zip(first, second)), 0.0)
        # The rate flips with it: still turning on about glTF +Y.
        self.assertGreater(pivot.rotations_out[5], 0.0)

    def test_an_effect_gltf_cannot_animate_is_refused_unless_dropped_then_baked_at_start(self):
        fade = {"targets": ["o1.4"], "times": [0, 4], "opacity": [0.25, 1.0]}
        hide = {"targets": ["o1.5"], "times": [0], "visible": [False]}
        clip = spin_clip(extra=[fade, hide])
        with self.assertRaisesRegex(ValueError, r"animates \.opacity\(\) on o1\.4.*drop: \[\"opacity\"\]"):
            clip_to_gltf(clip, whole(clip))
        baked = clip_to_gltf(clip, whole(clip), drop=["opacity", "visible"])
        self.assertEqual(({"o1.4": 0.25}, {"o1.5"}), (baked.opacity, baked.hidden))
        self.assertEqual(2, sum("is not an animated glTF channel" in warning for warning in baked.warnings))
        with self.assertRaisesRegex(ValueError, "drop names glow, which is not an effect"):
            clip_to_gltf(clip, whole(clip), drop=["glow"])

    def test_a_pivot_carrying_an_occurrence_with_no_geometry_drops_it_by_name(self):
        clip = spin_clip(targets=("o1.2", "o1.9"))
        restricted = restrict_to_nodes(clip_to_gltf(clip, whole(clip)), {"o1.2"})
        self.assertEqual(("o1.2",), restricted.pivots[0].members)
        self.assertIn("o1.9 moves in this clip but has no geometry in the export", restricted.warnings[-1])

    def test_a_clip_is_found_by_id_or_refused_with_the_ones_there_are(self):
        animation = {"clips": [spin_clip()]}
        self.assertEqual("spin", find_clip(animation, "spin")["id"])
        with self.assertRaisesRegex(ValueError, "Unknown animation clip: spun. This model declares: spin"):
            find_clip(animation, "spun")


class Skins(unittest.TestCase):
    def test_a_tube_track_is_a_skin_whose_joints_are_its_keys(self):
        clip = {"id": "bend", "label": "Bend", "duration": 1, "loop": False, "tracks": [
            tube_track([{"path": line(0.0), "twistDeg": 0.0}, {"path": line(4.0), "twistDeg": 90.0}], [0, 1])]}
        (skin,) = clip_to_gltf(clip, whole(clip)).skins
        rest = tube_skin.compile_rest(line(0.0))
        self.assertEqual(len(tube_skin.joint_fractions(rest, 1.0)), len(skin.fractions))
        self.assertEqual(((2, 11, 3), (2, 11, 4), (11, 16)),
                         (skin.translations.shape, skin.rotations.shape, skin.inverse_binds.shape))
        # The first key is the rest: every joint's pose times its inverse bind is the identity.
        for joint in range(11):
            q = skin.rotations[0, joint]
            x, y, z, w = q
            pose = np.eye(4)
            pose[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
            pose[:3, 3] = skin.translations[0, joint]
            np.testing.assert_allclose(np.eye(4), pose @ skin.inverse_binds[joint].reshape(4, 4).T, atol=1e-9)
        # The last key's far joint is the bent path's end: (10, 4, 0) mm is glTF (0.01, 0, -0.004) m.
        np.testing.assert_allclose([0.01, 0.0, -0.004], skin.translations[1, -1], atol=1e-12)

    def test_a_tube_whose_parts_a_pivot_also_moves_hangs_from_it(self):
        bend = tube_track([{"path": line(0.0), "twistDeg": 0.0}, {"path": line(4.0), "twistDeg": 0.0}], [0, 1])
        clip = spin_clip(duration=1, loop=False, targets=("o1.3",), extra=[bend])
        self.assertEqual(0, clip_to_gltf(clip, whole(clip)).skins[0].parent)
        apart = spin_clip(duration=1, loop=False, targets=("o1.3",),
                          extra=[{**bend, "targets": ["o1.3", "o1.6"]}])
        with self.assertRaisesRegex(ValueError, "bends o1.3, o1.6 as one tube while moving them apart"):
            clip_to_gltf(apart, whole(apart))

    def test_a_braid_exports_its_shape_and_says_the_finish_is_a_shader(self):
        braid = {"pitch": 2.0, "depth": 0.1, "strands": 8}
        clip = {"id": "bend", "label": "Bend", "duration": 1, "loop": False, "tracks": [
            tube_track([None, {"path": line(4.0), "twistDeg": 0.0}], [0, 1], braid=braid)]}
        (warning,) = clip_to_gltf(clip, whole(clip)).warnings
        self.assertIn("o1.3 carries a braid: the strand pattern is a shader", warning)


MODEL = textwrap.dedent("""\
    import math

    import cadgen
    from cadgen import build123d as bd
    from cadgen import step

    REST = {"normal": [0, 0, 1], "segments": [{"kind": "line", "start": [0, 10, 2], "end": [20, 10, 2]}]}


    def turn(t, m):
        m.get("#lever").rotate((0, 0, 1), 90 * t)


    def curl(cord, t, spacing):
        # The 20 mm cord curls into a quarter circle, keeping its length.
        angle = max(t, 1e-3) * math.pi / 2
        cord.deform_tube(rest=REST, path={"normal": [0, 0, 1], "segments": [{
            "kind": "arc", "center": [0, 10 + 20 / angle, 2], "axis": [0, 0, 1], "start": [0, 10, 2],
            "sweepDeg": math.degrees(angle)}]}, max_segment_length=spacing)


    def bend(t, m):
        curl(m.get("#cord"), t, 2)


    def swing(t, m):
        # Carried a quarter turn about Z as it curls, on joints 4 mm apart: six of them.
        cord = m.get("#cord")
        curl(cord, t, 4)
        cord.rotate((0, 0, 1), 90 * t)


    @step(out="arm.step", animation={"turn": cadgen.clip(turn, duration=1, loop=False, fps=10),
                                     "bend": cadgen.clip(bend, duration=1, loop=False, fps=10),
                                     "swing": cadgen.clip(swing, duration=1, loop=False, fps=10)})
    def arm():
        base = bd.Box(10, 10, 2)
        base.label = "base"
        lever = bd.Pos(10, 0, 3) * bd.Box(20, 2, 2)
        lever.label = "lever"
        cord = bd.sweep(bd.Plane(origin=(0, 10, 2), z_dir=(1, 0, 0)) * bd.Circle(0.8), path=bd.Edge.make_line((0, 10, 2), (20, 10, 2)))
        cord.label = "cord"
        return bd.Compound(children=[base, lever, cord], label="assembly")


    if __name__ == "__main__":
        arm()
    """)


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length]), data[28 + length:]


def _array(gltf: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[accessor["type"]]
    dtype = {5126: "<f4", 5123: "<u2", 5125: "<u4"}[accessor["componentType"]]
    start = view["byteOffset"] + accessor.get("byteOffset", 0)
    return np.frombuffer(binary, dtype=dtype, count=accessor["count"] * width, offset=start).reshape(
        accessor["count"], width)


def _matrix(translation, rotation) -> np.ndarray:
    x, y, z, w = rotation
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, 3] = translation
    return m


def _at(gltf: dict, binary: bytes, sampler: dict, t: float) -> np.ndarray:
    """A sampler's value at ``t`` as a glTF player draws it: CUBICSPLINE the cubic
    Hermite curve through each key's value and tangents, LINEAR read at its keys; a
    rotation normalized."""
    times = _array(gltf, binary, sampler["input"])[:, 0].astype(np.float64)
    output = _array(gltf, binary, sampler["output"]).astype(np.float64)
    k = min(max(int(np.searchsorted(times, t, side="right")) - 1, 0), len(times) - 2)
    span = times[k + 1] - times[k]
    u = (t - times[k]) / span
    if sampler["interpolation"] == "CUBICSPLINE":
        keys = output.reshape(len(times), 3, -1)  # in-tangent, value, out-tangent
        value = ((2 * u ** 3 - 3 * u ** 2 + 1) * keys[k, 1] + span * (u ** 3 - 2 * u ** 2 + u) * keys[k, 2]
                 + (3 * u ** 2 - 2 * u ** 3) * keys[k + 1, 1] + span * (u ** 3 - u ** 2) * keys[k + 1, 0])
    else:
        assert u in (0.0, 1.0), "a LINEAR sampler is read at its keys here"
        value = output[k + int(u)]
    return value / np.linalg.norm(value) if len(value) == 4 else value


def _worlds(gltf: dict, binary: bytes, t: float) -> list[np.ndarray]:
    """Every node's world matrix at ``t`` of the file's clip."""
    (clip,) = gltf["animations"]
    posed: dict[int, dict] = {}
    for channel in clip["channels"]:
        posed.setdefault(channel["target"]["node"], {})[channel["target"]["path"]] = _at(
            gltf, binary, clip["samplers"][channel["sampler"]], t)
    parents = {child: index for index, node in enumerate(gltf["nodes"]) for child in node.get("children", [])}
    worlds: dict[int, np.ndarray] = {}

    def world(index: int) -> np.ndarray:
        if index not in worlds:
            node, pose = gltf["nodes"][index], posed.get(index, {})
            local = _matrix(pose.get("translation", node.get("translation", [0.0, 0.0, 0.0])),
                            pose.get("rotation", node.get("rotation", [0.0, 0.0, 0.0, 1.0])))
            worlds[index] = world(parents[index]) @ local if index in parents else local
        return worlds[index]

    return [world(index) for index in range(len(gltf["nodes"]))]


def _cad(points: np.ndarray) -> np.ndarray:
    """glTF Y-up metres back to the document's Z-up millimetres."""
    return np.column_stack([points[:, 0], -points[:, 2], points[:, 1]]) * 1000.0


class ARealDocumentPlaysItsClip(unittest.TestCase):
    """The door end to end: a built document's clip, through the store's meshes, into a GLB."""

    def assert_one_skeleton(self, gltf: dict, *, under: int | None) -> None:
        """glTF asks a skin's joints for one common root: every joint is a child of the
        skin's ``skeleton``, a still node at the scene's root or ``under`` the pivot
        that carries the tube, and the skinned node itself stays a root."""
        parents = {child: index for index, node in enumerate(gltf["nodes"]) for child in node.get("children", [])}
        roots = set(gltf["scenes"][0]["nodes"])
        for skin in gltf["skins"]:
            skeleton = skin.get("skeleton")
            self.assertIsNotNone(skeleton, f"{skin['name']} names no skeleton")
            self.assertEqual({skeleton}, {parents.get(joint) for joint in skin["joints"]})
            self.assertEqual(under, parents.get(skeleton))
            self.assertEqual(under is None, skeleton in roots)
            self.assertFalse({"translation", "rotation", "scale", "matrix"} & set(gltf["nodes"][skeleton]))
        for index, node in enumerate(gltf["nodes"]):
            if "skin" in node:
                self.assertIn(index, roots)
                self.assertNotIn(index, parents)

    def assert_curled(self, gltf: dict, binary: bytes, *, carried: float) -> None:
        """Posed by the file's own last keys as glTF draws a skin -- each joint's world
        matrix times its inverse bind, the skinned node's own transform ignored -- every
        vertex of the cord's wall sits 0.8 mm from the quarter circle the clip curled its
        centerline into, carried ``carried`` degrees about Z."""
        names = {node["name"]: index for index, node in enumerate(gltf["nodes"])}
        cord = gltf["nodes"][names["cord"]]
        skin = gltf["skins"][cord["skin"]]
        worlds = _worlds(gltf, binary, 1.0)
        binds = _array(gltf, binary, skin["inverseBindMatrices"]).astype(np.float64)
        matrices = np.stack([worlds[joint] @ binds[n].reshape(4, 4).T for n, joint in enumerate(skin["joints"])])
        turn = math.radians(carried)
        center = (-math.sin(turn) * (10.0 + CURL_RADIUS), math.cos(turn) * (10.0 + CURL_RADIUS))
        for primitive in gltf["meshes"][cord["mesh"]]["primitives"]:
            positions = _array(gltf, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
            joints = _array(gltf, binary, primitive["attributes"]["JOINTS_0"])
            weights = _array(gltf, binary, primitive["attributes"]["WEIGHTS_0"]).astype(np.float64)
            # A slot with no weight names joint 0, as glTF asks.
            self.assertFalse(np.any(joints[weights == 0]), "an unweighted slot names a joint")
            homogeneous = np.column_stack([positions, np.ones(len(positions))])
            posed = _cad(sum(weights[:, slot, None] * np.einsum("vij,vj->vi", matrices[joints[:, slot]], homogeneous)
                             for slot in range(4))[:, :3])
            rest = _cad(positions)
            wall = np.hypot(rest[:, 1] - 10.0, rest[:, 2] - 2.0) > 0.79
            from_axis = np.hypot(np.hypot(posed[:, 0] - center[0], posed[:, 1] - center[1]) - CURL_RADIUS,
                                 posed[:, 2] - 2.0)
            self.assertGreater(int(wall.sum()), 0)
            self.assertLessEqual(float(np.max(np.abs(from_axis[wall] - 0.8))), 0.02)

    def test_the_exported_file_moves_and_bends_what_the_clip_does(self):
        with tempfile.TemporaryDirectory(prefix="glb-animation-") as folder:
            root = Path(folder).resolve()
            (root / "arm.py").write_text(MODEL, encoding="utf-8")
            env = {**os.environ, "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
                   "CADGEN_CACHE_DIR": str(root / "store"), "PYTHONPATH": str(REPO / "packages/cadgen/src")}

            def run(*argv: str) -> subprocess.CompletedProcess:
                proc = subprocess.run([sys.executable, *argv], cwd=root, env=env, capture_output=True,
                                      text=True, timeout=600)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                return proc

            run("arm.py")
            # A snapshot plays one clip, and is handed that clip alone: the one that only
            # turns names no tube skins though the other bends the cord; that one names them.
            snapshot = run("-c", "import json; from pathlib import Path\n"
                           "from cadgen.snapshot_cli import resolve_step_render_job\n"
                           "here = Path('.').resolve()\n"
                           "out = {}\n"
                           "for clip in ('turn', 'bend'):\n"
                           "    job = resolve_step_render_job({'input': 'arm.step', 'mode': 'view', 'outputs': [],"
                           " 'animation': {'clip': clip, 'time': 0.5}}, kind='step',"
                           " input_path=here / 'arm.step', root_path=here, reference_root=here)\n"
                           "    out[clip] = ([c['id'] for c in job['resolved']['animation']['clips']],"
                           " bool(job['resolved'].get('tubeSkinsUrl')))\n"
                           "print(json.dumps(out))")
            self.assertEqual({"turn": [["turn"], False], "bend": [["bend"], True]},
                             json.loads(snapshot.stdout.strip().splitlines()[-1]))
            door = run("-m", "cadgen.cli", "glb", "build", "arm.step", "arm-turn.glb", "--animation", "turn", "--json")
            (entry,) = json.loads(door.stdout.strip().splitlines()[-1])["files"]
            self.assertEqual({"clip": "turn", "seconds": 1.0, "start": 0.0, "pivots": 1, "skins": 0},
                             {key: entry["animation"][key] for key in ("clip", "seconds", "start", "pivots", "skins")})
            gltf, binary = _read_glb(root / "arm-turn.glb")
            names = {node["name"]: index for index, node in enumerate(gltf["nodes"])}
            self.assertEqual([names["lever"]], gltf["nodes"][names["pivot 0 offset"]]["children"])
            self.assertNotIn(names["lever"], gltf["scenes"][0]["nodes"])
            (clip,) = gltf["animations"]
            (rotation,) = [channel for channel in clip["channels"] if channel["target"]["path"] == "rotation"]
            self.assertEqual(names["pivot 0"], rotation["target"]["node"])
            sampler = clip["samplers"][rotation["sampler"]]
            self.assertEqual("CUBICSPLINE", sampler["interpolation"])
            # The last key is 1 s in: 90 degrees about CAD +Z, which is glTF +Y -- the middle of
            # its in-tangent, value and out-tangent.
            np.testing.assert_allclose([0.0, SQRT_HALF, 0.0, SQRT_HALF],
                                       np.abs(_array(gltf, binary, sampler["output"])[-2]), atol=1e-4)

            # The pivot plays the sidecar's own keys, the window's edge keys with the
            # tangents written for them: inside the first and the last segment the
            # lever's far end sits where those keys' curve puts it.
            sidecar = json.loads((root / "arm.step.json").read_text(encoding="utf-8"))
            (track,) = find_clip(sidecar["animation"], "turn")["tracks"]
            times, keys, pivot = track["times"], track["transform"], track["pivot"]
            off = 0.0
            for k in sorted({0, len(times) - 2}):
                span = times[k + 1] - times[k]
                for u in (0.25, 0.5, 0.75):
                    d, r = _pose_at(keys[k], keys[k + 1], span, u)
                    lever = _worlds(gltf, binary, times[k] + u * span)[names["lever"]]
                    for corner in ((20.0, -1.0, 4.0), (20.0, 1.0, 2.0)):
                        drawn = _cad((lever @ [*gltf_point(corner), 1.0])[None, :3])[0]
                        keyed = _apply_point(r, [pivot[n] + d[n] for n in range(3)],
                                             [corner[n] - pivot[n] for n in range(3)])
                        off = max(off, math.dist(drawn, keyed))
            # Bounded by the rounding the keys are written at: re-deriving the first key's
            # tangent missed by 2.4e-3 mm here, inside this model's bake tolerance.
            self.assertLess(off, LENGTH_FLOOR, "the GLB's pivot leaves the curve the sidecar's keys describe")

            # The cord bends as a skin: its node names the skin, its primitives are bound
            # to the joints, and the joints' keys drive it.
            door = run("-m", "cadgen.cli", "glb", "build", "arm.step", "arm-bend.glb", "--animation", "bend", "--json")
            (entry,) = json.loads(door.stdout.strip().splitlines()[-1])["files"]
            self.assertEqual((0, 1, 11), (entry["animation"]["pivots"], entry["animation"]["skins"],
                                          entry["animation"]["joints"]))
            gltf, binary = _read_glb(root / "arm-bend.glb")
            names = {node["name"]: index for index, node in enumerate(gltf["nodes"])}
            cord = gltf["nodes"][names["cord"]]
            (skin,) = gltf["skins"]
            self.assertEqual(0, cord["skin"])
            self.assertEqual(11, len(skin["joints"]))
            (clip,) = gltf["animations"]
            targets = {channel["target"]["node"] for channel in clip["channels"]}
            self.assertEqual(set(skin["joints"]), targets)
            self.assert_one_skeleton(gltf, under=None)

            # Posed by the file's own last keys, every vertex of the cord's wall sits 0.8 mm
            # from the quarter circle the clip bent its centerline into.
            self.assert_curled(gltf, binary, carried=0.0)

            # Carried by a turn while it bends, on an even count of joints: the joints
            # hang from the pivot by their skeleton, and the skinned node stays a root.
            door = run("-m", "cadgen.cli", "glb", "build", "arm.step", "arm-swing.glb", "--animation", "swing",
                       "--json")
            (entry,) = json.loads(door.stdout.strip().splitlines()[-1])["files"]
            self.assertEqual((1, 1, 6), (entry["animation"]["pivots"], entry["animation"]["skins"],
                                         entry["animation"]["joints"]))
            gltf, binary = _read_glb(root / "arm-swing.glb")
            names = {node["name"]: index for index, node in enumerate(gltf["nodes"])}
            self.assert_one_skeleton(gltf, under=names["pivot 0 offset"])
            self.assert_curled(gltf, binary, carried=90.0)

            # A CAD view reads the same tubes from the viewer's route, bound in the cord
            # component's own frame; a second read is the store's, binding nothing again.
            probe = run("-c", textwrap.dedent("""\
                import json, sys
                from pathlib import Path
                from cadgen._internal import tube_skin_payload
                from cadgen.store.view import descriptor_for_view
                from cadgen.viewer.store_paths import result_snapshot
                from cadgen.viewer.tube_skins import tube_skins_response

                status, body = tube_skins_response(sys.argv[1])
                Path(sys.argv[2]).write_bytes(body)
                tube_skin_payload.build_tube_skins = None
                again, cached = tube_skins_response(sys.argv[1])
                document, tree = result_snapshot(sys.argv[1])
                stale, _ = tube_skins_response(sys.argv[1], "0" * 64)
                placed = {o["id"]: o["transform"] for o in descriptor_for_view(tree, document_hash=document)["occurrences"]}
                print(json.dumps({"status": [status, again, stale], "same": cached == body, "placed": placed}))
                """), str(root / "arm.step"), str(root / "skins.glb"))
            answer = json.loads(probe.stdout.strip().splitlines()[-1])
            self.assertEqual(([200, 200, 409], True), (answer["status"], answer["same"]))
            skins = tube_skin_payload.decode_tube_skins((root / "skins.glb").read_bytes())
            (track,) = [entry for entry in skins["tracks"] if entry["clip"] == "bend"]
            binding = skins["bindings"][track["bindings"][0]]
            self.assertEqual(11, binding["joints"])
            placement = np.asarray(answer["placed"][binding["occurrence"]], dtype=np.float64).reshape(4, 4)
            keys = track["keys"].reshape(-1, 11, 7)
            local = binding["positions"].reshape(-1, 3).astype(np.float64)
            p = view_skin(local, binding["along"], binding["rest"].reshape(-1, 7), keys[-1], placement)
            from_axis = np.hypot(np.hypot(p[:, 0], p[:, 1] - (10.0 + CURL_RADIUS)) - CURL_RADIUS, p[:, 2] - 2.0)
            near = np.hypot(local @ placement[:3, :3].T[:, 1] + placement[1, 3] - 10.0,
                            local @ placement[:3, :3].T[:, 2] + placement[2, 3] - 2.0) > 0.79
            self.assertGreater(int(near.sum()), 0)
            self.assertLessEqual(float(np.max(np.abs(from_axis[near] - 0.8))), 0.02)


if __name__ == "__main__":
    unittest.main()
