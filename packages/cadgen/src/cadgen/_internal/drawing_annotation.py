"""What a view says about the part: its dimensions and callouts resolved against
the geometry and planned round the view, and its hole table.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, NamedTuple

from cadgen._internal.drawing_assembly import _BALLOON_AIR, _BALLOON_LEAD, _BALLOON_R, _balloon_axis
from cadgen._internal.drawing_base import (
    _CALLOUT_CLEAR, _CALLOUT_GAP, _CALLOUT_LANDING, _DIM_ROW, _FLAG_SIDE, _LABEL_ROOM, _OPPOSITE, _SECTION_LETTERS,
    _SAME_PLACE, _SIDES,
    _dot, _exact, _fmt, _ink_width, _look, _looks_down, _near, _places, _shown, _spans, _text_width, _where,
)
from cadgen._internal.drawing_features import Slot
from cadgen._internal.drawing_gdt import _DATUM_REACH, _datum_toward, _side_of, frame_size, mark_width
from cadgen._internal.drawing_sheet import _CAPTION_HEIGHT

if TYPE_CHECKING:
    from cadgen.eng_drawing import Sheet, View


@dataclass
class _Dim:
    kind: str
    p1: tuple[float, float, float]
    p2: tuple[float, float, float] | None
    #: Sheet millimetres from the dimensioned points, or None for the next free row.
    offset: float | None
    text: str | None
    orientation: str | None
    radius: float = 0.0
    angle: float = 45.0
    tol: Any = None
    fit: str | None = None
    hole: dict | None = None
    #: The parts-list item a flag note points at, where it names one.
    item: Any = None
    #: Filled in at render time, on a copy: the hole a callout states, the side and
    #: row an unplaced dimension was given, and the call's index for messages.
    feature: Any = None
    side: str | None = None
    row: int = 0
    index: int = 0
    #: The holes or slots a callout states, each one: its ``4×`` covers four.
    covers: tuple = ()
    #: A basic dimension (exact, boxed: a GD&T frame bounds it) or a reference one
    #: (information only, in parentheses); and limits, the two the part lies between.
    basic: bool = False
    reference: bool = False
    limits: tuple[float, float] | None = None
    #: A feature control frame the callout or dimension carries, and the datum
    #: letter its feature is (a datum feature of size: a bore, a width).
    frame: Any = None
    datum: str | None = None
    #: A key characteristic: marked with the profile's boxed letters after the value.
    key: bool = False


#: ISO 261 general-purpose metric screw threads: each nominal diameter's coarse
#: pitch (None where the size has fine pitches only) and its fine pitches. A
#: metric thread names one of these sizes and one of its pitches; ``M6`` with no
#: pitch is the coarse one.
_ISO_261: dict[float, tuple[float | None, tuple[float, ...]]] = {
    1.0: (0.25, (0.2,)), 1.2: (0.25, (0.2,)), 1.4: (0.3, (0.2,)), 1.6: (0.35, (0.2,)), 1.8: (0.35, (0.2,)),
    2.0: (0.4, (0.25,)), 2.5: (0.45, (0.35,)), 3.0: (0.5, (0.35,)), 3.5: (0.6, (0.35,)), 4.0: (0.7, (0.5,)),
    5.0: (0.8, (0.5,)), 6.0: (1.0, (0.75,)), 7.0: (1.0, (0.75,)), 8.0: (1.25, (1.0, 0.75)),
    10.0: (1.5, (1.25, 1.0, 0.75)), 12.0: (1.75, (1.5, 1.25, 1.0)), 14.0: (2.0, (1.5, 1.25, 1.0)),
    16.0: (2.0, (1.5, 1.0)), 18.0: (2.5, (2.0, 1.5, 1.0)), 20.0: (2.5, (2.0, 1.5, 1.0)),
    22.0: (2.5, (2.0, 1.5, 1.0)), 24.0: (3.0, (2.0, 1.5, 1.0)), 27.0: (3.0, (2.0, 1.5, 1.0)),
    30.0: (3.5, (3.0, 2.0, 1.5, 1.0)), 33.0: (3.5, (3.0, 2.0, 1.5)), 36.0: (4.0, (3.0, 2.0, 1.5)),
    39.0: (4.0, (3.0, 2.0, 1.5)), 42.0: (4.5, (4.0, 3.0, 2.0, 1.5)), 45.0: (4.5, (4.0, 3.0, 2.0, 1.5)),
    48.0: (5.0, (4.0, 3.0, 2.0, 1.5)), 50.0: (None, (3.0, 2.0, 1.5)), 52.0: (5.0, (4.0, 3.0, 2.0, 1.5)),
    56.0: (5.5, (4.0, 3.0, 2.0, 1.5)), 60.0: (5.5, (4.0, 3.0, 2.0, 1.5)), 64.0: (6.0, (4.0, 3.0, 2.0, 1.5)),
}

#: ASME B1.1's unified inch threads by size, as its numbered size (``#10``) or
#: fraction is written: the threads per inch of each series the size has (coarse
#: UNC, fine UNF, extra-fine UNEF). A unified thread names one of these sizes and
#: the series' own count.
_UNIFIED_SERIES: dict[str, dict[str, int]] = {
    "#0": {"UNF": 80}, "#1": {"UNC": 64, "UNF": 72}, "#2": {"UNC": 56, "UNF": 64}, "#3": {"UNC": 48, "UNF": 56},
    "#4": {"UNC": 40, "UNF": 48}, "#5": {"UNC": 40, "UNF": 44}, "#6": {"UNC": 32, "UNF": 40},
    "#8": {"UNC": 32, "UNF": 36}, "#10": {"UNC": 24, "UNF": 32}, "#12": {"UNC": 24, "UNF": 28, "UNEF": 32},
    "1/4": {"UNC": 20, "UNF": 28, "UNEF": 32}, "5/16": {"UNC": 18, "UNF": 24, "UNEF": 32},
    "3/8": {"UNC": 16, "UNF": 24, "UNEF": 32}, "7/16": {"UNC": 14, "UNF": 20, "UNEF": 28},
    "1/2": {"UNC": 13, "UNF": 20, "UNEF": 28}, "9/16": {"UNC": 12, "UNF": 18, "UNEF": 24},
    "5/8": {"UNC": 11, "UNF": 18, "UNEF": 24}, "11/16": {"UNEF": 24}, "3/4": {"UNC": 10, "UNF": 16, "UNEF": 20},
    "13/16": {"UNEF": 20}, "7/8": {"UNC": 9, "UNF": 14, "UNEF": 20}, "15/16": {"UNEF": 20},
    "1": {"UNC": 8, "UNF": 12, "UNEF": 20}, "1-1/16": {"UNEF": 18}, "1-1/8": {"UNC": 7, "UNF": 12, "UNEF": 18},
    "1-3/16": {"UNEF": 18}, "1-1/4": {"UNC": 7, "UNF": 12, "UNEF": 18}, "1-5/16": {"UNEF": 18},
    "1-3/8": {"UNC": 6, "UNF": 12, "UNEF": 18}, "1-7/16": {"UNEF": 18}, "1-1/2": {"UNC": 6, "UNF": 12, "UNEF": 18},
}

#: ``M6``, ``M6x1``, ``M6 x 1 - 6H``, ``M6x1-6H LH``: a metric thread, its pitch
#: and an ISO 965 tolerance class (an internal thread's letters are capitals).
_THREAD = re.compile(r"M(?P<d>\d+(?:\.\d+)?)(?:\s*[x×]\s*(?P<p>\d+(?:\.\d+)?))?"
                     r"(?:\s*-\s*(?P<cls>\d[A-Za-z](?:\d[A-Za-z])?))?(?:\s+LH)?")
#: ISO 965-1's tolerance classes for an internal thread, a tapped hole: grades 4
#: to 8 in position H or G, for the pitch and minor diameters (``5H6H``) or one
#: for both (``6H``).
_INTERNAL_CLASS = re.compile(r"[4-8][GH](?:[4-8][GH])?")
#: ``1/4-20 UNC``, ``#10-32 UNF - 2B``, ``1-1/4-7 UNC-2B``: a unified inch thread
#: (ASME B1.1), its size, threads per inch, series and class (A external, B
#: internal). A number 0 to 12 is a numbered size, ``#`` or not, and ``1`` is
#: the inch where the numbered size has no such count.
_UNIFIED = re.compile(r"(?P<size>#?\d+|\d+-\d+/\d+|\d+/\d+)\s*-\s*(?P<tpi>\d+)\s*"
                      r"(?P<series>UN[A-Z]*)(?:\s*-\s*(?P<cls>[123][AaBb]))?(?:\s+LH)?")


@dataclass(frozen=True)
class _Thread:
    """A thread a hole callout states: its text as given, nominal diameter and pitch (mm)."""

    text: str
    diameter: float
    pitch: float

    def fits(self, bore: float) -> str | None:
        """How a bore of this diameter carries the thread: ``"major"`` when it is
        modelled at the thread's nominal size, ``"drill"`` when it is the tap
        drill (from the basic minor diameter, d - 1.0825P, to d - P and a
        little over, where the common tap drills sit), else None."""
        if abs(bore - self.diameter) <= 0.01:
            return "major"
        if self.diameter - 1.0825 * self.pitch - 0.01 <= bore <= self.diameter - self.pitch + 0.1:
            return "drill"
        return None


def _inches(size: str) -> float:
    """A unified thread's size in inches: a numbered size (``#10``) or a
    fraction (``1/4``, ``1-1/4``) or a whole inch (``1``)."""
    if size.startswith("#"):
        return 0.060 + 0.013 * int(size[1:])
    whole, _, fraction = size.rpartition("-") if "/" in size else ("", "", size)
    if "/" not in fraction:
        return float(fraction)
    top, bottom = fraction.split("/")
    return (int(whole) if whole else 0) + int(top) / int(bottom)


def _unified_size(size: str, tpi: int) -> str | None:
    """The B1.1 size a unified thread's written size names: ``10`` and ``#10``
    are the numbered size, and ``1`` is #1 where #1 has that count, else the inch."""
    if size.lstrip("#").isdigit() and int(size.lstrip("#")) <= 12:
        numbered = f"#{int(size.lstrip('#'))}"
        if size.startswith("#") or tpi in _UNIFIED_SERIES.get(numbered, {}).values() or size not in _UNIFIED_SERIES:
            return numbered if numbered in _UNIFIED_SERIES else None
    return size if size in _UNIFIED_SERIES else None


