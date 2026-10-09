"""A face no mesher covers leaves its part drawn without it, and every door says so.

A tiny assembly -- a 20 x 10 x 5 plate and a radius-5 pin -- whose pin's side is made a
face no mesher covers: OCCT refuses it and cadgen's own tessellation cannot cover it
either, as the f14d wings' slivers once could not. That one face once failed the whole
document: the list, the view and the STL all ended in a traceback. Now the pin is meshed
without it, the plate whole, and each door does its work and names the face it left out:
the list counts the pin without it, the view draws the rest, and the STL is written open
where the face was.

Meshing is build-pool work; here it runs in this process (``daemon.artifacts`` inline), so
the refusal reaches it.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png

add_repo_path("packages/cadgen/src")

SIZE = (320, 240)
WARNED = r"^#o1\.2 pin: 1 face \(f\d+\) could not be meshed, so "


def write_assembly(path) -> None:
    from build123d import Compound, Location, Solid

    from cadgen.step_export import export_build123d_step_file

    plate = Solid.make_box(20, 10, 5)
    plate.label = "plate"
    pin = Solid.make_cylinder(5, 20).moved(Location((30, 0, 0)))
    pin.label = "pin"
    export_build123d_step_file(Compound(children=[plate, pin], label="asm"), path)


def refusing_the_pins_side(real):
    """``occt_mesh._mesh`` with every mesher's work on a cylinder's side undone: the face
    neither OCCT nor the fallback covers."""
    def mesh(topods, face_map, required, deflection, angle):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_Cylinder
        from OCP.TopoDS import TopoDS

        real(topods, face_map, required, deflection, angle)
        for ordinal in range(1, face_map.Extent() + 1):
            face = TopoDS.Face_s(face_map.FindKey(ordinal))
            if BRepAdaptor_Surface(face).GetType() == GeomAbs_Cylinder:
                BRepTools.Clean_s(face)
    return mesh


class UnmeshedFaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="unmeshed-face-")
        cls.workspace = cls._roots.cad_root
        document = cls.workspace / "asm.step"
        write_assembly(document)
        import cadgen.step as step_door
        import cadgen.stl as stl_door
        from cadgen._internal import occt_mesh
        from cadgen.daemon import artifacts

        inline = mock.patch.multiple(artifacts, _can_inline=mock.Mock(return_value=True),
                                     _dispatch=mock.Mock(side_effect=lambda request, _root: artifacts._run_inline(request)))
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"}), inline, \
                mock.patch.object(occt_mesh, "_mesh", refusing_the_pins_side(occt_mesh._mesh)):
            cls.listing = step_door.snapshot(document, mode="list")
            cls.view = step_door.snapshot(document, cls.workspace / "asm.png", width=SIZE[0], height=SIZE[1])
            cls.export = stl_door.build(document, cls.workspace / "asm.stl")
        cls.image = read_png((cls.workspace / "asm.png").read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_the_list_counts_the_pin_without_its_side_and_says_so(self) -> None:
        self.assertTrue(self.listing.ok)
        rows = {row["ref"]: row for row in self.listing.parts}
        self.assertEqual((12, 24), (rows["#o1.1"]["triangleCount"], rows["#o1.1"]["vertexCount"]), "the plate is whole")
        # The pin's two caps, and nothing of its side.
        self.assertGreater(rows["#o1.2"]["triangleCount"], 0)
        [warning] = self.listing.warnings
        self.assertRegex(warning, WARNED + "its triangle count leaves it out$")

    def test_the_view_draws_the_rest_and_says_so(self) -> None:
        self.assertTrue(self.view.ok)
        self.assertEqual(1, len(self.view.files))
        self.assertEqual(SIZE, (self.image.width, self.image.height))
        background = self.image.pixel(0, 0)
        drawn = sum(self.image.pixel(x, y) != background for x in range(0, SIZE[0], 4) for y in range(0, SIZE[1], 4))
        self.assertGreater(drawn, 200, "the view drew the plate and what it has of the pin")
        [warning] = self.view.warnings
        self.assertRegex(warning, WARNED + "the view does not draw it$")

    def test_the_stl_is_written_open_where_the_side_was_and_says_so(self) -> None:
        import trimesh

        self.assertTrue(self.export.ok)
        [written] = self.export.files
        mesh = trimesh.load(written.path)
        self.assertGreater(len(mesh.faces), 12, "the plate and the pin's caps")
        self.assertFalse(mesh.is_watertight)
        [warning] = self.export.warnings
        self.assertRegex(warning, WARNED + r"asm\.stl has a hole in place of it: it is not watertight$")


if __name__ == "__main__":
    unittest.main()
