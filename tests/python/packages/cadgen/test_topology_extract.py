"""A component's topology facts: what its selector table is built from.

The facts are read by the selector table a part's derivation builds from them --
never tessellated (cadgen meshes components with OCCT). So the oracle here is
OCCT itself for every value a reader uses, and the contract for everything else
is what the table takes: three ordinal tables holding exactly its inputs, loops
as ordered edge ordinals, a plane's oriented normal, a circle's sweep -- and
their object form, which an eager-only component's tree pins.
"""

from __future__ import annotations

import json
import math
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

SHAPE_KEYS = {"ord", "kind"}
FACE_KEYS = {"ord", "shape", "surfaceType", "loops"}
FACE_OPTIONAL = {"normal", "params"}
EDGE_KEYS = {"ord", "shape", "class", "continuity", "dihedralDeg", "flags", "adjacentFaceCount", "curveType",
             "faceOrds", "length", "center"}
EDGE_OPTIONAL = {"params", "sweepRadians"}


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
            with bd.BuildLine():
                bd.Spline((8, -2), (10.5, 0), (8, 2))
                bd.Line((8, 2), (8, -2))
            bd.make_face()
        bd.revolve(axis=bd.Axis.Z)
    revolved_part = revolved.part.moved(bd.Location((0, 0, 60)))
    # A square lofted to a smaller, turned square with ruled sides: bilinear
    # B-spline patches, whose facts are their type and metrics like any other's.
    with bd.BuildPart() as twisted:
        with bd.BuildSketch(bd.Plane.XY.offset(70)):
            bd.Rectangle(10, 10)
        with bd.BuildSketch(bd.Plane.XY.offset(80).rotated((0, 0, 30))):
            bd.Rectangle(6, 6)
        bd.loft(ruled=True)
    return bd.Compound(children=[fused, torus, lofted.part, revolved_part, twisted.part])


class TopologyFactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen._internal.topology_extract import extract_topology_facts

        cls.shape = _build_fixture().wrapped
        cls.facts = extract_topology_facts(cls.shape)

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

    def edge(self, entry):
        from OCP.TopoDS import TopoDS

        return TopoDS.Edge_s(self.edge_map.FindKey(entry["ord"]))

    def test_three_tables_in_ordinal_order(self) -> None:
        self.assertEqual(set(self.facts), {"shapes", "faces", "edges"})
        self.assertEqual([f["ord"] for f in self.facts["faces"]], list(range(1, self.face_map.Extent() + 1)))
        self.assertEqual([e["ord"] for e in self.facts["edges"]], list(range(1, self.edge_map.Extent() + 1)))
        self.assertEqual([s["ord"] for s in self.facts["shapes"]], [1, 2, 3, 4, 5], "one entity per solid")
        self.assertTrue(all(s["kind"] == "solid" for s in self.facts["shapes"]))
        self.assertEqual({f["shape"] for f in self.facts["faces"]}, {1, 2, 3, 4, 5})
        self.assertEqual({e["shape"] for e in self.facts["edges"]}, {1, 2, 3, 4, 5})

    def test_rows_hold_what_the_selector_table_reads_and_nothing_else(self) -> None:
        for row in self.facts["shapes"]:
            self.assertEqual(set(row), SHAPE_KEYS)
        for row in self.facts["faces"]:
            self.assertTrue(FACE_KEYS <= set(row) <= FACE_KEYS | FACE_OPTIONAL, row.keys())
            self.assertEqual("normal" in row, row["surfaceType"] == "plane")
        for row in self.facts["edges"]:
            self.assertTrue(EDGE_KEYS <= set(row) <= EDGE_KEYS | EDGE_OPTIONAL, row.keys())
            self.assertEqual("sweepRadians" in row, row["curveType"] == "circle" and row["class"] != "degenerate")

    def test_fixture_exercises_analytics_swept_surfaces_and_nurbs(self) -> None:
        kinds = {f["surfaceType"] for f in self.facts["faces"]}
        self.assertLessEqual({"plane", "cylinder", "torus", "surfaceofrevolution", "bsplinesurface"}, kinds)

    def test_metrics_and_analytic_parameters_are_occts(self) -> None:
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_Orientation

        for entry in self.facts["faces"]:
            face = self.face(entry)
            adaptor = BRepAdaptor_Surface(face)
            if entry["surfaceType"] == "plane":
                direction = adaptor.Plane().Position().Direction()
                sign = -1.0 if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED else 1.0
                self.assertEqual(entry["normal"], [sign * direction.X(), sign * direction.Y(), sign * direction.Z()])
                self.assertEqual(entry["params"]["origin"], [adaptor.Plane().Location().X(), adaptor.Plane().Location().Y(),
                                                             adaptor.Plane().Location().Z()])
            elif entry["surfaceType"] == "cylinder":
                self.assertEqual(entry["params"]["radius"], adaptor.Cylinder().Radius())
            elif entry["surfaceType"] == "torus":
                self.assertEqual((entry["params"]["majorRadius"], entry["params"]["minorRadius"]),
                                 (adaptor.Torus().MajorRadius(), adaptor.Torus().MinorRadius()))
        for entry in self.facts["edges"]:
            edge = self.edge(entry)
            props = GProp_GProps()
            BRepGProp.LinearProperties_s(edge, props)
            self.assertEqual(entry["length"], props.Mass())
            self.assertEqual(entry["center"], [props.CentreOfMass().X(), props.CentreOfMass().Y(), props.CentreOfMass().Z()])
            if "sweepRadians" in entry:
                curve = BRepAdaptor_Curve(edge)
                self.assertEqual(entry["sweepRadians"], abs(curve.LastParameter() - curve.FirstParameter()))
                self.assertEqual(entry["params"]["radius"], curve.Circle().Radius())

    def test_loops_are_ordered_edge_ordinals(self) -> None:
        from OCP.BRepTools import BRepTools_WireExplorer
        from OCP.TopAbs import TopAbs_WIRE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        edges = {edge["ord"]: edge for edge in self.facts["edges"]}
        for entry in self.facts["faces"]:
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
            self.assertEqual(entry["loops"], walked)
            for loop in entry["loops"]:
                for ordinal in loop:
                    self.assertIn(entry["ord"], edges[ordinal]["faceOrds"])

    def test_edge_classes(self) -> None:
        classes = {e["class"] for e in self.facts["edges"]}
        self.assertIn("feature", classes)
        self.assertIn("seam", classes)  # cylinder + torus both have seams
        self.assertIn("tangent", classes)  # fillet blends meet faces G1
        self.assertLessEqual({"line", "circle", "bsplinecurve"}, {e["curveType"] for e in self.facts["edges"]})
        for entry in self.facts["edges"]:
            self.assertEqual(entry["adjacentFaceCount"], len(entry["faceOrds"]))
            if entry["class"] == "feature" and entry["continuity"] == "c0":
                self.assertGreater(entry["dihedralDeg"], 0)