def _thread(value) -> _Thread:
    """A hole callout's ``thread=``, parsed: a metric thread (``M6``, ``M6x0.75 -
    6H``) of ISO 261's sizes and pitches, or a unified inch one (``1/4-20 UNC``,
    ``#10-32 UNF - 2B``) of ASME B1.1's sizes and series. Its diameter and pitch
    are what the bore is checked against. Any other thread is refused, because a
    thread is the one size of a tapped hole the part does not carry: the drawing
    can only state one it can read, and a pitch the size does not have
    (``M6x5``, ``1/4-28 UNC``) is no thread at all."""
    if not isinstance(value, str):
        raise TypeError(f"thread= takes the thread as a string (\"M6x1 - 6H\"), got {value!r}")
    text = value.strip()
    if match := _UNIFIED.fullmatch(text):
        tpi, series = int(match["tpi"]), match["series"]
        size = _unified_size(match["size"], tpi)
        if size is None:
            raise ValueError(f"thread={value!r}: {match['size']} is not an ASME B1.1 unified size this drawing "
                             f"knows; one of {', '.join(_UNIFIED_SERIES)}")
        counts = _UNIFIED_SERIES[size]
        if series not in counts or counts[series] != tpi:
            has = ", ".join(f"{s} {n}" for s, n in counts.items())
            raise ValueError(f"thread={value!r}: ASME B1.1 gives {size} {has} threads per inch, so "
                             f"{size}-{tpi} {series} is no unified thread; write one of "
                             + ", ".join(f"{size}-{n} {s}" for s, n in counts.items()))
        if match["cls"] and match["cls"][1] in "Aa":
            raise ValueError(f"thread={value!r}: {match['cls']} is an external thread's class (a tapped hole's ends "
                             "in B: 2B)")
        return _Thread(text, _inches(size) * 25.4, 25.4 / tpi)
    match = _THREAD.fullmatch(text)
    if match is None:
        raise ValueError(f"thread={value!r} is not a thread this drawing can check against the bore; write a metric "
                         "one as M<diameter>[x<pitch>][ - <class>] (\"M6\", \"M6x0.75 - 6H\") or a unified inch one as "
                         "<size>-<threads per inch> <series>[-<class>] (\"1/4-20 UNC\", \"#10-32 UNF - 2B\")")
    diameter = float(match["d"])
    if diameter not in _ISO_261:
        raise ValueError(f"thread={value!r}: M{_fmt(diameter)} is not an ISO 261 size this drawing knows; one of "
                         + ", ".join(f"M{_fmt(d)}" for d in _ISO_261))
    coarse, fine = _ISO_261[diameter]
    if match["p"] is None:
        if coarse is None:
            raise ValueError(f"thread={value!r}: ISO 261 gives M{_fmt(diameter)} no coarse pitch to assume; "
                             f"give its pitch, as M{_fmt(diameter)}x<pitch>")
        pitch = coarse
    else:
        pitch = float(match["p"])
        pitches = (coarse, *fine) if coarse is not None else fine
        if pitch not in pitches:
            raise ValueError(f"thread={value!r}: ISO 261 gives M{_fmt(diameter)} the pitches "
                             f"{', '.join(_fmt(p) for p in pitches)}, not {_fmt(pitch)}")
    if match["cls"] and match["cls"] != match["cls"].upper():
        raise ValueError(f"thread={value!r}: {match['cls']} is an external thread's tolerance class (ISO 965 "
                         "writes a nut's, a tapped hole's, in capitals: 6H)")
    if match["cls"] and not _INTERNAL_CLASS.fullmatch(match["cls"]):
        raise ValueError(f"thread={value!r}: {match['cls']} is not an ISO 965-1 class for a tapped hole, which "
                         "is a grade 4 to 8 in position H or G: 6H, 5H6H, 6G")
    return _Thread(text, diameter, pitch)


#: ISO 286-1's fundamental deviations: a hole's in capitals, a shaft's the same
#: in lower case.
_DEVIATIONS = ("A", "B", "C", "CD", "D", "E", "EF", "F", "FG", "G", "H", "J", "JS", "K", "M", "N", "P", "R", "S",
               "T", "U", "V", "X", "Y", "Z", "ZA", "ZB", "ZC")
