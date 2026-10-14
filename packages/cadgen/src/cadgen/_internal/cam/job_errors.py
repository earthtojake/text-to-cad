"""The job's teaching errors and the small validators every parser shares (job, tools, operations).

A :class:`CamJobError` is a job that cannot run, said in one plain sentence that names what to add or change and,
for a closed vocabulary, the allowed set (law 9). ``cadgen cam plan`` turns it into ``ok: false`` with one error
finding of type ``job``; nothing is written. Stdlib only.
"""

from __future__ import annotations

import difflib
import math
from collections.abc import Iterable

__all__ = ["CamJobError", "LARGEST", "MAX_LEVELS", "PLAN_ERROR_KINDS", "PlanError", "PlanTooBig", "PostRefusal",
           "check_keys", "choice", "is_number", "level_count", "number_words", "read_number", "shown"]

#: The largest number any job key takes unless it names its own maximum: a million (a kilometre in mm, a million
#: rpm or mm/min). Past it a number is a typo or a fuzz, never a part, and the engine's arithmetic stops being exact.
LARGEST = 1e6


class CamJobError(ValueError):
    """A job that cannot run: malformed, an unknown key or value, a missing tool, a face that does not exist, an
    operation the machine cannot do. The message is the whole answer."""


class PlanTooBig(CamJobError):
    """An operation that would plan more depth levels or moves than any program runs (a stepdown of a thousandth of
    a millimetre, a region a kilometre wide): refused rather than left to fill the memory. The run names the
    operation in front of the message."""


#: What an operation that cannot be planned says it is: a closed set, each a finding ``type`` (the skill's checks page
#: lists them). ``empty_operation``: it would cut nothing; ``too_deep``: it would cut below what the part allows;
#: ``unreachable``: the tool cannot get there from this setup (or come down there); ``tool_too_large`` and
#: ``tool_too_small``: the tool does not suit the feature; ``gouge``: the only path it has goes into the part.
PLAN_ERROR_KINDS = ("empty_operation", "too_deep", "unreachable", "tool_too_large", "tool_too_small", "gouge")


class PlanError(CamJobError):
    """An operation the job asks for that cannot be planned on this part, of a known ``kind``
    (:data:`PLAN_ERROR_KINDS`). The run turns it into an error finding of that type on the operation, plans every
    other operation, and posts no G-code; anywhere else (a library call) it is the job error it subclasses."""

    def __init__(self, kind: str, message: str):
        if kind not in PLAN_ERROR_KINDS:
            raise ValueError(f"PlanError kind {kind!r} is not one of {', '.join(PLAN_ERROR_KINDS)}")
        super().__init__(message)
        self.kind = kind


class PostRefusal(CamJobError):
    """What the job needs that the named post cannot write (a tap on a controller with no spindle-synchronised feed, a
    helix on one without helical arcs): said in one sentence naming the post and what to change, with the global
    ``operation`` index it is about (None when it is the whole program). The run turns it into a ``no_post_support``
    error finding on that operation and posts no G-code; the plan and its GLB still stand."""

    def __init__(self, message: str, *, operation: int | None = None):
        super().__init__(message)
        self.operation = operation


#: The most depth levels one operation cuts: 200 mm at a tenth of a millimetre each. Each level is a section of the
#: part and a set of rings, tens of milliseconds: past this an operation plans for minutes.
MAX_LEVELS = 2_000


def level_count(top: float, bottom: float, stepdown: float) -> int:
    """How many even levels take ``top`` down to ``bottom`` none deeper than ``stepdown``; :class:`PlanTooBig` past
    :data:`MAX_LEVELS`."""
    if stepdown <= 0:
        raise CamJobError("stepdown_mm must be more than 0")
    count = max(1, int(math.ceil((top - bottom) / stepdown - 1e-9)))
    if count > MAX_LEVELS:
        raise PlanTooBig(f"{top - bottom:g} mm of depth at a {stepdown:g} mm stepdown is {count:,} levels, and an "
                         f"operation cuts at most {MAX_LEVELS:,}: raise stepdown_mm, or check the depth (bottom_z, "
                         "depth_mm) is in the stock")
    return count


def _suggest(value: str, allowed: Iterable[str]) -> str:
    close = difflib.get_close_matches(value, list(allowed), n=1)
    return f" (did you mean '{close[0]}'?)" if close else ""


def check_keys(raw: dict, allowed: Iterable[str], where: str, *, hint: str = "") -> None:
    """Refuse any key outside ``allowed``, naming the allowed set."""
    allowed = tuple(allowed)
    for key in raw:
        if key not in allowed:
            what = f" for {hint}" if hint else ""
            raise CamJobError(f"{where}: unknown key {shown(str(key))}{_suggest(str(key), allowed)}; the keys{what} are "
                              f"{', '.join(allowed)}")


def choice(value: object, allowed: Iterable[str], where: str) -> str:
    """``value`` when it is one of ``allowed``, else the teaching error naming them."""
    allowed = tuple(allowed)
    if not isinstance(value, str) or value not in allowed:
        what = "nothing" if value is None else shown(value)
        suggestion = _suggest(value, allowed) if isinstance(value, str) else ""
        raise CamJobError(f"{where} is {what}{suggestion}; use one of {', '.join(allowed)}")
    return value


def is_number(value: object) -> bool:
    """Whether ``value`` is a finite int or float (never a bool; an int too big for a float is not)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def number_words(value: float) -> str:
    """``1,000,000`` for a whole number, else ``0.25``."""
    return f"{value:,.0f}" if float(value).is_integer() and abs(value) < 1e15 else f"{value:g}"


def read_number(raw: dict, key: str, where: str, *, default=None, minimum: float | None = None,
                maximum: float | None = None, inclusive: bool = False):
    """``raw[key]`` as a float. Absent: ``default`` as given. Present: a finite number, more than 0 (or at least
    ``minimum`` when one is given), at most ``maximum`` (:data:`LARGEST` when none is given)."""
    if key not in raw:
        return default
    value = raw[key]
    if not is_number(value):
        raise CamJobError(f"{where}.{key} must be a number, not {shown(value)}")
    value = float(value)
    if minimum is None:
        if value <= 0 and not inclusive:
            raise CamJobError(f"{where}.{key} must be more than 0, not {value:g}")
    elif value < minimum:
        raise CamJobError(f"{where}.{key} must be at least {minimum:g}, not {value:g}")
    maximum = LARGEST if maximum is None else maximum
    if value > maximum:
        raise CamJobError(f"{where}.{key} must be at most {number_words(maximum)}, not {value:g}")
    return value


def shown(value: object) -> str:
    """``value`` for a teaching error, cut short when it is long (a fuzzed job can hold anything)."""
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def number_list(value: object, where: str, *, length: int | tuple[int, ...], positive: bool = False) -> tuple[float, ...]:
    """A list of ``length`` finite numbers (one of several lengths when a tuple is given), each within
    :data:`LARGEST` of 0."""
    lengths = (length,) if isinstance(length, int) else length
    if not isinstance(value, (list, tuple)) or len(value) not in lengths or not all(is_number(v) for v in value):
        raise CamJobError(f"{where} must be a list of {' or '.join(str(n) for n in lengths)} numbers, not "
                          f"{shown(value)}")
    if any(abs(v) > LARGEST for v in value):
        raise CamJobError(f"{where} must hold numbers between -{number_words(LARGEST)} and {number_words(LARGEST)}, "
                          f"not {shown(value)}")
    out = tuple(float(v) for v in value)
    if positive and any(v <= 0 for v in out):
        raise CamJobError(f"{where} must hold numbers more than 0, not {shown(value)}")
    return out
