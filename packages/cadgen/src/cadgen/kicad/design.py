"""The PCB authoring model: what an ``@pcb`` function builds and returns.

A :class:`Board` holds a circuit and its layout, named in KiCad's own words:

- **parts** come from KiCad's libraries, a symbol (``Device:R``) and a
  footprint (``Resistor_SMD:R_0603_1608Metric``), and get a reference
  (``R1``) and a value;
- **nets** join part pins: ``board.connect(vbus, j1[1], u1["VI"])``. A pin is
  named by its number or, when that is unambiguous, by its name;
- **placement** is its own step, ``board.place(part, at=(x, y))``, so a
  subcircuit written as a plain function adds parts to a board or to a
  simulation testbench alike;
- **copper** is tracks, arcs, vias and zones on KiCad's layers (``F.Cu``,
  ``B.Cu``, ``In1.Cu``...), and **keepouts** forbid copper in an area;
- **shapes** (the outline and its cutouts, a zone's area, a keepout) are
  build123d 2D geometry, the same contract ``@dxf`` drawings use.

Coordinates are millimetres with y UP, as build123d's are, and the board's
(0, 0) is wherever the outline puts it: the KiCad files carry the same origin
as their drill/place origin, so the board's STEP export lands exactly on the
enclosure it was drawn against. Rotation is degrees counter-clockwise seen from
the top; a part on the ``"bottom"`` side is mirrored as KiCad mirrors it.

Nothing here talks to KiCad. Library lookups happen when a part is created
(the files read are the build's inputs); everything KiCad itself decides --
filled zones, clearances, connectivity -- happens when the build writes the
board and runs ``kicad-cli`` over it.

Each part and hole remembers the script line that made it (``part.script``):
the documents carry it as a hidden ``Script`` field, so a part a person points
at in the viewer leads back to that line.
"""

from __future__ import annotations

import functools
import math
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

from cadgen.kicad.geometry import nm
from cadgen.kicad.library import Footprint, Libraries, LibraryError, Symbol
from cadgen.kicad.naming import natural

__all__ = [
    "Board",
    "Circuit",
    "DesignError",
    "Net",
    "NetClass",
    "Part",
    "Pin",
    "Rules",
]


#: The fields every KiCad symbol has; the rest are a library's or a part's own.
STANDARD_FIELDS = ("Reference", "Value", "Footprint", "Datasheet", "Description")
#: The hidden field a board's documents carry on each part: the script line that made it.
SCRIPT_FIELD = "Script"

_CADGEN = os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + os.sep


@functools.lru_cache(maxsize=256)
def _in_cadgen(filename: str) -> bool:
    return os.path.normcase(os.path.abspath(filename)).startswith(_CADGEN)


def _script_line() -> tuple[str, int] | None:
    """The first frame outside cadgen, as (absolute file, line): the script line that called it."""
    frame = sys._getframe(1)
    while frame is not None:
        filename = frame.f_code.co_filename
        if filename.startswith("<"):
            return filename, frame.f_lineno
        if not _in_cadgen(filename):
            return os.path.abspath(filename), frame.f_lineno
        frame = frame.f_back
    return None


