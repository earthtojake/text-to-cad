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


def stroke(text: str, x: float, y: float, extra: str = "", font: str = "(size 2 2) (thickness 0.3)",
           layer: str = '"F.Cu"') -> str:
    return f'(gr_text "{text}" (at {x} {y} 0) (layer {layer}) (uuid "{_uuid()}") (effects (font {font}){extra}))'


class DrawnCopper(unittest.TestCase):
    """Every text, text box, table, barcode and dimension on a copper layer is copper the router keeps its clearance
    from, to where KiCad draws it (each place below is KiCad 10.99's, measured with its own outline of the item,
    its bounding box or its DRC); a hidden text is none."""

    ITEMS = (
        # A stroke-font text: KiCad's letters reach x = 18.674 (wider than a Hershey box, which ends at 18.1).
        stroke("Wg|x", 15, 6),
        # A knockout: KiCad fills its letters' box grown by max(stroke / 2, height / 9) = 0.222 mm.
        stroke("H", 30, 6, layer='"F.Cu" knockout'),
        # A TrueType text: the outline KiCad saved with it.
        f'(gr_text "AB" (at 42 6 0) (layer "F.Cu") (uuid "{_uuid()}") (effects (font (face "Arial") (size 2 2) '
        '(thickness 0.3))) (render_cache "AB" 0 (polygon (pts (xy 40 5) (xy 44 5) (xy 44 7) (xy 40 7)))))',
        # A hidden text draws nothing.
        f'(gr_text "HIDDEN" (at 60 6 0) (layer "F.Cu") (hide yes) (uuid "{_uuid()}") (effects (font (size 2 2) '
        '(thickness 0.3))))',
        # A text box: its box, its border's stroke round it.
        f'(gr_text_box "AB" (start 5 15) (end 15 20) (margins 1 1 1 1) (layer "F.Cu") (uuid "{_uuid()}") (effects '
        '(font (size 1 1) (thickness 0.15)) (justify left top)) (border yes) (stroke (width 0.4) (type solid)))',
        # A table: each cell's box, its borders' stroke round it.
        f'(table (column_count 2) (uuid "{_uuid()}") (layer "F.Cu") (border (external yes) (header yes) (stroke (width '
        '0.3) (type solid))) (separators (rows yes) (cols yes) (stroke (width 0.2) (type solid))) (column_widths 5 5) '
        '(row_heights 3) (cells '
        + " ".join(f'(table_cell "C{n}" (start {25 + 5 * n} 15) (end {30 + 5 * n} 18) (margins 0.5 0.5 0.5 0.5) '
                   f'(span 1 1) (layer "F.Cu") (uuid "{_uuid()}") (effects (font (size 1 1) (thickness 0.15)) '
                   '(justify left top)))' for n in range(2)) + '))',
        # A barcode: its symbol round its anchor, its text's foot 1 + 1.125 text heights below it, and DRC keeps
        # other copper 1 mm from it.
        f'(barcode (at 50 17 0) (layer "F.Cu") (size 6 4) (text "HELLO") (text_height 1) (type qr) (ecc_level L) '
        f'(hide no) (knockout no) (uuid "{_uuid()}"))',
        # A dimension, its arrows drawn inward: they stand 2 x 1.27 mm past its crossbar's ends.
        f'(dimension (type orthogonal) (layer "F.Cu") (uuid "{_uuid()}") (pts (xy 70 15) (xy 80 20)) (height 3) '
        f'(orientation 0) (gr_text "10 mm" (at 75 21.5 0) (layer "F.Cu") (uuid "{_uuid()}") (effects (font (size 1 1) '
        '(thickness 0.15)))) (format (prefix "") (suffix "") (units 3) (units_format 1) (precision 4)) (style '
        '(thickness 0.2) (arrow_length 1.27) (text_position_mode 0) (arrow_direction inward) (extension_height 0.58642) '
        '(extension_offset 0.5) (keep_text_aligned yes)))',
        # A footprint's text box, the footprint turned a quarter round: placed through its frame.
        f'(footprint "F" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate 100 15) (rotate 90) (scale 1 1)) '
        f'(fp_text_box "FP" (start 0 0) (end 4 2) (margins 0.3 0.3 0.3 0.3) (angle 90) (layer "F.Cu") '
        f'(uuid "{_uuid()}") (effects (font (size 0.8 0.8) (thickness 0.12)) (justify left top)) (border yes) '
        '(stroke (width 0.2) (type solid))))',
    )

    def setUp(self) -> None:
        pads = (resistor("R1", 10, 40, 0, "A", "B"), resistor("R2", 100, 40, 0, "A", "C"))
        self.copper = read_copper(board(*pads, *self.ITEMS, width=120, height=50))
        self.router = Router(self.copper, RULES, [want("A")])
        self.clear = self.router._clear(want("A"), self.router._net("A"), self.router.layer_of["F.Cu"], None, None)

    def near(self, point, direction, keep=0.2) -> bool:
        """Whether a track of A may pass a hair inside its clearance (and half width) of ``point``, off it along
        ``direction``: False where ``point`` is copper the router sees."""
        gap = keep + 0.125 - 0.01
        x, y = point[0] + direction[0] * gap, point[1] + direction[1] * gap
        return self.clear((round(x * 1e6), round(y * 1e6)), (round(x * 1e6) + 2, round(y * 1e6)))

    def test_each_is_copper_to_where_kicad_draws_it(self) -> None:
        cases = {
            "a stroke-font text's last letter": ((18.674, 6.0), (1, 0), 0.2),
            "a knockout's margin": ((30.0, 6.0 + 1.0 + 0.222), (0, 1), 0.2),
            "a TrueType text's outline": ((44.0, 7.0), (1, 1), 0.2),
            "a text box's border": ((10.0, 20.2), (0, 1), 0.2),
            "a table's border": ((32.5, 18.15), (0, 1), 0.2),
            "a barcode's symbol, kept 1 mm from": ((53.0, 15.0), (1, -1), 1.0),
            "a barcode's text": ((50.0, 19.0 + 2.125), (0, 1), 1.0),
            "a dimension's inward arrow": ((70.0 - 2.54, 18.0), (-1, 0), 0.2),
            "a footprint's text box, turned with it": ((102.1, 13.0), (1, 0), 0.2),
        }
        for name, (point, (dx, dy), keep) in cases.items():
            norm = math.hypot(dx, dy)
            with self.subTest(name):
                self.assertFalse(self.near(point, (dx / norm, dy / norm), keep), name)
        self.assertTrue(self.near((60.0, 6.0), (0, 0)), "a hidden text is no copper")
        self.assertTrue(self.near((60.0, 30.0), (0, 0)), "nor is the board's bare middle")

    def test_a_truetype_text_with_no_outline_saved_is_refused_by_name(self) -> None:
        text = (f'(gr_text "AB" (at 42 6 0) (layer "F.Cu") (uuid "{_uuid()}") (effects (font (face "Arial") (size 2 2) '
                '(thickness 0.3))))')
        with self.assertRaises(ValueError) as caught:
            read_copper(board(text))
        self.assertIn("text 'AB' on F.Cu: its font is 'Arial'", str(caught.exception))
        self.assertIn("open and save the board in KiCad", str(caught.exception))


