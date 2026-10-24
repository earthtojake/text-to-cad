"""Motions: definitions in a model's code (``motion``), kept in the document beside the
configurations as AP242's interpolated configuration sequences -- waypoints, a sweep, or a
function's samples, each segment's interpolation linear or synchronous -- read back whole,
patched by a warm build to the cold build's bytes; the removed ``loop`` and ``spline`` refused by
name; and a GLB export baking each motion into a finite glTF clip whose LINEAR keys stay within the
tolerance of forward kinematics, and the keys' of the bake."""

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
from cadgen.engine.export.keys import KEY_DEGREES, KEY_MM

ARM = """
import math
import build123d as bd
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.engine import xbf


@xbf("XBF/arm.xbf")
def arm():
    base = bd.Box(100, 60, 20)
    link = bd.Pos(40, 0, 25) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    tip = bd.Pos(60, 0, 35) * bd.Box(40, 10, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    base.label, link.label, tip.label = "base", "link", "tip"
    elbow = bd.Axis((40, 0, 20), (0, 1, 0))
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("mount", link, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    slide = bd.Axis((60, 0, 30), (1, 0, 0))
    bd.LinearJoint("slide", link, axis=slide, linear_range=(0, 80))
    bd.RigidJoint("carriage", tip, bd.Plane(origin=slide.position, z_dir=slide.direction).location)
    link.joints["slide"].connect_to(tip.joints["carriage"], position=0)
    base.joints["elbow"].connect_to(link.joints["mount"], angle=0)
    arm = bd.Compound(children=[base, link, tip], label="arm")
    mechanism_state(arm, "raised", elbow=90)
    {m}configuration_sequence(arm, "lift", [(0, {{"elbow": 0}}), (1.5, "raised"), (3, {{"elbow": 0, "slide": 60}})])
    {m}configuration_sequence(arm, "wave", sweep={{"elbow": (-10, {reach})}}, duration=2, ease="linear")
    {m}{nod}configuration_sequence(arm, "nod", lambda t: {{"elbow": 45 + 20 * math.sin(t), "slide": 40 + 30 * math.sin(2 * t)}}, duration=6)
    {more}
    return arm
"""


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-motion-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "arm.py"
        self.xbf = self.folder / "XBF/arm.xbf"
        memo.install()
        self.addCleanup(memo.clear)

    def arm(self, *, ok: bool = True, reach: int = 60, more: str = "pass", nod: bool = True,
            motions: bool = True) -> dict:
        text = ARM.format(reach=reach, more=more, nod="" if nod else "# ", m="" if motions else "# ")
        self.script.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))
        [report] = engine_build.build(self.script, ["arm"], cwd=self.folder)
        self.assertEqual(report["ok"], ok, report)
        return report

    def cold(self, **values) -> bytes:
        """The arm built by a process that never built it: its bytes."""
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        self.xbf.unlink()
        self.assertFalse(self.arm(**values)["converted"]["patched"])
        return self.xbf.read_bytes()


