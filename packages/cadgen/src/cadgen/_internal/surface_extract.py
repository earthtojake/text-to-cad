"""B-rep surface extraction: the `.surf` component artifact.

A `.surf` describes one component's exact topology for the clients that select,
measure and recognize it: per-face analytic surfaces (a bilinear B-spline patch
also keeps its four corners), each face's loops as ordered edge references, the
analytic curve of every edge, and the selector-table metadata -- surface and
curve types, parameters, exact metrics from GProps/BndLib, edge classes and
solid membership. Face and edge ordinals follow the ``TopExp.MapShapes_s``
order the selector system has always used, so refs (``#o1.2.f5``) keep their
meaning, and the component's mesh (``occt_mesh``) is grouped by the same
ordinals.

Nothing here tessellates, and nothing reads a `.surf` to tessellate: meshes
are cadgen's, made by OCCT from the exact BREP. So a `.surf` carries no
tessellation inputs -- no trim curves in parameter space, no control nets, no
basis curves of swept surfaces.

Container layout (GLB-style, little-endian):

    magic  b"SURF" | version u32 | json_len u32 | json bytes | f32 bin

The f32 binary chunk holds the bilinear patches' corners; the JSON index
references them as ``[offset_in_floats, count]`` pairs.
"""

from __future__ import annotations

import json
import struct
from typing import Any

from cadgen._internal.surf_container import SURF_MAGIC
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_Orientation,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)
from OCP.TopoDS import TopoDS

# 2: shape membership, selector-table metadata (surfaceType/curveType/
#    params/continuity/dihedral/flags), edge faceOrds.
# 3: no tessellation inputs. Loops are edge references, a B-spline surface
#    carries its degrees and pole counts (a bilinear patch its four corners),
#    a swept surface its axis or direction, a general curve its range.
SURF_VERSION = 3
# A store may still hold version-2 surfaces an older build pinned (an
# eager-only component's surface is part of its geometry identity); version 3
# only removed fields, so every reader reads both.
SURF_VERSIONS_READ = (2, 3)


def _enum_name_geomabs(value) -> str:
    # Same spelling the STEP_TOPOLOGY manifest has always used
    # (step_scene_loader._enum_name with the GeomAbs_ prefix stripped,
    # lowercased): "plane", "cylinder", "bsplinesurface", "line", ...
    from cadgen._internal.step_scene_types import _enum_name

    return _enum_name(value, "GeomAbs_")


def _selector_surface_params(adaptor) -> dict[str, Any]:
    from cadgen._internal.step_scene_geometry import _surface_params

    try:
        return _surface_params(adaptor, None)
    except Exception:
        return {}


def _selector_curve_params(adaptor) -> dict[str, Any]:
    from cadgen._internal.step_scene_geometry import _curve_params

    try:
        return _curve_params(adaptor, None)
    except Exception:
        return {}


def _bnd_box(topo) -> list[float] | None:
    """The face's or edge's own bounding box, TIGHT.

    ``BRepBndLib::Add`` bounds a B-spline by its CONTROL POLYGON, which for a
    NURBS circle of radius r reaches r/cos(22.5 deg) = 1.082 r -- an 8% overshoot
    on every rounded surface. These boxes are what ``inspect refs --facts``
    reports as bounds and what a caller measures clearance against, so they must
    describe the surface, not its poles: ``AddOptimal`` subdivides instead.
    ``useTriangulation=False`` throughout, because meshing here would mutate the
    shared ``TShape`` and break content-addressed component dedup.
    """
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        try:
            BRepBndLib.AddOptimal_s(topo, box, False, False)
        except Exception:
            box = Bnd_Box()
            BRepBndLib.Add_s(topo, box, False)
        if box.IsVoid():
            return None
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return [xmin, ymin, zmin, xmax, ymax, zmax]
    except Exception:
        return None


def _face_metrics(face) -> dict[str, Any]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    metrics: dict[str, Any] = {}
    try:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        metrics["area"] = float(props.Mass())
        center = props.CentreOfMass()
        metrics["center"] = [center.X(), center.Y(), center.Z()]
    except Exception:
        pass
    box = _bnd_box(face)
    if box is not None:
        metrics["bbox"] = box
    return metrics


