"""The router's copper is the same bits on Linux, macOS and Windows: a digest held on every CI OS.

``cad.kicad.route`` promises that the same board and plan give the same copper. Between processes on one machine
that is plain; across platforms it holds only because nothing between the board's text and a decision the router
makes goes through the C library's sin, cos, atan2, acos or hypot, which glibc, Apple's libm and the MSVC runtime
round differently in the last bit. The angles are ``geometry``'s own, IEEE-754's + - * / and sqrt alone, and
the arcs' sweeps are cross-product tests. This board reaches each of those paths: a footprint at 0 degrees, one at
37.3 and one at 90, an arc track to route round, an outline with arc corners (the edge's clearance field), and a
plan of four nets on two layers that needs vias.

The digest is of the new copper alone (sorted tracks and vias, integer nanometres). It changes only when the router
or the board readers change what they route, on purpose: then run this file, read the new digest from the failure,
check the copper is what the change meant, and commit the new constant with that change. Never change it to make
one platform pass: a digest that differs on one OS is the bug this test is here to catch.
"""

from __future__ import annotations

import hashlib
import math
import random
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad.geometry import atan2, cos_sin, cos_sin_degrees, rotate  # noqa: E402
from cad.kicad._routing.board import read_copper  # noqa: E402
from cad.kicad._routing.plan import Router, Want  # noqa: E402
from cad.kicad._routing.rules import NetClass, Rules  # noqa: E402

DIGEST = "c7a06ef108ab0c97ce3969f1deee4aa6b5e7704e851dc639d5b67f6dcba2a0f9"

RULES = Rules({}, NetClass("Default", 0.2, 0.25, 0.8, 0.4), min_clearance=0.15, min_track_width=0.15,
              edge_clearance=0.3, hole_clearance=0.25, hole_to_hole=0.5, min_via_diameter=0.6, min_via_drill=0.3,
              min_annulus=0.15)


def _pad(number: str, x: float, y: float, angle: float, net: str) -> str:
    return (f'(pad "{number}" smd roundrect (at {x} {y} {angle}) (size 0.8 0.95) (layers "F.Cu" "F.Mask") '
            f'(roundrect_rratio 0.25) (net "{net}"))')


def _footprint(ref: str, x: float, y: float, angle: float, pads: str) -> str:
    return (f'(footprint "Part" (layer "F.Cu") (transform (translate {x} {y}) (rotate {angle}) (scale 1 1)) '
            f'(property "Reference" "{ref}" (at 0 -2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15)))) '
            f'{pads})')


def _edge(head: str, *points: tuple[float, float]) -> str:
    keys = ("start", "mid", "end") if head == "gr_arc" else ("start", "end")
    at = " ".join(f"({key} {x} {y})" for key, (x, y) in zip(keys, points))
    return f'({head} {at} (stroke (width 0.1) (type default)) (layer "Edge.Cuts"))'


def board() -> str:
    """A 24 x 18 mm two-layer board, its corners arcs of 3 mm (their mid points as KiCad writes them, to the
    nanometre): R1 at 0 degrees, U1 at 37.3, R2 at 90, a 4-pad row J1, and an arc track of net E across the board,
    too near the edge at both ends to pass, between U1 and R2: net D, from U1 and J1 to R2, goes under it."""
    r, w, h = 3.0, 24.0, 18.0
    k = round(r - r * math.sqrt(0.5), 6)  # the corner arcs' mid points, 45 degrees round
    outline = [
        _edge("gr_line", (r, 0), (w - r, 0)), _edge("gr_arc", (w - r, 0), (w - k, k), (w, r)),
        _edge("gr_line", (w, r), (w, h - r)), _edge("gr_arc", (w, h - r), (w - k, h - k), (w - r, h)),
        _edge("gr_line", (w - r, h), (r, h)), _edge("gr_arc", (r, h), (k, h - k), (0, h - r)),
        _edge("gr_line", (0, h - r), (0, r)), _edge("gr_arc", (0, r), (k, k), (r, 0)),
    ]
    parts = [
        _footprint("R1", 5.0, 5.0, 0, _pad("1", -0.825, 0, 0, "A") + _pad("2", 0.825, 0, 0, "B")),
        _footprint("U1", 12.5, 7.5, 37.3, "".join(_pad(str(n + 1), x, y, 37.3, net) for n, (x, y, net) in enumerate(
            ((-1.3, -0.9, "A"), (1.3, -0.9, "B"), (-1.3, 0.9, "C"), (1.3, 0.9, "D"))))),
        _footprint("R2", 5.0, 14.5, 90, _pad("1", -0.825, 0, 90, "D") + _pad("2", 0.825, 0, 90, "F")),
        _footprint("J1", 20.0, 6.0, 0, "".join(_pad(str(n + 1), 0, -3.0 + 2.0 * n, 0, net)
                                                for n, net in enumerate(("B", "A", "C", "D")))),
    ]
    arc = '(arc (start 0.3 11.8) (mid 12 11) (end 23.7 11.8) (width 0.25) (layer "F.Cu") (net "E"))'
    return ('(kicad_pcb (version 20260901) (generator "pcbnew") (generator_version "10.99") (general (thickness 1.6)) '
            '(paper "A4") (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user) (5 "F.SilkS" user) '
            '(1 "F.Mask" user) (3 "B.Mask" user)) (setup (pad_to_mask_clearance 0)) '
            f'{" ".join(outline)} {" ".join(parts)} {arc})')


