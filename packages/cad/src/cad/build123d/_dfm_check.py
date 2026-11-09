"""The manufacturing check of exact geometry: what ``cad.<type>.dfm(source, process=...)`` runs for a
STEP, an xbf or a document the engine holds, once its options are resolved (``cad._internal.manufacturing``)
-- in the engine's kernel process that holds the document (``held``), or in this process where no engine
can be reached (``measure``) -- and what ``cad.build123d.cnc(shape)`` and its siblings run for a live shape.

The document is read as the engine reads it (``_dfm_brep.read``); the process's module measures it
(``_dfm_cnc``, ``_dfm_sheet``, ``_dfm_molding``, ``_dfm_printing``: each ``measure(document, options,
candidates)``, a report of plain data, facts alone); the type side makes the result of the report: the
process's findings and the rules' verdicts (``manufacturing.finish``). Given no process
(``measure_declared``), the document is read first and measured for the process its parts declare, the
options resolved for it then (``manufacturing.declared``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np

from cad._internal.dfm import Cancelled, checkpoint, stop  # what the engine's worker stops a check by
from cad.build123d import _dfm_brep

__all__ = ["Cancelled", "checked", "checkpoint", "held", "measure", "measure_declared", "stop"]


#: A solid of less volume than this fraction of its box's diagonal cubed holds no material: zero volume.
_ZERO_VOLUME = 1e-9
#: A document whose box's diagonal is under this many millimetres is implausibly small for a made part:
#: drawn in metres or inches as millimetres (build123d has no unit; a model's millimetre is its unit).
_PLAUSIBLE_DIAGONAL_MM = 1.0


def _closed_solids(part: _dfm_brep.Part) -> tuple[list[Any], list[Any], int]:
    """The part's solids whose every shell is closed and whose volume is not zero, its other solids, and the
    faces it holds outside any solid (a free face or shell beside them)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer

    closed, opened = [], []
    in_solids = 0
    for solid in part.solids():
        shells = shut = 0
        explorer = TopExp_Explorer(solid.wrapped, TopAbs_SHELL)
        while explorer.More():
            shells += 1
            shut += int(BRep_Tool.IsClosed_s(explorer.Current()))
            explorer.Next()
        box = solid.bounding_box(optimal=False)
        diagonal = float((box.size.X ** 2 + box.size.Y ** 2 + box.size.Z ** 2) ** 0.5)
        solid_ok = shells and shut == shells and abs(float(solid.volume)) > _ZERO_VOLUME * diagonal ** 3
        (closed if solid_ok else opened).append(solid)
        in_solids += len(solid.faces())
    return closed, opened, max(0, len(part.faces()) - in_solids)


def _integrity(document: _dfm_brep.Document, process: str) -> list[dict[str, Any]]:
    """``Unmeasured("not_solid")`` where a part holds no closed solid of any volume -- an open shell, a face, a
    solid of zero volume: no process makes a part of no material, and every figure of one would be of a
    surface. Else the findings that put every figure in doubt, errors in every process: ``not_watertight``
    (a solid with an open shell, or faces beside the solids that no solid holds) and ``not_sound`` (the
    kernel's topology check fails). Printing's own ``solid`` family judges its solids' shells and soundness
    (with the boolean check), so for printing only the faces beside the solids are said here."""
    from cad._internal.dfm import Unmeasured, checkpoint
    from cad.build123d import _geometry

    found: list[dict[str, Any]] = []
    refused: list[str] = []
    for part in document.parts:
        checkpoint()
        name = part.owner or part.name or "the part"
        closed, opened, loose = _closed_solids(part)
        if not closed:
            what = (f"{len(opened)} solid(s) open or of no volume" if opened else
                    f"{len(part.faces())} face(s) and no solid")
            refused.append(f"{name} ({what}, {abs(float(part.shape.volume)):g} mm3)")
            continue
        where = part.ref("face", 1)
        if opened or loose:
            said = ", ".join(([f"{len(opened)} solid(s) with an open shell or no volume"] if opened else [])
                             + ([f"{loose} face(s) outside any solid"] if loose else []))
            if loose or process != "printing":
                found.append({"severity": "error", "code": "not_watertight", "location": where,
                              "message": f"{name} is not one closed solid ({said}): its inside cannot be told, "
                                         "so every figure of it is of a surface -- read every figure below with that",
                              "hint": "close the open shell, fuse or delete the loose faces, and check again"})
        if process == "printing":
            continue
        try:
            issues = sorted({issue.code for issue in _geometry.topology_errors(part.shape)})
        except Exception:  # noqa: BLE001 - a check the kernel cannot finish is no verdict
            continue
        if issues:
            found.append({"severity": "error", "code": "not_sound", "location": where,
                          "message": f"{name} fails the kernel's validity check ({', '.join(issues)}): its faces "
                                     "and edges do not meet as a solid's must, so its figures are in doubt",
                          "hint": "rebuild the faulty feature (a fillet or boolean that failed), then check again"})
    if refused:
        raise Unmeasured("not_solid", f"{'; '.join(refused)}: a check measures closed solids, and this holds "
                         "none -- an open shell, a face or a solid of no volume is no part a process makes. Close "
                         "the shell into a solid (every edge shared by two faces), thicken or extrude the face, or "
                         "check the solid the model means")
    return found


