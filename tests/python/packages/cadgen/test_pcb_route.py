"""Autorouting without Freerouting, Java or KiCad: the DSN a board writes, the session read back.

Freerouting reads a board as a Specctra DSN and answers with a session (SES).
These tests pin cadgen's half of that exchange: the DSN states the board in
Freerouting's frame (micrometres, y up, the script's origin) with every pad
where KiCad puts it -- a bottom-side part's included, checked against
Freerouting's own placement transform -- and the board's rules, outline, holes
and keepouts; a hand-written session comes back as KiCad tracks and vias at
exact coordinates; the runner fails loudly on every way Freerouting can fail.
Routing a real board through Freerouting and KiCad is the KiCad suite's
(tests/python/packages/kicad/test_pcb_autoroute.py).
"""

from __future__ import annotations

import math
import os
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.kicad import route, sexpr  # noqa: E402
from cadgen.kicad.design import Board, DesignError  # noqa: E402
from cadgen.kicad.ids import Ids  # noqa: E402
from cadgen.kicad.project import project_texts  # noqa: E402
from cadgen.kicad.specctra import DsnFrame, SessionError, board_dsn, read_session, with_routes  # noqa: E402

# Two footprints of the tests' own: rectangular pads at odd places and angles
# (their corners are exact in a DSN), and a through-hole pair.
SKEW = (
    '(footprint "SKEW" (version 20241229) (generator "cadgen-tests") (layer "F.Cu")'
    '(property "Reference" "REF**" (at 0 -2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))'
    '(property "Value" "SKEW" (at 0 2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))'
    "(attr smd)"
    '(pad "1" smd rect (at -1.1 0.4 30) (size 0.6 1.2) (layers "F.Cu" "F.Mask" "F.Paste"))'
    '(pad "2" smd rect (at 1.2 -0.3 120) (size 0.5 1) (layers "F.Cu" "F.Mask" "F.Paste"))'
    "(embedded_fonts no))"
)
PTH2 = (
    '(footprint "PTH2" (version 20241229) (generator "cadgen-tests") (layer "F.Cu")'
    '(property "Reference" "REF**" (at 0 -3 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))'
    '(property "Value" "PTH2" (at 0 3 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))'
    "(attr through_hole)"
    '(pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"))'
    '(pad "2" thru_hole circle (at 0 2.54) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"))'
    "(embedded_fonts no))"
)


def _parse(dsn_text: str) -> list:
    """A DSN as nested lists of strings (its lone string-quote character set aside)."""
    from cadgen.kicad.specctra.session import _specctra

    return _specctra(dsn_text.replace('(string_quote ")', "(string_quote Q)"))


def _scope(node: list, *path: str) -> list:
    for name in path:
        node = next(child for child in node[1:] if isinstance(child, list) and child and child[0] == name)
    return node


def _scopes(node: list, name: str) -> list[list]:
    return [child for child in node[1:] if isinstance(child, list) and child and child[0] == name]


def _kicad_rotate(point, degrees):
    """KiCad's rotation: counter-clockwise as drawn, in its y-down frame."""
    angle = math.radians(degrees)
    x, y = point
    return x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)


def _turn(point, degrees):
    angle = math.radians(degrees)
    x, y = point
    return x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)


def _rounded(point):
    return round(point[0], 3), round(point[1], 3)


def _freerouting(point, *, pin, pin_rotation, place, back, rotation):
    """Where Freerouting puts a point of a pin's padstack (its Pin.getShape, default flip style)."""
    x, y = _turn(point, pin_rotation)
    px, py = pin
    if back:
        x, px = -x, -px
    x, y = _turn((x + px, y + py), rotation)
    return x + place[0], y + place[1]


class PcbRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="pcb-route-")
        folder = Path(self._tmp.name)
        (folder / "test").mkdir()
        self.library = write_test_library(folder / "test")
        pretty = folder / "route" / "Route.pretty"
        pretty.mkdir(parents=True)
        (pretty / "SKEW.kicad_mod").write_text(SKEW, encoding="utf-8")
        (pretty / "PTH2.kicad_mod").write_text(PTH2, encoding="utf-8")
        self.extra = folder / "route"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def board(self) -> Board:
        from cadgen import build123d as bd

        with bd.BuildSketch() as outline:
            bd.Rectangle(40, 30)
            with bd.Locations((12, -8)):
                bd.Circle(2, mode=bd.Mode.SUBTRACT)
        board = Board(outline=outline.sketch, libraries=[self.library, self.extra])
        board.netclass("Power", track_width=0.5, clearance=0.3)
        vin = board.net("VIN", power_flag=True, netclass="Power")
        out, gnd = board.net("TX/RX"), board.net("GND", power_flag=True)
        amp = board.part("Test:AMP", ref="U1")
        r1 = board.part("Test:R", footprint="Test:R_0603", value="10k")
        r2 = board.part("Test:R", footprint="Route:SKEW", value="1k")
        j1 = board.part("Test:R", footprint="Route:PTH2", ref="J1", value="header")
        board.connect(vin, amp["IN"], r1[1], j1[1])
        board.connect(out, amp["OUT"], r1[2], r2[1])
        board.connect(gnd, amp[3], amp[4], r2[2], j1[2])
        board.place(amp, at=(-5, 0))
        board.place(r1, at=(8, 4), rotation=90)
        board.place(r2, at=(8, -4), rotation=30, side="bottom")
        board.place(j1, at=(-15, -6), rotation=270)
        board.track(out, [amp["OUT"], r1[2]], width=0.3)
        board.via(gnd, at=(0, -8))
        board.hole(at=(-15, 10), diameter=3)
        with bd.BuildSketch() as keep:
            with bd.Locations((0, 10)):
                bd.Rectangle(6, 4)
        board.keepout(shape=keep.sketch, layers=["B.Cu"], tracks=False, vias=True)
        board.zone(gnd, layers=["B.Cu"])
        return board

    def dsn(self, **options):
        texts = project_texts(self.board(), name="amp")
        return texts, board_dsn(texts.pcb_tree, texts.pro, name="amp", **options)

    # -- the DSN --------------------------------------------------------------------

    def test_the_outline_is_the_boundary_and_its_holes_keep_copper_out(self) -> None:
        _texts, dsn = self.dsn()
        tree = _parse(dsn.text)
        self.assertEqual(_scope(tree, "resolution")[1:], ["um", "10"])
        layers = _scopes(_scope(tree, "structure"), "layer")
        self.assertEqual([layer[1] for layer in layers], ["F.Cu", "B.Cu"])
        boundary = _scope(tree, "structure", "boundary")
        path = boundary[1]
        points = [(float(path[i]), float(path[i + 1])) for i in range(3, len(path), 2)]
        # Micrometres, y up, about the script's origin; the path closes on itself.
        self.assertEqual(points[0], points[-1])
        self.assertEqual(set(points), {(-20000.0, -15000.0), (20000.0, -15000.0), (20000.0, 15000.0), (-20000.0, 15000.0)})
        self.assertEqual(boundary[2], ["clearance_class", "edge"])
        # The round cutout is an obstacle of its own: a pin of no net on a locked part at the
        # origin, kept the edge clearance, its outline outside the circle on every layer.
        obstacles = next(component for component in _scopes(_scope(tree, "placement"), "component") if component[1] == "I0_obstacles")
        place = _scope(obstacles, "place")
        self.assertEqual(place[1:6], ["@obstacles", "0", "0", "front", "0"])
        self.assertIn(["pin", "1", ["clearance_class", "edge"]], place)
        stack = next(item for item in _scopes(_scope(tree, "library"), "padstack") if item[1] == "K1")
        shapes = _scopes(stack, "shape")
        self.assertEqual([shape[1][1] for shape in shapes], ["F.Cu", "B.Cu"])
        polygon = shapes[0][1]
        corners = [(float(polygon[i]), float(polygon[i + 1])) for i in range(3, len(polygon), 2)]
        # Every edge stays 2 mm or more from the cutout's centre (to the nanometre its numbers
        # are written to).
        for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
            cx, cy = 12000.0 - x1, -8000.0 - y1
            dx, dy = x2 - x1, y2 - y1
            distance = abs(cx * dy - cy * dx) / math.hypot(dx, dy)
            self.assertGreaterEqual(distance, 2000.0 - 0.01)
        # A zone that forbids vias but not tracks stays a via keepout.
        self.assertEqual([item[2][1] for item in _scopes(_scope(tree, "structure"), "via_keepout")], ["B.Cu"])

    def test_the_rules_come_from_the_board_and_its_net_classes(self) -> None:
        texts, dsn = self.dsn()
        tree = _parse(dsn.text)
        rule = _scope(tree, "structure", "rule")
        # JLCPCB: 0.25 mm tracks, 0.2 mm clearance, 0.2 mm to the edge; each a micrometre over.
        self.assertEqual(rule[1:], [["width", "250"], ["clearance", "201"], ["clearance", "201", ["type", "default_edge"]]])
        classes = {item[1]: item for item in _scopes(_scope(tree, "network"), "class")}
        self.assertEqual(sorted(classes), ["C1Power", "kicad_default"])
        power = classes["C1Power"]
        self.assertEqual([dsn.nets[name] for name in power[2:] if isinstance(name, str)], ["VIN"])
        self.assertEqual(_scope(power, "rule")[1:], [["width", "500"], ["clearance", "301"]])
        via = _scope(power, "circuit", "use_via")[1]
        self.assertEqual(dsn.vias[via].diameter, 0.6)
        self.assertEqual(dsn.vias[via].drill, 0.3)
        # KiCad's spelling of a through-hole pad, so Freerouting reads its drill from the name.
        self.assertIn("T", [name[0] for name in dsn.vias] + [stack[1][0] for stack in _scopes(_scope(tree, "library"), "padstack")])
        stacks = [stack[1] for stack in _scopes(_scope(tree, "library"), "padstack")]
        self.assertTrue(any(name.endswith("_1700:1000_um") for name in stacks), stacks)
        self.assertEqual(dsn.widths[next(alias for alias, net in dsn.nets.items() if net == "VIN")], 0.5)

    def test_every_pad_is_where_kicad_puts_it_on_either_side(self) -> None:
        texts, dsn = self.dsn()
        tree = _parse(dsn.text)
        frame = DsnFrame(*(float(value) for value in sexpr.find(sexpr.find(texts.pcb_tree, "setup"), "aux_axis_origin")[1:3]))
        images = {image[1]: image for image in _scopes(_scope(tree, "library"), "image")}
        stacks = {stack[1]: stack for stack in _scopes(_scope(tree, "library"), "padstack")}
        places = {}
        for component in _scopes(_scope(tree, "placement"), "component"):
            for place in _scopes(component, "place"):
                places[place[1]] = (component[1], place)
        checked = 0
        for footprint in sexpr.find_all(texts.pcb_tree, "footprint"):
            ref = next(prop[2] for prop in sexpr.find_all(footprint, "property") if prop[1] == "Reference")
            if ref not in places:
                continue
            at = sexpr.find(footprint, "at")
            theta = float(at[3]) if len(at) > 3 else 0.0
            image, place = places[ref]
            back = place[4] == "back"
            self.assertEqual(back, sexpr.value(footprint, "layer") == "B.Cu")
            location = (float(place[2]), float(place[3]))
            pins = [pin for pin in _scopes(images[image], "pin")]
            pads = list(sexpr.find_all(footprint, "pad"))
            self.assertEqual(len(pins), len(pads))
            for pin, pad in zip(pins, pads):
                pad_at = sexpr.find(pad, "at")
                angle = float(pad_at[3]) if len(pad_at) > 3 else 0.0
                center = _kicad_rotate((float(pad_at[1]), float(pad_at[2])), theta)
                center = (float(at[1]) + center[0], float(at[2]) + center[1])
                width, height = (float(value) for value in sexpr.find(pad, "size")[1:3])
                kicad = sorted(
                    _rounded(frame.to_dsn(*(center[0] + dx, center[1] + dy)))
                    for dx, dy in (_kicad_rotate((sx * width / 2, sy * height / 2), angle) for sx in (-1, 1) for sy in (-1, 1))
                )
                rotate = next((float(item[1]) for item in pin[5:] if isinstance(item, list) and item[0] == "rotate"), 0.0)
                shape = _scope(stacks[pin[1]], "shape")[1]
                pin_at = (float(pin[3]), float(pin[4]))
                kwargs = dict(pin=pin_at, pin_rotation=rotate, place=location, back=back, rotation=float(place[5]))
                if shape[0] == "rect":
                    x1, y1, x2, y2 = (float(value) for value in shape[2:6])
                    ours = sorted(_rounded(_freerouting(corner, **kwargs)) for corner in ((x1, y1), (x1, y2), (x2, y1), (x2, y2)))
                    for (ax, ay), (bx, by) in zip(ours, kicad):
                        self.assertAlmostEqual(ax, bx, delta=1e-3, msg=f"{ref} pad {pad[1]}")
                        self.assertAlmostEqual(ay, by, delta=1e-3, msg=f"{ref} pad {pad[1]}")
                expected = frame.to_dsn(*center)
                found = _freerouting((0.0, 0.0), **kwargs)
                self.assertAlmostEqual(found[0], expected[0], delta=1e-3, msg=f"{ref} pad {pad[1]}")
                self.assertAlmostEqual(found[1], expected[1], delta=1e-3, msg=f"{ref} pad {pad[1]}")
                checked += 1
        self.assertEqual(checked, 4 + 2 + 2 + 2 + 1)

    def test_nets_skips_and_the_boards_own_copper(self) -> None:
        _texts, dsn = self.dsn(skip=["GND"])
        tree = _parse(dsn.text)
        names = {dsn.nets[net[1]]: net for net in _scopes(_scope(tree, "network"), "net")}
        # KiCad's own spelling of TX/RX; GND is left to its pour; each net names its pins.
        self.assertEqual(sorted(names), ["TX{slash}RX", "VIN"])
        self.assertEqual(sorted(_scope(names["VIN"], "pins")[1:]), ["J1-1", "R1-1", "U1-1"])
        self.assertEqual(dsn.routed, ("TX{slash}RX", "VIN"))
        wiring = _scope(tree, "wiring")
        wire = _scope(wiring, "wire")
        self.assertEqual(_scope(wire, "path")[1:3], ["F.Cu", "300"])
        self.assertEqual(dsn.nets[_scope(wire, "net")[1]], "TX{slash}RX")
        self.assertEqual(_scope(wire, "type")[1], "fix")
        via = _scope(wiring, "via")
        # GND's via stays as an obstacle of no net: the router may not join it.
        self.assertEqual([item[0] for item in via[4:]], ["type"])
        self.assertEqual(via[2:4], ["0", "-8000"])
        with self.assertRaisesRegex(DesignError, r"names 'VBUS', which is no net with pads.*GND, TX/RX, VIN"):
            self.dsn(skip=["VBUS"])

    def test_the_router_keeps_to_the_layers_it_is_given(self) -> None:
        # A layer the router may not run tracks on is a power layer to Freerouting:
        # never routed, and every via passes through it.
        _texts, dsn = self.dsn(layers=["F.Cu"])
        layers = _scopes(_scope(_parse(dsn.text), "structure"), "layer")
        self.assertEqual([(layer[1], _scope(layer, "type")[1]) for layer in layers], [("F.Cu", "signal"), ("B.Cu", "power")])
        with self.assertRaisesRegex(DesignError, r"takes this board's copper layers \(F\.Cu, B\.Cu\); got In1\.Cu"):
            self.dsn(layers=["In1.Cu"])

    def test_an_unplated_hole_keeps_the_hole_clearance(self) -> None:
        _texts, dsn = self.dsn()
        tree = _parse(dsn.text)
        image = next(image for image in _scopes(_scope(tree, "library"), "image") if image[1].endswith("Hole_3mm"))
        pin = _scope(image, "pin")
        # A pin of no net, on every layer: 3 mm drilled, grown by min_hole_clearance (JLCPCB's
        # 0.28) less the copper clearance (0.2) each side.
        joined = [ref for net in _scopes(_scope(tree, "network"), "net") for ref in _scope(net, "pins")[1:]]
        self.assertEqual(pin[2], "@1")
        self.assertNotIn("H1-@1", joined)
        stack = next(item for item in _scopes(_scope(tree, "library"), "padstack") if item[1] == pin[1])
        self.assertEqual([shape[1] for shape in _scopes(stack, "shape")], [["circle", "F.Cu", "3160", "0", "0"], ["circle", "B.Cu", "3160", "0", "0"]])

    def test_the_same_board_writes_the_same_dsn(self) -> None:
        _texts, first = self.dsn()
        _texts, second = self.dsn()
        self.assertEqual(first.text, second.text)
        # Freerouting reads a tab as part of a name.
        self.assertNotIn("\t", first.text)

    # -- the session ------------------------------------------------------------------

    def session(self, dsn, body: str) -> str:
        return textwrap.dedent(
            f"""
            (session amp
              (base_design amp)
              (placement (resolution um 10))
              (was_is)
              (routes
                (resolution um 10)
                (parser (host_cad cadgen) (host_version cadgen))
                (network_out
                  {body}
                )
              )
            )
            """
        )

    def test_a_session_comes_back_as_kicad_tracks_and_vias(self) -> None:
        texts, dsn = self.dsn()
        vin = next(alias for alias, net in dsn.nets.items() if net == "VIN")
        out = next(alias for alias, net in dsn.nets.items() if net == "TX{slash}RX")
        via = next(name for name in dsn.vias)
        text = self.session(
            dsn,
            f"""
            (net "{vin}"
              (wire (path F.Cu 5000 -150000 -60000 -150000 20000 -76750 20000))
              (wire (path B.Cu 5000 -76750 20000 80000 20000))
              (via "{via}" -76750 20000))
            (net "{out}" (wire (path F.Cu 2501 0 0 12345 -6789) (type protect)))
            """,
        )
        routes = read_session(text, dsn)
        ox, oy = dsn.frame.ox, dsn.frame.oy
        vin_tracks = [track for track in routes.tracks if track.net == "VIN"]
        # Tenths of a micrometre, y up, from the script's origin: back to KiCad's millimetres exactly.
        self.assertEqual(
            sorted((track.layer, track.start, track.end) for track in vin_tracks),
            sorted(
                [
                    ("F.Cu", (ox - 15.0, oy + 6.0), (ox - 15.0, oy - 2.0)),
                    ("F.Cu", (ox - 15.0, oy - 2.0), (ox - 7.675, oy - 2.0)),
                    ("B.Cu", (ox - 7.675, oy - 2.0), (ox + 8.0, oy - 2.0)),
                ]
            ),
        )
        self.assertEqual({track.width for track in vin_tracks}, {0.5})
        # A width a rounding off its net class's comes back as the class's own.
        [other] = [track for track in routes.tracks if track.net == "TX{slash}RX"]
        self.assertEqual((other.width, other.start, other.end), (0.25, (ox, oy), (ox + 1.2345, oy + 0.6789)))
        [found] = routes.vias
        self.assertEqual((found.net, found.at, found.kind.diameter, found.kind.drill), ("VIN", (ox - 7.675, oy - 2.0), 0.6, 0.3))

    def test_a_session_that_does_not_fit_its_design_is_refused(self) -> None:
        _texts, dsn = self.dsn()
        vin = next(alias for alias, net in dsn.nets.items() if net == "VIN")
        cases = {
            "a net the design does not have": '(net "N9_ELSEWHERE" (wire (path F.Cu 2500 0 0 10 10)))',
            "a layer the board does not have": f'(net "{vin}" (wire (path In7.Cu 2500 0 0 10 10)))',
            "a via the design does not offer": f'(net "{vin}" (via "Via_huge" 0 0))',
            "a copper area": f'(net "{vin}" (wire (polygon F.Cu 0 0 0 10 0 10 10)))',
        }
        for reason, body in cases.items():
            with self.subTest(reason=reason), self.assertRaisesRegex(SessionError, reason):
                read_session(self.session(dsn, body), dsn)
        swapped = self.session(dsn, "").replace("(was_is)", "(was_is (pins U1-3 U1-4))")
        with self.assertRaisesRegex(SessionError, "swapped pins"):
            read_session(swapped, dsn)
        with self.assertRaisesRegex(SessionError, "cut short"):
            read_session("(session amp (routes", dsn)

    def test_routes_join_the_board_after_its_own_copper_with_stable_ids(self) -> None:
        texts, dsn = self.dsn()
        vin = next(alias for alias, net in dsn.nets.items() if net == "VIN")
        via = next(name for name in dsn.vias)
        text = self.session(dsn, f'(net "{vin}" (wire (path F.Cu 5000 0 0 10000 0)) (via "{via}" 10000 0))')
        routes = read_session(text, dsn)
        routed = with_routes(texts.pcb_tree, routes, project="amp")
        self.assertEqual(sexpr.dumps(routed), sexpr.dumps(with_routes(texts.pcb_tree, routes, project="amp")))
        heads = [sexpr.head(item) for item in routed]
        # The script's own track and via, then the router's.
        start = heads.index("segment")
        self.assertEqual(heads[start:start + 4], ["segment", "via", "segment", "via"])
        new_segment, new_via = routed[start + 2], routed[start + 3]
        ids = Ids("amp")
        self.assertEqual(sexpr.value(new_segment, "uuid"), ids.of("route:0"))
        self.assertEqual(sexpr.value(new_via, "uuid"), ids.of("route:1"))
        self.assertEqual(sexpr.value(new_segment, "net"), "VIN")
        self.assertEqual(sexpr.find(new_via, "layers")[1:], ["F.Cu", "B.Cu"])
        self.assertIsNot(routed, texts.pcb_tree)
        self.assertNotIn(ids.of("route:0"), str(texts.pcb_tree))  # the board routed is a copy

    def test_the_frame_round_trips_kicads_nanometres(self) -> None:
        frame = DsnFrame(148.5, 105.0)
        for point in ((148.5, 105.0), (157.182, 109.606), (0.000001, 297.0), (-3.25, 0.1)):
            self.assertEqual(frame.to_kicad(*frame.to_dsn(*point)), point)
        # A session integer is a tenth of a micrometre: points on that grid come back exactly.
        ux, uy = frame.to_dsn(157.1823, 98.0007)
        self.assertEqual(frame.to_kicad(round(ux * 10) / 10, round(uy * 10) / 10), (157.1823, 98.0007))

    # -- the API and the runner ---------------------------------------------------------

    def test_autoroute_takes_its_settings_once_and_refuses_bad_ones(self) -> None:
        board = self.board()
        gnd = board.net("GND")
        with self.assertRaisesRegex(DesignError, "passes= is how many routing passes"):
            board.autoroute(passes=0)
        with self.assertRaisesRegex(DesignError, "timeout= is seconds, greater than 0"):
            board.autoroute(timeout=-1)
        with self.assertRaisesRegex(DesignError, "skip= takes nets or net names"):
            board.autoroute(skip=[3])
        other = Board(outline=object(), libraries=[self.library])
        with self.assertRaisesRegex(DesignError, "another board"):
            board.autoroute(skip=[other.net("GND")])
        with self.assertRaisesRegex(TypeError, "unexpected keyword"):
            board.autoroute(passes=5, optimize=True)
        with self.assertRaisesRegex(DesignError, "autoroute layer 'In1.Cu' is not a copper layer of this 2-layer board"):
            board.autoroute(layers=["In1.Cu"])
        board.autoroute(skip=gnd, layers=["B.Cu", "F.Cu"], passes=7, timeout=30)
        request = board.autoroute_request
        self.assertEqual((request.skip, request.layers, request.passes, request.timeout), ((gnd,), ("F.Cu", "B.Cu"), 7, 30.0))
        with self.assertRaisesRegex(DesignError, "already called"):
            board.autoroute()

    def test_freerouting_is_found_where_cadgen_says(self) -> None:
        with temporary_directory(prefix="pcb-route-find-") as folder:
            folder = Path(folder)
            missing = folder / "nowhere.jar"
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(missing)}):
                with self.assertRaisesRegex(route.FreeroutingMissingError, "CADGEN_FREEROUTING is .*nowhere.jar, which does not exist"):
                    route.find_freerouting()
            launcher = folder / "freerouting"
            launcher.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(launcher)}):
                self.assertEqual(route.find_freerouting().command, (str(launcher),))
            bundle = folder / "freerouting.app" / "Contents" / "MacOS"
            bundle.mkdir(parents=True)
            (bundle / "freerouting").write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(folder / "freerouting.app")}):
                self.assertEqual(route.find_freerouting().command, (str(bundle / "freerouting"),))
            unzipped = folder / "freerouting-2.4.1-linux-x64" / "bin"
            unzipped.mkdir(parents=True)
            (unzipped / "freerouting").write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(unzipped.parent)}):
                self.assertEqual(route.find_freerouting().command, (str(unzipped / "freerouting"),))
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(folder / "freerouting.app" / "Contents")}):
                with self.assertRaisesRegex(route.FreeroutingMissingError, "a folder with no Freerouting launcher"):
                    route.find_freerouting()
            jar, java = folder / "freerouting-2.4.1.jar", folder / "java"
            jar.write_text("", encoding="utf-8")
            java.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CADGEN_FREEROUTING": str(jar), "CADGEN_JAVA": str(java)}):
                with mock.patch.object(route, "_java_version", return_value="25.0.4.1"):
                    self.assertEqual(route.find_freerouting().command, (str(java), "-Djava.awt.headless=true", "-jar", str(jar)))
                with mock.patch.object(route, "_java_version", return_value="15.0.1"):
                    with self.assertRaisesRegex(route.FreeroutingMissingError, r"needs Java 25 or newer.*is Java 15\.0\.1"):
                        route.find_freerouting()
                with mock.patch.object(route, "_java_version", return_value="1.8.0_282"):
                    with self.assertRaisesRegex(route.FreeroutingMissingError, r"is Java 1\.8\.0_282"):
                        route.find_freerouting()

    def test_a_run_is_isolated_and_offline(self) -> None:
        # Freerouting asks GitHub for its latest release on every start; Java's proxy
        # properties, at a closed local port, keep that request on this machine.
        with mock.patch.dict(os.environ, {"FREEROUTING__GUI__ENABLED": "true", "JAVA_TOOL_OPTIONS": "-Xmx2g"}):
            env = route._isolated_env()
        self.assertNotIn("FREEROUTING__GUI__ENABLED", env)
        options = env["JAVA_TOOL_OPTIONS"].split()
        self.assertEqual(options[0], "-Xmx2g")  # a person's own options stay
        for scheme in ("http", "https"):
            self.assertIn(f"-D{scheme}.proxyHost=127.0.0.1", options)
            self.assertIn(f"-D{scheme}.proxyPort=9", options)

    def test_every_way_freerouting_fails_is_loud(self) -> None:
        fake = textwrap.dedent(
            """
            import os, sys, time
            mode = os.environ["FAKE_MODE"]
            print("2026-10-03 INFO   Freerouting v" + ("2.3.0" if mode == "old" else "2.4.1") + " (build-date: 2026-09-03)")
            if any(key.startswith("FREEROUTING__") for key in os.environ):
                print("a FREEROUTING__ override reached Freerouting")
                sys.exit(3)
            if mode == "refuse":
                print("WARN   Failed to apply CLI router setting: router.fanout.enabled: no such field")
            if mode == "fail":
                print("ERROR  Couldn't load the input file")
                sys.exit(1)
            if mode == "slow":
                time.sleep(60)
            args = sys.argv[1:]
            with open(args[args.index("-do") + 1], "w") as session:
                session.write("(session amp (routes (resolution um 10) (network_out)))")
            """
        )
        with temporary_directory(prefix="pcb-route-run-") as folder:
            folder = Path(folder)
            script = folder / "fake_freerouting.py"
            script.write_text(fake, encoding="utf-8")
            tool = route.Freerouting(command=(sys.executable, str(script)), location=script)
            dsn = folder / "amp.dsn"
            dsn.write_text("(pcb amp)", encoding="utf-8")

            def run(mode: str, timeout: float = 120):
                ses = folder / f"{mode}.ses"
                with mock.patch.dict(os.environ, {"FAKE_MODE": mode, "FREEROUTING__ROUTER__MAX_PASSES": "1"}):
                    return route.run_freerouting(tool, dsn=dsn, ses=ses, passes=5, timeout=timeout, folder=folder)

            self.assertEqual(run("ok"), "2.4.1")
            with self.assertRaisesRegex(route.FreeroutingMissingError, r"is Freerouting 2\.3\.0; cadgen needs 2\.4\.0"):
                run("old")
            with self.assertRaisesRegex(route.RouteError, "refused a setting"):
                run("refuse")
            with self.assertRaisesRegex(route.RouteError, r"exit status 1\) and wrote no routes:[\s\S]*Couldn't load the input file"):
                run("fail")
            with self.assertRaisesRegex(route.RouteError, r"did not finish routing in 0\.5 s"):
                run("slow", timeout=0.5)


if __name__ == "__main__":
    unittest.main()
