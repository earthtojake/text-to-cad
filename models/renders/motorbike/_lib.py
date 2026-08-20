"""Shared geometry vocabulary for the motorbike package.

Every helper here is pure build123d algebra-mode and positions geometry in
WORLD (bike-frame) coordinates. Probes in the repo tmp/ verified the API
contracts these rely on:

- ``revolve`` honors a world ``Axis`` with position; profiles are anchored on
  a ``Plane`` whose local x runs radially and local y equals world +Y, with
  ``x_dir`` pre-rotated to the start angle for partial revolves.
- ``loft`` through positioned ``RectangleRounded`` faces (smooth, not ruled).
- ``sweep`` of a ``Circle`` along a ``Spline`` path is BOP-clean.
- transforms compose in ONE ``.moved()`` call; chained ``.moved()`` calls
  accumulate translations and double-place geometry.
"""

from __future__ import annotations

from math import cos, sin, tau

from build123d import (
    Axis,
    Circle,
    Color,
    Cylinder,
    Location,
    Plane,
    Pos,
    Rectangle,
    RectangleRounded,
    Spline,
    Torus,
    Vector,
    loft,
    revolve,
    sweep,
)

from cadgen.assembly import label_shape

__all__ = [
    "paint",
    "axis_cylinder",
    "axis_ring",
    "tube",
    "paint_tube",
    "revolve_band",
    "loft_x_sections",
    "loft_path_xz",
    "coil_between",
    "paint_compound",
]


def paint(shape, name, *details, color):
    """Assign native label + color metadata and return the shape."""
    return label_shape(shape, name, *details, color=Color(*color))


def paint_compound(children, label):
    """Wrap labeled children in a compound carrying the part-level label."""
    from build123d import Compound

    return Compound(children=list(children), label=label)


def axis_cylinder(center, axis, radius, height):
    """Cylinder of given radius/height centered on ``center``, axis ``axis``."""
    z_dir = Vector(axis).normalized()
    plane = Plane(origin=Vector(center), z_dir=z_dir)
    return Cylinder(radius, height).moved(plane.location)


def axis_ring(center, axis, outer_r, bore_r, width):
    """Ring: outer cylinder with a through bore, both on the same axis."""
    body = axis_cylinder(center, axis, outer_r, width)
    bore = axis_cylinder(center, axis, bore_r, width + 2.0)
    return body - bore


def tube(points, od):
    """Round tube swept along a spline through 3D points."""
    pts = [Vector(p) for p in points]
    path = Spline(*pts)
    start_dir = (pts[1] - pts[0]).normalized()
    section = Circle(od / 2).moved(
        Plane(origin=pts[0], z_dir=start_dir).location
    )
    return sweep(section, path)


def paint_tube(points, od, name, *details, color):
    return paint(tube(points, od), name, *details, color=color)


def _radial_plane(axle, angle_deg):
    """Plane at the axle whose local x points at ``angle_deg`` (from +X toward
    +Z) and whose local y equals world +Y — the profile frame for revolving
    about the wheel axis."""
    a = float(angle_deg)
    x_dir = (cos(_d2r(a)), 0.0, sin(_d2r(a)))
    z_dir = (-sin(_d2r(a)), 0.0, cos(_d2r(a)))
    return Plane(origin=Vector(axle), x_dir=x_dir, z_dir=z_dir)


def _d2r(deg):
    return deg * 3.141592653589793 / 180.0


def revolve_band(axle, r_mid, band_t, half_width, a0, a1, corner=4.0):
    """Partial annular band (fender) around the Y axis through ``axle``,
    spanning ``a0..a1`` degrees from +X toward +Z."""
    plane = _radial_plane(axle, a0)
    profile = Pos(r_mid, 0, 0) * RectangleRounded(band_t, 2 * half_width, corner)
    return revolve(
        profile.moved(plane.location),
        Axis(Vector(axle), (0.0, -1.0, 0.0)),
        revolution_arc=a1 - a0,
    )


def loft_x_sections(sections, corner):
    """Loft through YZ-plane rounded rectangles given as
    ``(x, half_width, z_bottom, z_top)`` — for body parts that vary along X."""
    faces = []
    for x, half_w, z0, z1 in sections:
        plane = Plane(
            origin=(x, 0.0, (z0 + z1) / 2),
            x_dir=(0, 1, 0),
            z_dir=(1, 0, 0),
        )
        faces.append(
            RectangleRounded(2 * half_w, z1 - z0, min(corner, (z1 - z0) / 2.05, half_w / 1.05))
            .moved(plane.location)
        )
    return loft(faces)


def loft_path_xz(sections, thickness, corner):
    """Loft along a curved side-view path given as
    ``(x, z, half_width)`` sections; each section is a rounded rectangle
    ``2*half_width`` wide (along Y) by ``thickness`` deep along the path
    normal (leg shield, front cover)."""
    pts = [(float(x), float(z)) for x, z, _ in sections]
    tangents = []
    for i in range(len(pts)):
        if i == 0:
            t = Vector(pts[1][0] - pts[0][0], 0, pts[1][1] - pts[0][1]).normalized()
        elif i == len(pts) - 1:
            t = Vector(pts[i][0] - pts[i - 1][0], 0, pts[i][1] - pts[i - 1][1]).normalized()
        else:
            a = Vector(pts[i + 1][0] - pts[i][0], 0, pts[i + 1][1] - pts[i][1])
            b = Vector(pts[i][0] - pts[i - 1][0], 0, pts[i][1] - pts[i - 1][1])
            t = (a.normalized() + b.normalized()).normalized()
        tangents.append(t)
    faces = []
    for (x, z, half_w), t in zip(sections, tangents):
        plane = Plane(origin=(x, 0.0, z), x_dir=(0, 1, 0), z_dir=t)
        faces.append(
            RectangleRounded(2 * half_w, thickness, min(corner, thickness / 2.05))
            .moved(plane.location)
        )
    return loft(faces)


def coil_between(p0, p1, mean_d, wire_d, turns, segments_per_turn=20):
    """Compression coil running straight from ``p0`` to ``p1``.

    Tangent-aligned overlapping cylinder segments (the repo's proven spring
    pattern — exact helix sweeps hold the render mesh at ~600k triangles).
    """
    import math

    start, end = Vector(p0), Vector(p1)
    axis = (end - start).normalized()
    length = (end - start).length
    ref = Vector(0, 1, 0) if abs(axis.Y) < 0.9 else Vector(1, 0, 0)
    u = (ref - axis * ref.dot(axis)).normalized()
    v = axis.cross(u)
    r_mean, r_wire = mean_d / 2, wire_d / 2
    segments = max(8, round(turns * segments_per_turn))
    points = []
    for i in range(segments + 1):
        ang = turns * tau * i / segments
        radial = u * (r_mean * cos(ang)) + v * (r_mean * sin(ang))
        points.append(start + axis * (length * i / segments) + radial)
    links = [
        axis_cylinder(
            tuple((a + b) * 0.5),
            tuple((b - a).normalized()),
            r_wire,
            (b - a).length + wire_d,
        )
        for a, b in zip(points, points[1:])
    ]
    return links[0].fuse(*links[1:])