#: ISO 286-1's standard tolerance grades, IT01 to IT18.
_GRADES = ("01", "0", *(str(n) for n in range(1, 19)))
_TOLERANCE_CLASS = re.compile(r"(?P<deviation>[A-Za-z]{1,2})(?P<grade>\d{1,2})")


def _tolerance_class(text: str) -> str | None:
    """``"hole"`` or ``"shaft"`` for an ISO 286-1 tolerance class (``H7``,
    ``g6``, ``JS9``), else None."""
    match = _TOLERANCE_CLASS.fullmatch(text)
    if match is None or match["grade"] not in _GRADES:
        return None
    deviation = match["deviation"]
    if deviation in _DEVIATIONS:
        return "hole"
    if deviation.islower() and deviation.upper() in _DEVIATIONS:
        return "shaft"
    return None


def _fit(value, *, hole: bool = False) -> str | None:
    """A ``fit=``, checked: an ISO 286-1 tolerance class (``H7`` a hole's, ``g6``
    a shaft's) or a fit, a hole's class over a shaft's (``H7/g6``). It prints
    after the size as given, so anything else -- a word, a class with no grade,
    a hole's class on a shaft -- would print as a requirement nobody can read.
    A hole callout's fit is the hole's: a shaft's class is refused there."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"fit= takes an ISO 286 tolerance class or fit as a string (\"H7\", \"H7/g6\"), got {value!r}")
    kinds = [_tolerance_class(part) for part in value.split("/")]
    if len(kinds) == 1 and kinds[0] is not None and not (hole and kinds[0] == "shaft"):
        return value
    if kinds == ["hole", "shaft"]:
        return value
    if hole and kinds == ["shaft"]:
        raise ValueError(f"fit={value!r} is a shaft's tolerance class (lower case); a hole's is in capitals "
                         f"({value.upper()})")
    raise ValueError(f"fit={value!r} is not an ISO 286-1 tolerance class or fit: a fundamental deviation "
                     f"({', '.join(_DEVIATIONS)}; a shaft's in lower case) and a grade 01, 0 or 1 to 18, as \"H7\" "
                     "or \"g6\", or a hole's class over a shaft's, as \"H7/g6\"")


def _tol_suffix(tol) -> str:
    if not tol:
        return ""
    plus, minus = tol
    if abs(plus - minus) < 1e-9:
        return f" ±{_exact(plus)}"
    places = _places(plus, minus)  # plus and minus to one precision, as given
    return f" +{plus:.{places}f}/-{minus:.{places}f}"


def hole_callout_text(spec: dict, *, tol=None, fit: str | None = None) -> str:
    """The text of a hole callout, in the ISO/ASME symbols a shop reads."""
    parts = []
    # One hole is not "1×": a count prints only when there is something to count.
    lead = f"{spec['count']}× " if (spec.get("count") or 1) > 1 else ""
    if spec.get("slot"):
        text = f"{lead}{_fmt(spec['width'])} × {_fmt(spec['length'])} SLOT"
        text += " THRU" if spec.get("thru") else (f" \u21a7{_fmt(spec['depth'])}" if spec.get("depth") else "")
        if spec.get("cbore"):
            width, length, depth = spec["cbore"]
            text += f"   \u2334 {_fmt(width)} × {_fmt(length)} \u21a7{_fmt(depth)}"
        return text + (f"   {spec['label']}" if spec.get("label") else "")
    thread, drilled = spec.get("thread"), spec.get("tap_drill")
    thread_depth = spec.get("thread_depth")
    # A tapped hole whose bore is its tap drill states the drill and then the
    # thread, each with its own depth (\u23005 \u21a712   M6x1 - 6H \u21a710); one tapped
    # right through states the thread alone. A bore modelled at the thread's
    # size is the thread.
    both = bool(thread and drilled and (thread_depth is not None or not spec.get("thru")))
    size = thread if thread and not both else f"%%c{_fmt(spec['diameter'])}"
    size += _tol_suffix(tol) + (f" {fit}" if fit else "")
    if spec.get("thru"):
        size += " THRU"
    elif spec.get("depth") is not None:
        size += f" \u21a7{_fmt(spec['depth'])}"
    if spec.get("pcd"):
        # The bolt circle: equally spaced on a circle of this diameter.
        size += f" EQ SP ON %%c{_fmt(spec['pcd'])}"
    parts.append(lead + size)
    if both:
        parts.append(f"{thread} \u21a7{_fmt(thread_depth)}")  # a blind tapped hole always gives it

    def same(a, b) -> bool:
        return a is not None and b is not None and all(abs(x - y) < 1e-3 for x, y in zip(a, b))

    def cbore(pair) -> str:
        return f"\u2334 %%c{_fmt(pair[0])} \u21a7{_fmt(pair[1])}"

    def csk(pair) -> str:
        return f"\u2335 %%c{_fmt(pair[0])} × {_fmt(pair[1])}°"

    # A through hole can be opened out at both ends: the same at each is stated
    # once, BOTH ENDS; something different at the far end is stated FAR SIDE.
    for near, far, text in ((spec.get("cbore"), spec.get("far_cbore"), cbore),
                            (spec.get("csk"), spec.get("far_csk"), csk)):
        if near:
            parts.append(text(near) + (" BOTH ENDS" if same(near, far) else ""))
    for near, far, text in ((spec.get("cbore"), spec.get("far_cbore"), cbore),
                            (spec.get("csk"), spec.get("far_csk"), csk)):
        if far and not same(near, far):
            parts.append("FAR SIDE " + text(far))
    if spec.get("label"):
        parts.append(str(spec["label"]))
    return "   ".join(parts)


def _shows(view: View, proj, feature, run: float, cut) -> bool:
    """Whether a view draws a hole or slot that runs ``run`` from its mouth: not one
    wholly in the half a section takes away, outside a detail's circle, or inside
    the stretch a broken view leaves out."""
    if view._detail is not None:
        if math.dist(proj.point(feature.mouth), proj.point(view._detail.centre)) > view._detail.radius + 1e-6:
            return False
    if view._break is not None and view._break.low < feature.mouth[view._break.axis] < view._break.high:
        return False
    if cut is None:
        return True
    look = _look(view)
    far = tuple(m + a * run for m, a in zip(feature.mouth, feature.axis))
    return min(_dot(tuple(e - c for e, c in zip(end, cut[2])), look) for end in (feature.mouth, far)) <= 1e-6


def _faces_viewer(feature, look) -> bool:
    """Whether a view sees a hole's or a slot's mouth: its axis runs into the
    material away from the viewer, or it is through and reads the same from either
    end, plain or opened out alike at both (a hole chamfered both ends). A
    counterbore or countersink on the far side alone is not something this view
    shows."""
    if _dot(feature.axis, look) < 0:
        return True
    if isinstance(feature, Slot):
        return feature.thru and not feature.cbore
    # Its signature's near and far ends, rounded as a 4× count compares holes.
    _size, _thru, _depth, cbore, csk, far_cbore, far_csk, _problem = feature.signature()
    return feature.thru and ((far_cbore, far_csk) == (cbore, csk) or not (cbore or csk))


def _looks_into(feature, look) -> bool:
    """Whether a view looks down a hole or slot from the side it opens on."""
    return _looks_down(feature.axis, look) and _faces_viewer(feature, look)


def _kinds(features) -> list[list]:
    """Holes and slots grouped by kind, in the order a drawing lists them: holes,
    largest first, then slots."""
    groups: dict[tuple, list] = {}
    for feature in features:
        groups.setdefault((isinstance(feature, Slot), feature.signature()), []).append(feature)
    return sorted(groups.values(), key=lambda g: (isinstance(g[0], Slot),
                                                  0.0 if isinstance(g[0], Slot) else -g[0].diameter,
                                                  g[0].signature()))


@dataclass
class _Features:
    """What a drawing reads off one part, once however many views show it."""

    holes: list
    slots: list
    circles: list

    def pcd(self, members) -> float | None:
        """The bolt circle's diameter when these holes are exactly one bolt circle."""
        mouths = {tuple(round(c, 6) for c in h.mouth) for h in members}
        for circle in self.circles:
            if {tuple(round(c, 6) for c in m) for m in circle.mouths} == mouths:
                return circle.diameter
        return None


