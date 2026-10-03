"""@pcb models end to end through a real KiCad 10.

One small board -- a connector, a resistor and an LED, every net routed, a
ground pour -- is written into a fresh folder in several variations and built
with ``python <script>.py``, the one source door. Each test pins a contract a
person relies on: a clean board is written and then current; KiCad's errors
write nothing; an unrouted board is a reported draft; manufacturing files are
deterministic and refused for a draft; a board with a 3D export composes into
an enclosure in the script's own coordinates; the library files a board read
are its inputs; custom rules are KiCad's, and one it cannot read fails the build. Needs KiCad 10 (scripts/test/test-kicad.sh).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
import zipfile
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")

BOARD = textwrap.dedent(
    '''
    from cadgen import build123d as bd
    from cadgen import {imports}

    WIDTH, HEIGHT = 40.0, 30.0
    ROUTE_LED = {route_led}


    {decorators}
    def blinky():
        with bd.BuildSketch() as outline:
            bd.RectangleRounded(WIDTH, HEIGHT, 2)
        board = pcb.Board(outline=outline.sketch)
        vbus, gnd = board.net("VBUS", power_flag=True), board.net("GND", power_flag=True)
        j1 = board.part("Connector_Generic:Conn_01x02", footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
        r1 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="1k")
        d1 = board.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="red")
        {extra}
        led = board.net()
        board.connect(vbus, j1[1], r1[1])
        board.connect(led, r1[2], d1["A"])
        board.connect(gnd, j1[2], d1["K"])
        board.place(j1, at=(-15, 0))
        board.place(r1, at=(0, 5), rotation=90)
        board.place(d1, at=(8, -5))
        board.track(vbus, [j1[1], (0, 0), r1[1]])
        if ROUTE_LED:
            board.track(led, [r1[2], (0, 8), (12, 8), (12, -5), d1["A"]])
        board.track(gnd, [d1["K"], (7.2125, -8)])
        board.via(gnd, at=(7.2125, -8))
        board.zone(gnd, layers=["B.Cu"])
        return board


    if __name__ == "__main__":
        blinky()
    '''
)

CASE = textwrap.dedent(
    '''
    from cadgen import build123d as bd
    from cadgen import step

    from blinky import HEIGHT, WIDTH, blinky


    @step
    def case():
        shell = bd.Box(WIDTH + 4, HEIGHT + 4, 12, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        shell -= bd.Pos(0, 0, 2) * bd.Box(WIDTH, HEIGHT, 12, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        return bd.Compound(children=[shell, bd.Pos(0, 0, 2) * blinky()], label="case")


    if __name__ == "__main__":
        case()
    '''
)


def board_source(*, decorators: str = "@pcb", imports: str = "pcb", route_led: bool = True, extra: str = "") -> str:
    return BOARD.format(decorators=decorators, imports=imports, route_led=route_led, extra=extra)


class PcbModelsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="pcb-models-")
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CADGEN_DAEMON"] = "0"
        env["PYTHONPATH"] = os.pathsep.join([str(CADGEN_SRC), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        return subprocess.run(
            [sys.executable, name, *args], cwd=self.folder, env=env, capture_output=True, text=True, timeout=600
        )

    def write(self, name: str, text: str) -> None:
        (self.folder / name).write_text(text, encoding="utf-8")

    def test_a_clean_board_is_written_then_current(self) -> None:
        self.write("blinky.py", board_source())
        built = self.run_script("blinky.py", "--json")
        self.assertEqual(built.returncode, 0, built.stderr)
        result = json.loads(built.stdout.strip().splitlines()[-1])
        self.assertEqual((result["outcome"], result["kind"], result["unrouted"]), ("built", "pcb", 0))
        for suffix in (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_dru"):
            self.assertTrue((self.folder / f"blinky{suffix}").is_file(), suffix)
        first = (self.folder / "blinky.kicad_pcb").read_bytes()
        self.assertIn(b"filled_polygon", first)  # KiCad filled the ground pour
        again = self.run_script("blinky.py")
        self.assertEqual(again.stdout.strip().splitlines()[-1], "current blinky.kicad_pcb")
        forced = self.run_script("blinky.py", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual((self.folder / "blinky.kicad_pcb").read_bytes(), first)

    def test_an_unrouted_board_is_a_reported_draft(self) -> None:
        self.write("blinky.py", board_source(route_led=False))
        built = self.run_script("blinky.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(built.stdout.strip().splitlines()[-1], "built blinky.kicad_pcb (draft: 1 unrouted connection)")
        self.assertIn("Missing connection between items", built.stderr)

    def test_kicads_errors_write_nothing(self) -> None:
        # A resistor with neither pin connected: KiCad's ERC reports both pins.
        self.write("blinky.py", board_source(extra='board.place(board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric"), at=(-8, -9))'))
        built = self.run_script("blinky.py")
        self.assertNotEqual(built.returncode, 0)
        self.assertIn("pin_not_connected", built.stderr)
        self.assertFalse(any(self.folder.glob("blinky.kicad_*")))

    def test_custom_rules_are_kicads_and_one_it_cannot_read_fails_the_build(self) -> None:
        # The rule asks more than the board has (a 0.25 mm VBUS track): KiCad applying it fails the build.
        wide = """board.rule(\"\"\"(rule "wide VBUS" (constraint track_width (min 1mm)) (condition "A.NetName == 'VBUS'"))\"\"\")"""
        self.write("blinky.py", board_source(extra=wide))
        built = self.run_script("blinky.py")
        self.assertNotEqual(built.returncode, 0)
        self.assertIn("track_width", built.stderr)
        # KiCad drops a rules file it cannot parse without a word; the build may not.
        unknown = wide.replace("A.NetName == 'VBUS'", "A.noSuchFunction('VBUS')")
        self.write("blinky.py", board_source(extra=unknown))
        broken = self.run_script("blinky.py")
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn("could not read the board's custom rules", broken.stderr)
        self.assertFalse(any(self.folder.glob("blinky.kicad_*")))

    def test_manufacturing_files_are_deterministic_and_refused_for_a_draft(self) -> None:
        self.write("blinky.py", board_source(decorators="@pcb(gerber=True, bom=True, pos=True)"))
        built = self.run_script("blinky.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        gerbers = (self.folder / "blinky.gerbers.zip").read_bytes()
        names = zipfile.ZipFile(io.BytesIO(gerbers)).namelist()
        self.assertIn("blinky-F_Cu.gtl", names)
        self.assertIn("blinky-PTH.drl", names)
        placement = (self.folder / "blinky.pos.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(placement[0], "Designator,Val,Package,Mid X,Mid Y,Rotation,Layer")
        self.assertIn("R1,1k,R_0603_1608Metric,0.000000,5.000000,90.000000,top", placement)
        self.assertIn('"1k","R1"', (self.folder / "blinky.bom.csv").read_text(encoding="utf-8"))
        self.assertEqual(self.run_script("blinky.py", "--force").returncode, 0)
        self.assertEqual((self.folder / "blinky.gerbers.zip").read_bytes(), gerbers)

        self.write("blinky.py", board_source(decorators="@pcb(gerber=True)", route_led=False))
        (self.folder / "blinky.gerbers.zip").unlink()
        draft = self.run_script("blinky.py")
        self.assertNotEqual(draft.returncode, 0)
        self.assertIn("write manufacturing files only for a finished board", draft.stderr)
        self.assertFalse((self.folder / "blinky.gerbers.zip").exists())

    def test_a_board_with_a_3d_export_composes_into_an_enclosure(self) -> None:
        self.write("blinky.py", board_source(decorators="@step\n@pcb", imports="pcb, step"))
        self.write("case.py", CASE)
        built = self.run_script("case.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        for name in ("blinky.step", "blinky.kicad_pcb", "case.step"):
            self.assertTrue((self.folder / name).is_file(), name)
        # Run on its own, the current board hands its tree back like any current part.
        again = self.run_script("blinky.py")
        self.assertEqual((again.returncode, again.stdout.strip().splitlines()[-1]), (0, "current blinky.kicad_pcb"), again.stderr)
        probe = textwrap.dedent(
            """
            import json
            from cadgen import read_step
            case = read_step("case.step")
            board = next(child for child in case.children if child.label == "blinky")
            body = next(child for child in board.children if child.label == "board")
            box = body.bounding_box()
            print(json.dumps({"parts": sorted(child.label for child in board.children),
                              "board": [round(v, 3) for v in (box.min.X, box.min.Y, box.min.Z, box.max.X, box.max.Y)]}))
            """
        )
        self.write("probe.py", probe)
        found = json.loads(self.run_script("probe.py").stdout.strip().splitlines()[-1])
        # The outline as the script drew it, the board's bottom on the pocket floor (z = 2).
        self.assertEqual(found["board"], [-20.0, -15.0, 2.0, 20.0, 15.0])
        self.assertTrue({"D1", "J1", "R1", "board"} >= set(found["parts"]) >= {"board"}, found["parts"])

    def test_the_library_files_a_board_read_are_its_inputs(self) -> None:
        self.write("blinky.py", board_source())
        self.assertEqual(self.run_script("blinky.py").returncode, 0)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(CADGEN_SRC)
        why = subprocess.run(
            [sys.executable, "-m", "cadgen.cli", "store", "why", "blinky.py"],
            cwd=self.folder, env=env, capture_output=True, text=True, timeout=120,
        )
        for library in ("Device.kicad_sym", "power.kicad_sym", "R_0603_1608Metric.kicad_mod"):
            self.assertIn(library, why.stdout, why.stdout)


if __name__ == "__main__":
    unittest.main()
