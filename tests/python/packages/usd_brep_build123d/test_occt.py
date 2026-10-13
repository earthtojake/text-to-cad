"""The exact conversion to OpenCascade, which the parity tests trust as their judge.

Each body exercises a convention of the BrepArray format that had to be found by testing
(V-fastest NURBS poles, cylinders written as zero-angle cones, seams crossing trims, poles,
apexes, tori); the converted shape must be valid, keep its faces and enclose usd-brep's volume.
"""

from __future__ import annotations

import unittest

from tests.python.packages.usd_brep_build123d.parity import occt_volume, requires_usd_brep


@requires_usd_brep
class ExactConversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import usd_brep as ub
        from usd_brep_build123d import occt

        cls.ub, cls.occt = ub, occt

    def bodies(self):
        ub = self.ub

        def blended_box():
            b = ub.create_box((0, 0, 0), 10, 10, 10)
            return ub.fillet_edges(b, b.edges(), radius=1.0, xsect_type=2, continuity=2)

        def open_top_shell():
            b = ub.create_box((0, 0, 0), 20, 20, 20)
            top = [f for f in b.faces() if f.bounding_box(tight=True)[0][2] > 19.999]
            return ub.shell_brep(b, -2.0, faces_to_shell=top)

        return {
            "box minus cylinder": lambda: ub.boolean_difference(ub.create_box((0, 0, 0), 20, 10, 5), ub.create_cylinder((10, 5, -1), 2, 7)),
            "cube common sphere": lambda: ub.boolean_intersection(ub.create_box((0, 0, 0), 10, 10, 10), ub.create_sphere((5, 5, 5), 6)),
            "G2-blended box": blended_box,
            "napkin ring": lambda: ub.boolean_difference(ub.create_sphere((0, 0, 0), 10), ub.create_cylinder((0, 0, -11), 3, 22)),
            "torus minus cone": lambda: ub.boolean_difference(ub.create_torus((0, 0, 0), 20, 5), ub.create_cone((20, 0, -10), 8, 2, 20)),
            "cone apex": lambda: ub.boolean_difference(ub.create_cone((0, 0, 0), 5, 0, 10), ub.create_box((-1, -6, -1), 7, 12, 4)),
            "open-top shell": open_top_shell,
        }

    def test_bodies_convert_exactly(self):
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer

        for name, make in self.bodies().items():
            with self.subTest(body=name):
                brep = make()
                shape = self.occt.to_occt(brep, validate="strict")
                self.assertTrue(BRepCheck_Analyzer(shape).IsValid())
                faces, explorer = 0, TopExp_Explorer(shape, TopAbs_FACE)
                while explorer.More():
                    faces += 1
                    explorer.Next()
                self.assertEqual(faces, brep.face_count())
                self.assertAlmostEqual(occt_volume(shape) / brep.volume(relative_accuracy=1e-8), 1.0, places=6)

    def test_a_body_with_no_solid_is_refused(self):
        with self.assertRaises(self.occt.BridgeError):
            self.occt.to_occt(self.ub.create_planar_circle((0, 0, 0), 5.0))

    def test_to_build123d_keeps_the_label(self):
        import usd_brep_build123d as bd

        part = bd.Box(4, 4, 4)
        part.label = "cube"
        solid = self.occt.to_build123d(part)
        self.assertEqual(solid.label, "cube")
        self.assertAlmostEqual(solid.volume, 64.0, places=6)


if __name__ == "__main__":
    unittest.main()
