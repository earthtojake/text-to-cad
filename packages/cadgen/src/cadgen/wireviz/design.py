"""The harness authoring model: what a ``@harness`` function builds and returns.

A :class:`Harness` is a WireViz document written in Python, in WireViz's own
words:

- **connectors** have pins, pin labels, a ``type`` (``"Molex Micro-Fit 3.0"``),
  a ``subtype`` (``"female"``) and part numbers. A connector can come from a
  board: ``h.connector(board, "J3", type=...)`` takes the pins of the board's
  part ``J3`` and labels each with the net it carries on that board. The board
  has the header; the harness connector is the housing that mates with it, so
  its ``type`` is always the author's to name;
- **cables** have wires: a count, colours (``"RD"``, ``"BK"``, ``"WHGN"``...),
  a gauge (``"22 AWG"``, or a cross-section in mm²), a length in millimetres,
  a shield; ``category="bundle"`` makes them loose wires rather than one
  jacketed cable, so the bill of materials lists each wire;
- **connections** join connector pins through wires:
  ``h.connect(a[1], w[1], b[1])``, or a list of each for several at once.

Nothing here runs WireViz. The checks a build makes are this module's: a wire
whose two ends are on boards joins pins carrying the same net (or names the two
nets it joins on purpose), a pin takes one wire, a wire is connected once,
every connector and cable is used, and every colour, gauge and length is one
WireViz reads. Lengths are millimetres here and metres in the document, as
WireViz has them.
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from cadgen.wireviz.colors import COLOR_CODES, COLOR_NAMES, split_colors

__all__ = ["Cable", "Connection", "Connector", "Harness", "HarnessError", "Pin", "Wire"]


class HarnessError(ValueError):
    """A harness that cannot be what its script says. The message says how to fix it."""


# A designator is how WireViz names a connector or cable. WireViz reads a "." in a
# connection as "a new instance of a template" and a run of "-" or "=" as an arrow, so
# designators keep to letters, digits, "_", "+" and "-", starting with a letter or "_".
_DESIGNATOR = re.compile(r"[A-Za-z_][A-Za-z0-9_+-]*")
# The part-number fields a connector or a cable may carry, and an additional component's fields,
# in the order the document writes them (cadgen.wireviz.document).
PART_TEXT = ("pn", "manufacturer", "mpn", "supplier", "spn")
_CONNECTOR_KEYS = (
    "name", "type", "subtype", "color", "style", "pins", "pinlabels", "pincount", "pincolors",
    "hide_disconnected_pins", "notes", "additional_components", *PART_TEXT,
)
_CABLE_KEYS = (
    "wirecount", "colors", "color_code", "wirelabels", "gauge", "length", "shield", "category",
    "type", "color", "notes", "additional_components", *PART_TEXT,
)
COMPONENT_KEYS = ("type", "subtype", "manufacturer", "mpn", "supplier", "spn", "pn", "qty", "unit", "qty_multiplier")
_CONNECTOR_MULTIPLIERS = ("pincount", "populated", "unpopulated")
_CABLE_MULTIPLIERS = ("wirecount", "terminations", "length", "total_length")
_CATEGORIES = ("bundle",)
_STYLES = ("simple",)
# A bare gauge number is mm², as WireViz reads it; past this it is far more likely an AWG
# number written without its unit than a cable that thick.
_LARGEST_BARE_MM2 = 10.0


# --- values ------------------------------------------------------------------


def _closest(word: str, choices: Sequence[str]) -> str:
    found = difflib.get_close_matches(word, list(choices), n=1, cutoff=0.6)
    return f"did you mean {found[0]!r}? " if found else ""


def _check_keys(where: str, given: dict, allowed: Sequence[str]) -> None:
    for key in given:
        if key not in allowed:
            raise HarnessError(
                f"{where} has no {key!r}; {_closest(key, allowed)}its keywords are {', '.join(sorted(allowed))}"
            )


def _text(value: Any, *, what: str, multiline: bool = False, empty: bool = False) -> str:
    """Printable text WireViz can draw: its labels are Graphviz HTML, where < > & are markup."""
    if not isinstance(value, str):
        raise HarnessError(f"{what} is text, got {value!r}")
    text = value.strip()
    if not text and not empty:
        raise HarnessError(f"{what} cannot be empty")
    for char in text:
        if char in "<>&":
            raise HarnessError(
                f"{what} {value!r} contains {char!r}: WireViz draws text as Graphviz HTML labels, where "
                "<, > and & are markup; spell it out (\"and\", \"less than\")"
            )
        if char == "\n" and multiline:
            continue
        if unicodedata.category(char) in ("Cc", "Cs", "Zl", "Zp") or char in ("\ufffe", "\uffff"):
            line = "" if multiline else " on one line"
            raise HarnessError(f"{what} {value!r} contains the control character {char!r}; write printable text{line}")
    return text


def _color(value: Any, *, what: str) -> str:
    if isinstance(value, str) and split_colors(value) is not None:
        return value
    if isinstance(value, str) and split_colors(value.strip().upper()) is not None:
        raise HarnessError(f"{what} {value!r}: WireViz colour codes are capitals, {value.strip().upper()!r}")
    known = ", ".join(f"{code} ({name})" for code, name in COLOR_NAMES.items())
    raise HarnessError(
        f"{what} {value!r} is not a WireViz colour: a two-letter code, or several run together for a "
        f"striped wire (\"WHGN\" is white with a green stripe). The codes are {known}"
    )


def decimal(number: float) -> str:
    """A number as WireViz's YAML reads it: always a decimal point, never an exponent."""
    text = f"{number:.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _gauge(value: Any, *, what: str) -> str:
    """``"22 AWG"`` or a cross-section, as the document spells it (``"0.25 mm2"``)."""
    hint = (
        f"{what} is a wire gauge: \"22 AWG\", or a cross-section in mm² (0.25, or \"0.25 mm2\"); got {value!r}"
    )
    if isinstance(value, bool):
        raise HarnessError(hint)
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise HarnessError(hint)
        if number > _LARGEST_BARE_MM2:
            raise HarnessError(
                f"{what}={value!r} reads as {number:g} mm² (WireViz's unit for a bare number): for AWG write "
                f"\"{value} AWG\"; for a cable that thick write \"{value} mm2\""
            )
        return f"{decimal(number)} mm2"
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(AWG|awg|mm2|mm²|MM2)\s*", value)
        if match is not None:
            number, unit = match.group(1), match.group(2).lower()
            if unit == "awg":
                if "." in number or not 0 <= int(number) <= 40:
                    raise HarnessError(f"{what} {value!r}: an AWG gauge is a whole number from 0 to 40")
                return f"{int(number)} AWG"
            if float(number) <= 0:
                raise HarnessError(hint)
            return f"{decimal(float(number))} mm2"
    raise HarnessError(hint)


