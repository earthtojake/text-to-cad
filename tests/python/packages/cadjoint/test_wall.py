"""A sampled field's thinnest wall (``cad.cadjoint._field.sample``): measured on the field, refused under two cells.

Each figure is the construction's: a box of half-sizes 20 x 10 x 3 is 6 mm thick; a sphere shelled to a 2 mm
wall and cut flat at z = 10 (closed, its two faces would be two bodies) is 2 mm thick, its slanted rim an
acute edge that is no wall; the space-frame node (``fixtures/space_frame_node.py``) is hollowed to 2 mm,
its tube ends cut by a ball. Under two cells the sample is refused, naming the cell that gives the wall four.
"""

from __future__ import annotations

import runpy
import unittest
from pathlib import Path

from cad.cadjoint._field import Field, sample

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cup():
    """A sphere of radius 20 shelled to a 2 mm wall, cut flat at z = 10: one open body, its rim cut at a slant."""
    from cadjoint.construction import Solid
    from cadjoint.sdf import Shell
    from cadjoint.sdf.boolean import Intersection

    return Intersection(Shell(Solid.sphere(radius=20.0, name="ball"), 2.0),
                        Solid.box(size=(30.0, 30.0, 20.0), position=(0.0, 0.0, -10.0), name="below"), smoothness=0.0)


class WallTest(unittest.TestCase):
    def test_a_box_measures_its_thickness(self) -> None:
        from cadjoint.construction import Solid

        found = sample(Field(Solid.box(size=(20.0, 10.0, 3.0), name="block"), 1.0))
        self.assertAlmostEqual(found.wall_mm, 6.0, delta=0.1)
        self.assertAlmostEqual(found.cells, 6.0, delta=0.1)

    def test_an_open_shell_measures_its_wall_not_its_rim(self) -> None:
        found = sample(Field(_cup(), 0.5))
        self.assertAlmostEqual(found.wall_mm, 2.0, delta=0.1)
        self.assertAlmostEqual(found.cells, 4.0, delta=0.2)

    def test_the_space_frame_node_measures_its_two_millimetre_wall(self) -> None:
        scene = runpy.run_path(str(FIXTURES / "space_frame_node.py"), run_name="__fixture__")["scene"]
        found = sample(Field(scene, 0.5))
        self.assertAlmostEqual(found.wall_mm, 2.0, delta=0.1)

    def test_a_wall_under_two_cells_is_refused_naming_the_cell_for_four(self) -> None:
        from cad.cadjoint import solid

        refusal = (r"^the thinnest wall is 1\.\d cells \(1\.9\d* mm at a 1\.2 mm cell\), and a wall needs about four: "
                   r"use a cell of 0\.(49\d*|5) mm or less, or thicken it$")
        with self.assertRaisesRegex(ValueError, refusal):
            sample(Field(_cup(), 1.2), where="cad.cadjoint.field")
        with self.assertRaisesRegex(ValueError, refusal):
            solid(_cup(), cell=1.2)


if __name__ == "__main__":
    unittest.main()
