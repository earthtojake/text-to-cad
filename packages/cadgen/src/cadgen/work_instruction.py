"""Work instructions: ``@work_instruction``, :class:`Instruction` and the process records.

A work instruction is the HOW of one build: the steps a technician follows to put
one specific assembly together, in order, with the values each step needs. An
engineering drawing states the finished state; a process specification states
the company's rules for a kind of work (fastening, bonding, curing) across
every part. A work instruction applies those rules to one assembly, so the
technician holds exactly the steps for this build and not a hundred pages of
spec.

Every value a step prints -- a torque, an adhesive's mix ratio and pot life, a
cure cycle -- names where it came from: a section of a process spec the user
supplied (:class:`Spec`), a callout on the assembly drawing (:class:`Drawing`),
or something the user said (:class:`Stated`). Nothing here has a default value
for any of them. A value nobody stated prints as a captioned blank, ``NOT
STATED``, and the run lists it, so a draft says exactly what engineering still
owes the floor; so does a value written into free text (a step's title, an
instruction, a notice, a sequence, an inspection: :data:`VALUE_UNITS`) that
cites no source. A released instruction (``status="released"``) refuses to be
written with one.

Usage (every document and value here is a placeholder: a real one is copied
from the section of the user's document it cites)::

    from bracket_assembly import bracket_assembly        # the assembly's model
    from cadgen.work_instruction import work_instruction, Instruction, Spec, Drawing, Torque

    FASTENING = Spec("PS-XXXX", "<fastening spec title>", revision="<rev>")
    DWG = Drawing("DWG-ZZZZ", revision="<rev>")

    @work_instruction(out="../PDF/bracket_assembly_wi.pdf")
    def bracket_assembly_wi():
        wi = Instruction(bracket_assembly(),           # the document the model's call returns
                         title="BRACKET ASSEMBLY", number="WI-0001", revision="A", drawing=DWG)
        wi.step("Place the base plate on the fixture", install=["base_plate"])
        wi.step("Fasten the bracket to the base plate", install=["bracket"]).fasten(
            "<screw part number>", qty=4,
            torque=Torque(1, 2, unit="in-lbf", per=FASTENING.at("<table>")))  # <low>, <high> as stated
        return wi

    if __name__ == "__main__":
        bracket_assembly_wi()

How much paperwork the pages carry is the instruction's ``rigor``: a
``prototype`` build order, ``production`` (the default) traceability, or
``controlled`` QA hold points for audited work. Its ``emphasis`` is ``visual``
(a figure per step) or ``process`` (text-led, with a map of which steps apply
which document). A company's own template or example becomes a :class:`Format`
that renames or replaces the layout's title, columns, numbering and sign-offs.

Running the script writes one PDF at ``out``: front pages (documents, parts,
materials, equipment, open items, approvals) and the procedure as a ruled
table, one row per step with its values, a figure of the assembly as it stands
after the step (line art, the step's own parts filled, parts still to come left
out), the blanks the floor fills in and a column per sign-off.

The assembly is a model's document (what calling the model returns: the engine
builds it, or replays it) or an ``.xbf`` or ``.step`` file. Its parts are named
as the engine names them (``cadgen.engine.refs``), so a part or face ref copied
from ``cadgen inspect`` or the viewer is one ``install=`` and ``surfaces=`` take,
and the figures are the engine's snapshots of that document.

Like ``@eng_drawing`` this is a document over a document, run in the script's
own process, with no CLI: the script is the program. Import discipline: nothing
here pulls in matplotlib or the CAD kernel at module scope.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

__all__ = [
    "work_instruction", "Instruction", "Step",
    "Spec", "Drawing", "Datasheet", "Stated", "Source", "Cited",
    "Torque", "Material", "Adhesive", "Cure",
    "Format", "TORQUE_UNITS", "CAMERAS", "PAGE_SIZES", "STATUSES", "SOURCE_KINDS", "NOTICES",
    "RIGORS", "EMPHASES", "NUMBERINGS", "FRAMES", "VALUE_UNITS", "Unspecified",
]

TORQUE_UNITS = ("in-lbf", "ft-lbf", "N-m")
CAMERAS = ("iso", "front", "back", "left", "right", "top", "bottom")
PAGE_SIZES = ("LETTER", "A4")
RIGORS = ("prototype", "production", "controlled")
EMPHASES = ("visual", "process")
NUMBERINGS = ("sequential", "by-ten")
FRAMES = ("step", "assembly")
NOTICES = ("WARNING", "CAUTION", "NOTE")
STATUSES = ("draft", "released")
NOT_STATED = "NOT STATED"
UNNAMED = "(unnamed)"  # a part or subassembly with no label, as the pages name it


def _text(name: str, value, *, required: bool = True) -> str | None:
    """A printed field: a non-blank string, or None where the field may be absent."""
    if value is None:
        if required:
            raise TypeError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    value = " ".join(value.split())
    if not value:
        raise ValueError(f"{name} must not be blank: leave it out (None) to print it as {NOT_STATED}")
    return value


def _lines(name: str, values) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} takes a list of lines, not one string: {name}=[{values!r}]")
    return [_text(f"{name} line", value) for value in values]


def _one_of(name: str, value, allowed: Sequence[str]) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}; got {value!r}")
    return value


# --- where a value comes from ------------------------------------------------

SOURCE_KINDS = ("spec", "drawing", "datasheet", "stated")


@dataclass(frozen=True)
class Source:
    """Where one value comes from: made by :meth:`Spec.at`, :meth:`Drawing.at`,
    :meth:`Datasheet.at` or :func:`Stated`. ``kind`` is one of :data:`SOURCE_KINDS`,
    and a document and (but for ``stated``) the place in it are required."""

    kind: str
    document: str
    where: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        _one_of("Source kind", self.kind, SOURCE_KINDS)
        object.__setattr__(self, "document", _text("Source document", self.document))
        if self.kind != "stated":
            object.__setattr__(self, "where", _text(f"the place in {self.document}", self.where or None))

    def cite(self) -> str:
        if self.kind == "stated":
            return self.document
        if self.kind == "drawing":
            return f"{self.document}, {self.where} (drawing callout)"
        return f"{self.document} {self.where}" if self.kind == "spec" else f"{self.document}, {self.where}"


@dataclass(frozen=True)
class Spec:
    """A company process specification as the user supplied it: its number, title
    and revision. ``spec.at("4.2, Table 3")`` is a :class:`Source` naming the
    section a value was read from."""

    number: str
    title: str
    revision: str

    def __post_init__(self) -> None:
        for name in ("number", "title", "revision"):
            object.__setattr__(self, name, _text(f"Spec {name}", getattr(self, name)))

    @property
    def name(self) -> str:
        return f"{self.number} Rev {self.revision}"

    def at(self, section: str) -> Source:
        return Source("spec", self.name, f"\u00a7{_text('Spec.at section', section)}", self.title)


@dataclass(frozen=True)
class Drawing:
    """The assembly drawing. ``drawing.at("note 4")`` is a :class:`Source` for a
    value a drawing callout states -- a deviation from the general spec."""

    number: str
    revision: str
    title: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", _text("Drawing number", self.number))
        object.__setattr__(self, "revision", _text("Drawing revision", self.revision))
        object.__setattr__(self, "title", _text("Drawing title", self.title or None, required=False) or "")

    @property
    def name(self) -> str:
        return f"{self.number} Rev {self.revision}"

    def at(self, callout: str) -> Source:
        return Source("drawing", self.name, _text("Drawing.at callout", callout), self.title)


@dataclass(frozen=True)
class Datasheet:
    """A manufacturer's technical data sheet the user supplied, for a product the
    spec defers to (an adhesive's mix ratio and pot life, a prepreg's cure).
    ``revision`` is as the sheet prints it -- a revision letter or a date."""

    product: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "product", _text("Datasheet product", self.product))
        object.__setattr__(self, "revision", _text("Datasheet revision", self.revision))

    @property
    def name(self) -> str:
        return f"{self.product} datasheet, {self.revision}"

    def at(self, section: str) -> Source:
        return Source("datasheet", self.name, _text("Datasheet.at section", section), "Manufacturer's data sheet")


def Stated(by: str, *, on: str) -> Source:  # noqa: N802 - reads as the record it makes
    """A value the user stated themself: who said it and the date (``on``, as
    written, e.g. ``"2026-10-23"``). Use it only for what the person actually
    said; a value read from a document cites that document instead."""
    return Source("stated", f"stated by {_text('Stated by', by)}, {_text('Stated on', on)}")


def _source(owner: str, per) -> Source:
    if not isinstance(per, Source):
        raise TypeError(
            f"{owner} needs per=: where the value comes from -- Spec(...).at(section), "
            "Drawing(...).at(callout), Datasheet(...).at(section) or Stated(by, on=date). "
            "A value with no source is not written down."
        )
    return per


@dataclass(frozen=True)
class Cited:
    """One field of a record that comes from a different document than the rest:
    ``Adhesive(..., mix=Cited("100:17 by weight", per=TDS.at("Mixing")), per=SPEC.at("5.1"))``."""

    text: str
    _: KW_ONLY
    per: Source | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _text("Cited text", self.text))
        _source("Cited", self.per)


@dataclass(frozen=True)
class Unspecified:
    """A value that does not exist, as opposed to one nobody has stated yet: the
    user says there is no torque for this joint and says what to do instead
    (``Unspecified("snug, no torque specified", per=Stated("A. Zhou", on=...))``).
    It prints the text with its source and is not an open item."""

    text: str
    _: KW_ONLY
    per: Source | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _text("Unspecified text", self.text))
        _source("Unspecified", self.per)


# What makes free text a value: a number followed by one of these units. A step's title, an
# instruction, a notice, a tightening sequence or an inspection that states one cites where it comes
# from (``per=``, or ``Cited``) as a Torque does; one that does not leaves its source an open item, so
# a released instruction carries no value without a source. A one-letter unit is matched as written
# (``N`` is a newton, ``n`` is not), the rest in any case; a bare ``in`` is an inch only after a
# decimal or a fraction (``0.25 in``), since ``pin 2 in place`` states no length.
VALUE_UNITS = (
    "in-lbf", "in-lb", "in-lbs", "lbf-in", "ft-lbf", "ft-lb", "ft-lbs", "lbf-ft", "N-m", "N\u00b7m", "Nm", "cN-m",
    "kgf-cm", "N", "kN", "lbf", "lb", "lbs", "kg", "g", "oz",
    "mm", "cm", "m", "\u00b5m", "um", "in.", "inch", "inches", '"', "ft", "mil", "mils", "thou",
    "\u00b0F", "\u00b0C", "\u00b0", "F", "C", "deg", "degrees", "turn", "turns",
    "psi", "psig", "bar", "kPa", "MPa", "Pa",
    "s", "sec", "second", "seconds", "min", "minute", "minutes", "h", "hr", "hrs", "hour", "hours", "day", "days",
    "mL", "ml", "L", "cc", "%", "rpm",
)
_NUMBER = r"(?<![\w.])\d+(?:[.,]\d+)?(?:/\d+)?"
_UNIT = "|".join(re.escape(unit) if len(unit) == 1 else f"(?i:{re.escape(unit)})"
                 for unit in sorted(VALUE_UNITS, key=len, reverse=True))
_VALUE = re.compile(
    rf"{_NUMBER}(?:\s*(?:-|\u2013|to)\s*\d+(?:[.,]\d+)?(?:/\d+)?)?\s*(?:{_UNIT})(?![\w-])"
    r"|(?<![\w.])\d*[./]\d+\s*in(?![\w-])"  # 0.25 in, 1/4 in
    r"|(?<![\w.:])\d+:\d+(?![\w:])"  # a ratio, 100:17
)


def _owed(text: str, per: Source | None) -> list[str]:
    """The source free text owes: of each value it states (``VALUE_UNITS``), where it cites none."""
    found = [] if per is not None else [match.group(0) for match in _VALUE.finditer(text)]
    return [f"source of {', '.join(found)}"] if found else []


def _cited(name: str, value) -> tuple[str | None, Source | None]:
    """Plain text, or text that names where it came from."""
    if isinstance(value, Cited):
        return value.text, value.per
    return _text(name, value, required=False), None


# --- process records ---------------------------------------------------------


@dataclass(frozen=True)
class Torque:
    """A torque, ``Torque(20, 25, unit="in-lbf", per=...)`` for a range or
    ``Torque(30, unit="N-m", per=...)`` for one value. The unit is one of
    :data:`TORQUE_UNITS`, and named (``unit=``) so a value is never read as one;
    nothing is converted or rounded."""

    low: float
    high: float | None = None
    _: KW_ONLY
    unit: str = ""  # required: refused empty below, after a unit given as ``high`` is named as one
    per: Source | None = None

    def __post_init__(self) -> None:
        if isinstance(self.high, str):  # Torque(30, "N-m"): the unit given where the high end goes
            raise TypeError(f"Torque high must be a number, got {self.high!r}; the unit is named: "
                            f"Torque({self.low!r}, unit={self.high!r}), or Torque(low, high, unit=...) for a range")
        for name in ("low", "high"):
            value = getattr(self, name)
            if value is None and name == "high":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Torque {name} must be a positive number, got {value!r}")
        if self.high is not None and self.high < self.low:
            raise ValueError(f"Torque high ({self.high}) is below low ({self.low})")
        _one_of("Torque unit", self.unit, TORQUE_UNITS)
        _source("Torque", self.per)

    def text(self) -> str:
        span = _num(self.low) if self.high is None or self.high == self.low else f"{_num(self.low)}\u2013{_num(self.high)}"
        return f"{span} {self.unit}"


def _num(value: float) -> str:
    """The number as it was given: 12.345678 stays 12.345678, and 40.0 prints 40."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


