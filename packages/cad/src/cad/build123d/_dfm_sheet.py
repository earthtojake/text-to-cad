"""sheet's measurements of exact geometry (``cad._internal.dfm.sheet`` says what they are for)."""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import Unmeasured
from cad.build123d import _dfm_brep

__all__ = ["measure"]


def measure(document: _dfm_brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The sheet report of ``document``: facts alone, every family's ``items`` at a ref."""
    raise Unmeasured("not_measured", "the sheet measurements of exact geometry are not written yet")
