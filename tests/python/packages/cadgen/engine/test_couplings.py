"""Couplings: ``gear_pair``, ``rack_and_pinion_pair`` and ``screw_pair(assembly, name,
**joints)``, each a constraint moving joints by ratio from the as-built pose, their only way to
move, named after the AP242 pair it is written as. Validated by name, a joint of a kind the pair
does not relate refused; its range derived from its joints' limits; kept in the document's
mechanism as AP242's couplers (``:6 "couplings"``: gear and rack-and-pinion couplers, a screw pair)
and read back identically; served in the structure's ``kinematics.couplings``; forward kinematics
at a coupling's value the joints set by hand, in the sampler, a snapshot's ``--pose`` and a
``posed`` model; a door's
turn and travel from one screw pair; mechanism states and configuration sequences naming a coupling
resolved to pair values at document time; a warm edit patched to the cold build's bytes, the
elements' names unchanged."""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine import build as engine_build
from cadgen.engine import document, mechanism
from tests.python.support import opengl

# The spec's finger: four bones along +X, a knuckle across each joint between two, straight as
# built, and one control curling all three knuckles.
FINGER = """
import build123d as bd
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state, rack_and_pinion_pair, screw_pair
from cadgen.engine import xbf

CURL = {{"index_mcp_flexion": 90, "index_pip": 100, "index_dip": 70}}  # degrees at a full curl
BONES = {{"base": 30, "proximal": 40, "middle": 25, "distal": 20}}  # lengths along +X


@xbf("XBF/index_finger.xbf")
def index_finger():
    bones, x = [], -BONES["base"]
    for name, length in BONES.items():
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label = name
        bones.append(bone)
        x += length
    for joint, parent, child in zip(CURL, bones, bones[1:]):
        knuckle = bd.Axis(child.location.position, (0, 1, 0))
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)  # as built: straight
    finger = bd.Compound(children=bones, label="index_finger")
    {coupling}
    {extra}
    return configuration_sequence(finger, "grip", sweep={{"index_curl": (0, 1)}}, duration=1.5)
"""
CURL = 'gear_pair(finger, "index_curl", **CURL)'
RATIOS = {"index_mcp_flexion": 90, "index_pip": 100, "index_dip": 70}  # the finger's, at a full curl
BY_HAND = {"index_mcp_flexion": 54, "index_pip": 60, "index_dip": 42}  # its joints at index_curl 0.6
# The finger with no coupling, nor the motion naming it: its joints are posed by hand.
BARE = FINGER.format(coupling="return finger", extra="")

# The spec's hypercar door: a helical hinge, a cylindrical joint per side, a screw pair turning
# and sliding each door.
HYPERCAR = """
import build123d as bd
from cadgen.ap242 import gear_pair, mechanism_state, screw_pair
from cadgen.engine import xbf

SWEEP = {"left": -70, "right": 70}  # each door's turn when open, degrees
TRAVEL = 40  # and its travel along the hinge, mm


@xbf("XBF/hypercar.xbf")
def hypercar():
    chassis = bd.Box(4400, 900, 400, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    chassis.label = "chassis"
    doors = []
    for side, y in (("left", 475), ("right", -475)):
        door = bd.Pos(400, y, 500) * bd.Box(1000, 50, 600)
        door.label = f"door_{side}"
        hinge = bd.Axis((800, 450 if side == "left" else -450, 500), (0.3, 0, 1))  # a helical hinge
        bd.CylindricalJoint(f"door_{side}", chassis, axis=hinge, angular_range=tuple(sorted((0, SWEEP[side]))),
                            linear_range=(0, TRAVEL))
        bd.RigidJoint(f"door_{side}", door, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
        chassis.joints[f"door_{side}"].connect_to(door.joints[f"door_{side}"], angle=0, position=0)  # shut
        doors.append(door)
    car = bd.Compound(children=[chassis, *doors], label="hypercar")
    screw_pair(car, "left", door_left=360 * TRAVEL / SWEEP["left"])  # its pitch: travel per turn
    screw_pair(car, "right", door_right=360 * TRAVEL / SWEEP["right"])
    return mechanism_state(car, "open", left=SWEEP["left"], right=SWEEP["right"])  # shut is as built
"""

