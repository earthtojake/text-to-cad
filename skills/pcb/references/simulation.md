# Simulation: checking a board's circuits with SPICE

KiCad's ERC and DRC prove a board is connected and can be made. They do not prove the
divider gives 3.3 V, the filter's corner is at 1 kHz, the LED gets 10 mA or the transistor
saturates. A testbench simulates the board's own subcircuits with ngspice, the simulator
KiCad 10 ships, and your script asserts the numbers. It is a check, like
`cadgen.geometry`: no decorator and no output files, only facts for the script to judge.

## When to simulate

- Analog values: dividers, references, a regulator's feedback network, sensor front ends.
- Filters and timing: RC/LC corners, debounce and reset delays, oscillator RCs.
- Power: LED and load currents, a resistor's dissipation, a regulator under its load (with
  the maker's model), inrush into a capacitor.
- Switches: transistor saturation, base and gate drive, turn-on thresholds.

Skip it for digital logic, firmware and RF. It cannot see track resistance or inductance,
temperature, or part tolerances you do not sweep. Never make up a vendor model's
parameters: use the maker's model, or say the part was simulated with a generic one.

## Share the subcircuit with the board

Put each subcircuit in a plain function of a circuit, in a module beside the board script.
The `@pcb` script and the test script both import it, so the circuit you simulate is the
circuit you lay out.

- Give every part its footprint, which the board needs and a testbench ignores, and its
  simulation fields (below). They then reach the board's schematic too, and KiCad's own
  simulator reads the same model.
- Leave internal nets unnamed (`c.net()`) so the function can be used twice. Return the
  parts and nets a test reads; results take a net object or a net's name.
- Make the values you want to vary parameters (`resistor="270"`).

## Giving parts a model

Parts simulate from KiCad's own simulation fields, read the way KiCad reads them. These
need no fields:

| Part | Simulates as |
| --- | --- |
| `Device:R`, `C`, `L` and kin (two pins, reference R/C/L) | an ideal part of its value: `10k`, `4k7`, `2R2`, `100n`, `1M` (mega), `1m` (milli) |
| `Device:D` | SPICE's default diode (the symbol carries `Sim.Device=D`) |
| `Device:Battery` | a DC source of its value (`3V3`) |
| `Simulation_SPICE:*` | KiCad's simulation symbols: sources, generic NPN/PNP/NMOS/PMOS, `OPAMP` |

