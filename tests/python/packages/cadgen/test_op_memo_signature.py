"""Identity optimization must preserve every field of the original signature.

The reference deliberately retains the three independent topology searches.
Comparing its complete tuples covers set/dict ordering as well as equality;
comparing only volumes would miss a changed edge or face selection.
"""

from __future__ import annotations

import unittest

from cadgen._internal import op_memo


def _reference_signature(wrapped):
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    def rounded(point):
        return (round(point.X(), 6), round(point.Y(), 6), round(point.Z(), 6))

    def sub_shapes(kind):
        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(wrapped, kind, found)
        return [found.FindKey(i) for i in range(1, found.Extent() + 1)]

    vertices = sub_shapes(TopAbs_ShapeEnum.TopAbs_VERTEX)
    edges = sub_shapes(TopAbs_ShapeEnum.TopAbs_EDGE)
    faces = sub_shapes(TopAbs_ShapeEnum.TopAbs_FACE)
    points = sorted(rounded(BRep_Tool.Pnt_s(TopoDS.Vertex_s(v))) for v in vertices)
    samples = []
    if faces:
        for face in faces:
            surface = BRepAdaptor_Surface(TopoDS.Face_s(face))
            samples.append(rounded(surface.Value(
                (surface.FirstUParameter() + surface.LastUParameter()) / 2,
                (surface.FirstVParameter() + surface.LastVParameter()) / 2,
            )))
    else:
        for edge in edges:
            edge = TopoDS.Edge_s(edge)
            if BRep_Tool.Degenerated_s(edge):
                continue
            curve = BRepAdaptor_Curve(edge)
            samples.append(rounded(curve.Value(
                (curve.FirstParameter() + curve.LastParameter()) / 2,
            )))
    return (
        int(wrapped.ShapeType()), (len(vertices), len(edges), len(faces)),
        tuple(points), tuple(sorted(samples)),
    )


