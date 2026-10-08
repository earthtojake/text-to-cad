"""One component's exact section: OCCT cuts its BREP with a plane.

What ``cadgen step snapshot --mode section`` draws. The cut is
``BRepAlgoAPI_Section`` on the component's exact shape, in the component's own
coordinates, so a cylinder cut across its axis is a circle -- a centre, an axis
and a radius -- and never the chords of a tessellation. The edges the cut
leaves are joined into wires (``ShapeAnalysis_FreeBounds``) and walked in order
(``BRepTools_WireExplorer``), so every loop comes out oriented and connected.

Each edge is one of three records, in the component's own coordinates:

- ``{"line": [start, end]}``;
- ``{"arc": {"center", "axis", "radius", "start", "sweep"}}`` -- a circular
  arc, ``sweep`` radians about ``axis`` from ``start`` (2*pi for a whole
  circle; negative when the edge runs against the circle's own axis);
- ``{"points": [...]}`` -- any other curve (an ellipse, a B-spline), sampled
  at ``deflection`` model units, ends included.

The result is ``{"loops": [{"closed": bool, "edges": [...]}, ...]}``. A loop
is closed when its wire is: a solid's cut is all closed loops, while a shell or
a wire body may leave open chains, which are drawn but never filled.

Kernel work: only a build-pool worker imports this (``cadgen.store.sections``).
"""

from __future__ import annotations

import math
from typing import Any

# Edges the cut leaves within this distance of each other's ends are one wire.
# Relative to the component's bounding diagonal, floored for a degenerate one.
_CONNECT_TOLERANCE = 1e-7
_SCALE_FLOOR = 1e-9


def _point(value) -> list[float]:
    return [float(coordinate) for coordinate in value.Coord()]


def _diagonal(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return 0.0
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return math.dist((xmin, ymin, zmin), (xmax, ymax, zmax))


def _edge_record(edge, deflection: float) -> dict[str, Any]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
    from OCP.TopAbs import TopAbs_REVERSED

    curve = BRepAdaptor_Curve(edge)
    first, last = curve.FirstParameter(), curve.LastParameter()
    reversed_ = edge.Orientation() == TopAbs_REVERSED
    kind = curve.GetType()
    if kind == GeomAbs_Line:
        start, end = _point(curve.Value(first)), _point(curve.Value(last))
        return {"line": [end, start] if reversed_ else [start, end]}
    if kind == GeomAbs_Circle:
        circle = curve.Circle()
        sweep = last - first
        return {
            "arc": {
                "center": _point(circle.Location()),
                "axis": _point(circle.Axis().Direction()),
                "radius": float(circle.Radius()),
                "start": _point(curve.Value(last if reversed_ else first)),
                "sweep": float(-sweep if reversed_ else sweep),
            }
        }
    sampler = GCPnts_QuasiUniformDeflection(curve, deflection, first, last)
    if not sampler.IsDone() or sampler.NbPoints() < 2:
        points = [_point(curve.Value(first)), _point(curve.Value(last))]
    else:
        points = [_point(sampler.Value(index)) for index in range(1, sampler.NbPoints() + 1)]
    return {"points": points[::-1] if reversed_ else points}


def section_loops(shape, *, normal: tuple[float, float, float], offset: float) -> dict[str, Any]:
    """The loops the plane ``normal . p == offset`` cuts from ``shape``.

    ``normal`` is a unit vector in the shape's own coordinates. An empty result
    (``{"loops": []}``) is a true answer: the plane misses the shape.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_HSequenceOfShape

    diagonal = max(_diagonal(shape), _SCALE_FLOOR)
    origin = gp_Pnt(*(component * offset for component in normal))
    cut = BRepAlgoAPI_Section(shape, gp_Pln(origin, gp_Dir(*normal)), False)
    # The cut's own curves, never a B-spline fit of them: a circle stays a circle.
    cut.Approximation(False)
    cut.ComputePCurveOn1(False)
    cut.ComputePCurveOn2(False)
    cut.Build()
    if not cut.IsDone():
        raise ValueError("OCCT could not section this component")
    edges = TopTools_HSequenceOfShape()
    explorer = TopExp_Explorer(cut.Shape(), TopAbs_EDGE)
    while explorer.More():
        edges.Append(explorer.Current())
        explorer.Next()
    if edges.Length() == 0:
        return {"loops": []}
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edges, _CONNECT_TOLERANCE * diagonal, False, wires)
    deflection = 1e-4 * diagonal
    loops = []
    for index in range(1, wires.Length() + 1):
        wire = TopoDS.Wire_s(wires.Value(index))
        walker = BRepTools_WireExplorer(wire)
        records = []
        while walker.More():
            records.append(_edge_record(walker.Current(), deflection))
            walker.Next()
        if records:
            loops.append({"closed": bool(wire.Closed()), "edges": records})
    return {"loops": loops}
