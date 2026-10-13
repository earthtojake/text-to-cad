"""Exact conversion of a usd-brep body to OpenCascade B-rep: same planes, cylinders, cones,
spheres, tori and NURBS, same topology, never a mesh.

Not needed to model with this package (its native output is USD); it is how the tests prove
a result equals build123d's, and how a part reaches OpenCascade-only tools (STEP, say).
Needs OCP (``pip install build123d``); imported only by whoever calls it.

    from usd_brep_build123d.occt import to_occt, to_build123d

Pipeline: ``usd.export_brep`` writes a BrepArray ``.usda``; ``read_brep_arrays`` parses
its packed arrays (no ``pxr``); ``arrays_to_occt`` rebuilds one TopoDS edge per BrepArray
edge, shared by every face that uses it, loops in BrepArray order, faces oriented by the
solid region's faceuses; ShapeFix completes pcurves and tolerances. Every result is
validated (BRepCheck plus a volume match against usd-brep's own integral); a conversion
that does not validate raises ``BridgeError`` rather than returning a wrong solid.
Conventions the schema does not state, checked on real output: NURBS surface control
points are packed V-fastest; cylinders arrive as zero-angle cones; every circle is a
9-point rational quadratic NURBS; poles are bare vertices and seams are edges used twice
by one face.
"""

from __future__ import annotations

import math
import os
import re
import tempfile

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.ElCLib import ElCLib
from OCP.ElSLib import ElSLib
from OCP.GC import GC_MakeCircle
from OCP.GProp import GProp_GProps
from OCP.Geom import (
    Geom_BSplineCurve, Geom_BSplineSurface, Geom_Circle, Geom_ConicalSurface, Geom_CylindricalSurface,
    Geom_Ellipse, Geom_Line, Geom_Plane, Geom_SphericalSurface, Geom_ToroidalSurface,
)
from OCP.Geom2d import Geom2d_Line
from OCP.Geom2dAPI import Geom2dAPI_Interpolate
from OCP.ShapeFix import ShapeFix_Shape
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal, TColStd_Array2OfReal, TColStd_HArray1OfReal
from OCP.TColgp import TColgp_Array1OfPnt, TColgp_Array2OfPnt, TColgp_HArray1OfPnt2d
from OCP.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED
from OCP.TopoDS import TopoDS_Compound, TopoDS_Edge, TopoDS_Face, TopoDS_Shell, TopoDS_Solid, TopoDS_Wire
from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Vec

from .exporters import quiet_native_stderr

_TWO_PI = 2 * math.pi


class BridgeError(RuntimeError):
    """A usd-brep -> OpenCascade conversion that did not validate."""


# --------------------------------------------------------------------- arrays
_ATTR = re.compile(r"^\s*uniform\s+(\w+)\[\]\s+([\w:]+)\s*=\s*\[(.*?)\]\s*$", re.M | re.S)
_TUPLE = re.compile(r"\(([^)]*)\)")
_TUPLE_TYPES = {"point3d": float, "vector3d": float, "double3": float, "float3": float,
                "double2": float, "float2": float, "int2": int}
_SCALAR_TYPES = {"double": float, "float": float, "uint": int, "int": int}


def read_brep_arrays(usda_text: str) -> dict:
    """Every ``uniform T[] name = [...]`` attribute of the (single) BrepArray prim."""
    out = {}
    for typ, name, body in _ATTR.findall(usda_text):
        if typ == "token":
            out[name] = re.findall(r'"([^"]*)"', body)
        elif typ in _TUPLE_TYPES:
            cast = _TUPLE_TYPES[typ]
            out[name] = [tuple(cast(float(x)) for x in t.split(",")) for t in _TUPLE.findall(body)]
        elif typ in _SCALAR_TYPES:
            cast = _SCALAR_TYPES[typ]
            out[name] = [cast(float(x)) for x in body.split(",") if x.strip()]
    return out


_quiet_native_stderr = quiet_native_stderr


# ------------------------------------------------------------------- geometry
def _pnt(p):
    return gp_Pnt(*p)


def _ax3(origin, axis, ref):
    return gp_Ax3(_pnt(origin), gp_Dir(*axis), gp_Dir(*ref))


