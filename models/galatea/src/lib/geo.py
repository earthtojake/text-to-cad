"""Geometry builders: turned parts, machined plates and lofted shells.

Three families cover the whole robot:

- turned parts: a closed (r, z) polygon revolved about an axis (`revolve`);
- machined plates: a 2D outline made of tangent "bones" (the hull of two circles) with
  holes, extruded between two parallel planes (`bones`, `plate_yz`, `plate_xz`, `plate_xy`);
- shells: a loft through superellipse sections (`S`, `loft`), hollowed by a second,
  inset loft (`shell`) and trimmed by the caller.
"""

import math

import build123d as bd

from .kit import frame


# ---------------------------------------------------------------------------------------------
# Primitives placed in the world
# ---------------------------------------------------------------------------------------------
def cyl(radius, height, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), centered=False):
    """A cylinder from `origin` along `axis`, or centred on `origin`."""
    z_align = bd.Align.CENTER if centered else bd.Align.MIN
    return frame(origin, axis) * bd.Cylinder(radius, height, align=(bd.Align.CENTER, bd.Align.CENTER, z_align))


def tube(r_out, r_in, height, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), centered=False):
    z_align = bd.Align.CENTER if centered else bd.Align.MIN
    align = (bd.Align.CENTER, bd.Align.CENTER, z_align)
    shift = 0.0 if centered else -1.0
    ring = bd.Cylinder(r_out, height, align=align) - bd.Pos(0, 0, shift) * bd.Cylinder(r_in, height + 2.0, align=align)
    return frame(origin, axis) * ring


def box(dx, dy, dz, center=(0.0, 0.0, 0.0)):
    return bd.Pos(*center) * bd.Box(dx, dy, dz)


def rod(p0, p1, radius):
    """A round bar from p0 to p1."""
    v = bd.Vector(*p1) - bd.Vector(*p0)
    return cyl(radius, v.length, p0, (v.X, v.Y, v.Z))


def revolve(points, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), x_dir=None):
    """A turned part: the closed (r, z) polygon `points` revolved about local Z, then placed."""
    outline = bd.Polyline(*[(r, 0.0, z) for r, z in points], close=True)
    solid = bd.revolve(bd.Face(bd.Wire(outline.edges())), bd.Axis.Z, 360.0)
    return frame(origin, axis, x_dir) * solid


def hex_prism(across_flats, height, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0)):
    radius = across_flats / math.sqrt(3.0)
    return frame(origin, axis) * bd.extrude(bd.RegularPolygon(radius, 6), amount=height)


