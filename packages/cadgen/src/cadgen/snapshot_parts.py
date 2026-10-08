"""A STEP snapshot's parts, as Python knows them: what ``focus``/``hide`` keep.

``focus``/``hide`` select the same way the page's scene does for a view: an
occurrence matches a ref that IS its id, an ancestor group's id (``o1.2``
covers ``o1.2.3``), or its name. The rows are
:func:`cadgen.assembly_lookup.assembly_occurrence_rows`, the ones every
selector resolves against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["filter_occurrences"]


def _selector_values(value: object) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").split(",")
    out = []
    for item in values:
        text = str(item or "").strip()
        text = text[1:] if text.startswith("#") else text
        out.extend(part.strip() for part in text.split(",") if part.strip())
    return out


def _matches(row: Mapping[str, Any], selector: str) -> bool:
    occurrence_id = str(row.get("id") or "")
    if occurrence_id == selector or occurrence_id.startswith(f"{selector}."):
        return True
    return str(row.get("name") or "") == selector


def filter_occurrences(rows: Sequence[Mapping[str, Any]], selection: Mapping[str, Any] | None) -> list:
    """The rows ``selection``'s focus keeps and its hide does not remove.

    Raises ``ValueError`` when nothing is left: an empty picture is never the
    answer to a selection.
    """
    selection = selection if isinstance(selection, Mapping) else {}
    focus = _selector_values(selection.get("focus"))
    hide = _selector_values(selection.get("hide"))
    if not focus and not hide:
        return list(rows)
    kept = [
        row for row in rows
        if (not focus or any(_matches(row, selector) for selector in focus))
        and not any(_matches(row, selector) for selector in hide)
    ]
    if not kept:
        raise ValueError("No renderable parts remain after applying focus/hide filters")
    return kept
