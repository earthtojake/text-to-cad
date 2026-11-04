#!/usr/bin/env python3

"""The CNC check's planted-defect corpus: parts built here with known defects and clean controls, each
written to a STEP in a temporary folder and checked through ``cad.step.dfm`` as a person would.

The ground truth is the construction's: each case names the rules that must fail and the box (world
millimetres) of the feature they must fail at -- a failure's face, read back by the engine's own loader
from its ref, must touch that box. Any failure the case does not name is a false positive; any planted
defect no failure finds is a miss. Precision and recall per rule id are printed to stderr, and both must
be 1.0: the corpus is small and every case is exact, so a miss is a bug (or, where documented beside the
case, a limit of the measurement that the case shows).

Edge cases: fillets everywhere, a freeform (spline) surface, an assembly, an inch STEP, a 2 mm part and a
2.2 m one, a turned part, a part that needs five setups, a T-slot, a dovetail, a closed void, an inclined
hole on three axes and on five.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import build123d as bd

import cad.step
from cad.build123d import _dfm_brep as brep

A = bd.Align
Box3 = tuple[tuple[float, float, float], tuple[float, float, float]]


def box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Box3:
    return ((x0, y0, z0), (x1, y1, z1))


@dataclass
class Case:
    name: str
    build: Callable[[], Any]
    options: dict[str, Any] = field(default_factory=dict)
    #: (rule id, part owner or None, box): must fail there
    expect: list[tuple[str, str | None, Box3 | None]] = field(default_factory=list)
    #: may fail there (a consequence of a planted defect, not itself planted); never counted as a miss
    allow: list[tuple[str, str | None, Box3 | None]] = field(default_factory=list)
    unit: Any = None


def _at(shape: Any, x: float, y: float, z: float) -> Any:
    return bd.Pos(x, y, z) * shape


def _pocket(length: float, width: float, depth: float, radius: float, top: float) -> Any:
    """A pocket's void, its floor ``depth`` under ``top``, its vertical corners rounded to ``radius``."""
    cut = bd.Box(length, width, depth + 1, align=(A.CENTER, A.CENTER, A.MIN))
    if radius > 0:
        cut = bd.fillet(cut.edges().filter_by(bd.Axis.Z), radius)
    return bd.Pos(0, 0, top - depth) * cut


def _drill(diameter: float, depth: float, point: float | None = 118.0) -> Any:
    """A drilled hole's void from z = 0 down: the full diameter ``depth`` deep, then its point."""
    radius = diameter / 2
    body = bd.Cylinder(radius, depth + 1, align=(A.CENTER, A.CENTER, A.MAX))
    body = bd.Pos(0, 0, 1) * body
    if point is None:
        return body
    tip = radius / math.tan(math.radians(point / 2))
    return body + bd.Pos(0, 0, -depth) * bd.Cone(0.0, radius, tip, align=(A.CENTER, A.CENTER, A.MAX))


def _labelled(shape: Any, label: str) -> Any:
    shape.label = label
    return shape


# --- the parts -------------------------------------------------------------------------------------------


def pockets() -> Any:
    part = bd.Box(120, 80, 40)  # top at z = 20
    part -= _at(_pocket(40, 24, 30, 2.0, 20), -30, 15, 0)       # A: deep, small corners
    part -= _at(_pocket(12, 12, 6, 0.0, 20), 30, 20, 0)         # B: sharp corners
    part -= _at(_pocket(30, 24, 9, 4.0, 20), 30, -20, 0)        # C: control
    slot = bd.extrude(bd.SlotOverall(24, 3), 16)                 # D: a 3 mm slot 15 deep
    part -= bd.Pos(-30, -20, 5) * slot
    return _labelled(part, "pockets")


def walls() -> Any:
    part = bd.Box(60, 40, 5, align=(A.CENTER, A.CENTER, A.MAX))  # top at z = 0
    for y, thickness in ((-12, 0.8), (0, 1.2), (12, 3.0)):
        part += bd.Pos(0, y, 0) * bd.Box(50, thickness, 15, align=(A.CENTER, A.CENTER, A.MIN))
    return _labelled(part, "ribs")