def half_space(point, normal, size=3000.0):
    """Everything on the side of the plane through `point` that `normal` points to."""
    return frame(point, normal) * bd.Box(size, size, size, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


# ---------------------------------------------------------------------------------------------
# Machined plates
# ---------------------------------------------------------------------------------------------
def hull(circles):
    """The convex outline around circles [(u, v, r), ...]: tangent lines between round ends."""
    edges = []
    for u, v, r in circles:
        edges.extend((bd.Pos(u, v) * bd.Circle(r)).edges())
    return bd.make_hull(edges)


def bones(circles, links=None, holes=(), cuts=()):
    """A plate outline: the union of the hulls of linked circles (a chain of pairs by default;
    a link may name one circle or several), minus round `holes` [(u, v, r), ...] and any 2D
    `cuts` (a `slot`, say)."""
    if links is None:
        links = [(i, i + 1) for i in range(len(circles) - 1)]
    face = None
    for link in links:
        if len(link) == 1:
            u, v, r = circles[link[0]]
            piece = bd.Pos(u, v) * bd.Circle(r)
        else:
            piece = hull([circles[i] for i in link])
        face = piece if face is None else face + piece
    for u, v, r in holes:
        face = face - bd.Pos(u, v) * bd.Circle(r)
    for tool in cuts:
        face = face - tool
    return face


def slot(u0, v0, u1, v1, radius):
    """A rounded 2D slot between two points, for `bones(cuts=...)`."""
    return hull([(u0, v0, radius), (u1, v1, radius)])


def polygon(*points):
    """A 2D outline from corner points (u, v)."""
    return bd.Polygon(*points, align=None)


def behind_curve(points, closing):
    """A 2D region bounded by a smooth curve through `points` and straight lines through
    `closing` back to its start: the tool that trims a skin along a flowing edge."""
    curve = bd.Spline(*[(u, v, 0.0) for u, v in points])
    ring = [points[-1], *closing, points[0]]
    lines = bd.Polyline(*[(u, v, 0.0) for u, v in ring])
    return bd.Face(bd.Wire([curve, *lines.edges()]))


def band(points, width):
    """A thin 2D ribbon following a smooth curve through `points`, `width` tall in v: the
    tool that scores a reveal line across a skin."""
    lower = bd.Spline(*[(u, v, 0.0) for u, v in points])
    upper = bd.Spline(*[(u, v + width, 0.0) for u, v in reversed(points)])
    (u0, v0), (u1, v1) = points[0], points[-1]
    return bd.Face(bd.Wire([lower, bd.Line((u1, v1, 0), (u1, v1 + width, 0)), upper,
                            bd.Line((u0, v0 + width, 0), (u0, v0, 0))]))


def plate_yz(face, x0, x1):
    """Extrude a (u, v) = (y, z) outline from x0 to x1."""
    lo, hi = min(x0, x1), max(x0, x1)
    loc = bd.Plane(origin=(lo, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)).location
    return loc * bd.extrude(face, amount=hi - lo, dir=(0, 0, 1))


def plate_xz(face, y0, y1):
    """Extrude a (u, v) = (x, z) outline from y0 to y1."""
    lo, hi = min(y0, y1), max(y0, y1)
    loc = bd.Plane(origin=(0, hi, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0)).location
    return loc * bd.extrude(face, amount=hi - lo, dir=(0, 0, 1))


def plate_xy(face, z0, z1):
    """Extrude a (u, v) = (x, y) outline from z0 to z1."""
    lo, hi = min(z0, z1), max(z0, z1)
    return bd.Pos(0, 0, lo) * bd.extrude(face, amount=hi - lo, dir=(0, 0, 1))


# ---------------------------------------------------------------------------------------------
# Lofted shells
# ---------------------------------------------------------------------------------------------
def S(z, cx=0.0, cy=0.0, rx=50.0, ry=50.0, n=2.5, rxn=None, ryn=None):
    """One loft section at height z: a superellipse of exponent n centred (cx, cy), with
    half-widths rx toward +X and rxn toward -X, ry toward +Y (back) and ryn toward -Y (front)."""
    return (z, cx, cy, rx, rx if rxn is None else rxn, ry, ry if ryn is None else ryn, n)


def _section_points(sec, shrink, count, seam):
    z, cx, cy, rxp, rxn, ryp, ryn, n = sec
    e = 2.0 / n
    points = []
    for i in range(count):
        t = math.radians(seam) + 2.0 * math.pi * i / count
        c, s = math.cos(t), math.sin(t)
        rx = (rxp if c >= 0 else rxn) - shrink
        ry = (ryp if s >= 0 else ryn) - shrink
        points.append((cx + rx * math.copysign(abs(c) ** e, c), cy + ry * math.copysign(abs(s) ** e, s), z))
    return points


def section_face(sec, shrink=0.0, count=40, seam=90.0):
    return bd.Face(bd.Wire([bd.Spline(*_section_points(sec, shrink, count, seam), periodic=True)]))


def _extrapolate(a, b, dz):
    f = dz / (b[0] - a[0])
    return tuple(b[k] + (b[k] - a[k]) * f for k in range(7)) + (b[7],)


def loft(rows, shrink=0.0, extend=0.0, bottom=None, top=None, count=40, seam=90.0):
    """A solid lofted through sections (rows of `S`), bottom to top. `shrink` insets every
    section, `extend` continues the loft past both ends (or (low, high) for each), and
    `bottom`/`top` close an end in a point instead of a flat. `seam` is the angle, from +X
    toward +Y, of the surface's one seam line: put it where the skin is cut away."""
    rows = sorted(rows)
    lo, hi = extend if isinstance(extend, tuple) else (extend, extend)
    if lo:
        rows = [_extrapolate(rows[1], rows[0], -lo), *rows]
    if hi:
        rows = [*rows, _extrapolate(rows[-2], rows[-1], hi)]
    sections = [section_face(row, shrink, count, seam) for row in rows]
    if bottom is not None:
        sections.insert(0, bottom if isinstance(bottom, bd.Vertex) else bd.Vertex(*bottom))
    if top is not None:
        sections.append(top if isinstance(top, bd.Vertex) else bd.Vertex(*top))
    return bd.loft(sections)


def shell(rows, thickness=2.6, count=40, bottom=None, top=None, seam=90.0):
    """A thin-walled skin: (skin, cavity, outer). The skin is open at each flat end; the
    cavity is the solid inside it, which trims a mount pad to the skin's inner surface; the
    outer solid seats a screw on the skin's outside (`seat`)."""
    outer = loft(rows, bottom=bottom, top=top, count=count, seam=seam)
    inset = lambda v, d: None if v is None else (v[0], v[1], v[2] + d)
    cavity = loft(rows, shrink=thickness, extend=(0.0 if bottom else 10.0, 0.0 if top else 10.0), count=count,
                  bottom=inset(bottom, thickness), top=inset(top, -thickness), seam=seam)
    return outer - cavity, cavity, outer


def seat(outer, origin, direction):
    """Where the ray from `origin` along `direction` leaves `outer`: (point, outward normal),
    the seat of a screw head on a skin."""
    o, d = bd.Vector(*origin), bd.Vector(*direction).normalized()
    hits = outer.find_intersection_points(bd.Axis(tuple(o), tuple(d)))
    point, normal = max(hits, key=lambda hit: (hit[0] - o).dot(d))
    if normal.dot(d) < 0:
        normal = normal * -1
    return (point.X, point.Y, point.Z), (normal.X, normal.Y, normal.Z)


def mount_pad(cavity, origin, direction, radius=6.0, reach=120.0):
    """A boss from `origin` along `direction`, trimmed to the inner surface of the skin
    whose cavity this is: fuse it to the frame the skin is carried by."""
    return cyl(radius, reach, origin, direction) & cavity