class AuthoringTest(unittest.TestCase):
    def test_a_motion_is_one_of_waypoints_a_sweep_or_a_function_and_says_what_is_wrong(self) -> None:
        import build123d as bd

        from cadgen.ap242 import configuration_sequence

        box = bd.Box(1, 1, 1)
        for call, error in (
                (lambda: configuration_sequence(box, "m"), "waypoints, a function of time, or sweep=: one of them"),
                (lambda: configuration_sequence(box, "m", [(0, "a")], sweep={"j": (0, 1)}, duration=1), "one of them"),
                (lambda: configuration_sequence(box, "m", [(0, "a")]), "at least two waypoints"),
                (lambda: configuration_sequence(box, "m", [(1, "a"), (2, "b")]), "the first waypoint is at 0 s"),
                (lambda: configuration_sequence(box, "m", [(0, "a"), (0, "b")]), "is not after the one before it"),
                (lambda: configuration_sequence(box, "m", [(0, "a"), (1, "b")], duration=3), "waypoints give their own times"),
                (lambda: configuration_sequence(box, "m", [(0, "a"), (1, {"j": "x"})]), "joint 'j' takes a number"),
                (lambda: configuration_sequence(box, "m", sweep={"j": (0, 1)}), "sweep= takes duration="),
                (lambda: configuration_sequence(box, "m", sweep={"j": 5}, duration=1), "takes \\(from, to\\)"),
                (lambda: configuration_sequence(box, "m", lambda t: {}, duration=0), "duration is a number of seconds above 0"),
                (lambda: configuration_sequence(box, "m", lambda t: {}), "a function of time takes duration="),
                (lambda: configuration_sequence(box, "m", sweep={"j": (0, 1)}, duration=1, ease="bounce"), "ease is one of"),
                (lambda: configuration_sequence(box, "m", sweep={"j": (0, 1)}, duration=1, loop="loop"),
                 "configuration sequence 'm': loop= is gone: a configuration sequence is a finite clip, and a player "
                 "repeats it"),
                (lambda: configuration_sequence(box, "m", sweep={"j": (0, 1)}, duration=1, ease="spline"),
                 "configuration sequence 'm': ease 'spline' is gone: AP242 interpolates a configuration sequence linearly "
                 "or synchronously"),
                (lambda: configuration_sequence(box, "m", sweep={"j": (0, 1)}, duration=1, speed=2), "configuration_sequence\\(\\) takes no speed"),
                (lambda: configuration_sequence("arm", "m", sweep={"j": (0, 1)}, duration=1), "takes the assembly")):
            with self.assertRaisesRegex((TypeError, ValueError), error):
                call()
        self.assertIs(configuration_sequence(box, "m", sweep={"j": (0, 1)}, duration=1), box)


class SampledKeysTest(unittest.TestCase):
    """The keys a motion's function may return, checked at each sample: a coupling by its own or
    kept name, a joint below the assembly by its raw label or ``prefix:raw``; anything else fails
    by name, listing the assembly's joints and couplings."""

    JOINTS = [("elbow", (0, 0)), ("slide", (0, 1)), ("wrist", (1,))]  # wrist is outside path (0,)
    CONTROLS = [((0,), "curl", "hand:curl"), ((1,), "spread", "spread")]

    def sample(self, key: str) -> list:
        convert = lambda values, _at: {"elbow": (float(next(iter(values.values()))),)}  # noqa: E731
        return mechanism._sampled(lambda t: {key: 10.0}, 1.0, convert, {"elbow": [1.0]}, "motion 'm' of arm",
                                  (0,), self.JOINTS, self.CONTROLS)

    def test_accepted_key_forms(self) -> None:
        for key in ("elbow", "slide", "arm:elbow", "a:b:slide", "curl", "hand:curl"):
            with self.subTest(key=key):
                self.assertEqual(self.sample(key)[0], (0.0, None, {"elbow": (10.0,)}))

    def test_a_key_naming_no_joint_fails_by_name(self) -> None:
        for key in ("wrist", "arm:wrist", "elbowx", "spread", "elbow:", ":"):
            with self.subTest(key=key), self.assertRaises(mechanism.KinematicsError) as caught:
                self.sample(key)
            self.assertEqual(str(caught.exception), f"motion 'm' of arm names no joint {key!r}; its joints are "
                                                    "elbow, slide; its couplings are curl, hand:curl")