@dataclass(frozen=True)
class _Record:
    """A process record: its fields are printed text (or :class:`Cited` text), a
    required one left out prints as NOT STATED. Subclasses name REQUIRED and OPTIONAL."""

    REQUIRED = ()
    OPTIONAL = ()

    def __post_init__(self) -> None:
        kind = type(self).__name__
        object.__setattr__(self, "name", _text(f"{kind} name", self.name))
        for key in self.REQUIRED + self.OPTIONAL:
            value = getattr(self, key)
            if not isinstance(value, Cited):
                object.__setattr__(self, key, _text(f"{kind} {key}", value, required=False))
        _source(kind, self.per)

    def fields(self) -> list[tuple[str, str | None, Source | None]]:
        """(caption, text, source) to print; a required field's None is NOT STATED."""
        rows = []
        for key in self.REQUIRED + tuple(k for k in self.OPTIONAL if getattr(self, k) is not None):
            value = getattr(self, key)
            if isinstance(value, Cited):
                rows.append((key.replace("_", " "), value.text, value.per))
            else:
                rows.append((key.replace("_", " "), value, self.per if value is not None else None))
        return rows

    def missing(self) -> list[str]:
        return [key.replace("_", " ") for key in self.REQUIRED if getattr(self, key) is None]


@dataclass(frozen=True)
class Material(_Record):
    """A consumable a step uses with no process record of its own: a
    threadlocker, a sealant, a primer. ``note`` is how it is applied, as stated."""

    name: str
    _: KW_ONLY
    per: Source | None = None
    note: str | Cited | None = None
    OPTIONAL = ("note",)


