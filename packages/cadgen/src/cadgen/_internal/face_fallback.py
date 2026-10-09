"""A face OCCT's mesher refuses, tessellated over its own parameters.

OCCT's mesher discretizes a face's whole boundary and refuses the face outright when
that boundary, as it reads it, crosses itself or does not close: what a boolean's
leftovers do to a valid face -- a zero-length edge where the surface is not pinched
(radial's accessory case), a trimming loop that touches itself (the hand's fingertip
pad), a cone's tip it cannot close (the RoArm's screws). No setting of OCCT's and none
of its repairs meshes them, and the tessellator cadgen had before drew every one. So
such a face is tessellated here the way that one did, locally: a grid over the face's
parameters, each cell inside the face two triangles, each cell its boundary crosses
clipped to the boundary and ear-clipped, so a defect costs at most the cell it lies in.

The boundary takes the points the whole pass gave the meshed neighbours along each
shared edge, so the face meets them; where the clipping adds a point to that boundary,
the neighbour's triangle along it is split to take the point too, and the two meshes
share every vertex (an STL of them welds closed). OCCT computes the normals from the
surface, as it does for its own triangles.

Those points are spaced for the deflection, and a face narrower than the deflection
can lie between a curved edge and its chord: the f14d wing's 686 mm slivers, 1.2 mm
wide on average, whose curved side the skin beside them meshes as one chord. That
chord passes beyond the sliver's straight side, the boundary crosses itself, and
OCCT's own boundary check passes it before its triangulation fails. So a boundary
segment that follows a curve is split at its parameters' midpoint while it crosses
another or strays from its curve by more than a share of the face's own width, round
after round; each point a split adds lies on the edge's own curve, and the neighbour
along it takes the point too.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# The most cells a direction of the grid is cut into, as the earlier tessellator had it,
# and the fewest: a flat face still has cells for its boundary to be clipped to.
_MAX_STEPS = 256
_MIN_STEPS = 4
# The intervals a probe line is cut into when the grid is sized.
_PROBES = 16
# The points a degenerated edge (a pole, a cone's tip) is sampled at along its parameters.
_DEGENERATE_POINTS = 17
# Rounds of edge splitting after the grid, and the triangles a face may grow to.
_REFINE_ROUNDS = 7
_MAX_TRIANGLES = 200_000
# The chord a refined triangle may keep, as a share of the deflection. A face OCCT refuses
# is often a strip about as narrow as the deflection -- a fillet -- and a triangle as long as
# the deflection allows bridges its curve and counts the gap as area.
_REFINE_SHARE = 0.25
# A normal is the surface's only where its size is not lost to rounding: at a pole or a
# cone's tip, or a hair past it, it is a rounding's direction.
_NORMAL_FLOOR = 1e-3
# Rounds of splitting a boundary's crossing segments (each halves a segment: 24 rounds
# take a kilometre's chord under a tenth of a micron), the points a boundary may grow to
# meanwhile, and the segment pairs a round may test: past either bound the boundary is
# left as it is, and the area check decides.
_UNCROSS_ROUNDS = 24
_MAX_BOUNDARY_POINTS = 20_000
_MAX_CROSSING_PAIRS = 2_000_000
# The most a boundary segment may stray from its curve, as a share of the face's width
# (twice its area over its perimeter), where that is under the deflection: a chord
# straying by this share all round the boundary changes the face's area by under 7%.
_BOUNDARY_SHARE = 0.05


def tessellate_face(topods, face, deflection: float, angle: float):
    """``face``'s triangulation (a ``Poly_Triangulation`` with UV nodes) and the area its
    triangles cover, built over its parameters at ``deflection`` and ``angle``, the
    triangles of meshed neighbours split where its boundary takes a point theirs lack;
    None when the face bounds no region."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    location = TopLoc_Location()
    surface = BRep_Tool.Surface_s(face, location)
    loops = _boundary_loops(topods, face, location, deflection, angle)
    if not loops:
        return None
    points = np.concatenate([uv for uv, *_rest in loops])
    u0, v0 = points.min(axis=0)
    u1, v1 = points.max(axis=0)
    if not (u1 > u0 and v1 > v0):
        return None
    loops = _uncrossed(loops, location, (u1 - u0) + (v1 - v0), _boundary_sag(face, deflection))
    points = np.concatenate([uv for uv, *_rest in loops])
    u0, v0 = points.min(axis=0)
    u1, v1 = points.max(axis=0)
    box = (float(u0), float(u1), float(v0), float(v1))
    grid_u = np.linspace(u0, u1, _grid_steps(surface, box, 0, deflection, angle) + 1)
    grid_v = np.linspace(v0, v1, _grid_steps(surface, box, 1, deflection, angle) + 1)
    mesh = _Mesh(*box)
    boundary = set()
    for uv, xyz, _shared, _sources in loops:
        for (u, v), place in zip(uv, xyz):
            boundary.add(mesh.vertex(u, v, place))

    segments = _segments(loops)
    shared = [edge for _uv, _xyz, edges, _sources in loops for edge in edges]
    sources = [source for *_rest, edge_sources in loops for source in edge_sources]
    by_cell = _cells_of_segments(segments, grid_u, grid_v)
    inside = _inside_cells(segments, grid_u, grid_v)
    for i in range(len(grid_u) - 1):
        for j in range(len(grid_v) - 1):
            if (i, j) in by_cell or not inside[i, j]:
                continue
            a, b = mesh.vertex(grid_u[i], grid_v[j]), mesh.vertex(grid_u[i + 1], grid_v[j])
            c, d = mesh.vertex(grid_u[i + 1], grid_v[j + 1]), mesh.vertex(grid_u[i], grid_v[j + 1])
            mesh.triangles.extend(((a, b, c), (a, c, d)))
    for i, j in sorted(by_cell):
        cell = (grid_u[i], grid_u[i + 1], grid_v[j], grid_v[j + 1])
        pieces = [piece for uv, *_rest in loops if len(piece := _clip_to_cell(uv, *cell)) >= 3]
        pieces = sorted((piece for piece in pieces if abs(_area(piece)) > mesh.tiny_area), key=lambda piece: -abs(_area(piece)))
        if not pieces:
            continue
        for corners in _triangulate(pieces[0], pieces[1:], mesh.tiny_length, mesh.tiny_area):
            triangle = tuple(mesh.vertex(*corner) for corner in corners)
            if len(set(triangle)) == 3:
                mesh.triangles.append(triangle)
    if not mesh.triangles:
        return None
    mesh.place(surface)
    _refine(mesh, surface, deflection * _REFINE_SHARE, angle, _normal_scale(surface, box))
    mesh.weld()
    _conform_neighbours(mesh, boundary, segments, shared, sources, by_cell, grid_u, grid_v)
    return mesh.triangulation(), mesh.area()