class DocumentTest(_Folder):
    def test_motions_are_definitions_in_the_document_read_back_whole(self) -> None:
        self.arm()
        loaded = document.Loaded(self.xbf)
        motions = loaded.mechanism.motions
        self.assertEqual(list(motions), ["lift", "nod", "wave"])
        lift = motions["lift"]
        self.assertEqual(lift.keys, [(0.0, None, {"elbow": (0.0,)}), (1.5, "raised", {}),
                                     (3.0, None, {"elbow": (0.0,), "slide": (60.0,)})])
        self.assertEqual(lift.ease, "cubic")
        self.assertEqual(motions["wave"].keys, [(0.0, None, {"elbow": (-10.0,)}), (2.0, None, {"elbow": (60.0,)})])
        self.assertEqual(motions["wave"].ease, "linear")
        # Each segment's interpolation is AP242's: the ease to the next, the last's a discontinuity.
        from OCP.Standard import Standard_GUID

        root = next(label for label in mechanism._children_of(loaded.doc.Main())
                    if label.IsAttribute(Standard_GUID(mechanism.GUID)))
        sequences = {document._label_name(label): [mechanism._string(mechanism._named(segment), "interpolation")
                                                   for segment in mechanism._children_of(label)]
                     for label in mechanism._children_of(root.FindChild(1, False).FindChild(5, False))}
        self.assertEqual(sequences["lift"], ["synchronous_interpolation_type"] * 2 + ["discontinuous_interpolation_type"])
        self.assertEqual(sequences["wave"], ["linear_interpolation_type", "discontinuous_interpolation_type"])
        block = loaded.structure()["kinematics"]["motions"]
        self.assertEqual(block["lift"]["keys"][1], {"t": 1.5, "configuration": "raised"})
        self.assertEqual(block["wave"]["duration"], 2.0)
        # The build is as the joints connect the parts: no motion and no configuration moves it.
        self.assertEqual(loaded.structure()["kinematics"]["asBuilt"]["elbow"], 0.0)

    def test_a_function_is_kept_as_samples_within_the_tolerance_at_times_the_code_chooses(self) -> None:
        self.arm()
        nod = document.Loaded(self.xbf).mechanism.motions["nod"]
        self.assertEqual(nod.ease, "linear", "a function's samples, interpolated linearly")
        times = np.array([t for t, _name, _values in nod.keys])
        self.assertEqual((times[0], times[-1]), (0.0, 6.0))
        self.assertLess(len(times), 200)
        table = np.array([[values["elbow"][0], values["slide"][0]] for _t, _name, values in nod.keys])
        worst = np.zeros(2)
        for t in np.linspace(0, 6, 997):
            got = mechanism._interpolated(times, table, "linear", float(t))
            truth = np.array([45 + 20 * math.sin(t), 40 + 30 * math.sin(2 * t)])
            worst = np.maximum(worst, np.abs(got - truth))
        size = math.dist((-50, -30, -10), (160, 30, 40))  # the arm's bounding box as built
        # Within the tolerance at the checked points; between them, within half as much again.
        self.assertLess(worst[0], math.degrees(mechanism.ANGULAR_TOLERANCE) * 1.5)
        self.assertLess(worst[1], mechanism.LINEAR_TOLERANCE * size * 1.5)
        first = self.xbf.read_bytes()
        self.assertEqual(self.cold(), first, "the same code samples at the same times: the same bytes")

    def test_a_function_with_kinks_is_kept_within_the_tolerance_at_its_kinks_too(self) -> None:
        # A zigzag: straight runs meeting at kinks every 0.685 s, none on the sampler's grid. Its
        # error is largest at a kink, between any two check points.
        zigzag = lambda t: 40 + 60 * 2 * abs(t / 1.37 - math.floor(t / 1.37 + 0.5))  # noqa: E731
        self.arm(more='configuration_sequence(arm, "zigzag", lambda t: {"elbow": 40 + 60 * 2 * abs(t / 1.37 - math.floor(t / 1.37 + '
                      '0.5))}, duration=6)')
        keys = document.Loaded(self.xbf).mechanism.motions["zigzag"].keys
        times = np.array([t for t, _name, _values in keys])
        table = np.array([[values["elbow"][0]] for _t, _name, values in keys])
        kinks = [0.685 * k for k in range(1, 9) if 0.685 * k < 6]
        checked = sorted({*np.linspace(0, 6, 6001).tolist(), *kinks})
        worst = max(abs(float(mechanism._interpolated(times, table, "linear", t)[0]) - zigzag(t)) for t in checked)
        self.assertLessEqual(worst, math.degrees(mechanism.ANGULAR_TOLERANCE), "the samples hold the tolerance everywhere")
        self.assertLess(len(times), 200)

    def test_a_warm_edit_of_a_motion_patches_the_document_to_the_cold_bytes(self) -> None:
        self.arm()
        report = self.arm(reach=90)
        self.assertTrue(report["converted"]["patched"], report["converted"])
        self.assertEqual(report["converted"]["converted"], 0, "a motion edit converts no prototype")
        self.assertEqual(document.Loaded(self.xbf).mechanism.motions["wave"].keys[-1], (2.0, None, {"elbow": (90.0,)}))
        warm = self.xbf.read_bytes()
        self.assertEqual(self.cold(reach=90), warm)
        # A motion removed leaves nothing of itself: the warm file is the cold one's again.
        self.arm(reach=90, nod=False)
        warm = self.xbf.read_bytes()
        self.assertNotIn("nod", document.Loaded(self.xbf).mechanism.motions)
        self.assertEqual(self.cold(reach=90, nod=False), warm)

    def test_what_a_motion_names_wrong_fails_or_warns_by_name(self) -> None:
        report = self.arm(ok=False, more='configuration_sequence(arm, "bad", [(0, "raised"), (1, "lowered")])')
        self.assertIn("names no mechanism state 'lowered'", report["error"])
        report = self.arm(ok=False, more='configuration_sequence(arm, "bad", sweep={"knee": (0, 1)}, duration=1)')
        self.assertIn("configuration sequence 'bad' of arm names no joint 'knee'", report["error"])
        report = self.arm(more='configuration_sequence(arm, "far", sweep={"elbow": (0, 200)}, duration=1)')
        self.assertTrue(any("configuration sequence 'far'" in text and "outside its range" in text and "left out" in text
                            for text in report["kinematics"]["warnings"]), report.get("kinematics"))
        self.assertNotIn("far", document.Loaded(self.xbf).mechanism.motions)

    def test_a_step_carries_no_motion(self) -> None:
        from cadgen.engine.export import translate

        self.arm()
        whole = self.folder / "whole.step"
        translate(self.xbf, None, whole)
        self.assertIsNone(document.Loaded(whole).mechanism, "STEP carries no mechanism and no motion")


