"""The mesh contract: FreeCAD's default tolerance, BRepMesh as it is, every edge classed
from the B-rep, every vertex in the buffer, a face the mesher cannot mesh named with the
kernel's verdict on it, and the facts of any element measured on request."""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import textwrap
import unittest
import urllib.request
from pathlib import Path

import numpy as np

from cadgen.engine import build as engine_build
from cadgen.engine import mesh
from cadgen.engine.serve import Server


def classes(part: mesh.Mesh) -> dict[str, int]:
    found: dict[str, int] = {}
    for kind in part.edges[:, 3]:
        name = mesh.CLASS_NAMES[int(kind)]
        found[name] = found.get(name, 0) + 1
    return found


def bowtie_part():
    """A box and, beside it, a planar face whose one wire crosses itself."""
    import build123d as bd
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((0, 0), (1, 1), (1, 0), (0, 1)):
        polygon.Add(gp_Pnt(x + 5, y, 0))
    polygon.Close()
    return bd.Compound([bd.Box(1, 1, 1), bd.Face(BRepBuilderAPI_MakeFace(polygon.Wire(), True).Face())])


class MeshContractTest(unittest.TestCase):
    def test_the_tolerance_is_freecads_default(self) -> None:
        import build123d as bd

        part = mesh.mesh_shape(bd.Box(10, 20, 30).wrapped)
        self.assertAlmostEqual(part.linear, (10 + 20 + 30) / 300 * 0.5, places=6)
        self.assertAlmostEqual(part.angular, math.radians(28.5), places=6)

    def test_an_extrusions_far_cap_edges_are_drawn_where_they_are(self) -> None:
        import build123d as bd

        # The far cap's edges share the near cap's TShapes, moved by a location: each is its own polyline.
        prism = bd.extrude(bd.Polygon((-9, 8), (9, 8), (0, -8)), 35)
        part = mesh.mesh_shape(prism.wrapped)
        polylines = {tuple(np.round(part.edge_points[first:first + count].ravel(), 3)) for _o, first, count, _k in part.edges}
        self.assertEqual(len(polylines), 9)
        ends = sorted({round(float(z), 3) for line in polylines for z in line[2::3] if len(set(line[2::3])) == 1})
        self.assertEqual([len(ends), ends[-1] - ends[0]], [2, 35.0], "a cap's edges at each end")

    def test_an_analytic_face_is_held_to_the_deflection(self) -> None:
        import build123d as bd

        part = mesh.mesh_shape(bd.Torus(10, 3).wrapped)
        centroids = part.positions[part.indices.reshape(-1, 3)].astype(float).mean(axis=1)
        off = np.abs(3 - np.hypot(np.hypot(centroids[:, 0], centroids[:, 1]) - 10, centroids[:, 2]))
        self.assertLessEqual(off.max(), part.linear, "every triangle within the deflection of the torus")

    def test_a_part_is_meshed_from_its_bytes_and_left_as_it_was(self) -> None:
        import build123d as bd
        from OCP.BRep import BRep_Tool
        from OCP.TopLoc import TopLoc_Location

        rounded = bd.fillet(bd.Box(4, 4, 4).edges(), 0.5)
        live = mesh.mesh_shape(rounded.wrapped).to_bytes()
        self.assertEqual(live, mesh.mesh_shape(mesh.shape_bytes(rounded.wrapped)).to_bytes())
        self.assertTrue(all(BRep_Tool.Triangulation_s(face.wrapped, TopLoc_Location()) is None
                            for face in rounded.faces()), "the caller's shape carries no triangulation")

    def test_a_box_is_six_faces_twelve_feature_edges_and_eight_vertices(self) -> None:
        import build123d as bd

        part = mesh.Mesh.from_bytes(mesh.mesh_shape(bd.Box(1, 2, 3).wrapped).to_bytes())
        self.assertEqual(part.faces[:, 0].tolist(), [1, 2, 3, 4, 5, 6])
        self.assertEqual(classes(part), {"feature": 12})
        self.assertEqual(part.edges[:, 0].tolist(), list(range(1, 13)))
        # The face ranges tile the index buffer, in order.
        self.assertTrue(np.array_equal(part.faces[1:, 1], np.cumsum(part.faces[:-1, 2])))
        self.assertEqual(int(part.faces[:, 2].sum()), len(part.indices))
        self.assertEqual(len(part.vertices), 8)
        self.assertEqual(part.vertices[:, 0].tolist(), list(range(1, 9)))
        corners = {tuple(row) for row in np.round(np.abs(part.vertices[:, 1:]), 6).tolist()}
        self.assertEqual(corners, {(0.5, 1.0, 1.5)})
        self.assertEqual(part.unmeshed, {})

    def test_a_cylinder_has_one_seam_and_two_feature_circles(self) -> None:
        import build123d as bd

        part = mesh.mesh_shape(bd.Cylinder(1, 2).wrapped)
        self.assertEqual(classes(part), {"feature": 2, "seam": 1})
        self.assertEqual(len(part.vertices), 2)

    def test_a_filleted_box_has_tangent_edges(self) -> None:
        import build123d as bd

        rounded = bd.fillet(bd.Box(4, 4, 4).edges().filter_by(bd.Axis.Z), 0.5)
        found = classes(mesh.mesh_shape(rounded.wrapped))
        self.assertEqual(found.get("tangent"), 8, found)  # each round meets two flat sides
        self.assertEqual(found.get("feature"), 16, found)  # the top and bottom rims

    def test_a_pick_grows_by_tangent_groups_and_edge_chains(self) -> None:
        import build123d as bd

        rounded = bd.fillet(bd.Box(4, 4, 4).edges().filter_by(bd.Axis.Z), 0.5)
        groups = mesh.Topology(rounded.wrapped).groups()
        faces = {}
        for face, group in groups["faces"].items():
            faces.setdefault(group, []).append(int(face))
        # The four sides and four rounds are one smooth band; the top and the bottom stand alone.
        self.assertEqual(sorted(len(members) for members in faces.values()), [1, 1, 8])
        edges = {}
        for edge, chain in groups["edges"].items():
            edges.setdefault(chain, []).append(int(edge))
        # Each rim (four lines, four arcs) runs on round the box; each round's two seams to the
        # sides stop at the rims' corners.
        self.assertEqual(sorted(len(members) for members in edges.values()), [1] * 8 + [8, 8])

    def test_a_face_the_mesher_cannot_mesh_is_named_with_its_verdict(self) -> None:
        part = mesh.mesh_shape(bowtie_part().wrapped)
        self.assertEqual(sorted(part.unmeshed), [7])
        self.assertIn("SelfIntersectingWire", part.unmeshed[7])
        brepmesh, brepcheck = part.unmeshed[7].split("; BRepCheck: ", 1)
        self.assertIn("SelfIntersectingWire", brepmesh.removeprefix("BRepMesh: ").split(", "), "the mesher's own status first")
        self.assertTrue(brepcheck.startswith("wire 1: SelfIntersectingWire"), brepcheck)
        drawn = {int(o): int(c) for o, _first, c in part.faces}
        self.assertEqual(drawn[7], 0, "the face is left out")
        self.assertTrue(all(drawn[o] > 0 for o in range(1, 7)), "the rest of the part is drawn")
        self.assertEqual(mesh.Mesh.from_bytes(part.to_bytes()).unmeshed.keys(), {7})