@dataclass(frozen=True)
class Adhesive(_Record):
    """A bonding process record: surface prep, mixing, pot life and cure, each as
    the spec states it -- or, where the spec defers to the manufacturer, as
    :class:`Cited` text from the :class:`Datasheet`."""

    name: str
    _: KW_ONLY
    prep: str | Cited | None = None
    mix: str | Cited | None = None
    pot_life: str | Cited | None = None
    cure: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("prep", "mix", "pot_life", "cure")


@dataclass(frozen=True)
class Cure(_Record):
    """A cure cycle: ramp, hold, pressure and cool-down as the spec states them."""

    name: str
    _: KW_ONLY
    cycle: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("cycle",)


# --- the layout --------------------------------------------------------------


@dataclass(frozen=True)
class Format:
    """A company's own layout, read from a template or an example work instruction
    the user supplied. Give only what that document shows; a field left out keeps
    what the instruction's ``rigor`` lays out.

    ``title`` is what the document calls itself (``"ASSEMBLY PROCEDURE"``,
    ``"TRAVELER"``), ``company`` is printed in every header, ``step_label`` heads
    the step column (``"OP"``, ``"SEQ"``), ``numbering`` is ``sequential`` (1, 2,
    3) or ``by-ten`` (10, 20, 30), ``stamps`` are the sign-off columns left to
    right (``("MECH", "INSP")``), ``approvals`` the signature roles on the front
    pages, ``instruction_label`` heads the instruction column (``"OPERATION
    DESCRIPTION"``), and ``figures=False`` leaves out the figure column."""

    _: KW_ONLY
    title: str | None = None
    company: str | None = None
    step_label: str | None = None
    numbering: str | None = None
    stamps: Sequence[str] | None = None
    approvals: Sequence[str] | None = None
    instruction_label: str | None = None
    figures: bool | None = None

    def __post_init__(self) -> None:
        if self.figures is not None and not isinstance(self.figures, bool):
            raise TypeError("Format figures is True or False: whether the step table has a figure column")
        for name in ("title", "company", "step_label", "instruction_label"):
            object.__setattr__(self, name, _text(f"Format {name}", getattr(self, name), required=False))
        if self.numbering is not None:
            _one_of("Format numbering", self.numbering, NUMBERINGS)
        if self.stamps is not None:
            stamps = tuple(_lines("Format stamps", self.stamps))
            if not stamps:
                raise ValueError("Format stamps needs at least one sign-off column")
            object.__setattr__(self, "stamps", stamps)
        if self.approvals is not None:
            object.__setattr__(self, "approvals", tuple(_lines("Format approvals", self.approvals)))


@dataclass(frozen=True)
class Layout:
    """What the pages carry, resolved from a ``rigor`` and a :class:`Format`."""

    title: str
    company: str
    step_label: str
    numbering: str
    stamps: tuple[str, ...]
    approvals: tuple[str, ...]
    instruction_label: str
    figures: bool
    traceability: bool  # work order, serial, lot and expiry, and the actual-reading blanks
    calibration: bool  # equipment with ID and calibration-due blanks
    holds: bool  # an inspection is a hold point in the last sign-off column
    close_out: bool
    cite_inspections: bool  # an inspection criterion with no source is an open item


