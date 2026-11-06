"""The router's core (``cad.kicad._routing``), with no KiCad: exact distances, the search, the pull-tight pass, and
the plan read and checked before anything is routed.

The boards are written here, small, in KiCad 11's syntax (footprints placed by a ``transform``), and read the way
``cad.kicad.route`` reads the open board's text; the rules are given as KiCad would give them. The routes are held
to an independent check: points sampled every 10 microns along each new track, each measured to every other
net's copper, every keep-out and the edge. KiCad's own DRC of routed boards is the KiCad suite's
(``tests/python/packages/kicad/test_route.py``).
"""

from __future__ import annotations

import math
import random
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

import numpy as np  # noqa: E402

from cad.kicad._route import _entries, _wants  # noqa: E402
from cad.kicad._routing.board import read_copper  # noqa: E402
from cad.kicad._routing.field import move_margin  # noqa: E402
from cad.kicad._routing import plan  # noqa: E402
from cad.kicad._routing.plan import Router, Want, pitch_for  # noqa: E402
from cad.kicad._routing.rules import NetClass, Rules, custom_limits  # noqa: E402
from cad.kicad._routing.shapes import Shape  # noqa: E402
from cad.kicad._routing.tighten import octolinear  # noqa: E402

DEFAULT = NetClass("Default", 0.2, 0.25, 0.8, 0.4)
POWER = NetClass("Power", 0.3, 0.5, 0.8, 0.4)
RULES = Rules({"VCC": POWER}, DEFAULT, min_clearance=0.15, min_track_width=0.15, edge_clearance=0.3,
              hole_clearance=0.25, hole_to_hole=0.5, min_via_diameter=0.6, min_via_drill=0.3, min_annulus=0.15)

_UUID = iter(range(1, 10 ** 6))


def _uuid() -> str:
    return f"0e5a0000-0000-4000-8000-{next(_UUID):012x}"


def resistor(ref: str, x: float, y: float, rotate: float, one: str, two: str, side: str = "F") -> str:
    """An 0603 resistor (two roundrect pads 0.8 x 0.95 mm, 1.65 mm apart) placed by a transform."""
    pads = "".join(
        f'(pad "{n}" smd roundrect (at {dx} 0 {rotate}) (size 0.8 0.95) (layers "{side}.Cu" "{side}.Mask") '
        f'(roundrect_rratio 0.25) (net "{net}") (uuid "{_uuid()}"))'
        for n, dx, net in (("1", -0.825, one), ("2", 0.825, two)))
    return (f'(footprint "R_0603" (layer "{side}.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate {rotate}) '
            f'(scale 1 1)) (property "Reference" "{ref}" (at 0 -1.4 0) (layer "{side}.SilkS") (uuid "{_uuid()}") '
            f'(effects (font (size 1 1) (thickness 0.15)))) {pads})')


def header(ref: str, x: float, y: float, nets: list[str]) -> str:
    """A 1 x N pin header, 2.54 mm pitch down the page: round through-hole pads 1.7 mm, 1 mm drills."""
    pads = "".join(f'(pad "{k + 1}" thru_hole circle (at 0 {k * 2.54}) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") '
                   f'(net "{net}") (uuid "{_uuid()}"))' for k, net in enumerate(nets))
    return (f'(footprint "Header" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate 0) '
            f'(scale 1 1)) (property "Reference" "{ref}" (at 0 -2 0) (layer "F.SilkS") (uuid "{_uuid()}") '
            f'(effects (font (size 1 1) (thickness 0.15)))) {pads})')


def keepout(points: list[tuple[float, float]], layers: str = '"F.Cu" "B.Cu"', tracks: bool = True, vias: bool = True) -> str:
    pts = " ".join(f"(xy {x} {y})" for x, y in points)
    flag = {True: "not_allowed", False: "allowed"}
    return (f'(zone (net 0) (net_name "") (layers {layers}) (uuid "{_uuid()}") (hatch edge 0.5) '
            f'(keepout (tracks {flag[tracks]}) (vias {flag[vias]}) (pads allowed) (copperpour allowed) (footprints allowed)) '
            f'(polygon (pts {pts})))')