class TopologyFactsObjectTest(unittest.TestCase):
    """The facts as an eager-only component's tree pins them, read without the kernel."""

    def facts(self) -> dict:
        return {
            "shapes": [{"ord": 1, "kind": "solid"}],
            "faces": [{"ord": 1, "shape": 1, "surfaceType": "plane", "normal": [0.0, 0.0, -1.0],
                       "params": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]}, "loops": [[1]]}],
            "edges": [{"ord": 1, "shape": 1, "class": "feature", "continuity": "c0", "dihedralDeg": 90.0, "flags": 1,
                       "adjacentFaceCount": 1, "curveType": "circle", "faceOrds": [1], "length": 6.283185307179586,
                       "center": [0.0, 0.0, 0.0], "sweepRadians": 6.283185307179586}],
        }

    def test_round_trip_keeps_every_value_and_the_extractors_order(self) -> None:
        from cadgen._internal.topology_facts import read_topology_facts, topology_facts_bytes

        payload = topology_facts_bytes(self.facts())
        self.assertEqual(read_topology_facts(payload), self.facts())
        self.assertEqual(list(json.loads(payload)["faces"][0]["params"]), ["origin", "axis"])
        self.assertEqual(read_topology_facts(payload)["edges"][0]["sweepRadians"], 2 * math.pi)

    def test_anything_but_whole_ordinal_tables_is_refused(self) -> None:
        from cadgen._internal.topology_facts import read_topology_facts, topology_facts_bytes

        with self.assertRaisesRegex(ValueError, "invalid topology facts JSON"):
            read_topology_facts(b"SURF\x03")
        for broken in (
            {**self.facts(), "counts": {}},
            {name: rows for name, rows in self.facts().items() if name != "shapes"},
            {**self.facts(), "edges": [{**self.facts()["edges"][0], "ord": 2}]},
            {**self.facts(), "faces": [self.facts()["faces"][0], self.facts()["faces"][0]]},
            {**self.facts(), "shapes": [["not", "a", "row"]]},
        ):
            with self.assertRaisesRegex(ValueError, "invalid topology facts"):
                read_topology_facts(json.dumps(broken).encode())
            with self.assertRaisesRegex(ValueError, "invalid topology facts"):
                topology_facts_bytes(broken)
        with self.assertRaises(ValueError):
            topology_facts_bytes({**self.facts(), "edges": [{**self.facts()["edges"][0], "length": math.nan}]})

    def test_the_table_takes_the_pinned_object_as_it_takes_the_live_facts(self) -> None:
        from build123d import Box, Cylinder

        from cadgen._internal.selector_table import build_selector_table, selector_table_bytes
        from cadgen._internal.topology_extract import extract_topology_facts
        from cadgen._internal.topology_facts import read_topology_facts, topology_facts_bytes

        shape = (Box(4, 5, 3) - Cylinder(1, 6)).wrapped
        facts = extract_topology_facts(shape)
        boxes = {"faces": {1: [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]}, "edges": {}}
        live = selector_table_bytes(build_selector_table(shape, facts, boxes=boxes))
        pinned = selector_table_bytes(build_selector_table(shape, read_topology_facts(topology_facts_bytes(facts)),
                                                           boxes=boxes))
        self.assertEqual(live, pinned)


class TightBoundsTest(unittest.TestCase):
    """A face's exact box -- the one a geometric token's signature rounds -- must bound the
    SURFACE, not its poles; the table's, its display mesh's, lies within the display chord.

    ``BRepBndLib::Add`` bounds a B-spline by its control polygon: a NURBS
    circle of radius r reports r/cos(22.5 deg) = 1.082 r, so every rounded
    surface came back ~8% too big (PR #370 bug record 004).
    """

    def _nurbs_cylinder(self, radius: float, height: float):
        import build123d as bd
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

        solid = bd.Cylinder(radius=radius, height=height)
        return BRepBuilderAPI_NurbsConvert(solid.wrapped, True).Shape()

    def test_nurbs_cylinder_face_bounds_match_the_radius(self) -> None:
        from cadgen._internal.topology_extract import component_metrics

        radius, height = 7.5, 4.0
        metrics = component_metrics(self._nurbs_cylinder(radius, height), face_boxes=True)
        lateral = [f for f in metrics["faces"] if f["bbox"][5] - f["bbox"][2] > height / 2]
        self.assertTrue(lateral, "fixture must produce a NURBS lateral face")
        for face in lateral:
            xmin, ymin, _zmin, xmax, ymax, _zmax = face["bbox"]
            for value in (xmax, ymax, -xmin, -ymin):
                self.assertAlmostEqual(value, radius, places=4)

    def test_the_tables_bounds_lie_within_the_display_chord(self) -> None:
        from cadgen._internal.selector_table import build_selector_table
        from cadgen._internal.tessellate import _bounding_diagonal, mesh_component
        from cadgen._internal.topology_extract import extract_topology_facts
        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        radius, height = 7.5, 4.0
        shape = self._nurbs_cylinder(radius, height)
        facts = extract_topology_facts(shape)
        chord = DISPLAY_TESSELLATION["chordTolerance"]
        boxes = mesh_component(shape, facts, {}, part="0" * 64 + "-v1", chord=chord,
                               angle=DISPLAY_TESSELLATION["angleTolerance"]).boxes
        bbox = build_selector_table(shape, facts, boxes=boxes)["bbox"]
        deflection = chord * _bounding_diagonal(shape)
        # The mesh's nodes lie on the surface: never past it, short of it by the chord at most.
        for value, exact in ((bbox["max"][0], radius), (bbox["max"][1], radius), (-bbox["min"][0], radius),
                             (bbox["max"][2], height / 2)):
            self.assertLessEqual(value, exact + 1e-6)
            self.assertGreaterEqual(value, exact - deflection)


if __name__ == "__main__":
    unittest.main()
