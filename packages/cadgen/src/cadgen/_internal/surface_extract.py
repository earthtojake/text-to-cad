"""B-rep surface extraction: the `.surf` component artifact (R1,
design/surface-rendering.md).

A `.surf` describes one component's EXACT geometry for client-side GPU
tessellation: per-face parametric surfaces (analytic where possible, NURBS
via GeomConvert otherwise), trim loops as ordered pcurves in (u,v) space,
and per-edge 3D curves with precomputed visibility classes. Face and edge
ordinals follow the same ``TopExp.MapShapes_s`` order the selector system
has always used, so refs (``#o1.2.f5``) keep their meaning.

Container layout (GLB-style, little-endian):

    magic  b"SURF" | version u32 | json_len u32 | json bytes | f32 bin

All float arrays live in one f32 binary chunk; the JSON index references
them as ``[offset_in_floats, count]`` pairs.

Extraction is READING, not computing: no tessellation happens here, which
is the entire point — display cost leaves the build path.
"""

from __future__ import annotations

import json
import math
import struct
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_C0, GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GeomConvert import GeomConvert
from OCP.Geom import Geom_RectangularTrimmedSurface
from OCP.Geom2dConvert import Geom2dConvert
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

SURF_MAGIC = b"SURF"
# 2: shape membership, selector-table metadata (surfaceType/curveType/
#    params/continuity/dihedral/flags), edge faceOrds.
SURF_VERSION = 2


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
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

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


class Unextractable(Exception):
    """This shape cannot be represented as a .surf (caller falls through)."""


def _assert_surface_covers_face(payload, u0, u1, v0, v1, bin_out) -> None:
    """A serialized NURBS payload must COVER the face's UV range: evaluating
    a clamped B-spline outside its knots EXTRAPOLATES, which renders as
    flying geometry (the silent failure mode this guard makes loud).
    Analytic/swept kinds evaluate everywhere by construction."""
    if payload.get("kind") != "nurbs":
        return
    knots_u = bin_out.values
    ku_off, ku_len = payload["knotsU"]
    kv_off, kv_len = payload["knotsV"]
    first_u, last_u = knots_u[ku_off], knots_u[ku_off + ku_len - 1]
    first_v, last_v = knots_u[kv_off], knots_u[kv_off + kv_len - 1]
    eps_u = max(abs(u1 - u0), 1.0) * 1e-6
    eps_v = max(abs(v1 - v0), 1.0) * 1e-6
    if (u0 < first_u - eps_u or u1 > last_u + eps_u
            or v0 < first_v - eps_v or v1 > last_v + eps_v):
        raise Unextractable(
            f"surface domain [{first_u}, {last_u}]x[{first_v}, {last_v}] does "
            f"not cover face UV [{u0}, {u1}]x[{v0}, {v1}] — evaluation would "
            "extrapolate")


def _translate_knots_to_window(
    nurbs, period: float, w0: float, eps: float,
    first_knot: float, nb_knots, knot, set_knot,
) -> None:
    """Shift a clamped copy's knots by whole PERIODS so its span starts at
    the period containing ``w0`` (the face window's low edge).

    Translating every knot by the same constant re-parameterizes without
    moving geometry — and because the ORIGINAL surface is periodic, the
    copy evaluated in the shifted frame gives exactly the points the face's
    pcurves address there. A no-op for aperiodic directions (period 0) and
    for faces already inside the span."""
    if not period:
        return
    shift = math.floor((w0 - first_knot) / period + eps)
    if not shift:
        return
    _shift_knots(shift * period, nb_knots, knot, set_knot)


def _shift_knots(delta: float, nb_knots, knot, set_knot) -> None:
    """Translate every knot by ``delta``, keeping the sequence monotonic at
    every intermediate step: walk from the end for a positive shift, from
    the start for a negative one."""
    count = nb_knots()
    order = range(count, 0, -1) if delta > 0 else range(1, count + 1)
    for index in order:
        set_knot(index, knot(index) + delta)