def _hole_spec(hole, count: int, thread: str | None = None, label: str | None = None,
               pcd: float | None = None, *, tap_drill: bool = False, thread_depth: float | None = None) -> dict:
    if hole.problem is not None:
        raise ValueError(f"the hole at {_where(hole.mouth)} cannot be stated in one callout: {hole.problem}. "
                         "No hole callout or hole table states that; dimension its steps with diameter() and dim() "
                         "(in a section through it), call out the other holes with hole(), or change the model.")
    return {"diameter": hole.diameter, "depth": hole.depth, "thru": hole.thru, "cbore": hole.cbore,
            "csk": hole.csk, "far_cbore": hole.far_cbore, "far_csk": hole.far_csk, "count": count,
            "thread": thread, "label": label, "pcd": pcd, "tap_drill": tap_drill, "thread_depth": thread_depth}


def _feature_text(feature, count: int) -> str:
    """What a completeness line calls a hole or slot: its callout, or, for a hole
    no one callout can state, where it is and why."""
    if isinstance(feature, Slot):
        return _shown(hole_callout_text(_slot_spec(feature, count)))
    if feature.problem is not None:
        return f"the hole at {_where(feature.mouth)} ({feature.problem})"
    return _shown(hole_callout_text(_hole_spec(feature, count)))


def _slot_spec(slot, count: int, label: str | None = None) -> dict:
    return {"slot": True, "width": slot.width, "length": slot.length, "thru": slot.thru, "depth": slot.depth,
            "cbore": slot.cbore, "count": count, "label": label}


def _outer_radius(spec: dict) -> float:
    """Where a callout's leader ends: on the outermost circle the hole shows, so the
    arrow does not cross a counterbore to reach the bore inside it; on a slot,
    the arc of its end."""
    if spec.get("slot"):
        return (spec.get("cbore") or (spec["width"],))[0] / 2
    return max(spec["diameter"], (spec.get("cbore") or (0.0,))[0], (spec.get("csk") or (0.0,))[0]) / 2


def _radii_at(proj, target, *, closed_only: bool) -> list[float]:
    """The radii of the circles (and, unless ``closed_only``, arcs) a view draws
    centred on ``target``, in model millimetres. The hidden-line pass draws a
    turned groove's outline as a spline on one side and a circle on the other
    (where the torus's seam lies); a spline every point of which lies one
    distance from ``target`` is that arc."""
    from build123d import GeomType

    from cadgen._internal.drawing_views import _edge_polyline

    radii: set[float] = set()
    for edge in list(proj.visible) + list(proj.hidden):
        if edge.geom_type == GeomType.CIRCLE and not (closed_only and not edge.is_closed):
            if _near((edge.arc_center.X, edge.arc_center.Y), target):
                radii.add(round(edge.radius, 4))
        elif edge.geom_type == GeomType.BSPLINE and not closed_only:
            reach = [math.hypot(x - target[0], y - target[1]) for x, y in _edge_polyline(edge, 9)]
            if min(reach) > _SAME_PLACE and max(reach) - min(reach) <= _SAME_PLACE:
                radii.add(round(sum(reach) / len(reach), 4))
    return sorted(radii)


#: A hole callout wider than this on the sheet, mm, breaks after each of its
#: stages (the bore, then a counterbore or countersink, then the far end), a line
#: each, as a drafter stacks one: the long line pushed every view after it out.
_CALLOUT_WRAP = 60.0
#: The pitch of a stacked callout's lines, in text heights.
_CALLOUT_LINE = 1.5


def _callout_lines(dim: "_Dim", th: float) -> list[str]:
    """A callout's text as the lines it is drawn in: its stages a line each where
    the whole is wider than ``_CALLOUT_WRAP``, else one line. A basic callout,
    boxed as one value, is never broken."""
    value = _callout_value(dim)
    stages = value.split("   ")
    if dim.basic or len(stages) == 1 or _ink_width(value, th) <= _CALLOUT_WRAP:
        return [value]
    return stages


def _callout_value(dim: "_Dim") -> str:
    if dim.kind in ("hole", "slot"):
        return hole_callout_text(dim.hole, tol=dim.tol, fit=dim.fit)
    if dim.text:
        value = dim.text
    else:
        value = f"%%c{_fmt(2 * dim.radius)}" if dim.kind == "diameter" else f"R{_fmt(dim.radius)}"
    return f"({value})" if dim.reference else value


def _far_side(call: str, what: str, view) -> ValueError:
    """The refusal for a feature that opens away from the viewer, naming the view
    that looks into it where there is one by name."""
    there = (f"the {_OPPOSITE[view.name]} view, which looks into it" if view.name in _OPPOSITE
             else "a view that looks into it")
    return ValueError(f"{call}: that {what} opens on the far side of the part. Call it out in {there}.")


def _holes_hint(seen, look) -> str:
    mine = [h for h in seen if _faces_viewer(h, look)]
    if not mine:
        return ("This view looks down no hole; a hole is called out in the view that sees it as a circle "
                "and looks into its mouth.")
    listed = ", ".join(f"⌀{_fmt(h.diameter)} at {_where(h.mouth)}" for h in mine[:6])
    return f"The holes it looks down open at {listed}{' ...' if len(mine) > 6 else ''}; view.holes() calls out every one."


def _resolve_view(view: View, proj, bounds, part_features, warnings: list | None, cut=None) -> list["_Dim"]:
    """The view's annotation with every size the part decides filled in from the
    part, on copies: a hole callout's diameter, depth, counterbore, countersink and
    count, a diameter or radius callout's value, and ``holes()`` expanded into one
    callout per kind of hole, less the kinds a ``hole()`` or ``slot()`` on the view
    states. Anything the author typed is checked on the way."""
    look = _look(view)
    seen_cache: tuple | None = None

    def kept(feature, run: float) -> bool:
        return _shows(view, proj, feature, run, cut)

    def seen() -> tuple:
        nonlocal seen_cache
        if seen_cache is None:
            features = part_features(view.shape)
            seen_cache = (
                [h for h in features.holes if _looks_down(h.axis, look) and kept(h, h.length)],
                [sl for sl in features.slots if _looks_down(sl.axis, look) and kept(sl, sl.run)],
                features,
            )
        return seen_cache

    resolved: dict[int, list[_Dim]] = {}
    for index, dim in enumerate(view._dims):
        if dim.kind == "hole":
            holes, slots, features = seen()
            resolved[index] = [_resolve_hole(view, proj, dim, holes, look, features, slots)]
        elif dim.kind == "slot":
            _holes, slots, _features = seen()
            resolved[index] = [_resolve_slot(view, proj, bounds, dim, slots, look)]
        elif dim.kind in ("diameter", "radius"):
            resolved[index] = [_resolve_round(view, proj, dim)]
        elif dim.kind != "holes":
            resolved[index] = [replace(dim)]
    # A kind of hole a hole() call states is that call's, with its fit or frame;
    # holes() calls out the rest.
    stated: dict[int, int] = {}
    for index in sorted(resolved):
        for item in resolved[index]:
            for feature in item.covers or ((item.feature,) if item.feature is not None else ()):
                if id(feature) in stated:
                    first = view._dims[stated[id(feature)]]
                    raise ValueError(
                        f"{view.name}.{item.kind}({_where(item.feature.mouth)}) and "
                        f"{view.name}.{first.kind}({_where(first.p1)}) both call out the "
                        f"{item.kind} at {_where(feature.mouth)}; a feature takes one callout, so drop one.")
                stated[id(feature)] = index
    for index, dim in enumerate(view._dims):
        if dim.kind == "holes":
            holes, slots, features = seen()
            resolved[index] = _expand_holes(view, proj, bounds, dim, holes, look, warnings, features, slots, stated)
    out: list[_Dim] = []
    for index in sorted(resolved):
        for item in resolved[index]:
            item.index = index
        out.extend(resolved[index])
    return out


