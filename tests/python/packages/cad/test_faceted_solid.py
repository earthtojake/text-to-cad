"""``cad.build123d.faceted_solid``: a closed polygon mesh as a solid of planar faces.

Each mesh is written by hand or exported by build123d from a part whose answer is known: a tetrahedron's
volume is a sixth of its box's, a unit cube's is one, and a box with a hole read back from its STL has
the box's volume less the hole's, to the mesh's chords. A mesh that is no closed surface is refused
before anything is built.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer

from cad.build123d import faceted_solid

TETRAHEDRON = np.array([(0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)], dtype=float)
# Each wound counterclockwise seen from outside.
TRIANGLES = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
QUADS = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]


def _valid(shape) -> bool:
    return BRepCheck_Analyzer(shape.wrapped).IsValid()


class FacetedSolidTest(unittest.TestCase):
    def test_a_tetrahedron_is_four_planar_faces_and_its_volume(self) -> None:
        solid = faceted_solid(TETRAHEDRON, TRIANGLES)
        self.assertTrue(_valid(solid))
        self.assertEqual(len(solid.faces()), 4)
        self.assertTrue(all(face.geom_type.name == "PLANE" for face in solid.faces()))
        self.assertAlmostEqual(solid.volume, 1000 / 6, places=9)

    def test_a_cube_of_six_quads_is_six_faces_whatever_way_the_shell_turns(self) -> None:
        solid = faceted_solid(CUBE, QUADS)
        self.assertTrue(_valid(solid))
        self.assertEqual(len(solid.faces()), 6)
        self.assertAlmostEqual(solid.volume, 1.0, places=9)
        box = solid.bounding_box()
        self.assertEqual((tuple(box.min), tuple(box.max)), ((0, 0, 0), (1, 1, 1)))
        # Wound inward throughout, it is the same solid: the solid is oriented closed, never inside out.
        inward = faceted_solid(CUBE, [loop[::-1] for loop in QUADS])
        self.assertAlmostEqual(inward.volume, 1.0, places=9)

    def test_an_stl_build123d_wrote_reads_back_as_the_part(self) -> None:
        import build123d as bd

        from cad.engine.reader import read_mesh

        part = bd.Box(40, 20, 10) - bd.Cylinder(5, 20)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plate.stl"
            bd.export_stl(part, str(path), tolerance=0.01)
            mesh = read_mesh(path)
        solid = faceted_solid(mesh.vertices, mesh.triangles)
        self.assertTrue(_valid(solid))
        self.assertEqual(len(solid.faces()), len(mesh.triangles))
        # The hole's chords leave a little more material than its circle: within a tenth of a per cent.
        self.assertAlmostEqual(solid.volume, part.volume, delta=part.volume * 1e-3)
        self.assertEqual(tuple(round(value, 4) for value in solid.bounding_box().size), (40, 20, 10))

    def test_an_open_shell_is_refused_counting_its_edges(self) -> None:
        with self.assertRaisesRegex(ValueError, r"3 of the mesh's 6 edges are not shared by exactly two faces .*open"):
            faceted_solid(TETRAHEDRON, TRIANGLES[:3])

    def test_a_face_wound_against_its_neighbours_is_refused(self) -> None:
        flipped = TRIANGLES.copy()
        flipped[3] = flipped[3][::-1]
        with self.assertRaisesRegex(ValueError, "winding is inconsistent"):
            faceted_solid(TETRAHEDRON, flipped)

    def test_an_index_out_of_range_and_vertices_of_the_wrong_shape_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "names vertex 9, and there are 4 vertices"):
            faceted_solid(TETRAHEDRON, [[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 9]])
        with self.assertRaisesRegex(ValueError, "three or more distinct vertices"):
            faceted_solid(TETRAHEDRON, [[0, 2, 2], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
        with self.assertRaisesRegex(ValueError, r"\(n, 3\) array of points"):
            faceted_solid(TETRAHEDRON[:, :2], TRIANGLES)
        with self.assertRaisesRegex(ValueError, "not finite"):
            faceted_solid(np.vstack([TETRAHEDRON[:3], [np.nan, 0, 0]]), TRIANGLES)
        with self.assertRaisesRegex(TypeError, "integer indices"):
            faceted_solid(TETRAHEDRON, TRIANGLES.astype(float))

    def test_coincident_points_and_a_bent_polygon_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "coincident points"):
            faceted_solid(np.vstack([TETRAHEDRON[:3], TETRAHEDRON[:1]]), TRIANGLES)
        bent = [list(point) for point in CUBE]
        bent[6] = [1, 1, 1.01]
        with self.assertRaisesRegex(ValueError, "not in one plane"):
            faceted_solid(bent, QUADS)


if __name__ == "__main__":
    unittest.main()
