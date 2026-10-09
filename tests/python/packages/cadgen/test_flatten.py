"""Flat patterns stay EXACT: an arc that goes in comes out an arc.

``cadgen.flatten`` used to sample every wire into points, union polygons in
shapely, and emit polylines — so a filleted corner reached the DXF as a run of
chords at a resolution nobody chose, and kerf compensation compounded it. The
union and the offset are OCC operations on the real faces now,
with shapely kept only for the degenerate unions OCC
refuses.

The tests below are about the CURVES, because that is what changed. Counting
DXF entity types is the honest way to ask: a polygonized profile has no ARCs.
"""

from __future__ import annotations

import collections
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


def _plate():
    """A plate with everything a cut profile can have: rounded corners, round
    holes, and a slot (two arcs joined by lines)."""
    import build123d as bd

    with bd.BuildPart() as part:
        with bd.BuildSketch():
            bd.RectangleRounded(70, 40, 6)
            with bd.Locations((-26, 0), (26, 0)):
                bd.Circle(3.25, mode=bd.Mode.SUBTRACT)
            bd.SlotOverall(24, 8, mode=bd.Mode.SUBTRACT)
        bd.extrude(amount=6)
    return part.part


def _entity_kinds(shape) -> dict[str, int]:
    from cadgen._internal.dxf_emit import emit_dxf

    _, document = emit_dxf(shape, label="flatten-test")
    return dict(collections.Counter(entity.dxftype() for entity in document.modelspace()))


class FlatPatternTests(unittest.TestCase):
    def test_a_flat_pattern_keeps_arcs_and_circles(self) -> None:
        from cadgen import flatten

        kinds = _entity_kinds(flatten.flat_pattern(_plate(), coordinate=6.0))
        self.assertEqual(kinds.get("ARC"), 6, "four corner fillets and two slot ends")
        self.assertEqual(kinds.get("CIRCLE"), 2, "two bolt holes")
        self.assertNotIn("LWPOLYLINE", kinds, "an exact profile emits no sampled polyline")

    def test_kerf_compensation_keeps_arcs(self) -> None:
        """The reason the shapely path stopped being primary: its buffer()
        turned every offset curve into chords."""
        from cadgen import flatten

        kinds = _entity_kinds(flatten.flat_pattern(_plate(), coordinate=6.0, kerf=0.2))
        self.assertEqual(kinds.get("ARC"), 6)
        self.assertEqual(kinds.get("CIRCLE"), 2)

    def test_kerf_changes_the_geometry_in_the_right_direction(self) -> None:
        from cadgen import flatten

        plate = _plate()
        plain = flatten.flat_pattern(plate, coordinate=6.0)
        grown = flatten.flat_pattern(plate, coordinate=6.0, kerf=0.2)
        shrunk = flatten.flat_pattern(plate, coordinate=6.0, kerf=-0.2)
        self.assertGreater(grown.area, plain.area)
        self.assertLess(shrunk.area, plain.area)

    def test_flatten_face_lands_the_face_on_z_zero(self) -> None:
        import build123d as bd

        from cadgen import flatten

        raised = bd.Location((3, -4, 12)) * bd.Rectangle(10, 5).face()
        flat = flatten.flatten_face(raised)
        self.assertLess(max(abs(v.Z) for v in flat.vertices()), 1e-9)
        self.assertAlmostEqual(flat.area, raised.area, places=6)

    def test_planar_faces_raises_when_the_selection_is_empty(self) -> None:
        """An empty selection means the plane or the sign is wrong. Returning
        nothing would write an empty drawing that nobody notices."""
        from cadgen import flatten

        with self.assertRaises(RuntimeError):
            flatten.planar_faces(
                _plate(),
                normal_axis="z",
                normal_sign=1.0,
                coordinate_axis="z",
                coordinate=999.0,
            )

    def test_an_impossible_offset_says_what_went_wrong(self) -> None:
        import build123d as bd

        from cadgen import flatten

        with self.assertRaises(RuntimeError) as caught:
            flatten.offset_profile(bd.Rectangle(2, 2).face(), -5.0)
        self.assertIn("consumes it entirely", str(caught.exception))


class UnionTests(unittest.TestCase):
    def test_overlapping_faces_fuse_into_one(self) -> None:
        import build123d as bd

        from cadgen import flatten

        left = bd.Rectangle(10, 5).face()
        right = bd.Pos(5, 0) * bd.Rectangle(10, 5).face()
        fused = flatten.union_faces([left, right])
        self.assertEqual(len(fused.faces()), 1)
        self.assertAlmostEqual(fused.area, 15 * 5, places=6)
        self.assertEqual(_entity_kinds(fused), {"LINE": 4}, "the shared edge is gone")

    def test_disjoint_faces_stay_a_nested_layout(self) -> None:
        import build123d as bd

        from cadgen import flatten

        left = bd.Rectangle(10, 5).face()
        right = bd.Pos(30, 0) * bd.Rectangle(10, 5).face()
        fused = flatten.union_faces([left, right])
        self.assertEqual(len(fused.faces()), 2)
        self.assertEqual(_entity_kinds(fused), {"LINE": 8})

    def test_a_single_face_passes_through_untouched(self) -> None:
        import build123d as bd

        from cadgen import flatten

        face = bd.Rectangle(10, 5).face()
        self.assertIs(flatten.union_faces([face]), face)

    def test_no_faces_is_an_error(self) -> None:
        from cadgen import flatten

        with self.assertRaises(RuntimeError):
            flatten.union_faces([])

    def test_the_shapely_fallback_still_produces_a_usable_profile(self) -> None:
        """It is the fallback, and it costs curvature: the rebuilt profile is
        polygonal. That is the trade, and it is why nothing reaches for it by
        choice."""
        import build123d as bd

        from cadgen import flatten

        left = bd.Rectangle(10, 5).face()
        right = bd.Pos(5, 0) * bd.Rectangle(10, 5).face()
        rebuilt = flatten._shapely_union_fallback([left, right], cause=RuntimeError("forced"))
        self.assertAlmostEqual(rebuilt.area, 15 * 5, places=3)
        kinds = _entity_kinds(rebuilt)
        self.assertNotIn("ARC", kinds)
        self.assertGreater(kinds.get("LINE", 0), 4, "sampled, not exact")


if __name__ == "__main__":
    unittest.main()