def _resolve_hole(view: View, proj, dim: "_Dim", seen, look, features: _Features, slots) -> "_Dim":
    given, thread, label = dim.hole["given"], dim.hole["thread"], dim.hole["label"]
    call = f"{view.name}.hole({_where(dim.p1)})"
    target = proj.point(dim.p1)
    here = [h for h in seen if _near(proj.point(h.mouth), target)]
    if not here:
        if given["diameter"] is None and any(_near(proj.point(p), target) for sl in slots
                                             for p in (sl.mouth, *sl.ends)):
            raise ValueError(f"{call}: that is a slot, not a hole; call it out with "
                             f"{view.name}.slot({_where(dim.p1)}).")
        # A circle there is no hole (a boss's outline is one too): a callout states only what the
        # reader read, so a hole it cannot read takes a note, never a callout it cannot check.
        raise ValueError(f"{call}: no hole runs along the {view.name} view's line of sight there, so a callout "
                         "there states what nothing checks. " + _holes_hint(seen, look))
    # Two holes on one line (a clevis) both match; the one whose mouth this view
    # looks into, nearest the viewer, is the one it calls out.
    here.sort(key=lambda h: (not _faces_viewer(h, look), -_dot(h.mouth, look)))
    hole = here[0]
    if not _faces_viewer(hole, look):
        raise _far_side(call, "hole", view)
    same = [h for h in seen if h.signature() == hole.signature() and _faces_viewer(h, look)]
    reads = _shown(hole_callout_text(_hole_spec(hole, len(same))))
    if thread is not None:
        return _resolve_tapped(view, call, dim, hole, same, reads, thread, features)
    problems = []
    if given["diameter"] is not None and abs(given["diameter"] - hole.diameter) > 0.01:
        problems.append(f"diameter={_fmt(given['diameter'])}")
    if given["thru"] is not None and given["thru"] != hole.thru:
        problems.append(f"thru={given['thru']}")
    if given["depth"] is not None and (hole.thru or abs(given["depth"] - hole.depth) > 0.01):
        problems.append(f"depth={_fmt(given['depth'])}")
    problems += _sunk_problems(given, hole)
    if given["count"] is not None and given["count"] != len(same):
        problems.append(f"count={given['count']}")
    if problems:
        raise ValueError(
            f"{call}: the part's hole reads {reads}, but the "
            f"callout was given {', '.join(problems)}. Leave {'it' if len(problems) == 1 else 'them'} unset so "
            "the drawing states the part, or change the model."
        )
    spec = _hole_spec(hole, len(same), None, label, features.pcd(same))
    return replace(dim, hole=spec, radius=_outer_radius(spec), feature=hole, covers=tuple(same))


def _sunk_problems(given: dict, hole) -> list[str]:
    """The counterbore or countersink a callout was given that the hole does not have."""
    problems = []
    if given["cbore"] is not None and (hole.cbore is None or any(
            abs(a - b) > 0.01 for a, b in zip(given["cbore"], hole.cbore))):
        problems.append(f"cbore=({_fmt(given['cbore'][0])}, {_fmt(given['cbore'][1])})")
    if given["csk"] is not None and (hole.csk is None or abs(given["csk"][0] - hole.csk[0]) > 0.01
                                     or abs(given["csk"][1] - hole.csk[1]) > 0.5):
        problems.append(f"csk=({_fmt(given['csk'][0])}, {_fmt(given['csk'][1])})")
    return problems


def _resolve_tapped(view: View, call: str, dim: "_Dim", hole, same: list, reads: str, thread: "_Thread",
                    features: _Features) -> "_Dim":
    """A tapped hole's callout. The bore is the thread's tap drill or its nominal
    size; ``count`` says how many of the identical bores are tapped, ``depth``
    how deep the thread runs. Nothing in the part says either, so neither is
    assumed: a bore one of several identical ones, or a blind tap drill, needs
    them said."""
    given, label = dim.hole["given"], dim.hole["label"]
    bore = thread.fits(hole.diameter)
    if bore is None:
        raise ValueError(
            f"{call}: thread={thread.text!r} does not fit the part's hole, which reads {reads}. Its hole "
            f"(⌀{_fmt(round(thread.diameter, 3))}, pitch {_fmt(round(thread.pitch, 3))}) is its tap drill, ⌀"
            f"{_fmt(round(thread.diameter - 1.0825 * thread.pitch, 2))} to "
            f"⌀{_fmt(round(thread.diameter - thread.pitch + 0.1, 2))}, or the thread itself, "
            f"⌀{_fmt(round(thread.diameter, 2))}; give the thread this bore takes, or change the model."
        )
    problems = []
    if given["thru"] is not None and given["thru"] != hole.thru:
        problems.append(f"thru={given['thru']}")
    problems += _sunk_problems(given, hole)
    if problems:
        raise ValueError(f"{call}: the part's hole reads {reads}, but the callout was given {', '.join(problems)}. "
                         f"Leave {'it' if len(problems) == 1 else 'them'} unset so the drawing states the part, "
                         "or change the model.")
    count = given["count"]
    if count is None and len(same) > 1:
        raise ValueError(
            f"{call}: the part has {len(same)} holes that read {_shown(hole_callout_text(_hole_spec(hole, 1)))}, "
            f"and nothing in it says which are tapped. Pass count={len(same)} if every one is, or count=1 for "
            "this one alone.")
    count = count or 1
    if count not in (1, len(same)):
        raise ValueError(
            f"{call}: count={count} taps some of the {len(same)} identical holes, and one callout cannot say "
            f"which. Call each tapped hole out with count=1, or model the tapped ones as their own bores.")
    covers = tuple(same) if count == len(same) else (hole,)
    length = hole.length if hole.thru else hole.depth
    depth = given["depth"]
    if depth is not None and hole.thru and abs(depth - length) <= 0.01:
        depth = None  # threaded the whole way through
    if depth is not None and depth > length + 0.01:
        raise ValueError(f"{call}: depth={_fmt(depth)} is the thread's depth, and the hole, which reads {reads}, "
                         f"is {_fmt(length)} deep; a thread runs no deeper than its bore.")
    if bore == "major":
        # The bore is modelled at the thread's size: its depth is the thread's.
        if depth is not None and (hole.thru or abs(depth - hole.depth) > 0.01):
            raise ValueError(f"{call}: the hole is modelled at the thread's size and reads {reads}, so it is the "
                             f"thread, and depth={_fmt(depth)} contradicts it. Leave depth unset, or model the "
                             "tap drill.")
        depth = None
    elif depth is None and not hole.thru:
        raise ValueError(
            f"{call}: a blind tapped hole is threaded short of its tap drill's {_fmt(hole.depth)}, and nothing in "
            "the part says how far; pass depth= for the thread's depth.")
    pcd = features.pcd(covers) if len(covers) > 1 else None
    spec = _hole_spec(hole, len(covers), thread.text, label, pcd, tap_drill=bore == "drill", thread_depth=depth)
    return replace(dim, hole=spec, radius=_outer_radius(spec), feature=hole, covers=covers)