class _Mesh:
    """Vertices by their parameters, welded within a billionth of the face's span, and the
    triangles between them, counter-clockwise in the parameters."""

    def __init__(self, u0: float, u1: float, v0: float, v1: float) -> None:
        self.u0, self.v0 = u0, v0
        self.periods: tuple = (None, None)
        self.weld_u, self.weld_v = (u1 - u0) * 1e-9, (v1 - v0) * 1e-9
        self.tiny_length = max(u1 - u0, v1 - v0) * 1e-12
        self.tiny_area = (u1 - u0) * (v1 - v0) * 1e-14
        self.keys: dict[tuple[int, int], int] = {}
        self.uv: list[tuple[float, float]] = []
        self.xyz: list[Any] = []
        self.triangles: list[tuple[int, int, int]] = []

    def key(self, u: float, v: float) -> tuple[int, int]:
        return (round((u - self.u0) / self.weld_u), round((v - self.v0) / self.weld_v))

    def vertex(self, u: float, v: float, xyz: Any = None) -> int:
        key = self.key(u, v)
        index = self.keys.get(key)
        if index is None:
            index = self.keys[key] = len(self.uv)
            self.uv.append((float(u), float(v)))
            self.xyz.append(xyz)
        elif xyz is not None and self.xyz[index] is None:
            self.xyz[index] = xyz
        return index

    def place(self, surface) -> None:
        """Every vertex no neighbour placed, on the surface at its parameters."""
        self.periods = (surface.UPeriod() if surface.IsUPeriodic() else None,
                        surface.VPeriod() if surface.IsVPeriodic() else None)
        for index, (u, v) in enumerate(self.uv):
            if self.xyz[index] is None:
                self.xyz[index] = self.on_surface(surface, u, v)

    def weld(self) -> None:
        """Vertices that are one point in space -- a pole's run, a cone's tip, the two sides
        of a seam -- take one place, so their triangles meet bit for bit."""
        xyz = np.asarray(self.xyz, float)
        scale = max(float(np.ptp(xyz, axis=0).max()), 1e-12) * 1e-9
        first: dict[tuple, int] = {}
        for index, key in enumerate(map(tuple, np.round(xyz / scale).astype(np.int64).tolist())):
            self.xyz[index] = self.xyz[first.setdefault(key, index)]

    def on_surface(self, surface, u: float, v: float) -> tuple[float, float, float]:
        """The surface's point at (u, v), a period's parameters read as one: the two sides
        of a seam evaluate the same parameters and meet bit for bit."""
        period_u, period_v = self.periods
        if period_u:
            u = self.u0 + (u - self.u0) % period_u if not math.isclose(u - self.u0, period_u) else self.u0
        if period_v:
            v = self.v0 + (v - self.v0) % period_v if not math.isclose(v - self.v0, period_v) else self.v0
        point = surface.Value(u, v)
        return (point.X(), point.Y(), point.Z())

    def area(self) -> float:
        xyz = np.asarray(self.xyz, float)
        a, b, c = (xyz[np.asarray(self.triangles)[:, k]] for k in range(3))
        return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())

    def triangulation(self):
        from OCP.gp import gp_Pnt, gp_Pnt2d
        from OCP.Poly import Poly_Triangle, Poly_Triangulation

        result = Poly_Triangulation(len(self.uv), len(self.triangles), True)
        for index, ((u, v), (x, y, z)) in enumerate(zip(self.uv, self.xyz), 1):
            result.SetNode(index, gp_Pnt(x, y, z))
            result.SetUVNode(index, gp_Pnt2d(u, v))
        for index, (a, b, c) in enumerate(self.triangles, 1):
            result.SetTriangle(index, Poly_Triangle(a + 1, b + 1, c + 1))
        return result