def _length(value: Any, *, what: str) -> float:
    """Millimetres in, metres out: WireViz's unit for a bare length."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HarnessError(f"{what} is millimetres, a number (300 for a 30 cm cable); got {value!r}")
    millimetres = float(value)
    if not math.isfinite(millimetres) or millimetres <= 0:
        raise HarnessError(f"{what} must be more than 0 mm, got {value!r}")
    metres = round(millimetres / 1000.0, 6)
    if metres <= 0:
        raise HarnessError(f"{what} {value!r} mm is shorter than a micrometre")
    return metres


def _pin_id(value: Any, *, what: str) -> int | str:
    """A pin as WireViz names it: a whole number, or text WireViz will not read as one."""
    if isinstance(value, bool):
        raise HarnessError(f"{what} is a pin number or name, got {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise HarnessError(f"{what} {value!r} is negative")
        return value
    text = _text(value, what=what)
    if re.fullmatch(r"0|[1-9][0-9]*", text):
        return int(text)
    try:
        number = int(text)
    except ValueError:
        pass
    else:
        raise HarnessError(f"{what} {value!r} cannot be written for WireViz, which reads it as the number {number}")
    if "-" in text:
        low, high = text.split("-", 1)
        try:
            int(low), int(high)
        except ValueError:
            pass
        else:
            raise HarnessError(f"{what} {value!r} cannot be written for WireViz, which reads it as a range of pins")
    return text


def _components(value: Any, *, what: str, multipliers: Sequence[str]) -> tuple[dict, ...]:
    """WireViz's ``additional_components``: terminals, seals, sleeves -- each a BOM line."""
    if isinstance(value, dict) or not isinstance(value, (list, tuple)):
        raise HarnessError(f"{what} is a list of components, each a dict such as {{'type': 'Crimp terminal', 'mpn': '...'}}")
    found = []
    for index, item in enumerate(value):
        where = f"{what}[{index}]"
        if not isinstance(item, dict):
            raise HarnessError(f"{where} is a dict of {', '.join(COMPONENT_KEYS)}; got {item!r}")
        _check_keys(where, item, COMPONENT_KEYS)
        if "type" not in item:
            raise HarnessError(f"{where} needs a type, what the part is (\"Crimp terminal\")")
        component: dict[str, Any] = {}
        for key in COMPONENT_KEYS:
            if key not in item:
                continue
            raw = item[key]
            if key == "qty":
                if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw <= 0:
                    raise HarnessError(f"{where} qty is a number more than 0, got {raw!r}")
                component[key] = raw
            elif key == "qty_multiplier":
                if raw not in multipliers:
                    raise HarnessError(f"{where} qty_multiplier is one of {', '.join(multipliers)}; got {raw!r}")
                component[key] = raw
            else:
                component[key] = _text(raw, what=f"{where} {key}")
        found.append(component)
    return tuple(found)


def _part_text(fields: dict, *, where: str) -> dict[str, str]:
    return {key: _text(fields.pop(key), what=f"{where} {key}") for key in PART_TEXT if key in fields}


