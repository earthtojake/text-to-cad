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
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

import numpy as np  # noqa: E402

from cad.kicad._route import _entries, _rules, _wants, route  # noqa: E402
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
    # No end left dangling: each end of a new track is in a pad of its net, on a via of it, or where another
    # track of it ends (KiCad joins tracks end to end, and calls an end on another track's middle dangling).
    ends = {}
    for new in router.tracks:
        for end in (new.start, new.end):
            ends[(new.net, end)] = ends.get((new.net, end), 0) + 1
    vias = {(via.net, via.at) for via in router.vias}
    for (net, end), count in ends.items():
        x, y = end[0] / 1e6, end[1] / 1e6
        in_pad = any(pad.net == net and any(shape.point_distance(x, y) <= 1e-9 for shape in pad.copper)
                     for pad in copper.pads)
        case.assertTrue(in_pad or (net, end) in vias or count > 1, (net, end))


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


class Ends(unittest.TestCase):
    def test_a_route_ends_in_its_pad_where_the_pads_anchor_lies_outside_its_copper(self) -> None:
        """An SMD pad's copper may be offset past its anchor (KiCad's ``(at)``): the route ends in the copper, not on
        the anchor beside it, so no end is left dangling outside the pad."""
        pad = (f'(pad "1" smd rect (at 0 0 90) (size 0.8 0.8) (drill (offset 1.5 0)) (layers "F.Cu" "F.Mask") '
               f'(net "A") (uuid "{_uuid()}"))')
        part = (f'(footprint "Offset" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate 8 10) (rotate 90) '
                f'(scale 1 1)) (property "Reference" "U1" (at 0 -2 0) (layer "F.SilkS") (uuid "{_uuid()}") '
                f'(effects (font (size 1 1) (thickness 0.15)))) {pad})')
        copper = read_copper(board(part, resistor("R1", 20, 12, 0, "A", "B")))
        (box,) = [shape.box for shape in copper.pad("U1.1").copper]
        self.assertEqual((7.6, 8.1, 8.4, 8.9), tuple(round(v, 6) for v in box), "the copper offset, turned with its pad")
        router = Router(copper, RULES, [want("A")])
        done = router.run()
        self.assertTrue(done[0].routed, done[0].line())
        independent_check(self, copper, RULES, router, [want("A")])


class ViaLimit(unittest.TestCase):
    def test_a_via_limit_holds_for_the_whole_entry(self) -> None:
        """Three pads of a net on the front, each between walls of another net there: each connection takes two
        vias, so a net limited to two joins two of its pads and says the third has no way within the vias left."""
        walls = [segment("", "W", (x, -1.0), (x, 7.0), width=1.0) for x in (6.0, 12.0)]
        pads = [resistor(f"R{k}", 6 * k - 3, 3, 0, "A", f"N{k}") for k in (1, 2, 3)]
        copper = read_copper(board(*walls, *pads, width=18.0, height=6.0))
        router = Router(copper, RULES, [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)), vias=2)])
        done = router.run()
        self.assertEqual([True, False], [c.routed for c in done], [c.line() for c in done])
        self.assertEqual(2, len(router.vias))
        self.assertIn("with at most 0 vias left of the entry's 2", done[1].reason)

    def test_every_entry_answers_a_line_even_with_nothing_to_route(self) -> None:
        copper = read_copper(board(resistor("R1", 5, 10, 0, "B", "A"), resistor("R2", 9, 10, 0, "A", "C"),
                                   segment("", "A", (5.825, 10.0), (8.175, 10.0))))
        done = Router(copper, RULES, [want("A"), want("B")]).run()
        self.assertEqual(["A: R1.2 to R2.1: already joined by the copper on the board",
                          "B: R1.1: the net's one pad on the board: nothing to route"], [c.line() for c in done])

    def test_a_search_past_the_memory_cap_is_refused_before_anything_is_routed(self) -> None:
        """Each via a limit allows is another copy of the search's states: a limit whose search would not fit the
        router's memory is refused up front, naming both parts."""
        copper = read_copper(board(resistor("R1", 5, 10, 0, "A", "B"), resistor("R2", 25, 10, 0, "A", "C")))
        with self.assertRaises(ValueError) as caught:
            Router(copper, RULES, [want("A", layers=(("F.Cu", 1.0), ("B.Cu", 1.0)), vias=5000)])
        self.assertIn("MB for its largest search", str(caught.exception))


