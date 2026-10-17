"""A named STEP places every occurrence so that a reader mints its token as the result
does, and moves nothing it need not (``step_placements``).

A reader reads a translation exactly as the file states it, and a token rounds a
translation as stated, so no translation is ever moved. A rotation entry is rebuilt from two
stated directions, and about one placement in five hundred turned at a general angle has an
entry that rounds otherwise once rebuilt; written named, such an occurrence alone is turned,
by at most a picoradian, to one that is read rounding as given; written plain, it is
placed exactly as given.
"""

from __future__ import annotations

import math
import random
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


def _turned(rng: random.Random, span: float = 50.0):
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

    trsf = gp_Trsf()
    axis = gp_Dir(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
    trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), axis), rng.uniform(0, 2 * math.pi))
    trsf.SetTranslationPart(gp_Vec(rng.uniform(-span, span), rng.uniform(-span, span), rng.uniform(-span, span)))
    return trsf


def _values(trsf) -> list[float]:
    return [trsf.Value(row, column) for row in range(1, 4) for column in range(1, 5)]


def _rounded(values):
    from cadgen._internal.tree_tokens import rounded_placement

    return rounded_placement(list(values))


def _read(placements: list, names) -> list[list[float]]:
    """Each placement as a cold parse of a file holding a box placed by each reads it."""
    import build123d as bd
    from OCP.TopLoc import TopLoc_Location

    from cadgen._internal.step_scene_loader import load_step_scene
    from cadgen.step_export import export_build123d_step_file

    leaves = []
    for index, trsf in enumerate(placements):
        leaf = bd.Solid.make_box(1, 2, 3).moved(bd.Location(TopLoc_Location(trsf)))
        leaf.label = f"b{index}"
        leaves.append(leaf)
    with tempfile.TemporaryDirectory(prefix="step-placements-") as tmp:
        path = Path(tmp) / "placed.step"
        export_build123d_step_file(bd.Compound(children=leaves, label="rig"), path, names=names)
        return [list(node.transform[:12]) for node in load_step_scene(path).roots[0].children]


class ReadablePlacementTest(unittest.TestCase):
    def test_what_a_reader_rebuilds_is_computed_exactly(self) -> None:
        from cadgen._internal.step_placements import as_read

        rng = random.Random(20261016)
        placements = [_turned(rng, span) for span in (50.0, 5000.0) for _ in range(150)]
        for trsf, read in zip(placements, _read(placements, None)):
            self.assertEqual(list(as_read(trsf)), read)

    def test_a_translation_is_read_as_stated_so_it_never_moves(self) -> None:
        from OCP.gp import gp_Trsf, gp_Vec

        from cadgen._internal.step_placements import readable_placement
        from cadgen._internal.step_reals import stated_real
        from cadgen._internal.tree_tokens import TRANSLATION_QUANTUM

        values = [1234.0 + (n + 0.5) * TRANSLATION_QUANTUM - 3e-10 for n in range(1000)]
        stated = next(value for value in values
                      if round(value / TRANSLATION_QUANTUM) != round(stated_real(value) / TRANSLATION_QUANTUM))
        self.assertEqual(stated_real(stated_real(stated)), stated_real(stated), "a stated real reads as itself")
        trsf = gp_Trsf()
        trsf.SetTranslationPart(gp_Vec(stated, -stated, 0.25))
        self.assertIs(readable_placement(trsf), trsf)
        for names in (None, lambda shape: None):
            with self.subTest(named=names is not None):
                (read,) = _read([trsf], names)
                self.assertEqual(_rounded(read), _rounded(_values(trsf)))

    def test_only_a_rotation_that_would_be_read_as_another_token_is_turned_by_at_most_a_picoradian(self) -> None:
        from cadgen._internal.step_placements import as_read, readable_placement

        rng = random.Random(20261016)
        candidates = [_turned(rng) for _ in range(3000)]
        flipping = next(trsf for trsf in candidates if _rounded(as_read(trsf)) != _rounded(_values(trsf)))
        steady = next(trsf for trsf in candidates if _rounded(as_read(trsf)) == _rounded(_values(trsf)))
        self.assertIs(readable_placement(steady), steady, "a placement that is read as itself is kept")
        placed = readable_placement(flipping)
        self.assertEqual(_rounded(as_read(placed)), _rounded(_values(flipping)))
        for index, (given, written) in enumerate(zip(_values(flipping), _values(placed))):
            if index % 4 == 3:
                self.assertEqual(written, given, "a translation never moves")
            else:
                self.assertLessEqual(abs(written - given), 1.5e-12, "a rotation entry moves by one stated digit")

        plain, named = _read([flipping], None), _read([flipping], lambda shape: None)
        self.assertNotEqual(_rounded(plain[0]), _rounded(_values(flipping)),
                            "the premise: written as given, it rounds otherwise")
        self.assertEqual(_rounded(named[0]), _rounded(_values(flipping)))


class StatedRealTest(unittest.TestCase):
    """``step_reals.stated_real`` is what the reader returns for what the writer printed
    (``written_text``)."""

    def test_emulation_matches_the_writer_and_reader(self):
        import build123d as bd

        from cadgen._internal.step_reals import stated_real
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file

        scratch = tempfile.TemporaryDirectory(prefix="stated-real-")
        self.addCleanup(scratch.cleanup)
        values = [0.0, -0.0, 0.1, 0.09999999999999999, 0.1000000000000001, 999.9999999999999, 1000.0,
                  1000.0000000000001, 999.95, 0.5, 1 / 3, 2 / 3, -1 / 3, 1e-7, 1e-12, 1e-300, 1e300,
                  5e-324, 123456789.123456789, 12.345678901234567, -12.345678901234567, 99.999999999999,
                  666.6666666666666, -666.6666666666666, 999.123456789012, -999.123456789012,
                  0.000123456789012345, 1234.5678901234, 55.5555555555555, -5.5, 7.000000000001]
        generator = random.Random(20261001)
        for _ in range(240):
            magnitude = 10.0 ** generator.uniform(-9, 9)
            values.append(generator.choice((-1, 1)) * magnitude * generator.random())
        for _ in range(60):
            values.append(round(generator.uniform(-2000, 2000), generator.randint(0, 6)))
        box = bd.Solid.make_box(1, 1, 1)
        children = []
        for index in range(0, len(values), 3):
            x, y, z = (values[index:index + 3] + [0.0, 0.0])[:3]
            placed = box.moved(bd.Location((x, y, z)))
            placed.label = f"p{index}"
            children.append(placed)
        step = Path(scratch.name) / "points.step"
        export_build123d_step_file(bd.Compound(children=children, label="points"), step)
        scene = load_step_scene(step)
        mismatches = []
        for node, index in zip(scene.roots[0].children, range(0, len(values), 3)):
            expected = (values[index:index + 3] + [0.0, 0.0])[:3]
            for value, read in zip(expected, (node.transform[3], node.transform[7], node.transform[11])):
                emulated = stated_real(value)
                if emulated != read or math.copysign(1, emulated) != math.copysign(1, read):
                    mismatches.append((value, emulated, read))
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
