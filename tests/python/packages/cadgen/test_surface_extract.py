"""`.surf` extraction: one component's exact topology for its readers.

A `.surf` is read by the selector tables, the measure and reference panels and
feature recognition -- never tessellated (cadgen meshes components with OCCT).
So the oracle here is OCCT itself for every analytic value a reader uses, and
the contract for everything else is what those readers take: loops as ordered
edge references, B-spline surfaces as degrees and pole counts (a bilinear
patch's corners, which recognition reads as a ruled loft's sections), swept
surfaces by axis or direction, general curves by kind and range.
"""

from __future__ import annotations

import json
import math
import struct
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


def _floats(binbuf, ref):
    offset, count = ref
    return struct.unpack_from(f"<{count}f", binbuf, offset * 4)


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
    """Planes, a cylinder, a torus, NURBS faces (a rect-to-circle loft), a
    revolved spline profile, and the bilinear patches of a twisted ruled loft."""
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
    # Full revolve of a spline profile: a swept surface of revolution.
    with bd.BuildPart() as revolved:
        with bd.BuildSketch(bd.Plane.XZ):
            with bd.BuildLine() as profile:
                bd.Spline((8, -2), (10.5, 0), (8, 2))
                bd.Line((8, 2), (8, -2))
            bd.make_face()
        bd.revolve(axis=bd.Axis.Z)
    revolved_part = revolved.part.moved(bd.Location((0, 0, 60)))
    # A square lofted to a smaller, turned square with ruled sides: each side is
    # a bilinear B-spline patch, the one NURBS kind whose corners a .surf keeps.
    with bd.BuildPart() as twisted:
        with bd.BuildSketch(bd.Plane.XY.offset(70)):
            bd.Rectangle(10, 10)
        with bd.BuildSketch(bd.Plane.XY.offset(80).rotated((0, 0, 30))):
            bd.Rectangle(6, 6)
        bd.loft(ruled=True)
    return bd.Compound(children=[fused, torus, lofted.part, revolved_part, twisted.part])


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

    def face(self, entry):
        from OCP.TopoDS import TopoDS

        return TopoDS.Face_s(self.face_map.FindKey(entry["ord"]))

    def test_counts_match_topology_ordinals(self) -> None:
        self.assertEqual(self.index["counts"]["faces"], self.face_map.Extent())
        self.assertEqual(self.index["counts"]["edges"], self.edge_map.Extent())
        self.assertEqual([f["ord"] for f in self.index["faces"]],
                         list(range(1, self.face_map.Extent() + 1)))

    def test_fixture_exercises_analytics_swept_surfaces_and_nurbs(self) -> None:
        kinds = {f["surface"]["kind"] for f in self.index["faces"]}
        self.assertLessEqual({"plane", "cylinder", "torus", "revolution", "nurbs"}, kinds)

    def test_analytic_surfaces_match_occt(self) -> None:
        from OCP.BRep import BRep_Tool

        for entry in self.index["faces"]:
            if entry["surface"]["kind"] in ("nurbs", "revolution", "extrusion", "freeform"):
                continue
            geom = BRep_Tool.Surface_s(self.face(entry))
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

    def test_swept_surfaces_carry_their_axis_or_direction_alone(self) -> None:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        checked = 0
        for entry in self.index["faces"]:
            payload = entry["surface"]
            if payload["kind"] == "revolution":
                axis = BRepAdaptor_Surface(self.face(entry)).AxeOfRevolution()
                location, direction = axis.Location(), axis.Direction()
                self.assertEqual(payload, {"kind": "revolution",
                                           "origin": [location.X(), location.Y(), location.Z()],
                                           "dir": [direction.X(), direction.Y(), direction.Z()]})
                checked += 1
            elif payload["kind"] == "extrusion":
                direction = BRepAdaptor_Surface(self.face(entry)).Direction()
                self.assertEqual(payload, {"kind": "extrusion", "dir": [direction.X(), direction.Y(), direction.Z()]})
                checked += 1
        self.assertGreater(checked, 0, "fixture has no swept faces")

    def test_b_splines_carry_no_net_and_a_bilinear_patch_its_corners(self) -> None:
        from OCP.BRep import BRep_Tool

        bilinear = 0
        for entry in self.index["faces"]:
            payload = entry["surface"]
            if payload["kind"] != "nurbs":
                continue
            surface = BRep_Tool.Surface_s(self.face(entry))
            self.assertEqual({key: payload[key] for key in ("degU", "degV", "nu", "nv")},
                             {"degU": surface.UDegree(), "degV": surface.VDegree(),
                              "nu": surface.NbUPoles(), "nv": surface.NbVPoles()})
            self.assertFalse({"knotsU", "knotsV", "weights"} & set(payload), "no knots or weights")
            if (payload["degU"], payload["degV"], payload["nu"], payload["nv"]) != (1, 1, 2, 2):
                self.assertNotIn("poles", payload, f"face {entry['ord']} keeps no control net")
                continue
            corners = _floats(self.binbuf, payload["poles"])
            expected = [c for i in (1, 2) for j in (1, 2)
                        for c in (surface.Pole(i, j).X(), surface.Pole(i, j).Y(), surface.Pole(i, j).Z())]
            for got, want in zip(corners, expected, strict=True):
                self.assertAlmostEqual(got, want, places=4)
            bilinear += 1
        self.assertEqual(bilinear, 4, "the twisted loft's four ruled sides")
        self.assertEqual(len(self.binbuf), 4 * 12 * 4, "the float chunk is the bilinear corners alone")

    def test_loops_are_ordered_edge_references(self) -> None:
        from OCP.BRepTools import BRepTools_WireExplorer
        from OCP.TopAbs import TopAbs_WIRE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        edges = {edge["ord"]: edge for edge in self.index["edges"]}
        for entry in self.index["faces"]:
            face = self.face(entry)
            walked = []
            wires = TopExp_Explorer(face, TopAbs_WIRE)
            while wires.More():
                walker = BRepTools_WireExplorer(TopoDS.Wire_s(wires.Current()), face)
                loop = []
                while walker.More():
                    loop.append(self.edge_map.FindIndex(walker.Current()))
                    walker.Next()
                walked.append(loop)
                wires.Next()
            self.assertEqual([[ref["edgeOrd"] for ref in loop] for loop in entry["loops"]], walked)
            for loop in entry["loops"]:
                for ref in loop:
                    self.assertEqual(set(ref), {"edgeOrd", "reversed"})
                    self.assertIn(entry["ord"], edges[ref["edgeOrd"]]["faceOrds"])

    def test_edge_classes_and_curves(self) -> None:
        classes = {e["class"] for e in self.index["edges"]}
        self.assertIn("feature", classes)
        self.assertIn("seam", classes)  # cylinder + torus both have seams
        self.assertIn("tangent", classes)  # fillet blends meet faces G1
        kinds = set()
        for entry in self.index["edges"]:
            curve = entry["curve"]
            if curve is None:
                continue
            kinds.add(curve["kind"])
            if curve["kind"] == "bspline":
                self.assertEqual(set(curve), {"kind", "range"}, "a general curve is its kind and range")
        self.assertLessEqual({"line", "circle", "bspline"}, kinds)

    def test_container_roundtrip_and_the_previous_format_still_reads(self) -> None:
        from cadgen._internal.surface_extract import SURF_VERSION, read_surf
        from cadgen.store.surfaces import validate_surface_bytes

        index, _ = read_surf(bytes(self.data))
        self.assertEqual((index["version"], SURF_VERSION), (3, 3))
        self.assertEqual(validate_surface_bytes(bytes(self.data))["version"], 3)
        with self.assertRaises(ValueError):
            read_surf(b"GLBX" + bytes(self.data[4:]))
        # A version-2 surface an older build pinned (an eager-only component's)
        # still validates: version 3 only removed fields.
        previous = json.dumps({**index, "version": 2}, separators=(",", ":")).encode()
        legacy = b"SURF" + struct.pack("<II", 2, len(previous)) + previous
        self.assertEqual(validate_surface_bytes(legacy)["version"], 2)
        mixed = b"SURF" + struct.pack("<II", 3, len(previous)) + previous
        with self.assertRaisesRegex(ValueError, "invalid SURF index"):
            validate_surface_bytes(mixed)


