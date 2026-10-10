"""A testbench's SPICE netlist, without KiCad or ngspice: values, Sim.* fields, refusals.

Everything here runs against a tiny project-local symbol library written to a
temporary folder, so the suite needs neither a KiCad install nor ngspice. What
ngspice computes is the KiCad suite's (tests/python/packages/kicad/test_sim.py).
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad import ngspice  # noqa: E402
from cadgen.kicad.design import DesignError  # noqa: E402
from cadgen.kicad.install import KicadMissingError  # noqa: E402
from cadgen.kicad.sim import Testbench  # noqa: E402
from cadgen.kicad.spice import parse_value, spice_number  # noqa: E402
from cadgen.kicad.waveform import Waveform  # noqa: E402

_FONT = "(effects (font (size 1.27 1.27)))"


def _symbol(name: str, reference: str, pins: list[tuple[str, str]], fields: tuple = (), *, exclude: bool = False) -> str:
    properties = "".join(
        f'(property "{key}" "{value}" (at 0 0 0) (hide yes) {_FONT})'
        for key, value in (("Reference", reference), ("Value", name), ("Footprint", ""), *fields)
    )
    pin_text = "".join(
        f'(pin passive line (at 0 {-2.54 * index} 0) (length 2.54) (name "{pin_name}" {_FONT}) (number "{number}" {_FONT}))'
        for index, (number, pin_name) in enumerate(pins)
    )
    return (
        f'(symbol "{name}" (exclude_from_sim {"yes" if exclude else "no"}) (in_bom yes) (on_board yes) {properties}\n'
        f'(symbol "{name}_1_1" {pin_text}))\n'
    )


LIBRARY = (
    '(kicad_symbol_lib (version 20251024) (generator "cadgen-tests") (generator_version "10.0")\n'
    + _symbol("R", "R", [("1", "~"), ("2", "~")])
    + _symbol("C", "C", [("1", "~"), ("2", "~")])
    + _symbol("D", "D", [("1", "K"), ("2", "A")], (("Sim.Device", "D"), ("Sim.Pins", "1=K 2=A")))
    + _symbol("LED", "D", [("1", "K"), ("2", "A")], (("Sim.Pins", "1=K 2=A"),))
    + _symbol("NMOS_GSD", "Q", [("1", "G"), ("2", "S"), ("3", "D")])
    + _symbol("BUF", "U", [("1", "IN"), ("2", "OUT"), ("3", "GND")])
    + _symbol("HOLE", "H", [("1", "1")], exclude=True)
    + ")\n"
)


class ValueTest(unittest.TestCase):
    def test_values_read_as_kicads_simulator_reads_them(self) -> None:
        cases = {
            ("R", "10k"): 10e3, ("R", "4k7"): 4.7e3, ("R", "2R2"): 2.2, ("R", "1M"): 1e6, ("R", "1m"): 1e-3,
            ("R", "1Meg"): 1e6, ("R", "4.7kΩ"): 4.7e3, ("R", "47 k"): 47e3, ("R", "1e3"): 1e3, ("C", "100n"): 100e-9,
            ("C", "4n7"): 4.7e-9, ("C", "10uF"): 10e-6, ("C", "1µF"): 1e-6, ("L", "1uH"): 1e-6, ("V", "3V3"): 3.3,
            ("V", "DC 12"): 12.0, ("V", "-5"): -5.0, ("I", "20mA"): 0.02,
        }
        for (kind, text), expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_value(text, kind=kind), expected)

    def test_values_kicads_simulator_would_misread_are_refused(self) -> None:
        for kind, text, reason in (
            ("R", "10k 1%", "write it like 10k, 4k7"),
            ("R", "1,5k", "decimal point, not a comma"),
            ("R", "4k70", "misreads an RKM code"),
            ("R", "4.7k7", "would be dropped"),
            ("R", "R", "is not a resistance"),
            ("R", "", "empty"),
            ("C", "1F", "reads F as femto"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(DesignError, reason):
                parse_value(text, kind=kind)

    def test_spice_numbers_write_mega_as_meg(self) -> None:
        self.assertEqual(
            [spice_number(value) for value in (4700, 1e6, 1e-3, 100e-9, 2.2, 0, -5, 33e-12)],
            ["4.7k", "1Meg", "1m", "100n", "2.2", "0", "-5", "33p"],
        )


class TestbenchNetlistTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        (self.folder / "Bench.kicad_sym").write_text(LIBRARY, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def bench(self, title: str | None = None) -> Testbench:
        return Testbench(libraries=[self.folder], title=title)

    def divider(self) -> Testbench:
        tb = self.bench()
        vin, out = tb.net("VIN"), tb.net("OUT")
        r1, r2 = tb.part("Bench:R", value="10k"), tb.part("Bench:R", value="10k")
        tb.connect(vin, r1[1])
        tb.connect(out, r1[2], r2[1])
        tb.connect(tb.ground, r2[2])
        tb.source(vin, dc=5)
        return tb

    def test_a_testbench_is_written_as_kicad_reads_its_parts(self) -> None:
        tb = self.bench("filter")
        vin, out = tb.net("VIN"), tb.net("OUT")
        r1, r2 = tb.part("Bench:R", value="10k"), tb.part("Bench:R", value="4k7")
        c1 = tb.part("Bench:C", value="1u", properties={"Sim.Params": "c=100n"})  # Sim.Params wins over the value
        d1 = tb.part("Bench:D", properties={"Sim.Params": "is=1n m=2"})  # m is per instance, is the model's
        tb.connect(vin, r1[1])
        tb.connect(out, r1[2], r2[1], c1[1], d1["A"])
        tb.connect(tb.ground, r2[2], c1[2], d1["K"])
        tb.source(vin, dc=0, pulse=dict(v1=0, v2=5, rise=1e-9, fall=1e-9, width=1e-3, period=2e-3))
        tb.load(out, ohms="1M")  # a part value: M is mega, written Meg
        tb.probe(d1["A"])
        expected = (
            "* filter\n"
            ".model __D1 D(is=1n)\n"
            "R1 VIN OUT 10k\n"
            "R2 OUT 0 4.7k\n"
            "C1 OUT 0 100n\n"
            "D1 probe_D1_2 0 __D1 m=2\n"
            "Vprobe_D1_2 OUT probe_D1_2 0\n"
            "Vsrc_VIN VIN 0 DC 0 PULSE(0 5 0 1n 1n 1m 2m)\n"
            "Vload_OUT OUT load_OUT 0\n"
            "Rload_OUT load_OUT 0 1Meg\n"
            ".end\n"
        )
        self.assertEqual(tb.netlist(), expected)
        self.assertEqual(tb.netlist(), expected)

    def test_net_names_become_spice_nodes_one_to_one(self) -> None:
        tb = self.bench()
        nets = [tb.net(name) for name in ("TX/RX", "+5V", "Out", "OUT", "time", "V(z)")]
        for top, bottom in zip(nets, [*nets[1:], tb.ground]):
            part = tb.part("Bench:R", value="1k")
            tb.connect(top, part[1])
            tb.connect(bottom, part[2])
        tb.source("TX/RX", dc=1)
        nodes = [line.split()[1] for line in tb.netlist().splitlines() if line.startswith("R")]
        # ngspice folds case and names its axes "time"; "(" ends a SPICE token.
        self.assertEqual(nodes, ["TX/RX", "+5V", "Out", "OUT_2", "time_2", "V_z_"])

    def test_a_part_kicad_leaves_out_of_simulation_is_left_out(self) -> None:
        tb = self.divider()
        skipped = tb.part("Bench:R", value="not a value", properties={"Sim.Enable": "0"})
        hole = tb.part("Bench:HOLE")  # the library symbol is excluded from simulation
        tb.connect(tb.net("OUT"), skipped[1], hole[1])
        tb.connect(tb.ground, skipped[2])
        lines = tb.netlist().splitlines()
        self.assertEqual([line.split()[0] for line in lines[1:-1]], ["R1", "R2", "Vsrc_VIN"])

    def test_a_part_with_no_model_says_which_fields_to_add(self) -> None:
        tb = self.divider()
        led = tb.part("Bench:LED", value="red")
        tb.connect(tb.net("OUT"), led["A"])
        tb.connect(tb.ground, led["K"])
        with self.assertRaisesRegex(DesignError, r"D1 \(Bench:LED, value 'red'\) has no SPICE model.*'Sim.Device': 'D'.*'Sim.Enable': '0'"):
            tb.netlist()
        tb = self.divider()
        fet = tb.part("Bench:NMOS_GSD")
        for pin in fet.pins():
            tb.connect(tb.net("OUT") if pin.name == "D" else tb.ground, pin)
        with self.assertRaisesRegex(DesignError, r"'Sim.Device': 'NMOS', 'Sim.Type': 'VDMOS', 'Sim.Pins': '1=G 2=S 3=D'"):
            tb.netlist()

    def test_pins_taken_in_an_order_their_names_contradict_are_refused(self) -> None:
        tb = self.divider()
        fet = tb.part("Bench:NMOS_GSD", properties={"Sim.Device": "NMOS", "Sim.Type": "VDMOS", "Sim.Params": "vto=2"})
        tb.connect(tb.net("OUT"), fet["D"])
        tb.connect(tb.net("VIN"), fet["G"])
        tb.connect(tb.ground, fet["S"])
        with self.assertRaisesRegex(DesignError, r"names them G S D; add properties=\{'Sim.Pins': '1=G 2=S 3=D'\}"):
            tb.netlist()
        fet.properties["Sim.Pins"] = "1=G 2=S 3=D"
        text = tb.netlist()
        self.assertIn(".model __Q1 VDMOS NCHAN(vto=2)", text)
        self.assertIn("MQ1 OUT VIN 0 __Q1", text)  # SPICE's order: drain, gate, source

    def test_sim_fields_are_read_strictly(self) -> None:
        for properties, reason in (
            ({"Sim.Param": "r=1k"}, "does not read; did you mean Sim.Params"),
            ({"Sim.Params": "r=4k7"}, "r=4k7 is not a number KiCad's simulator reads the same way"),
            ({"Sim.Params": "r=1k tc1=0.001"}, "ideal resistor takes one parameter, r="),
            ({"Sim.Device": "SW"}, "does not simulate Sim.Device=SW"),
        ):
            tb = self.divider()
            part = tb.part("Bench:R", value="1k", properties=properties)
            tb.connect(tb.net("OUT"), part[1])
            tb.connect(tb.ground, part[2])
            with self.subTest(properties=properties), self.assertRaisesRegex(DesignError, reason):
                tb.netlist()
        tb = self.divider()
        part = tb.part("Bench:R", value="1k", properties={"Sim.Params": "r=1M"})
        tb.connect(tb.net("OUT"), part[1])
        tb.connect(tb.ground, part[2])
        self.assertIn("R3 OUT 0 1Meg", tb.netlist())

    def test_a_model_file_is_found_from_the_folder_of_the_script_that_made_the_testbench(self) -> None:
        (self.folder / "models").mkdir()
        model = self.folder / "models" / "amp.lib"
        model.write_text("* a buffer\n.subckt AMP in out gnd params: gain=2\nE1 out gnd in gnd {gain}\n.ends AMP\n", encoding="utf-8")
        script = self.folder / "bench_script.py"
        script.write_text("from cadgen.kicad.sim import Testbench\n\n\ndef make(libraries):\n    return Testbench(libraries=libraries)\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("bench_script_for_sim_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tb = module.make([self.folder])
        self.assertEqual(tb.folder, self.folder.resolve())
        amp = tb.part("Bench:BUF", properties={"Sim.Library": "models/amp.lib", "Sim.Name": "AMP", "Sim.Params": "gain=3"})
        tb.connect(tb.net("IN"), amp["IN"])
        tb.connect(tb.net("OUT"), amp["OUT"])
        tb.connect(tb.ground, amp["GND"])
        tb.source("IN", dc=1)
        text = tb.netlist()
        self.assertIn(f'.include "{model.resolve()}"', text)
        self.assertIn("XU1 IN OUT 0 AMP gain=3", text)  # pins in the .subckt's port order
        amp.properties["Sim.Name"] = "AMPS"
        with self.assertRaisesRegex(DesignError, r"amp.lib has no .model or .subckt named 'AMPS'; did you mean AMP\?"):
            tb.netlist()

    def test_sources_and_loads_take_closed_keywords(self) -> None:
        tb = self.divider()
        out = tb.net("OUT")
        for call, reason in (
            (lambda: tb.source(out, volts=5), r"source\(\) has no volts; its keywords are dc, ac, pulse, sine, pwl, reference"),
            (lambda: tb.source(out, pulse=dict(v1=0, v2=1, high=3)), "pulse= has no high; its keys are v1, v2, delay"),
            (lambda: tb.source(out, sine=dict(amplitude=1)), "sine= needs frequency"),
            (lambda: tb.source(out, pulse=dict(v1=0, v2=1), pwl=[(0, 0)]), "one waveform"),
            (lambda: tb.source(out), "needs a value"),
            (lambda: tb.source("NOPE", dc=1), "'NOPE' is not a net of this testbench"),
            (lambda: tb.load(out, watts=1), r"load\(\) has no watts"),
            (lambda: tb.load(out), r"load\(\) needs ohms="),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(DesignError, reason):
                call()

    def test_a_testbench_without_ground_is_refused(self) -> None:
        tb = self.bench()
        a, b = tb.net("A"), tb.net("B")
        r1 = tb.part("Bench:R", value="1k")
        tb.connect(a, r1[1])
        tb.connect(b, r1[2])
        tb.source(a, dc=1, reference=b)
        with self.assertRaisesRegex(DesignError, "no ground: SPICE measures every voltage from node 0, the net named GND"):
            tb.netlist()

    def test_an_ac_run_needs_a_stimulus_before_anything_runs(self) -> None:
        with self.assertRaisesRegex(DesignError, r"ac\(\) needs a stimulus.*ac=1"):
            self.divider().ac(1, 1e3)

    def test_a_missing_ngspice_is_reported_only_when_a_simulation_runs(self) -> None:
        tb = self.divider()
        with mock.patch.object(ngspice, "_ENGINE", None), mock.patch.object(ngspice, "library_candidates", return_value=[]):
            self.assertIn("R1 VIN OUT 10k", tb.netlist())
            with self.assertRaisesRegex(KicadMissingError, "ngspice, the simulator KiCad ships, was not found.*CADGEN_NGSPICE"):
                tb.operating_point()


class WaveformTest(unittest.TestCase):
    def test_crossings_narrow_to_a_direction_and_a_window(self) -> None:
        wave = Waveform([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 2.0, 0.0, 2.0, 0.0], name="V(A)", unit="V", axis="time", axis_unit="s")
        self.assertEqual(wave.crossings(1.0), [0.5, 1.5, 2.5, 3.5])
        self.assertEqual(wave.crossings(1.0, rising=True), [0.5, 2.5])
        self.assertEqual(wave.crossings(1.0, rising=False, start=2.0), [3.5])
        self.assertEqual(list(wave.window(1.0, 3.0).x), [1.0, 2.0, 3.0])
        self.assertEqual(wave.window(1.5, 3.0).min(), 0.0)


if __name__ == "__main__":
    unittest.main()
