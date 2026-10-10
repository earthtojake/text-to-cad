"""board.autoroute() end to end: Freerouting routes, KiCad fills and checks, the board is finished.

One small board -- a connector, a resistor on top, an LED on the bottom turned
30 degrees, a net with a ``/`` in its name, a supply drawn by hand, a ground
carried by a pour -- is written with no other tracks and built with
``python <script>.py``. The router must finish every connection it was given,
leave the hand-drawn track and the skipped ground alone, and KiCad's DRC must
pass the result. A build without Freerouting fails, saying how to install it.

Needs KiCad 10 and Freerouting (with Java 25 for its jar): the KiCad CI job
provides both (scripts/test/test-kicad.sh); locally, set CADGEN_FREEROUTING
(and CADGEN_JAVA) as cadgen.kicad.route describes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")

from cadgen.kicad import sexpr  # noqa: E402

BOARD = textwrap.dedent(
    '''
    from cadgen import build123d as bd
    from cadgen import pcb


    @pcb
    def blinky():
        with bd.BuildSketch() as outline:
            bd.RectangleRounded(40, 30, 2)
        board = pcb.Board(outline=outline.sketch)
        vbus, gnd = board.net("VBUS", power_flag=True), board.net("GND", power_flag=True)
        led = board.net("R/LED")
        j1 = board.part("Connector_Generic:Conn_01x02", footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
        r1 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="1k")
        d1 = board.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="red")
        board.connect(vbus, j1[1], r1[1])
        board.connect(led, r1[2], d1["A"])
        board.connect(gnd, j1[2], d1["K"])
        board.place(j1, at=(-15, 0))
        board.place(r1, at=(0, 5), rotation=90)
        board.place(d1, at=(8, -5), rotation=30, side="bottom")
        board.track(vbus, [j1[1], (-4, 0), r1[1]])
        board.zone(gnd, layers=["B.Cu"])
        board.autoroute(skip=[gnd])
        return board


    if __name__ == "__main__":
        blinky()
    '''
)


class PcbAutorouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="pcb-autoroute-")
        self.folder = Path(self._tmp.name)
        (self.folder / "blinky.py").write_text(BOARD, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["CADGEN_DAEMON"] = "0"
        environment["PYTHONPATH"] = os.pathsep.join([str(CADGEN_SRC), environment.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        environment.update(env or {})
        return subprocess.run(
            [sys.executable, "blinky.py", *args], cwd=self.folder, env=environment, capture_output=True, text=True, timeout=600
        )

    def test_an_unrouted_board_is_routed_and_passes_kicads_checks(self) -> None:
        built = self.build("--json")
        self.assertEqual(built.returncode, 0, built.stderr)
        result = json.loads(built.stdout.strip().splitlines()[-1])
        self.assertEqual((result["outcome"], result["unrouted"]), ("built", 0), built.stderr)
        # No DRC error (one would have failed the build), and no stub the router left behind.
        self.assertNotIn("track_dangling", built.stderr)
        tree = sexpr.parse((self.folder / "blinky.kicad_pcb").read_text(encoding="utf-8"))
        segments = list(sexpr.find_all(tree, "segment"))
        by_net: dict[str, int] = {}
        for segment in segments:
            by_net[str(sexpr.value(segment, "net"))] = by_net.get(str(sexpr.value(segment, "net")), 0) + 1
        # The hand-drawn supply is kept as drawn (two segments); the router joined R/LED,
        # top to bottom, in KiCad's spelling of the name; the ground is the pour's.
        self.assertEqual(by_net.get("VBUS"), 2, by_net)
        self.assertGreater(by_net.get("R{slash}LED", 0), 0, by_net)
        self.assertNotIn("GND", by_net)
        layers = {str(sexpr.value(segment, "layer")) for segment in segments if sexpr.value(segment, "net") == "R{slash}LED"}
        self.assertEqual(layers, {"F.Cu", "B.Cu"})
        self.assertTrue(any(sexpr.value(via, "net") == "R{slash}LED" for via in sexpr.find_all(tree, "via")))

    def test_without_freerouting_the_build_says_how_to_get_it(self) -> None:
        built = self.build(env={"CADGEN_FREEROUTING": str(self.folder / "missing" / "freerouting.jar")})
        self.assertNotEqual(built.returncode, 0)
        self.assertIn("CADGEN_FREEROUTING is", built.stderr)
        self.assertIn("github.com/freerouting/freerouting/releases", built.stderr)
        self.assertFalse(any(self.folder.glob("blinky.kicad_*")))


if __name__ == "__main__":
    unittest.main()