def board(*items: str, width: float = 30.0, height: float = 20.0) -> str:
    """A two-layer board, its outline from (0, 0) to (``width``, ``height``), holding ``items``."""
    return (f'(kicad_pcb (version 20260901) (generator "pcbnew") (generator_version "10.99") (general (thickness 1.6)) '
            f'(paper "A4") (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user) (5 "F.SilkS" user) '
            f'(1 "F.Mask" user) (3 "B.Mask" user)) (setup (pad_to_mask_clearance 0)) '
            f'(gr_rect (start 0 0) (end {width} {height}) (stroke (width 0.1) (type default)) (fill no) '
            f'(layer "Edge.Cuts") (uuid "{_uuid()}")) {" ".join(items)})')


def want(net: str, layers=(("F.Cu", 1.0),), pads=None, width=0.25, clearance=0.2, vias=None, via_cost=2.0) -> Want:
    return Want(net, pads, tuple(layers), width, clearance, 0.8, 0.4, vias, via_cost)


def segment(text: str, net: str, a: tuple[float, float], b: tuple[float, float], width: float = 0.25,
            layer: str = "F.Cu") -> str:
    return (f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {width}) (layer "{layer}") (net "{net}") '
            f'(uuid "{_uuid()}"))')


def independent_check(case: unittest.TestCase, copper, rules: Rules, router: Router, wants: list[Want]) -> None:
    """Every new segment octolinear, and every point of it (every 10 microns) at its clearance from every other
    net's copper and hole, at least its half width from every track keep-out, and its edge clearance inside the
    board: measured by sampling, not by the router's own checker."""
    width = {w.net: w for w in wants}
    obstacles = []
    for pad in copper.pads:
        for shape in pad.copper:
            obstacles.append((pad.net, set(pad.layers), shape, rules.clearance(pad.net, pad.clearance)))
    for track in copper.tracks:
        obstacles.append((track.net, {track.layer}, track.shape, rules.clearance(track.net)))
    for new in router.tracks:
        a, b = (p / 1e6 for p in new.start), (p / 1e6 for p in new.end)
        obstacles.append((new.net, {new.layer}, Shape.segment(tuple(a), tuple(b), new.width / 2), rules.clearance(new.net)))
    keepouts = [(set(k.layers), k.shape) for k in copper.keepouts if k.tracks]
    edges = [Shape.segment(p, q, 0.0) for ring in copper.outline for p, q in zip(ring, ring[1:])]
    for new in router.tracks:
        case.assertTrue(octolinear(new.start, new.end), new)
        a, b = np.array(new.start) / 1e6, np.array(new.end) / 1e6
        half, need = new.width / 2, width[new.net].clearance
        t = np.linspace(0.0, 1.0, max(2, int(math.dist(a, b) / 0.01) + 1))
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        for net, layers, shape, keep in obstacles:
            if net != new.net and new.layer in layers:
                case.assertGreaterEqual(float(shape.grid_distance(x, y).min()) - half, max(keep, need) - 1e-6, (new, net))
        for layers, shape in keepouts:
            if new.layer in layers:
                case.assertGreaterEqual(float(shape.grid_distance(x, y).min()) - half, -1e-6, (new, "keep-out"))
        edge = min(float(e.grid_distance(x, y).min()) for e in edges)
        case.assertGreaterEqual(edge - half, rules.edge_clearance - 1e-6, new)
        case.assertTrue(np.all((x > 0) & (x < 30) & (y > 0) & (y < 20)), new)