def holes() -> Any:
    part = bd.Box(100, 30, 50)  # top at z = 25
    part -= _at(_drill(6.8, 20), -40, 0, 25)                                 # control: an M8 tap drill
    part -= _at(_drill(6.6, 20), -25, 0, 25)                                 # control: counterbored 6.6
    part -= _at(bd.Cylinder(5.5, 6.5, align=(A.CENTER, A.CENTER, A.MAX)), -25, 0, 25.5)
    part -= _at(_drill(4.5, 15), -10, 0, 25)                                 # control: countersunk 4.5
    part -= _at(bd.Cone(2.25, 4.75, 2.5, align=(A.CENTER, A.CENTER, A.MAX)), -10, 0, 25.25)
    part -= _at(_drill(4.33, 12), 5, 0, 25)                                  # not a standard drill
    part -= _at(_drill(2.0, 35), 20, 0, 25)                                  # 17.5 diameters deep
    part -= _at(_drill(0.8, 3), 30, 0, 25)                                   # under 1 mm
    part -= _at(_drill(1.0, 45), 40, 0, 25)                                  # 45 diameters deep
    return _labelled(part, "drilled")


def tslots() -> Any:
    part = bd.Box(80, 60, 30)  # top at z = 15
    # open at both ends along x: a straight tool reaches every face from x
    part -= bd.Pos(0, -15, 12) * bd.Box(90, 8, 6)
    part -= bd.Pos(0, -15, 6) * bd.Box(90, 20, 6)
    # closed: the T's wide part is reached by no straight line
    part -= bd.Pos(0, 15, 12) * bd.Box(50, 8, 6)
    part -= bd.Pos(0, 15, 6) * bd.Box(50, 20, 6)
    return _labelled(part, "tslots")


def _groove(points: list[tuple[float, float]], length: float) -> Any:
    """A prism along x of the (y, z) polygon."""
    profile = bd.Polygon(*points, align=None)
    return bd.extrude(bd.Plane.YZ * profile, length / 2, both=True)


def grooves() -> Any:
    """Grooves through along x, their sections in y and z (the part's top at z = 15, each section drawn to
    z = 15.5 so the cut leaves no skin)."""
    part = bd.Box(80, 60, 30)
    over = 15.5

    def v(centre: float, bottom: float, left_deg: float, right_deg: float) -> Any:
        rise = over - bottom
        return _groove([(centre - rise * math.tan(math.radians(left_deg)), over),
                        (centre + rise * math.tan(math.radians(right_deg)), over), (centre, bottom)], 90)

    # a 60-degree dovetail slot (control: a dovetail cutter's): floor at z = 7, 5 mm half-neck at the top
    floor, half = 7.0, 5.0 + 8.0 / math.tan(math.radians(60))
    inset = (over - floor) / math.tan(math.radians(60))
    part -= _groove([(-20 - half, floor), (-20 + half, floor), (-20 + half - inset, over),
                     (-20 - half + inset, over)], 90)
    part -= v(-4, 9, 45, 45)    # a symmetric 90-degree V (control: a chamfer mill's)
    part -= v(6, 9, 15, 15)     # a 30-degree V: no rotating tool (planted)
    part -= v(14, 9, 40, 60)    # a lopsided 100-degree V: five axes tilt to a face, three do not (planted)
    return _labelled(part, "grooves")


def voided() -> Any:
    part = bd.Box(40, 40, 20) - bd.Sphere(5)
    return _labelled(part, "voided")


def six_sides() -> Any:
    part = bd.Box(60, 60, 60)
    for rotation in ((0, 0, 0), (180, 0, 0), (0, 90, 0), (0, -90, 0), (-90, 0, 0)):
        part -= bd.Rot(*rotation) * _at(_pocket(20, 20, 5, 5, 30), 0, 0, 0)
    return _labelled(part, "six_sides")


