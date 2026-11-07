"""The study file's primitives: a number, a list of faces, a short label, each refused in words that name the field.

The study and the materials say an error the same way through these. Stdlib only.
"""

from __future__ import annotations

import json
import math
from typing import Any

__all__ = ["faces", "json_text", "number", "text"]


def json_text(value: Any) -> str:
    """A value as the JSON an agent wrote it: true, null, "text", not Python's True, None, 'text'."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def number(value: Any, *, where: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {json_text(value)}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{where}: expected a finite number, got {result}")
    if positive and not result > 0:
        raise ValueError(f"{where}: must be > 0, got {result}")
    return result


def faces(entry: dict, *, where: str) -> tuple[str, ...]:
    refs = entry.get("faces")
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not refs or not all(isinstance(f, str) and f.strip() for f in refs):
        raise ValueError(f"{where}: 'faces' must be a non-empty list of face references like \"bracket/face 17\"")
    return tuple(f.strip() for f in refs)


def text(entry: dict, key: str, *, where: str) -> dict:
    if key not in entry:
        return {}
    if not isinstance(entry[key], str) or not entry[key].strip():
        raise ValueError(f"{where}.{key}: expected a short piece of text")
    return {key: entry[key].strip()}
