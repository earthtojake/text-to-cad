"""What a view draws: the part projected with its hidden lines, cut for a
section, clipped for a detail, shortened for a break, and the centre lines and
cutting planes drawn on it.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable, Sequence

from cadgen._internal.drawing_base import (
    _CENTRE_OVERSHOOT, _LAYERS, _SAME_PLACE, VIEW_DIRECTIONS, _cross, _dot, _look, _where,
)

if TYPE_CHECKING:
    from cadgen.eng_drawing import View


#: Points per curved edge when two views' pictures are compared: a circle's chords
#: then stray from it by well under the comparison's tolerance.
_ALIKE_SAMPLES = 72
#: The most edges a picture may have for it to be compared: the views that repeat
#: are a turned or symmetric part's few, and a coil spring's thousands of curves
#: would take longer to sample than the rest of its drawing.
_ALIKE_EDGES = 200
#: The shortest projected edge a view keeps, in model millimetres. Hidden-line
#: removal splits a projected curve where it passes behind another, and where the
#: split falls a hair from the curve's own seam it hands back the remainder as an
#: edge of a few hundredths of a micron: the shock absorber's coil spring (tilted
#: cylinders fused) seen from the top carries three, ellipses 4e-8 mm long, each
#: the last 1.3e-7 rad of its curve before the seam. Such an edge is a
#: point -- its ends are closer than the kernel's own confusion tolerance (1e-7),
#: so they are the same point to OCCT -- and OCCT cannot measure along it
#: (``GCPnts_AbscissaPoint`` raises ``Standard_Failure``), which failed the sheet
#: the first time anything sampled the view's edges. A micron is ten times that
#: tolerance and draws nothing at any scale a sheet uses, so dropping these loses
#: no line.
_POINT_EDGE = 1e-6


# --- projection -----------------------------------------------------------------------

def _project_to_viewport(shape, origin, up, look_at):
    """Hidden-line projection, with tangent transitions left out of the hidden half.

    ``Shape.project_to_viewport`` bundles three OCCT compounds into each half.
    For the hidden half those are sharp edges (``HCompound``), silhouettes
    (``OutLineHCompound``) and SMOOTH edges (``Rg1LineHCompound``) -- the
    tangent transition where a fillet runs into a face, or a cylinder into the
    plane it touches. A drawing does not draw those: ISO 128 has no tangent
    transition line, and one that is behind material marks nothing a shop could
    look at. Drawn anyway they print as extra dashed lines running the length of
    the feature they belong to, which reads as a hidden edge that is not there.
    On the examples' circular flange the right view drew two, the full width of
    the part.

    The visible half keeps all three: a tangent line you can see is the
    conventional runout, and the sheets already read correctly with them.
    """
    from build123d import Edge, ShapeList, Vector
    from build123d.topology import downcast
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Ax1, gp_Ax2
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    hlr = HLRBRep_Algo()
    hlr.Add(shape.wrapped)
    camera = gp_Ax2()
    camera.SetAxis(gp_Ax1(Vector(origin).to_pnt(), (Vector(origin) - Vector(look_at)).normalized().to_dir()))
    camera.SetYDirection(Vector(up).normalized().to_dir())
    hlr.Projector(HLRAlgo_Projector(camera))
    hlr.Update()
    hlr.Hide()
    shapes = HLRBRep_HLRToShape(hlr)

    def edges(compound) -> list:
        found = []
        if compound is None or compound.IsNull():
            return found
        explorer = TopExp_Explorer(downcast(compound), TopAbs_ShapeEnum.TopAbs_EDGE)
        while explorer.More():
            edge = downcast(explorer.Current())
            # Without this the curve is 2D only and later reads segfault.
            BRepLib.BuildCurves3d_s(edge, 1e-9)
            projected = Edge(edge)
            # A sliver is a point, not a line: see _POINT_EDGE.
            if projected.length >= _POINT_EDGE:
                found.append(projected)
            explorer.Next()
        return found

    # Same compounds in the same order as build123d, so the entity order on the
    # sheet -- and the PDF bytes -- do not move; the hidden half drops Rg1Line.
    visible = (edges(shapes.VCompound()) + edges(shapes.Rg1LineVCompound())
               + edges(shapes.OutLineVCompound()))
    hidden = edges(shapes.HCompound()) + edges(shapes.OutLineHCompound())
    return ShapeList(visible), ShapeList(hidden)


class _Projection:
    """The affine map a build123d viewport applies, recovered from the viewport
    itself, so dimension points land exactly where the geometry did."""

    def __init__(self, shape, dirs: tuple, draw=None, shift: Callable | None = None) -> None:
        """``draw`` is what to project, when it is not ``shape`` itself: a section
        draws the cut part through the whole part's map, so it lines up with the
        views beside it."""
        from build123d import Axis, Edge, Vector

        direction, up = dirs
        #: A broken view's map from model points to the shortened part's, or None.
        self.shift = shift
        bbox = shape.bounding_box()
        centre = bbox.center()
        radius = max(bbox.size.length, 1.0)
        d = Vector(*direction).normalized()
        origin = centre + d * (radius * 10.0)
        self.origin, self.up, self.look_at = origin, up, centre
        self.visible, self.hidden = _project_to_viewport(shape if draw is None else draw, origin, up, centre)
        # Recover the map from three unit lines along the model axes.
        probes = []
        for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            line = Edge.make_line(Vector(0, 0, 0), Vector(*axis))
            vis, hid = line.project_to_viewport(viewport_origin=origin, viewport_up=up, look_at=centre)
            edges = list(vis) + list(hid)
            if not edges:
                probes.append(((0.0, 0.0), (0.0, 0.0)))
                continue
            e = edges[0]
            a, b = e.position_at(0), e.position_at(1)
            probes.append(((a.X, a.Y), (b.X, b.Y)))
        # Each probe's start is the projected origin; its end minus start is the axis image.
        # Anchor on the first probe that projected to a line: the X probe is parallel
        # to the right and left views and comes back empty, and anchoring on its
        # zero placeholder put the projected centre in the wrong place, so the
        # fix-up below chose the wrong end of the Z probe and mirrored those views'
        # annotations vertically.
        o = next((p[0] for p in probes if p[0] != p[1]), (0.0, 0.0))
        self.c = o
        self.m = [(p[1][0] - p[0][0], p[1][1] - p[0][1]) for p in probes]
        # A probe whose line is parallel to the view direction projects to a point;
        # its axis image is zero, which is correct. A projected edge can come back
        # with its ends swapped, so the map is settled by probes anchored at the
        # model centre, whose projected start is unambiguous.
        self._m_fixup(shape, centre)

    def _m_fixup(self, shape, centre) -> None:
        from build123d import Edge, Vector

        # Probe with a line from the centre to the centre + axis, whose START is
        # unambiguous: its projected start must equal the projected centre.
        for index, axis in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            line = Edge.make_line(centre, centre + Vector(*axis) * 7.0)
            vis, hid = line.project_to_viewport(viewport_origin=self.origin, viewport_up=self.up, look_at=self.look_at)
            edges = list(vis) + list(hid)
            if not edges:
                continue
            e = edges[0]
            a, b = e.position_at(0), e.position_at(1)
            # Whichever end is closer to the projected centre is the start.
            pc = self._raw_point(tuple(centre))
            da = math.hypot(a.X - pc[0], a.Y - pc[1])
            db = math.hypot(b.X - pc[0], b.Y - pc[1])
            start, end = (a, b) if da <= db else (b, a)
            self.m[index] = ((end.X - start.X) / 7.0, (end.Y - start.Y) / 7.0)
            self.c = (pc[0] - (self.m[0][0] * centre.X + self.m[1][0] * centre.Y + self.m[2][0] * centre.Z),
                      pc[1] - (self.m[0][1] * centre.X + self.m[1][1] * centre.Y + self.m[2][1] * centre.Z))

    def _raw_point(self, p) -> tuple[float, float]:
        x = self.c[0] + self.m[0][0] * p[0] + self.m[1][0] * p[1] + self.m[2][0] * p[2]
        y = self.c[1] + self.m[0][1] * p[0] + self.m[1][1] * p[1] + self.m[2][1] * p[2]
        return (x, y)

    def point(self, p) -> tuple[float, float]:
        return self._raw_point(self.shift(p) if self.shift else p)


def _edges_bounds(edges) -> tuple[float, float, float, float] | None:
    """Exact (x0, x1, y0, y1) of projected edges, from the kernel's own bounding boxes,
    so a circle's extent is its diameter and not the chord of a few samples."""
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for edge in edges:
        bb = edge.bounding_box()
        x0, x1 = min(x0, bb.min.X), max(x1, bb.max.X)
        y0, y1 = min(y0, bb.min.Y), max(y1, bb.max.Y)
    if not math.isfinite(x0):
        return None
    return (x0, x1, y0, y1)