# What each rigor lays out. A prototype is a build order to follow; production adds
# the traceability a shop keeps; controlled (aerospace, medical) adds QA hold
# points, calibration and a cited criterion for every inspection.
RIGOR_LAYOUTS = {
    "prototype": Layout("WORK INSTRUCTION", "", "STEP", "sequential", ("DONE",), (), "INSTRUCTION", True,
                        traceability=False, calibration=False, holds=False, close_out=False,
                        cite_inspections=False),
    "production": Layout("WORK INSTRUCTION", "", "STEP", "sequential", ("TECH",), ("Prepared by", "Approved by"),
                         "INSTRUCTION", True,
                         traceability=True, calibration=True, holds=False, close_out=True,
                         cite_inspections=False),
    "controlled": Layout("WORK INSTRUCTION", "", "STEP", "sequential", ("TECH", "QA"),
                         ("Prepared by", "Reviewed by", "Approved by"), "INSTRUCTION", True,
                         traceability=True, calibration=True, holds=True, close_out=True,
                         cite_inspections=True),
}


def _layout(rigor: str, house: Format | None) -> Layout:
    base = RIGOR_LAYOUTS[_one_of("rigor", rigor, RIGORS)]
    if house is None:
        return base
    if not isinstance(house, Format):
        raise TypeError("format= takes a Format(...) read from the user's template or example")
    changes = {name: getattr(house, name) for name in ("title", "company", "step_label", "numbering", "stamps",
                                                        "approvals", "instruction_label", "figures")
               if getattr(house, name) is not None}
    from dataclasses import replace

    return replace(base, **changes)


# --- steps -------------------------------------------------------------------

# What the floor writes down in each kind of operation: the actual reading and the
# lot, time and equipment it was made with. Blanks to fill in, not values anyone owes:
# a NOT STATED field is engineering's; these are the technician's. The tools a step
# uses (a torque wrench, an oven) are listed once, on the front pages, with their
# calibration blanks.
RECORDS = {
    "fasten": ("Actual torque",),
    "bond": ("Prepared at", "Adhesive lot", "Expiry", "Mixed at", "Mated at"),
    "cure": ("Oven / autoclave ID", "Start", "End", "Chart no."),
}
# Equipment a kind of operation implies, for the front pages' equipment list: a torque
# wrench only where a torque is stated.
EQUIPMENT = {"fasten": "Torque wrench", "cure": "Oven / autoclave"}
# Past this many fasteners one actual-torque blank stands for them all.
TORQUE_BLANKS = 8


@dataclass(frozen=True)
class _Line:
    """One printed row: a ``None`` value is NOT STATED, and so is a ``None``
    source where one is owed (an inspection criterion with no document)."""

    caption: str
    value: str | None
    source: Source | None = None
    cite: bool = False


@dataclass
class _Op:
    kind: str
    lines: list[_Line]
    missing: list[str] = field(default_factory=list)
    record: str | None = None  # an inspection's measured-value caption
    surfaces: tuple[tuple[str, str], ...] = ()  # (face ref, the leaf occurrence it is on)
    records: tuple[str, ...] | None = None  # the floor's blanks, where not RECORDS[kind]
    equipment: bool = True  # whether it implies EQUIPMENT[kind]