def _reframe_knots_to_window(nurbs, surface, u0: float, u1: float, v0: float, v1: float) -> None:
    """Move a converted B-spline's knots back into the FACE's UV frame.

    ``Geom_RectangularTrimmedSurface`` on a PERIODIC basis does not trim where
    it is asked: it adjusts the requested window into the basis period
    (``ElCLib::AdjustPeriodic``), so a face whose window straddles the clamped
    seam — a STEP round trip re-anchors pcurves there (moonwatch: face u in
    [-9.36, 14.65] on a 24.78-periodic surface came back trimmed over
    [15.42, 39.42]) — converts to a B-spline whose knots sit a whole number of
    periods from the face's own bounds. Evaluating that at the face's
    parameters would extrapolate, and the coverage guard rightly refuses.
    The surface is periodic, so translating the knots by those periods
    changes nothing but the frame; the nearest whole period is the one."""
    for periodic, period_of, w0, w1, first_knot, nb_knots, knot, set_knot in (
        (surface.IsUPeriodic(), surface.UPeriod, u0, u1,
         nurbs.UKnot(1), nurbs.NbUKnots, nurbs.UKnot, nurbs.SetUKnot),
        (surface.IsVPeriodic(), surface.VPeriod, v0, v1,
         nurbs.VKnot(1), nurbs.NbVKnots, nurbs.VKnot, nurbs.SetVKnot),
    ):
        if not periodic:
            continue
        period = period_of()
        if not period:
            continue
        shift = round((w0 - first_knot) / period)
        if shift:
            _shift_knots(shift * period, nb_knots, knot, set_knot)


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