class LayerChanges(unittest.TestCase):
    def test_a_blind_via_changes_layer_only_between_the_layers_it_joins(self) -> None:
        """A blind via of the net joins F.Cu to In1.Cu, so a route may change between those two there for nothing,
        never to B.Cu: with no via of its own allowed, a pad on the back is out of reach; allowed vias, it places
        one."""
        text = board(resistor("R1", 3, 3, 0, "A", "N1"), resistor("R2", 11, 3, 0, "A", "N2", side="B"),
                     segment("", "A", (2.175, 3.0), (2.175, 5.0)), segment("", "A", (2.175, 5.0), (6.0, 5.0)),
                     f'(via blind (at 6 5) (size 0.8) (drill 0.4) (layers "F.Cu" "In1.Cu") (net "A") (uuid "{_uuid()}"))',
                     width=14.0, height=7.0)
        copper = read_copper(text.replace('(layers (0 "F.Cu" signal) (2 "B.Cu" signal)',
                                          '(layers (0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)'))
        self.assertEqual(("F.Cu", "In1.Cu"), copper.vias[0].layers)
        layers = (("F.Cu", 1.0), ("In1.Cu", 1.0), ("B.Cu", 1.0))
        done = Router(copper, RULES, [want("A", layers=layers, vias=0)]).run()
        self.assertFalse(done[0].routed, done[0].line())
        router = Router(copper, RULES, [want("A", layers=layers)])
        done = router.run()
        self.assertTrue(done[0].routed, done[0].line())
        self.assertEqual(1, len(router.vias))


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

    def test_a_board_without_a_closed_outline_is_refused_before_anything_is_routed(self) -> None:
        class Open:  # the open board, as far as route reads it before the rules
            def __init__(self, text: str) -> None:
                self.text = text

            def get_as_string(self) -> str:
                return self.text

        with self.assertRaises(TypeError) as caught:
            route("board.kicad_pcb", ["A"], layers=["F.Cu"])
        self.assertIn("the board a kicad_pcb.edit block has open", str(caught.exception))
        bare = board(resistor("R1", 5, 10, 0, "A", "B")).replace('(layer "Edge.Cuts")', '(layer "Dwgs.User")')
        with self.assertRaises(ValueError) as caught:
            route(Open(bare), ["A"], layers=["F.Cu"])
        self.assertIn("Edge.Cuts draws none", str(caught.exception))
        broken = board(resistor("R1", 5, 10, 0, "A", "B")).replace(
            "(gr_rect (start 0 0) (end 30.0 20.0)", "(gr_line (start 0 0) (end 30 0)")
        with self.assertRaises(ValueError) as caught:
            route(Open(broken), ["A"], layers=["F.Cu"])
        self.assertIn("does not close: it ends apart at (0, 0), (30, 0)", str(caught.exception))

    def test_custom_rules_are_kept_everywhere_or_refused_by_name(self) -> None:
        limits, refused = custom_limits([("hv", "CRCT_CLEARANCE", 0.5), ("edge", "CRCT_EDGE_CLEARANCE", 0.4),
                                         ("no", "CRCT_DISALLOW", 0.0), ("len", "CRCT_LENGTH", 10.0),
                                         ("power", "CRCT_TRACK_WIDTH", 1.5), ("is", "CRCT_ASSERTION", 0.0)])
        self.assertEqual({"clearance": 0.5, "edge_clearance": 0.4}, limits)
        self.assertEqual(["is", "no"], refused)
        self.assertEqual(0.5, RULES.with_custom(limits).clearance("A"))


class Edges(unittest.TestCase):
    def test_the_edge_is_kept_from_the_true_arc_not_its_chords(self) -> None:
        """The outline is read as chords within CHORD_TOLERANCE of its arcs, and a circular cutout's chords lie
        inside the circle, so the board's true edge passes each chord's middle on the board's side. A track kept
        its edge clearance from the chords alone would come short of it there: a track parallel to each chord, a
        micron short of the clearance from the true circle, is refused, even with KiCad's arc error at nothing;
        one a few microns past it is allowed."""
        cx, cy, r = 15.0, 10.0, 3.0
        cut = (f'(gr_circle (center {cx} {cy}) (end {cx + r} {cy}) (stroke (width 0.1) (type default)) (fill no) '
               f'(layer "Edge.Cuts") (uuid "{_uuid()}"))')
        copper = read_copper(board(resistor("R1", 4, 4, 0, "A", "B"), resistor("R2", 26, 16, 0, "A", "C"), cut))
        rules = replace(RULES, max_error=0.0)
        router = Router(copper, rules, [want("A")])
        clear = router._clear(want("A"), router._net("A"), 0, None, None)
        ring = next(ring for ring in copper.outline if max(math.dist(p, (cx, cy)) for p in ring) < r + 1e-6)
        need = rules.edge_clearance + 0.125  # the edge clearance and the track's half width
        for (px, py), (qx, qy) in zip(ring, ring[1:]):
            mx, my = (px + qx) / 2 - cx, (py + qy) / 2 - cy
            ux, uy = mx / math.hypot(mx, my), my / math.hypot(mx, my)
            tx, ty = qx - px, qy - py
            tx, ty = tx / math.hypot(tx, ty) * 0.02, ty / math.hypot(tx, ty) * 0.02
            for gap, ok in ((need - 0.001, False), (need + 0.007, True)):
                ox, oy = cx + ux * (r + gap), cy + uy * (r + gap)
                a, b = (round((ox - tx) * 1e6), round((oy - ty) * 1e6)), (round((ox + tx) * 1e6), round((oy + ty) * 1e6))
                self.assertEqual(ok, clear(a, b), (gap, a, b))


