"""The manufacturing check of exact geometry: what ``cad.<type>.dfm(source, process=...)`` runs for a
STEP, an xbf or a document the engine holds, once its options are resolved (``cad._internal.manufacturing``),
and what ``cad.build123d.cnc(shape)`` and its siblings run for a live shape.

The document is read as the engine reads it (``_dfm_brep.read``); the process's module measures it
(``_dfm_cnc``, ``_dfm_sheet``, ``_dfm_molding``, ``_dfm_printing``: each ``measure(document, options,
candidates)``, a report of plain data, facts alone); the type side makes the result of the report: the
process's findings and the rule set's verdicts (``manufacturing.finish``). Given no process
(``measure_declared``), the document is read first and measured for the process its parts declare, the
options resolved for it then (``manufacturing.declared``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from cad.build123d import _dfm_brep

__all__ = ["checked", "measure", "measure_declared"]


def _measured(document: _dfm_brep.Document, document_type: str, process: str, options: dict[str, Any],
              candidates: bool) -> dict[str, Any]:
    from cad._internal.dfm import Unmeasured

    if not document.parts:
        raise Unmeasured("document_empty", "the document holds no part with a face to measure")
    module = importlib.import_module(f"cad.build123d._dfm_{process}")
    report = module.measure(document, options, candidates)
    found = list(report.pop("findings", None) or ())
    if document.empty:
        shown = ", ".join(document.empty[:8]) + (f" and {len(document.empty) - 8} more" if len(document.empty) > 8 else "")
        found.append({"severity": "info", "code": "empty_parts", "location": document.empty[0],
                      "message": f"{len(document.empty)} part(s) hold no face and were not measured: {shown}"})
    return {"source": {"type": document_type, "measured_as": "brep", "document": document.name},
            "document": document.facts(), "bodies": [part.facts() for part in document.parts], **report,
            **({"findings": found} if found else {})}


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The report of ``source`` (a STEP's or an xbf's path, a document's id or handle) for ``process``, or
    ``Unmeasured``; ``cad.engine.serve.NotHeld`` for a document id the engine does not hold."""
    return _measured(_dfm_brep.read(document_type, source), document_type, process, options, candidates)


def _declared(document: _dfm_brep.Document, document_type: str, given: dict[str, Any], candidates: bool,
              measured_as: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The process ``document``'s parts declare, the options resolved for it, and the report, which says what
    was read (``process_declared``)."""
    from cad._internal import manufacturing
    from cad._internal.dfm import Unmeasured

    if not document.parts:
        raise Unmeasured("document_empty", "the document holds no part with a face to measure")
    process, resolved, said = manufacturing.declared(
        document_type, [(part.owner or part.name, part.material) for part in document.parts], given,
        candidates=candidates)
    report = _measured(document, measured_as, process, resolved, candidates)
    report["findings"] = [*(report.get("findings") or ()), said]
    return process, resolved, report


def measure_declared(document_type: str, source: Any, given: dict[str, Any],
                     candidates: bool) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """``measure`` with no process given: ``source`` read first, then measured for the process its parts
    declare, its options (``given``, unresolved) resolved for that process (``manufacturing.declared``).
    The process, the options and the report; ``Unmeasured``, or ``ArgumentRefused`` naming the fix for no
    process declared, one no check measures, parts that declare different ones, or an option the declared
    process does not take; ``cad.engine.serve.NotHeld`` for a document id the engine does not hold."""
    return _declared(_dfm_brep.read(document_type, source), document_type, given, candidates, document_type)


def checked(shape: Any, process: str | None, given: dict[str, Any], *, candidates: bool = False,
            name: str | None = None) -> Any:
    """The check of a live build123d shape, as a ``CheckResult``: its options resolved as a STEP's are, its
    findings at refs of the document the engine would make of it. With no ``process``, the one its parts
    declare (``manufacturing.declared``)."""
    from cad._internal import manufacturing
    from cad._internal.dfm import Unmeasured

    if process is None:
        # A live shape keeps its parts' materials, as a model's document does (a STEP does not): read as a model's.
        manufacturing.options("model", None, given, candidates=candidates)
        document = _dfm_brep.parts_of(shape, name=name)
        label = Path(document.name or "shape")
        try:
            process, resolved, measured = _declared(document, "step", given, candidates, "shape")
        except Unmeasured as failure:
            return manufacturing._failed(label, failure.message, failure.code)
        return manufacturing.finish(label, {"process": process, **measured}, process, resolved, candidates)
    resolved = manufacturing.options("step", process, given, candidates=candidates)
    assert resolved is not None
    document = _dfm_brep.parts_of(shape, name=name)
    report = {"process": process, **_measured(document, "shape", process, resolved, candidates)}
    return manufacturing.finish(Path(document.name or "shape"), report, process, resolved, candidates)


def cnc(shape: Any, *, rules: str | None = None, material: str | None = None, axes: int | None = None,
        turning: bool = False, tools: str | None = None, stock: str | None = None) -> Any:
    """CNC machining's check of ``shape`` (a build123d ``Shape``; an assembly's every part): a ``CheckResult``
    whose findings are at refs (``plate/face 7``) and whose ``measurements`` is the report -- the options are
    ``cad.step.dfm``'s for ``process="cnc"``."""
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
