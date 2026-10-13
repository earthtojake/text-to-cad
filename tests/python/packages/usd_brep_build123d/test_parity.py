"""The same build123d script builds the same solid on usd-brep.

Each case runs once with build123d and once with usd_brep_build123d, and the two solids
must coincide: the volume where they differ (OpenCascade booleans on the exact conversion)
is zero. A case covers a family of the language rather than one call, so a regression in
placement, a mode or a selector moves material and fails it.
"""

from __future__ import annotations

import unittest

from tests.python.packages.usd_brep_build123d.parity import ParityCase, requires_usd_brep


def builder_primitives(m):
    """Primitives with align and rotation, nested Locations, every mode."""
    with m.BuildPart() as p:
        m.Box(20, 10, 5, align=(m.Align.CENTER, m.Align.MIN, m.Align.MIN))
        with m.Locations(m.Location((3, 4, 0)), m.Location((-3, 4, 0))):
            with m.Locations(m.Location((0, 1, -1))):
                m.Cylinder(1.5, 10, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN), mode=m.Mode.SUBTRACT)
        with m.Locations(m.Location((0, 5, 2.5))):
            m.Cylinder(1, 30, rotation=(0, 90, 0), mode=m.Mode.SUBTRACT)
        with m.Locations((8, 8, 5)):
            m.Sphere(2)
            m.Cone(2, 0.5, 3, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN))
        m.Torus(6, 1, rotation=(90, 0, 0), mode=m.Mode.SUBTRACT)
        with m.Locations((-8, 8, 5)):
            m.Cylinder(3, 4, arc_size=120, rotation=(0, 0, 45), align=(m.Align.MIN, m.Align.MIN, m.Align.MIN))
        with m.Locations((0, 5, 0)):
            m.Box(30, 30, 2, mode=m.Mode.INTERSECT)
    return p.part


def builder_sketches(m):
    """Sketches on side planes, a sketch mode, extrude backwards and both ways, revolve."""
    with m.BuildPart() as p:
        with m.BuildSketch(m.Plane.XY):
            m.RectangleRounded(30, 20, 4)
            m.Circle(3, mode=m.Mode.SUBTRACT)
            with m.Locations((10, 0)):
                m.SlotOverall(8, 3, rotation=90, mode=m.Mode.SUBTRACT)
        m.extrude(amount=4)
        with m.BuildSketch(m.Plane.YZ):
            m.Polygon([(-10, 4), (10, 4), (0, 12)], align=None)
        m.extrude(amount=2, both=True)
        with m.BuildSketch(m.Plane.XZ.offset(-10)):
            with m.Locations((-12, 2), (12, 2)):
                m.RegularPolygon(2, 6)
        m.extrude(amount=-3)
        with m.BuildSketch(m.Plane.XZ):
            with m.Locations((14, 8)):
                m.Rectangle(2, 4)
        m.revolve(axis=m.Axis.Z, revolution_arc=90)
    return p.part


def builder_locations_and_holes(m):
    """PolarLocations, GridLocations, Hole, CounterBoreHole, CounterSinkHole."""
    with m.BuildPart() as p:
        m.Cylinder(30, 10, align=(m.Align.CENTER, m.Align.CENTER, m.Align.MIN))
        with m.Locations((0, 0, 10)):
            with m.PolarLocations(22, 6, start_angle=15):
                m.CounterBoreHole(2, 3.5, 2)
            with m.GridLocations(8, 8, 2, 2):
                m.CounterSinkHole(1.5, 3, depth=6)
        with m.PolarLocations(12, 3):
            m.Hole(2)
    return p.part


def builder_selectors_and_blends(m):
    """Fillet and chamfer through selectors inside the builder. (A selection must not hinge on
    the order of ties: the two kernels list a part's edges in different orders.)"""
    with m.BuildPart() as p:
        m.Box(40, 30, 10)
        m.Cylinder(6, 30, mode=m.Mode.SUBTRACT)
        m.fillet(p.edges().filter_by(m.Axis.Z), radius=3)
        m.chamfer(p.edges().group_by(m.Axis.Z)[-1], length=1)
        bottom = p.edges().filter_by(m.GeomType.CIRCLE).group_by(m.Axis.Z)[0]
        m.fillet(bottom.sort_by(m.SortBy.RADIUS)[-1:], radius=1)
    return p.part


def builder_mirror_and_split(m):
    with m.BuildPart() as p:
        with m.Locations((8, 0, 0)):
            m.Box(10, 6, 4)
            m.Cylinder(2, 8, mode=m.Mode.SUBTRACT)
        m.mirror(about=m.Plane.YZ)
        m.split(bisect_by=m.Plane.XZ.offset(-1), keep=m.Keep.BOTTOM)
    return p.part


def algebra_mode(m):
    """Pos/Rot placement, list booleans, a sketch placed by a rotated plane, mirror."""
    plate = m.Box(30, 20, 4) - [m.Pos(x, 0, 0) * m.Cylinder(2, 10) for x in (-10, 0, 10)]
    rib = m.Rot(0, 0, 30) * m.Box(25, 2, 8)
    part = plate + m.Pos(0, 0, 4) * rib
    slot = m.Plane.XY.rotated((0, 0, 90)) * m.SlotOverall(12, 4)
    part = part - m.extrude(m.Pos(5, 0, -5) * slot, amount=10)
    return m.mirror(part, m.Plane.YZ.offset(16)) + part


def algebra_moves(m):
    """moved/located/rotate/translate and an assembly of disjoint parts."""
    base = m.Cylinder(5, 2).moved(m.Location((0, 0, 1)))
    arm = m.Box(12, 2, 2).translate((6, 0, 3)).rotate(m.Axis.Z, 30)
    head = m.Sphere(2).located(m.Location((10, 6, 3)))
    return (base + arm).fuse(head)


def shell_and_scale(m):
    """offset with an opening (a shell), then a uniform scale."""
    box = m.Box(20, 14, 10)
    top = box.faces().sort_by(m.Axis.Z)[-1]
    cup = m.offset(box, amount=-1.5, openings=top)
    return m.scale(cup, by=1.5)


@requires_usd_brep
class SameSolid(ParityCase):
    def test_builder_primitives(self):
        self.assertSameSolid(builder_primitives)

    def test_builder_sketches(self):
        self.assertSameSolid(builder_sketches)

    def test_builder_locations_and_holes(self):
        self.assertSameSolid(builder_locations_and_holes)

    def test_builder_selectors_and_blends(self):
        self.assertSameSolid(builder_selectors_and_blends)

    def test_builder_mirror_and_split(self):
        self.assertSameSolid(builder_mirror_and_split)

    def test_algebra_mode(self):
        self.assertSameSolid(algebra_mode)

    def test_algebra_moves(self):
        self.assertSameSolid(algebra_moves)

    def test_shell_and_scale(self):
        self.assertSameSolid(shell_and_scale)


if __name__ == "__main__":
    unittest.main()