def _pictures_alike(first: _Projection, second: _Projection, extent: float) -> bool:
    """Whether two projections draw the same visible and hidden lines, allowing for
    the mirror image a turned or symmetric part shows from the next view round.
    Both are centred on the part's middle, so one picture lies on the other or on
    its mirror; ``extent`` (the part's diagonal) sets how close counts."""
    from shapely import affinity
    from shapely.geometry import MultiLineString

    tolerance = 0.02 + 0.001 * extent
    if any(len(p.visible) + len(p.hidden) > _ALIKE_EDGES for p in (first, second)):
        return False
    # Two pictures of different extent are not alike, and most pairs differ there:
    # settle those before sampling any curve.
    boxes = [_edges_bounds([*p.visible, *p.hidden]) for p in (first, second)]
    if None in boxes:
        return False
    (ax0, ax1, ay0, ay1), (bx0, bx1, by0, by1) = boxes
    if abs((ax1 - ax0) - (bx1 - bx0)) > tolerance or abs((ay1 - ay0) - (by1 - by0)) > tolerance:
        return False

    def lines(edges) -> MultiLineString:
        return MultiLineString([_edge_polyline(edge, _ALIKE_SAMPLES) for edge in edges])

    def covers(a, b) -> bool:
        if a.is_empty or b.is_empty:
            return a.is_empty and b.is_empty
        return a.buffer(tolerance).contains(b) and b.buffer(tolerance).contains(a)

    pairs = [(lines(first.visible), lines(second.visible)), (lines(first.hidden), lines(second.hidden))]
    return any(all(covers(a, affinity.scale(b, fx, fy, origin=(0, 0))) for a, b in pairs)
               for fx, fy in ((1, 1), (-1, 1), (1, -1), (-1, -1)))


