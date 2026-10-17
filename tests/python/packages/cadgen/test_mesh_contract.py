"""The mesh contract: what every display mesh cadgen stores must be, whichever algorithm made it.

README law 1 and STORE.md §3: a part's display mesh is closed (each edge of the welded mesh used by
an even number of triangles), covers every face of its BREP that the tolerance can resolve and
nothing outside it (each face's area is the exact face's, no face is left silently empty), lies on
its exact surfaces within the display tolerance (its vertices and the interior of its triangles
alike), is wound outward with its normals the surfaces' own, and has no folded triangle and no
degenerate one but the collapsed triangles that close a pole or an apex. A solid of every
surface kind cadgen meets -- planes and cylinders round a hole, fillets,
a sphere and a torus closing on themselves, a cone to its apex, a loft of degree 14, a spline and
an ellipse extruded, a spline revolved, a plate made of rational B-splines, and windows cut through
a sphere -- is built here and held to each clause through the store's own mesher, at the one
display tolerance. The scoreboard (the repository's manual benchmark) measures the same clauses
over a corpus of real models; this test says they hold at all.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

SAMPLE = 24  # the longest triangles of each face whose interiors are projected onto the surface
AREA_TOLERANCE = 1e-2
# A round body meshed at the display angle tolerance (0.35 rad between a vertex's normal and its
# neighbour's) loses up to half a per cent of its volume to its facets.
VOLUME_TOLERANCE = 1e-2
TRIANGLE_BUDGET = 4.0  # against OCCT's BRepMesh at the same tolerances
# A triangle is folded when its facet points against the normal it is drawn with by more than the
# rounding of a sliver seen edge-on: the cosine between them below this.
FOLDED_COSINE = -1e-3


def _shapes() -> dict:
    """The solids, one of each surface kind, as build123d shapes."""
    from build123d import Axis, Box, BuildLine, BuildPart, BuildSketch, Circle, Cone, Cylinder, Ellipse, \
        Location, Locations, Mode, Plane, Polygon, Polyline, Solid, Sphere, Spline, Torus, extrude, fillet, loft, \
        make_face, revolve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

    with BuildPart() as gear:  # sixteen teeth round a bore
        with BuildSketch(Plane.XY):
            Polygon(*[(r * math.cos(math.pi * k / 16), r * math.sin(math.pi * k / 16))
                      for k, r in enumerate([20, 24] * 16)])
        extrude(amount=8)
        Cylinder(6, 20, mode=Mode.SUBTRACT)
    with BuildPart() as vase:  # a loft through circles: a B-spline surface of degree 14
        for z, radius in ((0, 10), (8, 14), (16, 8), (24, 11)):
            with BuildSketch(Plane.XY.offset(z)):
                Circle(radius)
        loft()
    with BuildPart() as cam:  # a spline and an elliptical hole, extruded
        with BuildSketch():
            with BuildLine():
                Spline((0, 0), (10, 4), (20, -2), (30, 3))
                Polyline((30, 3), (30, -12), (0, -12), (0, 0))
            make_face()
            with Locations((15, -5)):
                Ellipse(6, 3, mode=Mode.SUBTRACT)
        extrude(amount=6)
    with BuildPart() as bell:  # a spline, revolved
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Spline((0, 0), (8, 2), (6, 10), (9, 18))
                Polyline((9, 18), (0, 18), (0, 0))
            make_face()
        revolve(axis=Axis.Z)
    plate = fillet((Box(40, 30, 12) - Cylinder(5, 20)).edges().group_by()[-1], 2)
    return {
        "plate": plate + Sphere(6).moved(Location((12, 0, 6))),
        "gear": gear.part,
        "sphere": Sphere(7),
        "torus": Torus(12, 4),
        "cone": Cone(10, 0, 20),
        "vase": vase.part,
        "cam": cam.part,
        "bell": bell.part,
        "nurbs plate": Solid(BRepBuilderAPI_NurbsConvert(plate.wrapped, True).Shape()),
        "windows": Sphere(10) - Box(12, 30, 9),
    }


def _mesh(topods):
    """The solid's display mesh as the store derives it, decoded, with its deflection in millimetres."""
    from cadgen._internal.tessellate import mesh_component
    from cadgen._internal.topology_extract import extract_topology_facts
    from cadgen.store.meshes import decode_payload
    from cadgen.store.parts import PART_VERSION
    from cadgen.tessellation_policy import DISPLAY_TESSELLATION
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box

    body = mesh_component(topods, extract_topology_facts(topods), {}, part="0" * 64 + f"-v{PART_VERSION}",
                          chord=DISPLAY_TESSELLATION["chordTolerance"], angle=DISPLAY_TESSELLATION["angleTolerance"]).body
    box = Bnd_Box()
    BRepBndLib.Add_s(topods, box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return decode_payload(body), DISPLAY_TESSELLATION["chordTolerance"] * math.dist((x0, y0, z0), (x1, y1, z1))


def _odd_edges(positions, triangles) -> int:
    """Edges of the mesh welded where its float32 vertices coincide that an odd number of triangles
    use: a crack, a T-junction or a hole."""
    _, label = np.unique(np.ascontiguousarray(positions, np.float32).view(np.dtype((np.void, 12))).ravel(),
                         return_inverse=True)
    welded = label.ravel()[triangles]
    keep = (welded[:, 0] != welded[:, 1]) & (welded[:, 1] != welded[:, 2]) & (welded[:, 2] != welded[:, 0])
    welded = welded[keep]
    edges = np.sort(np.concatenate([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]]), axis=1)
    _keys, counts = np.unique(edges[:, 0] * (int(label.max()) + 1) + edges[:, 1], return_counts=True)
    return int((counts % 2).sum())