def _is_geometry(value: Any) -> bool:
    return any(
        cls.__module__.split(".")[0] in ("build123d", "OCP") or cls.__name__ == "LazyCompound"
        for cls in type(value).__mro__
    )


def _listing(pins: Sequence["Pin"]) -> str:
    return ", ".join(f"{pin.id}" + (f"={pin.label}" if pin.label and pin.label != str(pin.id) else "") for pin in pins)


# --- the parts of a harness ------------------------------------------------------


class Pin:
    """One pin of a harness connector: what a wire ends on.

    ``net`` is the net the pin carries on its board (``None`` for a free
    connector's pin, or a board pin on no net); ``label`` is what the drawing
    shows beside it -- a board pin's net name, a free connector's pin label.
    """

    __slots__ = ("connector", "id", "label", "net", "net_named")

    def __init__(self, connector: "Connector", id: int | str, label: str, net: str | None = None, net_named: bool = False):
        self.connector = connector
        self.id = id
        self.label = label
        self.net = net
        self.net_named = net_named

    def describe(self) -> str:
        label = f" ({self.label})" if self.label and self.label != str(self.id) else ""
        return f"{self.connector.name} pin {self.id}{label}"

    def __repr__(self) -> str:
        label = f" {self.label}" if self.label and self.label != str(self.id) else ""
        return f"Pin({self.connector.name}:{self.id}{label})"


class Connector:
    """A connector: its pins, and the WireViz fields that say what it is."""

    def __init__(self, harness: "Harness", name: str, fields: dict[str, Any], *, mates: str | None = None):
        self._harness = harness
        self.name = name
        self.fields = fields
        #: For a board connector, what it mates with on the board ("J3 of controller").
        self.mates = mates
        self._pins: list[Pin] = []

    @property
    def on_board(self) -> bool:
        return self.mates is not None

    @property
    def pins(self) -> list[Pin]:
        """Every pin, in order: pass them to ``connect`` as a list."""
        return list(self._pins)

    def __getitem__(self, key: int | str) -> Pin:
        if isinstance(key, slice):
            raise HarnessError(f"take {self.name}'s pins as a list, [{self.name.lower()}[1], {self.name.lower()}[2]], or all of them as .pins")
        if isinstance(key, bool):
            raise HarnessError(f"{self.name}[{key!r}]: name a pin by its number or its label")
        text = str(key)
        for pin in self._pins:
            if str(pin.id) == text:
                return pin
        labelled = [pin for pin in self._pins if pin.label == text]
        if len(labelled) == 1:
            return labelled[0]
        if labelled:
            numbers = ", ".join(str(pin.id) for pin in labelled)
            raise HarnessError(
                f"{self.name} has {len(labelled)} pins labelled {text!r} (pins {numbers}); name one by its number, "
                f"for example {self.name.lower()}[{labelled[0].id!r}]"
            )
        raise HarnessError(f"{self.name} has no pin {key!r}; its pins are {_listing(self._pins)}")

    def __repr__(self) -> str:
        return f"Connector({self.name}, {len(self._pins)} pins)"


class Wire:
    """One wire of a cable (``id`` 1, 2...), or its shield (``id`` "s")."""

    __slots__ = ("cable", "id", "color", "label")

    def __init__(self, cable: "Cable", id: int | str, color: str, label: str):
        self.cable = cable
        self.id = id
        self.color = color
        self.label = label

    def describe(self) -> str:
        if self.id == "s":
            return f"{self.cable.name} shield"
        color = f" ({self.color})" if self.color else ""
        return f"{self.cable.name} wire {self.id}{color}"

    def __repr__(self) -> str:
        color = f" {self.color}" if self.color else ""
        return f"Wire({self.cable.name}:{self.id}{color})"


class Cable:
    """A cable (or, with ``category="bundle"``, loose wires): its wires and WireViz fields."""

    def __init__(self, harness: "Harness", name: str, fields: dict[str, Any], colors: list[str], labels: list[str], shield: bool):
        self._harness = harness
        self.name = name
        self.fields = fields
        self.colors = colors
        self.wirelabels = labels
        self._wires = [
            Wire(self, index + 1, color, labels[index] if labels else "") for index, color in enumerate(colors)
        ]
        self.shield = Wire(self, "s", "", "") if shield else None

    @property
    def wirecount(self) -> int:
        return len(self._wires)

    @property
    def wires(self) -> list[Wire]:
        """Every wire in order (the shield is ``cable["s"]``): pass them to ``connect`` as a list."""
        return list(self._wires)

    def __getitem__(self, key: int | str) -> Wire:
        if isinstance(key, slice):
            raise HarnessError(f"take {self.name}'s wires as a list, [w[1], w[2]], or all of them as .wires")
        if isinstance(key, bool):
            raise HarnessError(f"{self.name}[{key!r}]: name a wire by its number, colour or label")
        if key == "s":
            if self.shield is None:
                raise HarnessError(f"{self.name} has no shield; declare it with shield=True")
            return self.shield
        text = str(key)
        for wire in self._wires:
            if str(wire.id) == text:
                return wire
        for attribute, word in (("color", "coloured"), ("label", "labelled")):
            matches = [wire for wire in self._wires if getattr(wire, attribute) == text]
            if len(matches) == 1:
                return matches[0]
            if matches:
                numbers = ", ".join(str(wire.id) for wire in matches)
                raise HarnessError(
                    f"{self.name} has {len(matches)} wires {word} {text!r} (wires {numbers}); name one by its number"
                )
        listing = ", ".join(f"{wire.id}" + (f"={wire.color}" if wire.color else "") for wire in self._wires)
        raise HarnessError(f"{self.name} has no wire {key!r}; its wires are {listing}" + (", and s (the shield)" if self.shield else ""))

    def __repr__(self) -> str:
        return f"Cable({self.name}, {self.wirecount} wires)"