def _slot_end(proj, bounds, slot) -> tuple:
    """The end of a slot a callout's leader goes to: the one nearer the view's
    left or right edge, the short way out."""
    x0, x1 = bounds[0], bounds[1]
    return min(slot.ends, key=lambda e: (round(min(proj.point(e)[0] - x0, x1 - proj.point(e)[0]), 6),
                                         -round(proj.point(e)[1], 6)))


def _resolve_slot(view: View, proj, bounds, dim: "_Dim", seen, look) -> "_Dim":
    given, label = dim.hole["given"], dim.hole["label"]
    call = f"{view.name}.slot({_where(dim.p1)})"
    target = proj.point(dim.p1)
    here = [sl for sl in seen if any(_near(proj.point(p), target) for p in (sl.mouth, *sl.ends))]
    if not here:
        mine = [sl for sl in seen if _faces_viewer(sl, look)]
        hint = (f"The slots it looks down are centred at {', '.join(_where(sl.mouth) for sl in mine[:6])}."
                if mine else "This view looks down no slot.")
        raise ValueError(f"{call}: no slot runs along the {view.name} view's line of sight there. {hint}")
    slot = here[0]
    if not _faces_viewer(slot, look):
        raise _far_side(call, "slot", view)
    same = [sl for sl in seen if sl.signature() == slot.signature() and _faces_viewer(sl, look)]
    problems = []
    for name, value in (("width", slot.width), ("length", slot.length)):
        if given[name] is not None and abs(given[name] - value) > 0.01:
            problems.append(f"{name}={_fmt(given[name])}")
    if given["thru"] is not None and given["thru"] != slot.thru:
        problems.append(f"thru={given['thru']}")
    if given["depth"] is not None and (slot.thru or abs(given["depth"] - slot.depth) > 0.01):
        problems.append(f"depth={_fmt(given['depth'])}")
    if given["count"] is not None and given["count"] != len(same):
        problems.append(f"count={given['count']}")
    if problems:
        raise ValueError(
            f"{call}: the part's slot reads {_shown(hole_callout_text(_slot_spec(slot, len(same))))}, but the "
            f"callout was given {', '.join(problems)}. Leave {'it' if len(problems) == 1 else 'them'} unset so "
            "the drawing states the part, or change the model."
        )
    spec = _slot_spec(slot, len(same), label)
    end = _slot_end(proj, bounds, slot)
    return replace(dim, p1=end, hole=spec, radius=_outer_radius(spec), feature=slot, covers=tuple(same))


def _expand_holes(view: View, proj, bounds, dim: "_Dim", seen, look, warnings: list | None,
                  features: _Features, slots, stated: dict) -> list["_Dim"]:
    kinds = _kinds(f for f in (*seen, *slots) if _faces_viewer(f, look))
    brk = view._break
    if brk is not None:
        # A hole the break leaves out has no circle to point at, and holes() calls out every hole the
        # view looks down: one it cannot would leave the sheet short of a hole, so it is refused.
        lost = [f for f in (*features.holes, *features.slots) if brk.low < f.mouth[brk.axis] < brk.high
                and _looks_down(f.axis, look) and _faces_viewer(f, look) and id(f) not in stated]
        if lost:
            raise ValueError(f"{view.name}.holes(): {len(lost)} hole(s) or slot(s) at "
                             f"{', '.join(_where(f.mouth) for f in lost[:6])}{', ...' if len(lost) > 6 else ''} "
                             "are inside the break, which the view leaves out; call them out in a view without "
                             f"the break, and the rest here with {view.name}.hole().")
    if not kinds:
        if warnings is not None:
            warnings.append(f"{view.name}.holes(): the {view.name} view looks down no hole or slot, so it calls "
                            "nothing out.")
        return []
    x0, x1 = bounds[0], bounds[1]

    def short_way_out(point) -> tuple:
        p = proj.point(point)
        return (round(min(p[0] - x0, x1 - p[0]), 6), -round(p[1], 6))

    out = []
    for members in kinds:
        # What a hole() or slot() states is its own; holes() calls out the rest
        # of a kind, a tapped one among identical bores taken out of the count.
        members = [member for member in members if id(member) not in stated]
        if not members:
            continue
        if isinstance(members[0], Slot):
            slot = min(members, key=lambda sl: short_way_out(_slot_end(proj, bounds, sl)))
            spec = _slot_spec(slot, len(members))
            out.append(replace(dim, kind="slot", p1=_slot_end(proj, bounds, slot), hole=spec,
                                           radius=_outer_radius(spec), feature=slot, covers=tuple(members)))
        else:
            hole = min(members, key=lambda h: short_way_out(h.mouth))
            spec = _hole_spec(hole, len(members), pcd=features.pcd(members))
            out.append(replace(dim, kind="hole", p1=hole.mouth, hole=spec, radius=_outer_radius(spec),
                                           feature=hole, covers=tuple(members)))
    return out


def _resolve_round(view: View, proj, dim: "_Dim") -> "_Dim":
    closed = dim.kind == "diameter"
    what = "circle" if closed else "arc"
    target = proj.point(dim.p1)
    radii = _radii_at(proj, target, closed_only=closed)
    stated = "" if not dim.radius else f", size={_fmt(2 * dim.radius if closed else dim.radius)}"
    call = f"{view.name}.{dim.kind}({_where(dim.p1)}{stated})"
    shown = ", ".join(("⌀" + _fmt(2 * r)) if closed else ("R" + _fmt(r)) for r in radii)
    if dim.radius:
        if not any(abs(r - dim.radius) <= 0.01 for r in radii):
            raise ValueError(f"{call}: no {what} of that size is centred there in the {view.name} view"
                             f"{f'; it shows {shown}' if radii else ''}.")
        radius = dim.radius
    elif len(radii) == 1:
        radius = radii[0]
    elif not radii:
        raise ValueError(f"{call}: no {what} is centred there in the {view.name} view. A {dim.kind} is "
                         f"stated where the feature is seen as {'a circle' if closed else 'an arc'}, at its centre.")
    else:
        raise ValueError(f"{call}: {len(radii)} {what}s share that centre ({shown}); pass size= to say "
                         "which one this states.")
    return replace(dim, radius=radius)


def _rows_beyond(dim: "_Dim", horizontal: bool, th: float, mark: str) -> int:
    """The dimension rows a dimension's frame, datum symbol and key mark take
    beyond its own. Over a level dimension the frame takes the next row and the
    datum symbol the one after; beside an upright one's value they all run
    outward, across as many rows as they are wide."""
    if horizontal:
        return (dim.frame is not None) + (dim.datum is not None)
    width = ((mark_width(mark, th) + th * 0.5 if dim.key else 0.0)
             + (frame_size(dim.frame, th)[0] + th * 0.5 if dim.frame is not None else 0.0)
             + (_DATUM_REACH * th if dim.datum is not None else 0.0))
    return max(0, math.ceil((th * 1.5 + width + 2.0) / _DIM_ROW) - 1) if width else 0