def _boundary_loops(topods, face, location, deflection: float, angle: float) -> list:
    """Each wire of ``face`` as a closed polyline over its parameters: its points (n, 2),
    each one's place in the face's frame where a meshed neighbour fixes it (else None),
    per segment the neighbour edge it runs along, as (neighbour face, the node at the
    segment's start, the node at its end, the neighbour's frame from the face's, and the
    share of the way from the one node to the other the segment starts and ends at), or
    None, and per segment the curve it follows, as (edge, its curve, its curve on the
    face, the parameters at the segment's start and end), or None where a split could not
    move it: a degenerated edge, or a seam, whose two sides must keep the same points."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_WIRE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(topods, TopAbs_EDGE, TopAbs_FACE, ancestors)
    loops = []
    wires = TopExp_Explorer(face, TopAbs_WIRE)
    while wires.More():
        uv, xyz, shared, sources = [], [], [], []
        walk = BRepTools_WireExplorer(TopoDS.Wire_s(wires.Current()), face)
        while walk.More():
            edge = walk.Current()
            pcurve = BRepAdaptor_Curve2d(edge, face)
            parameters, places, neighbour = _edge_points(edge, face, pcurve, ancestors, location, deflection, angle)
            if edge.Orientation() == TopAbs_REVERSED:
                parameters, places = parameters[::-1], places[::-1]
                if neighbour is not None:
                    neighbour = (neighbour[0], neighbour[1][::-1], neighbour[2])
            curve = (None if BRep_Tool.Degenerated_s(edge) or BRep_Tool.IsClosed_s(edge, face)
                     else BRepAdaptor_Curve(edge))
            # The next edge starts where this one ends.
            for k in range(len(parameters) - 1):
                point = pcurve.Value(parameters[k])
                uv.append((point.X(), point.Y()))
                xyz.append(places[k])
                shared.append(None if neighbour is None
                              else (neighbour[0], neighbour[1][k], neighbour[1][k + 1], neighbour[2], 0.0, 1.0))
                sources.append(None if curve is None else (edge, curve, pcurve, parameters[k], parameters[k + 1]))
            walk.Next()
        if len(uv) >= 3:
            loops.append((np.array(uv, float), xyz, shared, sources))
        wires.Next()
    return loops


def _boundary_sag(face, deflection: float) -> float:
    """How far a boundary segment may stray from its curve: the deflection, or less on a
    face narrower than it -- ``_BOUNDARY_SHARE`` of twice its area over its perimeter."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    area, perimeter = GProp_GProps(), GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, area)
    BRepGProp.LinearProperties_s(face, perimeter)
    width = 2 * abs(area.Mass()) / perimeter.Mass() if perimeter.Mass() > 0 else 0.0
    return min(deflection, _BOUNDARY_SHARE * width) if width > 0 else deflection


def _segments(loops: list) -> np.ndarray:
    """The loops' segments, (n, 2, 2): each point to the next, the last to the first."""
    return np.concatenate([np.stack([uv, np.roll(uv, -1, axis=0)], axis=1) for uv, *_rest in loops])


def _uncrossed(loops: list, location, span: float, sag: float) -> list:
    """``loops`` with each segment that follows a curve split at its parameters' midpoint
    while it crosses another segment or strays from its curve by more than ``sag`` -- round
    after round, until none does: the added point is the curve's, on the face (its
    parameters) and in space (where a neighbour shares the edge, which takes the point as
    well). A split that would not move the segment -- a straight edge -- is not made; nor is
    any past ``_UNCROSS_ROUNDS``, ``_MAX_BOUNDARY_POINTS`` or ``_MAX_CROSSING_PAIRS``.
    ``span`` is the size of the loops' parameter box."""
    from OCP.gp import gp_Pnt

    to_face = location.Transformation().Inverted()
    still = span * 1e-12
    strays: dict[tuple, bool] = {}

    def strays_from(source) -> bool:
        """Whether the segment's chord passes its curve's midpoint by more than ``sag``."""
        _edge, curve, _pcurve, start, end = source
        key = (id(curve), start, end)
        if key not in strays:
            a, b, m = curve.Value(start), curve.Value(end), curve.Value((start + end) / 2)
            chord = gp_Pnt((a.X() + b.X()) / 2, (a.Y() + b.Y()) / 2, (a.Z() + b.Z()) / 2)
            strays[key] = m.Distance(chord) > sag
        return strays[key]

    for _round in range(_UNCROSS_ROUNDS):
        crossing = _crossing_segments(_segments(loops))
        sources = [source for *_rest, loop_sources in loops for source in loop_sources]
        wanted = {k for k, source in enumerate(sources)
                  if source is not None and (k in crossing or strays_from(source))}
        if not wanted or sum(len(uv) for uv, *_rest in loops) + len(wanted) > _MAX_BOUNDARY_POINTS:
            return loops
        split, first, result = 0, 0, []
        for uv, xyz, shared, sources in loops:
            count = len(uv)
            points, places, edges, curves = [], [], [], []
            for k in range(count):
                points.append(tuple(uv[k]))
                places.append(xyz[k])
                source, neighbour = sources[k], shared[k]
                middle = None
                if first + k in wanted:
                    edge, curve, pcurve, start, end = source
                    halfway = (start + end) / 2
                    point = pcurve.Value(halfway)
                    middle = (point.X(), point.Y())
                    chord = (uv[k] + uv[(k + 1) % count]) / 2
                    if abs(middle[0] - chord[0]) + abs(middle[1] - chord[1]) <= still:
                        middle = None
                if middle is None:
                    edges.append(neighbour)
                    curves.append(source)
                    continue
                split += 1
                if neighbour is None:
                    place, halves = None, (None, None)
                else:
                    at = curve.Value(halfway).Transformed(to_face)
                    place = (at.X(), at.Y(), at.Z())
                    share = (neighbour[4] + neighbour[5]) / 2
                    halves = ((*neighbour[:4], neighbour[4], share), (*neighbour[:4], share, neighbour[5]))
                edges.extend(halves)
                curves.extend(((edge, curve, pcurve, start, halfway), (edge, curve, pcurve, halfway, end)))
                points.append(middle)
                places.append(place)
            result.append((np.array(points, float), places, edges, curves))
            first += count
        if not split:
            return loops
        loops = result
    return loops