def _knots(flat):
    """Flat knot vector -> (distinct knots, multiplicities)."""
    ks, ms = [], []
    for k in flat:
        if ks and abs(k - ks[-1]) <= 1e-12 * max(1.0, abs(k)):
            ms[-1] += 1
        else:
            ks.append(k)
            ms.append(1)
    ka, ma = TColStd_Array1OfReal(1, len(ks)), TColStd_Array1OfInteger(1, len(ks))
    for i, (k, m) in enumerate(zip(ks, ms), 1):
        ka.SetValue(i, k)
        ma.SetValue(i, m)
    return ka, ma


class _Cursor:
    """Index of the next record in each packed per-type array."""

    def __init__(self):
        self.n = {}

    def next(self, key):
        i = self.n.get(key, 0)
        self.n[key] = i + 1
        return i


def _make_curve(kind, a, cur):
    if kind == "BrepCurve3dNurbAPI":
        p, i = "brep:edge3dNurb:curve3d:nurb:", cur.next("nurb")
        n, order = a[p + "vertexCount"][i], a[p + "order"][i]
        v0 = sum(a[p + "vertexCount"][:i])
        k0 = sum(a[p + "vertexCount"][j] + a[p + "order"][j] for j in range(i))
        poles, weights = TColgp_Array1OfPnt(1, n), TColStd_Array1OfReal(1, n)
        w = a.get(p + "weights")
        for j in range(n):
            poles.SetValue(j + 1, _pnt(a[p + "controlVertices"][v0 + j]))
            weights.SetValue(j + 1, w[v0 + j] if w else 1.0)
        ka, ma = _knots(a[p + "knots"][k0:k0 + n + order])
        return Geom_BSplineCurve(poles, weights, ka, ma, order - 1, False)
    if kind == "BrepCurve3dLineAPI":
        p, i = "brep:edge3dLine:curve3d:line:", cur.next("line")
        return Geom_Line(gp_Ax1(_pnt(a[p + "origin"][i]), gp_Dir(*a[p + "direction"][i])))
    if kind == "BrepCurve3dCircleAPI":
        p, i = "brep:edge3dCircle:curve3d:circle:", cur.next("circle")
        ax = gp_Ax2(_pnt(a[p + "center"][i]), gp_Dir(*a[p + "axis"][i]), gp_Dir(*a[p + "refDirection"][i]))
        return Geom_Circle(ax, a[p + "radius"][i])
    if kind == "BrepCurve3dEllipseAPI":
        p, i = "brep:edge3dEllipse:curve3d:ellipse:", cur.next("ellipse")
        ax = gp_Ax2(_pnt(a[p + "center"][i]), gp_Dir(*a[p + "axis"][i]), gp_Dir(*a[p + "refDirection"][i]))
        return Geom_Ellipse(ax, a[p + "xRadius"][i], a[p + "yRadius"][i])
    raise NotImplementedError(f"BrepArray edge curve type {kind}")


def _make_surface(kind, a, cur):
    if kind == "BrepSurfacePlaneAPI":
        p, i = "brep:surface:plane:", cur.next("plane")
        return Geom_Plane(_ax3(a[p + "origin"][i], a[p + "axis"][i], a[p + "refDirection"][i]))
    if kind == "BrepSurfaceCylinderAPI":
        p, i = "brep:surface:cylinder:", cur.next("cylinder")
        return Geom_CylindricalSurface(_ax3(a[p + "origin"][i], a[p + "axis"][i], a[p + "refDirection"][i]),
                                       a[p + "radius"][i])
    if kind == "BrepSurfaceConeAPI":
        p, i = "brep:surface:cone:", cur.next("cone")
        ax3 = _ax3(a[p + "origin"][i], a[p + "axis"][i], a[p + "refDirection"][i])
        semi, r = a[p + "semiAngle"][i], a[p + "radius"][i]
        if abs(semi) < 1e-12:  # cylinders arrive as zero-angle cones
            return Geom_CylindricalSurface(ax3, r)
        return Geom_ConicalSurface(ax3, semi, r)
    if kind == "BrepSurfaceSphereAPI":
        p, i = "brep:surface:sphere:", cur.next("sphere")
        return Geom_SphericalSurface(_ax3(a[p + "center"][i], a[p + "axis"][i], a[p + "refDirection"][i]),
                                     a[p + "radius"][i])
    if kind == "BrepSurfaceTorusAPI":
        p, i = "brep:surface:torus:", cur.next("torus")
        return Geom_ToroidalSurface(_ax3(a[p + "origin"][i], a[p + "axis"][i], a[p + "refDirection"][i]),
                                    a[p + "majorRadius"][i], a[p + "minorRadius"][i])
    if kind == "BrepSurfaceNurbAPI":
        p, i = "brep:surface:nurb:", cur.next("nurb")
        nu, nv = a[p + "uVertexCount"][i], a[p + "vVertexCount"][i]
        ou, ov = a[p + "uOrder"][i], a[p + "vOrder"][i]
        c0 = sum(a[p + "uVertexCount"][j] * a[p + "vVertexCount"][j] for j in range(i))
        ku0 = sum(a[p + "uVertexCount"][j] + a[p + "uOrder"][j] for j in range(i))
        kv0 = sum(a[p + "vVertexCount"][j] + a[p + "vOrder"][j] for j in range(i))
        poles, weights = TColgp_Array2OfPnt(1, nu, 1, nv), TColStd_Array2OfReal(1, nu, 1, nv)
        w = a.get(p + "weights")
        for iu in range(nu):  # V varies fastest (the schema's RenderMan note notwithstanding)
            for jv in range(nv):
                k = c0 + iu * nv + jv
                poles.SetValue(iu + 1, jv + 1, _pnt(a[p + "controlVertices"][k]))
                weights.SetValue(iu + 1, jv + 1, w[k] if w else 1.0)
        uk, um = _knots(a[p + "uKnots"][ku0:ku0 + nu + ou])
        vk, vm = _knots(a[p + "vKnots"][kv0:kv0 + nv + ov])
        return Geom_BSplineSurface(poles, weights, uk, vk, um, vm, ou - 1, ov - 1, False, False)
    raise NotImplementedError(f"BrepArray surface type {kind}")