def two_sides() -> Any:
    part = bd.Box(60, 40, 30)
    part -= _pocket(30, 20, 8, 5, 15)
    part -= bd.Rot(180, 0, 0) * _pocket(30, 20, 8, 5, 15)
    return _labelled(part, "two_sides")


def inclined() -> Any:
    part = bd.Box(60, 40, 30)
    part -= bd.Rot(0, 30, 0) * bd.Cylinder(4, 100)
    return _labelled(part, "inclined")


def shaft() -> Any:
    """A turned shaft whose every feature breaks one of Protolabs' turning limits."""
    body = bd.Cylinder(15, 120, align=(A.CENTER, A.CENTER, A.MIN))                    # z 0 .. 120, OD 30
    body += bd.Pos(0, 0, 120) * bd.Cylinder(1.5, 5, align=(A.CENTER, A.CENTER, A.MIN))  # a 3 mm pin
    body += bd.Pos(0, 0, -10) * bd.Cylinder(55, 10, align=(A.CENTER, A.CENTER, A.MIN))  # a 110 mm flange
    body += bd.Pos(0, 0, 60) * bd.Cylinder(17, 1.0, align=(A.CENTER, A.CENTER, A.MIN))  # a 1 mm collar
    body -= bd.Pos(0, 0, 30) * (bd.Cylinder(16, 1.0, align=(A.CENTER, A.CENTER, A.MIN))
                                - bd.Cylinder(13, 1.0, align=(A.CENTER, A.CENTER, A.MIN)))  # a 1 mm OD groove
    body -= bd.Pos(0, 0, -20) * bd.Cylinder(5, 100, align=(A.CENTER, A.CENTER, A.MIN))  # a 10 mm bore
    body -= bd.Pos(0, 0, 40) * bd.Cylinder(7, 3, align=(A.CENTER, A.CENTER, A.MIN))    # an ID groove
    body -= bd.Pos(0, 0, 100) * bd.Rot(0, 90, 0) * bd.Cylinder(0.75, 40)               # a 1.5 mm radial hole
    body -= bd.Pos(8, 0, 90) * bd.Rot(45, 0, 0) * bd.Cylinder(2, 60)                    # an off-axis hole
    return _labelled(body, "shaft")


def clean_shaft() -> Any:
    body = bd.Cylinder(12, 80, align=(A.CENTER, A.CENTER, A.MIN))
    body += bd.Pos(0, 0, 80) * bd.Cylinder(8, 30, align=(A.CENTER, A.CENTER, A.MIN))
    body -= bd.Pos(0, 0, 50) * (bd.Cylinder(13, 3, align=(A.CENTER, A.CENTER, A.MIN))
                                - bd.Cylinder(10, 3, align=(A.CENTER, A.CENTER, A.MIN)))
    body -= bd.Pos(0, 0, -1) * bd.Cylinder(3, 31, align=(A.CENTER, A.CENTER, A.MIN))
    body -= bd.Pos(0, 0, 20) * bd.Rot(0, 90, 0) * bd.Cylinder(2.5, 40)
    return _labelled(body, "clean_shaft")


def filleted() -> Any:
    part = bd.Box(60, 40, 25)  # top at z = 12.5
    part -= _pocket(30, 20, 12, 5.0, 12.5)
    sharp = [edge for edge in part.edges() if edge.geom_type == bd.GeomType.LINE]
    part = bd.fillet(sharp, 1.0)
    return _labelled(part, "filleted")


def freeform() -> Any:
    """A loft from a rectangle through two ellipses: every side a B-spline (a control)."""
    sections = [bd.Plane.XY * bd.Rectangle(60, 40), bd.Plane.XY.offset(10) * bd.Ellipse(28, 18),
                bd.Plane.XY.offset(16) * bd.Ellipse(20, 12)]
    part = bd.loft(sections) - bd.Cylinder(3, 40)
    return _labelled(part, "freeform")