def script_reference(script: tuple[str, int] | None, root: str | os.PathLike | None) -> str | None:
    """A script line as the ``Script`` field spells it, ``<path>:<line>``.

    The path is relative to ``root`` (the model script's folder), with ``/``
    between folders, so the same script writes the same documents wherever its
    project lives; a file outside that folder, or any file when no folder is
    known, is named by its file name alone.
    """
    if script is None:
        return None
    filename, line = script
    name = os.path.basename(filename) or filename
    if root is not None and not filename.startswith("<"):
        try:
            name = Path(filename).resolve().relative_to(Path(root).resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return f"{name}:{line}"


class DesignError(ValueError):
    """A board that cannot be what its script says. The message says how to fix it."""


# --- design rules --------------------------------------------------------------


@dataclass(frozen=True)
class Rules:
    """KiCad's board constraints (Board Setup > Constraints) and default net class.

    The field names are the ones KiCad writes in a ``.kicad_pro``. Lengths are
    millimetres. A fab's published capabilities go here; KiCad's own defaults
    are deliberately permissive, and a check against them passes boards no fab
    can make.
    """

    min_clearance: float
    min_track_width: float
    min_via_diameter: float
    min_via_annular_width: float
    min_through_hole_diameter: float
    min_hole_to_hole: float
    min_hole_clearance: float
    min_copper_edge_clearance: float
    min_silk_clearance: float
    min_text_height: float
    min_text_thickness: float
    # The Default net class: what a track, a via and a zone use unless their net says otherwise.
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float

    def replace(self, **changes: float) -> "Rules":
        unknown = sorted(set(changes) - set(self.__dataclass_fields__))
        if unknown:
            raise DesignError(
                f"Rules has no {', '.join(unknown)}; its fields are {', '.join(self.__dataclass_fields__)}"
            )
        return replace(self, **changes)


@dataclass(frozen=True)
class NetClass:
    name: str
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float


# --- the netlist ---------------------------------------------------------------


class Net:
    """A connection between pins. Named nets with one name are one net."""

    __slots__ = ("_board", "_name", "netclass", "power_flag", "current", "_index")

    def __init__(
        self,
        board: "Board",
        name: str | None,
        *,
        netclass: str | None,
        power_flag: bool,
        index: int,
        current: float | None = None,
    ):
        self._board = board
        self._name = name
        self.netclass = netclass
        self.power_flag = power_flag
        self.current = current
        self._index = index

    @property
    def name(self) -> str:
        """The net's name; an unnamed net is named after its first pin, as KiCad names one."""
        if self._name is not None:
            return self._name
        return self._board._anonymous_name(self)

    @property
    def named(self) -> bool:
        return self._name is not None

    @property
    def pins(self) -> list["Pin"]:
        return [pin for pin in self._board._pin_order if self._board._pin_nets.get(pin.key) is self]

    def __repr__(self) -> str:
        return f"Net({self.name!r})"


@dataclass(frozen=True)
class _Placement:
    x: float
    y: float
    rotation: float
    side: str


class Pin:
    """One pin of a part: what nets connect to, and where its pad is once placed."""

    __slots__ = ("part", "number", "name", "electrical_type")

    def __init__(self, part: "Part", number: str, name: str, electrical_type: str):
        self.part = part
        self.number = number
        self.name = name
        self.electrical_type = electrical_type

    @property
    def key(self) -> tuple[int, str]:
        return (self.part._index, self.number)

    @property
    def net(self) -> Net | None:
        return self.part._board._pin_nets.get(self.key)

    @property
    def stack(self) -> tuple["Pin", ...]:
        """This pin and every pin its symbol draws at the same point (a connector's repeated
        GND pins): one connection point in the schematic, so one net, always."""
        return tuple(self.part._pins[number] for number in self.part._stacks.get(self.number, (self.number,)))

    @property
    def pads(self) -> list[tuple[float, float]]:
        """Board coordinates of every pad numbered like this pin (a tab can repeat one)."""
        return [self.part._pad_position(pad) for pad in self.part.footprint.pads_numbered(self.number)]

    @property
    def position(self) -> tuple[float, float]:
        """Board coordinates of this pin's first pad; the part must be placed."""
        pads = self.pads
        if not pads:
            raise DesignError(
                f"{self.part.ref} pin {self.number} has no pad on {self.part.footprint.lib_id}"
            )
        return pads[0]

    def __repr__(self) -> str:
        label = f" ({self.name})" if self.name and self.name != self.number else ""
        return f"Pin({self.part.ref}.{self.number}{label})"


class Part:
    """A part from KiCad's libraries: its symbol, its footprint, its reference and value."""

    def __init__(
        self,
        board: "Board",
        *,
        index: int,
        symbol: Symbol,
        footprint: Footprint | None,
        ref: str,
        value: str,
        properties: dict[str, str],
        dnp: bool,
        script: tuple[str, int] | None = None,
    ):
        self._board = board
        self._index = index
        self.symbol = symbol
        self._footprint = footprint
        self.ref = ref
        self.value = value
        self.properties = dict(properties)
        self.dnp = dnp
        #: Where the script made this part: (absolute file, line), the first frame outside cadgen.
        self.script = script
        self._placement: _Placement | None = None
        seen: dict[str, Pin] = {}
        for library_pin in symbol.pins:
            if library_pin.number not in seen:
                seen[library_pin.number] = Pin(self, library_pin.number, library_pin.name, library_pin.electrical_type)
        self._pins = seen
        # KiCad joins pins drawn at one point of a unit; so does the board.
        points: dict[tuple[int, float, float], list[str]] = {}
        for library_pin in symbol.pins:
            if library_pin.body_style in (0, 1):
                numbers = points.setdefault((library_pin.unit, round(library_pin.x, 4), round(library_pin.y, 4)), [])
                if library_pin.number not in numbers:
                    numbers.append(library_pin.number)
        self._stacks = {number: tuple(numbers) for numbers in points.values() if len(numbers) > 1 for number in numbers}

    @property
    def footprint(self) -> Footprint:
        if self._footprint is None:
            raise DesignError(
                f"{self.ref} ({self.symbol.lib_id}) has no footprint: give it one with "
                f"footprint='Library:Name'"
            )
        return self._footprint

    @property
    def fields(self) -> dict[str, str]:
        """Every field the part carries beyond KiCad's five (reference, value, footprint, datasheet, description).

        The library symbol's own come first, as KiCad copies them when placing
        it (a diode's ``Sim.Device``); ``properties=`` are the part's and win.
        Both the schematic symbol and the footprint carry them all: KiCad's
        parity check compares the two.
        """
        carried = {
            key: value
            for key, value in self.symbol.properties.items()
            if key not in STANDARD_FIELDS and not key.startswith("ki_")
        }
        return {**carried, **self.properties}

    def document_fields(self, script_root: str | os.PathLike | None = None) -> dict[str, str]:
        """:attr:`fields`, and the hidden ``Script`` field: what the part's symbol and its
        footprint both carry in the written documents."""
        script = script_reference(self.script, script_root)
        fields = dict(self.fields)
        if script is not None:
            fields[SCRIPT_FIELD] = script
        return fields

    @property
    def placed(self) -> bool:
        return self._placement is not None

    @property
    def at(self) -> tuple[float, float]:
        placement = self._require_placement()
        return placement.x, placement.y

    @property
    def rotation(self) -> float:
        return self._require_placement().rotation

    @property
    def side(self) -> str:
        return self._require_placement().side

    def _require_placement(self) -> _Placement:
        if self._placement is None:
            raise DesignError(f"{self.ref} is not placed: call board.place({self.ref.lower()}, at=(x, y))")
        return self._placement

    def pins(self) -> list[Pin]:
        """Every pin, in the symbol's order."""
        return list(self._pins.values())

    def unconnected(self) -> list[Pin]:
        """Pins on no net and not marked no-connect: what ``board.no_connect`` is for."""
        board = self._board
        return [pin for pin in self._pins.values() if pin.key not in board._pin_nets and pin.key not in board._no_connects]

    def __getitem__(self, key: int | str) -> Pin:
        text = str(key)
        if text in self._pins:
            return self._pins[text]
        named = [pin for pin in self._pins.values() if pin.name == text]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            numbers = ", ".join(pin.number for pin in named)
            raise DesignError(
                f"{self.ref} has {len(named)} pins named {text!r} (numbers {numbers}); name one by its number, "
                f"for example {self.ref.lower()}[{named[0].number!r}]"
            )
        listing = ", ".join(
            f"{pin.number}" + (f"={pin.name}" if pin.name and pin.name != pin.number else "")
            for pin in self._pins.values()
        )
        raise DesignError(f"{self.ref} ({self.symbol.lib_id}) has no pin {text!r}; its pins are {listing}")

    def _pad_position(self, pad) -> tuple[float, float]:
        return self._local_to_board(pad.x, pad.y)

    def _local_to_board(self, x: float, y: float) -> tuple[float, float]:
        """A point of the footprint as its library draws it (y down), where it lands on the board (y up)."""
        placement = self._require_placement()
        # Library footprints are y-down (KiCad's footprint frame); the board's frame is y-up,
        # and a bottom part is flipped top-to-bottom in its own frame first, as KiCad flips it.
        local_x, local_y = x, (y if placement.side == "bottom" else -y)
        angle = math.radians(placement.rotation)
        cos, sin = math.cos(angle), math.sin(angle)
        return (
            nm(placement.x + local_x * cos - local_y * sin),
            nm(placement.y + local_x * sin + local_y * cos),
        )

    def __repr__(self) -> str:
        return f"Part({self.ref}: {self.symbol.lib_id}, {self.value!r})"


# --- copper and graphics ---------------------------------------------------------


@dataclass(frozen=True)
class Track:
    net: Net
    start: tuple[float, float]
    end: tuple[float, float]
    width: float | None
    layer: str
    mid: tuple[float, float] | None = None  # an arc passes through it


@dataclass(frozen=True)
class Via:
    net: Net
    at: tuple[float, float]
    diameter: float | None
    drill: float | None
    layers: tuple[str, str]


@dataclass(frozen=True)
class Zone:
    net: Net | None
    layers: tuple[str, ...]
    shape: Any
    clearance: float | None
    min_thickness: float | None
    priority: int
    thermal_gap: float | None
    thermal_width: float | None
    pads: str
    keepout: dict[str, bool] | None = None


@dataclass(frozen=True)
class Hole:
    at: tuple[float, float]
    diameter: float
    script: tuple[str, int] | None = None  # the line that made it, as Part.script


@dataclass(frozen=True)
class Text:
    text: str
    at: tuple[float, float]
    layer: str
    size: float
    thickness: float | None
    rotation: float


@dataclass(frozen=True)
class Autoroute:
    """What ``board.autoroute(...)`` asked for: the build routes the board with Freerouting."""

    skip: tuple[Any, ...]  # nets (or their names) the router leaves alone
    passes: int
    timeout: float
    layers: tuple[str, ...] | None = None  # the copper layers it may run tracks on; None is every one


def _point(value: Any, *, what: str) -> tuple[float, float]:
    if isinstance(value, Pin):
        return value.position
    try:
        x, y = value
        return nm(float(x)), nm(float(y))
    except (TypeError, ValueError):
        raise DesignError(f"{what} must be an (x, y) pair in millimetres or a pin, got {value!r}") from None


_FLIPPED = {"F.Cu": "B.Cu", "B.Cu": "F.Cu"}


def _pad_copper(pin: Pin) -> set[str] | None:
    """The copper layers a pin's pads are on, as placed; None when they reach every layer."""
    found: set[str] = set()
    bottom = pin.part.side == "bottom"
    for pad in pin.part.footprint.pads_numbered(pin.number):
        for layer in pad.layers:
            if layer in ("*.Cu", "F&B.Cu"):
                return None
            if layer.endswith(".Cu"):
                found.add(_FLIPPED.get(layer, layer) if bottom else layer)
    return found or None


def _positive(value: Any, *, what: str, allow_none: bool = True) -> float | None:
    if value is None and allow_none:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DesignError(f"{what} must be a number of millimetres, got {value!r}") from None
    if not math.isfinite(number) or number <= 0:
        raise DesignError(f"{what} must be greater than 0, got {value!r}")
    return nm(number)


_SIDES = ("top", "bottom")
_PAD_CONNECTIONS = ("thermal", "solid", "none")


# --- the circuit ------------------------------------------------------------------


class Circuit:
    """The netlist: parts from KiCad's libraries and the nets joining their pins.

    A :class:`Board` is a circuit with a layout; a simulation ``Testbench`` is a
    circuit with sources and analyses. A subcircuit written as a plain function
    of a circuit (``def ldo(c, vin, vout, gnd): ...``) builds into either.
    """

    #: A board needs a footprint for every part; a testbench does not.
    _requires_footprint = False

    def __init__(self, *, libraries: Iterable[str | Path] = ()):
        self._library_folders = tuple(Path(path) for path in libraries)
        self._libraries: Libraries | None = None
        self._parts: list[Part] = []
        self._refs: dict[str, Part] = {}
        self._nets: list[Net] = []
        self._named_nets: dict[str, Net] = {}
        self._pin_nets: dict[tuple[int, str], Net] = {}
        self._pin_order: list[Pin] = []
        self._no_connects: dict[tuple[int, str], Pin] = {}

    # -- libraries --

    @property
    def libraries(self) -> Libraries:
        if self._libraries is None:
            self._libraries = Libraries.for_project(self._library_folders)
        return self._libraries

    # -- the netlist --

    def net(
        self,
        name: str | None = None,
        *,
        netclass: str | None = None,
        power_flag: bool = False,
        current: float | None = None,
    ) -> Net:
        """A net. One name is one net; ``net()`` with no name makes a net named after its first pin.

        ``power_flag=True`` marks a net that is powered from off the board (a
        connector, a battery): KiCad's ERC needs a PWR_FLAG on such a net, or it
        reports its power inputs as undriven.

        ``current`` is what the net carries, in amperes: the review checks its tracks are wide enough.
        """
        if current is not None:
            try:
                current = float(current)
            except (TypeError, ValueError):
                raise DesignError(f"a net's current is in amperes and positive, not {current!r}") from None
            if not math.isfinite(current) or current <= 0:
                raise DesignError(f"a net's current is in amperes and positive, not {current:g}")
        if name is not None:
            name = str(name).strip()
            if not name:
                raise DesignError("a net name cannot be empty; call board.net() for an unnamed net")
            if name in self._named_nets:
                existing = self._named_nets[name]
                if netclass is not None and existing.netclass not in (None, netclass):
                    raise DesignError(f"net {name!r} is already in net class {existing.netclass!r}")
                if netclass is not None:
                    existing.netclass = netclass
                if current is not None and existing.current not in (None, current):
                    raise DesignError(f"net {name!r} already carries {existing.current:g} A")
                if current is not None:
                    existing.current = current
                if power_flag and not existing.power_flag:
                    self.libraries.symbol("power:PWR_FLAG")
                    existing.power_flag = True
                return existing
        if power_flag:
            # The schematic draws KiCad's PWR_FLAG for this net. Look it up now, while
            # the build's trace is watching, so its library is one of the inputs.
            self.libraries.symbol("power:PWR_FLAG")
        net = Net(
            self, name, netclass=netclass, power_flag=bool(power_flag), index=len(self._nets), current=current
        )
        self._nets.append(net)
        if name is not None:
            self._named_nets[name] = net
        return net

    @property
    def nets(self) -> list[Net]:
        """Every net that has at least one pin, in the order they were made."""
        used = set(id(net) for net in self._pin_nets.values())
        return [net for net in self._nets if id(net) in used]

    @property
    def net_currents(self) -> dict[str, float]:
        """Each used net the script gave a current, by name: what the review's track check reads."""
        return {net.name: net.current for net in self.nets if net.current is not None}

    def part(
        self,
        symbol: str,
        *,
        footprint: str | None = None,
        value: str | None = None,
        ref: str | None = None,
        properties: dict[str, str] | None = None,
        dnp: bool = False,
    ) -> Part:
        """A part: KiCad symbol ``Library:Name``, its footprint, reference and value.

        ``footprint`` defaults to the symbol's own Footprint field when it has
        one. ``ref`` defaults to the symbol's prefix and the next free number
        (``R1``, ``R2``...). ``properties`` adds fields such as ``MPN`` or
        ``LCSC`` (the BOM carries them). ``dnp=True`` keeps the footprint on the
        board but out of assembly.
        """
        libraries = self.libraries
        try:
            library_symbol = libraries.symbol(symbol)
        except LibraryError as error:
            raise DesignError(str(error)) from None
        if library_symbol.power is not None:
            raise DesignError(
                f"{symbol} is a power symbol, which is a schematic net label rather than a part; "
                "make the net with board.net(...) instead"
            )
        footprint_id = footprint if footprint is not None else library_symbol.default_footprint
        if footprint_id is None and self._requires_footprint:
            raise DesignError(
                f"{symbol} has no default footprint: give the part one, for example "
                f"footprint='Resistor_SMD:R_0603_1608Metric'"
            )
        library_footprint = None
        if footprint_id is not None:
            try:
                library_footprint = libraries.footprint(footprint_id)
            except LibraryError as error:
                raise DesignError(str(error)) from None
        reference = self._claim_ref(ref, library_symbol.reference_prefix)
        extra = {}
        for key, item in (properties or {}).items():
            key = str(key)
            if key in {"Reference", "Value", "Footprint"}:
                raise DesignError(f"properties= cannot set {key}; pass it as {key.lower()}=")
            if key == SCRIPT_FIELD:
                raise DesignError(f"properties= cannot set {SCRIPT_FIELD}: cadgen writes there the script line that made the part")
            extra[key] = str(item)
        part = Part(
            self,
            index=len(self._parts),
            symbol=library_symbol,
            footprint=library_footprint,
            ref=reference,
            value=str(value) if value is not None else library_symbol.properties.get("Value", library_symbol.name),
            properties=extra,
            dnp=bool(dnp),
            script=_script_line(),
        )
        self._check_pads(part)
        self._parts.append(part)
        self._refs[reference] = part
        return part

    def _check_pads(self, part: Part) -> None:
        if part._footprint is None:
            return
        pads = set(part.footprint.pad_numbers)
        missing = [pin.number for pin in part.pins() if pin.number not in pads and pin.electrical_type != "no_connect"]
        if missing:
            raise DesignError(
                f"{part.ref}: symbol {part.symbol.lib_id} has pin(s) {', '.join(missing)} that footprint "
                f"{part.footprint.lib_id} has no pad for (its pads are {', '.join(sorted(pads, key=natural)) or 'none'}); "
                "pick the footprint this symbol's pin numbering was drawn for"
            )

    def _claim_ref(self, ref: str | None, prefix: str) -> str:
        if ref is not None:
            reference = str(ref).strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_+-]*", reference):
                raise DesignError(f"ref {ref!r} is not a reference designator such as R1 or U3")
            if reference in self._refs:
                raise DesignError(f"ref {reference} is used twice")
            return reference
        number = 1
        while f"{prefix}{number}" in self._refs:
            number += 1
        return f"{prefix}{number}"

    @property
    def parts(self) -> list[Part]:
        return list(self._parts)

    def _owned_pin(self, pin: Any, *, what: str) -> Pin:
        if not isinstance(pin, Pin):
            raise DesignError(f"{what} takes pins such as r1[1] or u1['VIN'], got {pin!r}")
        if pin.part._board is not self:
            raise DesignError(f"{pin!r} belongs to another board or testbench")
        return pin

    def connect(self, net: Net, *pins: Pin) -> None:
        """Put ``pins`` on ``net``. A pin is on one net; joining it to a second is an error.

        Pins a symbol draws at one point (``pin.stack``: a connector's repeated GND
        pins) are one connection in the schematic, so connecting one connects them all.
        """
        if not isinstance(net, Net) or net._board is not self:
            raise DesignError("connect's first argument is a net from this board's board.net(...)")
        if not pins:
            raise DesignError("connect needs at least one pin")
        for pin in pins:
            pin = self._owned_pin(pin, what="connect")
            existing = self._pin_nets.get(pin.key)
            if existing is not None and existing is not net:
                raise DesignError(
                    f"{pin!r} is already on net {existing.name}; one pin joins one net "
                    f"(to join the two nets, connect both through the same net object){_stack_note(pin)}"
                )
            if pin.key in self._no_connects:
                raise DesignError(f"{pin!r} is marked no-connect{_stack_note(pin)}")
            for member in pin.stack:
                if member.key not in self._pin_nets:
                    self._pin_nets[member.key] = net
                    self._pin_order.append(member)

    def no_connect(self, *pins: Pin) -> None:
        """Mark pins deliberately unconnected (KiCad's no-connect flag), each with its stack."""
        for pin in pins:
            pin = self._owned_pin(pin, what="no_connect")
            if pin.key in self._pin_nets:
                raise DesignError(
                    f"{pin!r} is on net {self._pin_nets[pin.key].name}, so it cannot be no-connect{_stack_note(pin)}"
                )
            for member in pin.stack:
                self._no_connects[member.key] = member

    def _anonymous_name(self, net: Net) -> str:
        pins = net.pins
        if not pins:
            return f"Net-{net._index}"
        first = min(pins, key=lambda pin: (natural(pin.part.ref), natural(pin.number)))
        label = first.name if first.name and first.name not in {"~", ""} else f"Pad{first.number}"
        return f"Net-({first.part.ref}-{label})"