def _as_line(crv, t0, t1):
    """usd-brep writes every straight edge as a 2-pole degree-1 NURBS -> Geom_Line,
    so the STEP gets LINE rather than B_SPLINE_CURVE_WITH_KNOTS."""
    p0, p1 = crv.Value(t0), crv.Value(t1)
    length = p0.Distance(p1)
    if length < 1e-9:
        return crv, t0, t1
    return Geom_Line(gp_Ax1(p0, gp_Dir(gp_Vec(p0, p1)))), 0.0, length


def _canonical(crv, t0, t1, tol=1e-9):
    """Recognize the analytic curve a usd-brep NURBS edge really is (line or circle)."""
    if isinstance(crv, Geom_BSplineCurve) and crv.Degree() == 1 and crv.NbPoles() == 2:
        return _as_line(crv, t0, t1)
    return _as_circle(crv, t0, t1, tol)


def _as_circle(crv, t0, t1, tol=1e-9):
    """A 9-point rational quadratic NURBS that IS a circle -> Geom_Circle.

    Its angle(t) jumps in second derivative at every double knot, which no smooth
    pcurve can follow; as a true circle the pcurves on analytic faces are exact,
    and the STEP gets CIRCLE rather than B_SPLINE_CURVE_WITH_KNOTS."""
    if not isinstance(crv, Geom_BSplineCurve) or crv.Degree() != 2 or not crv.IsRational():
        return crv, t0, t1
    pts = [crv.Value(t0 + (t1 - t0) * i / 24) for i in range(25)]
    closed = pts[0].Distance(pts[-1]) < 1e-9
    try:
        circ = GC_MakeCircle(*((pts[0], pts[8], pts[16]) if closed else (pts[0], pts[12], pts[-1]))).Value()
    except Exception:  # collinear samples: not a circle
        return crv, t0, t1
    gc = circ.Circ()
    if any(gc.Distance(p) > tol * max(1.0, gc.Radius()) for p in pts):
        return crv, t0, t1
    a0 = ElCLib.Parameter_s(gc, pts[0])
    if closed:
        return circ, a0, a0 + _TWO_PI
    a1 = ElCLib.Parameter_s(gc, pts[-1])
    while a1 <= a0 + 1e-12:
        a1 += _TWO_PI
    return circ, a0, a1


# ------------------------------------------- pcurves on periodic analytic faces
# usd-brep closes a sphere/cylinder/cone face with a seam edge used twice and
# leaves its poles as bare vertices; OpenCascade needs one pcurve per use (u and
# u + 2pi) and a degenerated edge at each pole. ShapeFix cannot infer those once a
# trim crosses the seam, so: invert each edge onto the surface in closed form,
# unwrap it, chain the uses of a loop continuously, and close pole gaps.
def _inverter(surf):
    for cls, get in ((Geom_CylindricalSurface, "Cylinder"), (Geom_ConicalSurface, "Cone"),
                     (Geom_SphericalSurface, "Sphere"), (Geom_ToroidalSurface, "Torus")):
        if isinstance(surf, cls):
            prim = getattr(surf, get)()
            return lambda p: ElSLib.Parameters_s(prim, p)
    return None