def _plan_view(view: View, proj, bounds, items: list["_Dim"], sheet: Sheet) -> dict:
    """Which side and row each dimension takes, and the room the view's annotation
    needs on each side, before anything is drawn.

    A dimension left unplaced goes on the side of the view its points are on --
    a hole pitch along the top edge above the view, a height on the right half
    to the right -- so its extension lines do not cross the part to reach the
    far side. On each side the shortest dimension sits nearest the view and the
    longest outermost, so no extension line crosses another dimension's line;
    ``overall()`` is the longest and outermost of all. The room is what
    :func:`_arrange_three_views` spaces the views by.
    """
    bx0, bx1, by0, by1 = bounds
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    th = sheet.text_height
    sv = view.scale or sheet._scale()
    explicit = dict.fromkeys(_SIDES, 0)
    # A datum feature symbol stands on its face, in the first rows out of its side.
    for _letter, point, stem in view._datums:
        side = _side_of(_datum_toward(proj.point(point), bounds, stem))
        explicit[side] = max(explicit[side], math.ceil((_DATUM_REACH * th + 2.0) / _DIM_ROW) - 1)
    mark = sheet.profile.characteristic_mark if sheet.profile is not None else "KC"
    pending: dict[str, list] = {side: [] for side in _SIDES}
    for order, dim in enumerate(items):
        if dim.kind != "linear" or dim.orientation == "aligned":
            continue  # an aligned dimension stands off its own inclined edge, in no row
        a, b = proj.point(dim.p1), proj.point(dim.p2)
        horizontal = (dim.orientation or _spans(a, b)) == "h"
        if dim.offset is not None:
            dim.side = (("top" if dim.offset >= 0 else "bottom") if horizontal
                        else ("right" if dim.offset >= 0 else "left"))
            explicit[dim.side] = max(explicit[dim.side], int(abs(dim.offset) // _DIM_ROW))
            continue
        if horizontal:
            side, span = ("top" if (a[1] + b[1]) / 2 >= cy - 1e-9 else "bottom"), abs(b[0] - a[0])
        else:
            side, span = ("right" if (a[0] + b[0]) / 2 >= cx - 1e-9 else "left"), abs(b[1] - a[1])
        pending[side].append((round(span, 6), order, dim, horizontal))
    rows: dict[str, int] = {}
    for side in _SIDES:
        row = explicit[side]
        for _span, _order, dim, horizontal in sorted(pending[side], key=lambda t: (t[0], t[1])):
            row += 1
            dim.side, dim.row = side, row
            row += _rows_beyond(dim, horizontal, th, mark)
        rows[side] = row
    overall = {}
    if "width" in view._overall:
        overall["top"] = rows["top"] + 1
    if "height" in view._overall:
        overall["left"] = rows["left"] + 1
    rows_out = {side: overall.get(side, rows[side]) for side in _SIDES}
    room = {side: (rows_out[side] * _DIM_ROW + th * 1.5) if rows_out[side] else 0.0 for side in _SIDES}
    rowed = dict(room)
    for dim in items:
        if dim.kind in ("hole", "slot", "diameter", "radius"):
            # The side a callout prefers is its hole's own half of the view, the
            # short way out, past every dimension row on that side.
            side = "right" if proj.point(dim.p1)[0] > cx + 1e-6 else "left"
            width = max(_ink_width(line, th) for line in _callout_lines(dim, th))
            if dim.frame is not None:
                width = max(width, frame_size(dim.frame, th)[0])
            room[side] = max(room[side], rowed[side] + _CALLOUT_CLEAR + _CALLOUT_LANDING + _CALLOUT_GAP
                             + width + _CALLOUT_GAP)
        elif dim.kind == "flag" and dim.p1 is not None and dim.offset is None:
            # An unplaced flag goes out by the side nearest its point.
            side = _side_of(_datum_toward(proj.point(dim.p1), bounds, None))
            room[side] = max(room[side], rowed[side] + _FLAG_SIDE * th + 12.0)
        elif dim.kind in ("note", "frame", "flag") and dim.p1 is not None:
            p = proj.point(dim.p1)
            width = 4.0 + (_text_width(dim.text, th) if dim.kind == "note" else
                           frame_size(dim.frame, th)[0] if dim.kind == "frame" else _FLAG_SIDE * th)
            if dim.radius >= 0:
                room["right"] = max(room["right"], (p[0] - bx1) * sv + dim.radius + width)
            else:
                room["left"] = max(room["left"], (bx0 - p[0]) * sv - dim.radius + width)
            if dim.angle >= 0:
                room["top"] = max(room["top"], (p[1] - by1) * sv + dim.angle + th + 1.0)
            else:
                room["bottom"] = max(room["bottom"], (by0 - p[1]) * sv - dim.angle)
    if view._balloons:
        # A column of balloons each side of a tall view, a row above and below a wide one.
        for side in (("left", "right") if _balloon_axis(bounds) else ("bottom", "top")):
            room[side] += _BALLOON_LEAD + 2 * _BALLOON_R + _BALLOON_AIR
    room["bottom"] += _LABEL_ROOM  # the view's label hangs under everything below it
    return {"rows": rows, "overall": overall, "room": room}


#: A hole table's row height and its fixed columns; SIZE is as wide as its longest entry.
_TABLE_ROW = 6.0
_TABLE_COLUMNS = (("TAG", 12.0), ("X", 20.0), ("Y", 20.0))
#: The length of the X and Y arrows marking a hole table's origin.
_ORIGIN_ARM = 10.0


class _TableRow(NamedTuple):
    """One tabulated hole or slot: its tag, its X and Y from the table's origin
    (model mm, measured on the whole part), its size as a callout reads it, the
    feature, and the arc its tag stands beside: where the view draws that arc's
    centre (a hole's, or a slot's end furthest up and right) and its radius
    (model mm)."""

    tag: str
    x: float
    y: float
    size: str
    feature: Any
    beside: tuple[float, float]
    radius: float


@dataclass
class _HoleTable:
    """A view's hole table: its rows, the model point its X and Y run from, its
    size on the sheet, and its top-left corner once placed."""

    rows: list[_TableRow]
    origin: tuple[float, float, float]
    size: tuple[float, float]
    corner: tuple[float, float] | None = None


def _hole_table(view: View, proj, features, cut, items) -> _HoleTable:
    """The holes and slots a view tabulates, tagged and measured from its origin.
    A tapped hole is tabulated with its thread where a ``hole(thread=...)`` on the
    view says so, under a letter of its own: nothing in the part says a bore is
    tapped, so the table cannot."""
    tapped = [dim for dim in items if dim.kind == "hole" and dim.hole.get("thread")]
    if any(dim.kind in ("slot", "holes") or (dim.kind == "hole" and not dim.hole.get("thread")) for dim in items):
        raise ValueError(f"the {view.name} view both tabulates its holes and calls them out; hole_table() lists "
                         "every hole the view looks down, so drop its holes(), slot() and hole() calls (a "
                         "hole(thread=...) stays: it gives the table a tapped hole's thread)")
    for dim in tapped:
        if dim.frame is not None or dim.datum is not None or dim.key:
            raise ValueError(f"{view.name}.hole({_where(dim.p1)}): a tabulated hole's row carries its size, not a "
                             "frame, a datum or a key mark; state those on a view that calls the hole out")
    look = _look(view)
    taps = {id(feature): dim for dim in tapped for feature in dim.covers}
    order = []
    for members in _kinds([*(h for h in features.holes if _looks_into(h, look) and _shows(view, proj, h, h.length, cut)),
                    *(sl for sl in features.slots if _looks_into(sl, look) and _shows(view, proj, sl, sl.run, cut))]):
        plain = [m for m in members if id(m) not in taps]
        if plain:
            order.append((plain, None))
        for dim in tapped:
            mine = [m for m in members if taps.get(id(m)) is dim]
            if mine:
                order.append((mine, dim))
    if not order:
        raise ValueError(f"{view.name}.hole_table(): the {view.name} view looks down no hole or slot")
    origin = view._table.origin if view._table.origin is not None else _lower_left(view.shape, proj)
    zero = proj._raw_point(origin)
    if len(order) > len(_SECTION_LETTERS):
        raise ValueError(f"{view.name}.hole_table(): {len(order)} kinds of hole is more than the "
                         f"{len(_SECTION_LETTERS)} letters a table tags them with")

    def middle(feature) -> tuple[float, float, float]:
        """Where a hole's axis or a slot's middle meets the face it opens in."""
        if isinstance(feature, Slot):
            return tuple((a + b) / 2 for a, b in zip(*feature.ends))
        return feature.mouth

    def beside(feature) -> tuple[float, float]:
        """The centre of the arc a tag stands beside: up and right of it, the tag
        is clear of the outline and the centre lines."""
        if isinstance(feature, Slot):
            return max((proj.point(end) for end in feature.ends), key=lambda p: p[0] + p[1])
        return proj.point(feature.mouth)

    rows = []
    for letter, (members, tap) in zip(_SECTION_LETTERS, order):
        is_slot = isinstance(members[0], Slot)
        spec = (_slot_spec(members[0], 1) if is_slot else _hole_spec(members[0], 1) if tap is None
                else dict(tap.hole, count=1, pcd=None))
        size = hole_callout_text(spec)
        radius = members[0].width / 2 if is_slot else _outer_radius(spec)
        measured = []
        for feature in members:
            at = proj._raw_point(middle(feature))
            measured.append((round(at[0] - zero[0], 6), round(at[1] - zero[1], 6), feature))
        for number, (x, y, feature) in enumerate(sorted(measured, key=lambda m: (round(m[0], 3), round(m[1], 3))),
                                                start=1):
            rows.append(_TableRow(f"{letter}{number}", x, y, size, feature, beside(feature), radius))
    width = sum(w for _n, w in _TABLE_COLUMNS) + max(28.0, max(_ink_width(r.size, 2.5) for r in rows) + 6.0)
    return _HoleTable(rows, origin, (width, (len(rows) + 1) * _TABLE_ROW))


def _lower_left(shape, proj) -> tuple[float, float, float]:
    """The corner of the part's box a view draws lowest and furthest left."""
    box = shape.bounding_box()
    corners = [(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y) for z in (box.min.Z, box.max.Z)]
    return min(corners, key=lambda c: (round(proj._raw_point(c)[0], 6), round(proj._raw_point(c)[1], 6)))


def _draw_hole_tags(msp, table: _HoleTable, proj, to_sheet, sv: float, th: float, text) -> None:
    """Each tabulated hole's tag beside it, and the origin its X and Y run from. A
    tag leans off its hole up and to the right, or, where that would print over a
    tag already placed (holes close together at the sheet's scale), off the next
    corner round that is clear, and failing all four, a tag's height further out."""
    from ezdxf.enums import TextEntityAlignment as A

    from cadgen._internal.drawing_render import _text_box

    placed: list[tuple[float, float, float, float]] = []
    corners = [(1, 1, A.BOTTOM_LEFT), (-1, 1, A.BOTTOM_RIGHT), (1, -1, A.TOP_LEFT), (-1, -1, A.TOP_RIGHT)]
    for row in table.rows:
        c, r = to_sheet(row.beside), row.radius * sv
        tries = [(r * 0.71 + 0.8 + 2.5 * ring, sx, sy, align) for ring in range(4) for sx, sy, align in corners]
        boxes = [(_text_box(row.tag, c[0] + sx * lean, c[1] + sy * lean, 2.5, align), lean, sx, sy, align)
                 for lean, sx, sy, align in tries]
        box, lean, sx, sy, align = next((b for b in boxes if not any(
            b[0][0] < q[2] and q[0] < b[0][2] and b[0][1] < q[3] and q[1] < b[0][3] for q in placed)), boxes[0])
        placed.append(box)
        text(row.tag, c[0] + sx * lean, c[1] + sy * lean, 2.5, align, "DIM")
    o = to_sheet(proj.point(table.origin))
    # The arrows often lie along the part's edges, so each letter stands off its
    # arrow's tip on the far side of the corner, clear of those edges.
    x_tip, y_tip = (o[0] + _ORIGIN_ARM, o[1]), (o[0], o[1] + _ORIGIN_ARM)
    for tip in (x_tip, y_tip):
        msp.add_leader([tip, o], dxfattribs={"layer": "DIM"},
                       override={"dimasz": th * 0.7, "dimldrblk": "_CLOSEDFILLED"})
    text("X", x_tip[0], x_tip[1] - 1.0, 2.5, A.TOP_CENTER, "DIM")
    text("Y", y_tip[0] - 1.0, y_tip[1], 2.5, A.MIDDLE_RIGHT, "DIM")
    text("0,0", o[0] - 1.0, o[1] - 1.0, 2.5, A.TOP_RIGHT, "DIM")


def _draw_hole_table(msp, table: _HoleTable, text) -> None:
    """The table itself, header on top: TAG, X, Y, SIZE."""
    from ezdxf.enums import TextEntityAlignment as A

    x0, y1 = table.corner
    w, h = table.size
    columns = list(_TABLE_COLUMNS) + [("SIZE", w - sum(cw for _n, cw in _TABLE_COLUMNS))]
    msp.add_lwpolyline([(x0, y1), (x0 + w, y1), (x0 + w, y1 - h), (x0, y1 - h)], close=True,
                       dxfattribs={"layer": "TITLE"})
    for r in range(1, len(table.rows) + 1):
        msp.add_line((x0, y1 - r * _TABLE_ROW), (x0 + w, y1 - r * _TABLE_ROW), dxfattribs={"layer": "TITLE"})
    x = x0
    for c, (name, width) in enumerate(columns):
        if c:
            msp.add_line((x, y1), (x, y1 - h), dxfattribs={"layer": "TITLE"})
        text(name, x + width / 2, y1 - _TABLE_ROW / 2, _CAPTION_HEIGHT, A.MIDDLE_CENTER, fit=width - 2)
        for r, row in enumerate(table.rows, start=1):
            value = (row.tag, _fmt(row.x), _fmt(row.y), row.size)[c]
            mid = y1 - (r + 0.5) * _TABLE_ROW
            if c == 3:
                text(value, x + 2.0, mid, 2.5, A.MIDDLE_LEFT, "NOTES")
            else:
                text(value, x + width / 2, mid, 2.5, A.MIDDLE_CENTER, fit=width - 2)
        x += width