def copper_digest() -> tuple[str, list]:
    """The plan routed, and the digest of its new copper: sha256 of the sorted tracks (net, layer, width, ends) and
    vias (net, centre, diameter, drill), every length in integer nanometres."""
    layers = (("F.Cu", 1.0), ("B.Cu", 1.5))
    wants = [Want(net, None, layers, 0.25, 0.2, 0.8, 0.4, None, 2.0) for net in ("A", "B", "C", "D")]
    router = Router(read_copper(board()), RULES, wants)
    done = router.run()
    tracks = sorted((t.net, t.layer, round(t.width * 1e6), *t.start, *t.end) for t in router.tracks)
    vias = sorted((v.net, *v.at, round(v.diameter * 1e6), round(v.drill * 1e6)) for v in router.vias)
    return hashlib.sha256(repr((tracks, vias)).encode()).hexdigest(), [done, tracks, vias]


class RoutingIsTheSameEverywhere(unittest.TestCase):
    def test_the_copper_is_the_committed_digest(self) -> None:
        digest, (done, tracks, vias) = copper_digest()
        self.assertTrue(all(connection.routed for connection in done), done)
        self.assertTrue(vias, "the plan should need a via: this board no longer reaches the via path")
        self.assertTrue(any(t[1] == "B.Cu" for t in tracks), "the plan should reach the second layer")
        self.assertEqual(digest, DIGEST, f"the router's copper changed: {len(tracks)} tracks, {len(vias)} vias. If "
                         "that is on purpose, check the copper and commit the new digest (this file's docstring); if "
                         "it differs on one OS only, something between the board and a decision is not IEEE")

    def test_the_angles_agree_with_the_c_library_to_its_last_bits(self) -> None:
        """cos_sin and atan2 within two units in the last place of the C library's; cos_sin_degrees within 2e-15,
        since the library's own answer is off by up to 9e-16 at 720 degrees from rounding the angle to radians
        first (this module reduces the degrees exactly)."""
        rng = random.Random(7)

        def close(mine: float, theirs: float) -> bool:
            return abs(mine - theirs) <= 2 * math.ulp(max(abs(mine), abs(theirs), 1e-300))

        for _ in range(2000):
            x = rng.uniform(-10.0, 10.0)
            c, s = cos_sin(x)
            self.assertTrue(close(c, math.cos(x)) and close(s, math.sin(x)), x)
            d = round(rng.uniform(-720.0, 720.0), rng.choice((0, 1, 3, 6)))
            c, s = cos_sin_degrees(d)
            self.assertLessEqual(max(abs(c - math.cos(math.radians(d))), abs(s - math.sin(math.radians(d)))), 2e-15, d)
            y, x = rng.uniform(-5.0, 5.0), rng.uniform(-5.0, 5.0)
            self.assertTrue(close(atan2(y, x), math.atan2(y, x)), (y, x))

    def test_a_quarter_turn_is_exact(self) -> None:
        for degrees, expected in ((0, (1.0, 0.0)), (90, (0.0, 1.0)), (180, (-1.0, 0.0)), (270, (0.0, -1.0)),
                                  (-90, (0.0, -1.0)), (450, (0.0, 1.0)), (-360, (1.0, 0.0))):
            self.assertEqual(cos_sin_degrees(degrees), expected, degrees)
        self.assertEqual(rotate(1.25, -0.5, 90), (-0.5, -1.25))
        self.assertEqual((atan2(0.0, -1.0), atan2(2.0, 0.0), atan2(1.0, 1.0)), (math.pi, math.pi / 2, math.pi / 4))


if __name__ == "__main__":
    unittest.main()
