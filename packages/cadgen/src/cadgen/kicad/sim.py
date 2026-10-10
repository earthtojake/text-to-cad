"""Circuit simulation: a testbench of the parts a board uses, simulated by ngspice.

A :class:`Testbench` is a :class:`~cadgen.kicad.design.Circuit` -- parts from
KiCad's libraries, nets, ``connect`` and ``no_connect``, footprints optional --
plus what a bench adds: sources, loads, current probes and analyses. A
subcircuit written as a function of a circuit builds into a ``Board`` or a
``Testbench`` unchanged, so the circuit a board script lays out is the circuit
a test script simulates::

    tb = Testbench()
    vin, out = tb.net("VIN"), tb.net("OUT")
    divider(tb, vin, out, tb.ground)        # the board's own subcircuit
    tb.source(vin, dc=5.0)
    assert abs(tb.operating_point()["OUT"] - 2.5) < 1e-6

Like ``cadgen.geometry`` it returns facts -- node voltages, currents, waveforms
-- and the script decides what passes. There is no decorator, file kind or
command line: a testbench runs inside the script that builds it.

Parts simulate from KiCad's own simulation fields (``Sim.Device``,
``Sim.Params``, ``Sim.Library``...; see :mod:`cadgen.kicad.spice`), so a model
works in cadgen and in KiCad's simulator alike. Ground, SPICE's node 0, is the
net named ``GND`` (any case) or ``0``; ``tb.ground`` makes or finds it.

Sign conventions, all "into the thing measured": ``run.current(source)`` is the
current a source drives out of its + terminal into its net (positive when it
powers the circuit); ``run.current(load)`` the current a net feeds into a load;
``run.current(pin)`` the current a net feeds into a probed pin.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from cadgen.kicad.design import Circuit, DesignError, Net, Part, Pin
from cadgen.kicad.ngspice import error_hints
from cadgen.kicad.sim_plot import plot_run
from cadgen.kicad.spice import PartModel, parse_value, part_model, spice_number, to_number
from cadgen.kicad.waveform import Waveform

__all__ = ["Load", "OperatingPoint", "Run", "SimulationError", "Source", "Testbench", "Waveform"]


class SimulationError(RuntimeError):
    """ngspice could not simulate the testbench. The message says why; ``log`` is all it printed."""

    def __init__(self, message: str, *, log: Sequence[str] = ()):
        super().__init__(message)
        self.log = "\n".join(log)


class UnknownNetError(KeyError, DesignError):
    """A net name a result does not have (a ``KeyError``, so ``in`` and ``get`` work)."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


def _is_ground(name: str) -> bool:
    return name == "0" or name.lower() == "gnd"


def _calling_folder() -> Path:
    """The folder of the script that made the testbench: where its relative model paths start."""
    frame = sys._getframe(1)
    while frame is not None and str(frame.f_globals.get("__name__", "")).split(".")[0] == "cadgen":
        frame = frame.f_back
    script = frame.f_globals.get("__file__") if frame is not None else None
    return Path(script).resolve().parent if script else Path.cwd().resolve()


def _positive(value: Any, *, what: str) -> float:
    number = to_number(value, what=what)
    if number <= 0:
        raise DesignError(f"{what} must be greater than 0, got {value!r}")
    return number


def _closed(method: str, unknown: Mapping[str, Any], keys: Sequence[str]) -> None:
    if unknown:
        raise DesignError(f"{method}() has no {', '.join(sorted(unknown))}; its keywords are {', '.join(keys)}")


