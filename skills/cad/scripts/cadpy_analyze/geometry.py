"""build123d/OCP geometry computations for the analyze tool.

Importing this module pulls in build123d and OCP, so keep it out of the CLI's
module-level imports — load it lazily inside command handlers (mirrors the
lazy-import discipline in ``cadpy_inspect``).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from build123d import import_step


class AnalyzeError(Exception):
    """User-facing analyze failure (bad path, empty geometry, etc.)."""


_CAD_REF = re.compile(r"@cad\[(?P<path>[^#\]]+)(?:#[^\]]*)?\]")


def resolve_step_path(target: str) -> Path:
    """Accept a plain path or an ``@cad[path#selector]`` token and return the
    STEP/STP file path (selectors are ignored; analysis is whole-solid)."""
    text = str(target).strip()
    match = _CAD_REF.search(text)
    if match:
        text = match.group("path").strip()
    path = Path(text)
    if path.suffix.lower() not in {".step", ".stp"}:
        # Tolerate a bare entry name by trying common suffixes.
        for suffix in (".step", ".stp"):
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                path = candidate
                break
    if not path.exists():
        raise AnalyzeError(f"STEP file not found: {path}")
    return path


def load_solid(target: str) -> Any:
    """Load a STEP target into a single build123d shape (Solid or Compound)."""
    path = resolve_step_path(target)
    try:
        shape = import_step(str(path))
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise AnalyzeError(f"Failed to import STEP '{path}': {exc}") from exc
    if shape is None or shape.volume <= 0:
        raise AnalyzeError(f"STEP '{path}' contains no positive-volume solid.")
    return shape


def _bbox_payload(shape: Any) -> dict:
    bb = shape.bounding_box()
    return {
        "min": [round(bb.min.X, 6), round(bb.min.Y, 6), round(bb.min.Z, 6)],
        "max": [round(bb.max.X, 6), round(bb.max.Y, 6), round(bb.max.Z, 6)],
        "size": [round(bb.size.X, 6), round(bb.size.Y, 6), round(bb.size.Z, 6)],
        "center": [
            round((bb.min.X + bb.max.X) / 2, 6),
            round((bb.min.Y + bb.max.Y) / 2, 6),
            round((bb.min.Z + bb.max.Z) / 2, 6),
        ],
    }


def _gprops(shape: Any, about: Any | None = None):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps(about) if about is not None else GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    return props


def mass_properties(shape: Any) -> dict:
    """Volume, surface area, center of mass, and the inertia tensor.

    Inertia is reported about the center of mass for a unit-density solid
    (i.e. divide by the part mass once you assign a density). Reporting about
    the COM makes the principal-axis structure (and any symmetry) visible: a
    part with N>=3-fold symmetry about Z shows Ixx == Iyy and zero products of
    inertia.
    """
    props0 = _gprops(shape)
    com = props0.CentreOfMass()
    props_com = _gprops(shape, about=com)
    mat = props_com.MatrixOfInertia()
    return {
        "volume": round(shape.volume, 6),
        "area": round(shape.area, 6),
        "centerOfMass": [round(com.X(), 6), round(com.Y(), 6), round(com.Z(), 6)],
        "inertiaAboutCom": {
            "Ixx": round(mat.Value(1, 1), 6),
            "Iyy": round(mat.Value(2, 2), 6),
            "Izz": round(mat.Value(3, 3), 6),
            "Ixy": round(mat.Value(1, 2), 6),
            "Ixz": round(mat.Value(1, 3), 6),
            "Iyz": round(mat.Value(2, 3), 6),
        },
        "inertiaReference": "centerOfMass, unit density",
        "topology": {
            "faces": len(shape.faces()),
            "edges": len(shape.edges()),
            "vertices": len(shape.vertices()),
        },
        "bbox": _bbox_payload(shape),
    }


def interference(shape_a: Any, shape_b: Any) -> dict:
    """Boolean-intersection volume between two solids (overlap detection)."""
    try:
        inter = shape_a & shape_b
        vol = inter.volume
    except Exception:  # noqa: BLE001 - degenerate boolean => treat as no overlap
        vol = 0.0
        inter = None
    if inter is None or vol < 1e-9:
        return {"interferes": False, "volume": 0.0}
    bb = inter.bounding_box()
    return {
        "interferes": True,
        "volume": round(vol, 6),
        "bounds": {
            "min": [round(bb.min.X, 6), round(bb.min.Y, 6), round(bb.min.Z, 6)],
            "max": [round(bb.max.X, 6), round(bb.max.Y, 6), round(bb.max.Z, 6)],
        },
    }


def clearance(shape_a: Any, shape_b: Any) -> dict:
    """Spatial relationship between two solids.

    Returns the minimum surface-to-surface distance plus a ``status`` that
    disambiguates the cases a single distance value can hide:

      apart            surfaces don't touch; clearance is the gap (mm)
      touching         surfaces meet; clearance ~ 0, no overlap volume
      containing       one solid fully inside the other; clearance is the
                       smallest wall thickness from inner surface to outer hull
      interpenetrating partial overlap; clearance ~ 0, both solids have volume
                       outside the other (the wall-piercing case)

    ``intersectionVolume`` / ``aOutsideB`` / ``bOutsideA`` quantify overlap so
    callers don't need a second interference call.
    """
    dist = round(shape_a.distance_to(shape_b), 6)

    def _vol(shape: Any) -> float:
        try:
            return float(shape.volume)
        except Exception:  # noqa: BLE001
            return 0.0

    def _safe(op):
        try:
            return _vol(op())
        except Exception:  # noqa: BLE001
            return None

    inter_vol = _safe(lambda: shape_a & shape_b)
    a_out = _safe(lambda: shape_a - shape_b)
    b_out = _safe(lambda: shape_b - shape_a)
    va, vb = _vol(shape_a), _vol(shape_b)

    eps = 1e-6
    overlapping = inter_vol is not None and inter_vol > eps
    if overlapping:
        a_inside = a_out is not None and a_out <= eps
        b_inside = b_out is not None and b_out <= eps
        if a_inside or b_inside:
            status = "containing"
            containment = "a_in_b" if a_inside else "b_in_a"
        else:
            status = "interpenetrating"
            containment = "neither"
    else:
        containment = "neither"
        status = "touching" if dist <= eps else "apart"

    return {
        "clearance": dist,
        "status": status,
        "containment": containment,
        "intersectionVolume": None if inter_vol is None else round(inter_vol, 6),
        "aOutsideB": None if a_out is None else round(a_out, 6),
        "bOutsideA": None if b_out is None else round(b_out, 6),
        "aVolume": round(va, 6),
        "bVolume": round(vb, 6),
    }


def cross_sections(shape: Any, axis: str = "Z", num_slices: int = 10) -> dict:
    """Slice the solid along an axis and report the section area per station.

    Useful for spotting the minimum load-bearing cross-section of a flexure arm
    or a neck, and for sanity-checking that a part is continuous along an axis.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopTools import TopTools_HSequenceOfShape
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise AnalyzeError(f"axis must be X, Y, or Z (got {axis!r})")
    bb = shape.bounding_box()

    if axis == "X":
        lo, hi = bb.min.X, bb.max.X
        pln_dir = gp_Dir(1, 0, 0)
        make_pnt = lambda pos: gp_Pnt(pos, 0, 0)  # noqa: E731
    elif axis == "Y":
        lo, hi = bb.min.Y, bb.max.Y
        pln_dir = gp_Dir(0, 1, 0)
        make_pnt = lambda pos: gp_Pnt(0, pos, 0)  # noqa: E731
    else:
        lo, hi = bb.min.Z, bb.max.Z
        pln_dir = gp_Dir(0, 0, 1)
        make_pnt = lambda pos: gp_Pnt(0, 0, pos)  # noqa: E731

    num_slices = max(int(num_slices), 2)
    span = hi - lo
    lo_s = lo + span * 0.01
    hi_s = hi - span * 0.01
    step = (hi_s - lo_s) / (num_slices - 1)

    slices = []
    for i in range(num_slices):
        pos = lo_s + i * step
        plane = gp_Pln(make_pnt(pos), pln_dir)
        section = BRepAlgoAPI_Section(shape.wrapped, plane, False)
        section.Build()

        edges = TopTools_HSequenceOfShape()
        exp = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
        while exp.More():
            edges.Append(exp.Current())
            exp.Next()

        wires = TopTools_HSequenceOfShape()
        ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edges, 1e-7, False, wires)

        total_area = 0.0
        for j in range(1, wires.Length() + 1):
            wire = TopoDS.Wire_s(wires.Value(j))
            try:
                face_maker = BRepBuilderAPI_MakeFace(plane, wire)
                if face_maker.IsDone():
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties_s(face_maker.Face(), props)
                    total_area += abs(props.Mass())
            except Exception:  # noqa: BLE001 - open wire => skip
                pass

        slices.append({"position": round(pos, 6), "area": round(total_area, 6)})

    areas = [s["area"] for s in slices]
    return {
        "axis": axis,
        "slices": slices,
        "minArea": round(min(areas), 6) if areas else 0.0,
        "maxArea": round(max(areas), 6) if areas else 0.0,
    }