def _scale(document: _dfm_brep.Document, document_type: str, report: dict[str, Any]) -> None:
    """``report["scale"]`` says the units look wrong (``units_suspect``, a warning said first) where the
    whole document is under ``_PLAUSIBLE_DIAGONAL_MM`` across, unless the process's own scale already does."""
    scale = report.get("scale") if isinstance(report.get("scale"), dict) else {}
    if scale.get("units_suspect"):
        return
    boxes = [part.shape.bounding_box(optimal=False) for part in document.parts]
    lo = np.min([[box.min.X, box.min.Y, box.min.Z] for box in boxes], axis=0)
    hi = np.max([[box.max.X, box.max.Y, box.max.Z] for box in boxes], axis=0)
    diagonal = float(np.linalg.norm(hi - lo))
    if diagonal >= _PLAUSIBLE_DIAGONAL_MM:
        return
    declared = ("the STEP declares its unit and it reads" if document_type == "step"
                else "build123d has no unit and a model's is the millimetre: it reads")
    report["scale"] = {**scale, "bbox_diagonal_mm": round(diagonal, 6), "units_suspect": True,
                       "note": f"{declared} {diagonal:.4g} mm across, implausibly small for a made part: it is "
                               f"probably drawn in metres ({diagonal * 1000:.4g} mm if so) or inches "
                               f"({diagonal * 25.4:.4g} mm) -- scale the model to millimetres, then check again"}


def _measured(document: _dfm_brep.Document, document_type: str, process: str, options: dict[str, Any],
              candidates: bool) -> dict[str, Any]:
    from cad._internal.dfm import Unmeasured, checkpoint

    if not document.parts:
        raise Unmeasured("document_empty", "the document holds no part with a face to measure")
    checkpoint()
    doubt = _integrity(document, process)
    module = importlib.import_module(f"cad.build123d._dfm_{process}")
    report = module.measure(document, options, candidates)
    _scale(document, document_type, report)
    found = [*doubt, *(report.pop("findings", None) or ())]
    if document.empty:
        shown = ", ".join(document.empty[:8]) + (f" and {len(document.empty) - 8} more" if len(document.empty) > 8 else "")
        found.append({"severity": "info", "code": "empty_parts", "location": document.empty[0],
                      "message": f"{len(document.empty)} part(s) hold no face and were not measured: {shown}"})
    return {"source": {"type": document_type, "measured_as": "brep", "document": document.name},
            "document": document.facts(), "bodies": [part.facts() for part in document.parts], **report,
            **({"findings": found} if found else {})}


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The report of ``source`` (a STEP's or an xbf's path, read in this process) for ``process``, or
    ``Unmeasured``."""
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
    process does not take."""
    return _declared(_dfm_brep.read(document_type, source), document_type, given, candidates, document_type)