def _singular(surf, u, v):
    """The u-derivative vanishes: a sphere pole or a cone apex."""
    p, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surf.D1(u, v, p, du, dv)
    return du.Magnitude() < 1e-9


def _unwrap(vals):
    out = [vals[0]]
    for x in vals[1:]:
        out.append(x + _TWO_PI * round((out[-1] - x) / _TWO_PI))
    return out


def _edge_uv(surf, inv, crv, t0, t1, forward):
    """UV samples along one edgeuse, in its direction, continuous along it."""
    n = 33 if not isinstance(crv, Geom_BSplineCurve) else max(33, 4 * (crv.NbKnots() - 1) + 1)
    ts = [t0 + (t1 - t0) * i / (n - 1) for i in range(n)]
    if not forward:
        ts.reverse()
    uv = [inv(crv.Value(t)) for t in ts]
    us, vs = [p[0] for p in uv], [p[1] for p in uv]
    sing = [_singular(surf, us[i], vs[i]) for i in range(n)]
    for i in range(n):  # u is undefined at a pole: take the neighbour's
        if sing[i]:
            us[i] = us[i + 1 if i == 0 else i - 1]
    return ts, _unwrap(us), vs, sing[-1]


def _fit_pcurve(ts, us, vs):
    """Cubic B-spline through (u, v)(t) at the edge's own t: SameParameter by construction."""
    order = sorted(range(len(ts)), key=lambda i: ts[i])
    pts, prm = TColgp_HArray1OfPnt2d(1, len(ts)), TColStd_HArray1OfReal(1, len(ts))
    for k, i in enumerate(order, 1):
        pts.SetValue(k, gp_Pnt2d(us[i], vs[i]))
        prm.SetValue(k, ts[i])
    interp = Geom2dAPI_Interpolate(pts, prm, False, 1e-12)
    interp.Perform()
    return interp.Curve()


def _periodic_wire(B, face, surf, a, f_range, loop_eus, edges, curves, verts, tol):
    inv = _inverter(surf)
    (umin, _), (umax, _) = f_range
    uses = []
    for k in loop_eus:
        e = a["edgeuse:edgeIndex"][k]
        fwd = a["edgeuse:orientationType"][k] == "same"
        crv, t0, t1 = curves[e]
        ts, us, vs, end_sing = _edge_uv(surf, inv, crv, t0, t1, fwd)
        uses.append({"e": e, "fwd": fwd, "ts": ts, "us": us, "vs": vs, "end_sing": end_sing})

    def shift(use, du):
        use["us"] = [x + du for x in use["us"]]

    def into_face_range(use):
        """Put the use inside the face's u-range. On the seam (u = umin or umax) keep
        the material on the left: rising in v -> umax side, falling -> umin side."""
        mid = 0.5 * (use["us"][0] + use["us"][-1])
        base = _TWO_PI * math.floor((umin - mid) / _TWO_PI + 0.5)
        cands = [base + _TWO_PI * j for j in (-1, 0, 1)]
        inside = [c for c in cands if umin - 1e-7 <= mid + c <= umax + 1e-7]
        if len(inside) > 1:
            shift(use, max(inside) if use["vs"][-1] > use["vs"][0] else min(inside))
        else:
            shift(use, inside[0] if inside else min(cands, key=lambda c: abs(mid + c - 0.5 * (umin + umax))))

    for i, use in enumerate(uses):
        if i == 0 or uses[i - 1]["end_sing"]:
            into_face_range(use)
        else:  # continuous with the previous use's end
            shift(use, _TWO_PI * round((uses[i - 1]["us"][-1] - use["us"][0]) / _TWO_PI))

    wire = TopoDS_Wire()
    B.MakeWire(wire)
    pcurves = []
    for i, use in enumerate(uses):
        B.Add(wire, edges[use["e"]].Oriented(TopAbs_FORWARD if use["fwd"] else TopAbs_REVERSED))
        pcurves.append((use["e"], use["fwd"], _fit_pcurve(use["ts"], use["us"], use["vs"])))
        gap = uses[(i + 1) % len(uses)]["us"][0] - use["us"][-1]
        if use["end_sing"] and abs(gap) > 1e-7:  # pole: close the UV loop
            start, end = a["edge:vertexIndices"][use["e"]]
            pole = verts[end if use["fwd"] else start]
            deg = TopoDS_Edge()
            B.MakeEdge(deg)
            B.Add(deg, pole.Oriented(TopAbs_FORWARD))
            B.Add(deg, pole.Oriented(TopAbs_REVERSED))
            B.UpdateEdge(deg, Geom2d_Line(gp_Pnt2d(use["us"][-1], use["vs"][-1]), gp_Dir2d(math.copysign(1.0, gap), 0.0)),
                         face, tol)
            B.Range(deg, 0.0, abs(gap))
            B.Degenerated(deg, True)
            B.Add(wire, deg)
    return wire, pcurves