def _crossing_segments(segments: np.ndarray) -> set[int]:
    """The segments that cross another one properly, each through the other's inside: two
    that only meet at an end -- each segment and the next -- do not. The pairs tested are
    those sharing a cell of a grid as fine as the square root of their count, so a boundary
    of thousands of points costs as many tests, not their square."""
    count = len(segments)
    low, high = segments.min(axis=(0, 1)), segments.max(axis=(0, 1))
    if count < 4 or not (high > low).all():
        return set()
    steps = max(1, math.isqrt(count))
    by_cell = _cells_of_segments(segments, np.linspace(low[0], high[0], steps + 1),
                                 np.linspace(low[1], high[1], steps + 1))
    firsts, seconds, pairs = [], [], 0
    for members in by_cell.values():
        if len(members) < 2:
            continue
        ordered = np.fromiter(sorted(members), np.int64, len(members))
        a, b = np.triu_indices(len(ordered), 1)
        pairs += len(a)
        if pairs > _MAX_CROSSING_PAIRS:
            return set()
        firsts.append(ordered[a])
        seconds.append(ordered[b])
    if not firsts:
        return set()
    i, j = np.concatenate(firsts), np.concatenate(seconds)
    p, q, r, s = segments[i, 0], segments[i, 1], segments[j, 0], segments[j, 1]

    def side(o, a, b):
        return (a[:, 0] - o[:, 0]) * (b[:, 1] - o[:, 1]) - (a[:, 1] - o[:, 1]) * (b[:, 0] - o[:, 0])

    hit = (side(p, q, r) * side(p, q, s) < 0) & (side(r, s, p) * side(r, s, q) < 0)
    return set(i[hit].tolist()) | set(j[hit].tolist())


def _edge_points(edge, face, pcurve, ancestors, location, deflection: float, angle: float):
    """Increasing parameters along ``edge`` for the face's boundary, the point in the face's
    frame each one is fixed at (None where the surface places it), and, when a meshed
    neighbour gave them, (that neighbour, its node at each, its frame from the face's)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    first, last = pcurve.FirstParameter(), pcurve.LastParameter()
    if BRep_Tool.Degenerated_s(edge):
        # One point in space -- a pole, a tip, or a boolean's leftover where the surface is
        # not pinched at all -- and a run of parameters on the face: every point of the run
        # is the vertex, where the neighbours' meshes end too.
        vertex = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(edge)).Transformed(location.Transformation().Inverted())
        return (list(np.linspace(first, last, _DEGENERATE_POINTS)),
                [(vertex.X(), vertex.Y(), vertex.Z())] * _DEGENERATE_POINTS, None)
    index = ancestors.FindIndex(edge)
    for other in (ancestors.FindFromIndex(index) if index else []):
        if other.IsSame(face):
            continue
        neighbour = TopoDS.Face_s(other)
        place = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(neighbour, place)
        if triangulation is None or triangulation.NbTriangles() == 0:
            continue
        polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, place)
        if polygon is None or not polygon.HasParameters():
            continue
        # The neighbour's frame and the face's: the same in a component as built, but not always.
        to_face = location.Transformation().Inverted().Multiplied(place.Transformation())
        rows = []
        for k in range(1, polygon.NbNodes() + 1):
            node = polygon.Node(k)
            point = triangulation.Node(node).Transformed(to_face)
            rows.append((polygon.Parameter(k), (point.X(), point.Y(), point.Z()), node))
        rows.sort(key=lambda row: row[0])
        return [row[0] for row in rows], [row[1] for row in rows], (neighbour, [row[2] for row in rows], to_face)
    # A seam, a free edge, or one no neighbour meshed along: the edge's own curve.
    sampler = GCPnts_TangentialDeflection(BRepAdaptor_Curve(edge), angle, deflection, 2)
    parameters = sorted(sampler.Parameter(k) for k in range(1, sampler.NbPoints() + 1))
    return parameters, [None] * len(parameters), None


def _normal_scale(surface, box) -> float:
    """The size the surface's normal (Su x Sv) has across the face, read off a 9 x 9 grid."""
    from OCP.gp import gp_Pnt, gp_Vec

    point, d_u, d_v = gp_Pnt(), gp_Vec(), gp_Vec()
    u0, u1, v0, v1 = box
    sizes = []
    for u in np.linspace(u0, u1, 9):
        for v in np.linspace(v0, v1, 9):
            surface.D1(float(u), float(v), point, d_u, d_v)
            sizes.append(d_u.Crossed(d_v).Magnitude())
    return float(np.median(sizes))


