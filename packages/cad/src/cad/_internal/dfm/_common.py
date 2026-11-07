"""What the processes' options, findings and summaries share: an option's kind, a place, a figure, the
measurement's own findings."""

from __future__ import annotations

import math
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding

__all__ = ["first_error", "mm", "partial_findings", "require", "require_bool", "require_finite", "require_int",
           "require_text", "scale_findings", "where"]


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def require_int(name: str, value: Any) -> int:
    """``value``, a count or a whole number: an ``int``, never a ``bool`` (``True`` is no count) nor a float
    (``3.7`` axes are not taken as 3); ``ArgumentRefused`` naming the flag else (laws 16, 17)."""
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


def scale_findings(report: dict[str, Any]) -> list[CheckFinding]:
    scale = report.get("scale") or {}
    if scale.get("units_suspect"):
        return [CheckFinding("warning", "units_suspect", scale["note"], "scale")]
    return []