# ------------------------------------------------------------------- topology
def arrays_to_occt(a: dict, *, canonical: bool = True, periodic_pcurves: bool = True):
    """Rebuild the one Brep in a BrepArray's packed arrays as a TopoDS shape."""
    if len(a.get("brep:regionCount", [])) != 1:
        raise NotImplementedError("one Brep per BrepArray prim")
    B = BRep_Builder()
    tol = max(a.get("brep:intersectTol3d", [1e-6])[0], 1e-7)

    verts = [BRepBuilderAPI_MakeVertex(_pnt(p)).Vertex() for p in a.get("brep:vertexPoint:point:position", [])]
    for v in verts:
        B.UpdateVertex(v, tol)

    ccur, edges, curves = _Cursor(), [], []
    for i, kind in enumerate(a.get("edge:curveType", [])):
        crv = _make_curve(kind, a, ccur)
        t0, t1 = a["edge:range"][2 * i], a["edge:range"][2 * i + 1]
        if canonical:
            crv, t0, t1 = _canonical(crv, t0, t1)
        curves.append((crv, t0, t1))
        start, end = a["edge:vertexIndices"][i]
        mk = BRepBuilderAPI_MakeEdge(crv, verts[start], verts[end], t0, t1)
        if not mk.IsDone():
            raise BridgeError(f"edge {i}: BRepBuilderAPI_MakeEdge error {mk.Error()}")
        edges.append(mk.Edge())

    scur, faces, loop_i, eu_i = _Cursor(), [], 0, 0
    for f, kind in enumerate(a["face:surfaceType"]):
        surf = _make_surface(kind, a, scur)
        face = TopoDS_Face()
        B.MakeFace(face, surf, tol)
        # tori (periodic in u AND v) are left to ShapeFix, which handles their seams
        periodic = periodic_pcurves and _inverter(surf) is not None and not isinstance(surf, Geom_ToroidalSurface)
        f_range = (a["face:range"][2 * f], a["face:range"][2 * f + 1])
        on_face = {}
        for _ in range(a["face:loopCount"][f]):
            n = a["loop:edgeuseCount"][loop_i]
            loop_i += 1
            if n == 0:  # a vertex loop (bare pole): OpenCascade needs none
                continue
            eus = range(eu_i, eu_i + n)
            eu_i += n
            if periodic:
                wire, pcs = _periodic_wire(B, face, surf, a, f_range, eus, edges, curves, verts, tol)
                for e, fwd, pc in pcs:
                    on_face.setdefault(e, {})[fwd] = pc
            else:
                wire = TopoDS_Wire()
                B.MakeWire(wire)
                for k in eus:
                    same = a["edgeuse:orientationType"][k] == "same"
                    B.Add(wire, edges[a["edgeuse:edgeIndex"][k]].Oriented(TopAbs_FORWARD if same else TopAbs_REVERSED))
            B.Add(face, wire)
        for e, pcs in on_face.items():
            if len(pcs) == 2:  # a seam: the forward use's pcurve first
                B.UpdateEdge(edges[e], pcs[True], pcs[False], face, tol)
            else:
                B.UpdateEdge(edges[e], next(iter(pcs.values())), face, tol)
        faces.append(face)

    # regions -> shells -> faceuses. In a solid region a "same" faceuse means the
    # surface normal points INTO the material, so the OpenCascade face is REVERSED.
    solids, shell_i, faceuse_i = [], 0, 0
    for r, rtype in enumerate(a["region:type"]):
        shells = []
        for _ in range(a["region:shellCount"][r]):
            n = a["shell:faceuseCount"][shell_i]
            fus = range(faceuse_i, faceuse_i + n)
            shell_i += 1
            faceuse_i += n
            if rtype != "solidRegion":
                continue
            shell = TopoDS_Shell()
            B.MakeShell(shell)
            for k in fus:
                same = a["faceuse:orientationType"][k] == "same"
                B.Add(shell, faces[a["faceuse:faceIndex"][k]].Oriented(TopAbs_REVERSED if same else TopAbs_FORWARD))
            shell.Closed(True)
            shells.append(shell)
        if shells:
            solid = TopoDS_Solid()
            B.MakeSolid(solid)
            for sh in shells:
                B.Add(solid, sh)
            solids.append(solid)

    if not solids:  # e.g. a fillet usd-brep "completes" by leaving faces with no material
        raise BridgeError("the Brep has no solid region; the bridge converts solids only")
    if len(solids) == 1:
        shape = solids[0]
    else:
        shape = TopoDS_Compound()
        B.MakeCompound(shape)
        for s in solids:
            B.Add(shape, s)
    fixer = ShapeFix_Shape(shape)  # pcurves, SameParameter, tolerances; topology is already right
    fixer.SetPrecision(tol)
    fixer.SetMaxTolerance(max(1e-3, 10 * tol))
    fixer.Perform()
    return fixer.Shape()