@dataclass(frozen=True)
class Connection:
    """One wire's run: from a pin (or nothing), through the wire, to a pin (or nothing)."""

    start: Pin | None
    wire: Wire
    end: Pin | None
    #: The two board nets a wire joins on purpose (``joins=``), else None.
    joins: tuple[str, str] | None
    #: Which ``connect`` call made it: one call is one WireViz connection set (or several).
    group: int


# --- the harness -----------------------------------------------------------------


class Harness:
    """A wiring harness: connectors, cables and the connections between them."""

    def __init__(self, *, title: str | None = None):
        self.title = _text(title, what="Harness title") if title is not None else None
        self._connectors: dict[str, Connector] = {}
        self._cables: dict[str, Cable] = {}
        self._connections: list[Connection] = []
        self._groups = 0
        self._pin_uses: dict[int, Connection] = {}
        self._wire_uses: dict[int, Connection] = {}

    # -- what it holds --

    @property
    def connectors(self) -> list[Connector]:
        return list(self._connectors.values())

    @property
    def cables(self) -> list[Cable]:
        return list(self._cables.values())

    @property
    def connections(self) -> list[Connection]:
        return list(self._connections)

    def _designator(self, value: Any, *, what: str, hint: str) -> str:
        name = _text(value, what=what) if isinstance(value, str) else value
        if not isinstance(name, str) or not _DESIGNATOR.fullmatch(name):
            raise HarnessError(
                f"{what} {value!r} is not a designator WireViz can use: letters, digits, _ + and -, starting with a "
                "letter or _ (\"X1\", \"CTRL_J3\")"
            )
        if name.startswith("__"):
            raise HarnessError(f"{what} {value!r}: WireViz hides names that start with __; drop the leading underscores")
        if name in self._connectors or name in self._cables:
            raise HarnessError(f"{name} is already a connector or cable of this harness; {hint}")
        return name

    # -- connectors --

    def connector(self, source: Any, ref: str | None = None, /, **fields: Any) -> Connector:
        """A connector: a board's part, or a free one (a motor's lead, a battery).

        ``h.connector(board, "J3", type=...)`` or ``h.connector(board_part,
        type=...)``: the pins are the part's, each labelled with the net it
        carries on the board; ``type`` names the housing that mates with it,
        and the designator defaults to the part's reference (``name=`` sets
        one). ``h.connector("M1", pinlabels=[...])``: a free connector named
        by its designator, with ``pins``, ``pinlabels`` or ``pincount``.
        Either takes WireViz's fields: ``subtype``, ``color``, ``style``
        ("simple": one pin), ``pincolors``, ``hide_disconnected_pins``,
        ``notes``, ``pn``, ``manufacturer``, ``mpn``, ``supplier``, ``spn`` and
        ``additional_components`` (terminals and seals, each a BOM line).
        """
        _check_keys("connector()", fields, _CONNECTOR_KEYS)
        part = self._board_part(source, ref)
        if part is None:
            if "name" in fields:
                raise HarnessError(f"a free connector is named by its first argument, h.connector({source!r}, ...): drop name=")
            name = self._designator(source, what="connector", hint="give this one another designator")
            return self._free_connector(name, dict(fields))
        return self._board_connector(part, dict(fields))

    def _board_part(self, source: Any, ref: Any) -> Any:
        """The board part a connector mates with, or None for a free connector."""
        if isinstance(source, str):
            if ref is not None:
                raise HarnessError(
                    f"h.connector({source!r}, {ref!r}): a free connector takes its designator alone; a board's part is "
                    f"h.connector(board, {ref!r}, type=...)"
                )
            return None
        from cadgen.kicad.design import Board, Part

        if isinstance(source, Part):
            if ref is not None:
                raise HarnessError(f"h.connector({source.ref}, {ref!r}): a board's part is already one connector; drop {ref!r}")
            if not isinstance(source._board, Board):
                raise HarnessError(f"{source.ref} belongs to a simulation testbench, not a pcb.Board")
            return source
        if isinstance(source, Board):
            if ref is None:
                raise HarnessError("h.connector(board, ...) names the board's connector by its reference: h.connector(board, \"J3\", type=...)")
            wanted = str(ref)
            for part in source.parts:
                if part.ref == wanted:
                    return part
            refs = ", ".join(part.ref for part in source.parts) or "none"
            raise HarnessError(f"the board has no part {wanted!r}; its parts are {refs}")
        if _is_geometry(source):
            raise HarnessError(
                "h.connector() got 3D geometry, not a board. Call the board's @pcb model inside the @harness "
                "function: there it returns its pcb.Board, whether or not it has a 3D export"
            )
        raise HarnessError(
            "h.connector() takes a pcb.Board and a part reference (h.connector(board, \"J3\", type=...)), a board's "
            f"part (h.connector(j3, type=...)), or a designator for a free connector (h.connector(\"M1\", "
            f"pinlabels=[...])); got {type(source).__name__}"
        )

    def _board_connector(self, part: Any, fields: dict[str, Any]) -> Connector:
        for key in ("pins", "pinlabels", "pincount"):
            if key in fields:
                raise HarnessError(
                    f"{part.ref}'s pins come from the board, labelled with their nets; drop {key}= (a free connector "
                    "is h.connector(\"X1\", pinlabels=[...]))"
                )
        board = part._board
        where = f"{part.ref} of {board.title}" if getattr(board, "title", None) else part.ref
        if "type" not in fields:
            footprint = getattr(getattr(part, "_footprint", None), "lib_id", None)
            header = f" ({footprint})" if footprint else ""
            raise HarnessError(
                f"connector {where}: name the housing that mates with the board's header{header}, "
                "type=\"JST PH 2.0 mm, 4 pin\": the board has the header, the harness has the housing"
            )
        name = self._designator(
            fields.pop("name", part.ref), what="connector",
            hint=f"name this one: h.connector(board, {part.ref!r}, name=\"{part.ref}_2\", ...)",
        )
        footprint = getattr(getattr(part, "_footprint", None), "lib_id", None)
        mates = where + (f": {footprint.split(':', 1)[-1]}" if footprint else "")
        notes = fields.pop("notes", None)
        # The board's title is the board author's text: keep WireViz's markup out of it.
        mate_note = f"mates {mates}".replace("&", "and").replace("<", "").replace(">", "")
        fields["notes"] = (_text(notes, what=f"connector {name} notes", multiline=True) + "\n" + mate_note) if notes is not None else mate_note
        connector = Connector(self, name, {}, mates=mates)
        unconnected = {pin.number for pin in part.unconnected()}
        pins = []
        for board_pin in part.pins():
            net = board_pin.net
            if net is not None:
                if any(char in net.name for char in "<>&"):
                    raise HarnessError(
                        f"{where} pin {board_pin.number} is on net {net.name!r}, whose name WireViz cannot draw "
                        "(its labels are Graphviz HTML, where <, > and & are markup): rename the net on the board"
                    )
                label, net_name, named = net.name, net.name, net.named
            else:
                label, net_name, named = ("" if board_pin.number in unconnected else "NC"), None, False
            pins.append(Pin(connector, _pin_id(board_pin.number, what=f"{part.ref} pin"), label, net_name, named))
        connector._pins = pins
        connector.fields = self._connector_fields(name, fields, len(pins))
        self._connectors[name] = connector
        return connector

    def _free_connector(self, name: str, fields: dict[str, Any]) -> Connector:
        pins = fields.pop("pins", None)
        labels = fields.pop("pinlabels", None)
        count = fields.pop("pincount", None)
        where = f"connector {name}"
        if pins is None and labels is None and count is None:
            raise HarnessError(f"{where} needs its pins: pins=[1, 2], pinlabels=[\"A+\", \"A-\"] or pincount=2")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 1):
            raise HarnessError(f"{where} pincount is a whole number of pins, 1 or more; got {count!r}")
        for key, value in (("pins", pins), ("pinlabels", labels)):
            if value is not None and (isinstance(value, (str, dict)) or not isinstance(value, (list, tuple)) or not value):
                raise HarnessError(f"{where} {key} is a non-empty list, got {value!r}")
        ids = [_pin_id(pin, what=f"{where} pin") for pin in pins] if pins is not None else None
        texts = [_text(label, what=f"{where} pin label", empty=True) for label in labels] if labels is not None else None
        sizes = {key: len(value) for key, value in (("pins", ids), ("pinlabels", texts)) if value is not None}
        if count is not None:
            sizes["pincount"] = count
        if len(set(sizes.values())) > 1:
            listed = ", ".join(f"{key} {size}" for key, size in sizes.items())
            raise HarnessError(f"{where} has a different number of pins in each list ({listed}); give one per pin")
        total = next(iter(sizes.values()))
        ids = ids if ids is not None else list(range(1, total + 1))
        texts = texts if texts is not None else [""] * total
        seen: dict[str, int] = {}
        for pin in ids:
            if str(pin) in seen:
                raise HarnessError(f"{where} has pin {pin!r} twice; every pin has its own number or name")
            seen[str(pin)] = 1
        for index, label in enumerate(texts):
            other = next((pin for position, pin in enumerate(ids) if isinstance(pin, str) and pin == label and position != index), None)
            if other is not None:
                raise HarnessError(
                    f"{where} gives pin {ids[index]!r} the label {label!r}, which is another pin's name: WireViz could "
                    "not tell them apart; relabel it"
                )
        connector = Connector(self, name, {})
        connector._pins = [Pin(connector, pin, label) for pin, label in zip(ids, texts)]
        connector.fields = self._connector_fields(name, fields, total)
        self._connectors[name] = connector
        return connector

    def _connector_fields(self, name: str, fields: dict[str, Any], pincount: int) -> dict[str, Any]:
        where = f"connector {name}"
        found: dict[str, Any] = {}
        for key in ("type", "subtype"):
            if key in fields:
                found[key] = _text(fields.pop(key), what=f"{where} {key}")
        if "color" in fields:
            found["color"] = _color(fields.pop("color"), what=f"{where} color")
        if "style" in fields:
            style = fields.pop("style")
            if style not in _STYLES:
                raise HarnessError(f"{where} style is \"simple\" (a one-pin connector such as a ferrule) or omitted; got {style!r}")
            if pincount != 1:
                raise HarnessError(f"{where} has style=\"simple\", which is one pin, but it has {pincount}")
            found["style"] = style
        found.update(_part_text(fields, where=where))
        if "pincolors" in fields:
            colors = fields.pop("pincolors")
            if isinstance(colors, str) or not isinstance(colors, (list, tuple)) or len(colors) != pincount:
                raise HarnessError(f"{where} pincolors is a list of one colour per pin ({pincount}); got {colors!r}")
            found["pincolors"] = [_color(color, what=f"{where} pin colour") for color in colors]
        if "hide_disconnected_pins" in fields:
            hide = fields.pop("hide_disconnected_pins")
            if not isinstance(hide, bool):
                raise HarnessError(f"{where} hide_disconnected_pins is True or False, got {hide!r}")
            if hide:
                found["hide_disconnected_pins"] = True
        if "notes" in fields:
            found["notes"] = _text(fields.pop("notes"), what=f"{where} notes", multiline=True)
        if "additional_components" in fields:
            found["additional_components"] = _components(
                fields.pop("additional_components"), what=f"{where} additional_components", multipliers=_CONNECTOR_MULTIPLIERS
            )
        return found

    # -- cables --

    def cable(self, name: str, /, **fields: Any) -> Cable:
        """A cable: ``wirecount``/``colors``/``color_code``, ``gauge``, ``length`` (millimetres).

        ``colors=["RD", "BK"]`` names each wire's colour (and so the count);
        ``color_code="DIN"`` (also IEC, BW, TEL, TELALT, T568A, T568B) colours
        ``wirecount`` wires from a standard sequence. ``gauge`` is ``"22 AWG"``
        or a cross-section in mm²; ``length`` is millimetres. ``shield=True``
        adds a shield, wire ``"s"``. ``category="bundle"`` makes the wires loose
        (the BOM lists each wire). Also WireViz's ``type``, ``color`` (the
        jacket), ``wirelabels``, ``notes``, part numbers and
        ``additional_components``.
        """
        cable_name = self._designator(name, what="cable", hint="give this one another designator")
        where = f"cable {cable_name}"
        _check_keys("cable()", fields, _CABLE_KEYS)
        fields = dict(fields)
        found: dict[str, Any] = {}
        category = fields.pop("category", None)
        if category is not None:
            if category not in _CATEGORIES:
                raise HarnessError(f"{where} category is \"bundle\" (loose wires) or omitted (a jacketed cable); got {category!r}")
            found["category"] = category
        if "type" in fields:
            found["type"] = _text(fields.pop("type"), what=f"{where} type")
        if "gauge" not in fields:
            raise HarnessError(f"{where} needs gauge=, \"22 AWG\" or a cross-section in mm² (0.25): a wire with no gauge cannot be bought")
        found["gauge"] = _gauge(fields.pop("gauge"), what=f"{where} gauge")
        if "length" not in fields:
            raise HarnessError(f"{where} needs length=, in millimetres: a cable with no length cannot be cut")
        found["length"] = _length(fields.pop("length"), what=f"{where} length")
        colors = self._wire_colors(where, fields)
        labels = fields.pop("wirelabels", None)
        if labels is not None:
            if isinstance(labels, str) or not isinstance(labels, (list, tuple)) or len(labels) != len(colors):
                raise HarnessError(f"{where} wirelabels is a list of one label per wire ({len(colors)}); got {labels!r}")
            labels = [_text(label, what=f"{where} wire label") for label in labels]
        shield = fields.pop("shield", False)
        if not isinstance(shield, bool):
            raise HarnessError(f"{where} shield is True or False, got {shield!r}")
        if "color" in fields:
            found["color"] = _color(fields.pop("color"), what=f"{where} color")
        found.update(_part_text(fields, where=where))
        if "notes" in fields:
            found["notes"] = _text(fields.pop("notes"), what=f"{where} notes", multiline=True)
        if "additional_components" in fields:
            found["additional_components"] = _components(
                fields.pop("additional_components"), what=f"{where} additional_components", multipliers=_CABLE_MULTIPLIERS
            )
        cable = Cable(self, cable_name, found, colors, list(labels or ()), shield)
        self._cables[cable_name] = cable
        return cable

    def _wire_colors(self, where: str, fields: dict[str, Any]) -> list[str]:
        count = fields.pop("wirecount", None)
        colors = fields.pop("colors", None)
        code = fields.pop("color_code", None)
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 1):
            raise HarnessError(f"{where} wirecount is a whole number of wires, 1 or more; got {count!r}")
        if colors is not None and code is not None:
            raise HarnessError(f"{where} takes colors= or color_code=, not both")
        if code is not None:
            if code not in COLOR_CODES:
                raise HarnessError(f"{where} color_code {code!r} is not one of {', '.join(COLOR_CODES)}; {_closest(str(code), list(COLOR_CODES))}".rstrip("; "))
            if count is None:
                raise HarnessError(f"{where} color_code={code!r} needs wirecount=, how many wires to colour")
            sequence = COLOR_CODES[code]
            # More wires than the sequence starts it again, as WireViz does.
            return [sequence[index % len(sequence)] for index in range(count)]
        if colors is not None:
            if isinstance(colors, str) or not isinstance(colors, (list, tuple)) or not colors:
                raise HarnessError(f"{where} colors is a list of one colour per wire, such as [\"RD\", \"BK\"]; got {colors!r}")
            checked = [_color(color, what=f"{where} wire colour") for color in colors]
            if count is not None and count != len(checked):
                raise HarnessError(f"{where} has wirecount={count} but {len(checked)} colors; give one colour per wire")
            return checked
        if count is None:
            raise HarnessError(f"{where} needs its wires: colors=[\"RD\", \"BK\"], or wirecount= (with color_code= to colour them)")
        return [""] * count

    # -- connections --

    def connect(self, *items: Any, joins: tuple[str, str] | None = None) -> None:
        """Join pins through wires: ``h.connect(a[1], w[1], b[1])``.

        Each item is a pin, a wire, or a list of them -- one per connection, so
        ``h.connect(a.pins, w.wires, b.pins)`` makes as many connections as the
        lists are long. The order is pin, wire, pin; a wire with a free end is
        pin, wire or wire, pin. A pin takes one wire and a wire is connected
        once. Where both ends are on boards they must carry the same net;
        ``joins=("TX", "RX")`` says a wire joins two different nets on purpose
        (and is checked: the ends must carry exactly those).
        """
        if len(items) not in (2, 3):
            raise HarnessError(
                "connect() joins pins through wires: connect(pin, wire, pin), or connect(pin, wire) / "
                f"connect(wire, pin) for a wire with a free end; got {len(items)} items"
            )
        columns = [self._column(item) for item in items]
        counts = [len(column) for column in columns]
        if len(set(counts)) > 1:
            raise HarnessError(
                f"connect() got lists of {', '.join(str(count) for count in counts)} items: each list names one item "
                "per connection, so they are the same length"
            )
        kinds = tuple("pin" if isinstance(column[0], Pin) else "wire" for column in columns)
        if kinds not in (("pin", "wire", "pin"), ("pin", "wire"), ("wire", "pin")):
            raise HarnessError(f"connect() takes (pin, wire, pin), (pin, wire) or (wire, pin); got ({', '.join(kinds)})")
        if joins is not None:
            if (
                not isinstance(joins, (tuple, list)) or len(joins) != 2
                or not all(isinstance(name, str) and name.strip() for name in joins)
            ):
                raise HarnessError(f"joins= is the two board nets a wire joins, (\"TX\", \"RX\"); got {joins!r}")
            if counts[0] != 1:
                raise HarnessError("joins= declares one wire's crossing: connect that wire in a connect() call of its own")
            joins = (joins[0].strip(), joins[1].strip())
        made: list[Connection] = []
        pins_now: dict[int, Connection] = {}
        wires_now: dict[int, Connection] = {}
        for index in range(counts[0]):
            row = [column[index] for column in columns]
            start = row[0] if kinds[0] == "pin" else None
            wire = row[1] if kinds[0] == "pin" else row[0]
            end = row[-1] if kinds[-1] == "pin" else None
            connection = Connection(start, wire, end, joins, self._groups)
            for pin in (start, end):
                if pin is None:
                    continue
                earlier = self._pin_uses.get(id(pin)) or pins_now.get(id(pin))
                if earlier is not None:
                    raise HarnessError(
                        f"{pin.describe()} is already wired ({_run(earlier)}): a pin takes one wire"
                    )
                pins_now[id(pin)] = connection
            earlier = self._wire_uses.get(id(wire)) or wires_now.get(id(wire))
            if earlier is not None:
                raise HarnessError(
                    f"{wire.describe()} is already connected ({_run(earlier)}): connect each wire once, both ends in one call"
                )
            wires_now[id(wire)] = connection
            self._check_nets(connection)
            made.append(connection)
        self._connections.extend(made)
        self._pin_uses.update(pins_now)
        self._wire_uses.update(wires_now)
        self._groups += 1

    def _column(self, item: Any) -> list:
        values = list(item) if isinstance(item, (list, tuple)) else [item]
        if not values:
            raise HarnessError("connect() got an empty list")
        for value in values:
            if isinstance(value, Connector):
                raise HarnessError(f"connect() takes pins: {value.name}[1], or all of {value.name}'s pins as {value.name.lower()}.pins")
            if isinstance(value, Cable):
                raise HarnessError(f"connect() takes wires: {value.name}[1], or all of {value.name}'s wires as {value.name.lower()}.wires")
            if not isinstance(value, (Pin, Wire)):
                raise HarnessError(f"connect() takes pins (x[1]), wires (w[1]) or lists of them; got {value!r}")
            owner = value.connector if isinstance(value, Pin) else value.cable
            if owner._harness is not self:
                raise HarnessError(f"{value!r} belongs to another harness")
        if len({type(value) for value in values}) > 1:
            raise HarnessError("connect() got a list that mixes pins and wires: give pins and wires as separate lists")
        return values

    def _check_nets(self, connection: Connection) -> None:
        start, wire, end, joins = connection.start, connection.wire, connection.end, connection.joins
        on_boards = start is not None and end is not None and start.connector.on_board and end.connector.on_board
        if not on_boards:
            if joins is not None:
                raise HarnessError(
                    f"joins= names the two board nets a wire joins, but {wire.describe()} does not run from one board "
                    "connector to another; drop joins="
                )
            return
        for pin in (start, end):
            if pin.net is None:
                raise HarnessError(
                    f"{pin.describe()} is on no net on its board ({pin.connector.mates}): wire a pin the board "
                    "connects, or connect this one on the board"
                )
        if joins is not None:
            if start.net == end.net:
                raise HarnessError(
                    f"joins= declares that {wire.describe()} joins two different nets, but both ends carry "
                    f"{start.net}: drop joins="
                )
            if joins != (start.net, end.net):
                raise HarnessError(
                    f"joins={joins!r}, but {wire.describe()} runs from {start.describe()} (net {start.net}) to "
                    f"{end.describe()} (net {end.net}): joins= names those two nets, in that order"
                )
            return
        if start.net != end.net:
            here = [str(pin.id) for pin in end.connector.pins if pin.net == start.net]
            there = f" ({end.connector.name} carries {start.net} on pin {', '.join(here)})" if here else ""
            raise HarnessError(
                f"{wire.describe()} runs from {start.connector.name} pin {start.id} (net {start.net} on its board) "
                f"to {end.connector.name} pin {end.id} (net {end.net} on its board): the two ends carry different "
                f"nets{there}. Wire the pins that carry the same net, or, where the cable joins two different nets "
                f"on purpose (TX to RX), say so: h.connect(..., joins=(\"{start.net}\", \"{end.net}\"))"
            )
        if not start.net_named and not end.net_named:
            raise HarnessError(
                f"{wire.describe()} joins {start.describe()} to {end.describe()}, but neither board names that net "
                f"({start.net} is the name KiCad makes up for an unnamed net, so two boards can share it by chance): "
                "name it on each board, board.net(\"NAME\")"
            )

    # -- what a build checks before it writes --

    def problems(self) -> list[str]:
        """What stops this harness being written, each a sentence that says what to do."""
        found: list[str] = []
        if not self._connections:
            found.append("the harness connects nothing: join pins through wires with h.connect(pin, wire, pin)")
        used_connectors = {pin.connector.name for connection in self._connections for pin in (connection.start, connection.end) if pin is not None}
        used_cables = {connection.wire.cable.name for connection in self._connections}
        for name in self._connectors:
            if name not in used_connectors:
                found.append(
                    f"connector {name} is declared but no wire reaches it: connect it or remove it (WireViz leaves a "
                    "connector no connection names out of the drawing and the bill of materials)"
                )
        for name in self._cables:
            if name not in used_cables:
                found.append(f"cable {name} is declared but connected to nothing: connect it or remove it")
        return found


def _run(connection: Connection) -> str:
    ends = [
        connection.start.describe() if connection.start is not None else "a free end",
        connection.wire.describe(),
        connection.end.describe() if connection.end is not None else "a free end",
    ]
    return " -> ".join(ends)