MOVES = """
import json
import math
from pathlib import Path


def table(t):
    rows = json.loads((Path(__file__).parent / "table.json").read_text())
    return {"elbow": rows["base"] + 10 * math.sin(t)}
"""

HINGE = """
import build123d as bd
from cadgen.ap242 import configuration_sequence
from cadgen.engine import xbf
import moves


@xbf("XBF/hinge.xbf")
def hinge():
    base = bd.Box(100, 60, 20)
    arm = bd.Pos(40, 0, 25) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    base.label, arm.label = "base", "arm"
    elbow = bd.Axis((40, 0, 20), (0, 1, 0))
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("mount", arm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=0)
    hinge = bd.Compound(children=[base, arm], label="hinge")
    return configuration_sequence(hinge, "table", moves.table, duration=2)
"""


class MotionReadsTest(unittest.TestCase):
    """The files a function motion opens while it is sampled are the model's inputs
    (``memo.listened``): its closure holds them, so a change of one builds the model again, in
    a warm worker and after a restart alike."""

    def setUp(self) -> None:
        from unittest import mock

        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-motion-reads-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.xbf = self.folder / "XBF/hinge.xbf"
        memo.install()
        self.restart()
        self.addCleanup(self.restart)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for name in ("CADGEN_ENGINE_BODIES", "CADGEN_ENGINE_MEMO"):
            os.environ.pop(name, None)
        for name, text in (("moves.py", MOVES), ("hinge.py", HINGE)):
            (self.folder / name).write_text(textwrap.dedent(text), encoding="utf-8")
        self.table(40)

    def restart(self) -> None:
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()

    def table(self, base: float) -> None:
        path = self.folder / "table.json"
        path.write_text(json.dumps({"base": base}), encoding="utf-8")
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def hinge(self, *, verify: bool = False) -> dict:
        [report] = engine_build.build(self.folder / "hinge.py", ["hinge"], cwd=self.folder, verify=verify)
        self.assertTrue(report["ok"], report)
        return report

    def first(self) -> float:
        return document.Loaded(self.xbf).mechanism.motions["table"].keys[0][2]["elbow"][0]

    def test_a_file_a_motion_reads_changed_builds_the_model_again(self) -> None:
        self.assertEqual(self.hinge()["cache"]["reason"], "no file yet")
        self.assertIn(["read", "../table.json"], [row[:2] for row in document.Loaded(self.xbf).closure["inputs"]])
        self.assertEqual(self.hinge()["cache"], {"used": True, "from": "memory"})
        self.table(45)
        report = self.hinge()
        self.assertEqual(report["cache"]["reason"], "../table.json changed")
        self.assertEqual((report["bodies"], report["harvest"]), ({"hinge.py::hinge": "replayed"}, "run"),
                         "the body replayed, and its harvest is not reused: a file its function read changed")
        self.assertEqual(self.first(), 45.0, "sampled again, from the file as it is")
        self.restart()
        self.assertEqual(self.hinge()["cache"], {"used": True, "from": "file"})
        self.table(50)
        self.assertEqual(self.hinge()["cache"]["reason"], "../table.json changed")
        self.assertEqual(self.first(), 50.0)

    def test_a_verifying_build_runs_the_body_and_samples_as_ever(self) -> None:
        self.hinge()
        report = self.hinge(verify=True)
        self.assertEqual((report["cache"]["reason"], report["verify"]["checked"]), ("verifying", {"hinge.py::hinge": "same"}))
        self.assertNotIn("motions", report["verify"])
        self.assertNotIn("motions", report)
        self.assertEqual(self.first(), 40.0)