def held(source: Any, check: dict[str, Any], read: Any = None, keep: str | None = None) -> dict[str, Any]:
    """The check an engine's kernel process runs of a document it holds (``source``, an ``export.Source``:
    a model's in its worker, a file's or a held document's in the checks process), as ``check`` asks it
    (``{"type", "process", "resolved", "candidates", "given"}``, its options resolved by the caller,
    ``manufacturing.options``), measured in memory (``_dfm_brep.of_source``). Plain data, which the caller
    finishes (``manufacturing.finish``): ``{"measured": {"process", "resolved", "report"}}``; ``{"unmeasured":
    {"code", "message"}}``; ``{"refused": words}`` for what ``manufacturing.declared`` refuses (the command
    line's to fix). ``read``: what a reading failure is said as, ``failed to read ...``. ``keep``: what the
    document is, a build's parts read back kept for its next check (``_dfm_brep.of_source``); the answer's
    ``read`` says whether this check read any part anew.

    Its measurements equal ``measure``'s and ``measure_declared``'s of the same document read from a file."""
    from cad._internal.dfm import Unmeasured
    from cad._internal.refused import ArgumentRefused

    document_type, process = check["type"], check.get("process")
    candidates = bool(check.get("candidates"))
    made = _dfm_brep.made
    try:
        try:
            document = _dfm_brep.of_source(source, keep)
        except Unmeasured:
            raise
        except Exception as error:  # noqa: BLE001 - a document that does not read is the check's answer
            raise Unmeasured("document_unreadable", f"failed to read {read or 'the document'}: {error}") from None
        if process is None:
            process, resolved, report = _declared(document, document_type, dict(check.get("given") or {}),
                                                  candidates, document_type)
        else:
            resolved = dict(check["resolved"])
            report = _measured(document, document_type, process, resolved, candidates)
    except Unmeasured as failure:
        return {"unmeasured": {"code": failure.code, "message": failure.message}, "read": _dfm_brep.made != made}
    except ArgumentRefused as refused:
        return {"refused": str(refused), "read": _dfm_brep.made != made}
    return {"measured": {"process": process, "resolved": resolved, "report": report}, "read": _dfm_brep.made != made}


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
    label = Path(document.name or "shape")
    try:
        report = {"process": process, **_measured(document, "shape", process, resolved, candidates)}
    except Unmeasured as failure:
        return manufacturing._failed(label, failure.message, failure.code)
    return manufacturing.finish(label, report, process, resolved, candidates)


def cnc(shape: Any, *, material: str | None = None, axes: int | None = None,
        turning: bool = False, tools: str | None = None, stock: str | None = None) -> Any:
    """CNC machining's check of ``shape`` (a build123d ``Shape``; an assembly's every part): a ``CheckResult``
    whose findings are at refs (``plate/face 7``) and whose ``measurements`` is the report -- the options are
    ``cad.step.dfm``'s for ``process="cnc"``."""
    return checked(shape, "cnc", {"material": material, "axes": axes, "turning": turning,
                                  "tools": tools, "stock": stock})


def sheet_metal(shape: Any, *, material: str | None = None,
                thickness: float | None = None, k_factor: float | None = None, bend_radius: float | None = None,
                kerf: float | None = None, sheet_size: str | None = None) -> Any:
    """Sheet metal's check of ``shape``, as ``cnc``'s (``process="sheet"``)."""
    return checked(shape, "sheet", {"material": material, "thickness": thickness,
                                    "k_factor": k_factor, "bend_radius": bend_radius, "kerf": kerf,
                                    "sheet_size": sheet_size})


def molding(shape: Any, *, material: str | None = None, pull: str | None = None,
            wall_limit: float | None = None, zero_tol: float | None = None, cavities: int | None = None,
            candidates: bool = False) -> Any:
    """Injection molding's check of ``shape``, as ``cnc``'s (``process="molding"``)."""
    return checked(shape, "molding", {"material": material, "pull": pull,
                                      "wall_limit": wall_limit, "zero_tol": zero_tol, "cavities": cavities},
                   candidates=candidates)


def printing(shape: Any, *, material: str | None = None, technology: str | None = None,
             build_volume: str | None = None, angle_limit: float | None = None, layer_height: float | None = None,
             nozzle: float | None = None, candidates: bool = False) -> Any:
    """3D printing's check of ``shape``, as ``cnc``'s (``process="printing"``)."""
    return checked(shape, "printing", {"material": material, "technology": technology,
                                       "build_volume": build_volume, "angle_limit": angle_limit,
                                       "layer_height": layer_height, "nozzle": nozzle}, candidates=candidates)
