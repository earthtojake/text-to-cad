"""cadgen's mesher on what an ordinary part is not, and the STL cut from it.

A component of one vertex, a failure inside OCCT, a face OCCT's pass leaves
empty -- meshed again whole, or refused and tessellated over its own parameters --,
the singular points of a cone or a sphere, a free edge or vertex beside a solid, a
mirrored placement inside a component: each once broke a mesh, the export cut
from it or the view drawing it. Shapes are built here; meshing needs no store,
except where a whole tree is meshed. OCCT refuses a face for what a real model's
booleans leave in it, and a shape small enough to build here leaves nothing it
refuses, so a test that needs a refusal makes OCCT refuse.
"""

from __future__ import annotations

import collections
import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
# The module, not its test class: imported, the class would run here as well.
from tests.python.packages.cadgen import test_mesh_export_manifold as exported  # noqa: E402
from tests.python.support.tmp_root import generated_cad_directory  # noqa: E402

CHORD, ANGLE = 1.5e-3, 0.35
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _surf_index(topods) -> dict:
    from cadgen._internal.surf_container import read_surf
    from cadgen._internal.surface_extract import extract_surface_component

    return read_surf(extract_surface_component(topods))[0]


def _mesh(shape):
    """``shape`` meshed as the store meshes a component: its GLB body, decoded."""
    from cadgen._internal.mesh_formats import decode_tessellation
    from cadgen._internal.occt_mesh import mesh_component

    topods = getattr(shape, "wrapped", shape)
    body = mesh_component(topods, _surf_index(topods), surface_input="1" * 64, surface_object="a" * 64,
                          chord=CHORD, angle=ANGLE)
    return body, decode_tessellation(body)


def _compound(*shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    compound, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, getattr(shape, "wrapped", shape))
    return compound


def _corners(tessellation) -> np.ndarray:
    return tessellation.positions[tessellation.indices].reshape(-1, 3, 3).astype(np.float64)


def _collapsed(corners: np.ndarray) -> np.ndarray:
    """Triangles two of whose corners are one point."""
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    return (a == b).all(axis=1) | (b == c).all(axis=1) | (c == a).all(axis=1)


def _open_edges(tessellation) -> int:
    """Edges one triangle uses once the mesh is welded by exact position, as a slicer welds it."""
    edges: collections.Counter = collections.Counter()
    corners = _corners(tessellation)
    for triangle in corners[~_collapsed(corners)]:
        points = [tuple(point) for point in triangle]
        for a, b in ((points[0], points[1]), (points[1], points[2]), (points[2], points[0])):
            edges[(a, b) if a < b else (b, a)] += 1
    return sum(1 for used in edges.values() if used == 1)


class DegenerateComponents(unittest.TestCase):
    def test_a_component_of_one_vertex_meshes_to_nothing(self):
        from build123d import Vertex

        _body, mesh = _mesh(_compound(Vertex(10, 0, 0)))
        self.assertEqual((len(mesh.positions), len(mesh.indices), mesh.face_ranges), (0, 0, []))

    def test_a_failure_inside_occt_is_the_components_mesh_error(self):
        from build123d import Box
        from OCP import BRepMesh
        from OCP.Standard import Standard_ConstructionError

        from cadgen._internal.occt_mesh import MeshProductionError

        # Not a Standard_Failure in every OCP wheel: OCCT's own all the same.
        failing = mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh",
                                    side_effect=Standard_ConstructionError("no mesh"))
        with failing, self.assertRaisesRegex(MeshProductionError, r"Standard_ConstructionError: no mesh"):
            _mesh(Box(4, 4, 4))
        # A failure that is not OCCT's is not dressed up as one.
        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=KeyError("bug")), \
                self.assertRaises(KeyError):
            _mesh(Box(4, 4, 4))

    def test_a_tree_with_a_lone_vertex_meshes_every_component(self):
        from build123d import Box, Compound, Cylinder, Pos, Vertex

        from cadgen.store import meshes, surfaces
        from cadgen.store.build import build_tree_from_compound

        with generated_cad_directory(prefix="occt-mesh-vertex-") as temporary, \
                mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(temporary) / "cache")}):
            tree, geometry, _ = build_tree_from_compound(
                Compound(children=[Box(4, 4, 4), Vertex(10, 0, 0), Pos(20, 0, 0) * Cylinder(2, 4)]), root_name="trio")
            producer = surfaces.producer_identity()
            surfaces.derive(tree, producer=producer, tessellations=[{"chordTolerance": CHORD, "angleTolerance": ANGLE}])
            stored = [meshes.probe(meshes.tessellation_key(surfaces.lookup(entry, producer)["surfaceInput"], CHORD, ANGLE))
                      is not None for entry in geometry["components"].values()]
        self.assertEqual(stored, [True, True, True])