A value KiCad's simulator would misread is refused with the fix: `10k 1%` (put the
tolerance in another property), `4k70`, `1,5k`, or a capacitor `1F` (SPICE's F is femto).
Every other part needs fields in `properties=` or it is refused, naming the fields to add:

| Field | Meaning |
| --- | --- |
| `Sim.Device` | `R` `C` `L` `D` `NPN` `PNP` `NJFET` `PJFET` `NMOS` `PMOS` `V` `I` `SUBCKT` |
| `Sim.Type` | the model: `GUMMELPOON`/`VBIC` (BJT), `VDMOS`/`MOS1`... (MOSFET), `DC`/`PULSE`/`SIN` (source) |
| `Sim.Params` | `name=value` pairs: `bf=200 is=1e-14`. Numbers as `4.7k`, `10u`, `1M` (mega), no units |
| `Sim.Pins` | symbol pin number = model pin: `1=K 2=A`, `1=G 2=S 3=D`, `1=IN 2=GND 3=OUT` |
| `Sim.Library`, `Sim.Name` | a model file and the `.model` or `.subckt` in it |
| `Sim.Enable` | `0` leaves the part out of simulation |

```python
# LED: KiCad's symbol names its pins but has no model (forward voltage depends on colour)
properties={"Sim.Device": "D", "Sim.Params": "is=6e-19 n=2 rs=2"}      # red: 2.0 V at 20 mA
properties={"Sim.Device": "D", "Sim.Params": "is=1.5e-19 n=3 rs=2"}    # blue/white: 3.1 V at 20 mA
# BJT: Transistor_BJT symbols carry Sim.Device and Sim.Pins; add the model and its parameters
properties={"Sim.Type": "GUMMELPOON", "Sim.Params": "is=6.734f bf=416 vaf=74 rb=10 rc=1"}  # 2N3904-class
# MOSFET: Transistor_FET symbols carry nothing; map the pins by their names
properties={"Sim.Device": "NMOS", "Sim.Type": "VDMOS", "Sim.Pins": "1=G 2=S 3=D",
            "Sim.Params": "vto=1.6 kp=0.5 rd=0.1"}                      # PMOS: vto=-1.6
# An IC: the maker's SPICE model; map each pin number to a port of its .subckt line
properties={"Sim.Library": "models/AP2112.lib", "Sim.Name": "AP2112K-3.3",
            "Sim.Pins": "1=VIN 2=GND 3=EN 5=VOUT"}
# A connector, test point or mounting hole
properties={"Sim.Enable": "0"}
```

- Without `Sim.Pins`, pins are taken in number order as the model's: diode A K, BJT C B E,
  MOSFET D G S, a subcircuit in its port order. An order the symbol's own pin names
  contradict (a GSD MOSFET read as DGS) is refused, with the `Sim.Pins` to add.
- `Sim.Library` paths start at the folder of the script that made the testbench. Keep model
  files in `models/` beside the scripts: KiCad resolves the same relative path from its
  project folder, which is the board script's folder unless `@pcb(out=...)` moves it. An
  absolute path and `${KICAD10_SYMBOL_DIR}/Simulation_SPICE.sp` work too. The file is read
  when the testbench is simulated.
- To replace an IC you have no model for, leave it out (`Sim.Enable=0`) and drive its
  output net from the testbench: an LDO becomes `tb.source(vout, dc=3.3)`.

## The testbench

`pcb.Testbench(libraries=[...], title=...)` is a circuit like a board: `part`, `net`,
`connect` and `no_connect` work the same, footprints optional. Ground, SPICE's node 0, is the
net named `GND` (or `0`); `tb.ground` finds or makes it. A testbench with no ground is
refused.

| Call | What it adds |
| --- | --- |
| `tb.source(net, dc=, ac=, pulse=, sine=, pwl=, reference=gnd)` | a voltage source, `net` positive |
| `tb.current_source(net, ...)` | the same keywords, in amps driven into `net` |
| `tb.load(net, ohms=, farads=, henries=, reference=gnd)` | any of R, C, L in parallel (numbers or values like `"4k7"`) |
| `tb.probe(*pins)` | current meters on pins: `run.current(pin)` |
| `tb.netlist()` | the SPICE text simulated, for reading and debugging |

`dc` is the source's value for the operating point and what `dc_sweep` sweeps; with a
waveform, set it to the waveform's value at time 0. Waveforms are SPICE's, keyed by name:
`pulse=dict(v1, v2, delay, rise, fall, width, period)` (no width and period is a step),
`sine=dict(offset, amplitude, frequency, delay, damping, phase)`, `pwl=[(t, v), ...]`.
`ac=1` (or `(magnitude, degrees)`) marks the input of an AC analysis.

| Analysis | Returns |
| --- | --- |
| `tb.operating_point()` | each net's DC voltage as a float: `op["OUT"]`, `op[net]`, `op.current(src)` |
| `tb.transient(stop, step=None, start=0.0)` | a run over `run.time`; `step` is the longest time step (default a thousandth of the run) |
| `tb.ac(start, stop, points_per_decade=20)` | a run over `run.frequency`; values are complex |
| `tb.dc_sweep(source_or_net, start, stop, step)` | a run over `run.sweep`, the source's DC value |

A run's `run["OUT"]` and `run.current(source | load | probed pin)` are waveforms: `x` and
`values` (numpy arrays), `final`, `initial`, `max()`, `min()`, `at(x)` (interpolated),
`crossings(level, *, rising=None, start=None, stop=None)` (every axis value where it crosses;
`rising=True` only upward, `False` only downward, `start`/`stop` bound the axis),
`window(start, stop)` (the waveform between two axis values), and for AC `db`, `phase`
(degrees, unwrapped) and `magnitude`. `run["A"] - run["B"]` is the voltage across a part. A current
is positive into what it measures: a source's current is what it delivers into its net,
a load's or a pin's what the net feeds into it.

`run.plot("tmp/name.png", nets=[...], currents=[...])` draws a PNG (an AC run as gain over
phase). Look at it: a plot shows ringing, overshoot and a node floating where you expected a
level, which a single number hides.

A mistake in the testbench raises `DesignError` before anything runs, saying what to fix.
A circuit ngspice cannot solve raises `SimulationError` with ngspice's words and the likely
cause: "net X has no DC path to ground" means a node only capacitors reach (add
`tb.load(x, ohms=1e9)` or the bias resistor the real circuit needs). Its `log` holds
everything ngspice printed. With no ngspice (KiCad not installed; on Linux the
`libngspice0` package), simulating says how to install it; `CADGEN_NGSPICE` names the
library explicitly.

## Worked example

An indicator LED that a 3.3 V GPIO switches through an NPN, from 5 V. The subcircuit:

```python
# indicator.py
R_0603 = "Resistor_SMD:R_0603_1608Metric"


def led_switch(c, vcc, gpio, gnd, *, resistor="270"):
    r = c.part("Device:R", footprint=R_0603, value=resistor)
    led = c.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="red",
                 properties={"Sim.Device": "D", "Sim.Params": "is=6e-19 n=2 rs=2"})
    rb = c.part("Device:R", footprint=R_0603, value="4k7")
    q = c.part("Transistor_BJT:Q_NPN_BEC", footprint="Package_TO_SOT_SMD:SOT-23", value="MMBT3904",
               properties={"Sim.Type": "GUMMELPOON",
                           "Sim.Params": "is=6.734f bf=416 vaf=74 ikf=67m rb=10 rc=1 cje=4.5p cjc=3.6p tf=301p tr=240n"})
    anode, collector, base = c.net(), c.net(), c.net()
    c.connect(vcc, r[1])
    c.connect(anode, r[2], led["A"])
    c.connect(collector, led["K"], q["C"])
    c.connect(gpio, rb[1])
    c.connect(base, rb[2], q["B"])
    c.connect(gnd, q["E"])
    return led, q
```

The board script calls `led, q = led_switch(board, vbus, gpio, gnd)` and places the parts.
The test script:

```python
# indicator_sim.py
from cadgen import pcb

from indicator import led_switch

tb = pcb.Testbench(title="LED switch")
vcc, gpio = tb.net("VCC"), tb.net("GPIO")
led, q = led_switch(tb, vcc, gpio, tb.ground)
tb.source(vcc, dc=5.0)
drive = tb.source(gpio, dc=0, pulse=dict(v1=0, v2=3.3, delay=0.2e-3, rise=10e-9, fall=10e-9,
                                         width=0.5e-3, period=1e-3))
tb.probe(led["A"], q["B"])

off = tb.operating_point()                       # GPIO at its dc=0
assert off.current(led["A"]) < 1e-6

on = tb.dc_sweep(drive, 0, 3.3, 0.05)            # GPIO from low to high
i_led = on.current(led["A"])
assert 9e-3 < i_led.final < 12e-3, i_led.final   # 10.9 mA
assert on[q["C"].net].final < 0.2                # saturated: VCE 0.10 V
assert on.current(q["B"]).final < 1e-3           # the GPIO sources 0.54 mA
print("LED reaches 1 mA at GPIO", i_led.crossings(1e-3))   # [0.67...]

run = tb.transient(stop=2e-3, step=1e-6)
assert run.current(led["A"]).max() < 12e-3
run.plot("tmp/led_switch.png", nets=["GPIO"], currents=[led["A"]])
```

`python indicator_sim.py` passes silently but for its print, or stops at the first assert
that fails. To choose the resistor, build one testbench per candidate in a loop: 220 ohm
gives 13.3 mA, 270 ohm 10.9 mA, 330 ohm 9.0 mA. Report what you simulated, the
numbers, and which models were generic.