def _view_extent(shape, name: str, scale: float) -> tuple[float, float]:
    """The projected (width, height) of a view in sheet millimetres, for placement."""
    proj = _Projection(shape, VIEW_DIRECTIONS[name])
    bounds = _edges_bounds(list(proj.visible) + list(proj.hidden))
    if not bounds:
        return (0.0, 0.0)
    return ((bounds[1] - bounds[0]) * scale, (bounds[3] - bounds[2]) * scale)


def _edge_polyline(edge, samples: int = 24) -> list[tuple[float, float]]:
    """A projected edge as points. Sampled by arc length where OCCT can measure it;
    a projected spline that has collapsed to almost nothing (an assembly's hidden
    seam seen edge-on, say) makes that fail inside OCCT, so such an edge is
    sampled by its own curve parameter instead."""
    from build123d import GeomType

    n = 2 if edge.geom_type == GeomType.LINE else samples
    try:
        return [(float(v.X), float(v.Y)) for v in (edge.position_at(i / (n - 1)) for i in range(n))]
    except Exception:  # noqa: BLE001 - OCCT's Standard_Failure carries no type worth naming
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        curve = BRepAdaptor_Curve(edge.wrapped)
        t0, t1 = curve.FirstParameter(), curve.LastParameter()
        points = [curve.Value(t0 + (t1 - t0) * i / (n - 1)) for i in range(n)]
        return [(float(p.X()), float(p.Y())) for p in points]