class Step:
    """One step: a title, the parts it installs, and its operations in order.
    Made by :meth:`Instruction.step`; every method returns the step, so they chain."""

    def __init__(self, instruction: "Instruction", number: int, title: str, install: tuple[str, ...],
                 camera: str | None, picture: bool, operation: int | None,
                 units: tuple[tuple[str, str], ...] = (), frame: str = "step") -> None:
        self._instruction = instruction
        self.number = number
        self.label = str(number * 10 if instruction.layout.numbering == "by-ten" else number)
        self.title = title
        self.install = install  # every leaf occurrence, for the figure
        self.units = units  # (ref, name) at the level the step names them: a subassembly is one
        self.frame = frame
        self.camera = camera
        self.picture = picture
        self.operation = operation
        self.ops: list[_Op] = []
        self.notices: list[_Line] = []  # captioned WARNING, CAUTION or NOTE
        # What the step's title and notices owe, as (where, what): a title cites nothing, so a value in
        # one is owed until it moves into the operation that cites it.
        self.missing: list[tuple[str, str]] = [("title", name) for name in _owed(title, None)]
        self.hold = False
        self.record: str | None = None

    def sources(self) -> Iterator[Source]:
        """Every source the step cites, in the order it prints them."""
        for notice in self.notices:
            if notice.source is not None:
                yield notice.source
        for op in self.ops:
            for line in op.lines:
                if line.source is not None:
                    yield line.source

    def _add(self, op: _Op) -> "Step":
        self.ops.append(op)
        return self

    def instruct(self, text: str, *, per: Source | None = None) -> "Step":
        """A plain instruction, in the words the user gave, or as the cited document
        states it (``per=``): a clamping rule, a witness coupon, a lubrication step. Text
        that states a value (:data:`VALUE_UNITS`) with no ``per=`` leaves its source an open item."""
        if per is not None:
            _source("instruct", per)
        text = _text("instruct text", text)
        owed = _owed(text, per)
        return self._add(_Op("instruct", [_Line("", text, per, cite=bool(owed))], missing=owed))

    def not_stated(self, what: str) -> "Step":
        """Something this step needs that nobody has stated yet -- a retention
        method, a lubricant: it prints NOT STATED and is an open item."""
        what = _text("not_stated what", what)
        return self._add(_Op("ask", [_Line(what, None)], missing=[what.lower()]))

    def _notice(self, kind: str, text: str, per: Source | None) -> "Step":
        if per is not None:
            _source(kind.lower(), per)
        text = _text(f"{kind.lower()} text", text)
        owed = _owed(text, per)
        self.notices.append(_Line(kind, text, per, cite=bool(owed)))
        self.missing += [(kind.lower(), name) for name in owed]
        return self

    def warning(self, text: str, *, per: Source | None = None) -> "Step":
        """A WARNING (harm to people), boxed above the step it governs. A notice that states a
        value (:data:`VALUE_UNITS`) cites it (``per=``), or its source is an open item."""
        return self._notice("WARNING", text, per)

    def caution(self, text: str, *, per: Source | None = None) -> "Step":
        """A CAUTION (harm to the hardware), boxed above the step it governs."""
        return self._notice("CAUTION", text, per)

    def note(self, text: str, *, per: Source | None = None) -> "Step":
        """A NOTE, boxed above the step."""
        return self._notice("NOTE", text, per)

    def fasten(self, hardware: str, *, qty: int | None = None, torque: Torque | Unspecified | None = None,
               locking: Material | None = None, sequence: str | Cited | None = None,
               surfaces: Iterable[str] = ()) -> "Step":
        """Install threaded hardware. ``torque=None`` prints NOT STATED: a threaded
        joint with no stated torque is an open item, not a default. Where the
        user says no torque exists, ``torque=Unspecified(what to do, per=...)``.
        ``surfaces`` are the faces the hardware goes into (``bracket/face 3``), marked on
        the figure: hardware the model does not carry is drawn nowhere else. A ``sequence``
        that states a value (:data:`VALUE_UNITS`) is ``Cited(text, per=...)``, or its source is
        an open item."""
        hardware = _text("fasten hardware", hardware)
        if qty is not None and (isinstance(qty, bool) or not isinstance(qty, int) or qty < 1):
            raise ValueError(f"fasten qty must be a positive integer, got {qty!r}")
        if torque is not None and not isinstance(torque, (Torque, Unspecified)):
            raise TypeError("fasten torque= takes a Torque(...), an Unspecified(...) or None")
        if locking is not None and not isinstance(locking, Material):
            raise TypeError("fasten locking= takes a Material(...)")
        if isinstance(torque, Torque):
            value = torque.text()
            n = qty or 1
            records = ("Actual torque",) if n == 1 or n > TORQUE_BLANKS else \
                tuple(f"Actual torque {i}" for i in range(1, n + 1))
        else:
            value, records = (torque.text if torque else None), ("Actual torque",) if torque is None else ()
        lines = [_Line("Hardware", f"{hardware}{f', qty {qty}' if qty else ''}"),
                 _Line("Torque", value, torque.per if torque else None)]
        if locking is not None:
            self._instruction._use(locking)
            lines += [_Line("Locking", locking.name, locking.per)]
            lines += [_Line(caption.capitalize(), value, source) for caption, value, source in locking.fields()]
        missing = [] if torque else ["torque"]
        if sequence is not None:
            text, source = _cited("fasten sequence", sequence)
            owed = _owed(text, source)
            lines.append(_Line("Sequence", text, source, cite=bool(owed)))
            missing += owed
        return self._add(_Op("fasten", lines, missing=missing, records=records,
                             equipment=isinstance(torque, Torque), surfaces=self._faces(surfaces)))

    def _record(self, kind: str, record, cls, label: str, surfaces=()) -> "Step":
        if record is None:
            return self._add(_Op(kind, [_Line(label, None)], missing=[label.lower()],
                                 surfaces=self._faces(surfaces)))
        if not isinstance(record, cls):
            raise TypeError(f"{kind}() takes a {cls.__name__}(...) or None, got {type(record).__name__}")
        lines = [_Line(label, record.name, record.per)]
        lines += [_Line(caption.capitalize(), value, source) for caption, value, source in record.fields()]
        if kind == "bond":  # a consumable the kit list carries; a cure is not
            self._instruction._use(record)
        return self._add(_Op(kind, lines, missing=record.missing(), surfaces=self._faces(surfaces)))

    def bond(self, adhesive: Adhesive | None, *, surfaces: Iterable[str] = ()) -> "Step":
        """Bond with an adhesive. ``surfaces`` are face refs (``bracket/face 3``) marked
        on the step's picture; ``None`` for the adhesive prints NOT STATED."""
        return self._record("bond", adhesive, Adhesive, "Adhesive", surfaces)

    def cure(self, cure: Cure | None) -> "Step":
        """A cure cycle; ``None`` prints NOT STATED."""
        return self._record("cure", cure, Cure, "Cure")

    def apply(self, material: Material, *, surfaces: Iterable[str] = ()) -> "Step":
        """Apply a consumable (sealant, primer, threadlocker) with no record of its own."""
        if not isinstance(material, Material):
            raise TypeError("apply() takes a Material(...)")
        self._instruction._use(material)
        lines = [_Line("Apply", material.name, material.per)]
        lines += [_Line("How", value, source) for _caption, value, source in material.fields()]
        return self._add(_Op("apply", lines, surfaces=self._faces(surfaces)))

    def _faces(self, refs) -> tuple[tuple[str, str], ...]:
        """Each surface ref resolved on the assembly to exactly one face: (its canonical ref, the
        part it is on)."""
        if isinstance(refs, (str, bytes)):
            raise TypeError(f"surfaces takes a sequence of face refs, not one string: surfaces=({refs!r},)")
        out = []
        for ref in refs:
            ref = _text("surface ref", ref)
            try:
                face, part = self._instruction.scene.face(ref)
            except ValueError as exc:  # a RefError among them
                raise ValueError(f"step {self.label}: {ref} is not one face of {self._instruction.source_name}: "
                                 f"{exc}") from None
            out.append((face, part))
        return tuple(out)

    def inspect(self, text: str, *, per: Source | None = None, record: str | None = None) -> "Step":
        """An inspection hold point: the step is not complete until QA stamps it.
        The criterion cites where it comes from: in a ``controlled`` instruction,
        or where it states a value (:data:`VALUE_UNITS`), with ``per=None`` its
        source prints NOT STATED and is an open item. ``record`` captions a blank
        for the measured value (``"Pin height, mm"``)."""
        if per is not None:
            _source("inspect", per)
        layout = self._instruction.layout
        self.hold = self.hold or layout.holds
        text = _text("inspect text", text)
        # A controlled instruction owes every criterion its source; any other, a criterion stating a value.
        missing = (["criterion source"] if per is None else []) if layout.cite_inspections else _owed(text, per)
        op = _Op("inspect", [_Line("Inspect", text, per, cite=layout.cite_inspections or bool(missing))],
                 missing=missing)
        op.record = _text("inspect record", record, required=False)
        return self._add(op)