def _edge_metrics(edge) -> dict[str, Any]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    metrics: dict[str, Any] = {}
    try:
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(edge, props)
        metrics["length"] = float(props.Mass())
        center = props.CentreOfMass()
        metrics["center"] = [center.X(), center.Y(), center.Z()]
    except Exception:
        pass
    box = _bnd_box(edge)
    if box is not None:
        metrics["bbox"] = box
    return metrics


class _Bin:
    """The single f32 buffer; append() returns [offset, count] refs."""

    def __init__(self) -> None:
        self.values: list[float] = []

    def append(self, floats) -> list[int]:
        offset = len(self.values)
        data = [float(v) for v in floats]
        self.values.extend(data)
        return [offset, len(data)]

    def payload(self) -> bytes:
        return struct.pack(f"<{len(self.values)}f", *self.values)


def _xyz(p) -> list[float]:
    return [p.X(), p.Y(), p.Z()]


def _frame(ax3) -> dict[str, list[float]]:
    return {
        "origin": _xyz(ax3.Location()),
        "xdir": _xyz(ax3.XDirection()),
        "ydir": _xyz(ax3.YDirection()),
        "zdir": _xyz(ax3.Direction()),
    }


def _clamped_uv_bounds(face, surface) -> tuple[float, float, float, float]:
    """Face UV bounds clamped into the surface's own parametric range.

    ``BRepTools.UVBounds_s`` can return a bound a floating-point hair OUTSIDE
    the surface's own domain (-0.0 against 0.0, or a few 1e-3 past a trimmed
    span on vendor STEPs), and ``Geom_RectangularTrimmedSurface`` rejects that
    outright instead of clamping. Clamp each bound in the non-periodic
    directions; periodic directions wrap, so their windows may legitimately
    extend past ``Bounds()`` and are left alone. Infinite domains (planes,
    full cylinders) make the clamp a no-op."""
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    su0, su1, sv0, sv1 = surface.Bounds()
    if not surface.IsUPeriodic():
        u0 = min(max(u0, su0), su1)
        u1 = min(max(u1, su0), su1)
    if not surface.IsVPeriodic():
        v0 = min(max(v0, sv0), sv1)
        v1 = min(max(v1, sv0), sv1)
    return u0, u1, v0, v1


def _surface_payload(face, bin_out: _Bin) -> dict[str, Any]:
    """The face's surface: analytic frames exactly, a swept surface by its axis
    or direction, a B-spline by its degrees and pole counts (the corners of a
    bilinear patch, which feature recognition reads as a ruled loft's section)."""
    adaptor = BRepAdaptor_Surface(face)
    kind = adaptor.GetType()
    if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
        plane = adaptor.Plane()
        return {"kind": "plane", **_frame(plane.Position())}
    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        return {"kind": "cylinder", "radius": cylinder.Radius(),
                **_frame(cylinder.Position())}
    if kind == GeomAbs_SurfaceType.GeomAbs_Cone:
        cone = adaptor.Cone()
        return {"kind": "cone", "radius": cone.RefRadius(),
                "semiAngle": cone.SemiAngle(), **_frame(cone.Position())}
    if kind == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        return {"kind": "sphere", "radius": sphere.Radius(),
                **_frame(sphere.Position())}
    if kind == GeomAbs_SurfaceType.GeomAbs_Torus:
        torus = adaptor.Torus()
        return {"kind": "torus", "majorRadius": torus.MajorRadius(),
                "minorRadius": torus.MinorRadius(), **_frame(torus.Position())}
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution:
        axis = adaptor.AxeOfRevolution()
        return {"kind": "revolution", "origin": _xyz(axis.Location()), "dir": _xyz(axis.Direction())}
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion:
        return {"kind": "extrusion", "dir": _xyz(adaptor.Direction())}
    surface = BRep_Tool.Surface_s(face)
    if surface is not None and kind in (GeomAbs_SurfaceType.GeomAbs_BSplineSurface,
                                        GeomAbs_SurfaceType.GeomAbs_BezierSurface):
        from OCP.Geom import Geom_RectangularTrimmedSurface

        if isinstance(surface, Geom_RectangularTrimmedSurface):
            surface = surface.BasisSurface()
        return _nurbs_summary(surface, bin_out)
    # Offset and other surfaces: their type is the face's surfaceType.
    return {"kind": "freeform"}


