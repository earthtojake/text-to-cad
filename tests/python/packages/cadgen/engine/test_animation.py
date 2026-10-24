"""Animations (``animation()``): a GLB's own channels, authored in a model's body, refused by name
where they name nothing or collide, recorded in the xbf beside its closure, and baked into the GLB
the model declares -- and into a GLB of its xbf, the same bytes -- STEP and LINEAR samplers on translation, rotation and scale,
``pose`` through the mechanism's forward kinematics -- within the tolerance of what the channels
say; the GLB's LINEAR keys within ``KEY_MM`` and ``KEY_DEGREES`` of the dense bake at 240 Hz, and
its STEP keys the bake's own.

The two GLBs the core suite plays and validates (``packages/core/src/lib/render/fixtures``:
``animation.glb``, ``motion.glb``) are this module's ``CHANNELS`` and ``MOTION`` baked; a test
holds them to what the baker writes now. ``CADGEN_WRITE_FIXTURES=1`` writes them afresh."""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine import build as engine_build
from cadgen.engine import document, mechanism
from cadgen.engine.export import keys
from tests.python.support.paths import REPO_ROOT

FIXTURES = REPO_ROOT / "packages/core/src/lib/render/fixtures"

# A box whose lid hinges, a latch, a knob and two feet: every path, every interpolation, and a pose.
CHANNELS = '''
import math
import build123d as bd
from cadgen import glb, xbf
from cadgen.ap242 import mechanism_state
from cadgen.gltf import animation

HINGE = bd.Axis((-40, 0, 30), (0, -1, 0))


@xbf("XBF/channels.xbf")
@glb("channels.glb")
def channels():
    body = bd.Box(80, 50, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lid = bd.Pos(0, 0, 30) * bd.Box(80, 50, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    latch = bd.Pos(42, 0, 30) * bd.Cylinder(4, 8)
    knob = bd.Pos(0, 27, 15) * bd.Box(10, 4, 10)
    feet = [bd.Pos(x, 0, -4) * bd.Box(10, 40, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            for x in (-30, 30)]
    body.label, lid.label, latch.label, knob.label = "body", "lid", "latch", "knob"
    feet[0].label, feet[1].label = "foot_1", "foot_2"
    bd.RevoluteJoint("hinge", body, axis=HINGE, angular_range=(0, 110))
    bd.RigidJoint("hinge", lid, bd.Plane(origin=HINGE.position, z_dir=HINGE.direction).location)
    body.joints["hinge"].connect_to(lid.joints["hinge"], angle=0)
    box = bd.Compound(children=[body, lid, latch, knob, bd.Compound(children=feet, label="feet")], label="channels")
    mechanism_state(box, "open", hinge=100)
    half = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))
    show = animation(box, "showcase", duration=2)
    show.pose(at={0: {}, 1: "open", 2: {}})
    show.channel("latch", path="translation", keys=[(0, (0, 0, 0)), (1, (20, 0, 0)), (2, (0, 0, 0))],
                 interpolation="LINEAR")
    show.rotation("latch", axis=(0, 0, 1), turns=1, interpolation="LINEAR")
    show.channel("knob", path="rotation", keys=[(0, (0, 0, 0, 1)), (1, half)], interpolation="STEP")
    show.hide("knob", at=1.5)
    show.scale("feet/foot_1", to=0.5, interpolation="LINEAR")
    show.stagger("feet/*", by=(0, 0, -10), step=0.5)
    show.channel("body", path="scale", keys=[(0, 1), (2, 1.2)])
    {more}
    return box
'''

# The same box with a motion alone: an AP242 configuration sequence, which every GLB of it carries.
MOTION = '''
import build123d as bd
from cadgen import glb, xbf
from cadgen.ap242 import configuration_sequence, mechanism_state

HINGE = bd.Axis((-40, 0, 30), (0, -1, 0))


@xbf("XBF/motion.xbf")
@glb("motion.glb")
def motion_box():
    body = bd.Box(80, 50, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lid = bd.Pos(0, 0, 30) * bd.Box(80, 50, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body.label, lid.label = "body", "lid"
    bd.RevoluteJoint("hinge", body, axis=HINGE, angular_range=(0, 110))
    bd.RigidJoint("hinge", lid, bd.Plane(origin=HINGE.position, z_dir=HINGE.direction).location)
    body.joints["hinge"].connect_to(lid.joints["hinge"], angle=0)
    box = bd.Compound(children=[body, lid], label="motion_box")
    mechanism_state(box, "open", hinge=100)
    return configuration_sequence(box, "open_close", [(0, {"hinge": 0}), (1, "open"), (2, {"hinge": 0})])
'''


