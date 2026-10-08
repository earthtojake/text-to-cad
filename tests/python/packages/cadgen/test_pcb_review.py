"""The review: what a person reviewing a board checks that KiCad's checks do not."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad.board_index import BoardIndex, Pad, Part, Track  # noqa: E402
from cadgen.kicad.review import is_ground, net_currents, required_width, review  # noqa: E402


def pad(part, number, net, at, type="passive", name=None):
    return Pad(part=part, number=number, name=name, net=net, type=type, side="top", at=at, polygon=())


def part(ref, pads, dnp=False):
    return Part(ref=ref, value="", footprint="", side="top", at=pads[0].at, rotation=0.0, fields={}, dnp=dnp,
                outline=(), pads=tuple(pads))


def ic(at=(0.0, 0.0)):
    x, y = at
    return part("U2", [pad("U2", "7", "VDD", (x, y), "power_in", "VDD"), pad("U2", "8", "GND", (x + 1, y), "power_in", "GND"),
                       pad("U2", "1", "SDA", (x + 2, y), "bidirectional")])


def cap(ref, at, net="VDD", dnp=False):
    return part(ref, [pad(ref, "1", net, at), pad(ref, "2", "GND", (at[0] + 1, at[1]))], dnp=dnp)


def board(*parts, tracks=()):
    return BoardIndex(parts=tuple(parts), tracks=tuple(tracks), vias=(), zones=(), holes=(), outline=(), nets=(),
                      origin=(0.0, 0.0))


class ReviewTest(unittest.TestCase):
    def test_ground_names(self):
        for name in ("GND", "gnd", "AGND", "PGND", "GNDA", "GND_ISO", "VSS", "/Power/GND", "0V"):
            self.assertTrue(is_ground(name), name)
        for name in ("VDD", "VBUS", "SIGNAL_GND_SENSE", None, ""):
            self.assertFalse(is_ground(name), name)

    def test_a_close_capacitor_is_fine(self):
        self.assertEqual(review(board(ic(), cap("C4", (2.0, 0.0)))), ())

    def test_a_far_capacitor_is_named_with_its_distance(self):
        (found,) = review(board(ic(), cap("C4", (9.1, 0.0))))
        self.assertEqual((found.check, found.severity, found.type), ("review", "warning", "decoupling_far"))
        self.assertEqual(found.summary, "U2's VDD: the nearest decoupling capacitor, C4, is 9.1 mm away (aim for under 3 mm)")
        self.assertEqual([item.ref for item in found.items], ["#U2.7", "#C4.1"])

    def test_no_capacitor_on_a_power_input(self):
        (found,) = review(board(ic()))
        self.assertEqual(found.type, "decoupling_missing")
        self.assertEqual(found.summary, "U2's VDD has no decoupling capacitor")

    def test_ground_pins_are_never_reported(self):
        self.assertTrue(all("GND" not in found.summary for found in review(board(ic()))))

    def test_a_dnp_capacitor_decouples_nothing(self):
        (found,) = review(board(ic(), cap("C4", (2.0, 0.0), dnp=True)))
        self.assertEqual(found.type, "decoupling_missing")

    def test_a_connector_or_an_unfitted_part_is_not_reviewed(self):
        connector = part("J1", [pad("J1", "1", "+5V", (0.0, 0.0), "power_in"), pad("J1", "2", "3V3", (2.5, 0.0), "power_in")])
        self.assertEqual(review(board(connector)), ())
        unfitted = part("U2", [pad("U2", "7", "VDD", (0.0, 0.0), "power_in")], dnp=True)
        self.assertEqual(review(board(unfitted)), ())

    def test_a_board_without_power_inputs_has_nothing_to_say(self):
        connector = part("J1", [pad("J1", "1", "VBUS", (0.0, 0.0)), pad("J1", "2", "GND", (2.5, 0.0))])
        self.assertEqual(review(board(connector)), ())

    def test_a_thin_track_for_its_current(self):
        thin = Track(net="VBUS", layer="F.Cu", width=0.25, points=((0.0, 0.0), (10.0, 0.0)))
        wide = Track(net="VBUS", layer="F.Cu", width=1.0, points=((10.0, 0.0), (20.0, 0.0)))
        (found,) = review(board(tracks=(thin, wide)), {"VBUS": 2.0})
        self.assertEqual(found.type, "track_current")
        self.assertEqual(found.summary, "VBUS carries 2 A; its narrowest track is 0.25 mm, it needs about 0.78 mm")
        self.assertEqual(found.items[0].ref, "#net:VBUS")
        self.assertEqual(review(board(tracks=(wide,)), {"VBUS": 2.0}), ())
        self.assertEqual(review(board(tracks=(thin,))), ())

    def test_the_needed_width_never_reads_as_the_narrowest(self):
        thin = Track(net="VBUS", layer="F.Cu", width=0.1, points=((0.0, 0.0), (10.0, 0.0)))
        (found,) = review(board(tracks=(thin,)), {"VBUS": 0.5})
        self.assertEqual(found.summary, "VBUS carries 0.5 A; its narrowest track is 0.1 mm, it needs about 0.12 mm")

    def test_ipc_2221_width(self):
        self.assertAlmostEqual(required_width(2.0), 0.78, delta=0.02)
        self.assertAlmostEqual(required_width(1.0), 0.30, delta=0.02)

    def test_currents_are_read_from_the_project(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "t.kicad_pro"
            project.write_text(json.dumps({"cadgen": {"net_currents": {"VBUS": 2.0, "BAD": -1}}}))
            self.assertEqual(net_currents(project), {"VBUS": 2.0})
            for text in ('{"cadgen": []}', '{"cadgen": {"net_currents": [1]}}', '{"cadgen": {"net_currents": {"V": Infinity}}}'):
                project.write_text(text)
                self.assertEqual(net_currents(project), {}, text)
            project.write_text("{not json")
            self.assertEqual(net_currents(project), {})
            self.assertEqual(net_currents(Path(folder) / "missing.kicad_pro"), {})
            self.assertEqual(net_currents(None), {})

    def test_the_review_never_blocks_a_build(self):
        from cadgen.kicad.check import is_blocking
        from cadgen.kicad.cli import Finding

        for severity in ("warning", "error"):
            self.assertFalse(is_blocking(Finding(check="review", severity=severity, type="decoupling_far", description="", items=())))
        self.assertTrue(is_blocking(Finding(check="drc", severity="error", type="clearance", description="", items=())))

    def test_validate_passes_a_board_whose_only_findings_are_the_review(self):
        from unittest import mock

        from cadgen import pcb
        from cadgen.kicad.check import ProjectCheck
        from cadgen.kicad.cli import Finding

        for severity in ("warning", "error"):
            found = Finding(check="review", severity=severity, type="decoupling_far", description="far", items=(), summary="C1 is far")
            with tempfile.TemporaryDirectory() as folder, mock.patch("cadgen.kicad.check.check_project", return_value=ProjectCheck(findings=(found,))):
                board = Path(folder) / "b.kicad_pcb"
                board.write_text("")
                for strict in (False, True):
                    result = pcb.validate(board, strict=strict)
                    self.assertTrue(result.ok, (severity, strict, result.issues))
                    self.assertEqual([(issue.code, issue.severity, issue.message) for issue in result.issues],
                                     [("review.decoupling_far", severity, "C1 is far")])


if __name__ == "__main__":
    unittest.main()