class _Occurrence:
    """One occurrence of the assembly: its canonical ref in the engine's grammar (``bracket``,
    ``pin.2``, ``arm/pin``), its label, the occurrences below it (none for a part) and, a part's,
    its shape placed in the document's frame."""

    def __init__(self, ref: str, label: str, node: Any, shape: Any) -> None:
        self.ref, self.label, self.node, self._shape = ref, label, node, shape
        self.children: list[_Occurrence] = []

    def shape(self) -> Any:
        return self._shape


class _Scene:
    """The assembly's occurrence tree, read from the shape the document holds and named as the
    engine names it (``cadgen.engine.refs``), so a ref here is a ref ``cadgen inspect``, the
    viewer and a snapshot's ``hidden`` read the same way."""

    def __init__(self, shape: Any, source: str) -> None:
        from build123d import Location

        from cadgen.engine import refs

        self.source = source
        shapes: list[Any] = []

        def entry(node: Any, at: Any) -> dict[str, Any]:
            children = list(getattr(node, "children", ()) or ())
            index = len(shapes)
            shapes.append(None if children else node.moved(at))  # a part, placed where its parents put it
            found: dict[str, Any] = {"name": node.label or "", "index": index}
            if children:
                placed = at * node.location
                found["children"] = [entry(child, placed) for child in children]
            else:
                found["prototype"] = index
            return found

        tree = entry(shape, Location())
        # The structure a served document has, as far as refs read it: no element names (those are
        # the engine's document's own: ``face`` asks it for a named face).
        self.structure = {"tree": tree, "prototypes": [{} for _shape in shapes]}
        self.root = refs.structure_tree(self.structure)
        self._shapes = shapes
        self._by_index: dict[int, _Occurrence] = {}

        def build(node: Any) -> _Occurrence:
            made = _Occurrence(refs.owner_text(self.root, node), node.label, node, shapes[node.payload["index"]])
            self._by_index[node.payload["index"]] = made
            made.children = [build(child) for child in node.children]
            return made

        self.top = build(self.root)

    def leaves(self) -> list[_Occurrence]:
        return [self._by_index[node.payload["index"]] for node in self.root.parts()]

    def parts_under(self, occurrence: _Occurrence) -> list[_Occurrence]:
        return [self._by_index[node.payload["index"]] for node in occurrence.node.parts()]

    def occurrences(self, ref: str) -> list[_Occurrence]:
        """What a part or assembly ref names (the engine's grammar); ``RefError`` where it names
        nothing, several things where it names one, or an element."""
        from cadgen.engine import refs

        hits = refs.resolve_structure(self.structure, ref)
        if any(hit.kind is not None for hit in hits):
            raise refs.RefError(f"{ref!r} names a {hits[0].kind}; install takes parts and subassemblies")
        return [self._by_index[hit.node.payload["index"]] for hit in hits]

    def face(self, ref: str) -> tuple[str, str]:
        """(the canonical ref of the one face ``ref`` names, the ref of the part it is on). A face
        named by its ordinal (``bracket/face 3``) is resolved here; one named by its name
        (``bracket/f:...``), which only the engine's document holds, is asked of the engine."""
        from cadgen.engine import refs

        _file, selectors = refs.parse(ref)
        if len(selectors) != 1 or selectors[0].kind != "face":
            raise ValueError("surfaces takes face refs such as 'bracket/face 3'")
        if isinstance(selectors[0].element, str):
            import cadgen

            facts = cadgen.inspect(self.source, ref)
            facts = facts[0] if isinstance(facts, list) else facts
            node = next((node for node in self.root.parts() if refs.path_text(self.root, node) == facts["path"]), None)
            if node is None:
                raise ValueError(f"the engine's document has no part {facts['path']!r} here")
            part, ordinal = self._by_index[node.payload["index"]], int(facts["ordinal"])
        else:
            (hit,) = refs.resolve_structure(self.structure, ref)
            part, ordinal = self._by_index[hit.node.payload["index"]], int(hit.ordinal)
            count = len(_faces(part.shape()))
            if ordinal > count:
                raise ValueError(f"{part.ref} has no face {ordinal} (it has {count})")
        return f"{part.ref}/face {ordinal}", part.ref

    def face_shape(self, ref: str) -> Any:
        """The placed face a canonical face ref (``face``'s) names."""
        part, _slash, element = ref.rpartition("/")
        (found,) = self.occurrences(part)
        return _faces(found.shape())[int(element.split()[-1]) - 1]


def _faces(shape: Any) -> list[Any]:
    """A part's faces by their ``TopExp.MapShapes`` ordinals, the ones its refs number."""
    from build123d import Face
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    found = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, found)
    return [Face(found.FindKey(index)) for index in range(1, found.Extent() + 1)]


def _assembly(assembly: Any) -> tuple[Any, str, str]:
    """What an Instruction reads: (the assembly's shape, the document the engine knows it by --
    a model's id or the file's path -- and the name the pages print)."""
    from cadgen.engine.api import Document

    if isinstance(assembly, Document):
        return assembly.shape, assembly.id, assembly.name
    if isinstance(assembly, (str, Path)):
        path = Path(assembly).expanduser().resolve()
        suffix = path.suffix.lower()
        if suffix not in (".xbf", ".step", ".stp"):
            raise ValueError(f"Instruction takes a model's document (what calling the model returns) or an "
                             f"assembly's .xbf or .step, got {str(assembly)!r}")
        if not path.is_file():
            raise FileNotFoundError(f"no document at {path}")
        from cadgen import read_step, read_xbf

        return (read_xbf if suffix == ".xbf" else read_step)(path), str(path), path.name
    raise TypeError(f"Instruction takes a model's document (what calling the model returns) or an assembly's "
                    f".xbf or .step, got {type(assembly).__name__}")


