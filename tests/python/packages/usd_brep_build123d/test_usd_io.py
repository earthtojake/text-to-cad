"""USD is the package's native output: a part written and read back is the same exact solid.

Volumes are measured on the exact OpenCascade conversion: usd-brep's own integrator is not
accurate to the 1e-6 it is asked for (it reads a NURBS blend differently after a round trip
that changed nothing).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.packages.usd_brep_build123d.parity import occt_volume, requires_usd_brep
from tests.python.support.tmp_root import generated_cad_directory


@requires_usd_brep
class UsdRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import usd_brep_build123d as bd
        from usd_brep_build123d.occt import to_occt

        cls.bd = bd
        cls.exact_volume = staticmethod(lambda shape: occt_volume(to_occt(shape)))
        with bd.BuildPart() as p:
            bd.Cylinder(20, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            with bd.PolarLocations(14, 4):
                bd.Hole(2)
            bd.blend(p.edges().group_by(bd.Axis.Z)[-1].filter_by(lambda e: e.radius > 19), radius=1.5)
        cls.part = p.part

    def setUp(self):
        tmp = generated_cad_directory(prefix="usd-brep-build123d-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_text_and_binary_usd_round_trip(self):
        for suffix in (".usda", ".usdc"):
            with self.subTest(suffix=suffix):
                path = self.dir / f"flange{suffix}"
                self.bd.export_usd(self.part, path)
                back = self.bd.import_usd(path)
                self.assertEqual(len(back.faces()), len(self.part.faces()))
                self.assertAlmostEqual(self.exact_volume(back) / self.exact_volume(self.part), 1.0, places=9)
        self.assertIn("BrepArray", (self.dir / "flange.usda").read_text(encoding="utf-8"))

    def test_an_assembly_writes_one_prim_per_part(self):
        bd = self.bd
        assembly = bd.Compound([self.part, bd.Pos(60, 0, 0) * bd.Box(10, 10, 10)])
        path = self.dir / "assembly.usda"
        bd.export_usd(assembly, path)
        back = bd.import_usd(path)
        self.assertEqual(len(back.children), 2)
        volumes = sorted(self.exact_volume(child) for child in back.children)
        self.assertAlmostEqual(volumes[0], 1000.0, places=6)
        self.assertAlmostEqual(volumes[1] / self.exact_volume(self.part), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