# The hinged box with a configuration sequence and an animation of every helper but one: a pose, an
# explode, a stagger and a hide. What the GLB's keys are held to (``export/keys.py``).
FIDELITY = '''
import build123d as bd
from cadgen import glb, xbf
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.gltf import animation

HINGE = bd.Axis((-40, 0, 30), (0, -1, 0))


@xbf("XBF/fidelity.xbf")
@glb("fidelity.glb")
def fidelity():
    body = bd.Box(80, 50, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lid = bd.Pos(0, 0, 30) * bd.Box(80, 50, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    knob = bd.Pos(0, 27, 15) * bd.Box(10, 4, 10)
    feet = [bd.Pos(x, 0, -4) * bd.Box(10, 40, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            for x in (-30, 0, 30)]
    body.label, lid.label, knob.label = "body", "lid", "knob"
    for at, foot in enumerate(feet):
        foot.label = f"foot_{at + 1}"
    bd.RevoluteJoint("hinge", body, axis=HINGE, angular_range=(0, 110))
    bd.RigidJoint("hinge", lid, bd.Plane(origin=HINGE.position, z_dir=HINGE.direction).location)
    body.joints["hinge"].connect_to(lid.joints["hinge"], angle=0)
    box = bd.Compound(children=[body, lid, knob, bd.Compound(children=feet, label="feet")], label="fidelity")
    mechanism_state(box, "open", hinge=100)
    configuration_sequence(box, "open_close", [(0, {"hinge": 0}), (1, "open"), (2, {"hinge": 0})])
    show = animation(box, "show", duration=3)
    show.pose(at={0: {}, 1.5: "open", 3: {}})
    show.explode("feet/*", direction=(1, 0, 0), distance=15, end=1)
    show.stagger("feet/*", by=(0, 0, -10), step=0.4, start=1.2)
    show.hide("knob", at=2.5)
    return box
'''

