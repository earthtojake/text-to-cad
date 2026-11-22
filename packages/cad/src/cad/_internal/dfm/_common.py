"""What the processes' options, findings and summaries share: an option's kind, a place, a figure, the
measurement's own findings."""

from __future__ import annotations

import math
import re
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding

__all__ = ["ANGLE_EPS", "KNIFE_DEG", "UNITS_LARGE_MM", "UNITS_SMALL_MM", "first_error", "memory_passed", "mm",
           "not_applicable", "occurrence_count", "occurrences", "out_of_memory", "partial_findings", "passed_over", "require", "require_bool",
           "require_finite", "require_int", "require_text", "scale_findings", "units_doubt", "where"]

#: Every process's: a convex edge whose material angle is under this many degrees is a **knife edge**, not a
#: corner (printing's and CNC's ``knife_edges``). The
#: material at distance ``d`` from an edge of angle ``a`` is ``2 d tan(a / 2)`` thick, so it is thinner than a
#: minimum wall ``t`` for ``t / (2 tan(a / 2))`` from the edge: half a wall at a box's 90 deg corner (the one
#: bead every corner is), 1.2 walls at 45 deg, 1.9 at 30, 5.7 at 10 -- past 45 deg the sliver under the
#: minimum is deeper than a whole wall, which a printer cannot lay. 45 deg is also the slope the guides
#: (Hubs FDM) hold self-supporting: a chamfer of 45 deg or more leaves no knife edge.
KNIFE_DEG = 45.0

#: An angle within this many degrees of a limit is at the limit, not under it: a 45 deg chamfer the kernel
#: makes reads 44.999999999999936 on one axis and 45.000000000000014 on the other, and both are 45 (Hubs FDM:
#: "up to 45°" self-supports). Every comparison of a surface's angle with a limit subtracts it.
ANGLE_EPS = 1e-6

#: A part under this across (its box's diagonal, mm) is implausible for anything these processes make: it is
#: probably drawn in metres or inches and read as millimetres.
UNITS_SMALL_MM = 1.0
#: A part over this across is made in one piece by none of them: the largest standard sheet is 3048 x 1524
#: (3.4 m across), gantry mills and large-format printers reach a few metres, a molded part rarely one. It is
#: probably a thousand times too large (micrometres, or millimetres read as metres).
UNITS_LARGE_MM = 10_000.0


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def require_int(name: str, value: Any) -> int:
    """``value``, a count or a whole number: an ``int``, never a ``bool`` (``True`` is no count) nor a float
    (``3.7`` axes are not taken as 3); ``ArgumentRefused`` naming the flag else (laws 15, 16)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgumentRefused(f"{_flag(name)} is a whole number, not {value!r}")
    return value


def require_bool(name: str, value: Any) -> bool:
    """``value``, a flag: ``True`` or ``False``, never a truthy word (``"no"``) or number;
    ``ArgumentRefused`` naming the flag else."""
    if not isinstance(value, bool):
        raise ArgumentRefused(f"{_flag(name)} is true or false, not {value!r}")
    return value


def require_finite(name: str, value: Any) -> float:
    """``value``, a length, an angle or a ratio: a finite number (an ``int`` or a ``float``, never a ``bool``,
    NaN or infinity); ``ArgumentRefused`` naming the flag else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ArgumentRefused(f"{_flag(name)} is a finite number, not {value!r}")
    return float(value)


def require_text(name: str, value: Any) -> str:
    """``value``, text (a name, a list or a size written out: ``3,6,10``, ``100x60x25``); ``ArgumentRefused``
    naming the flag else."""
    if not isinstance(value, str):
        raise ArgumentRefused(f"{_flag(name)} is text, not {value!r}")
    return value


_REQUIRED = {int: require_int, bool: require_bool, float: require_finite, str: require_text}


def require(kind: type, name: str, value: Any) -> Any:
    """``value`` checked as an option of ``kind`` (``int``, ``bool``, ``float``, ``str``) by the helper above."""
    return _REQUIRED[kind](name, value)


def where(xyz: Any) -> str | None:
    """``x, y, z`` in millimetres, or None."""
    return ", ".join(f"{float(value):g}" for value in xyz) if xyz else None


def mm(value: Any) -> str:
    return "-" if value is None else f"{value:g}"


def not_applicable(item: dict[str, Any], *fields: str) -> None:
    """``item`` says these figures do not apply to it (its ``not_applicable``): a rule that reads one asks nothing
    of the item, where a figure merely missing was not measured and is said (``rules``). For a figure that
    cannot exist of the item -- a lone rib's gap to a neighbour, an open step's width -- never for one that
    could not be read."""
    named = item.setdefault("not_applicable", [])
    named.extend(field for field in fields if field not in named)