def _compound(*shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    result, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def _nonmanifold_shell():
    """Three triangular faces incident to the same edge."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.TopoDS import TopoDS_Shell
    from OCP.gp import gp_Pnt

    start, end = gp_Pnt(0, 0, 0), gp_Pnt(8, 0, 0)
    common = BRepBuilderAPI_MakeEdge(start, end).Edge()
    shell, builder = TopoDS_Shell(), BRep_Builder()
    builder.MakeShell(shell)
    for tip in (gp_Pnt(4, 6, 0), gp_Pnt(4, 0, 5), gp_Pnt(4, -7, 0)):
        wire = BRepBuilderAPI_MakeWire(
            common,
            BRepBuilderAPI_MakeEdge(end, tip).Edge(),
            BRepBuilderAPI_MakeEdge(tip, start).Edge(),
        ).Wire()
        builder.Add(shell, BRepBuilderAPI_MakeFace(wire).Face())
    return shell


def _bezier_face():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BezierSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.gp import gp_Pnt

    poles = TColgp_Array2OfPnt(1, 3, 1, 3)
    for u in range(1, 4):
        for v in range(1, 4):
            poles.SetValue(u, v, gp_Pnt(u * 3, v * 4, 2 if (u, v) == (2, 2) else 0))
    return BRepBuilderAPI_MakeFace(Geom_BezierSurface(poles), 0.1, 0.8, 0.2, 0.9, 1e-7).Face()


class OpMemoSignatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeTorus
        from OCP.TopAbs import TopAbs_INTERNAL
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS_Edge, TopoDS_Shell, TopoDS_Wire
        from OCP.gp import gp_Ax2, gp_Circ, gp_Pnt, gp_Dir, gp_Trsf, gp_Vec

        box = BRepPrimAPI_MakeBox(9, 7, 3).Shape()
        circle = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(2, 3, 4), gp_Dir(0, 0, 1)), 5)).Edge()
        internal = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(8, 0, 0)).Edge()
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(3, 0, 0)).Vertex()
        builder = BRep_Builder()
        builder.Add(internal, vertex.Oriented(TopAbs_INTERNAL))
        builder.UpdateVertex(vertex, 3.0, internal, 1e-7)
        degenerate = TopoDS_Edge()
        builder.MakeEdge(degenerate)
        builder.Degenerated(degenerate, True)
        builder.Add(degenerate, BRepBuilderAPI_MakeVertex(gp_Pnt(4, 5, 6)).Vertex())
        empty_wire, empty_shell = TopoDS_Wire(), TopoDS_Shell()
        builder.MakeWire(empty_wire)
        builder.MakeShell(empty_shell)
        shift = gp_Trsf()
        shift.SetTranslation(gp_Vec(13, -7, 4))
        nested = _compound(box, box.Reversed(), _compound(box.Located(TopLoc_Location(shift))))
        cls.cases = {
            "box": box,
            "sphere": BRepPrimAPI_MakeSphere(5).Shape(),
            "cone_apex": BRepPrimAPI_MakeCone(5, 0, 9).Shape(),
            "torus": BRepPrimAPI_MakeTorus(9, 2).Shape(),
            "trimmed_bezier_face": _bezier_face(),
            "closed_edge": circle,
            "closed_wire": BRepBuilderAPI_MakeWire(circle).Wire(),
            "internal_vertex": internal,
            "degenerate_edge": degenerate,
            "empty_wire": empty_wire,
            "empty_shell": empty_shell,
            "empty_compound": _compound(),
            "nonmanifold_shell": _nonmanifold_shell(),
            "nested_repeated_placements": nested,
        }

    def _assert_parity(self, shape):
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, found)
        for i in range(1, found.Extent() + 1):
            child = found.FindKey(i)
            with self.subTest(subshape=i, kind=child.ShapeType()):
                expected = _reference_signature(child)
                actual = op_memo._signature(child)
                self.assertEqual(actual, expected)
                self.assertEqual(hash(actual), hash(expected))
                self.assertEqual(op_memo._signature_hash(child), hash((expected[0], expected[2])))

    def test_all_topology_ranks_match_original_tuple(self):
        for label, shape in self.cases.items():
            with self.subTest(case=label):
                self._assert_parity(shape)
        # These cases exercise unique vertex counts, not an assumed two
        # endpoints, and a degenerate edge with no evaluable curve.
        self.assertEqual(op_memo._signature(self.cases["internal_vertex"])[1], (3, 1, 0))
        self.assertEqual(op_memo._signature(self.cases["closed_edge"])[1], (1, 1, 0))
        self.assertEqual(op_memo._signature(self.cases["degenerate_edge"])[3], ())
        self.assertEqual(op_memo._signature(self.cases["nonmanifold_shell"])[1][2], 3)

    def test_movement_reversal_copy_and_readback_match_original(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

        rotation = gp_Trsf()
        rotation.SetRotation(gp_Ax1(gp_Pnt(2, 3, 4), gp_Dir(1, 2, 3)), 0.4321)
        translation = gp_Trsf()
        translation.SetTranslation(gp_Vec(0.0000011, -17.5, 6.25))
        for label, original in self.cases.items():
            moved = original.Moved(TopLoc_Location(translation)).Moved(TopLoc_Location(rotation))
            for expression, shape in (
                ("moved", moved), ("reversed", moved.Reversed()),
                ("copied", BRepBuilderAPI_Copy(moved, True, False).Shape()),
                ("readback", op_memo._read_brep(op_memo._write_brep(moved))),
            ):
                with self.subTest(case=label, expression=expression):
                    self._assert_parity(shape)

    def test_native_vertex_mutation_is_seen_without_a_new_tshape(self):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Pnt

        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(1, 2, 3)).Vertex()
        tshape = vertex.TShape()
        before = op_memo._signature(vertex)
        BRep_Builder().UpdateVertex(vertex, gp_Pnt(4, 5, 6), 1e-7)
        self.assertIs(vertex.TShape(), tshape)
        self.assertNotEqual(op_memo._signature(vertex), before)
        self.assertEqual(op_memo._signature(vertex), _reference_signature(vertex))

    def test_location_changes_are_seen_without_a_new_tshape(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec

        edge = BRepBuilderAPI_MakeEdge(gp_Pnt(1, 2, 3), gp_Pnt(4, 5, 6)).Edge()
        tshape = edge.TShape()
        before = op_memo._signature(edge)
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(3, 5, 7))
        edge.Move(TopLoc_Location(transform))
        self.assertIs(edge.TShape(), tshape)
        self.assertNotEqual(op_memo._signature(edge), before)
        self.assertEqual(op_memo._signature(edge), _reference_signature(edge))

    def test_hash_collision_does_not_merge_an_arc_and_its_chord(self):
        import os
        from unittest import mock
        from build123d import Edge

        op_memo.install()
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "1"}):
            line = Edge.make_line((0, 0, 0), (10, 0, 0))
            arc = Edge.make_three_point_arc((0, 0, 0), (5, 3, 0), (10, 0, 0))
            self.assertEqual(hash(line), hash(arc))
            self.assertNotEqual(line, arc)
            self.assertEqual(len({line, arc}), 2)
            self.assertEqual({line: "line", arc: "arc"}[arc], "arc")

    def test_hash_does_not_evaluate_full_surface_or_curve_signature(self):
        import os
        from unittest import mock
        from build123d import Edge

        op_memo.install()
        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "1"}):
            edge = Edge.make_three_point_arc((0, 0, 0), (5, 3, 0), (10, 0, 0))
            with mock.patch.object(op_memo, "_signature", side_effect=AssertionError("hash evaluated full geometry")):
                self.assertIsInstance(hash(edge), int)


class NumericRoundingCacheTest(unittest.TestCase):
    def tearDown(self):
        op_memo.clear()

    def test_exact_rounding_preserves_signed_zero_nonfinite_and_boundary_values(self):
        import math
        import struct

        values = [0.0, -0.0, 1.0, -1.0, 1e-300, -1e-300,
                  math.inf, -math.inf, math.nan, 0.0000005, -0.0000005,
                  math.nextafter(0.0000005, 0), math.nextafter(0.0000005, math.inf)]
        for x in values:
            for y in values:
                coordinates = (x, y, -0.0)
                expected = tuple(round(value, op_memo._SIGNATURE_DECIMALS) for value in coordinates)
                for _ in range(2):
                    actual = op_memo._rounded_coordinates(coordinates)
                    self.assertEqual(struct.pack("<ddd", *actual), struct.pack("<ddd", *expected))
        # A cached NaN tuple would compare equal to itself by object identity.
        first = op_memo._rounded_coordinates((math.nan, 1.0, 2.0))
        second = op_memo._rounded_coordinates((math.nan, 1.0, 2.0))
        self.assertNotEqual(first, second)

    def test_numeric_retention_is_bounded_and_clear_releases_it(self):
        op_memo.clear()
        capacity = op_memo._rounded_coordinate_bytes.cache_info().maxsize
        for i in range(capacity + 100):
            op_memo._rounded_coordinates((float(i), 1.25, -0.0))
        self.assertEqual(op_memo._rounded_coordinate_bytes.cache_info().currsize, capacity)
        op_memo.clear()
        self.assertEqual(op_memo._rounded_coordinate_bytes.cache_info().currsize, 0)

    def test_numeric_subclasses_retain_their_rounding_callbacks(self):
        calls = []

        class Number(float):
            def __round__(self, digits=None):
                calls.append(digits)
                return 42.0

        coordinates = (Number(1.25), 2.0, 3.0)
        for _ in range(2):
            self.assertEqual(op_memo._rounded_coordinates(coordinates), (42.0, 2.0, 3.0))
        self.assertEqual(calls, [op_memo._SIGNATURE_DECIMALS] * 2)


class SignatureCacheStateParityTest(unittest.TestCase):
    def test_builder_selections_attributes_and_bytes_survive_every_cache_state(self):
        import hashlib
        import os
        import shutil
        from pathlib import Path
        from unittest import mock

        from build123d import Box, BuildPart, Cylinder, Location, Mode, Select, Solid
        from tests.python.support.tmp_root import generated_cad_directory

        def build():
            with BuildPart() as builder:
                Box(12, 10, 4)
                held = builder.edges()[0]
                Cylinder(2, 8, mode=Mode.SUBTRACT)
            shape = builder.part
            shape.label = "plate"
            shape.color = (0.2, 0.4, 0.6, 1.0)
            shape = shape.cut(Solid.make_cylinder(0.5, 1).moved(Location((4, 3, 0))))
            selections = {
                kind: sorted(_reference_signature(child.wrapped) for child in getattr(builder, kind)(Select.LAST))
                for kind in ("vertices", "edges", "faces", "solids")
            }
            selections["held"] = sorted(_reference_signature(child.wrapped) for child in shape.edges() if held.is_same(child))
            return shape, {
                "digest": hashlib.sha256(op_memo._write_brep(shape.wrapped)).hexdigest(),
                "volume": shape.volume, "label": shape.label, "color": tuple(shape.color),
                "selections": selections,
            }

        optimized = op_memo._signature
        outcomes = []
        op_memo.install()
        try:
            for implementation in (_reference_signature, optimized):
                with generated_cad_directory(prefix="signature-parity-") as scratch:
                    with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": scratch, "CADGEN_OP_MEMO": "1", "CADGEN_OP_MEMO_DISK": "1"}), mock.patch.object(op_memo, "_signature", implementation):
                        op_memo.clear()
                        consumers = []
                        for state in ("miss", "ram", "disk", "deleted"):
                            if state in ("disk", "deleted"):
                                op_memo.clear()
                            if state == "deleted":
                                shutil.rmtree(Path(scratch) / "objects")
                            before = op_memo.stats()
                            shape, outcome = build()
                            after = op_memo.stats()
                            with self.subTest(implementation=implementation.__name__, cache=state):
                                counter = "disk_hits" if state == "disk" else "hits" if state == "ram" else "misses"
                                self.assertGreater(after[counter], before[counter])
                                self.assertTrue(all(not shape.wrapped.IsPartner(other.wrapped) for other in consumers))
                                if outcomes:
                                    self.assertEqual(outcome, outcomes[0])
                            consumers.append(shape)
                            outcomes.append(outcome)
        finally:
            op_memo.clear()


if __name__ == "__main__":
    unittest.main()