def _circles(edges) -> list[tuple[tuple[float, float], float]]:
    """Full circles among projected edges: (centre, radius) in viewport coordinates."""
    from build123d import GeomType

    found: list[tuple[tuple[float, float], float]] = []
    for edge in edges:
        if edge.geom_type != GeomType.CIRCLE or not edge.is_closed:
            continue
        c = edge.arc_center
        key = ((round(c.X, 3), round(c.Y, 3)), round(edge.radius, 3))
        if key not in found:
            found.append(key)
    return found


def _centres(circles: Sequence[tuple[tuple[float, float], float]]) -> list[tuple[tuple[float, float], float]]:
    """One entry per circle centre, carrying the largest radius found on it."""
    largest: dict[tuple[float, float], float] = {}
    for centre, radius in circles:
        if radius > largest.get(centre, -1.0):
            largest[centre] = radius
    return list(largest.items())


def _axis_lines(view: View, proj, part_axes, to_sheet) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Centre lines for the turned features a view sees from the side: a shaft's
    axis, a hole drawn hidden through a plate. Axes that land on one drawn line
    (two holes one behind the other, a shaft's steps) merge into one line, which
    runs ``_CENTRE_OVERSHOOT`` past the feature at each end."""
    look = _look(view)
    segments = []
    for axis in part_axes:
        d = tuple(e - s for e, s in zip(axis.end, axis.start))
        n = math.sqrt(_dot(d, d))
        if n < 1e-9 or abs(_dot(d, look)) / n > 1e-6:
            continue  # seen end-on, where the centre mark is the cross on its circle
        segments.append((to_sheet(proj.point(axis.start)), to_sheet(proj.point(axis.end)), None))
    out = []
    for a, b, _tags in _collinear_runs(segments):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        out.append(((a[0] - ux * _CENTRE_OVERSHOOT, a[1] - uy * _CENTRE_OVERSHOOT),
                    (b[0] + ux * _CENTRE_OVERSHOOT, b[1] + uy * _CENTRE_OVERSHOOT)))
    return out


def _collinear_runs(segments) -> list[tuple[tuple[float, float], tuple[float, float], list]]:
    """Sheet segments ``(a, b, tag)`` joined where they lie on one line and overlap
    or touch: each run as its two ends and the tags of the segments it joins.
    Segments of no length are left out."""
    lines: dict[tuple, list] = {}
    for a, b, tag in segments:
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-9:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
            ux, uy = -ux, -uy
        offset = -uy * a[0] + ux * a[1]
        t0, t1 = sorted((ux * a[0] + uy * a[1], ux * b[0] + uy * b[1]))
        lines.setdefault((round(ux, 6), round(uy, 6), round(offset, 4)), []).append((t0, t1, tag))
    runs = []
    for (ux, uy, offset), spans in sorted(lines.items()):
        merged: list[list] = []
        for t0, t1, tag in sorted(spans, key=lambda span: (span[0], span[1])):
            if merged and t0 <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], t1)
                merged[-1][2].append(tag)
            else:
                merged.append([t0, t1, [tag]])
        runs += [((ux * t0 - uy * offset, uy * t0 + ux * offset), (ux * t1 - uy * offset, uy * t1 + ux * offset), tags)
                 for t0, t1, tags in merged]
    return runs


def _end_on(view: View, proj, part_axes) -> list[tuple[tuple[float, float], float]]:
    """(centre, radius) of every turned feature a view looks straight down: its
    centre mark belongs there even when part of its circle is hidden behind
    something nearer, which leaves no closed circle to find it by."""
    look = _look(view)
    marks = []
    for axis in part_axes:
        d = tuple(e - s for e, s in zip(axis.end, axis.start))
        n = math.sqrt(_dot(d, d))
        if n > 1e-9 and abs(_dot(d, look)) / n > 1 - 1e-6:
            c = proj.point(axis.start)
            marks.append(((round(c[0], 3), round(c[1], 3)), round(axis.radius, 3)))
    return marks


def _sheet_axis(proj, horizontal: bool) -> int | None:
    """The model axis (0, 1, 2 for X, Y, Z) a view draws along the sheet's
    horizontal or vertical, or None for a pictorial view that draws none."""
    component = 0 if horizontal else 1
    for index, image in enumerate(proj.m):
        if abs(abs(image[component]) - 1.0) < 1e-6 and abs(image[1 - component]) < 1e-6:
            return index
    return None


#: For a section in each view, the views that see its cutting plane edge-on, in the
#: order a drawing shows it: a front section's plane on the top view, and so on.
_PLANE_SHOWN_ON = {
    "front": ("top", "bottom", "right", "left"), "back": ("top", "bottom", "right", "left"),
    "right": ("front", "top", "back", "bottom"), "left": ("front", "top", "back", "bottom"),
    "top": ("front", "right", "back", "left"), "bottom": ("front", "right", "back", "left"),
}


def _plane_parent(view: View, others) -> View | None:
    """The view among ``others`` a section's cutting plane is drawn on: a whole,
    uncut view of the same part that sees the plane edge-on."""
    return next((other for name in _PLANE_SHOWN_ON[view.name] for other in others
                 if other.name == name and other.shape is view.shape and other._section is None
                 and other._detail is None), None)


def _plane_cut(shape, point, look) -> tuple:
    """``shape`` cut by the plane through ``point`` square to ``look``: (the half
    beyond the plane, the faces the cut leaves in the plane)."""
    from build123d import Compound, GeomType, Keep, Plane

    kept = shape.split(Plane(origin=point, z_dir=look), keep=Keep.BOTTOM)
    if isinstance(kept, (list, tuple)):
        kept = Compound(list(kept))
    faces = []
    for face in (kept.faces() if kept is not None else []):
        if face.geom_type != GeomType.PLANE:
            continue
        normal, centre = face.normal_at(), face.center()
        if (abs(abs(_dot((normal.X, normal.Y, normal.Z), look)) - 1) < 1e-6
                and abs(_dot((centre.X - point[0], centre.Y - point[1], centre.Z - point[2]), look)) < 1e-6):
            faces.append(face)
    return kept, faces


def _cut(view: View) -> tuple:
    """The part a section view draws: (the half beyond the plane, its cut faces,
    the point the plane passes through, and for a section through an assembly's
    parts each item with its own cut faces and whether it is drawn uncut: a
    solid turned part the plane cuts along its axis)."""
    from build123d import Compound

    letter, through = view._section
    shape = view.shape
    point = through if through is not None else tuple(shape.bounding_box().center())
    look = _look(view)
    items = []
    if view._section_parts is None:
        kept, faces = _plane_cut(shape, point, look)
    else:
        # Each part cut on its own, so each is hatched as what it is made of; and
        # parts the model overlaps on purpose (a thread) cut cleanly, which the
        # assembly cut whole does not.
        halves, faces = [], []
        for item in view._section_parts:
            own, plain = [], False
            for placed in item.occurrences:
                half, cut = _plane_cut(placed, point, look)
                if half is not None:
                    halves.append(half)
                if cut:
                    plain = plain or _solid_round_along(placed, point, look)
                own += cut
            if own:
                items.append((item, own, plain))
                faces += own
        kept = Compound(halves) if halves else None
    if not faces:
        raise ValueError(
            f"{view.name}.section({letter!r}): the plane through {_where(point)} square to the {view.name} "
            "view's line of sight does not cut the part. Give through= a model point inside it."
        )
    return kept, faces, point, items


def _solid_round_along(shape, point, look) -> bool:
    """Whether a part is solid and turned whole, its axis in the cutting plane: a
    shaft, a rod, a pin, a bolt, which a section shows uncut. A cross hole (a
    cotter pin's) leaves it solid; a bore along its axis does not."""
    from cadgen._internal.drawing_features import _surface_segments, revolved

    turned = revolved(shape, bores=True)
    if turned is None:
        return False
    d = tuple(float(k == turned.axis) for k in range(3))
    if abs(_dot(d, look)) > 1e-6 or abs(_dot(tuple(a - b for a, b in zip(turned.at, point)), look)) > 1e-3:
        return False  # its axis is not in the plane
    for line, foot, segments in _surface_segments(shape).values():
        rel = tuple(a - b for a, b in zip(turned.at, foot))
        on_axis = abs(abs(_dot(line, d)) - 1) < 1e-6 and math.dist(rel, tuple(_dot(rel, d) * c for c in d)) < 1e-3
        if on_axis and any(seg.concave for seg in segments):
            return False  # bored through along its axis: a tube, which is cut
    return True


def _edge_points(edge) -> list[tuple[float, float]]:
    """A projected edge as points close enough to clip: a line's two ends, a circle
    or arc in short chords."""
    from build123d import GeomType

    if edge.geom_type == GeomType.LINE:
        n = 2
    elif edge.geom_type == GeomType.CIRCLE:
        # A full circle at three degrees a point; an arc, at most a half circle's worth.
        n = 121 if edge.is_closed else 61
    else:
        n = 48
    return [(float(v.X), float(v.Y)) for v in (edge.position_at(i / (n - 1)) for i in range(n))]


def _clip_runs(points, region) -> list[list[tuple[float, float]]]:
    """The runs of a polyline that lie inside ``region`` (a shapely shape)."""
    from shapely.geometry import LineString

    if len(points) < 2:
        return []
    clipped = LineString(points).intersection(region)
    runs: list[list[tuple[float, float]]] = []
    for part in getattr(clipped, "geoms", [clipped]):
        if part.geom_type == "LineString" and len(part.coords) >= 2:
            runs.append([tuple(c) for c in part.coords])
        elif part.geom_type == "MultiLineString":
            runs.extend([tuple(c) for c in line.coords] for line in part.geoms)
    return runs


def _merge_centre_lines(msp) -> None:
    """One chain line where several land on one line and overlap: a row of holes'
    centre marks, a bore's mark, a cutting plane through them. Overlapping chain
    lines strike their dashes out of phase and print solid, which reads as an
    edge."""
    segments = [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y), e)
                for e in msp.query("LINE[layer=='CENTER']")]
    for a, b, entities in _collinear_runs(segments):
        if len(entities) < 2:
            continue
        for entity in entities:
            msp.delete_entity(entity)
        msp.add_line(a, b, dxfattribs={"layer": "CENTER"})