def kit() -> Any:
    plate = _labelled(bd.Box(50, 40, 6) - _at(bd.Cylinder(3.3, 10), 0, 0, 0), "plate")
    bracket = bd.Box(30, 30, 20) - _pocket(10, 10, 8, 0.0, 10)
    bracket = _labelled(bd.Pos(60, 0, 0) * bracket, "bracket")
    assembly = bd.Compound(children=[plate, bracket])
    assembly.label = "kit"
    return assembly


def inch_plate() -> Any:
    """Drawn in inches and written as an inch STEP (build123d labels the file's unit; it does not scale)."""
    inch = 1.0
    part = bd.Box(4 * inch, 2 * inch, 0.5 * inch)  # top at z = 6.35
    part -= _at(_drill(0.25 * inch, 0.3 * inch), -1.2 * inch, 0, 0.25 * inch)       # 1/4 in: standard
    part -= _at(_drill(0.2 * inch, 0.3 * inch), -0.6 * inch, 0, 0.25 * inch)        # 0.200 in: no drill
    part -= _at(_pocket(1.0 * inch, 1.0 * inch, 0.375 * inch, 0.0625 * inch, 0.25 * inch), 0.9 * inch, 0, 0)
    return _labelled(part, "inch_plate")


def tiny() -> Any:
    """A 4 x 2 x 2 mm part (top at z = 1) with slots through along y."""
    part = bd.Box(4.0, 2.0, 2.0)

    def slot(x0: float, x1: float, depth: float) -> Any:
        return bd.Pos((x0 + x1) / 2, 0, 1 - depth) * bd.Box(x1 - x0, 3, depth + 0.01, align=(A.CENTER, A.CENTER, A.MIN))

    part -= slot(-1.0, -0.7, 0.25)     # 0.3 wide
    part -= slot(-0.55, -0.25, 0.25)   # 0.3 wide, leaving a 0.15 mm wall between the two
    part -= slot(0.98, 1.02, 0.2)      # 0.04 wide, 0.2 deep
    return _labelled(part, "tiny")


def huge() -> Any:
    part = bd.Box(2200, 900, 50)
    part -= _pocket(400, 300, 30, 40, 25)
    return _labelled(part, "huge")


def tooled() -> Any:
    part = bd.Box(40, 30, 12)
    part -= _pocket(20, 14, 3, 1.0, 6)
    return _labelled(part, "tooled")


def xometry_cavity() -> Any:
    part = bd.Box(60, 40, 40)
    part -= _pocket(30, 6, 21, 2.5, 20)  # 21 deep, 6 wide: 3.5x, over Xometry's 3, under Hubs' 4
    return _labelled(part, "cavity")


def windows() -> Any:
    """A 10 mm plate (z -5 .. 5) with through windows: R0.5 corners at x = -25 (tighter than a 3 mm tool,
    planted), R4 at x = 25 (control)."""
    part = bd.Box(100, 50, 10)
    part -= bd.Pos(-25, 0, -6) * bd.extrude(bd.RectangleRounded(30, 20, 0.5), 12)
    part -= bd.Pos(25, 0, -6) * bd.extrude(bd.RectangleRounded(30, 20, 4), 12)
    return _labelled(part, "windows")


def through_slot() -> Any:
    """A 3 mm slot through 20 mm (planted: 6.7 widths deep) beside a 10 mm one (control)."""
    part = bd.Box(80, 40, 20)
    part -= bd.Pos(-20, 0, -11) * bd.extrude(bd.SlotOverall(30, 3), 22)
    part -= bd.Pos(20, 0, -11) * bd.extrude(bd.SlotOverall(30, 10), 22)
    return _labelled(part, "through_slot")