class Shapes(unittest.TestCase):
    """Distances are the shape's own: the grid's, a point's and a segment's agree with dense sampling."""

    SHAPES = (Shape.point(1.0, 2.0, 0.4), Shape.segment((0.0, 0.0), (3.0, 1.0), 0.3),
              Shape.polygon([(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 2.5), (0.0, 1.0)], 0.2),
              Shape.arc_through((2.0, 0.0), (0.0, 2.0), (-2.0, 0.0), 0.125))

    def test_a_grid_and_a_point_measure_alike(self) -> None:
        X, Y = np.meshgrid(np.linspace(-3, 4, 29), np.linspace(-3, 4, 29))
        for shape in self.SHAPES:
            grid = shape.grid_distance(X, Y)
            for x, y, d in zip(X.ravel(), Y.ravel(), grid.ravel()):
                self.assertAlmostEqual(d, shape.point_distance(float(x), float(y)), places=9, msg=(shape.kind, x, y))

    def test_a_segment_is_as_far_as_its_nearest_point(self) -> None:
        rng = random.Random(7)
        for shape in self.SHAPES:
            for _ in range(60):
                a = (rng.uniform(-3, 4), rng.uniform(-3, 4))
                b = (rng.uniform(-3, 4), rng.uniform(-3, 4))
                t = np.linspace(0, 1, 2001)
                sampled = float(shape.grid_distance(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t).min())
                exact = shape.segment_distance(a, b)
                self.assertLessEqual(exact, sampled + 1e-9, (shape.kind, a, b))
                self.assertGreaterEqual(exact, sampled - math.dist(a, b) / 2000, (shape.kind, a, b))

    def test_a_move_between_two_nodes_with_room_is_clear_all_along(self) -> None:
        """The search tests nodes, never moves: a node with ``move_margin`` more room than a track needs makes
        every move to a neighbour with as much room clear along its whole length."""
        rng = random.Random(11)
        pitch = 0.1
        for _ in range(300):
            obstacle = Shape.polygon([(rng.uniform(-1, 1), rng.uniform(-1, 1)) for _ in range(3)], rng.uniform(0, 0.3))
            need = rng.uniform(0.1, 0.5)
            i, j = rng.randrange(-15, 15), rng.randrange(-15, 15)
            di, dj = rng.choice([(1, 0), (0, 1), (1, 1), (1, -1)])
            a, b = (i * pitch, j * pitch), ((i + di) * pitch, (j + dj) * pitch)
            margin = move_margin(need, pitch)
            if min(obstacle.point_distance(*a), obstacle.point_distance(*b)) < need + margin:
                continue
            self.assertGreaterEqual(obstacle.segment_distance(a, b), need - 1e-12)


class Routes(unittest.TestCase):
    """A plan routed on a small board: octolinear, every clearance kept, the same copper twice, a walled-in
    connection said by name, the copper already there kept and routed round."""

    def setUp(self) -> None:
        self.text = board(
            resistor("R1", 5, 8, 0, "A", "B"), resistor("R2", 25, 8, 0, "A", "C"),
            resistor("R3", 15, 3.5, 90, "B", "C"), resistor("R4", 15, 16, 90, "D", "VCC"),
            header("J1", 3, 12, ["D", "VCC", "B"]),
            # A wall of another net between R1 and R2, open at the bottom; a keep-out over the top of it.
            segment("", "E", (12.0, 5.5), (12.0, 12.0), width=1.0),
            keepout([(10.5, 0.5), (13.5, 0.5), (13.5, 5.5), (10.5, 5.5)]),
            # R5 inside a closed ring of keep-out, on both layers: no way out for its pads.
            resistor("R5", 26, 4, 0, "F", "G"), resistor("R6", 22, 17, 0, "F", "G"),
            keepout([(23.5, 1.5), (28.5, 1.5), (28.5, 6.5), (23.5, 6.5), (23.5, 5.7), (27.7, 5.7), (27.7, 2.3),
                     (24.3, 2.3), (24.3, 5.7), (23.5, 5.7)]),
        )
        self.copper = read_copper(self.text)

    def route(self, wants: list[Want]) -> tuple[Router, list]:
        router = Router(self.copper, RULES, wants)
        return router, router.run()

    def test_a_plan_is_routed_octolinear_and_clear(self) -> None:
        wants = [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 2.0))), want("B", layers=(("F.Cu", 1.0), ("B.Cu", 1.0))),
                 want("C"), want("VCC", width=0.5, clearance=0.3), want("D")]
        router, done = self.route(wants)
        self.assertEqual([True] * len(done), [c.routed for c in done], [c.line() for c in done])
        self.assertEqual({"A", "B", "C", "VCC", "D"}, {c.net for c in done})
        self.assertEqual({0.5}, {t.width for t in router.tracks if t.net == "VCC"}, "the entry's width")
        independent_check(self, self.copper, RULES, router, wants)

    def test_the_same_plan_gives_the_same_copper(self) -> None:
        wants = [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 2.0))), want("B", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)))]
        first, _ = self.route(wants)
        again, _ = self.route(wants)
        self.assertEqual((first.tracks, first.vias), (again.tracks, again.vias))
        self.assertTrue(first.tracks)

    def test_a_connection_with_no_way_is_said_by_name_and_the_rest_go_on(self) -> None:
        router, done = self.route([want("F", layers=(("F.Cu", 1.0), ("B.Cu", 1.0))), want("A")])
        self.assertEqual([False, True], [c.routed for c in done], [c.line() for c in done])
        self.assertIn("R5.1", done[0].line())
        self.assertIn("walled in", done[0].reason)
        self.assertTrue(all(t.net == "A" for t in router.tracks), "nothing of F written")

    def test_the_copper_on_the_board_is_routed_round(self) -> None:
        """Net A, on the top layer alone, goes round the wall of net E (a track already there) and the keep-out
        above it: longer than the straight 20 mm, and every clearance kept."""
        router, done = self.route([want("A")])
        self.assertTrue(done[0].routed, done[0].line())
        length = sum(math.dist(t.start, t.end) for t in router.tracks) / 1e6
        self.assertGreater(length, 20.0 + 2.0)
        independent_check(self, self.copper, RULES, router, [want("A")])

    def test_a_wall_is_named_by_what_it_is(self) -> None:
        router, done = self.route([want("F", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)))])
        self.assertIn("R5.1 is walled in by a keep-out", done[0].reason)

    def test_one_pair_of_pads_is_one_connection(self) -> None:
        router, done = self.route([want("B", pads=("R3.1", "J1.3"), layers=(("F.Cu", 1.0), ("B.Cu", 1.0)))])
        self.assertEqual(1, len(done))
        self.assertEqual(("R3.1", "J1.3"), done[0].between)
        self.assertTrue(done[0].routed, done[0].line())