class Instruction:
    """The work instruction for one assembly: a model's document, or an assembly's .xbf or .step.

    ``status`` is ``draft`` (the default: every page says DRAFT, and NOT STATED
    values and parts no step installs are listed) or ``released`` (either one is
    refused). ``size`` is one of :data:`PAGE_SIZES` (US Letter by default),
    ``camera`` one of :data:`CAMERAS` for every step's picture (a step may name
    its own). ``pictures=False`` writes the document with no pictures, so
    the engine draws nothing.

    ``rigor`` is one of :data:`RIGORS`: ``prototype`` (a build order to follow:
    figures, a done column, no paperwork), ``production`` (the default: tech
    stamps, work order, serial, lot and actual-reading blanks, calibration,
    approvals, a close-out) or ``controlled`` (aerospace, medical: production
    plus a QA column, inspections as hold points and a cited criterion for every
    inspection). ``emphasis`` is ``visual`` (a figure per step) or ``process``
    (text-led steps, no figure column, and a table of which steps apply which
    section of which document). ``format`` is the company's own layout as a
    :class:`Format`, read from a template or example the user supplied; it
    overrides what the rigor lays out, and nothing else.

    The front pages carry ``scope`` (a sentence: what this instruction builds and
    when it applies), ``safety`` (the PPE and hazards the user's documents state;
    a line that states a value, :data:`VALUE_UNITS`, is ``Cited(text, per=...)``
    or its source is an open item, as in a step),
    ``tools`` (fixtures and tooling the user names, beside the equipment the steps
    imply) and ``revisions`` (``(rev, date, change)`` rows), each only if given.
    """

    def __init__(self, assembly: Any, *, title: str, number: str, revision: str,
                 part_number: str = "", drawing: Drawing | None = None, author: str = "",
                 status: str = "draft", size: str = "LETTER", camera: str = "iso", pictures: bool = True,
                 scope: str | Cited = "", safety: Sequence[str | Cited] = (), tools: Sequence[str] = (),
                 revisions: Sequence[tuple[str, str, str]] = (), rigor: str = "production",
                 emphasis: str = "visual", format: Format | None = None) -> None:  # noqa: A002
        shape, self.source, self.source_name = _assembly(assembly)
        self.title = _text("title", title)
        self.number = _text("number", number)
        self.revision = _text("revision", revision)
        self.part_number = _text("part_number", part_number or None, required=False) or ""
        self.author = _text("author", author or None, required=False) or ""
        if drawing is not None and not isinstance(drawing, Drawing):
            raise TypeError("drawing= takes a Drawing(number, revision=...)")
        self.drawing = drawing
        self.status = _one_of("status", status, STATUSES)
        self.size = _one_of("size", size, PAGE_SIZES)
        self.camera = _one_of("camera", camera, CAMERAS)
        self.rigor = _one_of("rigor", rigor, RIGORS)
        self.emphasis = _one_of("emphasis", emphasis, EMPHASES)
        self.layout = _layout(rigor, format)
        self.pictures = bool(pictures) and self.emphasis == "visual" and self.layout.figures
        # The front page's free text, held to the steps' rule: a value it states cites a source
        # (``Cited(text, per=...)``), or that source is an open item (``missing``, as (where, what)).
        self.missing: list[tuple[str, str]] = []
        self.scope = self._front("scope", scope) if scope else None
        if isinstance(safety, (str, bytes, Cited)):
            raise TypeError(f"safety takes a list of lines, not one: safety=[{safety!r}]")
        self.safety = [self._front("safety", line) for line in safety]
        self.tools = _lines("tools", tools)
        if isinstance(revisions, (str, bytes)) or any(
                not isinstance(row, (tuple, list)) or len(row) != 3 for row in revisions):
            raise TypeError("revisions takes (rev, date, change) rows")
        self.revisions = [tuple(_text("revisions cell", cell) for cell in row) for row in revisions]
        self.operations: list[str] = []
        self.steps: list[Step] = []
        self.materials: list[_Record] = []
        self._installed: dict[str, int] = {}
        self.scene = _Scene(shape, self.source)
        if len(self.scene.leaves()) < 2:  # refused before any step
            raise TypeError(f"{self.source_name} is a single part: work instructions are for an assembly; "
                            "instructions for machining or processing one detail part are not supported yet")

    def _front(self, where: str, value: str | Cited) -> _Line:
        text, source = _cited(f"{where} line", value)
        if text is None:
            raise ValueError(f"{where} takes a line of text or Cited(text, per=...), got {value!r}")
        if source is not None:
            _source(where, source)
        owed = _owed(text, source)
        self.missing += [(where, name) for name in owed]
        return _Line("", text, source, cite=bool(owed))

    def leaves(self) -> list[_Occurrence]:
        return self.scene.leaves()

    def _resolve(self, key: str) -> tuple[list[tuple[str, str]], list[str]]:
        """What a part's label or a part or subassembly ref installs: the units at the level it
        names them (a subassembly is one unit, a label several parts share is each of them), and
        every part under them."""
        from cadgen.engine.refs import RefError

        key = _text("install ref", key)
        leaves = self.leaves()
        named = [leaf for leaf in leaves if leaf.label == key]
        if not named:
            try:
                named = self.scene.occurrences(key)
            except RefError as exc:
                listing = ", ".join(leaf.ref for leaf in leaves[:40])
                more = f" and {len(leaves) - 40} more" if len(leaves) > 40 else ""
                raise KeyError(f"{key!r} names no one part or subassembly of {self.source_name} ({exc}); "
                               f"its parts are: {listing}{more}. wi.tree() lists the subassemblies too.") from None
        parts = [part.ref for unit in named for part in self.scene.parts_under(unit)]
        return [(unit.ref, unit.label or UNNAMED) for unit in named], parts

    def tree(self) -> str:
        """The assembly's occurrences, indented: every ref and name ``install=`` takes,
        subassemblies included."""
        rows: list[str] = []

        def walk(node: _Occurrence, depth: int) -> None:
            rows.append(f"{'  ' * depth}{node.ref or node.label or '(unnamed root)'}")
            for child in node.children:
                walk(child, depth + 1)

        walk(self.scene.top, 0)
        return "\n".join(rows)

    def operation(self, title: str) -> "Instruction":
        """Start the next operation: a heading over the steps that follow it (and a
        line in the front pages' overview). Steps keep one sequence across them."""
        self.operations.append(_text("operation title", title))
        return self

    def step(self, title: str, *, install: Iterable[str] = (), camera: str | None = None,
             picture: bool = True, frame: str = "step") -> Step:
        """Add the next step. ``install`` names the parts this step puts in place
        (labels, or refs such as ``bracket`` or ``arm/pin.2``; a label several parts share
        installs every one of them; a subassembly's ref or label installs it as one
        unit). A part is installed by one step only. ``frame`` is ``step`` (the
        figure fits the parts the step installs, with what is around them) or
        ``assembly`` (the figure fits the whole assembly, as every such figure does)."""
        if isinstance(install, (str, bytes)):
            raise TypeError(f"install takes a sequence of part names or refs, not one string: install=({install!r},)")
        number = len(self.steps) + 1
        # Everything that can refuse is checked before a part is claimed, so a refused
        # step leaves the parts free for the next one.
        title = _text("step title", title)
        camera = None if camera is None else _one_of("camera", camera, CAMERAS)
        frame = _one_of("frame", frame, FRAMES)
        refs: list[str] = []
        units: list[tuple[str, str]] = []
        for key in install:
            found, leaves = self._resolve(key)
            for ref in leaves:
                if ref in self._installed:
                    raise ValueError(f"step {self._label(number)} installs {key!r} ({ref}), "
                                     f"which step {self._label(self._installed[ref])} already installs")
                if ref not in refs:
                    refs.append(ref)
            units += [unit for unit in found if unit not in units]
        for ref in refs:
            self._installed[ref] = number
        step = Step(self, number, title, tuple(refs), camera, bool(picture),
                    len(self.operations) if self.operations else None, tuple(units), frame)
        self.steps.append(step)
        return step

    def _label(self, number: int) -> str:
        return str(number * 10 if self.layout.numbering == "by-ten" else number)

    def references(self) -> list[tuple[str, str, list[str]]]:
        """(document, where in it, the step labels that apply it), for every cited
        spec, drawing and data sheet section, in first-cited order."""
        found: dict[tuple[str, str], list[str]] = {}
        for step in self.steps:
            for source in step.sources():
                if source.kind != "stated":
                    labels = found.setdefault((source.document, source.where), [])
                    if step.label not in labels:
                        labels.append(step.label)
        return [(document, where, labels) for (document, where), labels in found.items()]

    def _use(self, record) -> None:
        if record not in self.materials:
            self.materials.append(record)

    def equipment(self) -> list[str]:
        """The equipment the steps imply, then the tools the user named, each once."""
        implied = [EQUIPMENT[op.kind] for step in self.steps for op in step.ops
                   if op.kind in EQUIPMENT and op.equipment]
        return list(dict.fromkeys(implied + self.tools))

    def open_items(self) -> list[str]:
        """Everything engineering still owes: each NOT STATED value, the source of each value free text
        states uncited, and each part no step installs."""
        items = [f"{where}: {name} not stated" for where, name in self.missing]
        for step in self.steps:
            items += [f"step {step.label} ({where}): {name} not stated" for where, name in step.missing]
            for op in step.ops:
                items += [f"step {step.label} ({op.kind}): {name} not stated" for name in op.missing]
        for leaf in self.leaves():
            if leaf.ref not in self._installed:
                items.append(f"{leaf.ref}: no step installs it")
        return items

    def documents(self) -> list[tuple[str, str]]:
        """(document, title) for the drawing and every spec a value cites, in first-cited order."""
        seen: dict[str, str] = {}
        if self.drawing is not None:
            seen[self.drawing.name] = self.drawing.title or "Assembly drawing"
        front = [line.source for line in ([self.scope] if self.scope else []) + self.safety if line.source is not None]
        for source in [*front, *(source for step in self.steps for source in step.sources())]:
            if source.kind in ("spec", "drawing", "datasheet"):
                seen.setdefault(source.document, source.title)
        return list(seen.items())