KEPT_MOVES = """
import math


def nod(t):
    return {{"elbow": 45 + {amplitude} * math.sin(t)}}


def unused():
    return {unused}
"""

KEPT = """
import build123d as bd
from cadgen import glb, xbf
from cadgen.ap242 import configuration_sequence
from cadgen.gltf import animation
import moves


@xbf("XBF/hinge.xbf")
@glb("GLB/hinge.glb")
def hinge():
    base = bd.Box(100, 60, 20)
    arm = bd.Pos(40, 0, 25) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
    cap = bd.Pos(-40, 0, 10 + {height} / 2) * bd.Box(10, 10, {height})
    base.label, arm.label, cap.label = "base", "arm", "{cap}"
    elbow = bd.Axis((40, 0, 20), (0, 1, 0))
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("mount", arm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=0)
    hinge = bd.Compound(children=[base, arm{cap_child}], label="hinge")
    configuration_sequence(hinge, "nod", moves.nod, duration=2)
    animation(hinge, "lift", duration=2).translation("{target}", by=(0, 0, 30))
    return hinge
"""


class HarvestKeptTest(unittest.TestCase):
    """A replayed model body's harvest -- its mechanism, its sequences' samples, its animations --
    is the one kept beside the body's run, not sampled again (``memo.harvest_of``), and what it
    writes is what a fresh harvest writes; an edit the body sees, or a file its functions read,
    harvests again."""

    def setUp(self) -> None:
        from unittest import mock

        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-harvest-kept-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.xbf, self.glb = self.folder / "XBF/hinge.xbf", self.folder / "GLB/hinge.glb"
        memo.install()
        for clear in (memo.clear, engine_build._WRITTEN.clear, engine_build._PARTS.clear):
            clear()
            self.addCleanup(clear)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for name in ("CADGEN_ENGINE_BODIES", "CADGEN_ENGINE_MEMO"):
            os.environ.pop(name, None)

    def write(self, *, amplitude: int = 20, unused: int = 0, height: int = 10, cap: str = "cap",
              target: str = "cap", placed: bool = True) -> None:
        for name, text in (("moves.py", KEPT_MOVES.format(amplitude=amplitude, unused=unused)),
                           ("hinge.py", KEPT.format(height=height, cap=cap, target=target,
                                                    cap_child=", cap" if placed else ""))):
            path = self.folder / name
            path.write_text(textwrap.dedent(text), encoding="utf-8")
            os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def build(self, ok: bool = True, **values: Any) -> dict:
        """The hinge built with its files gone, so a body the memo holds is replayed and they are
        written again (a model with no xbf replays every build: tom)."""
        self.write(**values)
        for path in (self.xbf, self.glb):
            path.unlink(missing_ok=True)
        [report] = engine_build.build(self.folder / "hinge.py", ["hinge"], cwd=self.folder)
        self.assertEqual(report["ok"], ok, report)
        return report

    def written(self) -> tuple[bytes, bytes, dict]:
        structure = engine_build.held(self.folder / "hinge.py", "hinge").structure
        return self.xbf.read_bytes(), self.glb.read_bytes(), {name: value for name, value in structure.items()
                                                                if name != "version"}

    def test_a_replay_reuses_the_harvest_and_writes_the_cold_builds_bytes(self) -> None:
        report = self.build()
        self.assertEqual((report["bodies"], report["harvest"]), ({"hinge.py::hinge": "run"}, "run"))
        cold = self.written()
        report = self.build()
        self.assertEqual((report["bodies"], report["harvest"], report["cache"]["reason"]),
                         ({"hinge.py::hinge": "replayed"}, "reused", "replayed from memory; the harvest reused"))
        self.assertEqual(self.written(), cold, "the xbf, the GLB and the served structure are the fresh harvest's")
        nod = document.Loaded(self.xbf).mechanism.motions["nod"].keys

        # An edit the body does not reach: replayed, and the harvest is reused.
        self.assertEqual(self.build(unused=1)["harvest"], "reused")
        self.assertEqual(self.written(), cold)
        # An edit of the sequence's function, in the module it is defined in: sampled again.
        report = self.build(amplitude=30)
        self.assertEqual((report["bodies"], report["harvest"]), ({"hinge.py::hinge": "run"}, "run"))
        self.assertNotEqual(document.Loaded(self.xbf).mechanism.motions["nod"].keys, nod, "the new function's samples")
        self.assertEqual(self.build(amplitude=30)["harvest"], "reused")

    def test_an_edit_of_a_part_an_animation_moves_harvests_again(self) -> None:
        self.build()
        lift = document.Loaded(self.xbf).animations["lift"]
        _xbf, glb, _structure = self.written()
        # Its geometry, its path the same: the body runs and harvests again; the track is the
        # same, and the GLB its new geometry's.
        report = self.build(height=14)
        self.assertEqual((report["bodies"], report["harvest"]), ({"hinge.py::hinge": "run"}, "run"))
        self.assertEqual(document.Loaded(self.xbf).animations["lift"], lift)
        self.assertNotEqual(self.glb.read_bytes(), glb)
        # Renamed, the animation following it: harvested again, the track named anew.
        self.assertEqual(self.build(height=14, cap="lid", target="lid")["harvest"], "run")
        renamed = document.Loaded(self.xbf).animations["lift"]
        self.assertEqual([track.groups for track in renamed.tracks], [track.groups for track in lift.tracks])
        self.assertIn("'lid'", renamed.tracks[0].label)
        # Removed, the animation still naming it: harvested again, and refused by name.
        report = self.build(False, height=14, placed=False)
        self.assertIn("has no part or assembly cap", report["error"])


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