def fine_pitch(ref: str, x: float, y: float, nets: list[str]) -> str:
    """A row of pads 0.3 x 0.775 mm at a 0.5 mm pitch (a TSSOP's side), down the page: a 0.2 mm track keeping
    0.2 mm leaves a pin straight out with 0.05 mm to spare, a lane narrower than a 0.1 mm grid."""
    pads = "".join(f'(pad "{k + 1}" smd roundrect (at 0 {k * 0.5}) (size 0.775 0.3) (layers "F.Cu" "F.Mask") '
                   f'(roundrect_rratio 0.25) (net "{net}") (uuid "{_uuid()}"))' for k, net in enumerate(nets))
    return (f'(footprint "TSSOP" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate 0) (scale 1 1)) '
            f'(property "Reference" "{ref}" (at 0 -2 0) (layer "F.SilkS") (uuid "{_uuid()}") '
            f'(effects (font (size 1 1) (thickness 0.15)))) {pads})')


class FinePitch(unittest.TestCase):
    def test_a_pin_whose_lane_is_narrower_than_the_grid_escapes_exactly(self) -> None:
        """The middle pin of a 0.5 mm-pitch row, off the grid by half its pitch, reaches a resistor 8 mm away: its
        free lane (0.07 mm, off every grid row) holds no node of the 0.1 mm grid, so the route leaves it by an elbow
        to a free node outside the pad, checked exactly. Without that escape there is no room for it."""
        nets = ["N1", "N2", "N3", "N4", "N5"]
        copper = read_copper(board(fine_pitch("U1", 10.05, 9.05, nets), resistor("R1", 18, 10, 0, "N3", "N9")))
        rules = Rules({}, NetClass("Default", 0.2, 0.2, 0.6, 0.3), min_clearance=0.1, min_track_width=0.1,
                      edge_clearance=0.3, hole_clearance=0.25, hole_to_hole=0.5)
        wants = [want("N3", width=0.2, clearance=0.2)]
        router = Router(copper, rules, wants)
        done = router.run()
        self.assertTrue(done[0].routed, done[0].line())
        self.assertIn((10_050_000, 10_050_000), {end for t in router.tracks for end in (t.start, t.end)}, "on its anchor")
        independent_check(self, copper, rules, router, wants)
        with mock.patch.object(plan, "ESCAPES", 0):
            done = Router(copper, rules, wants).run()
        self.assertIn("U1.3 has no room", done[0].reason)

    def test_the_pitch_is_a_quarter_of_the_narrowest_track_and_its_clearance(self) -> None:
        self.assertEqual(0.1, pitch_for([0.25, 0.5], [0.2, 0.3]))
        self.assertEqual(0.075, pitch_for([0.15], [0.15]))
        self.assertEqual(0.025, pitch_for([0.05], [0.05]))
        self.assertEqual(0.02, pitch_for([0.03], [0.03]), "and never finer than 0.02 mm")