TURNED = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/turned.xbf")
def turned():
    return bd.Rot(0, 0, 33) * bd.Box(4, 3, 2) + bd.Rot(17, 29, 41) * bd.Cylinder(1, 3)
"""


class OneKeyOneMeshTest(unittest.TestCase):
    def test_a_part_meshes_alike_live_and_read_back_from_its_document(self) -> None:
        """A build's live part and the same part read back from its xbf -- what a daemon
        that never ran the build holds -- give the same bytes, so the same mesh. The part's
        sub-shape locations move by a last bit at every read of its bytes: its raw bytes
        live and read back differ, and so did its meshes."""
        from cadgen.engine import document

        folder = Path(tempfile.mkdtemp(prefix="engine-mesh-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / "turned.py"
        script.write_text(textwrap.dedent(TURNED), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["turned"], cwd=folder)[-1]["ok"])
        live = document.saved(folder / "XBF/turned.xbf").parts[0]
        read = document.Loaded(folder / "XBF/turned.xbf").prototypes[0]
        self.assertEqual(live.key, read.key)
        data = mesh.shape_bytes(live.shape)
        self.assertEqual(data, mesh.shape_bytes(read.shape, read=True))
        self.assertEqual(mesh.mesh_shape(live.shape).to_bytes(), mesh.mesh_shape(mesh.shape_bytes(read.shape, read=True)).to_bytes())


MODEL = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/plate.xbf")
def plate():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((0, 0), (1, 1), (1, 0), (0, 1)):
        polygon.Add(gp_Pnt(x + 5, y, 0))
    polygon.Close()
    crossed = bd.Face(BRepBuilderAPI_MakeFace(polygon.Wire(), True).Face())
    return bd.Compound([bd.Box(1, 2, 3), crossed], label="plate")
"""


class FactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-mesh-")).resolve()
        script = cls.folder / "plate.py"
        script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
        reports = engine_build.build(script, ["plate"], cwd=cls.folder)
        assert reports[-1]["ok"], reports
        cls.server = Server(port=0, mesh_mode="inline")
        cls.server.start()
        cls.ident = cls.server.add(cls.folder / "XBF/plate.xbf")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def get(self, path: str) -> bytes:
        with urllib.request.urlopen(self.server.url + path, timeout=120) as response:
            return response.read()

    def test_the_structure_names_the_unmeshed_face_and_why(self) -> None:
        key = json.loads(self.get(f"/api/doc/{self.ident}"))["prototypes"][0]["key"]
        self.get(f"/api/doc/{self.ident}/part/{key}")
        prototype = json.loads(self.get(f"/api/doc/{self.ident}"))["prototypes"][0]
        self.assertEqual(prototype["unmeshed"], [7])
        self.assertRegex(prototype["unmeshedCheck"]["7"], r"^BRepMesh: [^;]*SelfIntersectingWire[^;]*; BRepCheck: ")
        face = json.loads(self.get(f"/api/doc/{self.ident}/part/{key}/face/7"))
        self.assertFalse(face["meshed"])
        self.assertIn("SelfIntersectingWire", face["check"])

    def test_facts_are_measured_on_request(self) -> None:
        key = json.loads(self.get(f"/api/doc/{self.ident}"))["prototypes"][0]["key"]
        part = mesh.Mesh.from_bytes(self.get(f"/api/doc/{self.ident}/part/{key}"))
        faces = [json.loads(self.get(f"/api/doc/{self.ident}/part/{key}/face/{o}")) for o in range(1, 7)]
        self.assertEqual(sorted(round(f["area"], 9) for f in faces), [2.0, 2.0, 3.0, 3.0, 6.0, 6.0])
        self.assertEqual({f["surface"] for f in faces}, {"plane"})
        self.assertTrue(all(f["check"] == "valid" and f["meshed"] for f in faces))
        first = faces[0]
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(first["centroid"], np.mean(
            [first["box"]["min"], first["box"]["max"]], axis=0))))
        edges = [json.loads(self.get(f"/api/doc/{self.ident}/part/{key}/edge/{o}")) for o in range(1, 13)]
        self.assertEqual(sorted(round(e["length"], 9) for e in edges), [1.0] * 4 + [2.0] * 4 + [3.0] * 4)
        self.assertEqual({(e["curve"], e["class"]) for e in edges}, {("line", "feature")})
        for edge in edges:
            start, end = np.array(edge["endpoints"])
            self.assertAlmostEqual(float(np.linalg.norm(end - start)), edge["length"], places=9)
        # The vertex table and the kernel agree on where every vertex is.
        for ordinal, x, y, z in part.vertices[:8]:
            vertex = json.loads(self.get(f"/api/doc/{self.ident}/part/{key}/vertex/{int(ordinal)}"))
            self.assertTrue(np.allclose(vertex["position"], [x, y, z], atol=1e-6))
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self.get(f"/api/doc/{self.ident}/part/{key}/edge/999")
        self.assertEqual(missing.exception.code, 404)