def _nurbs_surface_payload(surface, bin_out: _Bin) -> dict[str, Any]:
    """Serialize a Geom_BSplineSurface completely (poles, weights, knots
    with multiplicities flattened, degrees, periodicity)."""
    nu, nv = surface.NbUPoles(), surface.NbVPoles()
    poles: list[float] = []
    weights: list[float] = []
    rational = surface.IsURational() or surface.IsVRational()
    for i in range(1, nu + 1):
        for j in range(1, nv + 1):
            pole = surface.Pole(i, j)
            poles.extend((pole.X(), pole.Y(), pole.Z()))
            if rational:
                weights.append(surface.Weight(i, j))

    def flat_knots(count_fn, knot_fn, mult_fn) -> list[float]:
        flat: list[float] = []
        for k in range(1, count_fn() + 1):
            flat.extend([knot_fn(k)] * mult_fn(k))
        return flat

    payload = {
        "kind": "nurbs",
        "degU": surface.UDegree(),
        "degV": surface.VDegree(),
        "nu": nu,
        "nv": nv,
        "periodicU": bool(surface.IsUPeriodic()),
        "periodicV": bool(surface.IsVPeriodic()),
        "poles": bin_out.append(poles),
        "knotsU": bin_out.append(
            flat_knots(surface.NbUKnots, surface.UKnot, surface.UMultiplicity)),
        "knotsV": bin_out.append(
            flat_knots(surface.NbVKnots, surface.VKnot, surface.VMultiplicity)),
    }
    if rational:
        payload["weights"] = bin_out.append(weights)
    return payload


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
    # PARAMETRIZATION IS PART OF THE CONTRACT: pcurves live in the original
    # surface's (u, v), so any serialization must evaluate identically at the
    # same parameters — SurfaceToBSplineSurface does NOT (a rational-quadratic
    # circle cannot carry angle parametrization, so revolved/extruded-arc
    # surfaces come back reparametrized and every trim lands wrong).
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution:
        # Value(u, v) = basis(v) rotated by u around the axis.
        axis = adaptor.AxeOfRevolution()
        basis = _basis_curve_payload(adaptor.BasisCurve(), bin_out)
        return {
            "kind": "revolution",
            "origin": _xyz(axis.Location()),
            "dir": _xyz(axis.Direction()),
            "profile": basis,
        }
    if kind == GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion:
        # Value(u, v) = basis(u) + v * direction.
        basis = _basis_curve_payload(adaptor.BasisCurve(), bin_out)
        return {
            "kind": "extrusion",
            "dir": _xyz(adaptor.Direction()),
            "profile": basis,
        }
    surface = BRep_Tool.Surface_s(face)
    if surface is None:
        raise Unextractable("face with no surface")
    if kind in (GeomAbs_SurfaceType.GeomAbs_BSplineSurface,
                GeomAbs_SurfaceType.GeomAbs_BezierSurface):
        # Native NURBS: serialize DIRECTLY when the underlying surface is
        # already a B-spline (a COPY, clamped if periodic — exact and
        # parametrization-preserving). Vendor STEPs carry B-splines whose
        # trim-then-convert round trip can throw (NCollection range errors);
        # there is nothing to convert in the first place.
        from OCP.Geom import Geom_BSplineSurface, Geom_RectangularTrimmedSurface as _Trim

        native = surface
        if isinstance(native, _Trim):
            native = native.BasisSurface()
        if isinstance(native, Geom_BSplineSurface):
            period_u = native.UPeriod() if native.IsUPeriodic() else 0.0
            period_v = native.VPeriod() if native.IsVPeriodic() else 0.0
            nurbs = native.Copy()
            if nurbs.IsUPeriodic():
                nurbs.SetUNotPeriodic()
            if nurbs.IsVPeriodic():
                nurbs.SetVNotPeriodic()
            # Direct copy is valid only when the face addresses parameters
            # inside the (clamped) domain. A face on a PERIODIC surface may
            # sit a WHOLE number of periods away from the clamped span
            # (booleans re-anchor pcurves; f1 engine cover: face u exactly
            # one period past the basis knots). The surface is identical
            # there, so translate the copy's knots by those periods —
            # surface, face uv, and pcurves stay in ONE parameter frame,
            # which is the contract (:func:`_assert_surface_covers_face`).
            # A window that still does not fit ONE clamped span (u range
            # past one turn) goes through the trimmed conversion below
            # instead — segmenting a B-spline preserves parametrization, so
            # nothing is lost, while a clamped copy would EXTRAPOLATE
            # outside its knots (moonwatch bezel: face u in [28.5, 66.1]
            # over a ~41-period surface).
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
            eps_u = max(abs(u1 - u0), 1.0) * 1e-6
            eps_v = max(abs(v1 - v0), 1.0) * 1e-6
            _translate_knots_to_window(
                nurbs, period_u, u0, eps_u,
                nurbs.UKnot(1), nurbs.NbUKnots, nurbs.UKnot, nurbs.SetUKnot)
            _translate_knots_to_window(
                nurbs, period_v, v0, eps_v,
                nurbs.VKnot(1), nurbs.NbVKnots, nurbs.VKnot, nurbs.SetVKnot)
            if (
                u0 >= nurbs.UKnot(1) - eps_u
                and u1 <= nurbs.UKnot(nurbs.NbUKnots()) + eps_u
                and v0 >= nurbs.VKnot(1) - eps_v
                and v1 <= nurbs.VKnot(nurbs.NbVKnots()) + eps_v
            ):
                return _nurbs_surface_payload(nurbs, bin_out)
        try:
            u0, u1, v0, v1 = _clamped_uv_bounds(face, surface)
            bounded = Geom_RectangularTrimmedSurface(surface, u0, u1, v0, v1)
            nurbs = GeomConvert.SurfaceToBSplineSurface_s(bounded)
            if nurbs.IsUPeriodic():
                nurbs.SetUNotPeriodic()
            if nurbs.IsVPeriodic():
                nurbs.SetVNotPeriodic()
            _reframe_knots_to_window(nurbs, surface, u0, u1, v0, v1)
        except Exception as exc:
            raise Unextractable(f"NURBS conversion failed: {exc}") from exc
        return _nurbs_surface_payload(nurbs, bin_out)
    # Exotic kinds (offset surfaces, ...): parametrization-preserving
    # least-squares approximation.
    try:
        from OCP.GeomAbs import GeomAbs_C1
        from OCP.GeomConvert import GeomConvert_ApproxSurface

        u0, u1, v0, v1 = _clamped_uv_bounds(face, surface)
        bounded = Geom_RectangularTrimmedSurface(surface, u0, u1, v0, v1)
        approx = GeomConvert_ApproxSurface(
            bounded, 1e-4, GeomAbs_C1, GeomAbs_C1, 14, 14, 100, 0)
        if not approx.IsDone():
            raise Unextractable("surface approximation did not converge")
        nurbs = approx.Surface()
        if nurbs.IsUPeriodic():
            nurbs.SetUNotPeriodic()
        if nurbs.IsVPeriodic():
            nurbs.SetVNotPeriodic()
        _reframe_knots_to_window(nurbs, surface, u0, u1, v0, v1)
    except Unextractable:
        raise
    except Exception as exc:
        raise Unextractable(f"surface approximation failed: {exc}") from exc
    return _nurbs_surface_payload(nurbs, bin_out)


