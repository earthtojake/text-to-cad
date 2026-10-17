"""A face no mesher covers leaves its part drawn without it, and every door says so.

A tiny assembly -- a 20 x 10 x 5 plate and a radius-5 pin -- whose pin's side is made a
face no mesher covers: OCCT refuses it and cadgen's own tessellation cannot cover it
either, as the f14d wings' slivers once could not. That one face once failed the whole
document: the list, the view and the STL all ended in a traceback. Now the pin is meshed
without it, the plate whole, and each door does its work and names the face it left out:
the list counts the pin without it, the view draws the rest, and the STL is written open
where the face was.

The compile has every part meshed, by one build-pool job, before it reports done; here
the compile and its job run in this process (``step.compile``, ``inline_artifacts``), so
the refusal reaches it, and every door after it only reads.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.inline_artifacts import inline_artifacts
from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png

add_repo_path("packages/cadgen/src")

SIZE = (320, 240)
# The pin by its occurrence token, the face by its geometric token (a file read names its
# elements by their geometry): the refs a person pastes.
WARNED = r"^#o:[0-9a-f]{12} pin: 1 face \(f:[0-9a-f]{12}\) could not be meshed, so "


def write_assembly(path) -> None:
    from build123d import Compound, Location, Solid

    from cadgen.step_export import export_build123d_step_file

    plate = Solid.make_box(20, 10, 5)
    plate.label = "plate"
    pin = Solid.make_cylinder(5, 20).moved(Location((30, 0, 0)))
    pin.label = "pin"
    export_build123d_step_file(Compound(children=[plate, pin], label="asm"), path)


def refusing_the_pins_side(real):
    """``tessellate._mesh`` with every mesher's work on a cylinder's side undone: the face
    neither OCCT nor the fallback covers."""
    def mesh(topods, face_map, kinds, deflection, angle):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_Cylinder
        from OCP.TopoDS import TopoDS

        faces, required = real(topods, face_map, kinds, deflection, angle)
        for ordinal in range(1, face_map.Extent() + 1):
            face = TopoDS.Face_s(face_map.FindKey(ordinal))
            if BRepAdaptor_Surface(face).GetType() == GeomAbs_Cylinder:
                BRepTools.Clean_s(face)
                faces.pop(ordinal, None)
        return faces, required
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
        from cadgen._internal import tessellate

        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"}), inline_artifacts(), \
                mock.patch.object(tessellate, "_mesh", refusing_the_pins_side(tessellate._mesh)):
            step_door.compile(document)
        # Each door only reads what the compile stored: none starts a derivation job.
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"}), \
                mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("a door derived")):
            cls.listing = step_door.snapshot(document, mode="list")
            cls.view = step_door.snapshot(document, cls.workspace / "asm.png", width=SIZE[0], height=SIZE[1])
            cls.export = stl_door.build(document, cls.workspace / "asm.stl")
        cls.image = read_png((cls.workspace / "asm.png").read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_the_list_counts_the_pin_without_its_side_and_says_so(self) -> None:
        self.assertTrue(self.listing.ok)
        rows = {row["name"]: row for row in self.listing.parts}
        self.assertEqual((12, 24), (rows["plate"]["triangleCount"], rows["plate"]["vertexCount"]), "the plate is whole")
        # The pin's two caps, and nothing of its side.
        self.assertGreater(rows["pin"]["triangleCount"], 0)
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
