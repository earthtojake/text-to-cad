"""The GeomAbs_* enum families overlap numerically, so the name memo must key on type.

OCP's pybind11 enums compare and hash by their underlying int, and the families
collide: ``GeomAbs_Line``/``GeomAbs_Plane``/``GeomAbs_C0`` are all 0, and
``GeomAbs_Circle``/``GeomAbs_Cylinder``/``GeomAbs_G1`` are all 1. Memoized on the
value alone, whichever family reached a given int first answered for all of them
for the rest of the process — and since faces are extracted before edges, every
curve came back named after a surface.
"""

from __future__ import annotations

import unittest

from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_Shape, GeomAbs_SurfaceType

from cadgen._internal.step_scene import _enum_name


class EnumNameMemoTest(unittest.TestCase):

    def test_curve_names_survive_a_face_pass_first(self) -> None:
        # Extraction order: surfaces, then curves. This is the exact sequence that
        # used to report a circle as "cylinder" and a line as "plane".
        self.assertEqual("cylinder", _enum_name(GeomAbs_SurfaceType.GeomAbs_Cylinder, "GeomAbs_"))
        self.assertEqual("plane", _enum_name(GeomAbs_SurfaceType.GeomAbs_Plane, "GeomAbs_"))
        self.assertEqual("circle", _enum_name(GeomAbs_CurveType.GeomAbs_Circle, "GeomAbs_"))
        self.assertEqual("line", _enum_name(GeomAbs_CurveType.GeomAbs_Line, "GeomAbs_"))


    def test_continuity_shares_the_same_numbering_and_stays_distinct(self) -> None:
        self.assertEqual("c0", _enum_name(GeomAbs_Shape.GeomAbs_C0, "GeomAbs_"))
        self.assertEqual("g1", _enum_name(GeomAbs_Shape.GeomAbs_G1, "GeomAbs_"))
        self.assertEqual("line", _enum_name(GeomAbs_CurveType.GeomAbs_Line, "GeomAbs_"))
        self.assertEqual("plane", _enum_name(GeomAbs_SurfaceType.GeomAbs_Plane, "GeomAbs_"))


if __name__ == "__main__":
    unittest.main()