def _refine(mesh: _Mesh, surface, deflection: float, angle: float, normal_scale: float) -> None:
    """Split every edge whose midpoint strays from the surface by more than ``deflection``,
    or whose ends' normals part by more than ``angle``, and a triangle's longest edge where
    its centre strays, round after round, each triangle into two, three or four by how many
    of its edges split. A midpoint is one vertex for both triangles beside it, so the mesh
    stays whole; the earlier tessellator refined so."""
    from OCP.gp import gp_Pnt, gp_Vec

    point, d_u, d_v = gp_Pnt(), gp_Vec(), gp_Vec()
    normals: dict[int, Any] = {}

    def normal(index: int):
        if index not in normals:
            u, v = mesh.uv[index]
            surface.D1(u, v, point, d_u, d_v)
            cross = d_u.Crossed(d_v)
            size = cross.Magnitude()
            normals[index] = cross.Divided(size) if size > _NORMAL_FLOOR * normal_scale > 0 else None
        return normals[index]

    for _round in range(_REFINE_ROUNDS):
        midpoints: dict[tuple[int, int], int] = {}
        for a, b, c in mesh.triangles:
            for x, y in ((a, b), (b, c), (c, a)):
                key = (x, y) if x < y else (y, x)
                if key in midpoints:
                    continue
                (ux, vx), (uy, vy) = mesh.uv[x], mesh.uv[y]
                um, vm = (ux + uy) / 2, (vx + vy) / 2
                on = np.array(mesh.on_surface(surface, um, vm))
                chord = (np.array(mesh.xyz[x]) + np.array(mesh.xyz[y])) / 2
                nx, ny = normal(x), normal(y)
                turned = nx is not None and ny is not None and nx.Angle(ny) > angle
                midpoints[key] = (mesh.vertex(um, vm, tuple(on)) if float(np.linalg.norm(on - chord)) > deflection
                                  or turned else -1)
        # A boundary edge (one triangle uses it) splits only on its own midpoint above, which
        # both sides of a seam judge alike: a centre's split is an inner edge's.
        uses: dict[tuple[int, int], int] = {}
        for a, b, c in mesh.triangles:
            for x, y in ((a, b), (b, c), (c, a)):
                key = (x, y) if x < y else (y, x)
                uses[key] = uses.get(key, 0) + 1
        for a, b, c in mesh.triangles:
            corners = np.array([mesh.xyz[a], mesh.xyz[b], mesh.xyz[c]])
            (ua, va), (ub, vb), (uc, vc) = mesh.uv[a], mesh.uv[b], mesh.uv[c]
            centre = np.array(mesh.on_surface(surface, (ua + ub + uc) / 3, (va + vb + vc) / 3))
            if float(np.linalg.norm(centre - corners.mean(axis=0))) > deflection:
                inner = [(x, y) for x, y in ((a, b), (b, c), (c, a)) if uses[(x, y) if x < y else (y, x)] > 1]
                if not inner:
                    continue
                x, y = max(inner, key=lambda edge: float(np.linalg.norm(
                    np.array(mesh.xyz[edge[0]]) - np.array(mesh.xyz[edge[1]]))))
                key = (x, y) if x < y else (y, x)
                if midpoints.get(key, -1) < 0:
                    (ux, vx), (uy, vy) = mesh.uv[x], mesh.uv[y]
                    um, vm = (ux + uy) / 2, (vx + vy) / 2
                    midpoints[key] = mesh.vertex(um, vm, mesh.on_surface(surface, um, vm))
        split = {key: index for key, index in midpoints.items() if index >= 0}
        if not split or len(mesh.triangles) * 4 > _MAX_TRIANGLES:
            return
        refined = []
        for a, b, c in mesh.triangles:
            ab, bc, ca = (split.get((x, y) if x < y else (y, x), -1) for x, y in ((a, b), (b, c), (c, a)))
            count = (ab >= 0) + (bc >= 0) + (ca >= 0)
            if count == 0:
                refined.append((a, b, c))
            elif count == 3:
                refined.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
            else:
                # Turn the triangle so its first edge splits: (a, b) with m; then (b, c) may too.
                while ab < 0:
                    a, b, c, ab, bc, ca = b, c, a, bc, ca, ab
                if count == 1:
                    refined.extend(((a, ab, c), (ab, b, c)))
                elif bc >= 0:
                    refined.extend(((a, ab, bc), (ab, b, bc), (a, bc, c)))
                else:
                    refined.extend(((a, ab, ca), (ab, b, c), (ab, c, ca)))
        mesh.triangles = [triangle for triangle in refined if len(set(triangle)) == 3]