class StlAtSingularPoints(unittest.TestCase):
    def test_an_stl_of_poles_and_apexes_is_manifold_and_watertight(self):
        import trimesh
        from build123d import Box, Cone, Pos, Sphere, fillet

        from cadgen._internal.mesh_formats import build_primitives, stl_bytes

        parts = {
            "fully filleted box": fillet(Box(20, 20, 20).edges(), 3),
            "sphere beside a cone": _compound(Sphere(6), Pos(20, 0, 0) * Cone(5, 0, 10)),
        }
        descriptor = {"components": {"c": {}}, "occurrences": [{"id": "o1", "component": "c", "transform": IDENTITY}]}
        with generated_cad_directory(prefix="occt-mesh-stl-") as temporary:
            for label, shape in parts.items():
                with self.subTest(label):
                    _body, mesh = _mesh(shape)
                    # The case is still the case: OCCT's mesh, as stored, has them.
                    self.assertTrue(_collapsed(_corners(mesh)).any(), "the stored mesh has collapsed triangles")
                    path = Path(temporary) / f"{label}.stl"
                    path.write_bytes(stl_bytes(build_primitives(descriptor, {"c": mesh})))
                    exported.MeshExportManifoldTest.assertManifold(self, path, label)
                    self.assertTrue(trimesh.load(path).is_watertight)


def _range_area(mesh, ordinal: int) -> float:
    row = next(row for row in mesh.face_ranges if row["ord"] == ordinal)
    corners = mesh.positions[mesh.indices[row["indexStart"]:row["indexStart"] + row["indexCount"]]]
    a, b, c = (corners.reshape(-1, 3, 3).astype(np.float64)[:, k] for k in range(3))
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


