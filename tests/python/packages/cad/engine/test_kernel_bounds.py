"""A free-form shape's bounds reach its extrema (kernel/bounds.py, ``optimal_box``). OCP 8.0.1's
``BRepBndLib.AddOptimal`` can stop short of a B-spline surface's extremum (OCCT #1604): a sphere
scaled to semi-axes 20, 10 and 5 measures xmin -19.83 there, not -20. ``optimal_box`` measures
free-form faces by their distance to support planes instead, and this holds that workaround to
the shapes of issue #702 until a released OCP fixes the native call."""

from __future__ import annotations

import math
import unittest

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.kernel.bounds import box_limits, optimal_box  # noqa: E402

AXES = (20.0, 10.0, 5.0)


def ellipsoid(turn_degrees: float = 0.0, shift: tuple[float, float, float] = (0.0, 0.0, 0.0)):
    """A unit sphere scaled to ``AXES`` (a non-uniform scale makes its face a B-spline), turned
    about Z and moved."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax1, gp_Dir, gp_GTrsf, gp_Mat, gp_Pnt, gp_Trsf, gp_Vec

    scale = gp_GTrsf()
    scale.SetVectorialPart(gp_Mat(AXES[0], 0, 0, 0, AXES[1], 0, 0, 0, AXES[2]))
    shape = BRepBuilderAPI_GTransform(BRepPrimAPI_MakeSphere(1.0).Shape(), scale, True).Shape()
    place = gp_Trsf()
    place.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(turn_degrees))
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(*shift))
    return BRepBuilderAPI_Transform(shape, move.Multiplied(place), True).Shape()


def expected(turn_degrees: float, shift: tuple[float, float, float]) -> tuple[float, ...]:
    """The ellipsoid's exact box: turned about Z by t, its half-widths are sqrt(a²cos²t + b²sin²t)
    along X, sqrt(a²sin²t + b²cos²t) along Y, and c along Z."""
    a, b, c = AXES
    t = math.radians(turn_degrees)
    half = (math.hypot(a * math.cos(t), b * math.sin(t)), math.hypot(a * math.sin(t), b * math.cos(t)), c)
    return (*(s - h for s, h in zip(shift, half)), *(s + h for s, h in zip(shift, half)))


class FreeFormBoundsTest(unittest.TestCase):
    # The box may be a hair larger than the shape (its tolerance); it must never be smaller.
    INSIDE = 1e-4
    OUTSIDE = 1e-2

    def assert_box(self, shape, want: tuple[float, ...]) -> None:
        got = box_limits(optimal_box(shape))
        for axis, (low, high) in enumerate(zip(got[:3], got[3:])):
            with self.subTest(axis="xyz"[axis]):
                self.assertLessEqual(low, want[axis] + self.INSIDE, f"min {low} stops short of {want[axis]}")
                self.assertGreaterEqual(high, want[axis + 3] - self.INSIDE, f"max {high} stops short of {want[axis + 3]}")
                self.assertGreater(low, want[axis] - self.OUTSIDE)
                self.assertLess(high, want[axis + 3] + self.OUTSIDE)

    def test_a_scaled_sphere_reaches_its_semi_axes(self) -> None:
        self.assert_box(ellipsoid(), expected(0.0, (0.0, 0.0, 0.0)))

    def test_a_turned_and_moved_ellipsoid_reaches_its_extrema(self) -> None:
        for turn in (17.0, 45.0, 90.0):
            with self.subTest(turn=turn):
                shift = (5.0, -3.0, 2.0)
                self.assert_box(ellipsoid(turn, shift), expected(turn, shift))


if __name__ == "__main__":
    unittest.main()