def _face_map(topods):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
    return faces


def _exact_area_and_perimeter(face) -> tuple[float, float]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    area, length = GProp_GProps(), GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, area)
    BRepGProp.LinearProperties_s(face, length)
    return area.Mass(), length.Mass()


def _surface_distance_and_fold(face, positions, triangles) -> tuple[float, int]:
    """Over the face's longest triangles, the farthest any sampled point of them (centroid, edge
    midpoints, an interior point) lies from the exact surface, and how many of them are folded
    against the surface's normal where they sit."""
    from OCP.BRep import BRep_Tool
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomLProp import GeomLProp_SLProps
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt

    location = TopLoc_Location()
    surface = BRep_Tool.Surface_s(face, location)
    transform = location.Transformation()
    inverse = transform.Inverted()
    sign = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
    a, b, c = (positions[triangles[:, k]] for k in range(3))
    longest = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1)),
                         np.linalg.norm(a - c, axis=1))
    worst, folded = 0.0, 0
    for k in np.argsort(-longest)[:SAMPLE].tolist():
        facet = np.cross(b[k] - a[k], c[k] - a[k])
        samples = ((a[k] + b[k] + c[k]) / 3, (a[k] + b[k]) / 2, (b[k] + c[k]) / 2, (c[k] + a[k]) / 2,
                   0.6 * a[k] + 0.25 * b[k] + 0.15 * c[k])
        for index, point in enumerate(samples):
            projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point.tolist()).Transformed(inverse), surface)
            if not projector.NbPoints():
                continue
            worst = max(worst, projector.LowerDistance())
            if index == 0 and np.linalg.norm(facet) > 0:
                u, v = projector.LowerDistanceParameters()
                props = GeomLProp_SLProps(surface, u, v, 1, 1e-9)
                if props.IsNormalDefined():
                    normal = props.Normal().Transformed(transform)
                    n = sign * np.array([normal.X(), normal.Y(), normal.Z()])
                    folded += int(np.dot(facet, n) / (np.linalg.norm(facet) * np.linalg.norm(n)) < FOLDED_COSINE)
    return worst, folded


