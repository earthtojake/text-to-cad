"""SPICE text for a circuit: KiCad's simulation fields, read the way KiCad reads them.

KiCad keeps a part's simulation model in its symbol's own fields, and a
testbench reads the same fields, so a model given once works in cadgen and in
KiCad's simulator alike. A part's fields are its library symbol's, overridden
by the part's own ``properties``:

- ``Sim.Library`` + ``Sim.Name``: a ``.model`` or ``.subckt`` in a SPICE model
  file. The path is absolute, uses KiCad's variables (``${KICAD10_SYMBOL_DIR}``,
  ``${KIPRJMOD}``), or is relative to the testbench's folder, as KiCad's are to
  its project's. The file is read (so a build that simulates traces it) and
  included;
- ``Sim.Device`` + ``Sim.Type``: one of SPICE's built-in devices (``R``, ``C``,
  ``L``, ``D``, ``NPN``/``PNP``, ``NJFET``/``PJFET``, ``NMOS``/``PMOS``, the
  ``V``/``I`` sources), with ``Sim.Params`` its parameters (``bf=200 is=1f``);
- ``Sim.Pins``: which symbol pin is which model pin (``1=K 2=A``). Without it
  the pins are taken in number order, as KiCad takes them;
- no fields at all on a two-pin part whose reference starts with ``R``, ``C``
  or ``L``: an ideal resistor, capacitor or inductor of the part's value, read
  the way KiCad reads a value (``10k``, ``4k7``, ``2R2``, ``100n``, ``1M`` is
  mega and ``1m`` milli). A ``V`` or ``I`` reference makes a DC source;
- ``Sim.Enable`` = ``0``, or a library symbol marked ``exclude_from_sim``,
  leaves the part out.

What KiCad's simulator would read wrongly is refused here with the fix rather
than simulated differently: a value such as ``10k 1%`` or ``4k70``, a part with
no model, pins taken in an order their own names contradict.

Nothing here runs a simulator (that is :mod:`cadgen.kicad.ngspice`) or imports
anything heavy.
"""

from __future__ import annotations

import difflib
import math
import os
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cadgen.kicad import sexpr
from cadgen.kicad.design import DesignError, Part, Pin
from cadgen.kicad.naming import natural

__all__ = [
    "LibraryEntry",
    "PartModel",
    "SIM_FIELDS",
    "library_entries",
    "parse_value",
    "part_model",
    "sim_fields",
    "spice_number",
]

#: KiCad's simulation fields; any other ``Sim.*`` property on a part is a typo.
SIM_FIELDS = ("Sim.Device", "Sim.Type", "Sim.Pins", "Sim.Params", "Sim.Library", "Sim.Name", "Sim.Enable")

# --- numbers --------------------------------------------------------------------

_ENGINEERING = ((12, "T"), (9, "G"), (6, "Meg"), (3, "k"), (0, ""), (-3, "m"), (-6, "u"), (-9, "n"), (-12, "p"), (-15, "f"))


def spice_number(value: float) -> str:
    """``value`` in SPICE notation: ``4.7k``, ``100n``, ``1Meg`` (SPICE's ``M`` is milli)."""
    number = float(value)
    if not math.isfinite(number):
        raise DesignError(f"{value!r} is not a finite number")
    if number == 0:
        return "0"
    exponent = math.floor(math.log10(abs(number)))
    if exponent >= 15 or exponent < -15:
        return f"{number:.12g}"
    for power, prefix in _ENGINEERING:
        if exponent >= power:
            return f"{number / 10.0 ** power:.12g}{prefix}"
    return f"{number:.12g}"  # pragma: no cover - the table ends at -15


_MICRO = "uU\u00b5\u03bc\U0001d6cd\U0001d707\U0001d741"  # u, U and the micro signs KiCad accepts
_SCALES = {
    **{char: -15 for char in "fF"},
    **{char: -12 for char in "pP"},
    **{char: -9 for char in "nN"},
    **{char: -6 for char in _MICRO},
    "m": -3,
    "M": 6,
    **{char: 3 for char in "kK"},
    **{char: 9 for char in "gG"},
    **{char: 12 for char in "tT"},
}
_PREFIX = r"(?P<prefix>[Mm][Ee][Gg]|[fFpPnN" + _MICRO + r"mMkKgGtT])?"
# KiCad's unit letters for a passive's value: farad, henry, ohm (and RKM's R).
_PASSIVE_UNIT = "(?:[fFhHrR\u03a9\u2126\U0001d6c0\U0001d6fa\U0001d76e]|ohm)"
_SOURCE_UNIT = "[vVaA]"


def _value_pattern(unit: str) -> re.Pattern:
    return re.compile(
        r"(?P<sign>-)?(?P<mantissa>\d+\.?\d*|\.\d+)(?:[eE](?P<exponent>[+-]?\d+))?"
        + _PREFIX
        + f"(?P<unit>{unit})?(?P<fraction>\\d+)?(?P<unit2>{unit})?"
    )