class CustomPads(unittest.TestCase):
    @staticmethod
    def pad(primitives: str) -> str:
        pad = (f'(pad "1" smd custom (at 0 0) (size 0.5 0.5) (layers "F.Cu") (net "A") (options (clearance outline) '
               f'(anchor circle)) (primitives {primitives}) (uuid "{_uuid()}"))')
        return board(f'(footprint "C" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate 10 10) (rotate 0) (scale 1 1)) '
                     f'(property "Reference" "U1" (at 0 -2 0) (layer "F.SilkS") (uuid "{_uuid()}") '
                     f'(effects (font (size 1 1) (thickness 0.15)))) {pad})')

    def test_a_curve_is_copper_all_along_and_a_primitive_it_cannot_read_is_refused(self) -> None:
        """A custom pad's Bezier stroke is copper the router sees, to its true curve's edge (its chords grown by
        how far the curve strays from them); a proxy (the number's box) draws none; a primitive the router does not
        know is refused naming the pad, never copper left out."""
        controls = ((0.0, 0.0), (1.0, -2.0), (3.0, 2.0), (4.0, 0.0))
        pts = " ".join(f"(xy {x} {y})" for x, y in controls)
        copper = read_copper(self.pad(f"(gr_curve (pts {pts}) (width 0.2)) (gr_bbox (start -9 -9) (end 9 9))"))
        shapes = copper.pad("U1.1").copper
        for t in np.linspace(0.0, 1.0, 401):
            u = 1 - t
            x = 10 + sum(c * k for c, k in zip((u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3), (p[0] for p in controls)))
            y = 10 + sum(c * k for c, k in zip((u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3), (p[1] for p in controls)))
            dx = 3 * (u * u * (controls[1][0] - controls[0][0]) + 2 * u * t * (controls[2][0] - controls[1][0])
                      + t * t * (controls[3][0] - controls[2][0]))
            dy = 3 * (u * u * (controls[1][1] - controls[0][1]) + 2 * u * t * (controls[2][1] - controls[1][1])
                      + t * t * (controls[3][1] - controls[2][1]))
            nx, ny = -dy / math.hypot(dx, dy), dx / math.hypot(dx, dy)
            for side in (0.1, -0.1):  # the stroke's two edges
                self.assertEqual(0.0, min(s.point_distance(x + side * nx, y + side * ny) for s in shapes), t)
        self.assertLess(max(s.box[2] for s in shapes), 14.2, "the number's box is no copper")
        with self.assertRaises(ValueError) as caught:
            read_copper(self.pad("(gr_squiggle (start 0 0) (end 1 1))"))
        self.assertIn("pad U1.1: its primitive gr_squiggle", str(caught.exception))


class ApiError(Exception):
    """KiPy's, by name: what a KiCad without a request answers."""


class OpenBoard:
    """The open board as far as ``_rules`` asks it, on a KiCad that cannot give its custom rules."""

    def __init__(self, folder: str) -> None:
        self.document = SimpleNamespace(project=SimpleNamespace(path=folder, name="b"))

    def get_nets(self) -> list:
        return [SimpleNamespace(name="")]

    def get_netclass_for_nets(self, nets) -> dict:
        found = SimpleNamespace(name="Default", constituents=[], clearance=200_000, track_width=250_000,
                                via_diameter=800_000, via_drill=400_000)
        return {"": found}

    def get_design_rules(self):
        return SimpleNamespace(rules=SimpleNamespace(constraints=SimpleNamespace(
            min_clearance=0, min_track_width=0, copper_edge_clearance=0, hole_clearance=0, hole_to_hole_min=0,
            min_via_size=0, min_through_drill=0, min_via_annular_width=0)))

    def get_custom_design_rules(self):
        raise ApiError("no such request")


class KiCadRules(unittest.TestCase):
    def test_custom_rules_kicad_cannot_give_are_refused_never_dropped(self) -> None:
        """A KiCad whose API cannot give the custom rules routes a board without a .kicad_dru as ever, and refuses one
        with rules, naming the file: never routed by its netclasses alone."""
        with tempfile.TemporaryDirectory() as folder:
            board = OpenBoard(folder)
            self.assertAlmostEqual(0.2, _rules(board, []).default.clearance)
            Path(folder, "b.kicad_dru").write_text('(version 1)\n(rule "hv" (constraint clearance (min 1mm)))\n')
            with self.assertRaises(ValueError) as caught:
                _rules(board, [])
            self.assertIn("custom rules (b.kicad_dru)", str(caught.exception))

    def test_no_default_netclass_is_guessed(self) -> None:
        """Where KiCad gives no class for copper of no net and none named Default, the router does not take another."""
        board = OpenBoard("")
        power = SimpleNamespace(name="Power", constituents=[], clearance=300_000, track_width=500_000,
                                via_diameter=800_000, via_drill=400_000)
        board.get_nets = lambda: [SimpleNamespace(name="VCC")]
        board.get_netclass_for_nets = lambda nets: {"VCC": power}
        with self.assertRaises(ValueError) as caught:
            _rules(board, ["VCC"])
        self.assertIn("no Default netclass", str(caught.exception))


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