def _occt_triangles(topods, deflection: float, angle: float) -> int:
    """How many triangles OCCT's BRepMesh makes of the solid at the same tolerances."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.IMeshTools import IMeshTools_Parameters
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    copy = BRepBuilderAPI_Copy(topods).Shape()  # meshed apart, so the solid under test keeps no triangulation
    BRepTools.Clean_s(copy)
    params = IMeshTools_Parameters()
    params.Deflection, params.Angle, params.InParallel = deflection, angle, False
    BRepMesh_IncrementalMesh(copy, params)
    faces = _face_map(copy)
    total = 0
    for ordinal in range(1, faces.Extent() + 1):
        poly = BRep_Tool.Triangulation_s(TopoDS.Face_s(faces.FindKey(ordinal)), TopLoc_Location())
        total += poly.NbTriangles() if poly is not None else 0
    return total


class _Case:
    """One solid, meshed once for every clause."""

    def __init__(self, shape) -> None:
        self.shape = shape
        self.mesh, self.deflection = _mesh(shape.wrapped)
        self.positions = np.asarray(self.mesh.positions, np.float64)
        self.triangles = np.asarray(self.mesh.indices, np.int64).reshape(-1, 3)
        self.faces = _face_map(shape.wrapped)

    def face(self, ordinal: int):
        from OCP.TopoDS import TopoDS

        return TopoDS.Face_s(self.faces.FindKey(ordinal))


class MeshContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {name: _Case(shape) for name, shape in _shapes().items()}

    def test_every_solid_is_closed(self) -> None:
        for name, case in self.cases.items():
            with self.subTest(name):
                self.assertGreater(len(case.triangles), 0)
                self.assertEqual(0, _odd_edges(case.positions, case.triangles),
                                 f"{name}: an open edge, a crack or a T-junction")

    def test_every_face_is_covered_to_its_trim_and_none_is_silently_empty(self) -> None:
        for name, case in self.cases.items():
            with self.subTest(name):
                self.assertEqual([], list(case.mesh.unmeshed_faces), f"{name} names a face it could not mesh")
                for ordinal, start, count, _colour in case.mesh.faces.tolist():
                    exact, perimeter = _exact_area_and_perimeter(case.face(ordinal))
                    if exact < case.deflection * case.deflection:
                        continue
                    self.assertGreater(count, 0, f"{name}: face {ordinal} ({exact:.3g} mm²) is silently empty")
                    t = case.triangles[start // 3:(start + count) // 3]
                    p = case.positions
                    area = float(np.linalg.norm(np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]]),
                                                axis=1).sum() / 2)
                    # Polygonizing the boundary within the chord tolerance moves at most perimeter × d
                    # of area; anything beyond that, and beyond 1%, is trim the mesh missed or invented.
                    self.assertLessEqual(abs(area - exact), max(AREA_TOLERANCE * exact, perimeter * case.deflection),
                                         f"{name}: face {ordinal}'s area is {area:.4g} mm² against {exact:.4g} exact")

    def test_every_triangle_lies_on_its_surface_within_the_tolerance(self) -> None:
        for name, case in self.cases.items():
            with self.subTest(name):
                for ordinal, start, count, _colour in case.mesh.faces.tolist():
                    if not count:
                        continue
                    t = case.triangles[start // 3:(start + count) // 3]
                    distance, folded = _surface_distance_and_fold(case.face(ordinal), case.positions, t)
                    self.assertLessEqual(distance, 2 * case.deflection,
                                         f"{name}: face {ordinal} strays {distance / case.deflection:.2f} d off "
                                         "its surface")
                    self.assertEqual(0, folded, f"{name}: face {ordinal} has a triangle folded against its surface")

    def test_every_solid_is_wound_outward_with_the_surfaces_normals_and_no_degenerate_triangle(self) -> None:
        for name, case in self.cases.items():
            with self.subTest(name):
                a, b, c = (case.positions[case.triangles[:, k]] for k in range(3))
                facets = np.cross(b - a, c - a)
                # A triangle of no area is a collapsed one -- two corners at one point, where OCCT
                # closes a pole or an apex -- never a sliver of three distinct points.
                flat = np.linalg.norm(facets, axis=1) == 0
                collapsed = (a == b).all(axis=1) | (b == c).all(axis=1) | (c == a).all(axis=1)
                self.assertTrue(bool((~flat | collapsed).all()), f"{name}: a degenerate triangle")
                volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)
                self.assertAlmostEqual(1.0, volume / case.shape.volume, delta=VOLUME_TOLERANCE,
                                       msg=f"{name}: wound outward, its volume the solid's")
                normals = np.asarray(case.mesh.normals, np.float64)[case.triangles].sum(axis=1)
                cosine = np.einsum("ij,ij->i", facets, normals) / (np.linalg.norm(facets, axis=1)
                                                                   * np.maximum(np.linalg.norm(normals, axis=1), 1e-300))
                against = np.nonzero(cosine < FOLDED_COSINE)[0]
                self.assertEqual([], against.tolist(), f"{name}: triangles folded against the normals they are drawn with")

    def test_no_solid_costs_more_than_a_few_times_occts_triangles(self) -> None:
        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        for name, case in self.cases.items():
            with self.subTest(name):
                occt = _occt_triangles(case.shape.wrapped, case.deflection, DISPLAY_TESSELLATION["angleTolerance"])
                self.assertLessEqual(len(case.triangles), TRIANGLE_BUDGET * max(occt, 1),
                                     f"{name}: {len(case.triangles)} triangles against OCCT's {occt}")


if __name__ == "__main__":
    unittest.main()