def webs() -> Any:
    """6 mm holes through 10 mm: a pair at 6.4 mm pitch (a 0.4 mm web, planted), a pair at 9 mm (control)."""
    part = bd.Box(60, 20, 10)
    for x in (-23.2, -16.8, 14.5, 23.5):
        part -= bd.Pos(x, 0, 0) * bd.Cylinder(3, 12)
    return _labelled(part, "webs")


def knife() -> Any:
    """A block whose +x end is bevelled to an 18.4-degree knife edge (planted)."""
    profile = bd.Polygon((0, 0), (40, 0), (40, 10), (30, 10), align=None)
    return _labelled(bd.extrude(bd.Plane.XZ * profile, 15, both=True), "knife")


def valley() -> Any:
    """A block whose top is a 176-degree valley along y: a ball end mill's crease (a control)."""
    rise = 30 * math.tan(math.radians(2))
    profile = bd.Polygon((-30, 0), (30, 0), (30, 10 + rise), (0, 10), (-30, 10 + rise), align=None)
    return _labelled(bd.extrude(bd.Plane.XZ * profile, 20, both=True), "valley")


# --- the ground truth ------------------------------------------------------------------------------------

CASES = [
    Case("pockets", pockets, {"material": "aluminum"},
         expect=[("cnc.corner_radius_to_depth", None, box(-50, 3, -10, -10, 27, 20)),
                 ("cnc.corner_reach", None, box(-50, 3, -10, -10, 27, 20)),
                 ("cnc.internal_corner_sharp", None, box(24, 14, 14, 36, 26, 20)),
                 ("cnc.pocket_depth_to_width", None, box(-42, -21.5, 5, -18, -18.5, 20)),
                 ("cnc.corner_radius_to_depth", None, box(-42, -21.5, 5, -18, -18.5, 20)),
                 ("cnc.corner_reach", None, box(-42, -21.5, 5, -18, -18.5, 20))]),
    Case("ribs", walls, {"material": "abs"},
         expect=[("cnc.wall_thickness", None, box(-25, -12.4, 0, 25, -11.6, 15)),
                 ("cnc.wall_thickness_recommended", None, box(-25, -12.4, 0, 25, -11.6, 15)),
                 ("cnc.wall_thickness_recommended", None, box(-25, -0.6, 0, 25, 0.6, 15))]),
    Case("drilled", holes, {"material": "steel"},
         expect=[("cnc.drill_size", None, box(2.8, -2.2, 10, 7.2, 2.2, 25)),
                 ("cnc.hole_depth", None, box(19, -1, -12, 21, 1, 25)),
                 ("cnc.hole_diameter", None, box(29.6, -0.4, 21, 30.4, 0.4, 25)),
                 ("cnc.hole_depth", None, box(39.5, -0.5, -21, 40.5, 0.5, 25)),
                 ("cnc.hole_depth_limit", None, box(39.5, -0.5, -21, 40.5, 0.5, 25))]),
    Case("tslots", tslots, {"material": "aluminum"},
         expect=[("cnc.no_line_of_sight", None, box(-25, 5, 3, 25, 25, 9)),
                 ("cnc.internal_corner_sharp", None, box(-25, 5, 3, 25, 25, 15))],
         allow=[("cnc.undercut", None, box(-25, 5, 3, 25, 25, 15))]),
    Case("grooves", grooves, {"material": "aluminum"},
         expect=[("cnc.sharp_internal_edge", None, box(-40, 4.2, 9, 40, 7.8, 15)),
                 ("cnc.sharp_internal_edge", None, box(-40, 8.5, 9, 40, 25.4, 15))],
         # the 30-degree groove narrows to nothing at its root: a gap no tool enters; the dovetail's foot
         # (y = -29.62) stands 0.38 mm from the part's side (y = -30): a real wall the exact distance finds
         allow=[("cnc.gap_width", None, box(-40, 4.2, 9, 40, 7.8, 15)),
                ("cnc.gap_width_small", None, box(-40, 4.2, 9, 40, 7.8, 15)),
                ("cnc.wall_thickness", None, box(-40, -30, 7, 40, -29.6, 7.1)),
                ("cnc.wall_thickness_recommended", None, box(-40, -30, 7, 40, -29.6, 7.1))]),
    Case("grooves-5axis", grooves, {"material": "aluminum", "axes": 5},
         expect=[("cnc.sharp_internal_edge", None, box(-40, 4.2, 9, 40, 7.8, 15))],
         allow=[("cnc.gap_width", None, box(-40, 4.2, 9, 40, 7.8, 15)),
                ("cnc.gap_width_small", None, box(-40, 4.2, 9, 40, 7.8, 15)),
                ("cnc.wall_thickness", None, box(-40, -30, 7, 40, -29.6, 7.1)),
                ("cnc.wall_thickness_recommended", None, box(-40, -30, 7, 40, -29.6, 7.1))]),
    Case("voided", voided, {"material": "aluminum"},
         expect=[("cnc.enclosed_void", None, box(-5, -5, -5, 5, 5, 5))]),
    Case("six_sides", six_sides, {"material": "aluminum"}, expect=[("cnc.setups", None, None)]),
    Case("two_sides", two_sides, {"material": "aluminum"}),
    # the hole runs 30 / cos 30 = 34.6 mm at 8 mm: 4.3 diameters, over Hubs' recommended 4
    Case("inclined", inclined, {"material": "aluminum"},
         expect=[("cnc.undercut", None, box(-30, -4, -15, 30, 4, 15)),
                 ("cnc.hole_depth", None, box(-30, -4, -15, 30, 4, 15))]),
    Case("inclined-4axis", inclined, {"material": "aluminum", "axes": 4},
         expect=[("cnc.hole_depth", None, box(-30, -4, -15, 30, 4, 15))]),
    Case("inclined-5axis", inclined, {"material": "aluminum", "axes": 5},
         expect=[("cnc.hole_depth", None, box(-30, -4, -15, 30, 4, 15))]),
    Case("shaft", shaft, {"material": "steel", "turning": True, "rules": "protolabs"},
         expect=[("cnc.turned_diameter", None, None),
                 ("cnc.turned_feature_diameter_small", None, box(-1.5, -1.5, 120, 1.5, 1.5, 125)),
                 ("cnc.turned_feature_length", None, box(-17, -17, 60, 17, 17, 61)),
                 ("cnc.groove_width", None, box(-13, -13, 30, 13, 13, 31)),
                 ("cnc.internal_groove", None, box(-7, -7, 40, 7, 7, 43)),
                 ("cnc.radial_hole_diameter", None, box(-15, -0.75, 99.25, 15, 0.75, 100.75)),
                 ("cnc.off_axis_hole", None, box(6, -15, 70, 10, 15, 110))]),
    Case("clean_shaft", clean_shaft, {"material": "aluminum", "turning": True, "rules": "protolabs"}),
    Case("filleted", filleted, {"material": "aluminum"}),
    Case("freeform", freeform, {"material": "aluminum"}),
    Case("kit", kit, {"material": "aluminum"},
         expect=[("cnc.internal_corner_sharp", "bracket", box(55, -5, 2, 65, 5, 10))]),
    Case("inch_plate", inch_plate, {"material": "aluminum"}, unit=bd.Unit.IN,
         expect=[("cnc.drill_size", None, box(-17.8, -2.6, -1.3, -12.7, 2.6, 6.4)),
                 ("cnc.corner_radius_to_depth", None, box(10.16, -12.7, -3.2, 35.56, 12.7, 6.4))]),
    Case("tiny", tiny, {"material": "aluminum"},
         expect=[("cnc.gap_width_small", None, box(-1.0, -1, 0.75, -0.7, 1, 1)),
                 ("cnc.gap_width_small", None, box(-0.55, -1, 0.75, -0.25, 1, 1)),
                 ("cnc.gap_width", None, box(0.98, -1, 0.8, 1.02, 1, 1)),
                 ("cnc.gap_width_small", None, box(0.98, -1, 0.8, 1.02, 1, 1)),
                 ("cnc.pocket_depth_to_width", None, box(0.98, -1, 0.8, 1.02, 1, 1)),
                 ("cnc.wall_thickness", None, box(-0.7, -1, 0.75, -0.55, 1, 1)),
                 ("cnc.wall_thickness_recommended", None, box(-0.7, -1, 0.75, -0.55, 1, 1))]),
    Case("huge", huge, {"material": "aluminum"}, expect=[("cnc.envelope_length", None, None)]),
    Case("tooled", tooled, {"material": "aluminum", "tools": "3,6"},
         expect=[("cnc.internal_corner_radius", None, box(-10, -7, 3, 10, 7, 6))]),
    Case("cavity-xometry", xometry_cavity, {"material": "aluminum", "rules": "xometry"},
         expect=[("cnc.pocket_depth_to_width", None, box(-15, -3, -1, 15, 3, 20))]),
    Case("windows", windows, {"material": "aluminum", "tools": "3,6,10"},
         expect=[("cnc.internal_corner_radius", None, box(-40, -10, -5, -10, 10, 5)),
                 ("cnc.corner_radius_to_depth", None, box(-40, -10, -5, -10, 10, 5))]),
    Case("through_slot", through_slot, {"material": "aluminum"},
         expect=[("cnc.pocket_depth_to_width", None, box(-35, -1.5, -10, -5, 1.5, 10)),
                 ("cnc.corner_reach", None, box(-35, -1.5, -10, -5, 1.5, 10)),
                 ("cnc.corner_radius_to_depth", None, box(-35, -1.5, -10, -5, 1.5, 10))],
         # the 10 mm slot's R5 ends are a quarter of its 20 mm depth: Hubs' third, a warning on the control too
         allow=[("cnc.corner_radius_to_depth", None, box(5, -5, -10, 35, 5, 10))]),
    Case("webs", webs, {"material": "aluminum"},
         expect=[("cnc.wall_thickness", None, box(-20.3, -0.1, -5, -19.7, 0.1, 5)),
                 ("cnc.wall_thickness_recommended", None, box(-20.3, -0.1, -5, -19.7, 0.1, 5))]),
    Case("knife", knife, {"material": "aluminum"}, expect=[("cnc.knife_edge", None, box(-0.1, -7.5, -0.1, 0.1, 7.5, 0.1))]),
    Case("valley", valley, {"material": "aluminum"}),
    Case("cavity-hubs", xometry_cavity, {"material": "aluminum", "rules": "hubs"},
         allow=[("cnc.corner_radius_to_depth", None, box(-15, -3, -1, 15, 3, 20)),
                ("cnc.corner_reach", None, box(-15, -3, -1, 15, 3, 20))]),
]