def masked(*items: str, setup: str = "(pad_to_mask_clearance 0.3)", **size) -> str:
    """A board whose pads' solder-mask openings reach 0.3 mm past their copper, past the 0.2 mm clearance."""
    return board(*items, **size).replace("(setup (pad_to_mask_clearance 0))", f"(setup {setup})")


class SolderMask(unittest.TestCase):
    """DRC's solder_mask_bridge fires where another net's copper lies in a pad's solder-mask opening (KiCad 10.99,
    measured: a track 0.25 mm from a pad whose mask expands 0.3 mm is a bridge, one 0.32 mm away is not; the pad's
    own margin, else its footprint's, else the board's), so new copper keeps the opening's reach from it."""

    #: R1.1 and R2.1 of A, either side of R3 (X and Y) on the straight line between them.
    PARTS = (resistor("R1", 5, 10, 0, "A", "B"), resistor("R2", 25, 10, 0, "A", "C"), resistor("R3", 15, 10, 90, "X", "Y"))

    def clear(self, text: str, layer: str = "F.Cu"):
        router = Router(read_copper(text), RULES, [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)), vias=0)])
        return router._clear(want("A"), router._net("A"), router.layer_of[layer], None, None)

    def passes(self, clear, gap: float) -> bool:
        """Whether a track of A may run straight down the right of R3's pads (0.95 x 0.8 mm, turned a quarter
        round), ``gap`` from their copper."""
        x = 15 + 0.475 + gap + 0.125
        return clear((round(x * 1e6), 5_000_000), (round(x * 1e6), 15_000_000))

    def test_new_copper_keeps_out_of_another_nets_opening(self) -> None:
        clear = self.clear(masked(*self.PARTS))
        self.assertFalse(self.passes(clear, 0.29), "inside R3's openings")
        self.assertTrue(self.passes(clear, 0.31))
        self.assertTrue(self.passes(self.clear(masked(*self.PARTS), "B.Cu"), 0.21), "R3 opens no mask on B.Cu")
        own = masked(*self.PARTS).replace('(net "X")', '(net "X") (solder_mask_margin 0.05)')
        self.assertFalse(self.passes(self.clear(own), 0.21), "R3.2's opening, the board's")
        own = own.replace('(net "Y")', '(net "Y") (solder_mask_margin 0.05)')
        self.assertTrue(self.passes(self.clear(own), 0.21), "the pads' own margins")

    def test_a_routed_track_keeps_the_opening_from_another_nets_pad(self) -> None:
        copper = read_copper(masked(*self.PARTS))
        router = Router(copper, RULES, [want("A")])
        done = router.run()
        self.assertTrue(done[0].routed, done[0].line())
        for track in router.tracks:
            a, b = (tuple(v / 1e6 for v in end) for end in (track.start, track.end))
            for pad in copper.pads:
                if pad.net != "A":
                    gap = min(shape.segment_distance(a, b) for shape in pad.copper) - track.width / 2
                    self.assertGreaterEqual(gap, 0.3 - 1e-6, (track, pad.ref))

    def test_untented_vias_whose_openings_the_clearance_cannot_hold_are_refused(self) -> None:
        text = masked(*self.PARTS, setup="(pad_to_mask_clearance 0.3) (tenting (front no) (back yes))")
        with self.assertRaises(ValueError) as caught:
            Router(read_copper(text), RULES, [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)))])
        self.assertIn("untented on F.Cu", str(caught.exception))
        self.assertIn("tent the board's vias, give the entry vias: 0", str(caught.exception))
        Router(read_copper(text), RULES, [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)), vias=0)])


if __name__ == "__main__":
    unittest.main()