SOLIDS = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/solids.xbf")
def solids():
    parts = []
    for at, (label, shape) in enumerate((("cylinder", bd.Cylinder(1, 2)), ("sphere", bd.Sphere(2)),
                                         ("torus", bd.Torus(5, 1)), ("cone", bd.Cone(2, 1, 3)))):
        placed = bd.Pos(20 * at, 0, 0) * shape
        placed.label = label
        parts.append(placed)
    return bd.Compound(children=parts, label="solids")
"""


class SurfaceFactsTest(unittest.TestCase):
    """Every surface type answers its facts: a face closed on itself by a seam too."""

    def test_every_face_of_curved_solids_answers_its_facts(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="engine-mesh-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / "solids.py"
        script.write_text(textwrap.dedent(SOLIDS), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["solids"], cwd=folder)[-1]["ok"])
        server = Server(port=0, mesh_mode="inline")
        server.start()
        self.addCleanup(server.stop)
        ident = server.add(folder / "XBF/solids.xbf")

        def get(path: str) -> dict:
            with urllib.request.urlopen(server.url + path, timeout=120) as response:
                return json.loads(response.read())

        expected = {"cylinder": {"cylinder": 4 * math.pi, "plane": math.pi}, "sphere": {"sphere": 16 * math.pi},
                    "torus": {"torus": 20 * math.pi ** 2}, "cone": {"cone": None, "plane": None}}
        found = {}
        for prototype in get(f"/api/doc/{ident}")["prototypes"]:
            faces = [get(f"/api/doc/{ident}/part/{prototype['key']}/face/{o}") for o in range(1, 4)
                     if o <= {"cylinder": 3, "sphere": 1, "torus": 1, "cone": 3}[prototype["name"]]]
            for face in faces:
                self.assertEqual(face["check"], "valid", face)
                self.assertGreater(face["area"], 0)
                self.assertEqual(len(face["centroid"]), 3)
                self.assertEqual(len(face["box"]["min"]), 3)
                area = expected[prototype["name"]][face["surface"]]
                if area is not None:
                    self.assertAlmostEqual(face["area"], area, places=6)
                # A round face's radii, which its card reads.
                radii = {"cylinder": {"radius": 1}, "sphere": {"radius": 2}, "torus": {"majorRadius": 5, "minorRadius": 1}}
                for name, value in radii.get(face["surface"], {}).items():
                    self.assertAlmostEqual(face[name], value, places=6)
            if prototype["name"] == "cylinder":
                circles = [get(f"/api/doc/{ident}/part/{prototype['key']}/edge/{o}") for o in range(1, 4)]
                circles = [edge for edge in circles if edge["curve"] == "circle"]
                self.assertEqual(len(circles), 2)
                for edge in circles:
                    self.assertAlmostEqual(edge["radius"], 1, places=6)
                    self.assertAlmostEqual(edge["sweepRadians"], 2 * math.pi, places=6)
                groups = get(f"/api/doc/{ident}/part/{prototype['key']}/groups")
                self.assertEqual(set(groups), {"faces", "edges"})
                self.assertEqual(len(groups["faces"]), 3)
            found[prototype["name"]] = sorted({face["surface"] for face in faces})
        self.assertEqual(found, {"cylinder": ["cylinder", "plane"], "sphere": ["sphere"], "torus": ["torus"],
                                 "cone": ["cone", "plane"]})


if __name__ == "__main__":
    unittest.main()
