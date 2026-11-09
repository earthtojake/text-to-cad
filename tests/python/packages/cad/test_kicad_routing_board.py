"""The board as the router reads it (``cad.kicad._routing.board``), with no KiCad: the copper it sees and where a
track may end in it, held to the shapes KiCad draws.

The boards are written here, small, in KiCad's syntax, as ``test_kicad_routing`` writes them (its helpers); what
KiCad's own DRC makes of routed boards is the KiCad suite's (``tests/python/packages/kicad/test_route.py``).
"""

from __future__ import annotations

import math
import unittest

from tests.python.packages.cad.test_kicad_routing import RULES, _uuid, board, resistor, want
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.kicad._routing.board import read_copper  # noqa: E402
from cad.kicad._routing.plan import Router  # noqa: E402


def footprint(ref: str, x: float, y: float, pads: str) -> str:
    return (f'(footprint "F" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate 0) (scale 1 1)) '
            f'(property "Reference" "{ref}" (at 0 -3 0) (layer "F.SilkS") (uuid "{_uuid()}") '
            f'(effects (font (size 1 1) (thickness 0.15)))) {pads})')


def in_roundrect(point, center, size, radius, slack=1e-9) -> bool:
    """Whether ``point`` lies in the rectangle ``size`` round ``center``, its corners rounded by ``radius``."""
    dx = max(abs(point[0] - center[0]) - (size[0] / 2 - radius), 0.0)
    dy = max(abs(point[1] - center[1]) - (size[1] / 2 - radius), 0.0)
    return math.hypot(dx, dy) <= radius + slack


class Padstacks(unittest.TestCase):
    #: J1.1: F.Cu a 1.2 mm square; B.Cu (its padstack) a 1.4 x 1 mm rounded rectangle of its own offset, smaller
    #: than the square below it and reaching past it to the right.
    PAD = ('(pad "1" thru_hole rect (at 0 0) (size 1.2 1.2) (drill 0.3) (layers "*.Cu" "*.Mask") (net "P") '
           '(padstack (mode front_inner_back) (layer "B.Cu" (shape roundrect) (size 1.4 1) (offset 0.5 0.2) '
           f'(roundrect_rratio 0.25))) (uuid "{_uuid()}"))')

    def test_each_layer_is_drawn_at_its_own_offset_and_a_track_ends_in_its_copper(self) -> None:
        """Every layer's shape is copper at its own offset, and a track routed on B.Cu may end only where B.Cu's
        copper is: a disc round the pad's anchor no larger than how deep it lies in B.Cu's shape (0.2 mm)."""
        copper = read_copper(board(footprint("J1", 10, 10, self.PAD), resistor("R1", 20, 10, 0, "P", "Q", side="B")))
        pad = copper.pad("J1.1")
        b_cu = ((10.5, 10.2), (1.4, 1.0), 0.25)
        self.assertTrue(any(shape.contains(11.15, 10.2) for shape in pad.copper), "B.Cu's shape, at its own offset")
        self.assertEqual((10.0, 10.0), pad.anchor)
        self.assertEqual(1, len(pad.inner))
        self.assertAlmostEqual(0.2, pad.inner[0].radius, places=9)

        router = Router(copper, RULES, [want("P", layers=(("B.Cu", 1.0),))])
        b = router.layer_of["B.Cu"]
        window = router._window([], None)
        items = [item for item in router._own["P"] if item.pad is pad]
        found = router._terminals(items, window, [b])
        self.assertTrue(found, "the pad has somewhere a track may end")
        for state in found:
            x, y = (value / 1e6 for value in router._node_nm(window, state % (window.nx * window.ny)))
            self.assertTrue(in_roundrect((x, y), *b_cu), (x, y))

    def test_a_padstack_with_no_point_in_every_layers_copper_is_refused_by_name(self) -> None:
        pad = self.PAD.replace("(size 1.4 1) (offset 0.5 0.2)", "(size 0.4 0.4) (offset 0.5 0.2)")
        with self.assertRaises(ValueError) as caught:
            read_copper(board(footprint("J1", 10, 10, pad)))
        said = str(caught.exception)
        self.assertIn("pad J1.1", said)
        self.assertIn("give its layers' shapes a common point", said)


class Keepouts(unittest.TestCase):
    def test_a_keepouts_arc_is_kept_out_to_the_true_arc_not_its_chords(self) -> None:
        """A rule area's outline arc (radius 50.5 mm, its chord 20 mm) is read as chords inside it and the
        keep-out grown past them: every point a micron inside the true arc (and inside the area) is in the
        router's keep-out, where the arc passes its chords by up to 0.11 mm sampled every 10 degrees."""
        zone = (f'(zone (net 0) (net_name "") (layers "F.Cu") (uuid "{_uuid()}") (hatch edge 0.5) (keepout (tracks '
                'not_allowed) (vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed)) (polygon (pts '
                '(xy 0 10) (xy 20 10) (arc (start 20 10) (mid 10 9) (end 0 10)))))')
        keepout, = read_copper(board(zone)).keepouts
        cx, cy, r = 10.0, 59.5, 50.5
        first, last = math.atan2(10 - cy, 0 - cx), math.atan2(10 - cy, 20 - cx)
        for k in range(201):
            angle = first + (last - first) * k / 200
            x, y = cx + (r - 1e-3) * math.cos(angle), cy + (r - 1e-3) * math.sin(angle)
            if y < 10 - 1e-3:
                self.assertTrue(keepout.shape.contains(x, y), (x, y))


if __name__ == "__main__":
    unittest.main()