class EmptyFace(unittest.TestCase):
    """OCCT's pass leaves the bore of a plate empty: the bore is meshed all the same."""

    def setUp(self):
        from build123d import Box, Cylinder
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        self.topods = (Box(20, 20, 10) - Cylinder(4, 10)).wrapped
        self.bore = next(row["ord"] for row in _surf_index(self.topods)["faces"] if row["surfaceType"] == "cylinder")
        self.faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.topods, TopAbs_FACE, self.faces)

    def mesh(self, refuses):
        """Mesh the plate while OCCT leaves its bore empty after each call ``refuses``
        names (the shape it was asked to mesh, and the call's number)."""
        from OCP import BRepMesh
        from OCP.BRepTools import BRepTools

        real, self.meshed = BRepMesh.BRepMesh_IncrementalMesh, []

        def mesher(shape, *args):
            result = real(shape, *args)
            self.meshed.append(shape)
            if refuses(shape, len(self.meshed)):
                BRepTools.Clean_s(self.faces.FindKey(self.bore))
            return result

        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=mesher):
            return _mesh(self.topods)[1]

    def assertBoreMeshed(self, mesh):
        """The bore's range holds triangles, and they lie on the bore: radius 4 about z."""
        bore = next(row for row in mesh.face_ranges if row["ord"] == self.bore)
        self.assertGreater(bore["indexCount"], 0)
        corners = mesh.positions[mesh.indices[bore["indexStart"]:bore["indexStart"] + bore["indexCount"]]]
        np.testing.assert_allclose(np.hypot(corners[:, 0], corners[:, 1]), 4.0, atol=0.05)

    def test_a_face_the_pass_leaves_empty_is_meshed_with_its_whole_component_and_no_crack(self):
        mesh = self.mesh(lambda shape, call: call == 1)
        self.assertGreater(len(self.meshed), 1, "the component was meshed again")
        self.assertTrue(all(shape.IsSame(self.topods) for shape in self.meshed), "always the whole component")
        self.assertBoreMeshed(mesh)
        self.assertEqual(_open_edges(mesh), 0, "the bore meets its neighbours along every edge")

    def test_a_face_no_whole_pass_meshes_is_tessellated_over_its_parameters_and_meets_its_neighbours(self):
        # OCCT refuses the bore whenever it meshes the component, as it refused radial's
        # accessory case, the hand's fingertip pad and the RoArm's screw tips.
        mesh = self.mesh(lambda shape, call: shape.IsSame(self.topods))
        self.assertTrue(all(shape.IsSame(self.topods) for shape in self.meshed), "OCCT never meshed it alone")
        self.assertBoreMeshed(mesh)
        self.assertAlmostEqual(_range_area(mesh, self.bore), 2 * np.pi * 4 * 10, delta=2 * np.pi * 4 * 10 * 0.02,
                               msg="the bore's own area, a 4 mm radius 10 deep")
        self.assertEqual(_open_edges(mesh), 0, "the bore shares every vertex with the faces around it")

    def test_a_tessellation_that_misses_the_faces_area_is_not_kept(self):
        from cadgen._internal import face_fallback
        from cadgen._internal.occt_mesh import MeshProductionError

        real = face_fallback.tessellate_face

        def overcounted(*args):
            triangulation, covered = real(*args)
            return triangulation, covered * 2

        with mock.patch.object(face_fallback, "tessellate_face", side_effect=overcounted), \
                self.assertRaisesRegex(MeshProductionError, rf"did not mesh 1 face\(s\) of the component: f{self.bore}\b"):
            self.mesh(lambda shape, call: shape.IsSame(self.topods))