_PASSIVE_VALUE = _value_pattern(_PASSIVE_UNIT)
_SOURCE_VALUE = _value_pattern(_SOURCE_UNIT)
_WHAT = {"R": "a resistance", "C": "a capacitance", "L": "an inductance", "V": "a voltage", "I": "a current"}
_EXAMPLES = {"R": "10k, 4k7, 2R2 or 1M (mega)", "C": "100n, 4n7 or 10u", "L": "10u or 2u2", "V": "5, 3V3 or 1.8", "I": "1m, 20mA or 500u"}


def parse_value(text: str, *, kind: str, ref: str = "the part") -> float:
    """A part's Value field as KiCad's simulator reads it; ``kind`` is R, C, L, V or I.

    ``M`` is mega and ``m`` milli, as on a schematic; ``4k7`` is 4.7k and ``2R2``
    2.2 ohm. A value KiCad's simulator would misread (``10k 1%``, ``4k70``,
    ``1,5k``) is a :class:`DesignError` saying how to write it.
    """
    original = str(text)
    compact = "".join(original.split())
    what = _WHAT[kind]
    source = kind in "VI"
    if source and compact[:2].upper() in ("DC", "AC"):
        compact = compact[2:]

    def refuse(reason: str) -> DesignError:
        return DesignError(
            f"{ref}'s value {original!r} is not {what} KiCad's simulator reads{reason}; "
            f"write it like {_EXAMPLES[kind]}, or give the part properties={{'Sim.Params': "
            f"'{'dc' if source else kind.lower()}=...'}} and keep the value as the label"
        )

    if not compact:
        raise refuse(" (it is empty)")
    if "," in compact:
        raise refuse(" (write a decimal point, not a comma)")
    match = (_SOURCE_VALUE if source else _PASSIVE_VALUE).fullmatch(compact)
    if match is None:
        raise refuse("")
    if match.group("sign") and not source:
        raise refuse(" (a part's value cannot be negative)")
    mantissa, fraction = match.group("mantissa"), match.group("fraction")
    if fraction is not None:
        if "." in mantissa or match.group("exponent"):
            raise refuse(f" (the digits after its {match.group('prefix') or match.group('unit')} would be dropped)")
        if "0" in fraction:
            raise refuse(" (KiCad's simulator misreads an RKM code with a 0 after the letter)")
        mantissa = f"{mantissa}.{fraction}"
    prefix = match.group("prefix")
    if prefix and kind == "C" and prefix in "fF" and not (match.group("unit") or match.group("unit2")):
        raise DesignError(
            f"{ref}'s value {original!r} is ambiguous: KiCad's simulator reads F as femto (SPICE's F), "
            f"not farad. For a capacitor of that many farads keep the value and add "
            f"properties={{'Sim.Params': 'c={mantissa}'}}; for femtofarads write {mantissa}fF"
        )
    number = _decimal(mantissa, match.group("exponent"), prefix)
    return -number if match.group("sign") else number


def _decimal(mantissa: str, exponent: str | None, prefix: str | None) -> float:
    """``4.7`` ``k`` -> 4700.0, parsed once from decimal text so ``100n`` is exactly 1e-07."""
    power = int(exponent or 0) + ((6 if prefix.lower() == "meg" else _SCALES[prefix]) if prefix else 0)
    return float(f"{mantissa}e{power}")


_PARAM_NUMBER = re.compile(r"(?P<sign>[+-])?(?P<mantissa>\d+\.?\d*|\.\d+)(?:[eE](?P<exponent>[+-]?\d+))?(?P<prefix>[Mm][Ee][Gg]|[fpnumkKMgGtT])?")


def _param_number(text: str) -> float | None:
    """A number in a ``Sim.*`` field (KiCad's notation: ``M`` mega, ``m`` milli), or None."""
    match = _PARAM_NUMBER.fullmatch(text)
    if match is None:
        return None
    number = _decimal(match.group("mantissa"), match.group("exponent"), match.group("prefix"))
    return -number if match.group("sign") == "-" else number


def _param_text(value: str, *, ref: str, key: str) -> str:
    """One ``Sim.Params`` value as SPICE text: numbers converted, expressions passed through."""
    text = value.strip()
    number = _param_number(text)
    if number is not None:
        return spice_number(number)
    if text[:1].isdigit() or text[:1] in ".+-":
        raise DesignError(
            f"{ref}: Sim.Params {key}={value} is not a number KiCad's simulator reads the same way; "
            "write numbers like 4.7k, 100n, 10u, 1M (mega) or 1m (milli), with no unit"
        )
    return text