def _grid_steps(surface, box, direction: int, deflection: float, angle: float) -> int:
    """How many cells the grid cuts ``direction`` into (0: u, 1: v): enough that no cell's
    chord strays from the surface by more than ``deflection`` nor its normal turns by more
    than ``angle``, measured over probe lines -- chord error grows as a cell's square,
    turning as its length -- as the earlier tessellator sized its grid."""
    from OCP.gp import gp_Pnt, gp_Vec

    u0, u1, v0, v1 = box
    point, d_u, d_v = gp_Pnt(), gp_Vec(), gp_Vec()

    def at(t: float, across: float):
        u, v = (t, across) if direction == 0 else (across, t)
        surface.D1(u, v, point, d_u, d_v)
        normal = d_u.Crossed(d_v)
        size = normal.Magnitude()
        return np.array((point.X(), point.Y(), point.Z())), (normal.Divided(size) if size > 0 else None), size

    start, span = (u0, u1 - u0) if direction == 0 else (v0, v1 - v0)
    scale = _normal_scale(surface, box)
    worst_chord = worst_turn = 0.0
    for line in range(_PROBES + 1):
        across = (v0 + (v1 - v0) * line / _PROBES) if direction == 0 else (u0 + (u1 - u0) * line / _PROBES)
        for step in range(_PROBES):
            t0 = start + span * step / _PROBES
            t1 = t0 + span / _PROBES
            (pa, na, sa), (pb, nb, sb), (pm, _nm, _sm) = at(t0, across), at(t1, across), at((t0 + t1) / 2, across)
            worst_chord = max(worst_chord, float(np.linalg.norm(pm - (pa + pb) / 2)))
            if min(sa, sb) > _NORMAL_FLOOR * scale > 0:
                worst_turn = max(worst_turn, na.Angle(nb))
    needed = max(_PROBES * math.sqrt(worst_chord / deflection), _PROBES * worst_turn / angle if angle > 0 else 0.0)
    return int(min(_MAX_STEPS, max(_MIN_STEPS, math.ceil(needed))))


def _cells_of_segments(segments: np.ndarray, grid_u: np.ndarray, grid_v: np.ndarray) -> dict:
    """Each cell a boundary segment passes through, with the segments that do. A segment is
    cut to at most a cell's size first, so each piece's box covers only cells it can touch."""
    du, dv = grid_u[1] - grid_u[0], grid_v[1] - grid_v[0]
    start, end = segments[:, 0], segments[:, 1]
    pieces = np.maximum(1, np.ceil(np.maximum(np.abs(end[:, 0] - start[:, 0]) / du,
                                              np.abs(end[:, 1] - start[:, 1]) / dv))).astype(int)
    owner = np.repeat(np.arange(len(segments)), pieces)
    offset = np.arange(pieces.sum()) - np.repeat(np.cumsum(pieces) - pieces, pieces)
    a = start[owner] + (end[owner] - start[owner]) * (offset / pieces[owner])[:, None]
    b = start[owner] + (end[owner] - start[owner]) * ((offset + 1) / pieces[owner])[:, None]

    def cell(values, origin, size, steps):
        return np.clip(np.floor((values - origin) / size).astype(int), 0, steps - 1)

    steps_u, steps_v = len(grid_u) - 1, len(grid_v) - 1
    lo_u, hi_u = cell(np.minimum(a[:, 0], b[:, 0]), grid_u[0], du, steps_u), cell(np.maximum(a[:, 0], b[:, 0]), grid_u[0], du, steps_u)
    lo_v, hi_v = cell(np.minimum(a[:, 1], b[:, 1]), grid_v[0], dv, steps_v), cell(np.maximum(a[:, 1], b[:, 1]), grid_v[0], dv, steps_v)
    by_cell: dict[tuple[int, int], set[int]] = {}
    for segment, i0, i1, j0, j1 in zip(owner.tolist(), lo_u.tolist(), hi_u.tolist(), lo_v.tolist(), hi_v.tolist()):
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                by_cell.setdefault((i, j), set()).add(segment)
    return by_cell


def _inside_cells(segments: np.ndarray, grid_u: np.ndarray, grid_v: np.ndarray) -> np.ndarray:
    """Whether each cell's centre lies inside the loops, even-odd, one scanline per row."""
    centres_u = (grid_u[:-1] + grid_u[1:]) / 2
    inside = np.zeros((len(centres_u), len(grid_v) - 1), dtype=bool)
    u_a, v_a, u_b, v_b = segments[:, 0, 0], segments[:, 0, 1], segments[:, 1, 0], segments[:, 1, 1]
    for j, v in enumerate((grid_v[:-1] + grid_v[1:]) / 2):
        straddle = (v_a > v) != (v_b > v)
        if straddle.any():
            crossings = np.sort(u_a[straddle] + (v - v_a[straddle]) * (u_b[straddle] - u_a[straddle])
                                / (v_b[straddle] - v_a[straddle]))
            inside[:, j] = np.searchsorted(crossings, centres_u) % 2 == 1
    return inside