def _nurbs_summary(surface, bin_out: _Bin) -> dict[str, Any]:
    """A B-spline or Bezier surface's degrees, pole counts and periodicity, and
    the four corners of a bilinear patch (degree 1 by 1, 2 by 2 poles,
    polynomial, open), in u-major order."""
    nu, nv = surface.NbUPoles(), surface.NbVPoles()
    periodic_u = bool(getattr(surface, "IsUPeriodic", lambda: False)())
    periodic_v = bool(getattr(surface, "IsVPeriodic", lambda: False)())
    rational = bool(surface.IsURational() or surface.IsVRational())
    payload: dict[str, Any] = {
        "kind": "nurbs",
        "degU": surface.UDegree(),
        "degV": surface.VDegree(),
        "nu": nu,
        "nv": nv,
        "periodicU": periodic_u,
        "periodicV": periodic_v,
    }
    if rational:
        payload["rational"] = True
    elif (payload["degU"], payload["degV"], nu, nv) == (1, 1, 2, 2) and not (periodic_u or periodic_v):
        payload["poles"] = bin_out.append(
            coordinate for i in (1, 2) for j in (1, 2) for coordinate in _xyz(surface.Pole(i, j)))
    return payload


def _curve3d_payload(edge) -> dict[str, Any] | None:
    """The edge's curve: lines, circles and ellipses exactly, any other curve
    by its kind and parameter range."""
    if BRep_Tool.Degenerated_s(edge):
        return None
    adaptor = BRepAdaptor_Curve(edge)
    first, last = adaptor.FirstParameter(), adaptor.LastParameter()
    kind = adaptor.GetType()
    if kind == GeomAbs_CurveType.GeomAbs_Line:
        line = adaptor.Line()
        return {"kind": "line", "origin": _xyz(line.Location()),
                "dir": _xyz(line.Direction()), "range": [first, last]}
    if kind == GeomAbs_CurveType.GeomAbs_Circle:
        circle = adaptor.Circle()
        return {"kind": "circle", "radius": circle.Radius(),
                **_frame(circle.Position()), "range": [first, last]}
    if kind == GeomAbs_CurveType.GeomAbs_Ellipse:
        ellipse = adaptor.Ellipse()
        return {"kind": "ellipse", "majorRadius": ellipse.MajorRadius(),
                "minorRadius": ellipse.MinorRadius(),
                **_frame(ellipse.Position()), "range": [first, last]}
    return {"kind": "bspline", "range": [first, last]}


def _classify_surf_edge(edge, faces: list) -> dict[str, Any]:
    """Visibility class plus the classification columns the selector tables
    carry (continuity, dihedralDeg, flags, adjacentFaceCount) — mirrors
    step_scene_geometry._classify_edge minus its mesh dependencies."""
    from cadgen._internal.glb_topology import (
        STEP_EDGE_FLAGS as F,
        STEP_EDGE_VISIBILITY_CLASSES as C,
    )
    from cadgen._internal.glb_topology import (
        STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
    )
    from cadgen._internal.step_scene_geometry import (
        _edge_continuity_name,
        _is_smooth_continuity,
        _sampled_edge_dihedral_deg,
    )

    count = len(faces)
    result: dict[str, Any] = {
        "adjacentFaceCount": count,
        "dihedralDeg": None,
    }
    typed_faces = [TopoDS.Face_s(f) for f in faces]
    if BRep_Tool.Degenerated_s(edge):
        result.update(cls=C["DEGENERATE"], continuity="degenerate",
                      flags=F["DEGENERATE"])
        return result
    seam = any(BRep_Tool.IsClosed_s(edge, f) for f in typed_faces)
    if seam or (count == 1 and typed_faces
                and BRep_Tool.IsClosed_s(edge, typed_faces[0])):
        result.update(cls=C["SEAM"], continuity="seam", flags=F["SEAM"])
        return result
    if count == 0:
        result.update(cls=C["FEATURE"], continuity="unknown",
                      flags=F["NOT_REFERENCEABLE"] | F["UNKNOWN_CONTINUITY"])
        return result
    if count == 1:
        result.update(cls=C["BOUNDARY"], continuity="boundary",
                      flags=F["BOUNDARY"])
        return result
    if count > 2:
        result.update(cls=C["NON_MANIFOLD"], continuity="non_manifold",
                      flags=F["NON_MANIFOLD"])
        return result
    try:
        continuity = _edge_continuity_name(edge, typed_faces)
    except Exception:
        continuity = ""
    if continuity == "c0":
        dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, [None, None])
        result.update(cls=C["FEATURE"], continuity="c0", flags=F["HARD"],
                      dihedralDeg=dihedral)
        return result
    if _is_smooth_continuity(continuity):
        dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, [None, None])
        result.update(cls=C["TANGENT"], continuity=continuity,
                      flags=F["TANGENT"], dihedralDeg=dihedral)
        return result
    dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, [None, None])
    if dihedral is not None:
        if dihedral > STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG:
            result.update(cls=C["FEATURE"], continuity="sampled_hard",
                          flags=F["HARD"], dihedralDeg=dihedral)
        else:
            result.update(cls=C["TANGENT"], continuity="sampled_tangent",
                          flags=F["TANGENT"], dihedralDeg=dihedral)
        return result
    result.update(cls=C["UNKNOWN"], continuity="unknown",
                  flags=F["UNKNOWN_CONTINUITY"])
    return result


