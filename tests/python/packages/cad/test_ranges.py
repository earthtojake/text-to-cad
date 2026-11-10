"""``cad.<type>.ranges``: each joint of a mechanism swept alone against the parts' surfaces.

A base with a wall, an arm on a hinge and a carriage on a slide, built to an xbf: the arm turns until it
meets the wall one way and the base the other, the carriage slides until it meets the wall one way and an end
stop the other (touching the base all along, as built, which stops nothing), each stop where an exact
distance says the parts come within the clearance; the document is not changed. A smaller clearance only
widens a range. A STEP with no joint has nothing to sweep: an error, said by code. An option out of range is
refused by name. The stops are said as a table, and a long sweep says each joint as
it starts and ends; a verbose one says each step as it starts. A pair near as built, its gap narrowing a hair as the
joint turns, stops nothing until it truly closes, and is reported with its gaps. A pair drawn one inside the other
stops nothing where its overlap shrinks or slides, only where it deepens, and is reported with its volume and
depth."""

from __future__ import annotations

import math
import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cad._internal.refused import ArgumentRefused

RIG = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/rig.xbf")
def rig():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    wall = bd.Pos(-40, 0, 40) * bd.Box(10, 60, 60)
    wall.label = "wall"
    end = bd.Pos(75, -25, 15) * bd.Box(10, 10, 10)
    end.label = "end_stop"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    carriage = bd.Box(10, 10, 10)
    carriage.label = "carriage"
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((0, 0, 30), (0, 1, 0)), angular_range=(-170, 170))
    bd.RigidJoint("mount", arm, bd.Location())
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=0)
    bd.LinearJoint("slide", base, axis=bd.Axis((0, -25, 15), (1, 0, 0)), linear_range=(-100, 100))
    bd.RigidJoint("seat", carriage, bd.Location())
    base.joints["slide"].connect_to(carriage.joints["seat"], position=40)
    return bd.Compound(children=[base, wall, end, arm, carriage], label="rig")
"""


# An arm on a hinge about Z, 0.4 mm over a plate tilted so that the gap narrows to 0.35 mm as the arm turns, and a
# wall it truly meets at about +58 degrees. The marker sets the grid's cells so that a cell boundary lies at -0.38 mm:
# the plate's top falls in the arm's cells only past y = 17 mm, which a count of points within the clearance read as
# contact growing.
NEAR = """
import math

import build123d as bd
from cad.engine import xbf


@xbf("XBF/near.xbf")
def near():
    tilt = math.degrees(math.atan(0.05 / 43))
    plate = bd.Pos(0, 0, -0.4) * bd.Rot(X=tilt) * bd.Pos(0, 0, -2.5) * bd.Box(120, 120, 5)
    plate.label = "plate"
    wall = bd.Pos(30, 49, 4.5) * bd.Box(60, 10, 11)
    wall.label = "wall"
    marker = bd.Pos(-55, -55, -9.88) * bd.Box(4, 4, 1)
    marker.label = "marker"
    base = bd.Compound(children=[plate, wall, marker], label="base")
    arm = bd.Box(45, 4, 4, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(5, 0, 0) * arm
    arm.label = "SOLID"  # a vendor's anonymous body, named in messages by its component
    upper = bd.Compound(children=[arm], label="Upper_arm v9")
    hinge = bd.RevoluteJoint("hinge", base, axis=bd.Axis((0, 0, 0), (0, 0, 1)), angular_range=(-360, 360))
    bd.RigidJoint("hinge", upper, hinge.location)
    hinge.connect_to(upper.joints["hinge"], angle=0)
    return bd.Compound(children=[base, upper], label="near")
"""


# A rail with a stop block on it and an end block off its end; a carriage 36 mm wide drawn sunk 1 mm into the rail's
# top over its last 5 mm (an overlap of 180 mm^3), sliding along it; and a pad sunk 1 mm into the rail's top
# (100 mm^3), sliding up and down. The carriage leaving the rail's end shrinks its overlap, and sliding on along the rail moves it: neither
# stops it, and it slides until it meets the end block one way and the stop block the other. The pad pushed down
# deepens its overlap, which stops it; lifted, it leaves the rail.
OVERLAP = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/overlap.xbf")
def overlap():
    rail = bd.Box(100, 60, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    rail.label = "rail"
    end = bd.Pos(-40, 0, 15) * bd.Box(10, 60, 30)
    end.label = "end_block"
    stop = bd.Pos(65, 0, 20) * bd.Box(10, 20, 20)
    stop.label = "stop_block"
    base = bd.Compound(children=[rail, end, stop], label="base")
    carriage = bd.Pos(0, 0, 14) * bd.Box(10, 36, 10)
    carriage.label = "carriage"
    pad = bd.Pos(35, 25, 11.5) * bd.Box(10, 10, 5)
    pad.label = "pad"
    slide = bd.LinearJoint("slide", base, axis=bd.Axis((0, 0, 0), (1, 0, 0)), linear_range=(-100, 100))
    bd.RigidJoint("slide", carriage, bd.Location())
    slide.connect_to(carriage.joints["slide"], position=0)
    lift = bd.LinearJoint("lift", base, axis=bd.Axis((35, 25, 0), (0, 0, 1)), linear_range=(-50, 50))
    bd.RigidJoint("lift", pad, bd.Location((35, 25, 0)))
    lift.connect_to(pad.joints["lift"], position=0)
    return bd.Compound(children=[base, carriage, pad], label="overlap")
"""


# A motor drawn as one solid, its case and its output flange together, with six bolt holes through the flange and a
# key standing on its face; a plate bolted flat on the flange's face at every other hole, covering the rest, the key
# in a slot of it, turning on the output's axis; and a stop block on the motor's link further round. The plate turning
# on the flange's face passes over the flange's holes (its contact there grows over the holes' area) and meets the
# key a few degrees round, which turns with it in the hardware; the block is what stops it.
MOTOR = """
import math

import build123d as bd
from cad.engine import xbf


@xbf("XBF/motor.xbf")
def motor():
    holes = [bd.Pos(9 * math.cos(math.radians(at)), 9 * math.sin(math.radians(at)), 29)
             * bd.Cylinder(2.5, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) for at in range(0, 360, 60)]
    case = bd.Cylinder(20, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    flange = bd.Pos(0, 0, 30) * bd.Cylinder(12, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    key = bd.Pos(0, 7, 33) * bd.Box(2, 8, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body = case + flange + key
    for hole in holes:
        body -= hole
    body.label = "motor"
    block = bd.Pos(0, 40, 34.5) * bd.Box(8, 8, 10)
    block.label = "block"
    base = bd.Compound(children=[body, block], label="base")
    plate = bd.Pos(20, 0, 33) * bd.Box(64, 24, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for hole in holes[::2]:  # bolted at every other hole: the plate covers the rest
        plate -= hole
    plate -= bd.Pos(0, 7, 32) * bd.Box(3.3, 9.6, 7, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))  # the key's
    plate.label = "plate"
    output = bd.RevoluteJoint("output", base, axis=bd.Axis((0, 0, 33), (0, 0, 1)), angular_range=(-360, 360))
    bd.RigidJoint("output", plate, output.location)
    output.connect_to(plate.joints["output"], angle=0)
    return bd.Compound(children=[base, plate], label="motor")
"""


# An arm lying flat on a base's top face, hinged at its inner end: turned down, the 10 mm of it over the base go
# straight into the base (0.17 mm deep at a degree), touching all the while; turned up, it lifts off, and its end face
# comes down flat onto the base at 90 degrees.
HINGE = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/hinge.xbf")
def hinge():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    elbow = bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, -1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, elbow.location)
    elbow.connect_to(arm.joints["elbow"], angle=0)
    return bd.Compound(children=[base, arm], label="hinge")
"""


# A link turning in a clevis on a pin through the clevis's bores, the pin filling them, the link drawn 0.4 mm too wide
# for the gap between the cheeks (0.2 mm into each, under what counts as drawn overlapping), over a floor. Turning, the
# pin rides in its bores and the link's sides groove the cheeks: both go into surfaces it moves along, which stop
# nothing. The floor stops it, about 15 degrees down one way and 195 the other.
CLEVIS = """
import build123d as bd
from cad.engine import xbf