def _clip_to_cell(points: np.ndarray, u0: float, u1: float, v0: float, v1: float) -> np.ndarray:
    """``points`` (a closed polygon) clipped to the cell, Sutherland-Hodgman, as numpy."""
    for axis, bound, below in ((0, u0, False), (0, u1, True), (1, v0, False), (1, v1, True)):
        if len(points) < 3:
            return points[:0]
        keep = points[:, axis] <= bound if below else points[:, axis] >= bound
        if keep.all():
            continue
        previous = np.roll(points, 1, axis=0)
        crossing = keep != np.roll(keep, 1)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            t = (bound - previous[:, axis]) / (points[:, axis] - previous[:, axis])
            meeting = previous + t[:, None] * (points - previous)
        meeting[:, axis] = bound
        points = np.stack([meeting, points], axis=1)[np.stack([crossing, keep], axis=1)]
    return points


def _area(points) -> float:
    x, y = np.asarray(points, float).T
    return float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum() / 2)


def _triangulate(outer, holes, tiny_length: float, tiny_area: float) -> list:
    """Ear-clip ``outer`` with ``holes`` (each a polygon of (u, v)) into counter-clockwise
    triangles. A crossing boundary gives a cell's piece no clean ears; it is then clipped
    at its most convex corners, as the earlier tessellator's earcut cured it."""
    polygon = _cleaned(outer, tiny_length)
    if len(polygon) < 3:
        return []
    if _area(polygon) < 0:
        polygon.reverse()
    for hole in sorted((_cleaned(hole, tiny_length) for hole in holes), key=lambda hole: -max((p[0] for p in hole), default=0.0)):
        if len(hole) < 3:
            continue
        if _area(hole) > 0:
            hole.reverse()
        polygon = _bridged(polygon, hole)
    return _ear_clip(polygon, tiny_area)


def _cleaned(points, tiny: float) -> list:
    """The polygon's corners without a repeat in a row or a closing repeat."""
    kept: list = []
    for point in (tuple(map(float, p)) for p in points):
        if not kept or abs(point[0] - kept[-1][0]) + abs(point[1] - kept[-1][1]) > tiny:
            kept.append(point)
    while len(kept) > 1 and abs(kept[0][0] - kept[-1][0]) + abs(kept[0][1] - kept[-1][1]) <= tiny:
        kept.pop()
    return kept


def _bridged(polygon: list, hole: list) -> list:
    """``polygon`` and ``hole`` joined into one polygon along a segment that crosses neither:
    from the hole's rightmost corner to the nearest corner of the polygon it can see."""
    m = max(range(len(hole)), key=lambda k: hole[k][0])
    h = hole[m]
    edges = [(polygon[k], polygon[(k + 1) % len(polygon)]) for k in range(len(polygon))]
    edges += [(hole[k], hole[(k + 1) % len(hole)]) for k in range(len(hole))]
    for k in sorted(range(len(polygon)), key=lambda k: (polygon[k][0] - h[0]) ** 2 + (polygon[k][1] - h[1]) ** 2):
        p = polygon[k]
        if not any(_proper_cross(h, p, a, b) for a, b in edges):
            return polygon[:k + 1] + hole[m:] + hole[:m + 1] + polygon[k:]
    return polygon


def _proper_cross(p, q, a, b) -> bool:
    def side(o, s, t):
        return (s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0])
    return side(p, q, a) * side(p, q, b) < 0 and side(a, b, p) * side(a, b, q) < 0


def _ear_clip(polygon: list, tiny: float) -> list:
    corners = list(polygon)
    triangles = []

    def turn(k):
        a, b, c = corners[k - 1], corners[k], corners[(k + 1) % len(corners)]
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def is_ear(k):
        if turn(k) <= tiny:
            return False
        a, b, c = corners[k - 1], corners[k], corners[(k + 1) % len(corners)]
        for p in corners:
            if p in (a, b, c):
                continue
            if all((s[0] - r[0]) * (p[1] - r[1]) - (s[1] - r[1]) * (p[0] - r[0]) > -tiny for r, s in ((a, b), (b, c), (c, a))):
                return False
        return True

    while len(corners) > 3:
        ear = next((k for k in range(len(corners)) if is_ear(k)), None)
        if ear is None:
            # No clean ear: drop a corner that turns by nothing, else clip the most convex
            # corner whatever it covers (the boundary crosses itself in this cell).
            turns = [turn(k) for k in range(len(corners))]
            flat = next((k for k, value in enumerate(turns) if abs(value) <= tiny), None)
            if flat is not None:
                del corners[flat]
                continue
            ear = max(range(len(corners)), key=lambda k: turns[k])
            if turns[ear] <= 0:
                break
        triangles.append((corners[ear - 1], corners[ear], corners[(ear + 1) % len(corners)]))
        del corners[ear]
    if len(corners) == 3 and turn(1) > tiny:
        triangles.append(tuple(corners))
    return triangles