def _with_a_stray_degenerated_edge(topods):
    """``topods`` with a zero-length (degenerated) edge put into its first face's boundary at
    a corner, where the face is not pinched -- what the booleans left where a slot cuts the
    fillet of radial's accessory case -- and that face."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve2d
    from OCP.BRepTools import BRepTools_ReShape
    from OCP.Geom2d import Geom2d_Line
    from OCP.gp import gp_Dir2d
    from OCP.TopAbs import TopAbs_FACE, TopAbs_FORWARD, TopAbs_REVERSED
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Edge, TopoDS_Iterator, TopoDS_Wire

    face = TopoDS.Face_s(TopExp_Explorer(topods, TopAbs_FACE).Current())
    edges, iterator = [], TopoDS_Iterator(TopoDS_Iterator(face).Value())
    while iterator.More():
        edges.append(TopoDS.Edge_s(iterator.Value()))
        iterator.Next()
    curve = BRepAdaptor_Curve2d(edges[0], face)
    corner = curve.Value(curve.FirstParameter() if edges[0].Orientation() == TopAbs_FORWARD else curve.LastParameter())
    vertex = TopExp.FirstVertex_s(edges[0], True)
    builder, stray, wire = BRep_Builder(), TopoDS_Edge(), TopoDS_Wire()
    builder.MakeEdge(stray)
    builder.UpdateEdge(stray, Geom2d_Line(corner, gp_Dir2d(1, 0)), face, 1e-7)
    builder.Range(stray, face, 0.0, 0.0)
    builder.Degenerated(stray, True)
    builder.Add(stray, vertex.Oriented(TopAbs_FORWARD))
    builder.Add(stray, vertex.Oriented(TopAbs_REVERSED))
    builder.MakeWire(wire)
    for edge in [stray, *edges]:
        builder.Add(wire, edge)
    strayed = TopoDS.Face_s(face.EmptyCopied())
    builder.Add(strayed, wire)
    reshape = BRepTools_ReShape()
    reshape.Replace(face, strayed)
    return reshape.Apply(topods), strayed


class RefusedFace(unittest.TestCase):
    """A face OCCT is made to refuse, whole or alone, is drawn over its own parameters: a
    zero-length edge where the face is not pinched (radial's accessory case), a sphere's
    poles, a cone's tip (the RoArm's screws) -- on its surface, closed, and joined to its
    neighbours."""

    def mesh(self, topods, face):
        from OCP import BRepMesh
        from OCP.BRep import BRep_Builder

        real = BRepMesh.BRepMesh_IncrementalMesh

        def mesher(shape, *args):
            result = real(shape, *args)
            if shape.IsSame(topods) or shape.IsSame(face):
                BRep_Builder().UpdateFace(face, None)
            return result

        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=mesher):
            return _mesh(topods)[1]

    def assertDrawn(self, topods, face, area, what):
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
        mesh = self.mesh(topods, face)
        self.assertAlmostEqual(_range_area(mesh, faces.FindIndex(face)), area, delta=area * 0.02, msg=what)
        self.assertEqual(_open_edges(mesh), 0, "the face shares every vertex with the faces around it")

    def test_a_face_with_a_stray_zero_length_edge(self):
        from build123d import Box

        topods, face = _with_a_stray_degenerated_edge(Box(20, 20, 10).wrapped)
        self.assertDrawn(topods, face, 200.0, "a 20 x 10 side")

    def test_a_sphere_closed_at_its_poles(self):
        from build123d import Sphere
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        topods = Sphere(10).wrapped
        self.assertDrawn(topods, TopoDS.Face_s(TopExp_Explorer(topods, TopAbs_FACE).Current()),
                         4 * np.pi * 10 ** 2, "a 10 mm sphere")

    def test_a_cone_to_its_tip(self):
        from build123d import Cone
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cone
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        topods = Cone(4, 0, 6).wrapped
        explorer = TopExp_Explorer(topods, TopAbs_FACE)
        while BRepAdaptor_Surface(TopoDS.Face_s(explorer.Current())).GetType() != GeomAbs_Cone:
            explorer.Next()
        self.assertDrawn(topods, TopoDS.Face_s(explorer.Current()), np.pi * 4 * np.hypot(4, 6), "a 4 mm cone 6 tall")


class NarrowFace(unittest.TestCase):
    """A face narrower than the deflection: one of the f14d wing's slivers, 686 mm long and
    1.2 mm wide on average, between a straight side and a curve its neighbour meshes as one
    chord -- a chord that passes beyond the straight side, so the boundary crosses itself.
    OCCT refuses it; drawn over its parameters, it covers its own area and meets its
    neighbours, where it once covered twice its area and failed the component."""

    # The sliver's outline on its plane (mm): its straight side's corners, and points
    # along its curved side, which a spline through them follows.
    SIDE = [(5.681, 0.216), (147.532, 5.619), (365.14, 18.003), (690.28, 43.929)]
    CURVE = [(690.28, 43.929), (604.868, 36.196), (519.411, 28.977), (433.91, 22.306), (348.366, 16.212),
             (262.78, 10.734), (177.155, 5.915), (91.492, 1.806), (5.797, -1.534)]

    def test_a_sliver_beside_a_coarse_chord_covers_its_own_area_and_meets_its_neighbours(self):
        from build123d import Box, Line, Polyline, Pos, Spline, Wire, extrude, make_face
        from OCP import BRepMesh
        from OCP.BRep import BRep_Builder
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopoDS import TopoDS, TopoDS_Compound

        outline = Wire([*Polyline(*self.SIDE).edges(), Spline(*self.CURVE), Line(self.CURVE[-1], self.SIDE[0])])
        plate = extrude(make_face(outline), 2)
        # A plate in a component as large as the wing, so the deflection is ten times its width.
        topods = _compound(plate, Pos(8000, 0, 0) * Box(10, 10, 10))
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
        slivers = [faces.FindIndex(face.wrapped) for face in plate.faces() if abs(face.normal_at().Z) > 0.99]
        self.assertEqual(len(slivers), 2)
        # OCCT meshes everything but the slivers -- which it refuses at this deflection and,
        # finer, draws with a twentieth of their area.
        others, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(others)
        for ordinal in range(1, faces.Extent() + 1):
            if ordinal not in slivers:
                builder.Add(others, faces.FindKey(ordinal))
        real = BRepMesh.BRepMesh_IncrementalMesh
        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=lambda _shape, *args: real(others, *args)):
            mesh = _mesh(topods)[1]
        for ordinal in slivers:
            exact = GProp_GProps()
            BRepGProp.SurfaceProperties_s(TopoDS.Face_s(faces.FindKey(ordinal)), exact)
            self.assertAlmostEqual(_range_area(mesh, ordinal), exact.Mass(), delta=exact.Mass() * 0.02,
                                   msg=f"f{ordinal} covers its own area")
        self.assertFalse(np.isnan(mesh.positions).any() or np.isnan(mesh.normals).any())
        self.assertEqual(_open_edges(mesh), 0, "the slivers share every vertex with the faces around them")


class Normals(unittest.TestCase):
    def test_no_normal_points_into_the_solid_at_a_cones_apex(self):
        from build123d import Cone

        for label, cone in (("apex up", Cone(5, 0, 10)), ("apex down", Cone(0, 5, 10))):
            with self.subTest(label):
                _body, mesh = _mesh(cone)
                corners = _corners(mesh)
                facets = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
                lengths = np.linalg.norm(facets, axis=1)
                covering = lengths > 0
                facets = facets[covering] / lengths[covering, None]
                normals = mesh.normals[mesh.indices.reshape(-1, 3)[covering]].astype(np.float64)
                self.assertGreater(float(np.einsum("tj,tkj->tk", facets, normals).min()), 0.0)

    def test_the_writers_reading_and_the_face_by_face_one_are_the_same_bytes(self):
        from build123d import Cone, Sphere

        from cadgen._internal import occt_mesh

        for label, shape in (("cone", lambda: Cone(5, 0, 10)), ("sphere", lambda: Sphere(6))):
            with self.subTest(label):
                written, _ = _mesh(shape())
                with mock.patch.object(occt_mesh, "_faces_from_gltf", return_value=None):
                    read, _ = _mesh(shape())
                self.assertEqual(written, read)


class LooseGeometry(unittest.TestCase):
    def test_a_free_edge_or_vertex_beside_a_solid_keeps_the_writers_path(self):
        from build123d import Box, Edge, Vertex

        from cadgen._internal import occt_mesh

        for label, loose in (("edge", Edge.make_line((10, 0, 0), (20, 0, 0))), ("vertex", Vertex(10, 0, 0))):
            with self.subTest(label), mock.patch.object(
                    occt_mesh, "_faces_one_by_one", wraps=occt_mesh._faces_one_by_one) as one_by_one:
                _body, mesh = _mesh(_compound(Box(5, 5, 5), loose))
                one_by_one.assert_not_called()
                self.assertEqual(len(mesh.indices) // 3, 12)

    def test_a_mirrored_placement_read_face_by_face_still_faces_outward(self):
        from build123d import Box
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

        from cadgen._internal import occt_mesh

        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(50, 0, 0), gp_Dir(1, 0, 0)))
        mirrored = Box(10, 10, 10).wrapped.Moved(TopLoc_Location(mirror), False)
        with mock.patch.object(occt_mesh, "_faces_from_gltf", return_value=None):
            _body, mesh = _mesh(_compound(mirrored))
        corners = _corners(mesh)
        volume = np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])).sum() / 6
        self.assertAlmostEqual(float(volume), 1000.0, places=3)


if __name__ == "__main__":
    unittest.main()
