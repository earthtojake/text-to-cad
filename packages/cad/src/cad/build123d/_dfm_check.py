"""The manufacturing check of exact geometry: what ``cad.<type>.check(source, process=...)`` runs for a
STEP, an xbf or a document the engine holds, once its options are resolved (``cad._internal.manufacturing``),
and what ``cad.build123d.cnc(shape)`` and its siblings run for a live shape.

The document is read as the engine reads it (``_dfm_brep.read``); the process's module measures it
(``_dfm_cnc``, ``_dfm_sheet``, ``_dfm_molding``, ``_dfm_printing``: each ``measure(document, options,
candidates)``, a report of plain data, facts alone); the type side makes the result of the report: the
process's findings and the rule set's verdicts (``manufacturing.finish``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from cad.build123d import _dfm_brep

__all__ = ["checked", "measure"]


def _measured(document: _dfm_brep.Document, document_type: str, process: str, options: dict[str, Any],
              candidates: bool) -> dict[str, Any]:
    module = importlib.import_module(f"cad.build123d._dfm_{process}")
    report = module.measure(document, options, candidates)
    return {"source": {"type": document_type, "measured_as": "brep", "document": document.name},
            "document": document.facts(), "bodies": [part.facts() for part in document.parts], **report}


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The report of ``source`` (a STEP's or an xbf's path, a document's id or handle) for ``process``, or
    ``Unmeasured``."""
    return _measured(_dfm_brep.read(document_type, source), document_type, process, options, candidates)


def checked(shape: Any, process: str, given: dict[str, Any], *, candidates: bool = False,
            name: str | None = None) -> Any:
    """The check of a live build123d shape, as a ``CheckResult``: its options resolved as a STEP's are, its
    findings at refs of the document the engine would make of it."""
    from cad._internal import manufacturing

    resolved = manufacturing.options("step", process, given, candidates=candidates)
    document = _dfm_brep.parts_of(shape, name=name)
    report = {"process": process, **_measured(document, "shape", process, resolved, candidates)}
    return manufacturing.finish(Path(document.name or "shape"), report, process, resolved, candidates)


def cnc(shape: Any, *, rules: str | None = None, material: str | None = None, axes: int | None = None,
        turning: bool = False, tools: str | None = None, stock: str | None = None) -> Any:
    """CNC machining's check of ``shape`` (a build123d ``Shape``; an assembly's every part): a ``CheckResult``
    whose findings are at refs (``plate/face 7``) and whose ``measurements`` is the report -- the options are
    ``cad.step.check``'s for ``process="cnc"``."""
    return checked(shape, "cnc", {"rules": rules, "material": material, "axes": axes, "turning": turning,
                                  "tools": tools, "stock": stock})


def sheet_metal(shape: Any, *, rules: str | None = None, material: str | None = None,
                thickness: float | None = None, k_factor: float | None = None, bend_radius: float | None = None,
                kerf: float | None = None, sheet_size: str | None = None) -> Any:
    """Sheet metal's check of ``shape``, as ``cnc``'s (``process="sheet"``)."""
    return checked(shape, "sheet", {"rules": rules, "material": material, "thickness": thickness,
                                    "k_factor": k_factor, "bend_radius": bend_radius, "kerf": kerf,
                                    "sheet_size": sheet_size})


def molding(shape: Any, *, rules: str | None = None, material: str | None = None, pull: str | None = None,
            wall_limit: float | None = None, zero_tol: float | None = None, cavities: int | None = None,
            candidates: bool = False) -> Any:
    """Injection molding's check of ``shape``, as ``cnc``'s (``process="molding"``)."""
    return checked(shape, "molding", {"rules": rules, "material": material, "pull": pull,
                                      "wall_limit": wall_limit, "zero_tol": zero_tol, "cavities": cavities},
                   candidates=candidates)


def printing(shape: Any, *, rules: str | None = None, material: str | None = None, technology: str | None = None,
             build_volume: str | None = None, angle_limit: float | None = None, layer_height: float | None = None,
             nozzle: float | None = None, candidates: bool = False) -> Any:
    """3D printing's check of ``shape``, as ``cnc``'s (``process="printing"``)."""
    return checked(shape, "printing", {"rules": rules, "material": material, "technology": technology,
                                       "build_volume": build_volume, "angle_limit": angle_limit,
                                       "layer_height": layer_height, "nozzle": nozzle}, candidates=candidates)