def occurrences(report: dict[str, Any]) -> dict[str, int]:
    """How many times each part measured occurs, by its ref's owner (``bodies``: the occurrences turned alike are
    measured once and counted): what a total of a family's items multiplies by."""
    return {str(body.get("owner") or ""): int(body.get("occurrences") or 1)
            for body in report.get("bodies") or () if isinstance(body, dict)}


def occurrence_count(report: dict[str, Any]) -> int:
    """The parts as made: every occurrence of every part measured."""
    return sum(occurrences(report).values())


#: How a failure for want of memory names itself, whoever raised it: Python's ``MemoryError``, the kernel's
#: ``Standard_OutOfMemory``, a C++ ``bad_alloc``, a system's or a library's own words for it.
_OUT_OF_MEMORY = re.compile(r"memoryerror|out\s*of\s*memory|bad_alloc|(cannot allocate|not enough|insufficient) memory",
                            re.IGNORECASE)


def out_of_memory(failure: Any) -> bool:
    """Whether ``failure`` -- an exception, or the words one was said in (a family's ``error``: its type and its
    words) -- is a failure for want of memory, by any of its names (``_OUT_OF_MEMORY``): an exception's own, or
    those of the one it was raised from or while handling (a kernel's ``MemoryError`` said again as a
    ``GeometryError``). What failed so may not fail the next time: nothing measured through it is the part's
    alone."""
    if not isinstance(failure, BaseException):
        return _OUT_OF_MEMORY.search(str(failure)) is not None
    seen: set[int] = set()
    while failure is not None and id(failure) not in seen:
        seen.add(id(failure))
        if isinstance(failure, MemoryError) or _OUT_OF_MEMORY.search(f"{type(failure).__name__}: {failure}"):
            return True
        failure = failure.__cause__ or failure.__context__
    return False


#: The failures for want of memory a measurement caught and went on past, in this process, so far
#: (``passed_over``): a figure it then took another way, or left out, may come out otherwise the next time.
_PASSED = [0]


def passed_over(error: BaseException) -> None:
    """``error``, caught where a measurement goes on without what raised it, counted where it was a failure for
    want of memory (``out_of_memory``): what was measured meanwhile is kept nowhere (``memory_passed``)."""
    if out_of_memory(error):
        _PASSED[0] += 1


def memory_passed() -> int:
    """How many failures for want of memory this process's measurements caught and went on past so far
    (``passed_over``): a measurement that saw the count rise is not one to keep."""
    return _PASSED[0]


def first_error(value: Any) -> str | None:
    if isinstance(value, dict):
        if "error" in value:
            return str(value["error"])
        return next((found for item in value.values() if (found := first_error(item))), None)
    if isinstance(value, list):
        return next((found for item in value if (found := first_error(item))), None)
    return None


def partial_findings(report: dict[str, Any]) -> list[CheckFinding]:
    """An error for each family the measurement could not measure."""
    return [CheckFinding("error", "measurement_failed", f"{family} was not measured: {first_error(report[family])}",
                         family) for family in report.get("partial_sections") or []]


def units_doubt(diagonal: float, reading: str) -> dict[str, Any]:
    """``units_suspect`` and its ``note`` for a part ``diagonal`` mm across, ``reading`` saying how its unit was
    read (``"the STEP declares its unit and it reads"``): suspect under ``UNITS_SMALL_MM`` or over
    ``UNITS_LARGE_MM``, the note offering only the readings that would make it a plausible size. The same for
    every process and every source."""
    if not math.isfinite(diagonal) or UNITS_SMALL_MM <= diagonal <= UNITS_LARGE_MM:
        return {"units_suspect": False, "note": f"{reading} {diagonal:.4g} mm across: a plausible size"}
    small = diagonal < UNITS_SMALL_MM
    readings = ((("metres", 1000.0), ("inches", 25.4), ("centimetres", 10.0)) if small else
                (("micrometres, or millimetres read as metres", 1e-3), ("millimetres read as inches", 1 / 25.4),
                 ("millimetres read as centimetres", 0.1)))
    fits = [(name, f"{diagonal * factor:.4g} mm") for name, factor in readings
            if UNITS_SMALL_MM <= diagonal * factor <= UNITS_LARGE_MM]
    size = "small" if small else "large"
    if fits:
        found = "it is probably drawn in " + ", or ".join(f"{name} ({value} if so)" for name, value in fits) + \
            " -- scale it to millimetres, then check again"
    else:
        found = "no unit read as millimetres makes it a plausible size: check the unit it was drawn in"
    return {"units_suspect": True,
            "note": f"{reading} {diagonal:.6g} mm across, implausibly {size} for a made part: {found}"}


def scale_findings(report: dict[str, Any]) -> list[CheckFinding]:
    scale = report.get("scale") or {}
    if scale.get("units_suspect"):
        return [CheckFinding("warning", "units_suspect", scale["note"], "scale")]
    return []