def _keys(value: Any, keys: Sequence[str], required: Sequence[str], *, what: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DesignError(f"{what}= takes a dict with keys {', '.join(keys)}, got {value!r}")
    unknown = sorted(str(key) for key in value if key not in keys)
    if unknown:
        raise DesignError(f"{what}= has no {', '.join(unknown)}; its keys are {', '.join(keys)}")
    missing = [key for key in required if key not in value]
    if missing:
        raise DesignError(f"{what}= needs {', '.join(missing)} (its keys are {', '.join(keys)})")
    return dict(value)


# --- what the bench adds to the circuit -----------------------------------------------


class Source:
    """A voltage or current source driving a net; ``run.current(source)`` measures it."""

    __slots__ = ("kind", "net", "reference", "stimulus", "has_ac", "_bench")

    def __init__(self, bench: "Testbench", kind: str, net: Net, reference: Net, stimulus: str, has_ac: bool):
        self._bench = bench
        self.kind = kind
        self.net = net
        self.reference = reference
        self.stimulus = stimulus
        self.has_ac = has_ac

    def __repr__(self) -> str:
        return f"Source({self.kind} {self.net.name} to {self.reference.name}: {self.stimulus})"


class Load:
    """Passives from a net to its reference (ground by default); ``run.current(load)`` measures it."""

    __slots__ = ("net", "reference", "ohms", "farads", "henries", "_bench")

    def __init__(self, bench: "Testbench", net: Net, reference: Net, ohms: float | None, farads: float | None, henries: float | None):
        self._bench = bench
        self.net = net
        self.reference = reference
        self.ohms = ohms
        self.farads = farads
        self.henries = henries

    def __repr__(self) -> str:
        values = [f"{spice_number(value)}{unit}" for value, unit in ((self.ohms, "ohm"), (self.farads, "F"), (self.henries, "H")) if value is not None]
        return f"Load({self.net.name} to {self.reference.name}: {' || '.join(values)})"


_SOURCE_KEYS = ("dc", "ac", "pulse", "sine", "pwl", "reference")
_LOAD_KEYS = ("ohms", "farads", "henries", "reference")
_PULSE_KEYS = ("v1", "v2", "delay", "rise", "fall", "width", "period")
_SINE_KEYS = ("offset", "amplitude", "frequency", "delay", "damping", "phase")


def _stimulus(*, dc: Any, ac: Any, pulse: Any, sine: Any, pwl: Any, unit: str) -> tuple[str, bool]:
    """The SPICE text of a source's value, and whether it has an AC magnitude."""
    given = [name for name, value in (("pulse", pulse), ("sine", sine), ("pwl", pwl)) if value is not None]
    if len(given) > 1:
        raise DesignError(f"a source has one waveform; it was given {' and '.join(given)}")
    if dc is None and ac is None and not given:
        raise DesignError("a source needs a value: dc=, ac= (for ac()), or a waveform: pulse=, sine= or pwl=")
    words: list[str] = []
    if dc is not None:
        words.append(f"DC {spice_number(to_number(dc, what='dc'))}")
    if ac is not None:
        if isinstance(ac, (tuple, list)):
            if len(ac) != 2:
                raise DesignError(f"ac= is a magnitude, or (magnitude, phase in degrees); got {ac!r}")
            magnitude, phase = to_number(ac[0], what="ac magnitude"), to_number(ac[1], what="ac phase")
            words.append(f"AC {spice_number(magnitude)} {spice_number(phase)}")
        else:
            words.append(f"AC {spice_number(to_number(ac, what='ac'))}")
    if pulse is not None:
        spec = _keys(pulse, _PULSE_KEYS, ("v1", "v2"), what="pulse")
        values = [spice_number(to_number(spec[key], what=f"pulse {key}")) for key in ("v1", "v2")]
        for key in ("delay", "rise", "fall", "width", "period"):
            if key not in spec:
                values.append("0")  # SPICE's own default: rise/fall the step, width/period the whole run
                continue
            number = to_number(spec[key], what=f"pulse {key}")
            if number < 0 or (number == 0 and key != "delay"):
                raise DesignError(
                    f"pulse {key} must be {'0 or more' if key == 'delay' else 'greater than 0'}, got {spec[key]!r}"
                    + ("" if key == "delay" else " (leave it out for SPICE's default)")
                )
            values.append(spice_number(number))
        words.append(f"PULSE({' '.join(values)})")
    if sine is not None:
        spec = _keys(sine, _SINE_KEYS, ("amplitude", "frequency"), what="sine")
        frequency = _positive(spec["frequency"], what="sine frequency")
        delay = to_number(spec.get("delay", 0), what="sine delay")
        if delay < 0:
            raise DesignError(f"sine delay must be 0 or more, got {spec['delay']!r}")
        values = [
            to_number(spec.get("offset", 0), what="sine offset"),
            to_number(spec["amplitude"], what="sine amplitude"),
            frequency,
            delay,
            to_number(spec.get("damping", 0), what="sine damping"),
            to_number(spec.get("phase", 0), what="sine phase"),
        ]
        words.append(f"SIN({' '.join(spice_number(value) for value in values)})")
    if pwl is not None:
        try:
            points = [(to_number(time, what="pwl time"), to_number(value, what=f"pwl {unit}")) for time, value in pwl]
        except (TypeError, ValueError) as error:
            if isinstance(error, DesignError):
                raise
            raise DesignError(f"pwl= is a list of (time, value) pairs, for example [(0, 0), (1e-3, 5)]; got {pwl!r}") from None
        if not points:
            raise DesignError("pwl= needs at least one (time, value) pair")
        times = [time for time, _value in points]
        if times[0] < 0 or any(later < earlier for earlier, later in zip(times, times[1:])):
            raise DesignError(f"pwl= times start at 0 or later and never go back; got {times}")
        words.append(f"PWL({' '.join(f'{spice_number(time)} {spice_number(value)}' for time, value in points)})")
    return " ".join(words), ac is not None


# --- the netlist a testbench compiles to ------------------------------------------------

_UNSAFE = re.compile(r"[^A-Za-z0-9_+\-/:]")
# Names a node may not take: ngspice's ground, and the axes of its plots.
_RESERVED = {"0", "gnd", "time", "frequency", "v-sweep", "i-sweep", "temp-sweep", "res-sweep"}


@dataclass
class _Deck:
    text: str
    lines: list[str]
    node_of: dict[int, str]  # id(net) -> node
    nets: dict[str, Net]  # every net the netlist uses, by name, in the order they were made
    meters: dict[Any, tuple[str, float]]  # what run.current measures -> (vector, sign)
    sources: dict[int, str]  # id(source) -> its element
    described: dict[str, str]  # lowercased node or element -> what it is, for messages
    ac_sources: int


class _Names:
    """Unique SPICE names (ngspice folds case), in the order they are claimed."""

    def __init__(self, reserved: Iterable[str] = ()):
        self.used = {name.lower() for name in reserved}

    def claim(self, base: str) -> str:
        candidate, count = base, 2
        while candidate.lower() in self.used:
            candidate = f"{base}_{count}"
            count += 1
        self.used.add(candidate.lower())
        return candidate


class Testbench(Circuit):
    """A circuit to simulate: parts and nets as on a board, plus sources, loads and analyses.

    ``libraries`` are project symbol-library folders, searched before KiCad's.
    Relative ``Sim.Library`` paths start at :attr:`folder`, the folder of the
    script that made the testbench (KiCad starts them at its project's folder).
    """

    def __init__(self, *, libraries: Iterable[str | Path] = (), title: str | None = None):
        super().__init__(libraries=libraries)
        self.title = " ".join(str(title).split()) if title is not None and str(title).strip() else "cadgen testbench"
        self._folder = _calling_folder()
        self._sources: list[Source] = []
        self._loads: list[Load] = []
        self._probes: dict[tuple[int, str], Pin] = {}

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def ground(self) -> Net:
        """The ground net, SPICE's node 0: the net named GND (or 0), made when there is none."""
        for net in self._nets:
            if net.named and _is_ground(net.name):
                return net
        return self.net("GND")

    def _net_of(self, value: Any, *, what: str) -> Net:
        if isinstance(value, Net):
            if value._board is not self:
                raise DesignError(f"{what} is a net of another board or testbench")
            return value
        if isinstance(value, str):
            net = self._named_nets.get(value)
            if net is None:
                names = ", ".join(net.name for net in self._nets if net.named) or "none yet"
                raise DesignError(f"{what} {value!r} is not a net of this testbench (its named nets: {names})")
            return net
        raise DesignError(f"{what} takes a net (tb.net('VIN')) or a net's name, got {value!r}")

    # -- what the bench adds --

    def source(self, net: Net | str, *, dc: Any = None, ac: Any = None, pulse: Any = None, sine: Any = None,
               pwl: Any = None, reference: Net | str | None = None, **unknown: Any) -> Source:
        """A voltage source from ``reference`` (ground by default) to ``net``.

        ``dc`` volts (the operating point, and what ``dc_sweep`` sweeps); ``ac``
        the magnitude ``ac()`` drives (or ``(magnitude, degrees)``); one transient
        waveform: ``pulse=dict(v1, v2, delay, rise, fall, width, period)``,
        ``sine=dict(offset, amplitude, frequency, delay, damping, phase)`` or
        ``pwl=[(time, volts), ...]``. Times in seconds, frequencies in hertz.
        """
        _closed("source", unknown, _SOURCE_KEYS)
        return self._add_source("voltage", net, reference, _stimulus(dc=dc, ac=ac, pulse=pulse, sine=sine, pwl=pwl, unit="volts"))

    def current_source(self, net: Net | str, *, dc: Any = None, ac: Any = None, pulse: Any = None, sine: Any = None,
                       pwl: Any = None, reference: Net | str | None = None, **unknown: Any) -> Source:
        """A current source driving amps from ``reference`` (ground by default) into ``net``.

        The same keywords as :meth:`source`, in amps.
        """
        _closed("current_source", unknown, _SOURCE_KEYS)
        return self._add_source("current", net, reference, _stimulus(dc=dc, ac=ac, pulse=pulse, sine=sine, pwl=pwl, unit="amps"))

    def _add_source(self, kind: str, net: Any, reference: Any, stimulus: tuple[str, bool]) -> Source:
        target = self._net_of(net, what="a source's net")
        back = self.ground if reference is None else self._net_of(reference, what="reference")
        if target is back or (_is_ground(target.name) and _is_ground(back.name)):
            raise DesignError(f"a source from {back.name} to {target.name} drives nothing: give it the net it drives")
        source = Source(self, kind, target, back, *stimulus)
        self._sources.append(source)
        return source

    def load(self, net: Net | str, *, ohms: Any = None, farads: Any = None, henries: Any = None,
             reference: Net | str | None = None, **unknown: Any) -> Load:
        """A load from ``net`` to ``reference`` (ground by default): a resistor, capacitor and/or
        inductor in parallel. Values are numbers or part values (``'4k7'``, ``'100n'``)."""
        _closed("load", unknown, _LOAD_KEYS)
        values = {}
        for key, value, kind in (("ohms", ohms, "R"), ("farads", farads, "C"), ("henries", henries, "L")):
            if value is None:
                continue
            number = parse_value(value, kind=kind, ref=f"load {key}") if isinstance(value, str) else to_number(value, what=key)
            if number <= 0:
                raise DesignError(f"load {key} must be greater than 0, got {value!r}")
            values[key] = number
        if not values:
            raise DesignError("load() needs ohms=, farads= or henries=")
        target = self._net_of(net, what="a load's net")
        back = self.ground if reference is None else self._net_of(reference, what="reference")
        if target is back:
            raise DesignError(f"a load from {target.name} to itself does nothing")
        load = Load(self, target, back, values.get("ohms"), values.get("farads"), values.get("henries"))
        self._loads.append(load)
        return load

    def probe(self, *pins: Pin) -> None:
        """Measure the current each net feeds into these pins: ``run.current(pin)``.

        A probe is a 0 V source between the pin and its net, so it changes nothing.
        """
        if not pins:
            raise DesignError("probe() takes pins, for example tb.probe(d1['A'])")
        for pin in pins:
            pin = self._owned_pin(pin, what="probe")
            if pin.net is None:
                raise DesignError(f"{pin!r} is on no net, so no current flows into it; connect it first")
            self._probes[pin.key] = pin

    # -- the netlist --

    def netlist(self) -> str:
        """The SPICE netlist the analyses simulate (the analysis itself is not in it)."""
        return self._compile().text

    def _compile(self) -> _Deck:
        modelled: list[tuple[Part, PartModel]] = []
        for part in self._parts:
            model = part_model(part, folder=self._folder)
            if model is not None:
                modelled.append((part, model))
        touched: set[int] = set()
        for _part, model in modelled:
            touched.update(id(pin.net) for pins in model.pins for pin in pins if pin.net is not None)
        for handle in (*self._sources, *self._loads):
            touched.update((id(handle.net), id(handle.reference)))
        used = [net for net in self._nets if id(net) in touched]
        grounds = [net for net in used if _is_ground(net.name)]
        if len(grounds) > 1:
            raise DesignError(
                f"nets {' and '.join(net.name for net in grounds)} are both ground in SPICE (node 0) but "
                "separate nets here; name one ground net GND and connect through it"
            )
        nodes = _Names(_RESERVED)
        node_of: dict[int, str] = {}
        described: dict[str, str] = {}
        for net in used:
            node = "0" if _is_ground(net.name) else nodes.claim(_UNSAFE.sub("_", net.name))
            node_of[id(net)] = node
            described[node.lower()] = f"net {net.name}"
        elements = _Names()
        cards: list[str] = []
        includes: list[Path] = []
        lines: list[str] = []
        meters: dict[Any, tuple[str, float]] = {}
        sources: dict[int, str] = {}
        grounded = False
        ac_sources = 0

        def element(letter: str, base: str, what: str) -> str:
            base = re.sub(r"[^A-Za-z0-9_]", "_", base)
            name = elements.claim(base if base[:1].upper() == letter else f"{letter}{base}")
            described[name.lower()] = what
            return name

        def inner(base: str, what: str) -> str:
            node = nodes.claim(re.sub(r"[^A-Za-z0-9_]", "_", base))
            described[node.lower()] = what
            return node

        for part, model in modelled:
            for path in ([model.include] if model.include is not None else []):
                if path not in includes:
                    includes.append(path)
            for card in model.models:
                if card not in cards:
                    cards.append(card)
            if model.letter in ("V", "I") and " AC " in f" {model.tail} ":
                ac_sources += 1
            name = element(model.letter, part.ref, part.ref)
            element_nodes: list[str] = []
            after: list[str] = []
            for model_pin, pins in zip(model.model_pins, model.pins):
                if not pins:
                    continue  # an optional model pin (a substrate) no symbol pin is mapped to
                on = {id(pin.net): pin.net for pin in pins if pin.net is not None}
                if len(on) > 1:
                    raise DesignError(
                        f"{part.ref}: pins {', '.join(pin.number for pin in pins)} are all its model's {model_pin} "
                        f"(Sim.Pins), but they are on different nets ({', '.join(net.name for net in on.values())})"
                    )
                if on:
                    node = node_of[next(iter(on))]
                else:
                    node = inner(f"nc_{part.ref}_{pins[0].number}", f"{part.ref} pin {pins[0].number} (on no net)")
                grounded = grounded or node == "0"
                probed = [pin for pin in pins if pin.key in self._probes]
                if probed:
                    label = f"{part.ref}_{probed[0].number}"
                    pin_node = inner(f"probe_{label}", f"{part.ref} pin {probed[0].number}")
                    meter = element("V", f"probe_{label}", f"the probe on {part.ref} pin {probed[0].number}")
                    after.append(f"{meter} {node} {pin_node} 0")
                    for pin in probed:
                        meters[("pin", pin.key)] = (f"{meter.lower()}#branch", 1.0)
                    node = pin_node
                element_nodes.append(node)
            lines.append(" ".join([name, *element_nodes, model.tail]))
            lines.extend(after)
        for source in self._sources:
            plus, minus = node_of[id(source.net)], node_of[id(source.reference)]
            grounded = grounded or "0" in (plus, minus)
            ac_sources += source.has_ac
            if source.kind == "voltage":
                name = element("V", f"src_{plus}", f"the source on {source.net.name}")
                lines.append(f"{name} {plus} {minus} {source.stimulus}")
                meters[id(source)] = (f"{name.lower()}#branch", -1.0)
            else:
                name = element("I", f"src_{plus}", f"the current source on {source.net.name}")
                feed = inner(f"isrc_{plus}", f"the current source on {source.net.name}")
                meter = element("V", f"meter_{name}", f"the current source on {source.net.name}")
                lines.append(f"{name} {minus} {feed} {source.stimulus}")
                lines.append(f"{meter} {feed} {plus} 0")
                meters[id(source)] = (f"{meter.lower()}#branch", 1.0)
            sources[id(source)] = name
        for load in self._loads:
            top, bottom = node_of[id(load.net)], node_of[id(load.reference)]
            grounded = grounded or "0" in (top, bottom)
            what = f"the load on {load.net.name}"
            feed = inner(f"load_{top}", what)
            meter = element("V", f"load_{top}", what)
            lines.append(f"{meter} {top} {feed} 0")
            for letter, value in (("R", load.ohms), ("C", load.farads), ("L", load.henries)):
                if value is not None:
                    lines.append(f"{element(letter, f'load_{top}', what)} {feed} {bottom} {spice_number(value)}")
            meters[id(load)] = (f"{meter.lower()}#branch", 1.0)
        if not lines:
            raise DesignError("the testbench is empty: add parts with tb.part(...) and a source with tb.source(...)")
        if not grounded:
            raise DesignError(
                "the testbench has no ground: SPICE measures every voltage from node 0, the net named GND. "
                "Connect your circuit's ground to tb.ground (or name that net GND), or give a source "
                "reference= a grounded net"
            )
        deck_lines = [f"* {self.title}", *(f'.include "{path}"' for path in includes), *cards, *lines, ".end"]
        return _Deck(
            text="\n".join(deck_lines) + "\n",
            lines=deck_lines,
            node_of=node_of,
            nets={net.name: net for net in used},
            meters=meters,
            sources=sources,
            described=described,
            ac_sources=ac_sources,
        )

    # -- analyses --

    def _simulate(self, deck: _Deck, analysis: str, prefix: str, what: str):
        from cadgen.kicad.ngspice import NgspiceFailure, simulate

        try:
            return simulate(deck.lines, analysis, plot_prefix=prefix)
        except NgspiceFailure as failure:
            raise SimulationError(_explain(failure, deck, what), log=failure.log) from None

    def operating_point(self) -> "OperatingPoint":
        """The DC operating point: every net's voltage (a float, volts from ground), and currents."""
        deck = self._compile()
        plot = self._simulate(deck, "op", "op", "operating point")
        return OperatingPoint(self, deck, plot)

    def transient(self, stop: float, step: float | None = None, start: float = 0.0) -> "Run":
        """Time from 0 to ``stop`` seconds, recorded from ``start``.

        ``step`` is the longest time step, so the waveforms' resolution; by
        default a thousandth of the recorded span. The run starts from the
        operating point (each source's value at time 0).
        """
        stop = _positive(stop, what="transient stop")
        start = to_number(start, what="transient start")
        if start < 0 or start >= stop:
            raise DesignError(f"transient start must be 0 or more and before stop ({spice_number(stop)} s), got {start!r}")
        step = (stop - start) / 1000.0 if step is None else _positive(step, what="transient step")
        if step > stop - start:
            raise DesignError(f"transient step ({spice_number(step)} s) is longer than the run ({spice_number(stop - start)} s)")
        deck = self._compile()
        analysis = f"tran {spice_number(step)} {spice_number(stop)} {spice_number(start)} {spice_number(step)}"
        return Run(self, "transient", deck, self._simulate(deck, analysis, "tran", "transient"), analysis)

    def ac(self, start: float, stop: float, points_per_decade: int = 20) -> "Run":
        """Small-signal frequency response from ``start`` to ``stop`` hertz.

        Sources driven with ``ac=`` are the stimulus (an input of ``ac=1`` makes
        each net's result its transfer function); everything is linearised
        about the operating point.
        """
        start = _positive(start, what="ac start")
        stop = _positive(stop, what="ac stop")
        if stop <= start:
            raise DesignError(f"ac stop ({stop!r} Hz) must be above start ({start!r} Hz)")
        if isinstance(points_per_decade, bool) or not isinstance(points_per_decade, int) or points_per_decade < 1:
            raise DesignError(f"points_per_decade is a whole number 1 or more, got {points_per_decade!r}")
        deck = self._compile()
        if not deck.ac_sources:
            raise DesignError("ac() needs a stimulus: give the input source an AC magnitude, for example tb.source(vin, dc=0, ac=1)")
        analysis = f"ac dec {points_per_decade} {spice_number(start)} {spice_number(stop)}"
        return Run(self, "ac", deck, self._simulate(deck, analysis, "ac", "ac analysis"), analysis)

    def dc_sweep(self, source_net: Net | str | Source, start: float, stop: float, step: float) -> "Run":
        """The operating point as a source's DC value goes from ``start`` to ``stop``.

        ``source_net`` is a source this testbench made, or the net one drives.
        """
        source = self._sweep_source(source_net)
        start = to_number(start, what="dc_sweep start")
        stop = to_number(stop, what="dc_sweep stop")
        step = _positive(step, what="dc_sweep step")
        if start == stop:
            raise DesignError("dc_sweep start and stop are the same value")
        deck = self._compile()
        signed = step if stop > start else -step
        # ngspice folds the netlist's names to lower case, but not a command's.
        analysis = f"dc {deck.sources[id(source)].lower()} {spice_number(start)} {spice_number(stop)} {spice_number(signed)}"
        return Run(self, "dc_sweep", deck, self._simulate(deck, analysis, "dc", "dc sweep"), analysis, swept=source)

    def _sweep_source(self, value: Any) -> Source:
        if isinstance(value, Source):
            if value._bench is not self:
                raise DesignError("dc_sweep's source belongs to another testbench")
            return value
        net = self._net_of(value, what="dc_sweep's net")
        found = [source for source in self._sources if source.net is net]
        if len(found) != 1:
            raise DesignError(
                f"{'no source drives' if not found else f'{len(found)} sources drive'} net {net.name}; "
                "pass dc_sweep the source tb.source(...) returned"
            )
        return found[0]


def _explain(failure: Any, deck: _Deck, what: str) -> str:
    seen, hints = error_hints(failure.errors, deck.described)
    shown = seen[:12] + ([f"... and {len(seen) - 12} more"] if len(seen) > 12 else [])
    message = f"the {what} did not run: {failure.reason}"
    if shown:
        message += ". ngspice said:\n  " + "\n  ".join(shown)
    if hints:
        message += "\n" + "\n".join(f"- {hint}" for hint in hints)
    return message + "\n(tb.netlist() is the circuit simulated; this error's .log is everything ngspice printed)"


# --- results ----------------------------------------------------------------------------


def _measured(bench: Testbench, deck: _Deck, what: Any) -> tuple[str, float, str]:
    """The vector, sign and label of ``run.current(what)``."""
    if isinstance(what, (Source, Load)):
        if what._bench is not bench:
            raise DesignError(f"{what!r} belongs to another testbench")
        vector, sign = deck.meters[id(what)]
        return vector, sign, (f"I({what.net.name} source)" if isinstance(what, Source) else f"I({what.net.name} load)")
    if isinstance(what, Pin):
        if what.part._board is not bench:
            raise DesignError(f"{what!r} belongs to another board or testbench")
        found = deck.meters.get(("pin", what.key))
        if found is None:
            raise DesignError(f"{what!r} has no probe: call tb.probe({what.part.ref.lower()}[{what.number!r}]) before the analysis")
        unique = what.name and what.name != "~" and sum(pin.name == what.name for pin in what.part.pins()) == 1
        label = what.name if unique else what.number
        return found[0], found[1], f"I({what.part.ref}.{label})"
    if isinstance(what, Part):
        raise DesignError(f"current() takes a pin of {what.ref} (its direction): probe one with tb.probe({what.ref.lower()}[1])")
    raise DesignError(f"current() takes a source or load the testbench made, or a probed pin; got {what!r}")


class OperatingPoint(Mapping[str, float]):
    """Every net's DC voltage, in volts from ground: ``op["OUT"]``, ``dict(op)``.

    ``op.current(source | load | probed pin)`` is a current in amps (see the
    module's sign conventions). ``netlist`` is the circuit that was solved.
    """

    def __init__(self, bench: Testbench, deck: _Deck, plot: Any):
        self._bench = bench
        self._deck = deck
        self._voltages = {name: (0.0 if node == "0" else float(plot.vectors[node.lower()][0]))
                          for name, node in ((name, deck.node_of[id(net)]) for name, net in deck.nets.items())}
        self._vectors = plot.vectors
        self.netlist = deck.text
        self.log = "\n".join(plot.log)

    def _name(self, net: Any) -> str:
        name = net.name if isinstance(net, Net) else str(net)
        if name not in self._voltages:
            raise UnknownNetError(f"no net {name!r} in this testbench's results; its nets are {', '.join(self._voltages)}")
        return name

    def __getitem__(self, net: str | Net) -> float:
        return self._voltages[self._name(net)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._voltages)

    def __len__(self) -> int:
        return len(self._voltages)

    def __contains__(self, net: object) -> bool:
        name = net.name if isinstance(net, Net) else net
        return name in self._voltages

    def current(self, what: Source | Load | Pin) -> float:
        vector, sign, _label = _measured(self._bench, self._deck, what)
        return sign * float(self._vectors[vector][0])

    def __repr__(self) -> str:
        return "OperatingPoint(" + ", ".join(f"{name}={value:.6g} V" for name, value in self._voltages.items()) + ")"


_AXES = {"transient": ("time", "s"), "ac": ("frequency", "Hz"), "dc_sweep": ("sweep", "V")}


class Run:
    """An analysis's results over its axis: ``run["OUT"]`` a net's voltage, ``run.current(x)`` a current.

    Each is a :class:`Waveform`. ``x`` is the axis -- also ``time`` (seconds)
    for a transient, ``frequency`` (hertz) for an AC run, ``sweep`` (the swept
    source's volts or amps) for a DC sweep. ``netlist`` is the circuit simulated
    and ``analysis`` the ngspice command that ran it.
    """

    def __init__(self, bench: Testbench, kind: str, deck: _Deck, plot: Any, analysis: str, *, swept: Source | None = None):
        import numpy

        self._bench = bench
        self._deck = deck
        self.analysis = analysis
        self.kind = kind
        axis_name, axis_unit = _AXES[kind]
        if swept is not None and swept.kind == "current":
            axis_unit = "A"
        scale = {"transient": "time", "ac": "frequency"}.get(kind) or ("i-sweep" if axis_unit == "A" else "v-sweep")
        if scale not in plot.vectors:
            raise SimulationError(f"ngspice's {kind} results have no {scale} axis", log=plot.log)
        self.x = numpy.real(plot.vectors[scale]).astype(float)
        self._axis = (axis_name, axis_unit)
        self._vectors = plot.vectors
        self.netlist = deck.text
        self.log = "\n".join(plot.log)

    @property
    def nets(self) -> list[str]:
        """The nets this run has a voltage for, in the order they were made."""
        return list(self._deck.nets)

    def _axis_as(self, name: str):
        if self._axis[0] != name:
            raise DesignError(f"a {self.kind} run's axis is {self._axis[0]}, not {name}: use run.{self._axis[0]} or run.x")
        return self.x

    @property
    def time(self):
        return self._axis_as("time")

    @property
    def frequency(self):
        return self._axis_as("frequency")

    @property
    def sweep(self):
        return self._axis_as("sweep")

    def _waveform(self, values: Any, name: str, unit: str) -> "Waveform":
        return Waveform(self.x, values, name=name, unit=unit, axis=self._axis[0], axis_unit=self._axis[1])

    def __getitem__(self, net: str | Net) -> "Waveform":
        import numpy

        name = net.name if isinstance(net, Net) else str(net)
        found = self._deck.nets.get(name)
        if found is None:
            raise UnknownNetError(f"no net {name!r} in this run; its nets are {', '.join(self._deck.nets)}")
        node = self._deck.node_of[id(found)]
        values = numpy.zeros(len(self.x)) if node == "0" else self._vectors[node.lower()]
        return self._waveform(values, f"V({name})", "V")

    def __contains__(self, net: object) -> bool:
        name = net.name if isinstance(net, Net) else net
        return name in self._deck.nets

    def current(self, what: Source | Load | Pin) -> "Waveform":
        vector, sign, label = _measured(self._bench, self._deck, what)
        return self._waveform(sign * self._vectors[vector], label, "A")

    def plot(self, path: str | Path, *, nets: Sequence[str | Net] | None = None, currents: Sequence[Any] = (), title: str | None = None) -> Path:
        """Draw voltages (and ``currents``) against the axis into a PNG at ``path``; returns its path.

        ``nets`` defaults to every net but ground. An AC run is drawn as
        magnitude (dB) over phase (degrees) on a log frequency axis.
        """
        chosen = [name for name in self._deck.nets if not _is_ground(name)] if nets is None else [
            net.name if isinstance(net, Net) else str(net) for net in nets
        ]
        voltages = [self[name] for name in chosen]
        measured = [self.current(what) for what in currents]
        return plot_run(self, Path(path), voltages, measured, title=title or self._bench.title)

    def __repr__(self) -> str:
        return f"Run({self.kind}: {len(self.x)} points, nets {', '.join(self._deck.nets)})"
