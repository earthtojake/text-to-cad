"""What the processes' findings and summaries share: a place, a figure, the measurement's own findings."""

from __future__ import annotations

from typing import Any

from cad.results import CheckFinding

__all__ = ["first_error", "mm", "partial_findings", "scale_findings", "where"]


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