# --- the decorator -----------------------------------------------------------


def work_instruction(func: Callable[..., Any] | None = None, *, out: str | Path | None = None):
    """Declare a work instruction. The function returns an :class:`Instruction`;
    calling it (the script's ``__main__`` does) writes one PDF at ``out``, prints
    every open item, and returns the path written.

    ``out`` is required and relative paths resolve against the script.
    """

    def apply(fn: Callable[..., Any]) -> Callable[..., Any]:
        import inspect

        if out is None:
            raise ValueError(
                f"@work_instruction {fn.__name__} needs out=<path>.pdf: the instruction is that PDF, "
                "and cadgen does not choose where it lands."
            )
        target_spec = Path(out)
        if target_spec.suffix.lower() != ".pdf":
            raise ValueError(f"@work_instruction out= must name a .pdf, got {out!r}")
        script = Path(inspect.getsourcefile(fn) or inspect.getfile(fn)).resolve()

        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> list[Path]:
            # A refused or failed run writes nothing at out=, and an earlier instruction there
            # stays byte for byte (law 17): the PDF is written whole beside it, then moved in.
            target = target_spec if target_spec.is_absolute() else (script.parent / target_spec).resolve()
            return write(target, fn(*args, **kwargs))

        def write(target: Path, wi: Any) -> list[Path]:
            if not isinstance(wi, Instruction):
                raise TypeError(f"@work_instruction {fn.__name__} must return an Instruction")
            if not wi.steps:
                raise ValueError(f"@work_instruction {fn.__name__} has no steps")
            items = wi.open_items()
            if wi.status == "released" and items:
                raise ValueError(
                    f"@work_instruction {fn.__name__} is released with {len(items)} open item(s); "
                    "state them or keep it a draft:\n  " + "\n  ".join(items)
                )
            from cadgen._internal.work_instruction_pages import write_pdf

            pages = write_pdf(wi, target, open_items=items)
            for item in items:
                print(f"{fn.__name__}: open item: {item}")
            print(f"wrote {target} ({pages} page{'s' if pages != 1 else ''})")
            return [target]

        from cadgen import analytics

        return analytics.counted(run, "work_instruction")

    return apply(func) if func is not None else apply
