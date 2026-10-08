"""What the viewer and ``cadgen pcb validate`` read from a board, through a real KiCad 10.

The plot payload is KiCad's own SVG of each layer of the board (with a ratsnest
when it is a draft), the board's index on that sheet, and each schematic sheet
with the schematic's index on them; ``pcb.validate`` is KiCad's ERC and DRC of
any project, and checking never writes into it. ``pcb.read_board`` reads a
board KiCad filled. Needs KiCad 10.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.python.packages.kicad.test_pcb_models import BOARD, board_source
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")
# A dimension above the board on User.Drawings, the scratch layer a draft's ratsnest is plotted on.
DIMENSION = (
    """board.raw('(dimension (type aligned) (layer "Dwgs.User") (uuid "00000000-0000-4000-8000-0000000000d1")"""
    """ (pts (xy 130 85) (xy 165 85)) (height -2) (format (units 3) (units_format 1) (precision 4))"""
    """ (style (thickness 0.1) (arrow_length 1.27) (text_position_mode 0) (extension_height 0.58642) (extension_offset 0.5)))')"""
)

# The suite's blinky has no IC, so the review's board is the smallest model with a ``power_in`` pin: a
# linear regulator, its input decoupled by a capacitor ``{cap_x}`` mm along from the pad.
REGULATOR = textwrap.dedent(
    '''
    from cadgen import build123d as bd
    from cadgen import pcb


    @pcb
    def regulator():
        with bd.BuildSketch() as outline:
            bd.Rectangle(30, 20)
        board = pcb.Board(outline=outline.sketch)
        vin, gnd = board.net("VIN", power_flag=True), board.net("GND", power_flag=True)
        vout = board.net("VOUT")
        u1 = board.part("Regulator_Linear:AMS1117-3.3", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")
        c1 = board.part("Device:C", footprint="Capacitor_SMD:C_0603_1608Metric", value="10u")
        board.connect(vin, u1["VI"], c1[1])
        board.connect(vout, u1["VO"])
        board.connect(gnd, u1["GND"], c1[2])
        board.place(u1, at=(0, 0))
        board.place(c1, at=({cap_x}, 5))
        return board


    if __name__ == "__main__":
        regulator()
    '''
)


class PcbPlotAndValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = generated_cad_directory(prefix="pcb-plot-")
        cls.folder = Path(cls._tmp.name)
        env = dict(os.environ, CADGEN_DAEMON="0", PYTHONPATH=str(CADGEN_SRC))
        for name, routed in (("finished", True), ("draft", False)):
            (cls.folder / name).mkdir()
            (cls.folder / name / "blinky.py").write_text(board_source(route_led=routed, extra="" if routed else DIMENSION), encoding="utf-8")
            built = subprocess.run([sys.executable, "blinky.py"], cwd=cls.folder / name, env=env, capture_output=True, text=True, timeout=600)
            if built.returncode != 0:
                raise AssertionError(built.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def payloads(cls) -> tuple[dict, dict]:
        if not hasattr(cls, "_payloads"):
            from cadgen.kicad.plot import build_plot

            cls._payloads = tuple(build_plot(cls.folder / name / "blinky.kicad_pcb") for name in ("finished", "draft"))
        return cls._payloads

    def test_a_board_plots_as_one_sheet_of_layers_and_a_draft_carries_its_ratsnest(self) -> None:
        from cadgen.kicad.plot import BOARD_BACKGROUND, PLOT_SCHEMA_VERSION

        finished, draft = self.payloads()
        self.assertEqual((finished["schemaVersion"], PLOT_SCHEMA_VERSION), (2, 2))
        self.assertEqual((finished["kind"], finished["unrouted"], len(finished["sheets"])), ("board", 0, 1))
        self.assertEqual(draft["unrouted"], 1)
        sheet = finished["sheets"][0]
        self.assertEqual(sheet["background"], BOARD_BACKGROUND)
        self.assertAlmostEqual(sheet["width"], 40.0, delta=0.05)
        stack = ["B.CrtYd", "B.Fab", "B.SilkS", "B.Cu", "F.Cu", "F.SilkS", "F.Fab", "F.CrtYd", "Edge.Cuts"]
        self.assertEqual([layer["id"] for layer in sheet["layers"]], stack + ["drills"])
        self.assertEqual([layer["id"] for layer in draft["sheets"][0]["layers"]], stack + ["ratsnest", "drills"])
        kinds = {layer["id"]: (layer["kind"], layer["side"]) for layer in draft["sheets"][0]["layers"]}
        self.assertEqual(
            [kinds[name] for name in ("B.CrtYd", "B.Fab", "B.SilkS", "B.Cu", "F.Cu", "F.CrtYd", "Edge.Cuts", "ratsnest", "drills")],
            [("courtyard", "back"), ("fab", "back"), ("silk", "back"), ("copper", "back"), ("copper", "front"), ("courtyard", "front"), ("outline", "both"), ("ratsnest", "both"), ("drill", "both")],
        )
        for layer in sheet["layers"]:
            self.assertIn("<svg", layer["svg"][:600])
            self.assertNotIn("<title>", layer["svg"])  # KiCad's timestamped title is gone
        # The pour is on B.Cu: its layer comes again without it; F.Cu has nothing to strip.
        copper = {layer["id"]: layer for layer in sheet["layers"] if layer["kind"] == "copper"}
        self.assertLess(len(copper["B.Cu"]["unpoured"]), len(copper["B.Cu"]["svg"]))
        self.assertNotIn("unpoured", copper["F.Cu"])
        # The ratsnest is drawn in the grey KiCad gives the scratch layer, on a layer of its own:
        # its one line, and nothing else the board draws there (the draft's dimension).
        ratsnest = next(layer for layer in draft["sheets"][0]["layers"] if layer["id"] == "ratsnest")
        self.assertIn("#C2C2C2", ratsnest["svg"])
        self.assertEqual(ratsnest["svg"].count("<path"), 1)

    def test_the_index_lands_on_the_sheet_kicad_plotted(self) -> None:
        from cadgen.kicad import sexpr

        finished, draft = self.payloads()
        board = finished["board"]
        # The page is fitted to the outline: its corner is the outline's, and the script's origin
        # (the board's centre, which the outline is drawn around) is half the board in from it.
        tree = sexpr.parse((self.folder / "finished" / "blinky.kicad_pcb").read_text(encoding="utf-8"))
        edges = [node for node in tree[1:] if sexpr.head(node) in ("gr_line", "gr_arc") and sexpr.value(node, "layer") == "Edge.Cuts"]
        corner = (min(sexpr.find(node, key)[1] for node in edges for key in ("start", "end")),
                  min(sexpr.find(node, key)[2] for node in edges for key in ("start", "end")))
        origin = sexpr.find(sexpr.find(tree, "setup"), "aux_axis_origin")[1:]
        self.assertAlmostEqual(board["origin"][0], origin[0] - corner[0], places=3)
        self.assertAlmostEqual(board["origin"][1], origin[1] - corner[1], places=3)
        self.assertEqual([round(value, 3) for value in board["origin"]], [20.0, 15.0])
        counts = {key: len(board[key]) for key in ("parts", "pads", "tracks", "vias", "zones", "holes", "outline")}
        self.assertEqual(counts, {"parts": 3, "pads": 6, "tracks": 7, "vias": 1, "zones": 1, "holes": 0, "outline": 1})
        self.assertEqual(len(draft["board"]["tracks"]), 3)
        for pad in board["pads"]:
            self.assertTrue(_inside(pad["at"], pad["polygon"]), pad)
        # A through-hole pad carries its hole; a surface pad none.
        drills = {(pad["part"], pad["number"]): pad.get("drill") for pad in board["pads"]}
        self.assertEqual((drills[("J1", "1")], drills[("R1", "1")]), (1.0, None))
        j1 = next(part for part in board["parts"] if part["ref"] == "J1")
        line = next(number for number, text in enumerate(BOARD.splitlines(), start=1) if "j1 = board.part(" in text)
        self.assertEqual((j1["script"], j1["fields"]["Script"]), (f"blinky.py:{line}", f"blinky.py:{line}"))
        self.assertEqual({net["name"]: net["class"] for net in board["nets"]}["VBUS"], "Default")

    def test_findings_carry_references_to_what_they_name(self) -> None:
        _finished, draft = self.payloads()
        [unrouted] = [finding for finding in draft["board"]["findings"] if finding["check"] == "unconnected"]
        self.assertEqual(unrouted["severity"], "error")
        self.assertEqual([item["ref"] for item in unrouted["items"]], ["#R1.2", "#D1.2"])
        pads = {(pad["part"], pad["number"]): pad["at"] for pad in draft["board"]["pads"]}
        self.assertEqual([item["at"] for item in unrouted["items"]], [pads["R1", "2"], pads["D1", "2"]])

    def test_the_review_rides_every_plot_and_validate_without_blocking(self) -> None:
        """A regulator's input capacitor 10 mm past its pad (see ``REGULATOR``) is advised on, never blocked."""
        from cadgen import pcb
        from cadgen.kicad.plot import build_plot

        project = self.folder / "regulator"
        project.mkdir()
        (project / "regulator.py").write_text(REGULATOR.format(cap_x=10), encoding="utf-8")
        env = dict(os.environ, CADGEN_DAEMON="0", PYTHONPATH=str(CADGEN_SRC))
        built = subprocess.run([sys.executable, "regulator.py"], cwd=project, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(built.returncode, 0, built.stderr)
        payload = build_plot(project / "regulator.kicad_pcb")
        review = [finding for finding in payload["board"]["findings"] if finding["check"] == "review"]
        self.assertEqual([finding["type"] for finding in review], ["decoupling_far"])
        self.assertIn("aim for under 3 mm", review[0]["summary"])
        self.assertTrue(all(item["ref"] for item in review[0]["items"]))
        checked = pcb.validate(project / "regulator.kicad_pcb")
        [advice] = [issue for issue in checked.issues if issue.code == "review.decoupling_far"]
        self.assertEqual(advice.severity, "warning")
        self.assertTrue(all(finding.get("summary") for finding in payload["board"]["findings"]))

    def test_read_board_sees_the_copper_kicad_poured(self) -> None:
        from cadgen import pcb

        board = pcb.read_board(self.folder / "finished" / "blinky.kicad_pcb")
        line = next(number for number, text in enumerate(BOARD.splitlines(), start=1) if "r1 = board.part(" in text)
        self.assertEqual(board.resolve("blinky.kicad_pcb#R1").script, f"blinky.py:{line}")
        pour = board.resolve("#net:GND@x-10y-10")
        self.assertEqual([(item.kind, item.layer) for item in pour.items], [("zone", "B.Cu")])
        self.assertIn(pour.items[0], board.at(-10, -10).copper)

    def test_a_schematic_plots_one_sheet_per_page_with_its_index(self) -> None:
        from cadgen.kicad.plot import SCHEMATIC_BACKGROUND, build_plot

        payload = build_plot(self.folder / "finished" / "blinky.kicad_sch")
        self.assertEqual((payload["kind"], len(payload["sheets"])), ("schematic", 1))
        self.assertEqual(payload["sheets"][0]["background"], SCHEMATIC_BACKGROUND)
        # The index is on the plot's sheets: KiCad's library symbols placed, KiCad's nets.
        index = payload["schematic"]
        self.assertEqual([sheet["name"] for sheet in index["sheets"]], ["blinky"])
        self.assertEqual([part["ref"] for part in index["parts"]], ["D1", "J1", "R1"])
        line = next(number for number, text in enumerate(BOARD.splitlines(), start=1) if "r1 = board.part(" in text)
        self.assertEqual(index["parts"][2]["script"], f"blinky.py:{line}")
        nets = {(pin["part"], pin["number"]): pin["net"] for pin in index["pins"]}
        self.assertEqual((nets["J1", "1"], nets["R1", "1"], nets["J1", "2"], nets["D1", "1"]), ("VBUS", "VBUS", "GND", "GND"))
        self.assertEqual(nets["R1", "2"], nets["D1", "2"])
        self.assertTrue(all(item["net"] for item in index["wires"] + index["labels"]))

    def test_the_payload_is_cached_by_the_documents_bytes(self) -> None:
        from cadgen.kicad.plot import plot_payload_bytes

        board = self.folder / "finished" / "blinky.kicad_pcb"
        first = plot_payload_bytes(board)
        self.assertEqual(plot_payload_bytes(board), first)
        self.assertEqual(json.loads(first)["schemaVersion"], 2)

    def test_validate_reads_kicads_verdict_and_writes_nothing(self) -> None:
        from cadgen import pcb

        project = self.folder / "draft"
        before = sorted(path.name for path in project.iterdir())
        finished = pcb.validate(self.folder / "finished" / "blinky.kicad_pcb")
        draft = pcb.validate(project / "blinky.kicad_pcb")
        self.assertTrue(finished.ok, finished.issues)
        self.assertFalse(draft.ok)
        self.assertIn("unconnected.unconnected_items", [issue.code for issue in draft.issues])
        self.assertEqual(sorted(path.name for path in project.iterdir()), before)


def _inside(point, polygon) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, [*polygon[1:], polygon[0]]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


if __name__ == "__main__":
    unittest.main()