def _basis_curve_payload(basis_adaptor, bin_out: _Bin) -> dict[str, Any]:
    """Serialize a swept surface's basis curve in the edge-curve schema
    (line/circle/ellipse/bspline), preserving its parametrization: analytic
    kinds carry it inherently; general curves convert through
    CurveToBSplineCurve which keeps parameters for non-periodic input and is
    clamped (parametrization-preserving) otherwise."""
    kind = basis_adaptor.GetType()
    first = basis_adaptor.FirstParameter()
    last = basis_adaptor.LastParameter()
    if kind == GeomAbs_CurveType.GeomAbs_Line:
        line = basis_adaptor.Line()
        return {"kind": "line", "origin": _xyz(line.Location()),
                "dir": _xyz(line.Direction()), "range": [first, last]}
    if kind == GeomAbs_CurveType.GeomAbs_Circle:
        circle = basis_adaptor.Circle()
        return {"kind": "circle", "radius": circle.Radius(),
                **_frame(circle.Position()), "range": [first, last]}
    if kind == GeomAbs_CurveType.GeomAbs_Ellipse:
        ellipse = basis_adaptor.Ellipse()
        return {"kind": "ellipse", "majorRadius": ellipse.MajorRadius(),
                "minorRadius": ellipse.MinorRadius(),
                **_frame(ellipse.Position()), "range": [first, last]}
    if kind == GeomAbs_CurveType.GeomAbs_BSplineCurve:
        bspline = basis_adaptor.BSpline()
        period = None
        if bspline.IsPeriodic():
            # A swept face's parameter range may CROSS the closed profile's
            # period (bracelet-link outlines do); the client wraps into the
            # clamped domain using this period. Clamp a COPY — the adaptor
            # hands back the model's own curve handle, and SetNotPeriodic on
            # it would silently rewrite the shape being extracted.
            period = bspline.Period()
            bspline = bspline.Copy()
            bspline.SetNotPeriodic()
        return _bspline_curve3_payload(bspline, bin_out, period=period)
    if kind == GeomAbs_CurveType.GeomAbs_BezierCurve:
        # Exact and parametrization-preserving.
        try:
            bspline = GeomConvert.CurveToBSplineCurve_s(basis_adaptor.Bezier())
        except Exception as exc:
            raise Unextractable(f"basis bezier conversion failed: {exc}") from exc
        return _bspline_curve3_payload(bspline, bin_out)
    # Anything else (offset curves, ...): parametrization-preserving
    # approximation of the adaptor's underlying curve.
    try:
        from OCP.GeomAbs import GeomAbs_C1
        from OCP.Geom import Geom_TrimmedCurve
        from OCP.GeomConvert import GeomConvert_ApproxCurve

        curve = basis_adaptor.Curve()
        approx = GeomConvert_ApproxCurve(
            Geom_TrimmedCurve(curve, first, last), 1e-5, GeomAbs_C1, 32, 14)
        if not approx.IsDone():
            raise Unextractable("basis curve approximation did not converge")
        bspline = approx.Curve()
        if bspline.IsPeriodic():
            bspline.SetNotPeriodic()
    except Unextractable:
        raise
    except Exception as exc:
        raise Unextractable(f"basis curve conversion failed: {exc}") from exc
    return _bspline_curve3_payload(bspline, bin_out)


def _bspline_curve3_payload(bspline, bin_out: _Bin, *, period=None) -> dict[str, Any]:
    poles: list[float] = []
    weights: list[float] = []
    rational = bspline.IsRational()
    for i in range(1, bspline.NbPoles() + 1):
        pole = bspline.Pole(i)
        poles.extend((pole.X(), pole.Y(), pole.Z()))
        if rational:
            weights.append(bspline.Weight(i))
    flat: list[float] = []
    for k in range(1, bspline.NbKnots() + 1):
        flat.extend([bspline.Knot(k)] * bspline.Multiplicity(k))
    payload = {
        "kind": "bspline",
        "deg": bspline.Degree(),
        "n": bspline.NbPoles(),
        "periodic": bool(bspline.IsPeriodic()),
        "poles": bin_out.append(poles),
        "knots": bin_out.append(flat),
        "range": [bspline.FirstParameter(), bspline.LastParameter()],
    }
    if period is not None:
        # Clamped from a CLOSED profile: sweep faces may address parameters
        # past the period; the client wraps into the clamped domain.
        payload["period"] = float(period)
    if rational:
        payload["weights"] = bin_out.append(weights)
    return payload


