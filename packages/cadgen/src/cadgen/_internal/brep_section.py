"""One component's exact section: the material a plane cuts from its BREP.

What ``cadgen step snapshot --mode section`` draws. Everything is cut in the
component's own coordinates, from its exact shape, so a cylinder cut across its
axis is a circle -- a centre, an axis and a radius -- and never the chords of a
tessellation.

A section is what the plane cuts out of material, and only a solid has any:

- A SOLID's cut is the region of the plane inside it: the faces OCCT's Boolean
  common of the solids and a planar face spanning them leaves
  (``BRepAlgoAPI_Common``). Each face's wires are the exact boundary of
  material, so they are the loops the drawing fills and hatches. A plane that
  only touches a solid -- tangent to a torus's top, along a cylinder's side --
  leaves no face and cuts nothing, while a face of the solid lying in the plane
  is material in the plane and is its own cut.
- A SHEET (a face or shell that bounds no solid) has no inside. The plane cuts
  it along curves (``BRepAlgoAPI_Section``), joined into wires
  (``ShapeAnalysis_FreeBounds``): drawn as lines, never filled, even when one
  closes on itself.
- A wire or a free edge is no material at all: even one lying in the plane is
  no part of the section.

Every wire is walked in order (``BRepTools_WireExplorer``), so each loop comes
out oriented and connected, and each edge is one of three records, in the
component's own coordinates:

- ``{"line": [start, end]}``;
- ``{"arc": {"center", "axis", "radius", "start", "sweep"}}`` -- a circular
  arc, ``sweep`` radians about ``axis`` from ``start`` (2*pi for a whole
  circle; negative when the edge runs against the circle's own axis);
- ``{"points": [...]}`` -- any other curve (an ellipse, a B-spline), sampled
  at ``deflection`` model units, ends included.

The result is ``{"loops": [{"closed": bool, "filled": bool, "edges": [...]},
...]}``: ``filled`` loops bound a solid's cut and are always closed; the rest
are a sheet's cut curves.

Kernel work: only a build-pool worker imports this (``cadgen.store.sections``).
"""

from __future__ import annotations

import math
from typing import Any

# A sheet's cut edges within this distance of each other's ends are one wire.
# Relative to the component's bounding diagonal, floored for a degenerate one.
_CONNECT_TOLERANCE = 1e-7
_SCALE_FLOOR = 1e-9


def _point(value) -> list[float]:
    return [float(coordinate) for coordinate in value.Coord()]


def _box(shape):
    """``(min corner, max corner)`` of ``shape``'s box, or ``None`` for an empty shape."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return None
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin), (xmax, ymax, zmax)


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


def _walk(wire, deflection: float, face=None) -> list[dict[str, Any]]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools_WireExplorer

    walker = BRepTools_WireExplorer(wire) if face is None else BRepTools_WireExplorer(wire, face)
    records = []
    while walker.More():
        edge = walker.Current()
        if not BRep_Tool.Degenerated_s(edge):
            records.append(_edge_record(edge, deflection))
        walker.Next()
    return records


def _compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder, compound = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _subshapes(shape, kind, avoid=None) -> list:
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, kind) if avoid is None else TopExp_Explorer(shape, kind, avoid)
    found = []
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found


def _solid_cut(solids, normal, offset: float, deflection: float) -> list[dict[str, Any]]:
    """The faces of the plane inside ``solids``, as filled loops."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCP.TopoDS import TopoDS

    box = _box(solids)
    if box is None:
        return []
    low, high = box
    # A square of the plane centred on the box's centre projected onto it, its
    # half side the box's whole diagonal: every point of the solids projects
    # well inside it, so its common with them is their entire cut.
    centre = [(a + b) / 2 for a, b in zip(low, high)]
    reach = max(math.dist(low, high), _SCALE_FLOOR)
    above = sum(c * n for c, n in zip(centre, normal)) - offset
    if abs(above) > reach:
        return []  # the plane misses the box, so it misses the solids
    origin = gp_Pnt(*(c - above * n for c, n in zip(centre, normal)))
    plane = BRepBuilderAPI_MakeFace(gp_Pln(origin, gp_Dir(*normal)), -reach, reach, -reach, reach).Face()
    common = BRepAlgoAPI_Common(solids, plane)
    if not common.IsDone():
        raise ValueError("OCCT could not section this component's solids")
    loops = []
    for face in _subshapes(common.Shape(), TopAbs_FACE):
        face = TopoDS.Face_s(face)
        for wire in _subshapes(face, TopAbs_WIRE):
            records = _walk(TopoDS.Wire_s(wire), deflection, face)
            if records:
                loops.append({"closed": True, "filled": True, "edges": records})
    return loops


def _sheet_cut(sheets, normal, offset: float, deflection: float, diagonal: float) -> list[dict[str, Any]]:
    """The curves the plane cuts from ``sheets``, as unfilled loops."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_HSequenceOfShape

    origin = gp_Pnt(*(component * offset for component in normal))
    cut = BRepAlgoAPI_Section(sheets, gp_Pln(origin, gp_Dir(*normal)), False)
    # The cut's own curves, never a B-spline fit of them: a circle stays a circle.
    cut.Approximation(False)
    cut.ComputePCurveOn1(False)
    cut.ComputePCurveOn2(False)
    cut.Build()
    if not cut.IsDone():
        raise ValueError("OCCT could not section this component's sheets")
    edges = TopTools_HSequenceOfShape()
    for edge in _subshapes(cut.Shape(), TopAbs_EDGE):
        edges.Append(edge)
    if edges.Length() == 0:
        return []
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edges, _CONNECT_TOLERANCE * diagonal, False, wires)
    loops = []
    for index in range(1, wires.Length() + 1):
        wire = TopoDS.Wire_s(wires.Value(index))
        records = _walk(wire, deflection)
        if records:
            loops.append({"closed": bool(wire.Closed()), "filled": False, "edges": records})
    return loops


def section_loops(shape, *, normal: tuple[float, float, float], offset: float) -> dict[str, Any]:
    """The loops the plane ``normal . p == offset`` cuts from ``shape``'s material.

    ``normal`` is in the shape's own coordinates; a canonical one
    (``cadgen.store.sections.canonical_plane``) is a unit vector to within
    1e-9, and the plane is scaled to an exact one here. An empty result
    (``{"loops": []}``) is a true answer: the plane cuts no material.
    """
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID

    length = math.sqrt(sum(component * component for component in normal))
    normal, offset = tuple(component / length for component in normal), offset / length
    box = _box(shape)
    if box is None:
        return {"loops": []}
    diagonal = max(math.dist(*box), _SCALE_FLOOR)
    deflection = 1e-4 * diagonal
    solids = _subshapes(shape, TopAbs_SOLID)
    sheets = _subshapes(shape, TopAbs_FACE, TopAbs_SOLID)
    loops = []
    if solids:
        loops += _solid_cut(_compound(solids), normal, offset, deflection)
    if sheets:
        loops += _sheet_cut(_compound(sheets), normal, offset, deflection, diagonal)
    return {"loops": loops}
