"""cadgen's mesher on what an ordinary part is not, and the STL cut from it.

A component of one vertex, a failure inside OCCT, a face OCCT's pass leaves
empty -- meshed again whole, refused and tessellated over its own parameters, or
left empty when it is smaller than the mesh resolves --, the singular points of a
cone or a sphere, a free edge or vertex beside a solid, a mirrored placement inside
a component: each once broke a mesh, the export cut from it or the view drawing it.
Shapes are built here; meshing needs no store, except where a whole tree is meshed.
OCCT refuses a face for what a real model's booleans leave in it, and a shape small
enough to build here leaves nothing it refuses, so a test that needs a refusal makes
OCCT refuse.
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
PART = "1" * 64 + "-v1"
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _facts(topods) -> dict:
    from cadgen._internal.topology_extract import extract_topology_facts

    return extract_topology_facts(topods)


def _mesh(shape, *, chord=CHORD, angle=ANGLE, facts=None):
    """``shape`` meshed as the store meshes a component, from its topology facts (``facts``
    when given): its GLB body, decoded."""
    from cadgen._internal.mesh_formats import decode_tessellation
    from cadgen._internal.tessellate import mesh_component

    topods = getattr(shape, "wrapped", shape)
    facts = _facts(topods) if facts is None else facts
    body = mesh_component(topods, facts, {}, part=PART, chord=chord, angle=angle).body
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

        from cadgen._internal.tessellate import MeshProductionError

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

        from cadgen.store import parts
        from cadgen.store.build import build_tree_from_compound

        with generated_cad_directory(prefix="occt-mesh-vertex-") as temporary, \
                mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(temporary) / "cache")}):
            tree, geometry, _ = build_tree_from_compound(
                Compound(children=[Box(4, 4, 4), Vertex(10, 0, 0), Pos(20, 0, 0) * Cylinder(2, 4)]), root_name="trio")
            producer = parts.producer_identity()
            parts.derive(tree, producer=producer)
            stored = [parts.probe(parts.part_key(entry, producer)) is not None
                      for entry in geometry["components"].values()]
        self.assertEqual(stored, [True, True, True])


class AtTheFloors(unittest.TestCase):
    def test_a_face_curved_all_the_way_round_meshes_at_the_finest_tolerances_accepted(self):
        # Below the floors one such face meshed for minutes (cadgen.tessellation_policy);
        # at them, it is a mesh, closed, and finer than the standard rung's.
        from build123d import Sphere

        from cadgen.tessellation_policy import TESSELLATION_FLOORS

        _body, standard = _mesh(Sphere(5))
        _body, finest = _mesh(Sphere(5), chord=TESSELLATION_FLOORS["chordTolerance"],
                              angle=TESSELLATION_FLOORS["angleTolerance"])
        self.assertGreater(len(finest.indices), 10 * len(standard.indices))
        self.assertEqual(0, _open_edges(finest))


class OnTheSurface(unittest.TestCase):
    def test_a_thin_round_swept_along_an_arc_stays_within_its_deflection(self):
        """The motorbike's front fender: a band of rounded section revolved through 120 degrees,
        its 4 mm corners swept along a 230 mm arc. OCCT measures its triangles against the surface
        only on freeform faces unless told to on every face, and at this band's display deflection
        its grid on a toroidal corner skipped the corner's inner rows: triangles spanning the whole
        corner sat 1.2 mm off it, five times the deflection, and every view drew a saw-toothed edge."""
        import math

        from build123d import Axis, Plane, Pos, RectangleRounded, revolve
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        from cadgen._internal.tessellate import _bounding_diagonal
        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        start = math.radians(30)
        axle = (595.0, 0.0, 205.0)
        plane = Plane(origin=axle, x_dir=(math.cos(start), 0, math.sin(start)), z_dir=(-math.sin(start), 0, math.cos(start)))
        band = revolve((Pos(228, 0, 0) * RectangleRounded(12, 92, 4)).moved(plane.location),
                       Axis(axle, (0, -1, 0)), revolution_arc=120)
        chord, angle = DISPLAY_TESSELLATION["chordTolerance"], DISPLAY_TESSELLATION["angleTolerance"]
        _mesh(band, chord=chord, angle=angle)  # meshing leaves its triangulation on the shape
        deflection = chord * _bounding_diagonal(band.wrapped)
        # Each triangle's centre against the surface at its centre's parameters: a triangle across
        # a corner it should have stepped round sits that corner's sag off it.
        worst = 0.0
        explorer = TopExp_Explorer(band.wrapped, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            explorer.Next()
            surface = BRepAdaptor_Surface(face, False)
            if surface.GetType() == GeomAbs_Plane:
                continue
            triangulation = BRep_Tool.Triangulation_s(face, TopLoc_Location())
            for index in range(1, triangulation.NbTriangles() + 1):
                nodes = triangulation.Triangle(index).Get()
                u = sum(triangulation.UVNode(node).X() for node in nodes) / 3
                v = sum(triangulation.UVNode(node).Y() for node in nodes) / 3
                a, b, c = (triangulation.Node(node).XYZ() for node in nodes)
                worst = max(worst, surface.Value(u, v).Distance(gp_Pnt((a + b + c).Divided(3))))
        self.assertLess(worst, 2 * deflection, f"{worst:.3f} mm off the surface at a {deflection:.3f} mm deflection")

    def test_a_part_far_from_its_origin_is_not_meshed_again_for_its_rounding(self):
        """Faces are measured on the single-precision positions the mesh is read in. A 10 mm
        part built a kilometre from its origin rounds them by up to 0.06 mm, several times its
        deflection, which no finer pass changes: held to its deflection alone, every round of
        it counted as off its surface, and it was meshed four times and its rounds tessellated
        over their parameters, cracked where they met their neighbours."""
        from build123d import Box, Cylinder, fillet
        from OCP import BRepMesh
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf, gp_Vec
        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        shift = gp_Trsf()
        shift.SetTranslation(gp_Vec(1e6, 0, 0))
        far = BRepBuilderAPI_Transform((fillet(Box(10, 10, 10).edges(), radius=2) - Cylinder(2, 20)).wrapped,
                                       shift, True).Shape()
        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", wraps=BRepMesh.BRepMesh_IncrementalMesh) as mesher:
            _mesh(far, chord=DISPLAY_TESSELLATION["chordTolerance"], angle=DISPLAY_TESSELLATION["angleTolerance"])
        self.assertEqual(mesher.call_count, 1)

    def test_a_tessellation_that_would_open_the_part_is_undone(self):
        """A round no finer pass meshes on its surface goes to the tessellator, whose points
        along a shared edge split its neighbours' triangles to meet them. Where that fails the
        faces part, and the round keeps OCCT's triangles: off its surface, but closed. Here no
        neighbour is split at all."""
        from build123d import Axis, Pos, RectangleRounded, revolve
        from cadgen._internal import face_fallback
        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        band = revolve(Pos(230, 0, 0) * RectangleRounded(8, 24, 1), Axis.Y, revolution_arc=360)
        with mock.patch.object(face_fallback, "_conform_neighbours", return_value=lambda: None) as conform:
            _body, mesh = _mesh(band, chord=DISPLAY_TESSELLATION["chordTolerance"] / 10,
                                angle=DISPLAY_TESSELLATION["angleTolerance"])
        self.assertTrue(conform.called, "a round went to the tessellator")
        self.assertEqual(_open_edges(mesh), 0)


class FreeformSurfaces(unittest.TestCase):
    """OCCT holds a freeform face's triangles to the deflection as it meshes it, but on some
    B-splines -- an F1 floor panel, the hand's palm, a Juno forearm -- it left them up to 48
    times off, where main's tessellator held them. A cylinder's side as a B-spline, meshed ten
    times coarser than it is measured, stands in for such a face."""

    def setUp(self):
        from build123d import Cylinder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
        from cadgen._internal import tessellate

        self.topods = BRepBuilderAPI_NurbsConvert(Cylinder(10, 20).wrapped, True).Shape()
        self.face_map, _edges = tessellate._maps(self.topods)
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        facts = _facts(self.topods)
        self.kinds = {face["ord"]: face["surfaceType"] for face in facts["faces"]}

        def area(ordinal):
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(self.face_map.FindKey(ordinal), props)
            return props.Mass()

        # Every face is a B-spline now; the side is the largest, and the one that is curved.
        self.side = max(self.kinds, key=area)
        self.assertEqual(self.kinds[self.side], "bsplinesurface")

    def faulty(self, meshed_at, freeform=True):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepTools import BRepTools
        from cadgen._internal import tessellate

        BRepTools.Clean_s(self.topods)
        BRepMesh_IncrementalMesh(self.topods, meshed_at, False, 0.8, True)
        faces = tessellate._read_faces(self.topods, self.face_map)
        return tessellate._faulty(faces, self.face_map, list(faces), self.kinds, 0.05, False, freeform)

    def test_a_freeform_face_meshed_coarser_than_it_is_held_to_is_off_its_surface(self):
        self.assertIn(self.side, self.faulty(meshed_at=0.5))

    def test_a_freeform_face_meshed_at_its_deflection_is_not(self):
        self.assertEqual(self.faulty(meshed_at=0.05), [])

    def test_a_component_whose_first_pass_is_slow_goes_unmeasured(self):
        self.assertEqual(self.faulty(meshed_at=0.5, freeform=False), [])
        from cadgen._internal import tessellate

        with mock.patch.object(tessellate, "_RETRY_SECONDS", -1.0), \
                mock.patch.object(tessellate, "_freeform_distance", wraps=tessellate._freeform_distance) as measured:
            _mesh(self.topods)
        self.assertFalse(measured.called)
        with mock.patch.object(tessellate, "_freeform_distance", wraps=tessellate._freeform_distance) as measured:
            _mesh(self.topods)
        self.assertTrue(measured.called)


class ExportAtSingularPoints(unittest.TestCase):
    def test_an_export_of_poles_and_apexes_is_manifold_and_watertight_in_every_format(self):
        import trimesh
        from build123d import Box, Cone, Pos, Sphere, fillet

        from cadgen._internal.mesh_formats import build_primitives, glb_bytes, stl_bytes, threemf_bytes

        parts = {
            "fully filleted box": fillet(Box(20, 20, 20).edges(), 3),
            "sphere beside a cone": _compound(Sphere(6), Pos(20, 0, 0) * Cone(5, 0, 10)),
        }
        descriptor = {"components": {"c": {}}, "occurrences": [{"id": "o1", "component": "c", "transform": IDENTITY}]}
        with generated_cad_directory(prefix="occt-mesh-export-") as temporary:
            for label, shape in parts.items():
                _body, mesh = _mesh(shape)
                # The case is still the case: OCCT's mesh, as stored, has them.
                self.assertTrue(_collapsed(_corners(mesh)).any(), "the stored mesh has collapsed triangles")
                primitives = build_primitives(descriptor, {"c": mesh})
                for fmt, write in (("stl", stl_bytes), ("glb", glb_bytes), ("3mf", threemf_bytes)):
                    with self.subTest(label, format=fmt):
                        path = Path(temporary) / f"{label}.{fmt}"
                        path.write_bytes(write(primitives))
                        if fmt == "stl":
                            exported.MeshExportManifoldTest.assertManifold(self, path, label)
                        # Read as the file says, then welded by exact position, as a slicer welds.
                        read = trimesh.load(path, force="mesh", process=False)
                        corners = np.asarray(read.vertices)[np.asarray(read.faces)]
                        self.assertFalse(_collapsed(corners).any(), f"{fmt} carries triangles that cover nothing")
                        read.merge_vertices(merge_tex=True, merge_norm=True)
                        self.assertTrue(read.is_watertight)


def _range_area(mesh, ordinal: int) -> float:
    row = next(row for row in mesh.face_ranges if row["ord"] == ordinal)
    corners = mesh.positions[mesh.indices[row["indexStart"]:row["indexStart"] + row["indexCount"]]]
    a, b, c = (corners.reshape(-1, 3, 3).astype(np.float64)[:, k] for k in range(3))
    return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())


class EmptyFace(unittest.TestCase):
    """OCCT's pass leaves the bore of a plate empty: the bore is meshed all the same,
    unless it is smaller than the mesh resolves."""

    def setUp(self):
        from build123d import Box, Cylinder
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        self.topods = (Box(20, 20, 10) - Cylinder(4, 10)).wrapped
        self.bore = next(row["ord"] for row in _facts(self.topods)["faces"] if row["surfaceType"] == "cylinder")
        self.faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.topods, TopAbs_FACE, self.faces)

    def mesh(self, refuses, facts=None):
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
            self.body, mesh = _mesh(self.topods, facts=facts)
        return mesh

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

    def test_a_tessellation_that_misses_the_faces_area_is_not_kept_and_splits_no_neighbour(self):
        from cadgen._internal import face_fallback
        from cadgen.store.meshes import decode_payload

        real = face_fallback.tessellate_face

        def overcounted(topods, face, deflection, angle, keep):
            return real(topods, face, deflection, angle, lambda covered: keep(covered * 2))

        with mock.patch.object(face_fallback, "tessellate_face", return_value=None):
            untessellated = self.mesh(lambda shape, call: shape.IsSame(self.topods))
        with mock.patch.object(face_fallback, "tessellate_face", side_effect=overcounted):
            mesh = self.mesh(lambda shape, call: shape.IsSame(self.topods))
        bore = next(row for row in mesh.face_ranges if row["ord"] == self.bore)
        self.assertEqual(bore["indexCount"], 0, "the bore is left out")
        self.assertEqual(decode_payload(self.body).unmeshed_faces, [self.bore], "and named")
        # Its neighbours were split to meet the triangles before they were refused, and kept
        # the splits: a vendor motor's two refused faces left 88 open edges around them.
        self.assertEqual([row["indexCount"] for row in mesh.face_ranges],
                         [row["indexCount"] for row in untessellated.face_ranges], "no neighbour was split")

    def test_the_tessellator_meets_the_pass_that_left_the_least_wrong(self):
        # A finer pass can close what the component's own deflection leaves: an actuator kept 32
        # open edges at a quarter of its deflection and 443 when it was meshed at its own again.
        from OCP import BRepMesh
        from cadgen._internal import tessellate

        real_mesher, real_faulty, deflections, calls = BRepMesh.BRepMesh_IncrementalMesh, tessellate._faulty, [], []

        def mesher(shape, deflection, *args):
            deflections.append(deflection)
            return real_mesher(shape, deflection, *args)

        def faulty(faces, face_map, required, *args):
            calls.append(None)
            real_faulty(faces, face_map, required, *args)
            # Two faces wrong at its own deflection and at a quarter, one at half.
            return [self.bore, 1][:1 if len(calls) == 2 else 2] if len(calls) <= 3 else []

        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=mesher), \
                mock.patch.object(tessellate, "_faulty", side_effect=faulty):
            _mesh(self.topods)
        self.assertEqual([round(d / deflections[0], 3) for d in deflections], [1.0, 0.5, 0.25, 0.5])

    def test_a_tessellation_that_would_fold_a_neighbour_out_is_refused_and_splits_none(self):
        # A point the tessellator lays on its boundary must be a point of the edge it shares:
        # one that is not, split into a neighbour, folded a vendor button's B-spline 399
        # deflections out. Here every point is taken to lie far from the edge.
        from cadgen._internal import face_fallback
        from cadgen.store.meshes import decode_payload

        with mock.patch.object(face_fallback, "tessellate_face", return_value=None):
            untessellated = self.mesh(lambda shape, call: shape.IsSame(self.topods))
        with mock.patch.object(face_fallback, "_off_segment", return_value=float("inf")):
            mesh = self.mesh(lambda shape, call: shape.IsSame(self.topods))
        self.assertEqual(decode_payload(self.body).unmeshed_faces, [self.bore], "the bore is left out and named")
        self.assertEqual([row["indexCount"] for row in mesh.face_ranges],
                         [row["indexCount"] for row in untessellated.face_ranges], "no neighbour was split")

    def test_a_tessellation_off_its_surface_is_undone(self):
        # The tessellator's triangles are measured as OCCT's are: a vendor nut's tessellated
        # face lay 25 deflections off. Here the bore is taken to lie off its surface however it
        # is meshed, so it goes to the tessellator, whose triangles are then undone.
        from cadgen._internal import face_fallback, tessellate

        real = tessellate._surface_distance

        def bore_off(surface, positions, triangles):
            from OCP.GeomAbs import GeomAbs_Cylinder

            return 1e9 if surface.GetType() == GeomAbs_Cylinder else real(surface, positions, triangles)

        with mock.patch.object(face_fallback, "tessellate_face", return_value=None):
            occt_only = self.mesh(lambda shape, call: False)
        with mock.patch.object(tessellate, "_surface_distance", side_effect=bore_off), \
                mock.patch.object(face_fallback, "tessellate_face", wraps=face_fallback.tessellate_face) as tessellator:
            mesh = self.mesh(lambda shape, call: False)
        self.assertTrue(tessellator.called, "the bore went to the tessellator")
        self.assertEqual([row["indexCount"] for row in mesh.face_ranges],
                         [row["indexCount"] for row in occt_only.face_ranges], "and kept OCCT's triangles")
        self.assertEqual(_open_edges(mesh), 0)

    def test_triangles_a_stored_brep_carries_are_not_kept(self):
        # A BREP can come with triangles some earlier tool made, which OCCT keeps where they are
        # fine enough for it, whatever they are: every component is meshed from none.
        from build123d import Sphere
        from OCP.BRepMesh import BRepMesh_IncrementalMesh

        fresh = _mesh(Sphere(5))[1].indices.size
        carried = Sphere(5)
        BRepMesh_IncrementalMesh(carried.wrapped, 0.001, False, 0.05, True)
        self.assertEqual(_mesh(carried)[1].indices.size, fresh)

    def test_a_component_whose_first_pass_is_slow_is_not_meshed_again_whole(self):
        # An F1 floor's B-spline took ten seconds to mesh once; with a faulty face, meshing it
        # again whole at half and a quarter of its deflection cost it four times over.
        from cadgen._internal import tessellate

        with mock.patch.object(tessellate, "_RETRY_SECONDS", -1.0):
            mesh = self.mesh(lambda shape, call: call == 1)
        self.assertEqual(len(self.meshed), 1, "one pass: the bore went straight to the tessellator")
        self.assertBoreMeshed(mesh)
        self.assertEqual(_open_edges(mesh), 0, "the bore meets its neighbours along every edge")

    def test_a_face_the_pass_leaves_a_gap_in_is_meshed_again(self):
        # OCCT leaves part of a face uncovered now and then -- a sixth of the radial engine's
        # cylinder head around a B-spline's pole -- and a gap inside a face drew as a hole. Here
        # the plate's largest face loses a triangle on the first pass.
        from OCP import BRepMesh
        from OCP.BRep import BRep_Tool
        from OCP.Poly import Poly_Triangle
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        real, meshed = BRepMesh.BRepMesh_IncrementalMesh, []

        def mesher(shape, *args):
            result = real(shape, *args)
            meshed.append(shape)
            if len(meshed) > 1:
                return result
            largest = max((BRep_Tool.Triangulation_s(TopoDS.Face_s(self.faces.FindKey(o)), TopLoc_Location())
                           for o in range(1, self.faces.Extent() + 1)), key=lambda t: t.NbTriangles())
            kept = [largest.Triangle(k).Get() for k in range(2, largest.NbTriangles() + 1)]
            largest.ResizeTriangles(len(kept), True)
            for k, corners in enumerate(kept, 1):
                largest.SetTriangle(k, Poly_Triangle(*corners))
            return result

        # OCCT reports nothing: it left the W16's, the hand's and the rear suspension's gaps
        # without a word, so a pass whose mesh has an open edge is looked at.
        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=mesher):
            _body, mesh = _mesh(self.topods)
        self.assertGreater(len(meshed), 1, "the component was meshed again")
        self.assertEqual(_open_edges(mesh), 0, "and no face has a gap")

    def test_only_a_face_a_pass_leaves_empty_is_measured_exactly_and_once(self):
        # The first pass's triangles say which faces the mesh resolves; the kernel's integral is
        # taken of a face the pass left empty -- the bore, here, on the first call -- once,
        # however many passes and checks ask after it.
        from OCP.BRepGProp import BRepGProp

        measured, real = [], BRepGProp.SurfaceProperties_s

        def counted(face, *args):
            measured.append(self.faces.FindIndex(face))
            return real(face, *args)

        with mock.patch.object(BRepGProp, "SurfaceProperties_s", side_effect=counted):
            self.assertBoreMeshed(self.mesh(lambda shape, call: False))
            self.assertEqual(measured, [], "a pass that meshes every face measures none")
            self.assertBoreMeshed(self.mesh(lambda shape, call: call == 1))
        self.assertEqual(measured, [self.bore])

    def test_a_face_under_what_the_mesh_resolves_may_be_left_empty_and_unnamed(self):
        # A pin a hundredth of a millimetre across on the plate: its top, a thousandth of a
        # square millimetre, is under the square of the component's deflection. OCCT leaves it
        # empty here and no mesher covers it: nothing has to say so, and it earns no finer pass.
        from build123d import Axis, Box, Cylinder, Location
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from cadgen._internal import face_fallback
        from cadgen.store.meshes import decode_payload

        plate = Box(20, 20, 10) - Cylinder(4, 10) + Location((8, 8, 5.005)) * Box(0.01, 0.1, 0.01)
        self.topods = plate.wrapped
        self.faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.topods, TopAbs_FACE, self.faces)
        self.bore = self.faces.FindIndex(plate.faces().sort_by(Axis.Z)[-1].wrapped)
        with mock.patch.object(face_fallback, "tessellate_face", return_value=None):
            mesh = self.mesh(lambda shape, call: True)
        top = next(row for row in mesh.face_ranges if row["ord"] == self.bore)
        self.assertEqual((top["indexCount"], decode_payload(self.body).unmeshed_faces, len(self.meshed)), (0, [], 1))


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

    def test_a_needle_folded_over_its_neighbour_is_unfolded_and_keeps_its_edges_running_both_ways(self):
        # OCCT's Delaunay leaves the odd needle across a B-spline folded over its neighbour -- a
        # bracelet link's five, half a deflection wide -- which a two-sided material drew dark.
        # The edge the two share is flipped: wound the other way instead, the needle's edges
        # would run the way its neighbours' run, and a mesh export's orientation checks fail.
        from cadgen._internal.tessellate import _unfold_needles

        a, b, c, d = 0, 1, 2, 3
        positions = np.array([[0, 0, 0], [4, 0, 0], [2, -0.5, 0], [2, -2, 0]], np.float32)
        normals = np.tile(np.array([0, 0, 1], np.float32), (4, 1))
        triangles = np.array([[a, b, c], [b, a, d]], np.uint32)  # c lies inside the other: folded
        _unfold_needles(positions, normals, triangles)
        self.assertEqual(sorted(map(tuple, triangles.tolist())), [(a, d, c), (d, b, c)])

    def test_every_part_is_unfolded(self):
        from build123d import Box
        from cadgen._internal import tessellate

        with mock.patch.object(tessellate, "_unfold_needles", wraps=tessellate._unfold_needles) as unfold:
            _body, mesh = _mesh(Box(4, 4, 4))
        self.assertEqual(unfold.call_count, 1)
        self.assertEqual(unfold.call_args.args[2].size, mesh.indices.size, "the whole part's triangles")

    def test_the_writers_reading_and_the_face_by_face_one_are_the_same_bytes(self):
        from build123d import Cone, Sphere

        from cadgen._internal import tessellate

        for label, shape in (("cone", lambda: Cone(5, 0, 10)), ("sphere", lambda: Sphere(6))):
            with self.subTest(label):
                written, _ = _mesh(shape())
                with mock.patch.object(tessellate, "_faces_from_gltf", return_value=None):
                    read, _ = _mesh(shape())
                self.assertEqual(written, read)


class LooseGeometry(unittest.TestCase):
    def test_a_free_edge_or_vertex_beside_a_solid_keeps_the_writers_path(self):
        from build123d import Box, Edge, Vertex

        from cadgen._internal import tessellate

        for label, loose in (("edge", Edge.make_line((10, 0, 0), (20, 0, 0))), ("vertex", Vertex(10, 0, 0))):
            with self.subTest(label), mock.patch.object(
                    tessellate, "_faces_one_by_one", wraps=tessellate._faces_one_by_one) as one_by_one:
                _body, mesh = _mesh(_compound(Box(5, 5, 5), loose))
                one_by_one.assert_not_called()
                self.assertEqual(len(mesh.indices) // 3, 12)

    def test_a_mirrored_placement_read_face_by_face_still_faces_outward(self):
        from build123d import Box
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

        from cadgen._internal import tessellate

        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(50, 0, 0), gp_Dir(1, 0, 0)))
        mirrored = Box(10, 10, 10).wrapped.Moved(TopLoc_Location(mirror), False)
        with mock.patch.object(tessellate, "_faces_from_gltf", return_value=None):
            _body, mesh = _mesh(_compound(mirrored))
        corners = _corners(mesh)
        volume = np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])).sum() / 6
        self.assertAlmostEqual(float(volume), 1000.0, places=3)


if __name__ == "__main__":
    unittest.main()
