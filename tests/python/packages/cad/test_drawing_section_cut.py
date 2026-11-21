"""A section's cut is the whole part: a split that comes back short is not drawn short.

OCCT's splitter has returned done with a piece missing (a two-solid part read from
STEP: three pieces of four on its first run in a process, four the next). These
tests stand that behaviour in with a split that drops a piece, so they do not
depend on which shapes OCCT happens to mis-split. A split that keeps losing is
refused (law 17), never drawn short.
"""

from __future__ import annotations

import unittest
from unittest import mock


def _two_blocks():
    from build123d import Box, Compound, Pos

    # One part of two solids, as a split pad is: the plane y=0 cuts both.
    return Compound([Pos(-30, 0, 0) * Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)])


def _dropping(times: int):
    """A Shape.split that loses its last piece on the first ``times`` calls."""
    from build123d import Shape

    real = Shape.split
    calls: list[int] = []

    def split(self, tool, keep=None):
        pieces = real(self, tool, keep) if keep is not None else real(self, tool)
        calls.append(1)
        if len(calls) <= times and isinstance(pieces, (list, tuple)) and len(pieces) > 1:
            return type(pieces)(list(pieces)[:-1]) if not isinstance(pieces, tuple) else pieces[:-1]
        return pieces

    return split, calls


class PlaneCutTests(unittest.TestCase):
    def test_a_whole_cut_keeps_every_solid_and_its_faces(self):
        from cad._internal.drawing_views import _plane_cut

        kept, faces = _plane_cut(_two_blocks(), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertEqual(len(kept.solids()), 2)
        self.assertEqual(len(faces), 2)
        self.assertAlmostEqual(sum(s.volume for s in kept.solids()), 1000.0, places=6)

    def test_a_split_that_loses_a_piece_is_run_again(self):
        from build123d import Shape

        from cad._internal.drawing_views import _plane_cut

        split, calls = _dropping(times=1)
        with mock.patch.object(Shape, "split", split):
            kept, faces = _plane_cut(_two_blocks(), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertGreaterEqual(len(calls), 2, "the short split was not run again")
        self.assertEqual(len(kept.solids()), 2)
        self.assertEqual(len(faces), 2)

    def test_a_split_that_keeps_losing_is_refused_never_drawn_short(self):
        from build123d import Shape

        from cad._internal.drawing_views import _plane_cut

        split, calls = _dropping(times=99)
        with mock.patch.object(Shape, "split", split), self.assertRaisesRegex(ValueError, "kept .* mm3 after three tries"):
            _plane_cut(_two_blocks(), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertEqual(len(calls), 3)

    def test_numerical_noise_on_curved_faces_is_not_a_loss(self):
        import warnings

        from build123d import Cylinder

        from cad._internal.drawing_views import _plane_cut

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            kept, faces = _plane_cut(Cylinder(5, 20), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertEqual(len(faces), 1)


if __name__ == "__main__":
    unittest.main()