def _conform_neighbours(mesh: _Mesh, boundary: set, segments: np.ndarray, shared: list, sources: list,
                        by_cell: dict, grid_u: np.ndarray, grid_v: np.ndarray) -> None:
    """Split each meshed neighbour's triangle along a shared edge where this face's boundary
    took a point the neighbour lacks -- a grid line crossing it, or a point ``_uncrossed``
    put on the edge's curve -- so the two meshes share every vertex along it. The
    neighbour's triangulation is grown in place: its own nodes keep their numbers, which
    its edges' discretizations name."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve2d
    from OCP.gp import gp_Pnt, gp_Pnt2d
    from OCP.Poly import Poly_Triangle
    from OCP.TopLoc import TopLoc_Location

    du, dv = grid_u[1] - grid_u[0], grid_v[1] - grid_v[0]
    used = {index for triangle in mesh.triangles for index in triangle}
    # Per face segment along a neighbour: the points this face's triangles put on it, as
    # (the share of the way from the neighbour's one node to its other, the vertex, and the
    # edge and its parameter where the point is the edge curve's, else None).
    runs: dict[int, list] = {}
    for index in used - boundary:
        u, v = mesh.uv[index]
        i, j = (u - grid_u[0]) / du, (v - grid_v[0]) / dv
        nearby = set()
        for ci in {math.floor(i) - 1, math.floor(i), math.floor(i) + 1}:
            for cj in {math.floor(j) - 1, math.floor(j), math.floor(j) + 1}:
                nearby |= by_cell.get((ci, cj), set())
        for segment in nearby:
            if shared[segment] is None:
                continue
            a, b = segments[segment]
            span, offset = b - a, np.array((u, v)) - a
            length = float(span @ span)
            t = float(offset @ span) / length if length > 0 else -1.0
            if 1e-9 < t < 1 - 1e-9 and abs(offset[0] * span[1] - offset[1] * span[0]) <= 1e-9 * length:
                start, end = shared[segment][4:6]
                runs.setdefault(segment, []).append((start + t * (end - start), index, None))
                break
    for segment, neighbour in enumerate(shared):
        # A segment ending short of the neighbour's node ends at a point ``_uncrossed`` added.
        if neighbour is None or neighbour[5] >= 1.0:
            continue
        index = mesh.keys.get(mesh.key(*segments[segment][1]))
        if index is not None and index in used:
            edge, _curve, _pcurve, _start, end = sources[segment]
            runs.setdefault(segment, []).append((neighbour[5], index, (edge, end)))
    if not runs:
        return
    # One neighbour edge may run along several of this face's segments: its points are split
    # into its triangle together.
    by_neighbour: list = []
    for segment, run in runs.items():
        neighbour, node_a, node_b, to_face = shared[segment][:4]
        entry = next((entry for entry in by_neighbour if entry[0].IsSame(neighbour)), None)
        if entry is None:
            entry = [neighbour, to_face.Inverted(), {}]
            by_neighbour.append(entry)
        entry[2].setdefault((node_a, node_b), []).extend(run)
    for neighbour, to_neighbour, splits in by_neighbour:
        triangulation = BRep_Tool.Triangulation_s(neighbour, TopLoc_Location())
        if triangulation.HasNormals():
            triangulation.RemoveNormals()
        count = triangulation.NbNodes()
        triangles = [list(triangulation.Triangle(k).Get()) for k in range(1, triangulation.NbTriangles() + 1)]
        owner = {}
        for k, (p, q, r) in enumerate(triangles):
            for first, second in ((p, q), (q, r), (r, p)):
                owner[(first, second)] = k
        added = []
        for (node_a, node_b), run in splits.items():
            forward = owner.get((node_a, node_b))
            backward = owner.get((node_b, node_a)) if forward is None else None
            if forward is None and backward is None:
                continue
            numbers = []
            for t, index, on_edge in sorted(run, key=lambda point: point[0]):
                x, y, z = mesh.xyz[index]
                added.append((gp_Pnt(x, y, z).Transformed(to_neighbour), node_a, node_b, t, on_edge))
                numbers.append(count + len(added))
            if forward is not None:
                chain, k = [node_a, *numbers, node_b], forward
            else:
                chain, k = [node_b, *numbers[::-1], node_a], backward
            p, q, r = triangles[k]
            third = next(n for n in (p, q, r) if n not in (chain[0], chain[-1]))
            fan = [[c0, c1, third] for c0, c1 in zip(chain, chain[1:])]
            triangles[k] = fan[0]
            for extra in fan[1:]:
                triangles.append(extra)
            for t_index, (c0, c1, _third) in enumerate(fan):
                at = k if t_index == 0 else len(triangles) - len(fan) + t_index
                owner[(c0, c1)] = at
                owner[(c1, third)] = at
                owner[(third, c0)] = at
        if not added:
            continue
        triangulation.ResizeNodes(count + len(added), True)
        for k, (point, node_a, node_b, t, on_edge) in enumerate(added, count + 1):
            triangulation.SetNode(k, point)
            if triangulation.HasUVNodes():
                if on_edge is not None:
                    # A point on the edge's curve is where the neighbour's own curve of the
                    # edge puts its parameter.
                    edge, parameter = on_edge
                    triangulation.SetUVNode(k, BRepAdaptor_Curve2d(edge, neighbour).Value(parameter))
                else:
                    ua, ub = triangulation.UVNode(node_a), triangulation.UVNode(node_b)
                    triangulation.SetUVNode(k, gp_Pnt2d(ua.X() + t * (ub.X() - ua.X()), ua.Y() + t * (ub.Y() - ua.Y())))
        triangulation.ResizeTriangles(len(triangles), True)
        for k, (p, q, r) in enumerate(triangles, 1):
            triangulation.SetTriangle(k, Poly_Triangle(p, q, r))


