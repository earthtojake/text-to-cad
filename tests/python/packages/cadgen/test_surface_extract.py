"""`.surf` extraction fidelity (design/surface-rendering.md R1).

The renderer trusts these buffers completely, so the oracle here is OCCT
itself: rebuild every serialized NURBS from its arrays and compare sampled
points against the source geometry; evaluate analytic frames directly; walk
pcurves and check they stay inside the face's UV bounds.
"""

from __future__ import annotations

import math
import struct
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


def _floats(binbuf, ref):
    offset, count = ref
    return struct.unpack_from(f"<{count}f", binbuf, offset * 4)


def _rebuild_bspline_surface(payload, binbuf):
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TColStd import (
        TColStd_Array1OfInteger,
        TColStd_Array1OfReal,
        TColStd_Array2OfReal,
    )
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.gp import gp_Pnt

    nu, nv = payload["nu"], payload["nv"]
    raw = _floats(binbuf, payload["poles"])
    poles = TColgp_Array2OfPnt(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            base = (i * nv + j) * 3
            poles.SetValue(i + 1, j + 1, gp_Pnt(*raw[base:base + 3]))

    def knots_and_mults(flat):
        knots, mults = [], []
        for value in flat:
            if knots and math.isclose(value, knots[-1], rel_tol=0, abs_tol=1e-9):
                mults[-1] += 1
            else:
                knots.append(value)
                mults.append(1)
        k_arr = TColStd_Array1OfReal(1, len(knots))
        m_arr = TColStd_Array1OfInteger(1, len(knots))
        for idx, (k, m) in enumerate(zip(knots, mults), start=1):
            k_arr.SetValue(idx, k)
            m_arr.SetValue(idx, m)
        return k_arr, m_arr

    uk, um = knots_and_mults(_floats(binbuf, payload["knotsU"]))
    vk, vm = knots_and_mults(_floats(binbuf, payload["knotsV"]))
    if "weights" in payload:
        wraw = _floats(binbuf, payload["weights"])
        weights = TColStd_Array2OfReal(1, nu, 1, nv)
        for i in range(nu):
            for j in range(nv):
                weights.SetValue(i + 1, j + 1, wraw[i * nv + j])
        return Geom_BSplineSurface(
            poles, weights, uk, vk, um, vm, payload["degU"], payload["degV"],
            payload["periodicU"], payload["periodicV"])
    return Geom_BSplineSurface(
        poles, uk, vk, um, vm, payload["degU"], payload["degV"],
        payload["periodicU"], payload["periodicV"])


def _rebuild_bspline_curve3(payload, binbuf):
    from OCP.Geom import Geom_BSplineCurve
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.gp import gp_Pnt

    n = payload["n"]
    raw = _floats(binbuf, payload["poles"])
    poles = TColgp_Array1OfPnt(1, n)
    for i in range(n):
        poles.SetValue(i + 1, gp_Pnt(*raw[i * 3:i * 3 + 3]))
    flat = _floats(binbuf, payload["knots"])
    knots, mults = [], []
    for value in flat:
        if knots and math.isclose(value, knots[-1], rel_tol=0, abs_tol=1e-9):
            mults[-1] += 1
        else:
            knots.append(value)
            mults.append(1)
    k_arr = TColStd_Array1OfReal(1, len(knots))
    m_arr = TColStd_Array1OfInteger(1, len(knots))
    for idx, (k, m) in enumerate(zip(knots, mults), start=1):
        k_arr.SetValue(idx, k)
        m_arr.SetValue(idx, m)
    if "weights" in payload:
        wraw = _floats(binbuf, payload["weights"])
        weights = TColStd_Array1OfReal(1, n)
        for i in range(n):
            weights.SetValue(i + 1, wraw[i])
        return Geom_BSplineCurve(poles, weights, k_arr, m_arr,
                                 payload["deg"], payload["periodic"])
    return Geom_BSplineCurve(poles, k_arr, m_arr, payload["deg"],
                             payload["periodic"])


def _rebuild_bspline_curve2d(payload, binbuf):
    from OCP.Geom2d import Geom2d_BSplineCurve
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.TColgp import TColgp_Array1OfPnt2d
    from OCP.gp import gp_Pnt2d

    n = payload["n"]
    raw = _floats(binbuf, payload["poles"])
    poles = TColgp_Array1OfPnt2d(1, n)
    for i in range(n):
        poles.SetValue(i + 1, gp_Pnt2d(raw[i * 2], raw[i * 2 + 1]))
    flat = _floats(binbuf, payload["knots"])
    knots, mults = [], []
    for value in flat:
        if knots and math.isclose(value, knots[-1], rel_tol=0, abs_tol=1e-9):
            mults[-1] += 1
        else:
            knots.append(value)
            mults.append(1)
    k_arr = TColStd_Array1OfReal(1, len(knots))
    m_arr = TColStd_Array1OfInteger(1, len(knots))
    for idx, (k, m) in enumerate(zip(knots, mults), start=1):
        k_arr.SetValue(idx, k)
        m_arr.SetValue(idx, m)
    if "weights" in payload:
        wraw = _floats(binbuf, payload["weights"])
        weights = TColStd_Array1OfReal(1, n)
        for i in range(n):
            weights.SetValue(i + 1, wraw[i])
        return Geom2d_BSplineCurve(poles, weights, k_arr, m_arr,
                                   payload["deg"], payload["periodic"])
    return Geom2d_BSplineCurve(poles, k_arr, m_arr, payload["deg"],
                               payload["periodic"])


def _analytic_point(surface, u, v):
    ox, oy, oz = surface["origin"]
    xd, yd, zd = surface["xdir"], surface["ydir"], surface["zdir"]

    def mix(px, py, pz):
        return tuple(ox_ + px * x + py * y + pz * z for ox_, x, y, z in
                     zip((ox, oy, oz), xd, yd, zd))

    kind = surface["kind"]
    if kind == "plane":
        return mix(u, v, 0.0)
    if kind == "cylinder":
        r = surface["radius"]
        return mix(r * math.cos(u), r * math.sin(u), v)
    if kind == "cone":
        r = surface["radius"] + v * math.sin(surface["semiAngle"])
        return mix(r * math.cos(u), r * math.sin(u),
                   v * math.cos(surface["semiAngle"]))
    if kind == "sphere":
        r = surface["radius"]
        return mix(r * math.cos(v) * math.cos(u), r * math.cos(v) * math.sin(u),
                   r * math.sin(v))
    if kind == "torus":
        big, small = surface["majorRadius"], surface["minorRadius"]
        ring = big + small * math.cos(v)
        return mix(ring * math.cos(u), ring * math.sin(u), small * math.sin(v))
    raise AssertionError(f"unexpected analytic kind {kind}")


def _build_fixture():
    """Planes + cylinder + torus + true NURBS faces (rect-to-circle loft)."""
    import build123d as bd
    from build123d.topology import Solid

    box = Solid.make_box(20, 14, 8)
    filleted = box.fillet(2.0, box.edges().group_by(bd.Axis.Z)[-1])
    cyl = Solid.make_cylinder(3, 20)
    fused = filleted.fuse(cyl)
    torus = Solid.make_torus(9, 1.5).moved(bd.Location((0, 0, 25)))
    with bd.BuildPart() as lofted:
        with bd.BuildSketch(bd.Plane.XY.offset(40)):
            bd.Rectangle(12, 8)
        with bd.BuildSketch(bd.Plane.XY.offset(52)):
            bd.Circle(3)
        bd.loft(ruled=False)
    # Full revolve of a spline profile: periodic NURBS surface + periodic
    # pcurves, which the extractor must CLAMP (SetNotPeriodic) because the
    # client evaluator is clamped-only. Un-clamped periodic payloads render
    # as flying geometry (moonwatch regression).
    with bd.BuildPart() as revolved:
        with bd.BuildSketch(bd.Plane.XZ):
            with bd.BuildLine() as profile:
                bd.Spline((8, -2), (10.5, 0), (8, 2))
                bd.Line((8, 2), (8, -2))
            bd.make_face()
        bd.revolve(axis=bd.Axis.Z)
    revolved_part = revolved.part.moved(bd.Location((0, 0, 60)))
    return bd.Compound(children=[fused, torus, lofted.part, revolved_part])


class SurfaceExtractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen._internal.surface_extract import (
            extract_surface_component,
            read_surf,
        )

        cls.shape = _build_fixture().wrapped
        cls.data = extract_surface_component(cls.shape)
        cls.index, cls.binbuf = read_surf(bytes(cls.data))

        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        cls.face_map = TopTools_IndexedMapOfShape()
        cls.edge_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(cls.shape, TopAbs_FACE, cls.face_map)
        TopExp.MapShapes_s(cls.shape, TopAbs_EDGE, cls.edge_map)

    def test_counts_match_topology_ordinals(self) -> None:
        self.assertEqual(self.index["counts"]["faces"], self.face_map.Extent())
        self.assertEqual(self.index["counts"]["edges"], self.edge_map.Extent())
        self.assertEqual([f["ord"] for f in self.index["faces"]],
                         list(range(1, self.face_map.Extent() + 1)))

    def test_fixture_exercises_analytics_and_nurbs(self) -> None:
        kinds = {f["surface"]["kind"] for f in self.index["faces"]}
        self.assertLessEqual({"plane", "cylinder", "torus", "nurbs"}, kinds)

    def test_swept_surfaces_match_occt(self) -> None:
        """Revolution/extrusion serialize as axis + profile so the ORIGINAL
        parametrization survives (a NURBS conversion reparametrizes and every
        trim lands wrong). Evaluate the payload independently vs OCCT."""
        import numpy as np
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        def profile_point(profile, t):
            kind = profile["kind"]
            period = profile.get("period")
            if period and not (profile["range"][0] <= t <= profile["range"][1]):
                t = profile["range"][0] + (t - profile["range"][0]) % period
            if kind == "bspline":
                curve = _rebuild_bspline_curve3(profile, self.binbuf)
                p = curve.Value(t)
                return np.array([p.X(), p.Y(), p.Z()])
            if kind == "line":
                o, d = np.array(profile["origin"]), np.array(profile["dir"])
                return o + t * d
            frame = {k: np.array(profile[k]) for k in ("origin", "xdir", "ydir")}
            if kind == "circle":
                r = profile["radius"]
                return (frame["origin"] + r * math.cos(t) * frame["xdir"]
                        + r * math.sin(t) * frame["ydir"])
            raise AssertionError(kind)

        checked = 0
        for entry in self.index["faces"]:
            payload = entry["surface"]
            if payload["kind"] not in ("revolution", "extrusion"):
                continue
            face = TopoDS.Face_s(self.face_map.FindKey(entry["ord"]))
            geom = BRep_Tool.Surface_s(face)
            u0, u1, v0, v1 = entry["uv"]
            for s, t in ((0.1, 0.2), (0.5, 0.5), (0.9, 0.8)):
                u = u0 + s * (u1 - u0)
                v = v0 + t * (v1 - v0)
                truth = geom.Value(u, v)
                if payload["kind"] == "revolution":
                    p = profile_point(payload["profile"], v)
                    o = np.array(payload["origin"])
                    d = np.array(payload["dir"])
                    rel = p - o
                    mine = (o + rel * math.cos(u)
                            + np.cross(d, rel) * math.sin(u)
                            + d * np.dot(d, rel) * (1 - math.cos(u)))
                else:
                    p = profile_point(payload["profile"], u)
                    mine = p + v * np.array(payload["dir"])
                distance = math.dist((truth.X(), truth.Y(), truth.Z()), tuple(mine))
                self.assertLess(distance, 1e-3, msg=f"face {entry['ord']}")
                checked += 1
        self.assertGreater(checked, 0, "fixture has no swept faces")

    def test_analytic_surfaces_match_occt(self) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        for entry in self.index["faces"]:
            if entry["surface"]["kind"] in ("nurbs", "revolution", "extrusion"):
                continue
            face = TopoDS.Face_s(self.face_map.FindKey(entry["ord"]))
            geom = BRep_Tool.Surface_s(face)
            u0, u1, v0, v1 = entry["uv"]
            for s, t in ((0.1, 0.2), (0.5, 0.5), (0.9, 0.7)):
                u = u0 + s * (u1 - u0)
                v = v0 + t * (v1 - v0)
                truth = geom.Value(u, v)
                mine = _analytic_point(entry["surface"], u, v)
                for a, b in zip((truth.X(), truth.Y(), truth.Z()), mine):
                    self.assertAlmostEqual(a, b, places=5,
                                           msg=f"face {entry['ord']} "
                                               f"{entry['surface']['kind']}")

    def test_nurbs_surfaces_rebuild_bit_faithfully(self) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        checked = 0
        for entry in self.index["faces"]:
            payload = entry["surface"]
            if payload["kind"] != "nurbs":
                continue
            face = TopoDS.Face_s(self.face_map.FindKey(entry["ord"]))
            geom = BRep_Tool.Surface_s(face)
            rebuilt = _rebuild_bspline_surface(payload, self.binbuf)
            u0, u1, v0, v1 = entry["uv"]
            for s, t in ((0.15, 0.3), (0.5, 0.5), (0.85, 0.65)):
                u = u0 + s * (u1 - u0)
                v = v0 + t * (v1 - v0)
                truth = geom.Value(u, v)
                mine = rebuilt.Value(u, v)
                # f32 quantization over model-scale coordinates.
                self.assertLess(truth.Distance(mine), 1e-3,
                                msg=f"face {entry['ord']}")
            checked += 1
        self.assertGreater(checked, 0)

    def test_pcurves_evaluate_inside_uv_bounds(self) -> None:
        """Rebuild each serialized 2D BSpline in OCCT and sample it: points
        must stay inside the face's UV box (poles may legitimately exceed
        it — rational arc middle poles do)."""
        for entry in self.index["faces"]:
            u0, u1, v0, v1 = entry["uv"]
            slack_u = max(1e-4, (u1 - u0) * 1e-2)
            slack_v = max(1e-4, (v1 - v0) * 1e-2)
            self.assertGreaterEqual(len(entry["loops"]), 1,
                                    msg=f"face {entry['ord']} untrimmable")
            for loop in entry["loops"]:
                for pcurve in loop:
                    curve = _rebuild_bspline_curve2d(pcurve, self.binbuf)
                    t0, t1 = pcurve["range"]
                    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
                        point = curve.Value(t0 + s * (t1 - t0))
                        self.assertGreaterEqual(point.X(), u0 - slack_u,
                                                msg=f"face {entry['ord']}")
                        self.assertLessEqual(point.X(), u1 + slack_u,
                                             msg=f"face {entry['ord']}")
                        self.assertGreaterEqual(point.Y(), v0 - slack_v,
                                                msg=f"face {entry['ord']}")
                        self.assertLessEqual(point.Y(), v1 + slack_v,
                                             msg=f"face {entry['ord']}")

    def test_edge_classes_and_curves(self) -> None:
        classes = {e["class"] for e in self.index["edges"]}
        self.assertIn("feature", classes)
        self.assertIn("seam", classes)  # cylinder + torus both have seams
        self.assertIn("tangent", classes)  # fillet blends meet faces G1
        for entry in self.index["edges"]:
            if entry["curve"] is None:
                continue
            self.assertIn(entry["curve"]["kind"],
                          {"line", "circle", "ellipse", "bspline"})

    def test_container_roundtrip(self) -> None:
        from cadgen._internal.surface_extract import read_surf

        index, _ = read_surf(bytes(self.data))
        self.assertEqual(index["version"], 2)
        with self.assertRaises(ValueError):
            read_surf(b"GLBX" + bytes(self.data[4:]))


class ClampedUvBoundsTest(unittest.TestCase):
    """UVBounds_s can return a bound a floating-point hair OUTSIDE the
    surface's own domain (vendor STEPs: -0.0 vs 0.0, a few 1e-6 past a
    trimmed span), and Geom_RectangularTrimmedSurface rejects that outright.
    _clamped_uv_bounds must pull each non-periodic bound into the domain so
    the trim construction — and the coverage guard downstream — accept faces
    the surface fully covers (Waveshare ESP32 driver board regression)."""

    def _bspline_patch(self):
        # A non-periodic B-spline with the exact domain [0,1]x[0,0.015] from
        # the reported failure (solid #194 face #101 had V 0.0150 vs 0.0180,
        # solid #215 face #112 had U -0.0 vs 0.0).
        from OCP.Geom import Geom_Plane, Geom_RectangularTrimmedSurface
        from OCP.GeomConvert import GeomConvert
        from OCP.gp import gp_Pln

        trimmed = Geom_RectangularTrimmedSurface(
            Geom_Plane(gp_Pln()), 0.0, 1.0, 0.0, 0.015)
        return GeomConvert.SurfaceToBSplineSurface_s(trimmed)

    def test_hairline_overshoot_is_clamped_and_trims(self) -> None:
        from unittest import mock

        from OCP.Geom import Geom_RectangularTrimmedSurface

        from cadgen._internal import surface_extract

        surface = self._bspline_patch()
        raw = (-1e-17, 1.0, 0.0, 0.015 + 5e-6)

        # The raw bounds are exactly what OCCT rejects.
        with self.assertRaises(Exception):
            Geom_RectangularTrimmedSurface(surface, *raw)

        fake_tools = mock.Mock()
        fake_tools.UVBounds_s.return_value = raw
        with mock.patch.object(surface_extract, "BRepTools", fake_tools):
            clamped = surface_extract._clamped_uv_bounds(object(), surface)

        self.assertEqual((0.0, 1.0, 0.0, 0.015), clamped)
        # And the clamped window constructs cleanly.
        Geom_RectangularTrimmedSurface(surface, *clamped)

    def test_interior_bounds_pass_through_unchanged(self) -> None:
        from unittest import mock

        from cadgen._internal import surface_extract

        surface = self._bspline_patch()
        raw = (0.25, 0.75, 0.001, 0.014)
        fake_tools = mock.Mock()
        fake_tools.UVBounds_s.return_value = raw
        with mock.patch.object(surface_extract, "BRepTools", fake_tools):
            clamped = surface_extract._clamped_uv_bounds(object(), surface)
        self.assertEqual(raw, clamped)

    def test_periodic_direction_is_left_alone(self) -> None:
        # A periodic direction wraps: a window past Bounds() is legitimate
        # there (booleans re-anchor pcurves whole periods away) and must not
        # be clamped into one span.
        from unittest import mock

        from OCP.Geom import Geom_CylindricalSurface
        from OCP.gp import gp_Ax3

        from cadgen._internal import surface_extract

        surface = Geom_CylindricalSurface(gp_Ax3(), 5.0)
        self.assertTrue(surface.IsUPeriodic())
        raw = (6.0, 7.0, -3.0, 3.0)  # u window a whole period out
        fake_tools = mock.Mock()
        fake_tools.UVBounds_s.return_value = raw
        with mock.patch.object(surface_extract, "BRepTools", fake_tools):
            clamped = surface_extract._clamped_uv_bounds(object(), surface)
        self.assertEqual(raw, clamped)


class PeriodicSeamWindowTest(unittest.TestCase):
    """A face whose UV window straddles a periodic surface's seam, anchored a
    period BELOW the basis knots — what a STEP round trip does to pcurves
    (moonwatch.step: face u in [-9.36, 14.65] on a 24.78-periodic B-spline).

    The clamped copy cannot cover such a window after whole-period
    translation, so the extractor trims and converts — but
    Geom_RectangularTrimmedSurface on a periodic basis ADJUSTS the window into
    the basis period, handing back knots over [15.42, 39.42] for a face that
    addresses [-9.36, 14.65]. Before the reframe the coverage guard refused the
    face and the whole component's compile died with it."""

    def _periodic_nurbs(self):
        from OCP.Geom import Geom_CylindricalSurface, Geom_RectangularTrimmedSurface
        from OCP.GeomConvert import GeomConvert
        from OCP.gp import gp_Ax3

        cylinder = Geom_CylindricalSurface(gp_Ax3(), 5.0)
        nurbs = GeomConvert.SurfaceToBSplineSurface_s(
            Geom_RectangularTrimmedSurface(cylinder, 0.0, 2 * math.pi, 0.0, 10.0))
        self.assertTrue(nurbs.IsUPeriodic())
        return nurbs

    def test_seam_straddling_window_is_covered_in_the_face_frame(self) -> None:
        from unittest import mock

        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

        from cadgen._internal import surface_extract

        nurbs = self._periodic_nurbs()
        face = BRepBuilderAPI_MakeFace(nurbs, 0.5, 1.5, 1.0, 9.0, 1e-6).Face()
        # Six radians wide (under one turn), straddling u = 0 from below: the
        # window the clamped copy cannot hold whichever period it is moved to.
        window = (-3.0, 3.0, 1.0, 9.0)
        fake_tools = mock.Mock()
        fake_tools.UVBounds_s.return_value = window
        bin_out = surface_extract._Bin()
        with mock.patch.object(surface_extract, "BRepTools", fake_tools):
            payload = surface_extract._surface_payload(face, bin_out)

        # The guard that used to raise "surface domain [3.28, 9.28] does not
        # cover face UV [-3.0, 3.0]".
        surface_extract._assert_surface_covers_face(payload, *window, bin_out)

        # And the reframed surface evaluates to the SAME points the periodic
        # original does at the face's own parameters — a translation of the
        # knots, not a move of the geometry.
        rebuilt = _rebuild_bspline_surface(payload, bin_out.payload())
        for u in (-2.9, -1.0, 0.0, 1.7, 2.9):
            for v in (1.0, 5.0, 9.0):
                expected = nurbs.Value(u, v)
                actual = rebuilt.Value(u, v)
                self.assertLess(expected.Distance(actual), 1e-6, (u, v))


if __name__ == "__main__":
    unittest.main()