class Plans(unittest.TestCase):
    """A plan is read and checked whole before anything is routed: each mistake said in one line, naming what
    to give."""

    def setUp(self) -> None:
        self.copper = read_copper(board(resistor("R1", 5, 10, 0, "A", "B"), resistor("R2", 25, 10, 0, "A", "C"),
                                        resistor("R3", 15, 15, 0, "B", "C", side="B")))

    def wants(self, plan, **options):
        return _wants(_entries(plan, {"layers": None, **options}), self.copper, RULES)

    def refused(self, plan, said: str, **options) -> None:
        with self.assertRaises(ValueError) as caught:
            self.wants(plan, **options)
        self.assertIn(said, str(caught.exception))

    def test_no_plan_is_refused_naming_what_to_give(self) -> None:
        for plan in ([], None, "A"):
            self.refused(plan, "route needs a plan")
        self.refused(["A"], "has no layers")

    def test_an_entry_is_a_net_a_pair_of_pads_or_a_dict_of_known_keys(self) -> None:
        self.refused([{"net": "A", "layer": ["F.Cu"]}], "unknown key 'layer'")
        self.refused([{"net": "A", "pads": ("R1.1", "R2.1"), "layers": ["F.Cu"]}], "a net or a pair of pads")
        self.refused([("R1.1", "R1.2")], "a connection joins two pads of one net", layers=["F.Cu"])
        self.refused(["Z"], "no pad of the board is on a net 'Z'", layers=["F.Cu"])
        self.refused(["A"], "'In1.Cu' is not a copper layer of this board", layers=["In1.Cu"])
        self.refused(["B"], "R3.1 is on no layer it may use", layers=["F.Cu"])
        self.refused([{"net": "A", "layers": ["F.Cu"], "clearance": 0.1}], "under the 0.2 mm DRC holds A to")
        self.refused([{"net": "A", "layers": ["F.Cu"], "width": 0.1}], "under the board's least track width")
        self.refused([{"net": "A", "layers": ["F.Cu"], "vias": 1.5}], "vias is a whole number")

    def test_the_options_and_their_defaults(self) -> None:
        (a, b, c) = self.wants(["#net:A", ("#R3.1", "R1.2"), {"net": "C", "layers": {"F.Cu": 1, "B.Cu": 3}, "vias": 0}],
                               layers=["F.Cu", "B.Cu"], via_cost=3)
        self.assertEqual(("A", None, (("F.Cu", 1.0), ("B.Cu", 1.0)), 0.25, 0.2, 3.0), (a.net, a.pads, a.layers, a.width,
                                                                                     a.clearance, a.via_cost))
        self.assertEqual(("B", ("R3.1", "R1.2")), (b.net, b.pads))
        self.assertEqual(((("F.Cu", 1.0), ("B.Cu", 3.0)), 0), (c.layers, c.vias))

    def test_custom_rules_are_kept_everywhere_or_refused_by_name(self) -> None:
        limits, refused = custom_limits([("hv", "CRCT_CLEARANCE", 0.5), ("edge", "CRCT_EDGE_CLEARANCE", 0.4),
                                         ("no", "CRCT_DISALLOW", 0.0), ("len", "CRCT_LENGTH", 10.0),
                                         ("power", "CRCT_TRACK_WIDTH", 1.5)])
        self.assertEqual({"clearance": 0.5, "edge_clearance": 0.4}, limits)
        self.assertEqual(["no"], refused)
        self.assertEqual(0.5, RULES.with_custom(limits).clearance("A"))


class Keepouts(unittest.TestCase):
    def test_a_footprints_own_keepout_is_in_its_frame(self) -> None:
        """A footprint placed by a transform holds its own zones in its frame, as KiCad places them: a keep-out
        drawn round (0, 0) of a footprint at (10, 5) turned 90 degrees keeps out round (10, 5)."""
        zone = keepout([(-1, -2), (1, -2), (1, 0), (-1, 0)])
        text = board(f'(footprint "K" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate 10 5) (rotate 90) '
                     f'(scale 1 1)) {zone})')
        found = read_copper(text).keepouts
        self.assertEqual(1, len(found))
        box = found[0].shape.box
        self.assertEqual((8.0, 4.0, 10.0, 6.0), tuple(round(v, 6) for v in box))


if __name__ == "__main__":
    unittest.main()