# Tried in order; the first that validates wins.
STRATEGIES = (
    {"canonical": True, "periodic_pcurves": True},    # spheres, cones, seams crossing trims
    {"canonical": False, "periodic_pcurves": False},  # everything to ShapeFix
    {"canonical": True, "periodic_pcurves": False},
)
_VALIDATION = {"fast": (1e-3, 2e-2), "strict": (1e-8, 1e-6)}  # (usd-brep accuracy, relative tolerance)


def _occt_volume(shape, accuracy):
    """OpenCascade's volume to a relative accuracy: its default integration is off by ~1%
    on rational NURBS faces, which are most of what usd-brep writes."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, accuracy)
    return props.Mass()


def brep_to_occt(brep, *, validate="fast", report=None):
    """usd_brep.Brep (or a shape of this package) -> OCP TopoDS_Shape.

    ``validate``: ``"fast"`` (BRepCheck + volume within 2% of usd-brep's default
    integral), ``"strict"`` (volume to 1e-6; seconds on large parts) or ``False``.
    """
    import usd_brep

    brep = getattr(brep, "_brep", brep)
    with tempfile.TemporaryDirectory(prefix="usd-brep-build123d-") as tmp:
        path = os.path.join(tmp, "brep.usda")
        with _quiet_native_stderr():
            usd_brep.usd.export_brep(brep.copy(), path)  # a copy: export caches UV trims on its input
        with open(path, encoding="utf-8") as fh:
            arrays = read_brep_arrays(fh.read())
    if not validate:
        return arrays_to_occt(arrays)
    accuracy, rel_tol = _VALIDATION["strict" if validate == "strict" else "fast"]
    want = brep.volume(relative_accuracy=accuracy) if brep.is_manifold_solid() else None
    if want is not None and want <= 0:
        raise BridgeError(f"usd-brep reports a volume of {want:g} for this solid; it is not a valid body")
    tried = []
    for i, strategy in enumerate(STRATEGIES):
        try:
            shape = arrays_to_occt(arrays, **strategy)
        except Exception as exc:  # a strategy may not apply; the next might
            tried.append(f"strategy {i}: {type(exc).__name__}: {exc}")
            continue
        valid = BRepCheck_Analyzer(shape).IsValid()
        rel = abs(_occt_volume(shape, accuracy) - want) / abs(want) if want else 0.0
        if valid and rel < rel_tol:
            if report is not None:
                report.update(strategy=i, volume_rel_err=rel)
            return shape
        tried.append(f"strategy {i}: valid={valid} volume_rel_err={rel:.2e}")
    raise BridgeError("usd-brep -> OpenCascade conversion did not validate: " + "; ".join(tried))


to_occt = brep_to_occt


def to_build123d(shape, *, label=None, validate="fast"):
    """A shape of this package (or a usd_brep.Brep) as a build123d Solid or Compound."""
    import build123d as bd
    from OCP.TopAbs import TopAbs_SOLID

    occ = brep_to_occt(shape, validate=validate)
    obj = bd.Solid(occ) if occ.ShapeType() == TopAbs_SOLID else bd.Compound(occ)
    name = label if label is not None else getattr(shape, "label", "")
    if name:
        obj.label = name
    return obj
