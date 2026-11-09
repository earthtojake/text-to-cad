"""``cad.<type>.ranges``: each joint of a mechanism swept alone against the parts' collision geometry.

A base with a wall, an arm on a hinge and a carriage on a slide, built to an xbf: the arm turns until it
meets the wall one way and the base the other, the carriage slides until it meets the wall one way and an end
stop the other (touching the base all along, as built, which stops nothing), each stop where an exact
distance says the parts come within the clearance; the document is not changed. A STEP with no joint has
nothing to sweep: an error, said by code. An option out of range is refused by name. A part declared decomposed
is cut into hulls for the collision geometry alone."""

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