def extract_surface_component(
    shape,
    *,
    face_colors: dict | None = None,
) -> bytes:
    """Serialize one (unlocated) component shape as a .surf container.

    Geometry and per-face colours only. The part-level colour is NOT in here:
    the surf is content-addressed by geometry, so two occurrences of one part
    in different colours share one file, and the assembly.json's occurrence is
    where colour rides (``component_package._occurrence_color``)."""
    bin_out = _Bin()

    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)

    edge_ord_by_hash = {
        _shape_hash(edge_map.FindKey(i)): i
        for i in range(1, edge_map.Extent() + 1)
    }

    # Shape (solid/shell) membership: the selector tables group faces/edges
    # by solid; record each solid's ordinal + volume and every face/edge's
    # owning solid. Mirrors the prototype extraction's decomposition.
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID

    shapes_meta: list[dict[str, Any]] = []
    shape_by_face: dict[int, int] = {}
    shape_by_edge: dict[int, int] = {}
    face_ord_by_hash = {
        _shape_hash(face_map.FindKey(i)): i
        for i in range(1, face_map.Extent() + 1)
    }

    def _record_shape(sub, kind: str) -> None:
        ordinal = len(shapes_meta) + 1
        volume = None
        if kind == "solid":
            try:
                props = GProp_GProps()
                BRepGProp.VolumeProperties_s(sub, props)
                volume = float(props.Mass())
            except Exception:
                volume = None
        shapes_meta.append({"ord": ordinal, "kind": kind, "volume": volume})
        sub_faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sub, TopAbs_FACE, sub_faces)
        for i in range(1, sub_faces.Extent() + 1):
            face_ord = face_ord_by_hash.get(_shape_hash(sub_faces.FindKey(i)))
            if face_ord is not None:
                shape_by_face.setdefault(face_ord, ordinal)
        sub_edges = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sub, TopAbs_EDGE, sub_edges)
        for i in range(1, sub_edges.Extent() + 1):
            edge_ord = edge_ord_by_hash.get(_shape_hash(sub_edges.FindKey(i)))
            if edge_ord is not None:
                shape_by_edge.setdefault(edge_ord, ordinal)

    from cadgen._internal.entity_ordinals import shape_entities

    for sub in shape_entities(shape):
        kind = {TopAbs_SOLID: "solid", TopAbs_SHELL: "shell"}.get(sub.ShapeType(), "shape")
        _record_shape(sub, kind)

    faces: list[dict[str, Any]] = []
    for ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        # Clamp the recorded window into the surface's own domain: UVBounds_s
        # noise past a non-periodic domain edge (vendor STEPs: -0.0 vs 0.0,
        # or a few 1e-6 past a trimmed span) would otherwise fail the
        # coverage guard on a surface that fully covers the real face.
        face_surface = BRep_Tool.Surface_s(face)
        if face_surface is not None:
            u0, u1, v0, v1 = _clamped_uv_bounds(face, face_surface)
        else:
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
        adaptor = BRepAdaptor_Surface(face)
        entry: dict[str, Any] = {
            "ord": ordinal,
            "shape": shape_by_face.get(ordinal, 1),
            "reversed": face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED,
            "uv": [u0, u1, v0, v1],
            # Selector-table columns (surfaceType/params in the exact
            # spelling the STEP_TOPOLOGY manifest has always used), with
            # EXACT metrics from GProps/BndLib — reading, not meshing.
            "surfaceType": _enum_name_geomabs(adaptor.GetType()),
            **_face_metrics(face),
            "surface": _surface_payload(face, bin_out),
            "loops": [],
        }
        if entry["surface"].get("kind") == "plane":
            sign = -1.0 if entry["reversed"] else 1.0
            entry["normal"] = [sign * c for c in entry["surface"]["zdir"]]
        params = _selector_surface_params(adaptor)
        if params:
            entry["params"] = params
        if face_colors:
            color = face_colors.get(ordinal)
            if color is not None:
                entry["color"] = [float(c) for c in color]
        wire_explorer = TopExp_Explorer(face, TopAbs_WIRE)
        while wire_explorer.More():
            wire = TopoDS.Wire_s(wire_explorer.Current())
            loop: list[dict[str, Any]] = []
            walker = BRepTools_WireExplorer(wire, face)
            while walker.More():
                edge = walker.Current()
                loop.append({
                    "edgeOrd": edge_ord_by_hash.get(_shape_hash(edge), 0),
                    "reversed": edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED,
                })
                walker.Next()
            if loop:
                entry["loops"].append(loop)
            wire_explorer.Next()
        faces.append(entry)

    edges: list[dict[str, Any]] = []
    for ordinal in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(ordinal))
        # NB: list(TopTools_ListOfShape) costs ~2ms/call in OCP (its Python
        # iteration protocol unwinds C++ exceptions); First/Last/iterator
        # access is ~1000x cheaper and this loop runs once per edge.
        adjacent = []
        if edge_faces.Contains(edge):
            face_list = edge_faces.FindFromKey(edge)
            extent = face_list.Extent()
            if extent == 1:
                adjacent = [face_list.First()]
            elif extent == 2:
                adjacent = [face_list.First(), face_list.Last()]
            elif extent > 2:
                # Rare (non-manifold); the slow generic path is fine here.
                adjacent = list(face_list)
        # A seam edge appears under its single face TWICE in the ancestor
        # map; adjacency and faceOrds carry DEDUPED faces (matching the
        # selector tables), and a duplicate implies seam classification.
        unique_faces = []
        deduped_ords = []
        seen_face_ords = set()
        for f in adjacent:
            face_ord = face_ord_by_hash.get(_shape_hash(f), 0)
            if face_ord not in seen_face_ords:
                seen_face_ords.add(face_ord)
                unique_faces.append(f)
                deduped_ords.append(face_ord)
        classification = _classify_surf_edge(edge, unique_faces)
        if len(unique_faces) != len(adjacent):
            from cadgen._internal.glb_topology import (
                STEP_EDGE_FLAGS,
                STEP_EDGE_VISIBILITY_CLASSES,
            )

            classification["cls"] = STEP_EDGE_VISIBILITY_CLASSES["SEAM"]
            classification["continuity"] = "seam"
            classification["flags"] = STEP_EDGE_FLAGS["SEAM"]
        curve_adaptor = BRepAdaptor_Curve(edge)
        entry = {
            "ord": ordinal,
            "shape": shape_by_edge.get(ordinal, 1),
            "class": classification["cls"],
            "continuity": classification["continuity"],
            "dihedralDeg": classification["dihedralDeg"],
            "flags": int(classification["flags"]),
            "adjacentFaceCount": len(unique_faces),
            "curveType": _enum_name_geomabs(curve_adaptor.GetType()),
            "faceOrds": deduped_ords,
            **_edge_metrics(edge),
            "curve": _curve3d_payload(edge),
        }
        params = _selector_curve_params(curve_adaptor)
        if params:
            entry["params"] = params
        edges.append(entry)

    index = {
        "version": SURF_VERSION,
        "shapes": shapes_meta,
        "faces": faces,
        "edges": edges,
        "counts": {"faces": face_map.Extent(), "edges": edge_map.Extent()},
    }
    json_bytes = json.dumps(index, separators=(",", ":")).encode("utf-8")
    payload = bin_out.payload()
    return (
        SURF_MAGIC
        + struct.pack("<II", SURF_VERSION, len(json_bytes))
        + json_bytes
        + payload
    )


def _shape_hash(shape) -> int:
    # Same identity the scene loader uses for ordinal joins.
    from cadgen._internal.step_scene_loader import _shape_hash as impl

    return impl(shape)
