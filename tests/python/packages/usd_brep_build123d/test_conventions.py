"""Where usd-brep and OpenCascade disagree, the package behaves as build123d (OpenCascade) does.

These are the rules a direct mapping of build123d's calls onto usd-brep gets wrong without
an error: each was found by building real models both ways and seeing a different part.
"""

from __future__ import annotations

import unittest

from tests.python.packages.usd_brep_build123d.parity import ParityCase, requires_usd_brep


def rounded_plate(m):
    with m.BuildPart() as p:
        with m.BuildSketch():
            m.RectangleRounded(100, 70, 5)
        m.extrude(amount=8)
        m.Cylinder(14, 20, mode=m.Mode.SUBTRACT)
    return p.part


def triangular_prism(m):
    with m.BuildPart() as p:
        with m.BuildSketch():
            m.Polygon([(0, 0), (20, 0), (0, 12)], align=None)
        m.extrude(amount=8)
    return p.part


@requires_usd_brep
class OpenCascadeConventions(ParityCase):
    def test_shapes_are_values(self):
        """usd-brep's booleans consume their operands and its fillets edit in place."""
        ub = self.ub
        box, pin = ub.Box(10, 10, 10), ub.Cylinder(2, 20)
        cut = box - pin
        rounded = ub.fillet(cut.edges().filter_by(ub.Axis.Z), radius=1)
        self.assertAlmostEqual(box.volume, 1000.0, places=6)
        self.assertGreater(pin.volume, 0)
        self.assertGreater(cut.volume, rounded.volume)
        self.assertEqual(len(cut.faces()), 7)

    def test_a_fillet_follows_the_tangent_chain(self):
        """OpenCascade rounds the whole tangent-continuous loop through one straight edge."""
        def one_edge(m):
            part = rounded_plate(m)
            top = part.edges().filter_by(lambda e: abs(e.center().Z - 8) < 1e-9)
            straight = top.filter_by(m.GeomType.LINE).sort_by(m.Axis.Y)[0]
            return m.fillet(straight, radius=0.8)

        self.assertSameSolid(one_edge)

    def test_seams_and_tangent_edges_are_skipped_or_refused(self):
        """Mixed in, smooth edges are ignored; alone, the fillet fails as in build123d."""
        def smooth_edges(m, part):
            return [e for e in part.edges() if e.geom_type == m.GeomType.LINE and e.bounding_box().size.Z > 1]

        for m in (self.b3d, self.ub):
            with self.subTest(library=m.__name__), self.assertRaises(ValueError):
                part = rounded_plate(m)
                part.fillet(0.8, smooth_edges(m, part))
        self.assertSameSolid(lambda m: m.fillet(rounded_plate(m).edges(), radius=0.8))

    def test_chamfer_length_is_the_setback_at_any_angle(self):
        for corner in range(3):
            with self.subTest(corner=corner):
                def chamfered(m, corner=corner):
                    part = triangular_prism(m)
                    vertical = part.edges().filter_by(m.Axis.Z).sort_by(lambda e: (round(e.center().X, 6), round(e.center().Y, 6)))
                    return m.chamfer(vertical[corner], length=1.0)

                self.assertSameSolid(chamfered)

    def test_edges_report_build123d_types(self):
        """usd-brep makes sketch arcs and extruded-arc seams B-splines, and approximates the
        circles where a torus groove meets a cylinder; selectors see lines and circles."""
        def grooved(m):
            with m.BuildPart() as p:
                with m.BuildSketch():
                    m.RectangleRounded(60, 40, 6)
                m.extrude(amount=16)
                with m.Locations((0, 0, 8)):
                    m.Cylinder(15, 16, mode=m.Mode.SUBTRACT)
                    m.Torus(16.2, 3.0, mode=m.Mode.SUBTRACT)
            return p.part

        expected, actual = grooved(self.b3d), grooved(self.ub)
        for kind in ("LINE", "CIRCLE"):
            with self.subTest(kind=kind):
                self.assertEqual(len(expected.edges().filter_by(getattr(self.b3d.GeomType, kind))),
                                 len(actual.edges().filter_by(getattr(self.ub.GeomType, kind))))
        radii = sorted(round(e.radius, 6) for e in actual.edges().filter_by(self.ub.GeomType.CIRCLE))
        self.assertEqual(radii, sorted(round(e.radius, 6) for e in expected.edges().filter_by(self.b3d.GeomType.CIRCLE)))

    def test_a_fillet_that_leaves_no_material_raises(self):
        """usd-brep returned a body with no solid region for this fillet; OpenCascade raises."""
        def cover(m):
            with m.BuildPart() as p:
                with m.BuildSketch(m.Plane.XY):
                    m.RectangleRounded(90, 60, 4)
                m.extrude(amount=4)
                with m.Locations(m.Location((0, 0, 4))):
                    with m.BuildSketch(m.Plane.XY):
                        m.RectangleRounded(80, 50, 3)
                    m.extrude(amount=3)
                with m.Locations(m.Location((0, 0, 3.2))):
                    m.Box(58, 28, 4.2, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN), mode=m.Mode.SUBTRACT)
                with m.Locations(m.Location((0, 0, 4))):
                    m.Box(66, 36, 4, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN), mode=m.Mode.SUBTRACT)
            return p.part

        for m in (self.b3d, self.ub):
            part = cover(m)
            lines = [e for e in part.edges() if str(e.geom_type).endswith("LINE")]
            with self.subTest(library=m.__name__), self.assertRaises(ValueError):
                m.fillet(lines, radius=0.5)

    def test_builder_quirks_are_build123d_quirks(self):
        """A sketch ignores an enclosing Locations; a builder opened in another function is
        not a child of the one that is open."""
        def sketch_in_locations(m):
            with m.BuildPart() as p:
                m.Box(20, 20, 4, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN))
                with m.Locations(m.Location((0, 0, 4))):
                    with m.BuildSketch(m.Plane.XY):
                        m.Circle(5)
                    m.extrude(amount=10)
            return p.part

        def helper_builder(m):
            def peg():
                with m.BuildPart() as inner:
                    m.Cylinder(2, 10, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN))
                return inner.part.moved(m.Location((5, 0, 4)))

            with m.BuildPart() as p:
                m.Box(20, 20, 4, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN))
                m.add(peg())
            return p.part

        self.assertSameSolid(sketch_in_locations)
        self.assertSameSolid(helper_builder)


if __name__ == "__main__":
    unittest.main()