def _model_to_sheet(proj, at, centre, scale, point) -> tuple[float, float]:
    """Where a model point lands on the sheet in a placed view."""
    x, y = proj.point(point)
    return (at[0] + (x - centre[0]) * scale, at[1] + (y - centre[1]) * scale)


#: The paper left between the two ends of a broken view.
_BREAK_GAP = 10.0


def _break_shift(brk: tuple, gap: float) -> Callable:
    """Where a model point lands in a broken view's shortened part: past the break
    it moves back by the length taken out, less ``gap`` (model mm); inside it, it
    is squeezed into the gap."""
    axis, lo, hi = brk

    def shift(p):
        q = list(p)
        if q[axis] >= hi:
            q[axis] -= (hi - lo) - gap
        elif q[axis] > lo:
            q[axis] = lo + (q[axis] - lo) * gap / (hi - lo)
        return tuple(q)

    return shift


def _one_shape(kept):
    """A split's result as one shape: the kernel hands back a list where the cut
    leaves several pieces (a fork's two arms), and None where it leaves none."""
    from build123d import Compound

    if kept is None:
        return Compound([])
    if isinstance(kept, (list, tuple)):
        return Compound(list(kept))
    return kept


def _broken_shape(shape, brk: tuple, gap: float):
    """The part with the stretch between the break's ends taken out and its far
    end moved up to ``gap`` (model mm) from its near one."""
    from build123d import Compound, Keep, Location, Plane, Vector

    axis, lo, hi = brk
    normal = Vector(*(1.0 if k == axis else 0.0 for k in range(3)))
    near = _one_shape(shape.split(Plane(origin=normal * lo, z_dir=normal), keep=Keep.BOTTOM))
    far = _one_shape(shape.split(Plane(origin=normal * hi, z_dir=normal), keep=Keep.TOP))
    far = far.moved(Location(normal * -((hi - lo) - gap)))
    return Compound([near, far])