# A gear train: three wheels on a plate, one coupling turning them at fixed ratios.
TRAIN = """
import build123d as bd
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state
from cadgen.engine import xbf

RATIOS = {{"sun": 1.0, "idler": -2.0, "ring": 0.5}}


@xbf("XBF/train.xbf")
def train():
    plate = bd.Box(200, 60, 5, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MAX))
    plate.label = "plate"
    wheels = []
    for at, name in enumerate(RATIOS):
        centre = (30 + 60 * at, 0, 0)
        wheel = bd.Pos(*centre) * bd.Cylinder(20, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        wheel.label = name
        bd.RevoluteJoint(name, plate, axis=bd.Axis(centre, (0, 0, 1)), angular_range=(-720, 720))
        bd.RigidJoint(name, wheel, bd.Plane(origin=centre, z_dir=(0, 0, 1)).location)
        plate.joints[name].connect_to(wheel.joints[name], angle=0)
        wheels.append(wheel)
    train = bd.Compound(children=[plate, *wheels], label="train")
    gear_pair(train, "drive", **RATIOS)
    mechanism_state(train, "quarter", drive=90)
    {extra}
    return configuration_sequence(train, "run", sweep={{"drive": (0, 360)}}, duration=4, ease="linear")
"""

# Two fingers, one function's: each placement's joints and coupling labelled alike.
HAND = """
import build123d as bd
from cadgen.ap242 import gear_pair, mechanism_state
from cadgen.engine import xbf


def finger(name):
    bones, x = [], 0
    for bone_name, length in (("proximal", 40), ("middle", 25), ("distal", 20)):
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label = bone_name
        bones.append(bone)
        x += length
    for joint, parent, child, at in (("pip", bones[0], bones[1], 40), ("dip", bones[1], bones[2], 65)):
        knuckle = bd.Axis((at, 0, 0), (0, 1, 0))
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, 100))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)
    found = bd.Compound(children=bones, label=name)
    return gear_pair(found, "curl", pip=100, dip=70)


@xbf("XBF/hand.xbf")
def hand():
    palm = bd.Box(10, 60, 12, align=(bd.Align.MAX, bd.Align.CENTER, bd.Align.CENTER))
    palm.label = "palm"
    hand = bd.Compound(children=[palm, finger("index"), bd.Pos(0, 20, 0) * finger("middle")], label="hand")
    return mechanism_state(hand, "fist", curl=1)
"""