_PARAM = re.compile(r'\s*([A-Za-z_][\w.]*)\s*=\s*("(?:[^"\\]|\\.)*"|\{[^}]*\}|[^\s"]+)')


def _params(text: str, *, ref: str) -> dict[str, str]:
    """``Sim.Params`` (``bf=200 is=1f``) as ``{name: raw value}``, names lowercased."""
    found: dict[str, str] = {}
    position = 0
    text = text or ""
    while position < len(text):
        if text[position:].strip() == "":
            break
        match = _PARAM.match(text, position)
        if match is None:
            raise DesignError(
                f"{ref}: Sim.Params {text!r} is not name=value pairs (for example 'bf=200 is=1f'); "
                f"the trouble starts at {text[position:].strip()!r}"
            )
        key, raw = match.group(1).lower(), match.group(2)
        if raw.startswith('"'):
            raw = re.sub(r"\\(.)", r"\1", raw[1:-1])
        if key in found:
            raise DesignError(f"{ref}: Sim.Params sets {key} twice")
        found[key] = raw
        position = match.end()
    return found


# --- fields ---------------------------------------------------------------------


def sim_fields(part: Part) -> dict[str, str]:
    """The part's ``Sim.*`` fields: the library symbol's, then the part's own, empty ones dropped."""
    fields: dict[str, str] = {}
    for key in part.properties:
        if key.startswith("Sim.") and key not in SIM_FIELDS:
            close = difflib.get_close_matches(key, SIM_FIELDS, n=1)
            raise DesignError(
                f"{part.ref} has property {key!r}, which KiCad's simulator does not read"
                + (f"; did you mean {close[0]}?" if close else f"; its fields are {', '.join(SIM_FIELDS)}")
            )
    for source in (part.symbol.properties, part.properties):
        for key, text in source.items():
            if key.startswith("Sim."):
                fields[key] = str(text).strip()
    return {key: text for key, text in fields.items() if text}


def _excluded(part: Part, fields: dict[str, str]) -> bool:
    enable = fields.get("Sim.Enable")
    if enable is not None:
        if enable.lower() in {"0", "false", "no", "off"}:
            return True
        if enable.lower() not in {"1", "true", "yes", "on"}:
            raise DesignError(f"{part.ref}: Sim.Enable is {enable!r}; KiCad reads 0 (leave the part out of simulation) or 1")
    flag = sexpr.find(part.symbol.tree, "exclude_from_sim")
    return flag is not None and len(flag) > 1 and str(flag[1]) == "yes"


# --- the model of one part ------------------------------------------------------


@dataclass(frozen=True)
class PartModel:
    """How one part is written into a netlist.

    ``pins`` holds, for each of the model's pins in SPICE's order, the symbol
    pins on it (several when ``Sim.Pins`` maps several to one; none for an
    optional pin left off, which is then not written). ``tail`` is the rest of
    the element's line after its nodes.
    """

    letter: str
    model_pins: tuple[str, ...]
    pins: tuple[tuple[Pin, ...], ...]
    tail: str
    models: tuple[str, ...] = ()
    include: Path | None = None


@dataclass(frozen=True)
class LibraryEntry:
    """A ``.model`` or ``.subckt`` in a SPICE model file."""

    kind: str  # "model" | "subckt"
    name: str
    type: str = ""  # a .model's type: D, NPN, NMOS, VDMOS...
    ports: tuple[str, ...] = ()  # a .subckt's ports, in order


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        for marker in (";", " $ ", "\t$ "):
            cut = line.find(marker)
            if cut >= 0:
                line = line[:cut].rstrip()
        if not line:
            continue
        if line.startswith("+") and lines:
            lines[-1] += " " + line[1:].strip()
        else:
            lines.append(line)
    return lines


def library_entries(path: Path) -> dict[str, LibraryEntry]:
    """Every ``.model`` and ``.subckt`` in a SPICE file, by lowercased name. The file is read."""
    entries: dict[str, LibraryEntry] = {}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line in _logical_lines(text):
        tokens = line.replace("(", " ( ").split()
        head = tokens[0].lower()
        if head == ".subckt" and len(tokens) >= 2:
            ports: list[str] = []
            for token in tokens[2:]:
                if token.lower() in {"params:", "optional:", "("} or "=" in token:
                    break
                ports.append(token)
            entries.setdefault(tokens[1].lower(), LibraryEntry("subckt", tokens[1], ports=tuple(ports)))
        elif head == ".model" and len(tokens) >= 3:
            entries.setdefault(tokens[1].lower(), LibraryEntry("model", tokens[1], type=tokens[2].upper()))
    return entries


_VARIABLE = re.compile(r"\$\{([^}]+)\}|\$\(([^)]+)\)")