def _broken_size(size, brk: tuple, scale: float):
    """A part's extents as a broken view draws them at ``scale``."""
    from build123d import Vector

    axis, lo, hi = brk
    shorter = [size.X, size.Y, size.Z]
    shorter[axis] -= (hi - lo) - _BREAK_GAP / scale
    return Vector(*shorter)


def _break_hides(shape, brk: tuple) -> bool:
    """Whether the part changes inside a break: the stretch taken out is not one
    section drawn long, so the break hides some of the part."""
    from build123d import Keep, Plane, Vector

    axis, lo, hi = brk
    normal = Vector(*(1.0 if k == axis else 0.0 for k in range(3)))
    middle = _one_shape(shape.split(Plane(origin=normal * lo, z_dir=normal), keep=Keep.TOP))
    middle = _one_shape(middle.split(Plane(origin=normal * hi, z_dir=normal), keep=Keep.BOTTOM))
    # The section at each end, and the mean section between: one section drawn
    # long has all three equal.
    ends = [sum(f.area for f in middle.faces() if abs(f.center().dot(normal) - at) < 1e-6) for at in (lo, hi)]
    mean = middle.volume / (hi - lo)
    # Volumes of spline sections carry about 1e-5 of the kernel's error.
    tolerance = 1e-4 * max(ends[0], 1.0)
    return abs(ends[0] - ends[1]) > tolerance or abs(mean - ends[0]) > tolerance


def _break_cuts(view: View, proj) -> list[tuple]:
    """A broken view's two cuts as projected lines: a point on each, and the unit
    direction across them (the image of the broken axis)."""
    axis, lo, hi = view._break
    origin = proj.point((0.0, 0.0, 0.0))
    unit = proj.point(tuple(1.0 if k == axis else 0.0 for k in range(3)))
    length = math.hypot(unit[0] - origin[0], unit[1] - origin[1]) or 1.0
    across = ((unit[0] - origin[0]) / length, (unit[1] - origin[1]) / length)
    return [(proj.point(tuple(at if k == axis else 0.0 for k in range(3))), across) for at in (lo, hi)]


def _on_cut(edge, cuts: list[tuple]) -> bool:
    """Whether a projected edge lies along one of those cuts."""
    points = [edge.position_at(t) for t in (0.0, 0.5, 1.0)]
    return any(all(abs((p.X - c[0]) * d[0] + (p.Y - c[1]) * d[1]) < 1e-5 for p in points) for c, d in cuts)


def _draw_break_lines(msp, view: View, proj, to_sheet) -> None:
    """A thin zigzag line across each end of a broken view's break (ISO 128-2,
    type 01.1), as long as the part's section there and a little over."""
    from build123d import Keep, Plane, Vector

    axis, lo, hi = view._break
    normal = Vector(*(1.0 if k == axis else 0.0 for k in range(3)))
    near = view.shape.split(Plane(origin=normal * lo, z_dir=normal), keep=Keep.BOTTOM)
    section = [f for f in near.faces() if abs(f.center().dot(normal) - lo) < 1e-6]
    if not section:
        return
    corners = []
    for face in section:
        box = face.bounding_box()
        corners += [(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
                    for z in (box.min.Z, box.max.Z)]
    for at in (lo, hi):
        ends = [to_sheet(proj.point(tuple(at if k == axis else c[k] for k in range(3)))) for c in corners]
        start, finish = min(ends), max(ends)
        if math.dist(start, finish) < 1e-6:
            continue
        length = math.dist(start, finish)
        t = ((finish[0] - start[0]) / length, (finish[1] - start[1]) / length)
        d = (t[1], -t[0])
        mid = ((start[0] + finish[0]) / 2, (start[1] + finish[1]) / 2)

        def along(point, k: float, j: float = 0.0):
            return (point[0] + t[0] * k + d[0] * j, point[1] + t[1] * k + d[1] * j)

        msp.add_lwpolyline([along(start, -2.0), along(mid, -2.0), along(mid, -0.7, 2.5), along(mid, 0.7, -2.5),
                            along(mid, 2.0), along(finish, 2.0)], dxfattribs={"layer": "NOTES"})


def _bbox_bounds(shape, proj, raw: bool = False) -> tuple[float, float, float, float]:
    """A part's projected (x0, x1, y0, y1), from its bounding box's corners;
    ``raw`` maps them as the whole part, not a broken view's shortened one."""
    bb = shape.bounding_box()
    to = proj._raw_point if raw else proj.point
    points = [to((x, y, z)) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y)
              for z in (bb.min.Z, bb.max.Z)]
    return (min(p[0] for p in points), max(p[0] for p in points),
            min(p[1] for p in points), max(p[1] for p in points))