class TightBoundsTest(unittest.TestCase):
    """A face's or edge's reported bbox must bound the SURFACE, not its poles.

    ``BRepBndLib::Add`` bounds a B-spline by its control polygon: a NURBS
    circle of radius r reports r/cos(22.5 deg) = 1.082 r, so every rounded
    surface came back ~8% too big and `inspect refs --facts` bounds could
    invent a clash that is not there (PR #370 bug record 004).
    """

    def _nurbs_cylinder(self, radius: float, height: float):
        import build123d as bd
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

        solid = bd.Cylinder(radius=radius, height=height)
        return BRepBuilderAPI_NurbsConvert(solid.wrapped, True).Shape()

    def test_nurbs_cylinder_face_bounds_match_the_radius(self) -> None:
        from cadgen._internal.surface_extract import extract_surface_component, read_surf

        radius, height = 7.5, 4.0
        index, _ = read_surf(bytes(extract_surface_component(self._nurbs_cylinder(radius, height))))
        lateral = [f for f in index["faces"] if f["surface"]["kind"] == "nurbs" and f["bbox"][5] - f["bbox"][2] > height / 2]
        self.assertTrue(lateral, "fixture must produce a NURBS lateral face")
        for face in lateral:
            xmin, ymin, _zmin, xmax, ymax, _zmax = face["bbox"]
            for value in (xmax, ymax, -xmin, -ymin):
                self.assertAlmostEqual(value, radius, places=4)

    def test_component_bounds_match_the_radius(self) -> None:
        from cadgen._internal.selector_table import build_selector_table
        from cadgen._internal.surface_extract import extract_surface_component, read_surf

        radius, height = 7.5, 4.0
        shape = self._nurbs_cylinder(radius, height)
        index, _ = read_surf(bytes(extract_surface_component(shape)))
        bbox = build_selector_table(shape, index)["bbox"]
        self.assertAlmostEqual(bbox["max"][0], radius, places=4)
        self.assertAlmostEqual(bbox["max"][1], radius, places=4)
        self.assertAlmostEqual(bbox["min"][0], -radius, places=4)
        self.assertAlmostEqual(bbox["max"][2], height / 2, places=4)


class ClampedUvBoundsTest(unittest.TestCase):
    """UVBounds_s can return a bound a floating-point hair OUTSIDE the
    surface's own domain (vendor STEPs: -0.0 vs 0.0, a few 1e-6 past a
    trimmed span). A face's recorded ``uv`` window -- what feature recognition
    reads a cylinder's sweep from -- is pulled into the domain in each
    non-periodic direction, so it names parameters the surface has (Waveshare
    ESP32 driver board regression)."""

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


if __name__ == "__main__":
    unittest.main()
