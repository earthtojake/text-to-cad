"""Circuit simulation end to end: KiCad's own parts, simulated by the ngspice KiCad ships.

Each test pins a number a person can check by hand: a resistive divider's
operating point, an RC step against 1 - exp(-t/RC), an RC low-pass's -3 dB
point against 1/(2 pi RC). One subcircuit function builds into a Board and into
a Testbench unchanged. A failed simulation raises -- a fatal ngspice error
included -- and the next one runs. Needs KiCad 10 (scripts/test/test-kicad.sh):
with no KiCad or no ngspice these tests fail, saying how to install them.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad import ngspice  # noqa: E402
from cadgen.kicad.design import Board  # noqa: E402
from cadgen.kicad.install import find_kicad  # noqa: E402
from cadgen.kicad.sim import SimulationError, Testbench  # noqa: E402

R_0603 = "Resistor_SMD:R_0603_1608Metric"
C_0603 = "Capacitor_SMD:C_0603_1608Metric"


def setUpModule() -> None:
    # Fail, never skip: these raise KicadMissingError with the install hint.
    find_kicad()
    ngspice.simulate(["* ngspice is here", "V1 a 0 1", "R1 a 0 1k", ".end"], "op", plot_prefix="op")


class _Outline:
    """Board(outline=...) is read only when a board is written, which this suite never does."""


def divider(c, vin, out, gnd):
    """The subcircuit a board script and a test script share."""
    top = c.part("Device:R", footprint=R_0603, value="10k")
    bottom = c.part("Device:R", footprint=R_0603, value="10k")
    c.connect(vin, top[1])
    c.connect(out, top[2], bottom[1])
    c.connect(gnd, bottom[2])
    return top, bottom


def low_pass(c, vin, out, gnd):
    r = c.part("Device:R", footprint=R_0603, value="1k")
    cap = c.part("Device:C", footprint=C_0603, value="1u")
    c.connect(vin, r[1])
    c.connect(out, r[2], cap[1])
    c.connect(gnd, cap[2])


class SimulationTest(unittest.TestCase):
    def test_a_divider_solves_exactly(self) -> None:
        tb = Testbench()
        vin, out = tb.net("VIN"), tb.net("DIV/OUT")  # a net name KiCad's files escape
        divider(tb, vin, out, tb.ground)
        supply = tb.source(vin, dc=5.0)
        op = tb.operating_point()
        self.assertAlmostEqual(op["DIV/OUT"], 2.5, delta=1e-9)
        self.assertEqual(op[out], op["DIV/OUT"])
        self.assertEqual(op["GND"], 0.0)
        self.assertAlmostEqual(op.current(supply), 5.0 / 20e3, delta=1e-12)  # the current it supplies

    def test_an_rc_step_follows_the_analytic_curve(self) -> None:
        tb = Testbench()
        vin, out = tb.net("VIN"), tb.net("OUT")
        low_pass(tb, vin, out, tb.ground)
        tb.source(vin, pulse=dict(v1=0, v2=1, rise=1e-9))
        run = tb.transient(stop=5e-3, step=1e-6)
        tau = 1e3 * 1e-6
        for t in (0.5 * tau, tau, 2 * tau, 3 * tau):
            expected = 1 - math.exp(-t / tau)
            self.assertLess(abs(run["OUT"].at(t) - expected) / expected, 0.01, f"t = {t}")
        self.assertAlmostEqual(run["OUT"].crossings(1 - math.exp(-1))[0], tau, delta=0.01 * tau)
        self.assertEqual(run.time[0], 0.0)
        self.assertAlmostEqual(run.time[-1], 5e-3)
        picture = run.plot(Path(self._tmp.name) / "rc.png", nets=["VIN", "OUT"])
        self.assertEqual(picture.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_an_rc_low_pass_is_3db_down_at_its_corner(self) -> None:
        tb = Testbench()
        vin, out = tb.net("VIN"), tb.net("OUT")
        low_pass(tb, vin, out, tb.ground)
        tb.source(vin, dc=0, ac=1)
        run = tb.ac(10, 100e3, points_per_decade=40)
        corner = 1 / (2 * math.pi * 1e3 * 1e-6)
        found = run["OUT"].db.crossings(-10 * math.log10(2))
        self.assertEqual(len(found), 1)
        self.assertLess(abs(found[0] - corner) / corner, 0.01)
        self.assertAlmostEqual(run["OUT"].phase.at(corner), -45.0, delta=0.5)
        self.assertAlmostEqual(abs(run["OUT"].at(10)), 1.0, delta=0.01)

    def test_one_subcircuit_builds_a_board_and_a_testbench(self) -> None:
        board = Board(outline=_Outline())
        top, bottom = divider(board, board.net("VIN"), board.net("OUT"), board.net("GND"))
        board.place(top, at=(-3, 0))
        board.place(bottom, at=(3, 0))
        self.assertEqual(board.problems(), [])
        tb = Testbench()
        vin, out = tb.net("VIN"), tb.net("OUT")
        divider(tb, vin, out, tb.ground)
        tb.source(vin, dc=3.3)
        sweep = tb.dc_sweep(vin, 0, 3.3, 1.1)
        self.assertEqual([round(value, 9) for value in sweep.sweep], [0.0, 1.1, 2.2, 3.3])
        self.assertAlmostEqual(sweep["OUT"].final, 1.65, delta=1e-9)

    def test_kicads_own_models_simulate(self) -> None:
        # Device:D carries KiCad's Sim.Device=D (SPICE's default diode); Simulation_SPICE:OPAMP names
        # KiCad's model file through ${KICAD9_SYMBOL_DIR}.
        tb = Testbench()
        vin, anode, vcc, vee, out = (tb.net(name) for name in ("VIN", "A", "VCC", "VEE", "OUT"))
        r = tb.part("Device:R", value="4k3")
        d = tb.part("Device:D")
        tb.connect(vin, r[1])
        tb.connect(anode, r[2], d["A"])
        tb.connect(tb.ground, d["K"])
        amp = tb.part("Simulation_SPICE:OPAMP")
        tb.connect(anode, amp["+"])
        tb.connect(out, amp["-"], amp[5])
        tb.connect(vcc, amp["V+"])
        tb.connect(vee, amp["V-"])
        tb.source(vin, dc=5)
        tb.source(vcc, dc=5)
        tb.source(vee, dc=-5)
        tb.probe(d["A"])
        op = tb.operating_point()
        self.assertTrue(0.5 < op["A"] < 0.9, op["A"])
        self.assertAlmostEqual(op.current(d["A"]), (5 - op["A"]) / 4.3e3, delta=1e-9)
        self.assertAlmostEqual(op["OUT"], op["A"], delta=0.02)  # a follower, within KiCad's model's 10 mV offset

    def test_a_failed_simulation_raises_and_the_next_one_runs(self) -> None:
        floating = Testbench()
        a, b = floating.net("A"), floating.net("B")
        cap = floating.part("Device:C", value="1u")
        floating.connect(a, cap[1])
        floating.connect(b, cap[2])
        floating.source(a, dc=1)
        with self.assertRaisesRegex(SimulationError, "net B has no DC path to ground"):
            floating.operating_point()
        # A model file that includes a missing file: ngspice 45 gives up through its
        # ControlledExit callback (an older one may report a plain error); either way it raises.
        library = Path(self._tmp.name) / "broken.lib"
        library.write_text('.include "missing-nested.lib"\n.model DX D\n', encoding="utf-8")
        broken = Testbench()
        d = broken.part("Device:D", properties={"Sim.Library": str(library), "Sim.Name": "DX"})
        broken.connect(broken.net("A"), d["A"])
        broken.connect(broken.ground, d["K"])
        broken.source("A", dc=1)
        with self.assertRaisesRegex(SimulationError, "missing-nested.lib"):
            broken.operating_point()
        tb = Testbench()
        vin, out = tb.net("VIN"), tb.net("OUT")
        divider(tb, vin, out, tb.ground)
        tb.source(vin, dc=2)
        self.assertAlmostEqual(tb.operating_point()["OUT"], 1.0, delta=1e-9)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