def _wire_points(wire) -> list[tuple[float, float, float]]:
    """A closed wire as points close enough together that a hatch fills its arcs."""
    count = max(24, min(720, int(wire.length / 0.5)))
    return [tuple(wire.position_at(i / count)) for i in range(count)]


def _draw_cutting_plane(msp, parent: tuple, point, look, letter: str, text, th: float) -> None:
    """ISO 128-40's cutting plane on the view that sees it edge-on: a thin chain line
    across the view, thick at its ends, with arrows in the direction the section is
    viewed and the section's letter at each."""
    from ezdxf.enums import TextEntityAlignment

    _view, model_to_sheet, box = parent
    along = _cross(_look(_view), look)
    p0 = model_to_sheet(point)
    p1 = model_to_sheet(tuple(a + b for a, b in zip(point, along)))
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
    u = ((p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length)
    ts = [(x - p0[0]) * u[0] + (y - p0[1]) * u[1] for x in box[:2] for y in box[2:]]
    # Just past the view, inside the first dimension row on either side.
    a = (p0[0] + u[0] * (min(ts) - 4.0), p0[1] + u[1] * (min(ts) - 4.0))
    b = (p0[0] + u[0] * (max(ts) + 4.0), p0[1] + u[1] * (max(ts) + 4.0))
    msp.add_line(a, b, dxfattribs={"layer": "CENTER"})
    # The section is viewed looking AWAY from where its viewer stands.
    q = model_to_sheet(tuple(c - d for c, d in zip(point, look)))
    run = math.hypot(q[0] - p0[0], q[1] - p0[1]) or 1.0
    d = ((q[0] - p0[0]) / run, (q[1] - p0[1]) / run)
    for end, inward in ((a, u), (b, (-u[0], -u[1]))):
        # Thick at the ends, at the outline's weight, but not on VISIBLE: that layer
        # is the part's edges and nothing else.
        msp.add_line(end, (end[0] + inward[0] * 7.0, end[1] + inward[1] * 7.0),
                     dxfattribs={"layer": "NOTES", "lineweight": int(round(_LAYERS["VISIBLE"][2] * 100))})
        head = (end[0] + d[0] * 7.0, end[1] + d[1] * 7.0)
        msp.add_leader([head, end], dxfattribs={"layer": "DIM"},
                       override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
        # The letter just past the end of the line, level with the middle of its
        # arrow: at the arrow's tip it sat on the extension lines that leave the
        # view's corners, and further out it reached the first dimension row.
        out, gap = (-inward[0], -inward[1]), (th + 1.5) / 2 + 1.0
        text(letter, end[0] + d[0] * 3.5 + out[0] * gap, end[1] + d[1] * 3.5 + out[1] * gap,
             th + 1.5, TextEntityAlignment.MIDDLE_CENTER, "NOTES")


def _flat_face(shape, point) -> tuple:
    """The flat face of ``shape`` through ``point``: its outward normal and its
    outline's points."""
    from build123d import GeomType, Vector

    target = Vector(*point)
    near = []
    for face in shape.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        # On the face's plane and inside its outline: the middle of a face with a
        # hole in it is a point on that face to whoever names it.
        normal = face.normal_at(face.center())
        box = face.bounding_box()
        if abs((target - face.center()).dot(normal)) < _SAME_PLACE and all(
                lo - _SAME_PLACE <= v <= hi + _SAME_PLACE for v, lo, hi in zip(target, box.min, box.max)):
            near.append((face.distance_to(target), face))
    if not near:
        raise ValueError(f"no flat face of the part passes through {_where(point)}; an auxiliary view looks "
                         "square onto a flat face, so give a point on one")
    face = min(near, key=lambda pair: pair[0])[1]
    normal = face.normal_at(target)
    return (normal.X, normal.Y, normal.Z), _wire_points(face.outer_wire())
