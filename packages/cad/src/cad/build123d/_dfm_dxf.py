"""A sheet's cut file (a DXF), checked with ezdxf, build123d's own DXF library (``cad._internal.dfm.sheet``)."""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import Unmeasured

__all__ = ["measure"]


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The cut-file report of the DXF ``source``: facts alone."""
    raise Unmeasured("not_measured", "the cut-file measurements are not written yet")