def _vertices(loaded: document.Loaded, name: str, pose: Any = None) -> np.ndarray:
    """Every vertex of the instance named ``name``, where the document places it, or where
    ``pose`` does (``mechanism.posed_structure``, as the viewer and the snapshot pose it)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    index, instance = next((at, i) for at, i in enumerate(loaded.instances) if i.path[-1] == name)
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(loaded.prototypes[instance.prototype].shape, TopAbs_VERTEX, mapped)
    matrix = np.array(instance.matrix if pose is None else
                      mechanism.posed_structure(loaded.structure(), pose)["instances"][index]["matrix"]).reshape(4, 4).T
    points = [BRep_Tool.Pnt_s(TopoDS.Vertex_s(mapped.FindKey(at))) for at in range(1, mapped.Extent() + 1)]
    return np.array(sorted((matrix @ np.array([p.X(), p.Y(), p.Z(), 1.0]))[:3].tolist() for p in points))


def _couplers(loaded: document.Loaded) -> dict[str, list[tuple]]:
    """Each coupling's couplers in the document's subtree, by the coupling's name: entity, kind,
    ratios (or a screw's pitch), value types and the pairs it references, by name."""
    from OCP.Standard import Standard_GUID

    root = next(label for label in mechanism._children_of(loaded.doc.Main())
                if label.IsAttribute(Standard_GUID(mechanism.GUID)))
    top = root.FindChild(1, False)
    pairs = {document._entry(label): document._label_name(label)
             for label in mechanism._children_of(top.FindChild(2, False))}
    found = {}
    for held in mechanism._children_of(top.FindChild(6, False)):
        rows = []
        for label in mechanism._children_of(held):
            data = mechanism._named(label)
            entity = mechanism._string(data, "entity")
            scales = (mechanism._real(data, "pitch") if entity == mechanism.SCREW
                      else mechanism._array(data, "CouplingRatios"))
            rows.append((entity, mechanism._string(data, "Kind"), scales, mechanism._string(data, "CouplingTypes"),
                         [pairs[entry] for entry in mechanism._references(label)]))
        found[document._label_name(held)] = rows
    return found


# The finger posed by a model of its own: a posed file is a function, never an export's option.
POSED = """
from cadgen.ap242 import posed
from cadgen.engine import xbf
from index_finger import index_finger


@xbf("XBF/posed_finger.xbf")
def posed_finger():
    return posed(index_finger().shape, {pose})
"""


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-couplings-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        memo.install()
        self.addCleanup(memo.clear)

    def build(self, name: str, source: str, *, ok: bool = True) -> dict:
        script = self.folder / f"{name}.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, [name], cwd=self.folder)[0]
        self.assertEqual(report["ok"], ok, report)
        return report

    def finger(self, coupling: str = CURL, extra: str = "pass", ok: bool = True) -> dict:
        return self.build("index_finger", FINGER.format(coupling=coupling, extra=extra), ok=ok)

    def cold(self, name: str, source: str) -> bytes:
        """The model built by a process that never built it: its xbf's bytes."""
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        (self.folder / f"XBF/{name}.xbf").unlink()
        self.assertFalse(self.build(name, source)["converted"]["patched"])
        return (self.folder / f"XBF/{name}.xbf").read_bytes()


class AuthoringTest(unittest.TestCase):
    def test_each_pair_says_what_is_wrong_by_name_and_returns_the_assembly(self) -> None:
        import build123d as bd

        from cadgen.ap242 import gear_pair, rack_and_pinion_pair, screw_pair

        box = bd.Box(1, 1, 1)
        for call, error in (
                (lambda: gear_pair("arm", "c", j=1, k=1), "gear_pair\\(\\) takes the assembly"),
                (lambda: gear_pair(box, " ", j=1, k=1), "a gear pair's name is a non-empty string"),
                (lambda: gear_pair(box, "c"), "gear pair 'c' drives no joint"),
                (lambda: gear_pair(box, "c", j=1), "gear pair 'c' drives 'j' alone; it relates two joints or more"),
                (lambda: gear_pair(box, "c", j="x", k=1), "joint 'j' takes a ratio"),
                (lambda: gear_pair(box, "c", j=float("nan"), k=1), "joint 'j' takes a ratio"),
                (lambda: gear_pair(box, "c", j=(1, 2), k=1), "joint 'j' takes a ratio, a number"),
                (lambda: gear_pair(box, "c", j=0, k=1), "joint 'j' has no ratio but 0"),
                (lambda: rack_and_pinion_pair(box, "c", j=1), "rack and pinion pair 'c' drives 'j' alone"),
                (lambda: rack_and_pinion_pair(box, "c", j=1, k=(1, 2)), "joint 'k' takes a ratio, a number"),
                (lambda: screw_pair("arm", "c", j=1), "screw_pair\\(\\) takes the assembly"),
                (lambda: screw_pair(box, "c", j=(1, 1)), "joint 'j' takes its pitch, the millimetres it travels"),
                (lambda: screw_pair(box, "c", j=0), "joint 'j' has a pitch 0"),
                (lambda: screw_pair(box, "c", j=1, k=1), "screw pair 'c' drives one cylindrical joint")):
            with self.assertRaisesRegex((TypeError, ValueError), error):
                call()
        self.assertIs(gear_pair(box, "c", j=2, k=-1), box)
        self.assertIs(rack_and_pinion_pair(box, "r", j=1, k=0.5), box)
        self.assertIs(screw_pair(box, "s", j=90), box)
        self.assertEqual(box.__dict__[mechanism.COUPLINGS], {"c": ("gear_pair", {"j": (2.0,), "k": (-1.0,)}),
                                                             "r": ("rack_and_pinion_pair", {"j": (1.0,), "k": (0.5,)}),
                                                             "s": ("screw_pair", {"j": (1.0, 0.25)})})

    def test_a_coupling_s_range_is_the_tightest_its_joints_limits_allow(self) -> None:
        pairs = {"a": mechanism.Pair("a", "revolute", (0, 1), None, ((-30.0, 60.0),)),
                 "b": mechanism.Pair("b", "prismatic", (0, 2), None, ((0.0, 100.0),)),
                 "free": mechanism.Pair("free", "revolute", (0, 3), None, ((None, None),)),
                 "door": mechanism.Pair("door", "cylindrical", (0, 4), None, ((None, None), (None, 40.0)))}
        as_built = {"a": (10.0,), "b": (20.0,), "free": (0.0,), "door": (0.0, 10.0)}

        def derived(**ratios):
            return mechanism._derived_range(mechanism.Coupling("c", {k: tuple(v) for k, v in ratios.items()}),
                                            pairs, as_built)

        self.assertEqual(derived(a=[2], b=[1]), (-20.0, 25.0), "a's [-40, 50] over 2 within b's [-20, 80]")
        self.assertEqual(derived(a=[-2], b=[1]), (-20.0, 20.0), "a negative ratio turns a's limits round")
        self.assertEqual(derived(free=[1], b=[-1]), (-80.0, 20.0), "a joint with no limits bounds nothing")
        self.assertEqual(derived(free=[1], door=[1, 0]), (None, None), "nothing bounds it")
        self.assertEqual(derived(door=[0, 3], free=[1]), (None, 10.0), "a value with a ratio 0 bounds nothing")


class FingerTest(_Folder):
    XBF = "XBF/index_finger.xbf"

    def test_a_coupling_round_trips_through_the_xbf_and_is_served(self) -> None:
        report = self.finger()
        self.assertNotIn("kinematics", report, "no warning")
        path = self.folder / self.XBF
        loaded = document.Loaded(path)
        found = loaded.mechanism
        self.assertEqual(found.couplings, {"index_curl": mechanism.Coupling(
            "index_curl", {label: (float(ratio),) for label, ratio in RATIOS.items()})})
        self.assertEqual(found.as_built, {label: (0.0,) for label in RATIOS})
        # The motion sweeping the coupling is its joints' values, resolved at document time.
        self.assertEqual(found.motions["grip"].keys, [(0.0, None, {label: (0.0,) for label in RATIOS}),
                                                      (1.5, None, {label: (float(r),) for label, r in RATIOS.items()})])
        # The subtree: under :6 the coupling's couplers, two gear pairs from its first-named
        # joint, each s1 * d1 + s2 * d2 = 0 over its two pairs' turns from as built.
        self.assertEqual(_couplers(loaded), {"index_curl": [
            ("KinematicPairWithMotionCoupling", "gear_pair", (100.0, -90.0), "rotation,rotation",
             ["index_mcp_flexion", "index_pip"]),
            ("KinematicPairWithMotionCoupling", "gear_pair", (70.0, -90.0), "rotation,rotation",
             ["index_mcp_flexion", "index_dip"])]})
        # The structure serves it, its range its joints' limits, the same from the file as from the build's tree.
        block = loaded.structure()["kinematics"]
        self.assertEqual(block["couplings"], {"index_curl": {"range": [0.0, 1.0], "terms": [
            [label, 0, float(ratio)] for label, ratio in RATIOS.items()]}})
        self.assertEqual(block, document.tree_structure(document.saved(path), path)["kinematics"])

    def test_forward_kinematics_at_a_coupling_value_is_the_joints_set_by_hand(self) -> None:
        self.finger()
        path = self.folder / self.XBF
        structure = document.Loaded(path).structure()
        values, named = mechanism.resolve(structure["kinematics"], {"index_curl": 0.6})
        # The document's own values may set a coupling's joints (a motion's keys do).
        by_hand, _named = mechanism.resolve(structure["kinematics"], BY_HAND, own=True)
        self.assertIsNone(named)
        for label in RATIOS:
            self.assertAlmostEqual(values[label][0], by_hand[label][0], places=12)
        np.testing.assert_allclose(mechanism.posed_instances(structure, values),
                                   mechanism.posed_instances(structure, by_hand), atol=1e-9)
        # A posed model: the distal bone where the joints set by hand on the bare finger put it,
        # and moved from as built.
        self.build("posed_finger", POSED.format(pose='{"index_curl": 0.6}'))
        coupled = _vertices(document.Loaded(self.folder / "XBF/posed_finger.xbf"), "distal")
        self.build("index_finger", BARE)
        np.testing.assert_allclose(coupled, _vertices(document.Loaded(path), "distal", BY_HAND), atol=1e-6)
        self.assertGreater(np.abs(coupled - _vertices(document.Loaded(path), "distal")).max(), 10.0)

    def test_what_a_coupling_pose_names_wrong_is_refused_by_name_before_anything_is_written(self) -> None:
        self.finger()
        out = self.folder / "XBF/posed_finger.xbf"
        for pose, words in (('{"index_curl": 1.5}', ["coupling 'index_curl' at 1.5 is outside its range [0, 1]"]),
                            ('{"index_pip": 10}',
                             ["joint 'index_pip' moves only with its coupling 'index_curl'; set 'index_curl'"]),
                            ('{"index_curl": 0.5, "index_pip": 10}',
                             ["joint 'index_pip' moves only with its coupling 'index_curl'"]),
                            ('{"index_curl": [0.5, 1]}', ["coupling 'index_curl' takes a number"]),
                            ('{"crul": 1}', ["names no joint 'crul'", "its couplings: index_curl"])):
            err = self.build("posed_finger", POSED.format(pose=pose), ok=False)["error"]
            for word in words:
                self.assertIn(word, err, pose)
            self.assertFalse(out.exists(), pose)

    def test_a_snapshot_draws_a_coupling_as_its_joints_set_by_hand(self) -> None:
        from cadgen.engine.render import context
        from cadgen.engine.snapshot import SnapshotRefused, snapshot

        self.finger()
        previous = os.environ.get("CADGEN_ENGINE_MESH")
        os.environ["CADGEN_ENGINE_MESH"] = "inline"  # one part at a time on this thread: no pool
        self.addCleanup(lambda: os.environ.pop("CADGEN_ENGINE_MESH") if previous is None
                        else os.environ.__setitem__("CADGEN_ENGINE_MESH", previous))
        path = self.folder / self.XBF
        out = self.folder / "stale.png"
        out.write_bytes(b"before")
        with self.assertRaisesRegex(SnapshotRefused, "--pose: .*coupling 'index_curl' at 2 is outside its range"):
            snapshot(path, out, pose={"index_curl": 2}, size=(160, 120), daemon=False)
        self.assertEqual(out.read_bytes(), b"before", "a refused snapshot keeps the picture at OUT")
        # The posed structure the picture is drawn from: every instance where the joints set by hand put it.
        structure = document.Loaded(path).structure()
        coupled = mechanism.posed_structure(structure, {"index_curl": 0.6})
        by_hand = mechanism.posed_instances(structure, mechanism.resolve(structure["kinematics"], BY_HAND,
                                                                         own=True)[0])
        np.testing.assert_allclose([i["matrix"] for i in coupled["instances"]], by_hand, atol=1e-9)
        opengl.require(context.available(), "the posed structure is checked; drawing it needs an OpenGL context")
        drawn = {}
        for name, pose in (("rest", None), ("coupled", {"index_curl": 0.6}), ("by_hand", BY_HAND)):
            if name == "by_hand":  # the bare finger, its joints set by hand
                self.build("index_finger", BARE)
            report = snapshot(path, self.folder / f"{name}.png", camera="front", size=(160, 120), daemon=False,
                              pose=pose)
            drawn[name] = (self.folder / f"{name}.png").read_bytes()
            if name == "coupled":
                self.assertAlmostEqual(report["pose"]["values"]["index_pip"], 60.0, places=9)
        self.assertEqual(drawn["coupled"], drawn["by_hand"], "the coupled picture is the joints set by hand")
        self.assertNotEqual(drawn["coupled"], drawn["rest"])

    def test_a_warm_edit_of_a_coupling_patches_to_the_cold_bytes_and_renames_nothing(self) -> None:
        path = self.folder / self.XBF
        without = BARE
        self.build("index_finger", without)
        bare = document.Loaded(path).structure()
        self.finger()
        names = document.Loaded(path).structure()
        self.assertEqual([(p["name"], p["faceNames"], p["edgeNames"]) for p in names["prototypes"]],
                         [(p["name"], p["faceNames"], p["edgeNames"]) for p in bare["prototypes"]],
                         "a coupling renames no element")
        edited = 'gear_pair(finger, "index_curl", index_mcp_flexion=80, index_pip=100, index_dip=70)'
        report = self.finger(coupling=edited)
        self.assertTrue(report["converted"]["patched"], report["converted"])
        self.assertEqual(report["converted"]["converted"], 0, "a coupling edit converts no prototype")
        self.assertEqual(document.Loaded(path).mechanism.couplings["index_curl"].ratios["index_mcp_flexion"], (80.0,))
        warm = path.read_bytes()
        self.assertEqual(self.cold("index_finger", FINGER.format(coupling=edited, extra="pass")), warm)
        # The coupling removed (the motion naming it with it): the warm file the cold one's.
        self.build("index_finger", without)
        warm = path.read_bytes()
        self.assertEqual(document.Loaded(path).mechanism.couplings, {})
        self.assertEqual(self.cold("index_finger", without), warm)


class DoorTest(_Folder):
    def test_a_screw_pair_turns_and_slides_a_cylindrical_joint(self) -> None:
        self.build("hypercar", HYPERCAR)
        loaded = document.Loaded(self.folder / "XBF/hypercar.xbf")
        found = loaded.mechanism
        self.assertEqual([(pair.label, pair.kind) for pair in found.pairs],
                         [("door_left", "cylindrical"), ("door_right", "cylindrical")])
        # A screw pair's value is its joint's turn: its travel moves by the pitch over 360.
        self.assertEqual({name: coupling.ratios for name, coupling in found.couplings.items()},
                         {"left": {"door_left": (1.0, 40.0 / -70.0)}, "right": {"door_right": (1.0, 40.0 / 70.0)}})
        # Each door's coupler: Part 105's screw pair, its pitch the travel per turn.
        self.assertEqual(_couplers(loaded), {
            "left": [("SCREW_PAIR", None, 360.0 * (360.0 * 40.0 / -70.0 / 360.0), None, ["door_left"])],
            "right": [("SCREW_PAIR", None, 360.0 * (360.0 * 40.0 / 70.0 / 360.0), None, ["door_right"])]})
        couplings = loaded.structure()["kinematics"]["couplings"]
        self.assertEqual([couplings[name]["range"] for name in ("left", "right")], [[-70.0, 0.0], [0.0, 70.0]])
        self.assertEqual(couplings, document.tree_structure(document.saved(self.folder / "XBF/hypercar.xbf"),
                                                            self.folder / "XBF/hypercar.xbf")["kinematics"]["couplings"],
                         "the same from the file as from the build's tree")
        # The mechanism state naming them holds their joints' values: the turn and the travel from shut.
        for label, turn in (("door_left", -70.0), ("door_right", 70.0)):
            np.testing.assert_allclose(found.configurations["open"][label], (turn, 40.0), atol=1e-9)
        kinematics = loaded.structure()["kinematics"]
        values, _named = mechanism.resolve(kinematics, {"left": -35, "right": 35})
        np.testing.assert_allclose(values["door_left"], (-35.0, 20.0), atol=1e-9)
        np.testing.assert_allclose(values["door_right"], (35.0, 20.0), atol=1e-9)
        car = self.folder / "XBF/hypercar.xbf"
        half = {door: _vertices(document.Loaded(car), door, {"left": -35, "right": 35})
                for door in ("door_left", "door_right")}
        # Its joint is posed through it alone; the car with no coupling poses them by hand.
        pose = {"door_left": [-35, 20], "door_right": [35, 20]}
        with self.assertRaisesRegex(mechanism.KinematicsError, "joint 'door_left' moves only with its coupling 'left'"):
            mechanism.resolve(kinematics, pose)
        self.build("hypercar", HYPERCAR.split("    screw_pair(car")[0] + "    return car\n")
        for door in ("door_left", "door_right"):
            np.testing.assert_allclose(half[door], _vertices(document.Loaded(car), door, pose), atol=1e-6)


class ConstraintTest(_Folder):
    def test_a_coupling_is_its_joints_only_way_to_move(self) -> None:
        report = self.build("train", TRAIN.format(extra='mechanism_state(train, "jammed", idler=10)'))
        self.assertIn("mechanism state 'jammed' of train: joint 'idler' moves only with its coupling 'drive'; "
                      "set 'drive': the value is left out", report["kinematics"]["warnings"])
        loaded = document.Loaded(self.folder / "XBF/train.xbf")
        coupler = "KinematicPairWithMotionCoupling"
        self.assertEqual(_couplers(loaded), {"drive": [
            (coupler, "gear_pair", (-2.0, -1.0), "rotation,rotation", ["sun", "idler"]),
            (coupler, "gear_pair", (0.5, -1.0), "rotation,rotation", ["sun", "ring"])]})
        # Its range: the idler's limits, turning twice as fast, bound it first.
        self.assertEqual(loaded.structure()["kinematics"]["couplings"]["drive"]["range"], [-360.0, 360.0])
        quarter = {"sun": (90.0,), "idler": (-180.0,), "ring": (45.0,)}
        self.assertEqual(loaded.mechanism.configurations["quarter"], quarter)
        kinematics = loaded.structure()["kinematics"]
        self.assertEqual(mechanism.resolve(kinematics, {"drive": 10})[0],
                         {"sun": (10.0,), "idler": (-20.0,), "ring": (5.0,)})
        with self.assertRaisesRegex(mechanism.KinematicsError, "joint 'idler' moves only with its coupling 'drive'"):
            mechanism.resolve(kinematics, {"idler": 5})
        # The document's own values pose it: a configuration, and the motion baked into a GLB.
        self.assertEqual(mechanism.resolve(kinematics, "quarter")[0]["ring"], (45.0,))
        timeline = mechanism.Timeline(kinematics, "run")
        self.assertEqual(timeline.values(1.0), quarter)
        from cadgen.engine.export import translate

        glb = self.folder / "train.glb"
        translate(self.folder / "XBF/train.xbf", None, glb)
        self.assertGreater(glb.stat().st_size, 0)

    def test_a_joint_two_couplings_drive_fails_the_build_by_name(self) -> None:
        report = self.build("train", TRAIN.format(extra='gear_pair(train, "trim", ring=1, sun=1)'), ok=False)
        self.assertIn("joint 'sun' is driven by the couplings 'drive' and 'trim': a coupling is a constraint",
                      report["error"])


class HarvestTest(_Folder):
    def test_a_coupling_naming_no_joint_or_named_as_one_fails_the_build_by_name(self) -> None:
        report = self.finger(extra='gear_pair(finger, "spread", knuckle=1, index_pip=1)', ok=False)
        self.assertIn("gear pair 'spread' of index_finger names no joint 'knuckle'; its joints are index_dip, "
                      "index_mcp_flexion, index_pip", report["error"])
        report = self.finger(extra='gear_pair(finger, "index_pip", index_mcp_flexion=1, index_dip=1)', ok=False)
        self.assertIn("gear pair 'index_pip' of index_finger has a joint's name", report["error"])
        report = self.finger(extra='mechanism_state(finger, "fist", crul=1)', ok=False)
        self.assertIn("mechanism state 'fist' of index_finger names no joint 'crul'", report["error"])
        self.assertIn("its couplings are index_curl", report["error"])

    def test_a_coupling_no_coupler_can_hold_fails_the_build_by_name(self) -> None:
        # Two joints pushed past their limits at once, either way.
        report = self.finger(extra='gear_pair(finger, "spread", index_pip=1, index_dip=-1)', ok=False)
        self.assertIn("gear pair 'spread' of index_finger: its joints' limits leave it no range around as built "
                      "([0, 0])", report["error"])

    def test_a_joint_its_pair_does_not_relate_fails_the_build_by_name(self) -> None:
        # Each function writes the pair it is named after, so a joint of another kind is refused.
        for extra, words in (
                ('rack_and_pinion_pair(finger, "r", index_pip=1, index_dip=1)',
                 "rack and pinion pair 'r' of index_finger drives 'index_pip' and 'index_dip', both revolute"),
                ('screw_pair(finger, "s", index_pip=2)',
                 "screw pair 's' of index_finger drives the revolute joint 'index_pip': a screw pair is a "
                 "cylindrical joint's turn and travel")):
            with self.subTest(extra=extra):
                report = self.finger(extra=extra, ok=False)
                self.assertIn(words, report["error"])
        report = self.build("hypercar", HYPERCAR.replace('screw_pair(car, "left", door_left=360 * TRAVEL / SWEEP["left"])',
                                                         'gear_pair(car, "left", door_left=1, door_right=1)'), ok=False)
        self.assertIn("gear pair 'left' of hypercar drives the cylindrical joint 'door_left': a gear pair turns "
                      "revolute joints", report["error"])

    def test_each_placement_s_coupling_is_kept_by_its_path_and_a_configuration_sets_them_all(self) -> None:
        self.build("hand", HAND)
        path = self.folder / "XBF/hand.xbf"
        found = document.Loaded(path).mechanism
        self.assertEqual(sorted(found.couplings), ["hand/index:curl", "hand/middle:curl"])
        index = found.couplings["hand/index:curl"]
        self.assertEqual(index.ratios, {"hand/index/proximal:pip": (100.0,), "hand/index/middle:dip": (70.0,)},
                         "its own placement's joints alone")
        self.assertEqual(found.configurations["fist"], {
            "hand/index/proximal:pip": (100.0,), "hand/index/middle:dip": (70.0,),
            "hand/middle/proximal:pip": (100.0,), "hand/middle/middle:dip": (70.0,)})
        kinematics = document.Loaded(path).structure()["kinematics"]
        values, _named = mechanism.resolve(kinematics, {"hand/index:curl": 0.5})
        self.assertEqual([values[label] for label in ("hand/index/proximal:pip", "hand/index/middle:dip",
                                                      "hand/middle/proximal:pip")], [(50.0,), (35.0,), (0.0,)])


if __name__ == "__main__":
    unittest.main()