def _curve2d_payload(edge, face, bin_out: _Bin) -> dict[str, Any]:
    curve = BRep_Tool.CurveOnSurface_s(edge, face, 0.0, 0.0)
    if curve is None:
        raise Unextractable("edge with no pcurve on its face")
    first, last = BRep_Tool.Range_s(edge, face)
    # Convert every pcurve to a 2D BSpline: one evaluator client-side, and
    # Geom2dConvert handles lines/arcs exactly (degree 1 / rational degree 2).
    # Trim first — unbounded curves (lines) refuse direct conversion.
    try:
        from OCP.Geom2d import Geom2d_TrimmedCurve

        bspline = Geom2dConvert.CurveToBSplineCurve_s(
            Geom2d_TrimmedCurve(curve, first, last))
        if bspline.IsPeriodic():
            bspline.SetNotPeriodic()
    except Exception as exc:
        raise Unextractable(f"pcurve conversion failed: {exc}") from exc
    poles: list[float] = []
    weights: list[float] = []
    rational = bspline.IsRational()
    for i in range(1, bspline.NbPoles() + 1):
        pole = bspline.Pole(i)
        poles.extend((pole.X(), pole.Y()))
        if rational:
            weights.append(bspline.Weight(i))
    flat: list[float] = []
    for k in range(1, bspline.NbKnots() + 1):
        flat.extend([bspline.Knot(k)] * bspline.Multiplicity(k))
    payload = {
        "deg": bspline.Degree(),
        "n": bspline.NbPoles(),
        "periodic": bool(bspline.IsPeriodic()),
        "poles": bin_out.append(poles),
        "knots": bin_out.append(flat),
        # The CONVERTED curve's own domain, not the edge range: trimming a
        # periodic pcurve near/past the period normalizes the parameter into
        # the principal interval, and evaluating the stored knots at the
        # original edge parameters extrapolates wildly off the trim.
        "range": [bspline.FirstParameter(), bspline.LastParameter()],
    }
    if rational:
        payload["weights"] = bin_out.append(weights)
    span = flat[-1] - flat[0] or 1.0
    if (payload["range"][0] < flat[0] - 1e-6 * span
            or payload["range"][1] > flat[-1] + 1e-6 * span):
        raise Unextractable(
            f"pcurve range {payload['range']} escapes knot domain "
            f"[{flat[0]}, {flat[-1]}] — evaluation would extrapolate")
    return payload


def _curve3d_payload(edge, bin_out: _Bin) -> dict[str, Any] | None:
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
    # General curve: sample-free exact NURBS conversion.
    curve = BRep_Tool.Curve_s(edge, 0.0, 0.0)
    if curve is None:
        return None
    try:
        from OCP.Geom import Geom_TrimmedCurve

        bspline = GeomConvert.CurveToBSplineCurve_s(
            Geom_TrimmedCurve(curve, first, last))
        if bspline.IsPeriodic():
            bspline.SetNotPeriodic()
    except Exception:
        return None
    poles: list[float] = []
    weights: list[float] = []
    rational = bspline.IsRational()
    for i in range(1, bspline.NbPoles() + 1):
        pole = bspline.Pole(i)
        poles.extend((pole.X(), pole.Y(), pole.Z()))
        if rational:
            weights.append(bspline.Weight(i))
    flat: list[float] = []
    for k in range(1, bspline.NbKnots() + 1):
        flat.extend([bspline.Knot(k)] * bspline.Multiplicity(k))
    payload = {
        "kind": "bspline",
        "deg": bspline.Degree(),
        "n": bspline.NbPoles(),
        "periodic": bool(bspline.IsPeriodic()),
        "poles": bin_out.append(poles),
        "knots": bin_out.append(flat),
        "range": [bspline.FirstParameter(), bspline.LastParameter()],
    }
    if rational:
        payload["weights"] = bin_out.append(weights)
    return payload


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
    in different colours share one file, and the descriptor's occurrence is
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

    solid_explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while solid_explorer.More():
        _record_shape(solid_explorer.Current(), "solid")
        solid_explorer.Next()
    if not shapes_meta:
        shell_explorer = TopExp_Explorer(shape, TopAbs_SHELL)
        while shell_explorer.More():
            _record_shape(shell_explorer.Current(), "shell")
            shell_explorer.Next()
    if not shapes_meta:
        shapes_meta.append({"ord": 1, "kind": "shape", "volume": None})

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
        _assert_surface_covers_face(entry["surface"], u0, u1, v0, v1, bin_out)
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
                pcurve = _curve2d_payload(edge, face, bin_out)
                pcurve["edgeOrd"] = edge_ord_by_hash.get(_shape_hash(edge), 0)
                pcurve["reversed"] = (
                    edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED)
                loop.append(pcurve)
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
            "curve": _curve3d_payload(edge, bin_out),
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


def read_surf(data: bytes) -> tuple[dict, memoryview]:
    if data[:4] != SURF_MAGIC:
        raise ValueError("not a SURF container")
    version, json_len = struct.unpack_from("<II", data, 4)
    index = json.loads(data[12:12 + json_len].decode("utf-8"))
    return index, memoryview(data)[12 + json_len:]


def _shape_hash(shape) -> int:
    # Same identity the scene loader uses for ordinal joins.
    from cadgen._internal.step_scene_loader import _shape_hash as impl

    return impl(shape)