def _library_path(text: str, *, folder: Path, ref: str) -> Path:
    def expand(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        if name == "KIPRJMOD":
            return str(folder)
        if name in os.environ:
            return os.environ[name]
        if re.fullmatch(r"KICAD\d+_SYMBOL_DIR", name):
            from cadgen.kicad.install import find_kicad

            symbols = find_kicad().symbol_dir
            if symbols is not None:
                return str(symbols)
        raise DesignError(f"{ref}: Sim.Library {text!r} uses ${{{name}}}, which is not set")

    expanded = _VARIABLE.sub(expand, text).replace("\\", "/")
    path = Path(expanded).expanduser()
    candidates = [path] if path.is_absolute() else [folder / path]
    spice_lib_dir = os.environ.get("SPICE_LIB_DIR", "").strip()
    if spice_lib_dir and not path.is_absolute():
        candidates.append(Path(spice_lib_dir).expanduser() / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise DesignError(
        f"{ref}: Sim.Library {text!r} is not a file (looked for {', '.join(str(c) for c in candidates)}); "
        "a relative path starts at the folder of the script that made the testbench, as KiCad's start "
        "at the project's"
    )


def _model_pin_order(part: Part, model_pins: Sequence[str], text: str | None, *, what: str, optional: Sequence[str] = ()):
    """For each model pin, in order, the symbol pins on it (``Sim.Pins``, else number order)."""
    symbol_pins = sorted(part.pins(), key=lambda pin: natural(pin.number))
    by_number = {pin.number: pin for pin in symbol_pins}
    canonical = {name.lower(): name for name in model_pins}
    assigned: dict[str, list[Pin]] = {name: [] for name in model_pins}
    if text:
        for token in text.split():
            number, equals, model_pin = token.partition("=")
            if not equals or not number or not model_pin:
                raise DesignError(f"{part.ref}: Sim.Pins {text!r} is symbol-pin=model-pin pairs, for example '1=K 2=A'")
            pin = by_number.get(number)
            if pin is None:
                raise DesignError(
                    f"{part.ref}: Sim.Pins names pin {number!r}, which {part.symbol.lib_id} does not have "
                    f"(its pins are {', '.join(p.number for p in symbol_pins)})"
                )
            name = canonical.get(model_pin.lower())
            if name is None:
                raise DesignError(
                    f"{part.ref}: Sim.Pins maps pin {number} to {model_pin!r}, but {what} has no such pin; "
                    f"its pins are {' '.join(model_pins)}"
                )
            assigned[name].append(pin)
    else:
        for pin, name in zip(symbol_pins, model_pins):
            assigned[name].append(pin)
        _check_positional(part, symbol_pins, model_pins, what=what)
    missing = [name for name in model_pins if not assigned[name] and name not in optional]
    if missing:
        listing = " ".join(f"{pin.number}" + (f"({pin.name})" if pin.name and pin.name != "~" else "") for pin in symbol_pins)
        raise DesignError(
            f"{part.ref}: {what} has pin(s) {', '.join(missing)} that no symbol pin is mapped to; "
            f"map every model pin ({' '.join(model_pins)}) in properties={{'Sim.Pins': ...}} "
            f"(symbol pins: {listing})"
        )
    return tuple(tuple(assigned[name]) for name in model_pins)


def _check_positional(part: Part, symbol_pins: list[Pin], model_pins: Sequence[str], *, what: str) -> None:
    """Refuse taking pins in number order when their own names say otherwise (a GSD MOSFET as DGS)."""
    canonical = {name.lower(): name for name in model_pins}
    names = [pin.name.lower() for pin in symbol_pins]
    if len(model_pins) < 2 or not names or any(name not in canonical for name in names) or len(set(names)) != len(names):
        return
    if all(names[index] == model_pins[index].lower() for index in range(min(len(names), len(model_pins)))):
        return
    pairs = " ".join(f"{pin.number}={canonical[pin.name.lower()]}" for pin in symbol_pins)
    raise DesignError(
        f"{part.ref}: without Sim.Pins, KiCad takes pins {' '.join(pin.number for pin in symbol_pins)} in order as "
        f"{what}'s {' '.join(model_pins[: len(symbol_pins)])}, but the symbol names them "
        f"{' '.join(pin.name for pin in symbol_pins)}; add properties={{'Sim.Pins': '{pairs}'}}"
    )


# Instance parameters go on the element's line; every other parameter is the model's.
_INSTANCE_PARAMS = {
    "D": {"area", "m", "pj", "off", "ic", "temp", "dtemp", "lm", "wm", "lp", "wp"},
    "Q": {"area", "areab", "areac", "m", "off", "ic", "icvbe", "icvce", "temp", "dtemp"},
    "J": {"area", "m", "off", "ic", "icvds", "icvgs", "temp"},
    "M": {"m", "l", "w", "ad", "as", "pd", "ps", "nrd", "nrs", "off", "ic", "icvds", "icvgs", "icvbs", "temp", "dtemp", "nf"},
}
_BJT_TYPES = {"GUMMELPOON": None, "VBIC": 4, "HICUL2": 8}
_JFET_TYPES = {"SHICHMANHODGES": None, "PARKERSKELLERN": 2}
_MOS_TYPES = {"VDMOS": None, "MOS1": None, "MOS2": 2, "MOS3": 3, "BSIM1": 4, "BSIM2": 5, "MOS6": 6, "BSIM3": 8, "MOS9": 9, "B4SOI": 10, "BSIM4": 14}
# A library .model's type: the element letter, its pins in SPICE's order, the optional ones.
_MODEL_TYPES = {
    "D": ("D", ("A", "K"), ()),
    "NPN": ("Q", ("C", "B", "E", "S"), ("S",)),
    "PNP": ("Q", ("C", "B", "E", "S"), ("S",)),
    "NJF": ("J", ("D", "G", "S"), ()),
    "PJF": ("J", ("D", "G", "S"), ()),
    "NMOS": ("M", ("D", "G", "S", "B"), ()),
    "PMOS": ("M", ("D", "G", "S", "B"), ()),
    "VDMOS": ("M", ("D", "G", "S"), ()),
}
_SOURCE_PARAMS = {
    "DC": ("dc", "ac", "ph"),
    "SIN": ("dc", "ampl", "f", "td", "theta", "phase", "ac", "ph"),
    "PULSE": ("y1", "y2", "td", "tr", "tf", "tw", "per", "np", "ac", "ph"),
    "EXP": ("y1", "y2", "td1", "tau1", "td2", "tau2", "ac", "ph"),
    "PWL": ("pwl", "ac", "ph"),
}
_DEVICES = "R, C, L, D, NPN, PNP, NJFET, PJFET, NMOS, PMOS, V, I and SUBCKT (with Sim.Library)"


def _a(word: str) -> str:
    """``word`` with its article, as it is spoken: an NPN, a PNP, an NMOS."""
    return f"{'an' if word[:1].upper() in 'AEFHILMNORSX' else 'a'} {word}"


def _model_name(ref: str) -> str:
    """The ``.model`` name of a part's own model: ``__R1`` (KiCad's), safe for SPICE and unique."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", ref)
    return f"__{safe}" if safe == ref else f"__{safe}_{zlib.crc32(ref.encode('utf-8')):08x}"


def _prefix(ref: str) -> str:
    """KiCad's reference prefix: the reference without its number (``R`` of ``R12``)."""
    return re.sub(r"\d+[A-Za-z]?$", "", ref) or ref


def part_model(part: Part, *, folder: Path) -> PartModel | None:
    """How ``part`` simulates, from its ``Sim.*`` fields; None when it is left out of simulation."""
    fields = sim_fields(part)
    if _excluded(part, fields):
        return None
    if "Sim.Library" in fields or "Sim.Name" in fields:
        return _library_model(part, fields, folder=folder)
    device, subtype = fields.get("Sim.Device", ""), fields.get("Sim.Type", "")
    if device or subtype:
        return _builtin_model(part, fields, device.upper(), subtype.upper())
    prefix = _prefix(part.ref)
    if len(part.pins()) == 2 and prefix[:1] in ("R", "C", "L"):
        return _ideal(part, fields, prefix[:1], inferred=True)
    if len(part.pins()) == 2 and prefix[:1] in ("V", "I"):
        return _source(part, fields, prefix[:1], "DC")
    raise DesignError(_no_model(part, fields))


def _library_model(part: Part, fields: dict[str, str], *, folder: Path) -> PartModel:
    library, name = fields.get("Sim.Library"), fields.get("Sim.Name")
    if not library or not name:
        raise DesignError(
            f"{part.ref}: Sim.Library and Sim.Name go together, the model file and the .model or .subckt "
            f"in it (has {'Sim.Library' if library else 'Sim.Name'} only)"
        )
    path = _library_path(library, folder=folder, ref=part.ref)
    entries = library_entries(path)
    entry = entries.get(name.lower())
    if entry is None:
        names = [found.name for found in entries.values()]
        close = difflib.get_close_matches(name, names, n=5, cutoff=0.4)
        raise DesignError(
            f"{part.ref}: {path.name} has no .model or .subckt named {name!r}"
            + (f"; did you mean {', '.join(close)}?" if close else f"; it has {', '.join(names[:12]) or 'none'}")
        )
    params = _params(fields.get("Sim.Params", ""), ref=part.ref)
    if entry.kind == "subckt":
        what = f"subcircuit {entry.name}"
        pins = _model_pin_order(part, entry.ports, fields.get("Sim.Pins"), what=what)
        tail = " ".join([entry.name, *(f"{key}={_param_text(value, ref=part.ref, key=key)}" for key, value in params.items())])
        return PartModel("X", entry.ports, pins, tail, include=path)
    kind = _MODEL_TYPES.get(entry.type)
    if kind is None:
        raise DesignError(
            f"{part.ref}: {entry.name} in {path.name} is a .model of type {entry.type}, which a part cannot use "
            f"directly; the types that can are {', '.join(_MODEL_TYPES)} (wrap anything else in a .subckt)"
        )
    letter, model_pins, optional = kind
    instance = _INSTANCE_PARAMS.get(letter, set())
    changed = [key for key in params if key not in instance]
    if changed:
        raise DesignError(
            f"{part.ref}: Sim.Params {', '.join(changed)} would change {entry.name}, a .model in {path.name}; "
            "put the value in the model file (or a copy of the model under a new name). Only instance "
            f"parameters ({', '.join(sorted(instance))}) can be set per part"
        )
    pins = _model_pin_order(part, model_pins, fields.get("Sim.Pins"), what=f"{entry.type} model {entry.name}", optional=optional)
    tail = " ".join([entry.name, *(f"{key}={_param_text(value, ref=part.ref, key=key)}" for key, value in params.items())])
    return PartModel(letter, model_pins, pins, tail, include=path)


_IDEAL = {"R": "resistor", "C": "capacitor", "L": "inductor"}


def _ideal(part: Part, fields: dict[str, str], letter: str, *, inferred: bool = False) -> PartModel:
    params = _params(fields.get("Sim.Params", ""), ref=part.ref)
    key = letter.lower()
    if params:
        if set(params) != {key}:
            raise DesignError(
                f"{part.ref}: KiCad's ideal {_IDEAL[letter]} takes one parameter, {key}= "
                f"(Sim.Params has {', '.join(params)})"
            )
        value = _param_text(params[key], ref=part.ref, key=key)
    else:
        try:
            value = spice_number(parse_value(part.value, kind=letter, ref=part.ref))
        except DesignError as error:
            if not inferred:
                raise
            raise DesignError(
                f"{error}. ({part.ref} has no Sim.* fields, so it simulates the way KiCad reads such a part: "
                f"a two-pin part whose reference starts with {letter} is an ideal {_IDEAL[letter]} of its value. "
                "If it is something else, give it a model with Sim.* fields or properties={'Sim.Enable': '0'})"
            ) from None
    pins = _model_pin_order(part, ("+", "-"), fields.get("Sim.Pins"), what=f"an ideal {_IDEAL[letter]}")
    return PartModel(letter, ("+", "-"), pins, value)


def _source(part: Part, fields: dict[str, str], letter: str, subtype: str) -> PartModel:
    subtype = subtype or "DC"
    allowed = _SOURCE_PARAMS.get(subtype)
    if allowed is None:
        raise DesignError(
            f"{part.ref}: cadgen simulates {letter} sources of Sim.Type {', '.join(_SOURCE_PARAMS)}, not {subtype}; "
            "make the stimulus with the testbench's source(...) instead"
        )
    params = _params(fields.get("Sim.Params", ""), ref=part.ref)
    unknown = [key for key in params if key not in allowed]
    if unknown:
        raise DesignError(
            f"{part.ref}: a {subtype} source's Sim.Params are {', '.join(allowed)}, not {', '.join(unknown)}"
        )
    if subtype == "DC" and not params:
        text = part.value.strip()
        number = parse_value(text, kind=letter, ref=part.ref)
        params = {"ac": spice_number(number)} if text[:2].upper() == "AC" else {"dc": spice_number(number)}
    values = {key: (raw if key == "pwl" else _param_text(raw, ref=part.ref, key=key)) for key, raw in params.items()}

    def get(key: str) -> str:
        return values.get(key, "0")

    if subtype == "DC":
        words = [f"DC {get('dc')}"]
    elif subtype == "SIN":
        words = [f"DC {get('dc')}", f"SIN({get('dc')} {get('ampl')} {get('f')} {get('td')} {get('theta')} {get('phase')})"]
    elif subtype == "PULSE":
        pulse = [get(key) for key in ("y1", "y2", "td", "tr", "tf", "tw", "per")] + ([values["np"]] if "np" in values else [])
        words = [f"PULSE({' '.join(pulse)})"]
    elif subtype == "EXP":
        words = [f"EXP({' '.join(get(key) for key in ('y1', 'y2', 'td1', 'tau1', 'td2', 'tau2'))})"]
    else:
        points = values.get("pwl", "").split()
        numbers = [_param_text(point, ref=part.ref, key="pwl") for point in points]
        if not numbers or len(numbers) % 2:
            raise DesignError(f"{part.ref}: Sim.Params pwl= is time-value pairs, for example pwl=\"0 0 1m 5\"")
        words = [f"PWL({' '.join(numbers)})"]
    if "ac" in values or "ph" in values:
        words.append(f"AC {get('ac')}" + (f" {values['ph']}" if "ph" in values else ""))
    pins = _model_pin_order(part, ("+", "-"), fields.get("Sim.Pins"), what=f"a {letter} source")
    return PartModel(letter, ("+", "-"), pins, " ".join(words))


def _semiconductor(
    part: Part, fields: dict[str, str], *, letter: str, model_pins: tuple[str, ...], card: str, level: int | None, what: str, optional: Sequence[str] = ()
) -> PartModel:
    params = _params(fields.get("Sim.Params", ""), ref=part.ref)
    instance = _INSTANCE_PARAMS[letter]
    model_words = [f"level={level}"] if level is not None else []
    model_words += [f"{key}={_param_text(value, ref=part.ref, key=key)}" for key, value in params.items() if key not in instance]
    instance_words = [f"{key}={_param_text(value, ref=part.ref, key=key)}" for key, value in params.items() if key in instance]
    name = _model_name(part.ref)
    pins = _model_pin_order(part, model_pins, fields.get("Sim.Pins"), what=what, optional=optional)
    model = f".model {name} {card}" + (f"({' '.join(model_words)})" if model_words else "")
    return PartModel(letter, model_pins, pins, " ".join([name, *instance_words]), models=(model,))


def _builtin_model(part: Part, fields: dict[str, str], device: str, subtype: str) -> PartModel:
    ref = part.ref
    if device in ("R", "C", "L"):
        if subtype == "":
            return _ideal(part, fields, device)
        if device == "R" and subtype == "POT":
            return _potentiometer(part, fields)
        raise DesignError(
            f"{ref}: cadgen simulates an ideal {device} (no Sim.Type){' or a potentiometer (Sim.Type=POT)' if device == 'R' else ''}, "
            f"not Sim.Type={subtype}; a behavioural part goes in a .subckt (Sim.Library + Sim.Name)"
        )
    if device in ("V", "I"):
        return _source(part, fields, device, subtype)
    if device == "D":
        if subtype:
            raise DesignError(f"{ref}: a diode (Sim.Device=D) has no Sim.Type; remove {subtype!r}")
        return _semiconductor(part, fields, letter="D", model_pins=("A", "K"), card="D", level=None, what="a diode")
    if device in ("NPN", "PNP"):
        if subtype not in _BJT_TYPES:
            raise DesignError(_needs_type(part, device, subtype, _BJT_TYPES, "GUMMELPOON", "bf=100 is=1e-14"))
        return _semiconductor(
            part, fields, letter="Q", model_pins=("C", "B", "E", "S"), card=device, level=_BJT_TYPES[subtype],
            what=f"{_a(device)} transistor", optional=("S",),
        )
    if device in ("NJFET", "PJFET"):
        if subtype not in _JFET_TYPES:
            raise DesignError(_needs_type(part, device, subtype, _JFET_TYPES, "SHICHMANHODGES", "vto=-2 beta=1m"))
        return _semiconductor(
            part, fields, letter="J", model_pins=("D", "G", "S"), card="NJF" if device == "NJFET" else "PJF",
            level=_JFET_TYPES[subtype], what=_a(device),
        )
    if device in ("NMOS", "PMOS"):
        if subtype not in _MOS_TYPES:
            raise DesignError(_needs_type(part, device, subtype, _MOS_TYPES, "VDMOS", "vto=2 kp=1"))
        if subtype == "VDMOS":
            return _semiconductor(
                part, fields, letter="M", model_pins=("D", "G", "S"), card=f"VDMOS {'NCHAN' if device == 'NMOS' else 'PCHAN'}",
                level=None, what=f"{_a(device)} VDMOS",
            )
        mapped = {token.partition("=")[2].upper() for token in fields.get("Sim.Pins", "").split()}
        if ("B" not in mapped) if "Sim.Pins" in fields else len(part.pins()) < 4:
            raise DesignError(
                f"{ref}: Sim.Type={subtype} is a four-terminal MOSFET (D G S B) and no symbol pin is its bulk B; "
                "map one in Sim.Pins, or simulate a discrete three-pin MOSFET as Sim.Type=VDMOS"
            )
        return _semiconductor(
            part, fields, letter="M", model_pins=("D", "G", "S", "B"), card=device, level=_MOS_TYPES[subtype],
            what=f"{_a(device)} {subtype}",
        )
    if device == "SUBCKT":
        raise DesignError(f"{ref}: Sim.Device=SUBCKT needs the subcircuit: Sim.Library (the file) and Sim.Name (the .subckt)")
    raise DesignError(
        f"{ref}: cadgen does not simulate Sim.Device={device or '(none)'}"
        + (f" Sim.Type={subtype}" if subtype else "")
        + f"; it simulates {_DEVICES}. Put anything else in a .subckt, or leave the part out with "
        "properties={'Sim.Enable': '0'}"
    )


def _needs_type(part: Part, device: str, subtype: str, types: dict, default: str, params: str) -> str:
    if subtype:
        return f"{part.ref}: Sim.Type={subtype} is not {_a(device)} model cadgen simulates; use one of {', '.join(types)}"
    return (
        f"{part.ref} ({part.symbol.lib_id}) is {_a(device)} (Sim.Device={device}) with no model: KiCad's simulator "
        f"reads it as a raw SPICE line and fails too. Give it one: properties={{'Sim.Type': '{default}', "
        f"'Sim.Params': '{params}'}} for SPICE's built-in {device} (set the parameters from the datasheet), "
        f"or the maker's model with properties={{'Sim.Library': 'models/<file>.lib', 'Sim.Name': '<model>'}}"
    )


def _potentiometer(part: Part, fields: dict[str, str]) -> PartModel:
    params = _params(fields.get("Sim.Params", ""), ref=part.ref)
    unknown = [key for key in params if key not in ("r", "pos")]
    if unknown:
        raise DesignError(f"{part.ref}: a potentiometer's Sim.Params are r and pos, not {', '.join(unknown)}")
    r = _param_text(params["r"], ref=part.ref, key="r") if "r" in params else spice_number(parse_value(part.value, kind="R", ref=part.ref))
    words = [f"r={r}"] + ([f"position={_param_text(params['pos'], ref=part.ref, key='pos')}"] if "pos" in params else [])
    name = _model_name(part.ref)
    pins = _model_pin_order(part, ("r0", "wiper", "r1"), fields.get("Sim.Pins"), what="a potentiometer (pins r0 wiper r1)")
    return PartModel("A", ("r0", "wiper", "r1"), pins, name, models=(f".model {name} potentiometer({' '.join(words)})",))


def _no_model(part: Part, fields: dict[str, str]) -> str:
    pins = sorted(part.pins(), key=lambda pin: natural(pin.number))
    names = {pin.name.upper() for pin in pins}
    lib_id = part.symbol.lib_id
    head = f"{part.ref} ({lib_id}, value {part.value!r}) has no SPICE model"
    pin_map = " ".join(f"{pin.number}={pin.name.upper()}" for pin in pins)
    keep_pins = "" if "Sim.Pins" in fields else f", 'Sim.Pins': '{pin_map}'"
    if names == {"A", "K"}:
        if "LED" in (lib_id + part.value).upper():
            hint = (
                f"KiCad's LED symbol names its pins but no model, because the forward voltage depends on the "
                f"colour. Give it one: properties={{'Sim.Device': 'D'{keep_pins}, 'Sim.Params': 'is=6e-19 n=2 rs=2'}} "
                "is about 2.0 V at 20 mA (red); 'is=1.5e-19 n=3 rs=2' about 3.1 V (blue, white). Fit is/n/rs to "
                "the datasheet, or use the maker's model with Sim.Library + Sim.Name"
            )
        else:
            hint = (
                f"give it properties={{'Sim.Device': 'D'{keep_pins}}} for SPICE's default diode, with 'Sim.Params' "
                "from the datasheet (is=, n=, rs=, bv=), or the maker's model with Sim.Library + Sim.Name"
            )
    elif names >= {"B", "C", "E"}:
        kind = "PNP" if "PNP" in lib_id.upper() else "NPN"
        hint = (
            f"give it properties={{'Sim.Device': '{kind}', 'Sim.Type': 'GUMMELPOON'{keep_pins}, "
            "'Sim.Params': 'bf=100 is=1e-14'}} (SPICE's built-in transistor; parameters from the datasheet), "
            "or the maker's model with Sim.Library + Sim.Name"
        )
    elif names >= {"G", "S", "D"} and len(pins) <= 4:
        kind = "PMOS" if "PMOS" in lib_id.upper() or "P-CH" in lib_id.upper() else "NMOS"
        hint = (
            f"give it properties={{'Sim.Device': '{kind}', 'Sim.Type': 'VDMOS', 'Sim.Pins': '{pin_map}', "
            f"'Sim.Params': 'vto={'-' if kind == 'PMOS' else ''}2 kp=1'}} (SPICE's discrete MOSFET; vto is the "
            "threshold, from the datasheet), or the maker's model with Sim.Library + Sim.Name"
        )
    else:
        ports = " ".join(f"{pin.number}=<port>" for pin in pins[:8]) + (" ..." if len(pins) > 8 else "")
        hint = (
            "give it the maker's SPICE model: properties={'Sim.Library': 'models/<file>.lib', 'Sim.Name': "
            f"'<the .subckt>', 'Sim.Pins': '{ports}'}}, mapping each pin number to the .subckt's port"
        )
    return (
        f"{head}: {hint}. KiCad's simulator reads the same fields, so the model works there too. "
        "To leave the part out of simulation instead, give it properties={'Sim.Enable': '0'}"
    )