def _linear(times: np.ndarray, rows: np.ndarray, t: float, rotation: bool) -> np.ndarray:
    """glTF's LINEAR at ``t``, as a viewer evaluates it: a lerp, a rotation's slerp."""
    at = max(0, min(int(np.searchsorted(times, t, side="right")) - 1, len(times) - 2))
    s = min(1.0, max(0.0, (t - times[at]) / (times[at + 1] - times[at])))
    a, b = rows[at], rows[at + 1]
    if not rotation:
        return a + s * (b - a)
    b = -b if float(np.dot(a, b)) < 0 else b
    theta = math.acos(min(1.0, float(np.dot(a, b))))
    return a if theta < 1e-9 else (math.sin((1 - s) * theta) * a + math.sin(s * theta) * b) / math.sin(theta)


def _rotation(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def deviations(glb: Path, structure: dict, rate: int = 240) -> dict[str, tuple[int, float, float]]:
    """Each clip of ``glb`` sampled ``rate`` times a second, against forward kinematics through
    the document's mechanism at those times: its most keys on a channel, its worst origin (mm) and
    its worst rotation (radians) apart."""
    gltf, read = _glb(glb)
    kinematics = structure["kinematics"]
    instances = {instance["path"]: at for at, instance in enumerate(structure["instances"])}
    root = structure["tree"]["name"]
    found = {}
    for animation in gltf["animations"]:
        timeline = mechanism.Timeline(kinematics, animation["name"])
        duration = animation["extras"]["cadgen"]["duration"]
        truths = {}
        worst = [0.0, 0.0]
        most = 0
        for channel in animation["channels"]:
            node = gltf["nodes"][channel["target"]["node"]]
            index = instances[f"{root}/{node['name']}"]
            sampler = animation["samplers"][channel["sampler"]]
            times = read(sampler["input"])[:, 0]
            rows = read(sampler["output"])
            most = max(most, len(times))
            for t in np.append(np.arange(0.0, duration, 1 / rate), duration):
                t = float(t)
                if t not in truths:
                    truths[t] = mechanism.posed_instances(structure, timeline.values(t))
                truth = np.array(truths[t][index]).reshape(4, 4).T
                got = _linear(times, rows, t, channel["target"]["path"] == "rotation")
                if channel["target"]["path"] == "translation":
                    worst[0] = max(worst[0], float(np.linalg.norm(got - truth[:3, 3])))
                else:
                    turned = _rotation(got).T @ truth[:3, :3]
                    worst[1] = max(worst[1], math.acos(max(-1.0, min(1.0, (np.trace(turned) - 1) / 2))))
        found[animation["name"]] = (most, worst[0], worst[1])
    return found


class GlbTest(_Folder):
    def test_a_glb_bakes_every_motion_into_a_clip_within_the_tolerance_of_forward_kinematics(self) -> None:
        from cadgen.engine.export import translate

        self.arm()
        out = self.folder / "arm.glb"
        translate(self.xbf, None, out)
        gltf, read = _glb(out)
        structure = document.Loaded(self.xbf).structure()
        self.assertEqual([animation["name"] for animation in gltf["animations"]], ["lift", "nod", "wave"])
        nodes = {node["name"]: node for node in gltf["nodes"][1:]}
        self.assertIn("matrix", nodes["base"], "a placement no motion moves stands by its matrix")
        for name in ("link", "tip"):
            self.assertNotIn("matrix", nodes[name], "an animated node stands by translation and rotation")
            self.assertEqual(len(nodes[name]["rotation"]), 4)
        for animation in gltf["animations"]:
            self.assertEqual(len(animation["channels"]), 4, "translation and rotation of the link and the tip")
            for channel in animation["channels"]:
                sampler = animation["samplers"][channel["sampler"]]
                self.assertEqual(sampler["interpolation"], "LINEAR", "the bake's keys, thinned to lines (export/keys.py)")
                output = gltf["accessors"][sampler["output"]]
                self.assertEqual(output["count"], gltf["accessors"][sampler["input"]]["count"], "a value per key")
                self.assertEqual(output["type"], {"translation": "VEC3", "rotation": "VEC4"}[channel["target"]["path"]])
                times = read(sampler["input"])[:, 0]
                self.assertTrue(np.all(np.diff(times) > 0))
                self.assertEqual(gltf["accessors"][sampler["input"]]["min"][0], 0.0)
                self.assertAlmostEqual(float(times[-1]), animation["extras"]["cadgen"]["duration"], places=5)
        extras = {animation["name"]: animation["extras"]["cadgen"] for animation in gltf["animations"]}
        self.assertEqual(extras, {"lift": {"duration": 3.0}, "nod": {"duration": 6.0}, "wave": {"duration": 2.0}})
        self.assertAlmostEqual(read(gltf["animations"][2]["samplers"][0]["input"])[-1, 0], 2.0, places=5,
                               msg="a clip is the motion once: a player repeats it")
        size = math.dist((-50, -30, -10), (160, 30, 40))
        found = deviations(out, structure)
        for name, (keys, linear, angular) in found.items():
            self.assertLess(keys, 200, name)
            # Within the bake's tolerance at its checks, half as much again between them, and the keys'
            # tenth of a millimetre and of a degree of the bake.
            self.assertLess(linear, mechanism.LINEAR_TOLERANCE * size * 1.5 + KEY_MM, (name, found))
            self.assertLess(angular, mechanism.ANGULAR_TOLERANCE * 1.5 + math.radians(KEY_DEGREES), (name, found))
        self.assertLess(found["wave"][0], found["nod"][0], "few keys where the motion is simple")
        again = self.folder / "again.glb"
        translate(self.xbf, None, again)
        self.assertEqual(again.read_bytes(), out.read_bytes(), "the same document bakes the same bytes")

    def test_a_clip_samples_with_the_frames_worked_out_once_and_its_quaternions_stacked(self) -> None:
        """The bake's inner loop: a sample is each link's pair motion and the products along the
        chain -- no frame read or inverted again (``mechanism.LinkWorlds``) -- and every moving
        placement's quaternion one stack (``motion.quaternions``), the same numbers, bit for bit, as
        worked out link by link and placement by placement."""
        from unittest import mock

        from cadgen.engine.export import Source, motion

        self.arm()
        view = Source.read(self.xbf).view()
        kinematics = view.source.structure["kinematics"]
        for name in kinematics["motions"]:
            moving = motion._Motion(view, name, [placed.instance for placed in view.placements])
            for t in np.linspace(0.0, moving.timeline.duration, 7):
                values = moving.timeline.values(float(t))
                with mock.patch.object(mechanism, "_from_column", side_effect=AssertionError("a frame read again")):
                    worlds = moving.worlds(values)
                    translations, rotations = moving.at(float(t))
                for got, want in zip(worlds, _link_worlds(kinematics, values), strict=True):
                    self.assertTrue(np.array_equal(got, want), (name, t))
                for at, index in enumerate(moving.instances):
                    link = moving.owner[index]
                    matrix = worlds[link] @ moving.unrest[link] @ moving.base[index]
                    self.assertTrue(np.array_equal(translations[at], matrix[:3, 3]), (name, t))
                    self.assertTrue(np.array_equal(rotations[at], _quaternion(matrix)), (name, t))
        # Every branch of the stacked quaternion (the trace's and each diagonal's), as one matrix's.
        turns = [np.eye(4)]
        for axis in range(3):
            for degrees in (10.0, 179.0, -170.0, 90.0):
                turns.append(mechanism._rotation(axis, degrees) @ mechanism._rotation((axis + 1) % 3, degrees / 3))
        stacked = motion.quaternions(np.array(turns))
        for turn, got in zip(turns, stacked, strict=True):
            self.assertTrue(np.array_equal(got, _quaternion(turn)))

    def test_a_glb_keeps_its_clips_and_the_other_exports_ignore_motions(self) -> None:
        from cadgen.engine.export import translate

        self.arm()
        moved = self.folder / "moved.glb"
        translate(self.xbf, None, moved)
        self.assertEqual([animation["name"] for animation in _glb(moved)[0]["animations"]], ["lift", "nod", "wave"])
        moving = {kind: self.folder / f"moving{suffix}" for kind, suffix in (("stl", ".stl"), ("threemf", ".3mf"))}
        for path in moving.values():
            translate(self.xbf, None, path)
        self.arm(motions=False)
        still = self.folder / "still.glb"
        translate(self.xbf, None, still)
        self.assertNotIn("animations", _glb(still)[0], "no motion, no animation")
        for kind, path in moving.items():
            other = self.folder / f"still{path.suffix}"
            translate(self.xbf, None, other)
            self.assertEqual(other.read_bytes(), path.read_bytes(), f"a {kind} is the same with motions or without")

    def test_neither_export_nor_glb_takes_an_animation_argument(self) -> None:
        import inspect

        from cadgen.engine import api
        from cadgen.engine.export import translate

        for function in (translate, api.export, api.Document.export):
            self.assertNotIn("animate", inspect.signature(function).parameters, function)
        import contextlib
        import io

        from cadgen.engine import cli

        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.build_parser().parse_args(["export", "a.xbf", "a.glb", "--animate", "x"])


def _quaternion(matrix: np.ndarray) -> np.ndarray:
    """A rotation matrix's quaternion one at a time, as the bake took them before it stacked them."""
    m = matrix[:3, :3]
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = np.array([0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = np.array([(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = np.array([(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s])
    q /= np.linalg.norm(q)
    return -q if q[3] < 0 else q


def _link_worlds(kinematics: dict, values: dict) -> list[np.ndarray]:
    """Each link's placement worked out from the structure at every call, as the bake did before
    ``mechanism.LinkWorlds`` kept its frames."""
    links = kinematics["links"]
    read = mechanism._from_column
    found: list[Any] = [None] * len(links)
    found[kinematics["ground"]] = read(links[kinematics["ground"]]["matrix"])
    pending = [pair for pair in kinematics["pairs"] if pair.get("frames")]
    progress = True
    while pending and progress:
        progress = False
        for pair in list(pending):
            first, second = pair["links"]
            if pair["label"] not in values:
                item_1, item_2 = np.linalg.inv(read(links[first]["matrix"])), np.linalg.inv(read(links[second]["matrix"]))
                moved = np.eye(4)
            else:
                item_1, item_2 = (read(frame) for frame in pair["frames"])
                moved = mechanism.pair_motion(pair["type"], values[pair["label"]])
            if found[first] is not None and found[second] is None:
                found[second] = found[first] @ item_1 @ moved @ np.linalg.inv(item_2)
            elif found[second] is not None and found[first] is None:
                found[first] = found[second] @ item_2 @ np.linalg.inv(moved) @ np.linalg.inv(item_1)
            elif found[first] is None:
                continue
            pending.remove(pair)
            progress = True
    return [matrix if matrix is not None else read(links[at]["matrix"]) for at, matrix in enumerate(found)]


if __name__ == "__main__":
    unittest.main()