def _touches(face_box: Any, region: Box3, slack: float = 0.02) -> bool:
    (x0, y0, z0), (x1, y1, z1) = region
    return (face_box.min.X <= x1 + slack and face_box.max.X >= x0 - slack and face_box.min.Y <= y1 + slack
            and face_box.max.Y >= y0 - slack and face_box.min.Z <= z1 + slack and face_box.max.Z >= z0 - slack)


def _matches(entry: tuple[str, str | None, Box3 | None], rule: str, location: str, faces: dict[str, Any]) -> bool:
    wanted, owner, region = entry
    if wanted != rule:
        return False
    if owner is not None and not location.startswith(owner + "/"):
        return False
    if region is None:
        return True
    face = faces.get(location)
    return face is not None and _touches(face.bounding_box(), region)


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory(prefix="cnc-corpus-")
        cls.results: dict[str, tuple[Case, Any, dict[str, Any]]] = {}
        for case in CASES:
            path = Path(cls.folder.name) / f"{case.name}.step"
            if case.unit is not None:
                bd.export_step(case.build(), str(path), unit=case.unit)
            else:
                bd.export_step(case.build(), str(path))
            result = cad.step.dfm(path, process="cnc", **case.options)
            document = brep.read("step", path)
            faces = {part.ref("face", n): face for part in document.parts
                     for n, face in enumerate(part.faces(), start=1)}
            cls.results[case.name] = (case, result, faces)
        cls.table = cls._score()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.folder.cleanup()

    @classmethod
    def _score(cls) -> dict[str, dict[str, int]]:
        table: dict[str, dict[str, int]] = {}
        cls.misses: list[str] = []
        cls.false: list[str] = []
        for name, (case, result, faces) in cls.results.items():
            record = result.measurements.get("rules") or {}
            failures = [(outcome["rule"], failure["location"]) for outcome in record.get("outcomes", [])
                        for failure in outcome.get("failures", [])]
            for rule, location in failures:
                row = table.setdefault(rule, {"tp": 0, "fp": 0, "planted": 0, "found": 0})
                if any(_matches(entry, rule, location, faces) for entry in case.expect + case.allow):
                    row["tp"] += 1
                else:
                    row["fp"] += 1
                    cls.false.append(f"{name}: {rule} at {location}")
            for entry in case.expect:
                row = table.setdefault(entry[0], {"tp": 0, "fp": 0, "planted": 0, "found": 0})
                row["planted"] += 1
                if any(_matches(entry, rule, location, faces) for rule, location in failures):
                    row["found"] += 1
                else:
                    cls.misses.append(f"{name}: {entry[0]} at {entry[2]}")
        lines = [f"{'rule':34} {'precision':>9} {'recall':>7} {'failures':>8} {'planted':>7}"]
        for rule in sorted(table):
            row = table[rule]
            failures = row["tp"] + row["fp"]
            precision = row["tp"] / failures if failures else 1.0
            recall = row["found"] / row["planted"] if row["planted"] else 1.0
            lines.append(f"{rule:34} {precision:9.2f} {recall:7.2f} {failures:8d} {row['planted']:7d}")
        print("\nCNC planted-defect corpus\n" + "\n".join(lines), file=sys.stderr)
        for line in cls.false:
            print(f"  false positive: {line}", file=sys.stderr)
        for line in cls.misses:
            print(f"  missed: {line}", file=sys.stderr)
        return table

    def test_every_planted_defect_is_found(self) -> None:
        self.assertEqual(self.misses, [])

    def test_no_rule_fails_where_nothing_was_planted(self) -> None:
        self.assertEqual(self.false, [])

    def test_every_family_is_measured(self) -> None:
        for name, (_, result, _) in self.results.items():
            with self.subTest(case=name):
                self.assertFalse(result.measurements["partial"], result.measurements["partial_sections"])

    def test_the_inch_step_is_read_in_millimetres(self) -> None:
        _, result, _ = self.results["inch_plate"]
        self.assertEqual(result.measurements["stock"]["items"][0]["size_mm"], [101.6, 50.8, 12.7])
        diameters = sorted(hole["diameter_mm"] for hole in result.measurements["holes"]["items"])
        self.assertEqual(diameters, [5.08, 6.35])

    def test_the_assembly_reports_each_part(self) -> None:
        _, result, _ = self.results["kit"]
        self.assertEqual(sorted(item["part"] for item in result.measurements["stock"]["items"]), ["bracket", "plate"])

    def test_four_axes_turn_about_the_axis_that_reaches_the_inclined_hole(self) -> None:
        setup = self.results["inclined-4axis"][1].measurements["setups"]["items"][0]
        self.assertEqual(setup["rotary_axis"], [0.0, 1.0, 0.0])
        self.assertEqual(setup["unreached_area_fraction"], 0.0)

    def test_setups_count_the_sides(self) -> None:
        counts = {name: self.results[name][1].measurements["setups"]["items"][0]["setup_count"]
                  for name in ("six_sides", "two_sides")}
        self.assertEqual(counts, {"six_sides": 5, "two_sides": 2})


if __name__ == "__main__":
    unittest.main()