# --- the board -------------------------------------------------------------------


class Board(Circuit):
    """A printed circuit board: a circuit, its outline, its layout and its copper."""

    _requires_footprint = True
    #: What ``board.autoroute(...)`` asked for; None until it is called.
    autoroute_request: Autoroute | None = None

    def __init__(
        self,
        *,
        outline: Any,
        layers: int = 2,
        thickness: float = 1.6,
        fab: Any = None,
        rules: Rules | None = None,
        libraries: Iterable[str | Path] = (),
        title: str | None = None,
    ):
        from cadgen.kicad.fabs import FABS, JLCPCB, Fab

        if outline is None:
            raise DesignError("a Board needs outline=: a build123d face or sketch, in millimetres")
        if not isinstance(layers, int) or isinstance(layers, bool) or layers < 2 or layers % 2 or layers > 32:
            raise DesignError(f"layers= is the copper layer count, an even number from 2 to 32; got {layers!r}")
        fab = JLCPCB if fab is None else fab
        if not isinstance(fab, Fab):
            presets = ", ".join(f"pcb.{name}" for name in ("JLCPCB", "PCBWAY", "OSHPARK", "AISLER", "EUROCIRCUITS", "SEEED_FUSION", "NEXTPCB"))
            raise DesignError(f"fab= takes a pcb.Fab: one of {presets} (the fabs: {', '.join(FABS)}); got {fab!r}")
        if rules is not None and not isinstance(rules, Rules):
            raise DesignError("rules= takes a pcb.Rules, such as pcb.PCBWAY.rules.replace(min_track_width=0.15)")
        super().__init__(libraries=libraries)
        self.outline = outline
        self.layer_count = layers
        self.thickness = _positive(thickness, what="thickness", allow_none=False)
        #: Where the board is made: its limits are the board's rules unless rules= says otherwise.
        self.fab = fab
        self.rules = rules if rules is not None else fab.rules_for(layers)
        self.title = title
        self._netclasses: dict[str, NetClass] = {}
        self.tracks: list[Track] = []
        self.vias: list[Via] = []
        self.zones: list[Zone] = []
        self.holes: list[Hole] = []
        self.texts: list[Text] = []
        self.raw_items: list[str] = []
        self.design_rules: list[list] = []

    # -- layers --

    @property
    def copper_layers(self) -> tuple[str, ...]:
        inner = tuple(f"In{index}.Cu" for index in range(1, self.layer_count - 1))
        return ("F.Cu", *inner, "B.Cu")

    def _copper(self, layer: Any, *, what: str) -> str:
        text = str(layer)
        if text not in self.copper_layers:
            raise DesignError(
                f"{what} {layer!r} is not a copper layer of this {self.layer_count}-layer board; "
                f"use one of {', '.join(self.copper_layers)}"
            )
        return text

    def _check_end(self, net: Net, point: Any, layer: str, *, what: str) -> None:
        """A pin copper ends on must be on the copper's net and have a pad on its layer.

        KiCad would report either as a short or a dangling end; this says which
        pin and what to do while the call that drew it is still in hand.
        """
        if not isinstance(point, Pin):
            return
        pin = self._owned_pin(point, what=what)
        if pin.net is not net:
            if pin.net is not None:
                state = f"on net {pin.net.name}, so the {what} would short the two"
            elif pin.key in self._no_connects:
                state = "marked no-connect"
            else:
                state = f"on no net yet: connect it to {net.name} (board.connect) before routing to it"
            raise DesignError(f"a {net.name} {what} ends on {pin.part.ref} pin {pin.number}, which is {state}")
        layers = _pad_copper(pin)
        if layers is not None and layer not in layers:
            raise DesignError(
                f"{pin.part.ref} pin {pin.number} has copper on {' and '.join(sorted(layers))} only "
                f"({pin.part.ref} is on the {pin.part.side}), so {'an' if what[0] in 'aeiou' else 'a'} {what} on {layer} "
                "cannot reach it: draw it on "
                f"{sorted(layers)[0]}, or change layers through a via beside the pad"
            )

    # -- placement --

    def place(self, part: Part, *, at: Any, rotation: float = 0.0, side: str = "top") -> None:
        """Put ``part`` on the board: ``at`` (x, y) mm, ``rotation`` degrees CCW from the top, ``side``."""
        if not isinstance(part, Part) or part._board is not self:
            raise DesignError("place takes a part made by this board's board.part(...)")
        if side not in _SIDES:
            raise DesignError(f"side= is 'top' or 'bottom', got {side!r}")
        x, y = _point(at, what="at")
        try:
            angle = float(rotation)
        except (TypeError, ValueError):
            raise DesignError(f"rotation= is degrees, got {rotation!r}") from None
        angle = round(angle % 360.0, 6)
        part._placement = _Placement(x=x, y=y, rotation=0.0 if angle == 360.0 else angle, side=side)

    # -- copper --

    def track(self, net: Net, points: Sequence[Any], *, width: float | None = None, layer: str = "F.Cu") -> None:
        """Straight copper from point to point. A point may be a pin: the track ends on its pad."""
        if not isinstance(net, Net) or net._board is not self:
            raise DesignError("track's first argument is a net from this board")
        if len(points) < 2:
            raise DesignError("a track needs at least two points")
        layer = self._copper(layer, what="track layer")
        width = _positive(width, what="track width")
        for point in points:
            self._check_end(net, point, layer, what="track")
        resolved = [_point(point, what="a track point") for point in points]
        for start, end in zip(resolved, resolved[1:]):
            if start == end:
                raise DesignError(f"a track segment starts and ends at {start}")
            self.tracks.append(Track(net=net, start=start, end=end, width=width, layer=layer))

    def arc(
        self, net: Net, *, start: Any, mid: Any, end: Any, width: float | None = None, layer: str = "F.Cu"
    ) -> None:
        """A circular copper arc from ``start`` through ``mid`` to ``end``."""
        if not isinstance(net, Net) or net._board is not self:
            raise DesignError("arc's first argument is a net from this board")
        layer = self._copper(layer, what="arc layer")
        for point in (start, end):
            self._check_end(net, point, layer, what="arc")
        a, b, c = (_point(p, what="an arc point") for p in (start, mid, end))
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) < 1e-9:
            raise DesignError("an arc's start, mid and end lie on one line; use track() for a straight run")
        self.tracks.append(
            Track(net=net, start=a, end=c, mid=b, width=_positive(width, what="arc width"), layer=layer)
        )

    def via(
        self,
        net: Net,
        *,
        at: Any,
        diameter: float | None = None,
        drill: float | None = None,
        layers: tuple[str, str] = ("F.Cu", "B.Cu"),
    ) -> None:
        """A plated through-hole joining copper layers (all of them by default)."""
        if not isinstance(net, Net) or net._board is not self:
            raise DesignError("via's first argument is a net from this board")
        if len(layers) != 2:
            raise DesignError("a via joins two layers, layers=(top, bottom)")
        pair = (self._copper(layers[0], what="via layer"), self._copper(layers[1], what="via layer"))
        if pair != ("F.Cu", "B.Cu"):
            raise DesignError(
                "only through vias (F.Cu to B.Cu) are supported; blind and buried vias go through board.raw(...)"
            )
        self.vias.append(
            Via(
                net=net,
                at=_point(at, what="via at"),
                diameter=_positive(diameter, what="via diameter"),
                drill=_positive(drill, what="via drill"),
                layers=pair,
            )
        )

    def zone(
        self,
        net: Net,
        *,
        layers: Sequence[str] = ("F.Cu",),
        shape: Any = None,
        clearance: float | None = None,
        min_thickness: float | None = None,
        priority: int = 0,
        thermal_gap: float | None = None,
        thermal_width: float | None = None,
        pads: str = "thermal",
    ) -> None:
        """A copper pour of ``net`` (a ground plane): the whole board, or ``shape``.

        KiCad fills it when the board is written, keeping ``clearance`` from
        other nets. ``pads`` is how the pour meets its own net's pads:
        ``"thermal"`` (spokes, solderable), ``"solid"`` or ``"none"``. A higher
        ``priority`` fills first where pours overlap.
        """
        if not isinstance(net, Net) or net._board is not self:
            raise DesignError("zone's first argument is a net from this board")
        if pads not in _PAD_CONNECTIONS:
            raise DesignError(f"pads= is one of {', '.join(_PAD_CONNECTIONS)}, got {pads!r}")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise DesignError(f"priority= is a whole number 0 or more, got {priority!r}")
        if isinstance(layers, str):
            layers = (layers,)
        self.zones.append(
            Zone(
                net=net,
                layers=tuple(self._copper(layer, what="zone layer") for layer in layers),
                shape=shape,
                clearance=_positive(clearance, what="zone clearance"),
                min_thickness=_positive(min_thickness, what="zone min_thickness"),
                priority=priority,
                thermal_gap=_positive(thermal_gap, what="zone thermal_gap"),
                thermal_width=_positive(thermal_width, what="zone thermal_width"),
                pads=pads,
            )
        )

    def keepout(
        self,
        *,
        shape: Any,
        layers: Sequence[str] | None = None,
        tracks: bool = True,
        vias: bool = True,
        pads: bool = False,
        pours: bool = True,
        footprints: bool = False,
    ) -> None:
        """An area copper may not enter: each flag forbids one kind of item there."""
        if shape is None:
            raise DesignError("keepout needs shape=: a build123d face or sketch")
        if isinstance(layers, str):
            layers = (layers,)
        chosen = tuple(self._copper(layer, what="keepout layer") for layer in (layers or self.copper_layers))
        self.zones.append(
            Zone(
                net=None,
                layers=chosen,
                shape=shape,
                clearance=None,
                min_thickness=None,
                priority=0,
                thermal_gap=None,
                thermal_width=None,
                pads="none",
                keepout={
                    "tracks": bool(tracks),
                    "vias": bool(vias),
                    "pads": bool(pads),
                    "copperpour": bool(pours),
                    "footprints": bool(footprints),
                },
            )
        )

    def netclass(
        self,
        name: str,
        *,
        track_width: float,
        clearance: float,
        via_diameter: float | None = None,
        via_drill: float | None = None,
    ) -> None:
        """A net class: the widths and clearance nets in it are routed with."""
        name = str(name).strip()
        if not name or name == "Default":
            raise DesignError("a net class needs a name other than Default (Default is rules=)")
        self._netclasses[name] = NetClass(
            name=name,
            track_width=_positive(track_width, what="netclass track_width", allow_none=False),
            clearance=_positive(clearance, what="netclass clearance", allow_none=False),
            via_diameter=_positive(via_diameter, what="netclass via_diameter") or self.rules.via_diameter,
            via_drill=_positive(via_drill, what="netclass via_drill") or self.rules.via_drill,
        )

    @property
    def netclasses(self) -> list[NetClass]:
        return list(self._netclasses.values())

    def netclass_of(self, net: Net) -> NetClass:
        if net.netclass is None:
            return NetClass("Default", self.rules.track_width, self.rules.clearance, self.rules.via_diameter, self.rules.via_drill)
        found = self._netclasses.get(net.netclass)
        if found is None:
            raise DesignError(f"net {net.name} is in net class {net.netclass!r}, which board.netclass(...) never defined")
        return found

    # -- routing --

    def autoroute(
        self,
        *,
        skip: Any = (),
        layers: Sequence[str] | None = None,
        passes: int = 100,
        timeout: float = 600.0,
    ) -> None:
        """Route every connection the script did not draw, with Freerouting, when the board is built.

        Place the parts first, and draw what must run one way (a power path, a
        pour): the router keeps every track and via the script drew, routes
        around them and continues from them. Each net is routed in its net
        class's width, clearance and via. ``skip`` is nets (or their names) the
        router leaves alone, such as a ground a pour carries. ``layers`` is the
        copper layers it may run tracks on (every one by default; vias still
        pass through all), so an inner plane stays whole. ``passes`` caps
        Freerouting's routing passes; the same board and passes always route
        the same way. ``timeout`` (seconds) stops a run that takes longer, and
        fails the build. A connection the router cannot make stays unrouted and
        the board is a draft that says so.

        The build runs Freerouting, a separate program: install it (and Java,
        for its jar) as cadgen.kicad.route says.
        """
        if self.autoroute_request is not None:
            raise DesignError("board.autoroute(...) was already called; call it once, with every setting")
        routing_layers = None
        if layers is not None:
            names = (layers,) if isinstance(layers, str) else tuple(layers)
            chosen = {self._copper(name, what="autoroute layer") for name in names}
            if not chosen:
                raise DesignError(f"layers= names the copper layers to route on, at least one of {', '.join(self.copper_layers)}")
            routing_layers = tuple(name for name in self.copper_layers if name in chosen)
        items = (skip,) if isinstance(skip, (Net, str)) else skip
        try:
            items = tuple(items)
        except TypeError:
            raise DesignError(f"skip= takes nets or net names, like skip=[gnd]; got {skip!r}") from None
        for item in items:
            if isinstance(item, Net):
                if item._board is not self:
                    raise DesignError(f"skip= names {item!r}, a net of another board or testbench")
            elif not isinstance(item, str) or not item.strip():
                raise DesignError(f"skip= takes nets or net names, like skip=[gnd]; got {item!r}")
        if not isinstance(passes, int) or isinstance(passes, bool) or passes < 1:
            raise DesignError(f"passes= is how many routing passes Freerouting may make, a whole number from 1; got {passes!r}")
        try:
            seconds = float(timeout)
        except (TypeError, ValueError):
            raise DesignError(f"timeout= is seconds, got {timeout!r}") from None
        if not math.isfinite(seconds) or seconds <= 0:
            raise DesignError(f"timeout= is seconds, greater than 0; got {timeout!r}")
        self.autoroute_request = Autoroute(skip=items, passes=passes, timeout=seconds, layers=routing_layers)

    # -- mechanical and graphics --

    def hole(self, *, at: Any, diameter: float) -> None:
        """An unplated hole (a mounting hole with no copper)."""
        self.holes.append(
            Hole(
                at=_point(at, what="hole at"),
                diameter=_positive(diameter, what="hole diameter", allow_none=False),
                script=_script_line(),
            )
        )

    def text(
        self,
        text: str,
        *,
        at: Any,
        layer: str = "F.SilkS",
        size: float = 1.0,
        thickness: float | None = None,
        rotation: float = 0.0,
    ) -> None:
        """Board text: silkscreen by default, or any layer KiCad has (``F.Cu`` for copper text)."""
        if not str(text):
            raise DesignError("text cannot be empty")
        self.texts.append(
            Text(
                text=str(text),
                at=_point(at, what="text at"),
                layer=str(layer),
                size=_positive(size, what="text size", allow_none=False),
                thickness=_positive(thickness, what="text thickness"),
                rotation=float(rotation) % 360.0,
            )
        )

    def raw(self, item: str) -> None:
        """Any board item KiCad's file format has, written as KiCad writes it.

        For what the typed methods do not cover: dimensions, teardrop settings,
        blind vias, images. Coordinates in a raw item are KiCad's own (y down,
        page origin), and KiCad checks the item when the board is written.
        """
        from cadgen.kicad import sexpr

        text = str(item).strip()
        try:
            sexpr.parse(text)
        except sexpr.SexprError as error:
            raise DesignError(f"board.raw(...) takes one KiCad S-expression: {error}") from None
        self.raw_items.append(text)

    def rule(self, text: str) -> None:
        """A custom design rule, in KiCad's own rule language (Board Setup > Custom Rules).

        For a constraint the board-wide rules cannot scope: a connector whose own
        land pattern puts its pads nearer its locating holes than
        ``min_hole_clearance`` allows, more clearance on a high-voltage net,
        tighter rules under one fine-pitch part. The rules are the project's
        ``.kicad_dru``, so KiCad applies them in every check, its own editor's
        included. A rule KiCad cannot read fails the build: KiCad itself would
        drop the whole file without a word.
        """
        from cadgen.kicad import sexpr

        example = """(rule "J1 land pattern" (constraint hole_clearance (min 0.15mm)) (condition "A.memberOfFootprint('J1')"))"""
        source = str(text).strip()
        try:
            tree = sexpr.parse(source)
        except sexpr.SexprError as error:
            raise DesignError(f"board.rule(...) takes one KiCad rule, like {example}: {error}") from None
        if sexpr.head(tree) != "rule" or len(tree) < 3 or isinstance(tree[1], list):
            raise DesignError(f"board.rule(...) takes one (rule NAME ...) of KiCad's rule language, like {example}")
        if not any(sexpr.head(child) == "constraint" for child in tree[2:] if isinstance(child, list)):
            raise DesignError(f"rule {tree[1]!r} has no (constraint ...); like {example}")
        if any(str(existing[1]) == str(tree[1]) for existing in self.design_rules):
            raise DesignError(f"the board already has a rule named {str(tree[1])!r}; give each rule its own name")
        self.design_rules.append(tree)

    # -- what a build checks before KiCad does --

    def problems(self) -> list[str]:
        """What stops this board being written, each a sentence that says what to do."""
        found: list[str] = []
        for part in self._parts:
            if not part.placed:
                found.append(f"{part.ref} is not placed: call board.place({part.ref.lower()}, at=(x, y))")
        for net in self._nets:
            if net.netclass is not None and net.netclass not in self._netclasses and any(
                self._pin_nets.get(pin.key) is net for pin in self._pin_order
            ):
                found.append(f"net {net.name} is in net class {net.netclass!r}, which board.netclass(...) never defined")
        names: dict[str, Net] = {}
        for net in self.nets:
            other = names.get(net.name)
            if other is not None and other is not net:
                found.append(f"two nets are both called {net.name}: name one of them")
            names[net.name] = net
        return found


def _stack_note(pin: Pin) -> str:
    """Why a pin the script never named is on a net: it is stacked with one that is."""
    stack = pin.stack
    if len(stack) == 1:
        return ""
    others = ", ".join(repr(member) for member in stack if member is not pin)
    return (
        f"; {pin.part.symbol.lib_id} draws it at one point with {others}, which the schematic joins: "
        "stacked pins are one connection (pin.stack)"
    )


def kicad_net_name(name: str) -> str:
    """A net's name as KiCad stores and compares it.

    ``/`` separates sheets in KiCad's net names, so KiCad escapes one inside a
    name (a label ``TX/RX`` is the net ``TX{slash}RX``) and drops line breaks;
    a board's pads must carry the same form or the parity check reports them.
    """
    return str(name).replace("/", "{slash}").replace("\n", "").replace("\r", "")


def unit_letter(unit: int) -> str:
    """KiCad's letter for a symbol unit: 1 is A, 26 is Z, 27 is AA."""
    letters = ""
    unit = max(int(unit), 1)
    while unit > 0:
        unit, remainder = divmod(unit - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters
