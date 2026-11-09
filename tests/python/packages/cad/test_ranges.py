"""``cad.<type>.ranges``: each joint of a mechanism swept alone against the parts' collision geometry.

A base with a wall, an arm on a hinge and a carriage on a slide, built to an xbf: the arm turns until it
meets the wall one way and the base the other, the carriage slides until it meets the wall one way and an end
stop the other (touching the base all along, as built, which stops nothing), each stop where an exact
distance says the parts come within the clearance; the document is not changed. A STEP with no joint has
nothing to sweep: an error, said by code. An option out of range is refused by name. A part declared decomposed
is cut into hulls for the collision geometry alone. The stops are said as a table, and a long sweep says each joint as
it starts and ends; a verbose one says each step as it starts. A pair near as built, its gap narrowing a hair as the
joint turns, stops nothing until it truly closes, and is reported with its gaps."""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cad._internal.refused import ArgumentRefused

RIG = """
import build123d as bd
from cad.build123d import collision
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
    {declare}
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


class Ranges(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-ranges-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def rig(self, declare: str = "pass") -> Path:
        from cad.engine import build as engine_build

        script = self.folder / "rig.py"
        script.write_text(textwrap.dedent(RIG.format(declare=declare)), encoding="utf-8")
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
        # 0.09 mm from the base at +101, touching it at +102 (build123d's exact distances).
        self.assertEqual(("deg", -30.0, 101.0), (elbow["unit"], elbow["lower"], elbow["upper"]))
        self.assertEqual(("arm", "wall", "arm", "base"),
                         (elbow["lower_contact"]["moving"], elbow["lower_contact"]["still"],
                          elbow["upper_contact"]["moving"], elbow["upper_contact"]["still"]))
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

    def test_a_pair_near_as_built_stops_only_where_its_gap_closes(self) -> None:
        from cad import xbf
        from cad.engine import build as engine_build

        script = self.folder / "near.py"
        script.write_text(textwrap.dedent(NEAR), encoding="utf-8")
        report = engine_build.build(script, ["near"], cwd=self.folder)[0]
        self.assertTrue(report["ok"], report)
        result = xbf.ranges(self.folder / "XBF/near.xbf")
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
                         [["joint", "lower", "upper", "range"], ["elbow", "-30", "deg", "+101", "deg", "-30", "to",
                                                                 "101", "deg"],
                          ["slide", *lines[2].split()[1:]]])
        self.assertTrue(lines[3].startswith("elbow: lower -30 deg: arm (arm) meets wall"), lines)
        self.assertFalse([line for line in lines if line.startswith("info:")], lines)
        # Each joint said as it starts, about how long it may take, and as it ends, though not verbose.
        heard = said.getvalue().splitlines()
        self.assertTrue(heard[0].startswith("ranges: sweeping elbow (1 of 2): up to about "), heard)
        self.assertTrue(heard[1].startswith("ranges: elbow swept in "), heard)
        # Verbose, each step is said as it starts, the reading and the sampling before any joint: a fine sweep's
        # minutes of sampling are not minutes of silence.
        said = io.StringIO()
        with mock.patch("cad.engine.ranges.LONG", 1e9), contextlib.redirect_stderr(said):
            xbf.ranges(document, verbose=True)
        heard = [line.split(":")[1].strip().split(" ")[0] for line in said.getvalue().splitlines()]
        self.assertEqual(["reading", "sampling", "sweeping", "elbow", "sweeping", "slide"], heard, said.getvalue())
        self.assertIn("ranges: sampling 5 part surfaces every 0.6 mm: about ", said.getvalue())

    def test_a_decomposed_part_is_cut_for_the_collision_geometry_alone(self) -> None:
        from cad import xbf

        calls: list[int] = []

        def stand_in(meshes: Any) -> list[list[tuple[Any, Any]]]:  # each mesh its own one hull
            calls.append(len(meshes))
            return [[(positions, triangles)] for positions, triangles, _options in meshes]

        document = self.rig('collision(wall, "decomposed")')
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")}), \
                mock.patch("cad.engine.hulls._decompose", stand_in):
            parts = xbf.ranges(document)
            self.assertEqual(calls, [], "on the parts, nothing is decomposed")
            collided = xbf.ranges(document, geometry="collision")
            self.assertEqual(calls, [1])
        lower = [{found["joint"]: found for found in result.measurements["joints"]}["elbow"]["lower"]
                 for result in (parts, collided)]
        self.assertEqual(lower[0], -30.0, "on the parts the arm still stops at the wall")
        self.assertIsNotNone(lower[1], "and at the wall's hull on the collision geometry")

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
                              ({"geometry": "hull"}, "--geometry")):
            with self.subTest(options), self.assertRaisesRegex(ArgumentRefused, flag):
                xbf.ranges(self.folder / "missing.xbf", **options)


if __name__ == "__main__":
    unittest.main()