def _glb(path: Path) -> tuple[dict, Any]:
    """A GLB's JSON chunk, and a reader of its accessors (as float64 rows)."""
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    blob = data[28 + length:28 + length + struct.unpack_from("<I", data, 20 + length)[0]]

    def read(at: int) -> np.ndarray:
        accessor = gltf["accessors"][at]
        view = gltf["bufferViews"][accessor["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[accessor["type"]]
        return np.frombuffer(blob, "<f4", accessor["count"] * width, view.get("byteOffset", 0)).reshape(
            accessor["count"], width).astype(float)

    return gltf, read


def _sample(times: np.ndarray, rows: np.ndarray, interpolation: str, t: float, rotation: bool) -> np.ndarray:
    """A glTF sampler at ``t``, as the specification (and three.js) evaluates it."""
    if interpolation == "CUBICSPLINE":
        keys = rows.reshape(len(times), 3, -1)
        values = keys[:, 1]
    else:
        values = rows
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    at = int(np.searchsorted(times, t, side="right")) - 1
    span = times[at + 1] - times[at]
    s = (t - times[at]) / span
    if interpolation == "STEP":
        return values[at]
    if interpolation == "LINEAR":
        a, b = values[at], values[at + 1]
        if not rotation:
            return a + s * (b - a)
        dot = float(np.dot(a, b))
        b, dot = (-b, -dot) if dot < 0 else (b, dot)
        theta = math.acos(min(1.0, dot))
        return a if theta < 1e-9 else (math.sin((1 - s) * theta) * a + math.sin(s * theta) * b) / math.sin(theta)
    found = ((2 * s ** 3 - 3 * s ** 2 + 1) * keys[at, 1] + span * (s ** 3 - 2 * s ** 2 + s) * keys[at, 2]
             + (-2 * s ** 3 + 3 * s ** 2) * keys[at + 1, 1] + span * (s ** 3 - s ** 2) * keys[at + 1, 0])
    return found / np.linalg.norm(found) if rotation else found


def _rotation(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _turn(q_a: np.ndarray, q_b: np.ndarray) -> float:
    return 2 * math.acos(min(1.0, abs(float(np.dot(q_a / np.linalg.norm(q_a), q_b / np.linalg.norm(q_b))))))


def _smooth(s: float) -> float:
    s = min(1.0, max(0.0, s))
    return s * s * (3 - 2 * s)


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-animation-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        memo.install()
        self.addCleanup(memo.clear)

    def build(self, source: str, name: str, *, ok: bool = True, stem: str = "model") -> dict:
        script = self.folder / f"{stem}.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        [report] = engine_build.build(script, [name], cwd=self.folder)
        self.assertEqual(report["ok"], ok, report.get("error") or report)
        return report

    def channels(self, more: str = "pass", ok: bool = True) -> dict:
        return self.build(CHANNELS.replace("{more}", more), "channels", ok=ok)


class AuthoringTest(unittest.TestCase):
    def test_a_builder_call_says_what_is_wrong_with_it(self) -> None:
        import build123d as bd

        from cadgen.gltf import animation

        box = bd.Box(1, 1, 1)
        show = animation(box, "show", duration=2)
        for call, error in (
                (lambda: animation("box", "a", duration=1), "takes the assembly"),
                (lambda: animation(box, "a", duration=0), "duration is a number of seconds above 0"),
                (lambda: show.translation("a", by=(1, 0, 0), end=3), "end 3 s is outside the animation's 0 to 2 s"),
                (lambda: show.translation("a", by=(1, 0, 0), to=(0, 0, 0)), "takes by= or to=: one of them"),
                (lambda: show.translation("a", by=(1, 0, 0), interpolation="cubic"),
                 "interpolation is one of CUBICSPLINE, LINEAR, STEP, not 'cubic'"),
                (lambda: show.translation("a", by=(1, 0, 0), start=1, end=1), "end 1 s is not after start 1 s"),
                (lambda: show.rotation("a", axis=(0, 0, 0), by=10), "has no direction"),
                (lambda: show.rotation("a", axis=(0, 0, 1), by=10, turns=1), "turns=, by= or to=: one of them"),
                (lambda: show.channel("a", path="weights", keys=[(0, 1)]), "path is one of translation, rotation, scale"),
                (lambda: show.channel("a", path="scale", keys=[(1, 1), (0.5, 2)]), "is not after the one before it"),
                (lambda: show.channel("a", path="rotation", keys=[(0, (0, 0, 0, 2))]), "is not a unit quaternion"),
                (lambda: show.channel("a", path="translation", keys=[]), "has no key"),
                (lambda: show.scale("a", to=-1), "a factor of 0 or more"),
                (lambda: show.hide("a", at=5), "at 5 s is outside"),
                (lambda: show.pose(at={3: "open"}), "a time 3 s is outside"),
                (lambda: show.stagger("a", by=(0, 0, 1), step=1, start=1.5), "the first move's end 2.5 s is outside"),
                (lambda: show.explode("a", distance=5), "direction= or radial=: one of them"),
                (lambda: show.translation(3, by=(0, 0, 1)), "parts is a name, a path or a glob")):
            with self.subTest(error=error), self.assertRaisesRegex((TypeError, ValueError), error):
                call()
        self.assertIs(show.rotation("a", axis=(0, 0, 1), turns=1).hide("a", at=1), show, "calls chain")


class HarvestTest(_Folder):
    def test_what_an_animation_names_wrong_fails_the_build_by_name(self) -> None:
        for more, error in (
                ('show.translation("lidd", by=(1, 0, 0))', "channels has no part or assembly lidd; nearest: lid"),
                ('show.translation("wheel*", by=(1, 0, 0))', "the glob 'wheel\\*' matches no part or assembly"),
                ('show.channel("latch", path="translation", keys=[(1.5, (0, 0, 0)), (2, (1, 0, 0))])',
                 "both drive the translation of channels/latch"),
                ('show.pose(at={1.5: "shut"})', "no configuration 'shut'"),
                ('show.translation("knob", by=(0, 0, 5), start=0, end=1)',
                 "the translation of channels/knob is STEP by .* and CUBICSPLINE by"),
                ('show.rotation("latch", axis=(1, 0, 0), to=10, start=1, end=2)',
                 "both drive the rotation of channels/latch"),
        ):
            with self.subTest(more=more):
                report = self.channels(more, ok=False)
                self.assertRegex(report["error"], error)

    def test_an_animation_named_as_a_configuration_sequence_is_refused(self) -> None:
        report = self.build(MOTION.replace('    return configuration_sequence(box', '    from cadgen.gltf import animation\n'
                                           '    animation(box, "open_close", duration=1).translation("lid", by=(0, 0, 1))\n'
                                           '    return configuration_sequence(box'), "motion_box", ok=False)
        self.assertIn("animation 'open_close' has the name of a configuration sequence of the mechanism", report["error"])

    def test_the_document_differs_by_its_animations_record_alone(self) -> None:
        import build123d as bd

        from cadgen.gltf import animation

        def shape(animated: bool) -> Any:
            base, arm = bd.Box(10, 10, 10), bd.Pos(20, 0, 0) * bd.Box(5, 5, 5)
            base.label, arm.label = "base", "arm"
            assembly = bd.Compound(children=[base, arm], label="pair")
            if animated:
                animation(assembly, "slide", duration=1).translation("arm", by=(30, 0, 0)).hide("base", at=1)
            return assembly

        from OCP.Standard import Standard_GUID

        written, loaded, trees = [], [], []
        for animated in (False, True):
            tree = document.collect(shape(animated), "pair")
            self.assertEqual(tree.animations is not None, animated)
            path = self.folder / f"pair-{animated}.xbf"
            document.save(document.to_xcaf(tree, document.Kept()), path, compare=False)
            loaded.append(document.Loaded(path))
            trees.append(tree)
            # The same document with its record forgotten: what remains is the plain one's bytes.
            doc = document.to_xcaf(tree, document.Kept())
            doc.Main().ForgetAttribute(Standard_GUID(document.ANIMATIONS_GUID))
            written.append(document.to_bytes(doc))
        self.assertEqual(written[0], written[1], "the record is all an animation adds to the document")
        self.assertIsNone(loaded[0].animations)
        self.assertEqual(loaded[1].animations, trees[1].animations, "the compiled tracks, as the harvest made them")


class RefinementLoopTest(unittest.TestCase):
    """A record read from a file whose key times are one ulp apart with a value jump between them
    must not spin the baker's refinement loop forever: a pass that adds no new key is refused."""

    def test_a_channel_that_cannot_settle_is_refused_not_looped(self) -> None:
        from cadgen.engine.export import ExportRefused
        from cadgen.engine.export.animation import _channel

        edge = 0.5
        nxt = math.nextafter(edge, 1.0)  # one ulp above 0.5; its midpoint with 0.5 rounds back to 0.5

        class StubMotion:
            duration = 1.0
            def value(self, index, path, t):  # a step jump across the edge, larger than any tolerance
                return np.array([0.0, 0.0, 0.0]) if t <= edge else np.array([30.0, 0.0, 0.0])

        start = time.monotonic()
        with self.assertRaises(ExportRefused):
            _channel(StubMotion(), 0, 'translation', {'LINEAR'}, {edge, nxt}, {'translation': 0.03})
        self.assertLess(time.monotonic() - start, 10.0, 'the loop must end quickly, not spin')


class KeysTest(unittest.TestCase):
    """``keys.linear`` alone: what it keeps of a track, and what it adds to one."""

    def test_a_line_keeps_its_ends_and_a_jump_both_its_keys(self) -> None:
        times = np.array([0.0, 0.5, 1.0, 1.0 + 1e-9, 1.5, 2.0])
        values = np.array([[0, 0, 0], [5, 0, 0], [10, 0, 0], [30, 0, 0], [35, 0, 0], [40, 0, 0]], dtype=float)
        kept, rows = keys.linear(times, values, "LINEAR", "translation", 2.0)
        self.assertEqual(kept.tolist(), [0.0, 1.0, 1.0 + 1e-9, 2.0], "collinear keys go; the jump's stay")
        np.testing.assert_array_equal(rows, values[[0, 2, 3, 5]])

    def test_an_eased_step_gets_the_keys_a_line_needs_between_the_bakes(self) -> None:
        # One CUBICSPLINE step easing 60 mm over a second: two keys, flat tangents.
        rows = np.zeros((2, 3, 3))
        rows[1, 1] = (60.0, 0.0, 0.0)
        kept, values = keys.linear(np.array([0.0, 1.0]), rows, "CUBICSPLINE", "translation", 1.0)
        self.assertGreater(len(kept), 10)
        for t in np.linspace(0.0, 1.0, 1001):
            self.assertLessEqual(abs(_sample(kept, values, "LINEAR", t, False)[0] - 60 * _smooth(t)), keys.KEY_MM, t)
        again = keys.linear(np.array([0.0, 1.0]), rows, "CUBICSPLINE", "translation", 1.0)
        self.assertEqual((again[0].tobytes(), again[1].tobytes()), (kept.tobytes(), values.tobytes()))

    def test_a_dense_bake_keeps_a_few_of_its_keys(self) -> None:
        # A swing baked as a dense clip is (250 keys a second, its tangents exact): a line needs few of them.
        times = np.linspace(0.0, 2.0, 501)
        rows = np.zeros((len(times), 3, 3))
        rows[:, 1, 0] = 50 * np.sin(math.pi * times)
        rows[:, 0, 0] = rows[:, 2, 0] = 50 * math.pi * np.cos(math.pi * times)
        kept, values = keys.linear(times, rows, "CUBICSPLINE", "translation", 2.0)
        self.assertLess(len(kept), len(times) * 0.15)
        for t in np.linspace(0.0, 2.0, 2001):
            self.assertLessEqual(abs(_sample(kept, values, "LINEAR", t, False)[0] - 50 * math.sin(math.pi * t)),
                                 keys.KEY_MM + 1e-6, t)

    def test_a_turn_keeps_its_keys_within_a_third_of_a_turn(self) -> None:
        # Two whole turns at constant speed: a slerp is exact, but no two keys turn more than 120 degrees apart.
        times = np.linspace(0.0, 2.0, 49)
        values = np.array([[0.0, 0.0, math.sin(math.pi * t), math.cos(math.pi * t)] for t in times])
        kept, rows = keys.linear(times, values, "LINEAR", "rotation", 2.0)
        self.assertLess(len(kept), len(times))
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(_turn(a, b), math.radians(keys.MOST_TURN_DEGREES) + 1e-9)

    def test_a_scale_is_held_to_the_millimetres_its_part_moves(self) -> None:
        rows = np.zeros((2, 3, 3))
        rows[0, 1], rows[1, 1] = (1.0, 1.0, 1.0), (2.0, 2.0, 2.0)
        near = keys.linear(np.array([0.0, 1.0]), rows, "CUBICSPLINE", "scale", 1.0, reach=1.0)
        far = keys.linear(np.array([0.0, 1.0]), rows, "CUBICSPLINE", "scale", 1.0, reach=1000.0)
        self.assertLess(len(near[0]), len(far[0]), "a larger part needs its scale closer")


class GlbTest(_Folder):
    def test_a_restart_takes_an_animated_model_from_its_xbf_and_its_glb_is_the_cold_builds(self) -> None:
        from cadgen.engine import export
        from cadgen.engine.kernel import memo

        source = """
            import build123d as bd
            from cadgen import glb, xbf
            from cadgen.gltf import animation


            @xbf("XBF/pair.xbf")
            @glb("pair.glb")
            def pair():
                base, arm = bd.Box(10, 10, 10), bd.Pos(20, 0, 0) * bd.Box(5, 5, 5)
                base.label, arm.label = "base", "arm"
                assembly = bd.Compound(children=[base, arm], label="pair")
                animation(assembly, "slide", duration=1).translation("arm", by=(30, 0, 0))
                return assembly
        """
        self.build(source, "pair")
        self.assertNotIn("animations", document.Loaded(self.folder / "XBF/pair.xbf").closure, "the record is its own")
        memo.clear()  # a fresh worker: no memo, no document in memory
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        again = self.build(source, "pair")
        self.assertTrue(again["cache"]["used"], again["cache"])
        self.assertEqual(again["memo"]["bodies_run"], 0, "taken from its file: nothing ran")
        out = self.folder / "again.glb"
        export.translate(engine_build.held(self.folder / "model.py", "pair"), None, out)
        self.assertEqual([clip["name"] for clip in _glb(out)[0]["animations"]], ["slide"])
        self.assertEqual(out.read_bytes(), (self.folder / "pair.glb").read_bytes())

    def test_a_declared_glb_bakes_every_path_and_interpolation_within_the_tolerance(self) -> None:
        self.channels()
        out = self.folder / "channels.glb"
        gltf, read = _glb(out)
        names = [node["name"] for node in gltf["nodes"]]
        [showcase] = [animation for animation in gltf["animations"] if animation["name"] == "showcase"]
        self.assertEqual(showcase["extras"], {"cadgen": {"duration": 2.0}})
        found = {}
        for channel in showcase["channels"]:
            sampler = showcase["samplers"][channel["sampler"]]
            times = read(sampler["input"])[:, 0]
            self.assertEqual((times[0], times[-1]), (0.0, 2.0), "every sampler runs the whole animation")
            found[(names[channel["target"]["node"]], channel["target"]["path"])] = (
                sampler["interpolation"], times, read(sampler["output"]))
        # What the bake eases, the GLB keys LINEAR (``export/keys.py``); a STEP stays STEP.
        self.assertEqual({key: value[0] for key, value in found.items()}, {
            ("lid", "translation"): "LINEAR", ("lid", "rotation"): "LINEAR",
            ("latch", "translation"): "LINEAR", ("latch", "rotation"): "LINEAR",
            ("knob", "rotation"): "STEP", ("knob", "scale"): "STEP",
            ("feet/foot_1", "translation"): "LINEAR", ("feet/foot_1", "scale"): "LINEAR",
            ("feet/foot_2", "translation"): "LINEAR", ("body", "scale"): "LINEAR"})

        def at(node: str, path: str, t: float) -> np.ndarray:
            interpolation, times, rows = found[(node, path)]
            return _sample(times, rows, interpolation, t, path == "rotation")

        structure = document.Loaded(self.folder / "XBF/channels.xbf").structure()
        instances = {instance["path"].split("/", 1)[1]: instance for instance in structure["instances"]}
        size = math.dist((-45, -29, -4), (46, 29, 36))
        # The bake's tolerance of the channels, and the keys' of the bake.
        linear, angular = mechanism.LINEAR_TOLERANCE * size + keys.KEY_MM, mechanism.ANGULAR_TOLERANCE + math.radians(
            keys.KEY_DEGREES)
        worst = [0.0, 0.0]
        for t in np.linspace(0, 2, 81):
            # The lid by forward kinematics: the hinge eased 0 -> 100 -> 0 degrees.
            hinge = 100 * (_smooth(t) if t <= 1 else 1 - _smooth(t - 1))
            truth = np.array(mechanism.posed_instances(structure, {"hinge": (hinge,)})[
                structure["instances"].index(instances["lid"])]).reshape(4, 4).T
            worst[0] = max(worst[0], float(np.linalg.norm(at("lid", "translation", t) - truth[:3, 3])))
            turned = _rotation(at("lid", "rotation", t)).T @ truth[:3, :3]
            worst[1] = max(worst[1], math.acos(max(-1.0, min(1.0, (np.trace(turned) - 1) / 2))))
            # The latch: out 20 mm and back, linearly, turning once about its own axis at constant speed.
            np.testing.assert_allclose(at("latch", "translation", t), [42 + 20 * (1 - abs(1 - t)), 0, 30], atol=1e-3)
            spun = _rotation(at("latch", "rotation", t))
            angle = math.atan2(spun[1, 0], spun[0, 0]) % (2 * math.pi)
            self.assertLess(min(abs(angle - (math.pi * t) % (2 * math.pi)),
                                2 * math.pi - abs(angle - (math.pi * t) % (2 * math.pi))), 1e-3, t)
            # The knob: its quarter turn held until 1 s, then its scale 0 from 1.5 s.
            self.assertAlmostEqual(_turn(at("knob", "rotation", t), np.array([0, 0, 0, 1.0])),
                                   0.0 if t < 1 else math.pi / 2, places=5)
            np.testing.assert_allclose(at("knob", "scale", t), [0.0 if t >= 1.5 else 1.0] * 3)
            # The feet: dropped 10 mm in turn, the first shrinking to half over the whole.
            for foot, start in (("feet/foot_1", 0.0), ("feet/foot_2", 0.5)):
                expected = -4 - 10 * _smooth((t - start) / 0.5)
                self.assertLess(abs(at(foot, "translation", t)[2] - expected), linear, (foot, t))
            np.testing.assert_allclose(at("feet/foot_1", "scale", t), [1 - 0.25 * t] * 3, atol=1e-6)
            # The body's scale: within the bake's 1e-3, and the keys' tenth of a millimetre at its farthest corner.
            self.assertLess(abs(at("body", "scale", t)[0] - (1 + 0.2 * _smooth(t / 2))),
                            1e-3 + keys.KEY_MM / math.dist((0, 0, 0), (40, 25, 30)), t)
        self.assertLess(worst[0], mechanism.LINEAR_TOLERANCE * size * 1.5 + keys.KEY_MM, worst)
        self.assertLess(worst[1], mechanism.ANGULAR_TOLERANCE * 1.5 + math.radians(keys.KEY_DEGREES), worst)
        nodes = {node["name"]: node for node in gltf["nodes"][1:]}
        self.assertNotIn("matrix", nodes["knob"], "an animated node stands by translation and rotation")

    def test_parts_that_move_as_one_share_one_sampler(self) -> None:
        """Two parts of one reference stand where its motion puts them, the same keys: their channels
        point at one sampler, written once, and each still plays its part's motion."""
        self.build("""
            import build123d as bd
            from cadgen import glb
            from cadgen.gltf import animation


            @glb("arm.glb")
            def arm():
                upper = bd.Box(10, 10, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
                lower = bd.Box(6, 6, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
                base = bd.Box(30, 30, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
                upper.label, lower.label, base.label = "upper", "lower", "base"
                arm = bd.Compound(children=[upper, lower], label="arm")
                model = bd.Compound(children=[base, arm], label="model")
                show = animation(model, "lift", duration=2)
                show.translation("arm", by=(0, 0, 25), interpolation="LINEAR")
                show.rotation("arm", axis=(0, 0, 1), by=90, start=1, end=2)
                return model
        """, "arm")
        gltf, read = _glb(self.folder / "arm.glb")
        names = [node["name"] for node in gltf["nodes"]]
        [lift] = gltf["animations"]
        sampler = {(names[channel["target"]["node"]], channel["target"]["path"]): channel["sampler"]
                   for channel in lift["channels"]}
        self.assertEqual(sorted(sampler), [("arm/lower", "rotation"), ("arm/lower", "translation"),
                                           ("arm/upper", "rotation"), ("arm/upper", "translation")])
        for path in ("translation", "rotation"):
            self.assertEqual(sampler[("arm/upper", path)], sampler[("arm/lower", path)], path)
        self.assertEqual(len(lift["samplers"]), 2, "one sampler per motion, not per part")
        outputs = [entry["output"] for entry in lift["samplers"]]
        self.assertEqual(len(set(outputs)), 2)
        at = {path: lift["samplers"][sampler[("arm/upper", path)]] for path in ("translation", "rotation")}
        moved = _sample(read(at["translation"]["input"])[:, 0], read(at["translation"]["output"]),
                        at["translation"]["interpolation"], 2.0, False)
        np.testing.assert_allclose(moved, [0, 0, 25], atol=1e-3)

    def test_the_glbs_linear_keys_stay_within_a_tenth_of_the_dense_bake_at_240_hz(self) -> None:
        """A configuration sequence and an animation with a pose, an explode, a stagger and a hide,
        exported from the xbf: every track the bakes hand the GLB (a spy on ``keys.linear``) and the
        LINEAR keys written for it, sampled at 240 Hz, stay within ``KEY_MM`` (a scale: at its part's
        farthest point) and ``KEY_DEGREES``; the hide's STEP keys are the bake's, its jump at the time
        it names; the same document writes the same bytes."""
        from unittest import mock

        from cadgen.engine.export import translate

        self.build(FIDELITY, "fidelity")
        recorded = []
        real = keys.linear

        def spy(times, rows, interpolation, path, duration, reach=0.0):
            found = real(times, rows, interpolation, path, duration, reach)
            recorded.append((np.array(times), np.array(rows), interpolation, path, duration, reach, found))
            return found

        out = self.folder / "fidelity-again.glb"
        with mock.patch.object(keys, "linear", spy):
            translate(self.folder / "XBF/fidelity.xbf", None, out)
        self.assertEqual(out.read_bytes(), (self.folder / "fidelity.glb").read_bytes(),
                         "the same document writes the same bytes")
        self.assertEqual({(entry[2], entry[3]) for entry in recorded},
                         {("CUBICSPLINE", "translation"), ("CUBICSPLINE", "rotation")})
        dense = kept = 0  # a sparse eased bake takes more LINEAR keys, a dense one far fewer (``KeysTest``)
        worst = {"translation": 0.0, "rotation": 0.0}
        for times, rows, interpolation, path, duration, _reach, (key_times, key_values) in recorded:
            rotation = path == "rotation"
            self.assertEqual((key_times[0], key_times[-1]), (times[0], times[-1]), "the first and the last key")
            self.assertTrue(np.all(np.diff(key_times.astype(np.float32)) > 0), "times rising, as written")
            for t in np.append(np.arange(0.0, duration, 1 / 240), duration):
                bake = _sample(times, rows.reshape(-1, rows.shape[-1]), interpolation, t, rotation)
                got = _sample(key_times, key_values, "LINEAR", t, rotation)
                worst[path] = max(worst[path], _turn(got, bake) if rotation else float(np.linalg.norm(got - bake)))
            dense, kept = dense + len(times), kept + len(key_times)
        self.assertLessEqual(worst["translation"], keys.KEY_MM, worst)
        self.assertLessEqual(worst["rotation"], math.radians(keys.KEY_DEGREES), worst)
        self.assertGreater(worst["translation"], 0.0, "the keys are a line's, not the bake's curve")
        self.assertNotEqual(kept, dense)

        gltf, read = _glb(out)
        names = [node["name"] for node in gltf["nodes"]]
        self.assertEqual([animation["name"] for animation in gltf["animations"]], ["open_close", "show"])
        steps = 0
        for animation in gltf["animations"]:
            for channel in animation["channels"]:
                sampler = animation["samplers"][channel["sampler"]]
                times = read(sampler["input"])[:, 0]
                if sampler["interpolation"] == "STEP":
                    steps += 1
                    self.assertEqual((names[channel["target"]["node"]], channel["target"]["path"]), ("knob", "scale"))
                    self.assertEqual(times.tolist(), [0.0, 2.5, 3.0], "the hide keyed at the time it names, exactly")
                    self.assertEqual(read(sampler["output"])[:, 0].tolist(), [1.0, 0.0, 0.0])
                else:
                    self.assertEqual(sampler["interpolation"], "LINEAR")
                    self.assertEqual(gltf["accessors"][sampler["output"]]["count"], len(times), "a value a key")
        self.assertEqual(steps, 1)

    def test_a_glb_from_the_xbf_is_the_declared_one_and_an_edit_of_an_animation_rewrites_both(self) -> None:
        from cadgen.engine.export import translate

        self.build(MOTION.replace("    return configuration_sequence(box", "    from cadgen.gltf import animation\n"
                                  "    animation(box, 'drop', duration=1).translation('lid', by=(0, 0, 5))\n"
                                  "    return configuration_sequence(box"), "motion_box")
        declared, _read = _glb(self.folder / "motion.glb")
        self.assertEqual([animation["name"] for animation in declared["animations"]], ["open_close", "drop"])
        again = self.folder / "again.glb"
        translate(self.folder / "XBF/motion.xbf", None, again)
        self.assertEqual(again.read_bytes(), (self.folder / "motion.glb").read_bytes(),
                         "the sequence and the animation, from the xbf's record")
        before = (self.folder / "motion.glb").read_bytes()
        report = self.build(MOTION.replace("    return configuration_sequence(box", "    from cadgen.gltf import animation\n"
                                           "    animation(box, 'drop', duration=1).translation('lid', by=(0, 0, 9))\n"
                                           "    return configuration_sequence(box"), "motion_box")
        self.assertTrue(report["files"][str(self.folder / "motion.glb")]["written"])
        self.assertTrue(report["files"][str(self.folder / "XBF/motion.xbf")]["written"], "its record moved")
        self.assertNotEqual((self.folder / "motion.glb").read_bytes(), before)

    def test_a_parent_that_reads_a_childs_xbf_has_none_of_its_animations(self) -> None:
        self.build(MOTION.replace("    return configuration_sequence(box", "    from cadgen.gltf import animation\n"
                                  "    animation(box, 'drop', duration=1).translation('lid', by=(0, 0, 5))\n"
                                  "    return configuration_sequence(box"), "motion_box")
        self.assertEqual(sorted(document.Loaded(self.folder / "XBF/motion.xbf").animations), ["drop"])
        self.build(f"""
            import build123d as bd
            from cadgen import glb, read_xbf
            from cadgen.gltf import animation


            @glb("shelf.glb")
            def shelf():
                box = read_xbf({str(self.folder / "XBF/motion.xbf")!r})
                box.label = "box"
                board = bd.Box(200, 100, 5)
                board.label = "board"
                shelf = bd.Compound(children=[board, box], label="shelf")
                animation(shelf, "lift", duration=1).translation("board", by=(0, 0, 9))
                return shelf
        """, "shelf", stem="shelf")
        self.assertEqual([clip["name"] for clip in _glb(self.folder / "shelf.glb")[0]["animations"]], ["lift"],
                         "its own animation alone: read_xbf imports a part, never the child's record")


class FixturesTest(_Folder):
    """The core suite's animated GLBs are what the baker writes: their animations, key for key."""

    def test_the_core_suites_glb_fixtures_are_the_bakers(self) -> None:
        for source, name, glb, fixture in ((CHANNELS.replace("{more}", "pass"), "channels", "channels.glb",
                                            "animation.glb"), (MOTION, "motion_box", "motion.glb", "motion.glb")):
            with self.subTest(fixture=fixture):
                self.build(source, name, stem=name)
                made = self.folder / glb
                if os.environ.get("CADGEN_WRITE_FIXTURES") == "1":
                    shutil.copyfile(made, FIXTURES / fixture)
                ours, read_ours = _glb(made)
                theirs, read_theirs = _glb(FIXTURES / fixture)
                self.assertEqual(ours["animations"], theirs["animations"])
                self.assertEqual([node["name"] for node in ours["nodes"]], [node["name"] for node in theirs["nodes"]])
                for animation in ours["animations"]:
                    for sampler in animation["samplers"]:
                        for key in ("input", "output"):
                            np.testing.assert_allclose(read_ours(sampler[key]), read_theirs(sampler[key]), atol=1e-4)


if __name__ == "__main__":
    unittest.main()