@xbf("XBF/clevis.xbf")
def clevis():
    floor = bd.Pos(0, 0, 5) * bd.Box(140, 40, 10)
    floor.label = "floor"
    cheeks = bd.Pos(0, -9, 25) * bd.Box(20, 6, 30) + bd.Pos(0, 9, 25) * bd.Box(20, 6, 30)
    body = cheeks - bd.Pos(0, 0, 30) * bd.Rot(X=90) * bd.Cylinder(4, 30)
    body.label = "clevis"
    base = bd.Compound(children=[floor, body], label="base")
    arm = bd.Pos(26, 0, 30) * bd.Box(68, 12.4, 8) + bd.Pos(0, 0, 30) * bd.Rot(X=90) * bd.Cylinder(4, 24)
    arm.label = "arm"
    pivot = bd.RevoluteJoint("pivot", base, axis=bd.Axis((0, 0, 30), (0, 1, 0)), angular_range=(-180, 180))
    bd.RigidJoint("pivot", arm, pivot.location)
    pivot.connect_to(arm.joints["pivot"], angle=0)
    return bd.Compound(children=[base, arm], label="clevis")
"""


class Ranges(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-ranges-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def rig(self) -> Path:
        from cad.engine import build as engine_build

        script = self.folder / "rig.py"
        script.write_text(textwrap.dedent(RIG), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, ["rig"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        return self.folder / "XBF/rig.xbf"

    def test_each_joint_stops_where_its_parts_meet_another(self) -> None:
        from cad import xbf

        document = self.rig()
        before = document.read_bytes()

        result = xbf.ranges(document)
        self.assertTrue(result.ok, result.human_lines())
        joints = {found["joint"]: found for found in result.measurements["joints"]}
        elbow, slide = joints["elbow"], joints["slide"]
        # The arm stands up from the hinge at 30 mm: 0.31 mm from the wall at -30 degrees, touching it at -31;
        # 0.09 mm from the base at +101, touching it at +102 (build123d's exact distances). Within the clearance
        # (0.3 mm by default, the least: where the parts all but touch) is touching, so each stop is the pose
        # before: the arm is 0.31 mm clear at -30 and over a millimetre at +100.
        self.assertEqual(0.3, result.measurements["clearance"])
        self.assertEqual(("deg", -30.0, 100.0), (elbow["unit"], elbow["lower"], elbow["upper"]))
        self.assertEqual(("arm", "wall", "arm", "base"),
                         (elbow["lower_contact"]["moving"], elbow["lower_contact"]["still"],
                          elbow["upper_contact"]["moving"], elbow["upper_contact"]["still"]))
        # The gap said at each contact (-31, touching; +101, 0.09 mm) is measured, at most twice the resolution over
        # the exact one.
        self.assertTrue(0.0 <= elbow["lower_contact"]["gap"] <= 0.6, elbow["lower_contact"])
        self.assertTrue(0.09 <= elbow["upper_contact"]["gap"] <= 0.09 + 0.6, elbow["upper_contact"])
        # The carriage, built 40 mm along the slide: 70 mm from the wall behind it and 25 mm from the end stop
        # ahead, so about a clearance short of each; seated on the base all along, which stops nothing.
        self.assertEqual("mm", slide["unit"])
        self.assertEqual(40.0, slide["as_built"])
        self.assertTrue(-70.0 < slide["lower"] <= -68.0, slide)
        self.assertTrue(23.0 <= slide["upper"] < 25.0, slide)
        self.assertEqual(("wall", "end_stop"), (slide["lower_contact"]["still"], slide["upper_contact"]["still"]))
        self.assertEqual([40.0 + slide["lower"], 40.0 + slide["upper"]], slide["range"])
        self.assertIn(["carriage", "base"], [list(pair) for pair in slide["resting"]])
        self.assertEqual((None, None, None, None), (elbow["lower_clash"], elbow["upper_clash"], slide["lower_clash"],
                                                    slide["upper_clash"]), "each stop is its own: nothing else first")
        self.assertEqual({"joint_stops"}, {finding.code for finding in result.findings})
        self.assertEqual(before, document.read_bytes(), "the document is not changed")
        self.assertEqual(("", ""), (elbow["why"], slide["why"]), "each has a stop: no reason it has none")

    def test_a_smaller_clearance_never_narrows_a_range(self) -> None:
        from cad import xbf
        from cad._internal import ranges as options
        from cad.engine import ranges as engine

        self.assertEqual(options.RESOLUTION, engine.RESOLUTION, "the refusal and the sweep's samples agree")
        document = self.rig()
        found = {}
        for clearance in (2.0, 1.0, 0.6, 0.3):
            result = xbf.ranges(document, clearance=clearance)
            found[clearance] = {joint["joint"]: (joint["lower"], joint["upper"])
                                for joint in result.measurements["joints"]}
        # Each range holds the one at every larger clearance: its stops at or past them, each way.
        clearances = sorted(found, reverse=True)
        for wider, narrower in zip(clearances, clearances[1:]):
            for name, (lower, upper) in found[narrower].items():
                with self.subTest(joint=name, clearance=narrower):
                    self.assertLessEqual(lower, found[wider][name][0])
                    self.assertGreaterEqual(upper, found[wider][name][1])
        # And it widens: at 2 mm the arm stops short of where it does at 0.3, the wall closing a degree's worth.
        self.assertLess(found[0.3]["elbow"][0], found[2.0]["elbow"][0])
        self.assertGreater(found[0.3]["slide"][1], found[2.0]["slide"][1])

    def test_a_pair_near_as_built_stops_only_where_its_gap_closes(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "near.py"
        script.write_text(textwrap.dedent(NEAR), encoding="utf-8")
        report = engine_build.build(script, ["near"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        result = xbf.ranges(self.folder / "XBF/near.xbf", clearance=1.0)  # the plate 0.4 mm away: within it
        [hinge] = result.measurements["joints"]
        # The plate narrowing from 0.4 to 0.35 mm stops nothing: the arm turns on until it meets the wall, its corner
        # there at +58 degrees (a stop a few degrees on: the count wants about 15 mm^2 of the narrow arm in contact).
        self.assertEqual(("wall", "wall"), (hinge["lower_contact"]["still"], hinge["upper_contact"]["still"]), hinge)
        self.assertTrue(56.0 <= hinge["upper"] <= 66.0, hinge)
        self.assertIsNone(hinge["upper_contact"]["near"])
        [near] = hinge["near"]
        # The anonymous SOLID is named by its component; its label stays the file's.
        self.assertEqual(("Upper_arm v9/SOLID", "Upper_arm v9", "plate"),
                         (near["moving"], near["moving_link"], near["still"]))
        self.assertEqual("Upper_arm v9/SOLID", hinge["upper_contact"]["moving"])
        self.assertTrue(0.39 <= near["rest"] <= 0.45, near)
        self.assertTrue(0.33 <= near["upper"] < near["rest"], near)
        self.assertEqual([], hinge["resting"])
        [line] = [line for line in result.human_lines() if line.startswith("hinge: ")]
        self.assertIn("near as built: Upper_arm v9/SOLID (Upper_arm v9) and plate (base) 0.", line)

    def test_a_pair_drawn_overlapping_stops_only_where_its_overlap_deepens(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "overlap.py"
        script.write_text(textwrap.dedent(OVERLAP), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["overlap"], cwd=self.folder)[0]["ok"])
        swept = {clearance: {found["joint"]: found for found in
                             xbf.ranges(self.folder / "XBF/overlap.xbf", clearance=clearance).measurements["joints"]}
                 for clearance in (1.0, 0.3)}
        slide, lift = swept[0.3]["slide"], swept[0.3]["lift"]
        # The carriage's 5 mm overlap shrinking off the rail's end, and sliding along it, stop nothing: it meets the end
        # block 30 mm one way and the stop block 55 mm the other, a clearance short of each.
        self.assertEqual(("end_block", "stop_block"), (slide["lower_contact"]["still"], slide["upper_contact"]["still"]),
                         slide)
        self.assertTrue(-30.0 < slide["lower"] <= -28.0, slide)
        self.assertTrue(53.0 <= slide["upper"] < 55.0, slide)
        # The overlap is said: the carriage in the rail by about 180 mm^3, 1 mm deep.
        [drawn] = slide["overlapping"]
        self.assertEqual(("carriage", "rail"), (drawn["moving"], drawn["still"]))
        self.assertTrue(160.0 <= drawn["volume"] <= 200.0 and 0.9 <= drawn["depth"] <= 1.3, drawn)
        # The pad pushed down deepens its overlap: it stops within a few millimetres, at the rail, the overlap said; lifted
        # off the rail it is clear.
        self.assertEqual("rail", lift["lower_contact"]["still"], lift)
        self.assertTrue(-4.0 <= lift["lower"] <= -0.0, lift)
        contact = lift["lower_contact"]
        self.assertEqual((100.0, 1.0, None), (round(contact["overlap"], -1), round(contact["depth"]), contact["gap"]))
        self.assertIsNone(lift["upper"], lift)
        [line] = [line for line in xbf.ranges(self.folder / "XBF/overlap.xbf", joint=("lift",)).human_lines()
                  if line.startswith("lift: ")]
        self.assertIn(", deeper than drawn (overlapping ", line)
        self.assertIn("; overlapping as drawn, stopping only where that deepens: pad (pad) in rail (base) by ", line)
        # Nothing of it reads the clearance: a smaller one never narrows a range.
        for name in ("slide", "lift"):
            wide, narrow = swept[1.0][name], swept[0.3][name]
            self.assertLessEqual(narrow["lower"], wide["lower"], name)
            self.assertGreaterEqual(math.inf if narrow["upper"] is None else narrow["upper"],
                                    math.inf if wide["upper"] is None else wide["upper"], name)

    def test_a_plate_on_an_output_drawn_with_its_motor_turns_on_it_to_the_real_stop(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "motor.py"
        script.write_text(textwrap.dedent(MOTOR), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["motor"], cwd=self.folder)[0]["ok"])
        result = xbf.ranges(self.folder / "XBF/motor.xbf", step=2.0)
        [output] = result.measurements["joints"]
        # The plate turning on the flange's face stops nothing there, its holes passing over the flange's: it turns
        # until its side meets the block, about 67 degrees one way and 248 the other.
        self.assertEqual(("block", "block"), (output["lower_contact"]["still"], output["upper_contact"]["still"]),
                         output)
        self.assertTrue(55.0 <= output["upper"] <= 70.0, output)
        self.assertTrue(-260.0 <= output["lower"] <= -235.0, output)
        # The pair is said: the plate turns on a surface about the joint's axis, touching as built.
        self.assertEqual([("plate", "plate", "motor", "base")],
                         [(pair["moving"], pair["moving_link"], pair["still"], pair["still_link"])
                          for pair in output["riding"]])
        self.assertIn(["plate", "motor"], [list(pair) for pair in output["resting"]])
        [line] = [line for line in result.human_lines() if line.startswith("output: ")]
        self.assertIn("turns on: plate (plate) on motor (base), touching as built on a surface about its axis", line)

    def test_a_part_resting_on_its_parent_stops_where_it_is_pushed_into_it(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "hinge.py"
        script.write_text(textwrap.dedent(HINGE), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["hinge"], cwd=self.folder)[0]["ok"])
        [elbow] = xbf.ranges(self.folder / "XBF/hinge.xbf").measurements["joints"]
        # Turned down it goes into the base at once: its stop is where it lies, to within the step, not where it
        # has turned far enough for some other part of it to reach the base's side.
        self.assertEqual(("base", "base"), (elbow["lower_contact"]["still"], elbow["upper_contact"]["still"]), elbow)
        self.assertTrue(-1.0 <= elbow["lower"] <= 0.0, elbow)
        # Turned up it lifts off: its end face comes within the clearance of the base, over a contact grown,
        # short of lying flat on it at 90 degrees.
        self.assertTrue(70.0 <= elbow["upper"] < 90.0, elbow)

    def test_a_link_turning_in_its_clevis_is_stopped_by_neither_its_pin_nor_the_cheeks(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "clevis.py"
        script.write_text(textwrap.dedent(CLEVIS), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["clevis"], cwd=self.folder)[0]["ok"])
        [pivot] = xbf.ranges(self.folder / "XBF/clevis.xbf").measurements["joints"]
        # The pin in its bores and the sides grooving the cheeks stop nothing: the floor stops it, its tip there at
        # 15.4 degrees one way and 195.4 the other.
        self.assertEqual(("floor", "floor"), (pivot["lower_contact"]["still"], pivot["upper_contact"]["still"]), pivot)
        self.assertTrue(13.0 <= pivot["upper"] <= 15.4, pivot)
        self.assertTrue(-195.4 <= pivot["lower"] <= -193.0, pivot)
        self.assertEqual([("arm", "clevis")], [(pair["moving"], pair["still"]) for pair in pivot["riding"]])
        self.assertEqual([], pivot["overlapping"])

    def test_the_stops_are_said_as_a_table_and_a_long_sweep_as_it_goes(self) -> None:
        import contextlib
        import io

        from cad import xbf

        document = self.rig()
        said = io.StringIO()
        with mock.patch("cad.engine.ranges.LONG", 0.0), contextlib.redirect_stderr(said):
            result = xbf.ranges(document)
        lines = result.human_lines()
        self.assertEqual([line.split() for line in lines[:3]],
                         [["joint", "lower", "upper", "range"], ["elbow", "-30", "deg", "+100", "deg", "-30", "to",
                                                                 "100", "deg"],
                          ["slide", *lines[2].split()[1:]]])
        self.assertTrue(lines[3].startswith("elbow: lower -30 deg: arm (arm) meets wall"), lines)
        self.assertFalse([line for line in lines if line.startswith("info:")], lines)
        # Each joint said as it starts, about how long it may take, and as it ends, though not verbose.
        heard = [line for line in said.getvalue().splitlines() if "re-estimated" not in line]
        self.assertTrue(heard[0].startswith("ranges: sweeping elbow (1 of 2): up to about "), heard)
        self.assertTrue(heard[1].startswith("ranges: elbow swept in "), heard)
        # A sweep running long says each joint as it starts, though each is short, and each joint it said as it ends:
        # none goes unsaid, and none said starting goes unsaid ending.
        said = io.StringIO()
        with mock.patch("cad.engine.ranges.LONG", 1e9), mock.patch("cad.engine.ranges.QUIET", 0.0), \
                contextlib.redirect_stderr(said):
            xbf.ranges(document)
        heard = said.getvalue().splitlines()
        self.assertEqual(["ranges: sweeping elbow (1 of 2)", "ranges: elbow swept in", "ranges: sweeping slide (2 of 2)",
                          "ranges: slide swept in"], [line.rsplit(" ", 2)[0] if " swept in " in line else line
                                                      for line in heard])
        # A joint that runs long after its start is said then, and as it ends; an estimate found low is said again.
        calls = iter(range(10 ** 6))  # a clock still until the joint's first pose is timed, then an hour a call

        def clock() -> float:
            return max(0.0, next(calls) - 6.0) * 3600.0

        said = io.StringIO()
        with mock.patch("cad.engine.ranges.LONG", 100.0), mock.patch("cad.engine.ranges.QUIET", 1e9), \
                mock.patch("cad.engine.ranges.time.perf_counter", clock), contextlib.redirect_stderr(said):
            xbf.ranges(document, joint=("elbow",))
        heard = said.getvalue().splitlines()
        self.assertTrue(heard[0].startswith("ranges: sweeping elbow (1 of 1): up to about ") and
                        heard[0].endswith(" more"), heard)
        self.assertTrue(heard[-1].startswith("ranges: elbow swept in "), heard)
        self.assertEqual(2, len(heard), heard)
        # Verbose, each step is said as it starts, the reading and the sampling before any joint: a fine sweep's
        # minutes of sampling are not minutes of silence.
        said = io.StringIO()
        with mock.patch("cad.engine.ranges.LONG", 1e9), contextlib.redirect_stderr(said):
            xbf.ranges(document, verbose=True)
        heard = [line.split(":")[1].strip().split(" ")[0] for line in said.getvalue().splitlines()]
        self.assertEqual(["reading", "sampling", "sweeping", "elbow", "sweeping", "slide"], heard, said.getvalue())
        self.assertIn("ranges: sampling 5 part surfaces to within 0.3 mm: about ", said.getvalue())

    def test_one_joint_is_swept_alone_and_an_unknown_one_is_refused_by_name(self) -> None:
        from cad import xbf

        document = self.rig()
        result = xbf.ranges(document, joint=("slide",))
        self.assertEqual(["slide"], [found["joint"] for found in result.measurements["joints"]])
        self.assertIn("1 joint swept", result.summary)
        with self.assertRaisesRegex(ArgumentRefused, r"^--joint 'elbo' is no joint the sweep moves; its joints: "
                                                     r"elbow, slide$"):
            xbf.ranges(document, joint=("elbo",))

    def test_a_document_with_no_joint_has_nothing_to_sweep(self) -> None:
        import build123d as bd

        from cad import step

        path = self.folder / "block.step"
        block = bd.Box(10, 10, 10)
        block.label = "block"
        bd.export_step(block, str(path))
        result = step.ranges(path)
        self.assertFalse(result.ok)
        self.assertEqual(["no_joints"], [finding.code for finding in result.findings])

    def test_a_step_or_a_clearance_out_of_range_is_refused_by_name(self) -> None:
        from cad import xbf

        for options, flag in (({"step": 0}, "--step"), ({"step": 90}, "--step"), ({"clearance": -1}, "--clearance"),
                              ({"clearance": 0.2}, "--clearance 0.2 is under the sweep's resolution, 0.3 mm")):
            with self.subTest(options), self.assertRaisesRegex(ArgumentRefused, flag):
                xbf.ranges(self.folder / "missing.xbf", **options)


if __name__ == "__main__":
    unittest.main()
