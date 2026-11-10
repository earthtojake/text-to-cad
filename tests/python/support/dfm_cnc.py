"""What the CNC check's tests share: the check of a part written to STEP, a part named, a pocket cut, and
the codes a result says (``tests/python/packages/cad/test_dfm_cnc_*.py``)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import build123d as bd

import cad.step

A = bd.Align


def _check(shape: Any, **options: Any) -> Any:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "part.step"
        bd.export_step(shape, str(path))
        return cad.step.dfm(path, process="cnc", **options)


def _part(shape: Any, label: str = "part") -> Any:
    shape.label = label
    return shape


def _pocket(length: float, width: float, depth: float, radius: float, top: float) -> Any:
    cut = bd.Box(length, width, depth + 1, align=(A.CENTER, A.CENTER, A.MIN))
    if radius > 0:
        cut = bd.fillet(cut.edges().filter_by(bd.Axis.Z), radius)
    return bd.Pos(0, 0, top - depth) * cut


def _codes(result: Any) -> set[str]:
    return {finding.code for finding in result.findings}


def _judged(result: Any) -> set[str]:
    return {finding.code for finding in result.findings if finding.severity in ("error", "warning")}
