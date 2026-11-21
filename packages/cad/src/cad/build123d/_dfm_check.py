"""The manufacturing check of exact geometry: what ``cad.<type>.dfm(source, process=...)`` runs for a
STEP, an xbf or a document the engine holds, once its options are resolved (``cad._internal.manufacturing``)
-- in one of the engine's checks processes (``held``), or in this process where no engine can be reached
(``measure``) -- and what ``cad.build123d.dfm(shape, process=...)`` runs for a live shape.

The document is read as the engine reads it (``_dfm_brep.read``); the process's module measures it
(``_dfm_cnc``, ``_dfm_sheet``, ``_dfm_molding``, ``_dfm_printing``: each ``measure(document, options,
candidates)``, a report of plain data, facts alone, handed the options its process declares it reads alone:
``kept.Measuring``); the type side makes the result of the report: the
process's findings and the rules' verdicts (``manufacturing.finish``). Given no process
(``measure_declared``), the document is read first and measured for the process its parts declare, the
options resolved for it then (``manufacturing.declared``). Asked to describe a document rather than measure it
(``described``), a checks process answers what a measurement of it would read (``_dfm_brep.content``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np

from cad._internal.dfm._common import out_of_memory
from cad.build123d import _dfm_brep

__all__ = ["checked", "described", "dfm", "held", "measure", "measure_declared"]


#: A solid of less volume than this fraction of its box's diagonal cubed holds no material: zero volume.
_ZERO_VOLUME = 1e-9
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


#: Whether the integrity of the document last measured here (``_measured``) was cut short: the kernel's validity
#: check raised on a part, so its ``not_sound`` was not looked for and the report does not say so; or a pair of
#: solids could not be compared for want of memory. Such a report is not one to keep (``_transient``).
_CUT_SHORT = {"integrity": False}

#: Solids of one part share volume where their common is over this share of the smaller's volume.
_OVERLAP = 1e-6
#: The pairs of one part's solids whose common is computed, at most: each a boolean of the kernel's.
_PAIRS = 256


#: How a process's measurement reads a part of several solids, said with ``several_solids``.
_READ_AS = {
    "cnc": "; each is judged as a part of its own (its own stock, setups and tool access), as each is machined",
    "molding": "; they are read together, so they shadow each other (its undercuts, walls and bosses are read "
               "across them), and where two touch without being fused their contact is no surface of the molded "
               "part: it is left out of its draft and undercuts (measurements.touching lists each pair)",
}


def _several(part: _dfm_brep.Part, name: str, closed: list[Any], process: str) -> list[dict[str, Any]]:
    """What a part of several solids says, alike in every process: ``several_solids`` (a warning: a process
    makes one solid a part, so the solids are judged as the process's module reads them, together or each on
    its own -- ``_READ_AS`` says which, so no process says it again -- and the part is not one piece), and
    ``not_sound`` (an error) where two of them share volume --
    interpenetrating solids are no part: its volume, walls and reach are of material counted twice. A pair is
    compared where their boxes meet, ``_PAIRS`` pairs at most (said where more remain). Printing's own
    ``solid`` family finds shared volume with its boolean check, so it is not looked for twice."""
    from cad.build123d import _geometry

    where = part.ref("face", 1)
    found = [{"severity": "warning", "code": "several_solids", "location": where,
              "message": f"{name} is {len(closed)} solids in one part: a process makes a part of one solid"
                         + _READ_AS.get(process, ""),
              "hint": "fuse them into one solid (`a + b` in build123d) if they are one piece, or make each its own "
                      "part (its own label in an assembly)"}]
    if process == "printing":
        return found
    boxes = [solid.bounding_box(optimal=False) for solid in closed]
    low = np.array([[box.min.X, box.min.Y, box.min.Z] for box in boxes])
    high = np.array([[box.max.X, box.max.Y, box.max.Z] for box in boxes])
    pairs = [(i, j) for i in range(len(closed)) for j in range(i + 1, len(closed))
             if bool(np.all(low[i] <= high[j]) and np.all(low[j] <= high[i]))]
    shared: list[str] = []
    unknown = max(0, len(pairs) - _PAIRS)
    for i, j in pairs[:_PAIRS]:
        try:
            common = float(_geometry.overlap_volume(closed[i], closed[j]))
        except Exception as error:  # noqa: BLE001 - a boolean the kernel cannot finish is no verdict on the pair
            _CUT_SHORT["integrity"] = _CUT_SHORT["integrity"] or out_of_memory(error)
            unknown += 1
            continue
        if common > _OVERLAP * min(abs(float(closed[i].volume)), abs(float(closed[j].volume))):
            shared.append(f"solids {i + 1} and {j + 1} share {common:.6g} mm3")
    if shared:
        named = "; ".join(shared[:4]) + (f" and {len(shared) - 4} more pair(s)" if len(shared) > 4 else "")
        found.append({"severity": "error", "code": "not_sound", "location": where,
                      "message": f"{name}'s solids interpenetrate ({named}): its material is counted twice there, "
                                 "so its figures are in doubt",
                      "hint": "fuse them into one solid (`a + b` in build123d), or cut one from the other"})
    if unknown:
        found.append({"severity": "warning", "code": "solids_not_compared", "location": where,
                      "message": f"{unknown} pair(s) of {name}'s solids were not compared for shared volume "
                                 f"(over {_PAIRS} pairs whose boxes meet, or a boolean the kernel could not finish)",
                      "hint": "make each solid its own part, or fuse them, then check again"})
    return found


def _integrity(document: _dfm_brep.Document, process: str) -> list[dict[str, Any]]:
    """``Unmeasured("not_solid")`` where a part holds no closed solid of any volume -- an open shell, a face, a
    solid of zero volume: no process makes a part of no material, and every figure of one would be of a
    surface. Else the findings that put every figure in doubt, errors in every process: ``not_watertight``
    (a solid with an open shell, or faces beside the solids that no solid holds) and ``not_sound`` (the
    kernel's topology check fails, or a part's solids interpenetrate) -- and, of a part of several solids,
    ``several_solids`` (``_several``), said alike in every process. Printing's own ``solid`` family judges its
    solids' shells and soundness (with the boolean check), so for printing only the faces beside the solids
    and the count of solids are said here."""
    from cad._internal.dfm import Unmeasured
    from cad.build123d import _geometry

    found: list[dict[str, Any]] = []
    refused: list[str] = []
    for part in document.parts:
        name = part.owner or part.name or "the part"
        closed, opened, loose = _closed_solids(part)
        if not closed:
            what = (f"{len(opened)} solid(s) open or of no volume" if opened else
                    f"{len(part.faces())} face(s) and no solid")
            refused.append(f"{name} ({what}, {abs(float(part.shape.volume)):g} mm3)")
            continue
        where = part.ref("face", 1)
        if len(closed) > 1:
            found.extend(_several(part, name, closed, process))
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
            _CUT_SHORT["integrity"] = True  # and says nothing in the report: it is not one to keep (``_transient``)
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
    """``report["scale"]`` says the units look wrong (``units_suspect``, a warning said first) where the whole
    document is implausibly small or large across (``_common.units_doubt``: the one test every process and
    source takes), unless the process's own scale already says so."""
    from cad._internal.dfm._common import units_doubt

    scale = report.get("scale") if isinstance(report.get("scale"), dict) else {}
    if scale.get("units_suspect"):
        return
    boxes = [part.shape.bounding_box(optimal=False) for part in document.parts]
    lo = np.min([[box.min.X, box.min.Y, box.min.Z] for box in boxes], axis=0)
    hi = np.max([[box.max.X, box.max.Y, box.max.Z] for box in boxes], axis=0)
    diagonal = float(np.linalg.norm(hi - lo))
    doubt = units_doubt(diagonal, "the STEP declares its unit and it reads" if document_type == "step"
                        else "build123d has no unit and a model's is the millimetre: it reads")
    if doubt["units_suspect"]:
        report["scale"] = {**scale, "bbox_diagonal_mm": round(diagonal, 6), **doubt}


def _measured(document: _dfm_brep.Document, document_type: str, process: str, options: dict[str, Any],
              candidates: bool) -> dict[str, Any]:
    """The report of ``document`` for ``process``, measured with the options its measurement reads alone
    (``kept.Measuring``): a read of any other fails it (``RuntimeError``), even one a family caught."""
    from cad._internal.dfm import Unmeasured, kept

    if not document.parts:
        raise Unmeasured("document_empty", "the document holds no part with a face to measure")
    _CUT_SHORT["integrity"] = False
    doubt = _integrity(document, process)
    module = importlib.import_module(f"cad.build123d._dfm_{process}")
    measuring = kept.Measuring(process, options)
    report = module.measure(document, measuring, candidates)
    if measuring.undeclared:
        raise RuntimeError(f"the {process} measurement read {', '.join(sorted(measuring.undeclared))}, which "
                           f"cad._internal.dfm.{process}.MEASURES does not declare: declare it, or leave it to the "
                           "rules")
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
              measured_as: str, *, printer_snapshot: dict[str, Any] | None = None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The process ``document``'s parts declare, the options resolved for it, and the report, which says what
    was read (``process_declared``)."""
    from cad._internal import manufacturing
    from cad._internal.dfm import Unmeasured

    if not document.parts:
        raise Unmeasured("document_empty", "the document holds no part with a face to measure")
    process, resolved, said = manufacturing.declared(
        document_type, [(part.owner or part.name, part.material) for part in document.parts], given,
        candidates=candidates, printer_snapshot=printer_snapshot)
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


def held(source: Any, check: dict[str, Any], read: Any = None) -> dict[str, Any]:
    """The check of a document its process holds (``source``, an ``export.Source``: a STEP's or an xbf's file,
    a held document's bytes -- one of the engine's checks processes today), as ``check`` asks it (``{"type", "process", "resolved",
    "candidates"}``: the process named, and of its resolved options those its measurement reads,
    ``kept.measuring``), measured in memory (``_dfm_brep.of_source``). Plain data: ``{"measured": {"process",
    "resolved", "report"}, "content_key"}``, the report with the key of the content record of the very parts
    it was measured of (``_dfm_brep.content``), so whoever keeps the report keeps it under what was measured,
    whatever it took the document to hold -- and ``"transient": True`` beside them for a report not to be kept
    at all (``_transient``); or ``{"unmeasured": {"code", "message"}}``. ``read``: what a reading failure is
    said as, ``failed to read ...``.

    A check given no process is not asked of it: whoever asks reads the process the parts declare from the
    document's record (``described``, ``kept.asked``) and names it here. Its measurements equal ``measure``'s
    and ``measure_declared``'s of the same document read from a file."""
    from cad._internal.dfm import Unmeasured

    document_type, process = check["type"], check.get("process")
    if process is None:
        raise ValueError("a check is measured for the process it names: the one a document's parts declare is "
                         "read from its content record (cad._internal.dfm.kept.asked) before it is asked")
    candidates = bool(check.get("candidates"))
    try:
        try:
            document = _dfm_brep.of_source(source)
        except Unmeasured:
            raise
        except Exception as error:  # noqa: BLE001 - a document that does not read is the check's answer
            raise Unmeasured("document_unreadable", f"failed to read {read or 'the document'}: {error}") from None
        key = _dfm_brep.content(document)["key"]
        resolved = dict(check["resolved"])
        report = _measured(document, document_type, process, resolved, candidates)
    except Unmeasured as failure:
        return {"unmeasured": {"code": failure.code, "message": failure.message}}
    return {"measured": {"process": process, "resolved": resolved, "report": report}, "content_key": key,
            **({"transient": True} if _transient(process, report) else {})}


def _transient(process: str, report: dict[str, Any]) -> bool:
    """Whether a report just measured here is one the same parts, options and code could measure otherwise the
    next time, so no one keeps it in a measurement's place: its process's module says so of the measurement it
    last made (``transient()``: molding's release search out of its seconds, a hull printing's fit took another
    way for want of memory); its integrity was cut short (``_CUT_SHORT``: the kernel's validity check raised,
    so the report is silent on what it would have said); a family failed for want of memory, by any of its
    names (its ``error``: ``_common.out_of_memory``); or a table of the report says of itself that it is not
    repeatable (``"repeatable": False``, wherever it lies and whatever made it: what it holds came of
    something the next run may not meet -- a helper not ready yet, an answer that timed out; one that says
    true, or nothing, is repeatable). Every other report, with a family not measured or none, is what its code
    makes of those parts each time."""
    said = getattr(importlib.import_module(f"cad.build123d._dfm_{process}"), "transient", None)
    if (callable(said) and said()) or _CUT_SHORT["integrity"]:
        return True

    def says_so(value: Any) -> bool:
        if isinstance(value, dict):
            error = value.get("error")
            return ((isinstance(error, str) and out_of_memory(error)) or value.get("repeatable") is False
                    or any(says_so(item) for item in value.values()))
        return isinstance(value, list) and any(says_so(item) for item in value)

    return says_so(report)


def described(source: Any, check: dict[str, Any], read: Any = None) -> dict[str, Any]:
    """What one of the engine's checks processes answers when ``check`` asks it to describe a document it holds
    (``{"describe": True, "type", ...}``) rather than measure it: what a measurement of it reads (``source``, as
    ``held`` reads it, its parts read in place, never copied, since nothing meshes them), as its content record --
    ``{"content": {...}}`` (``_dfm_brep.content``: plain data with its ``key``) -- or ``{"unmeasured": {"code",
    "message"}}`` for a document that does not read, as ``held`` says it. ``read``: what a reading failure is said
    as. Nothing is measured, and no option is read."""
    from cad._internal.dfm import Unmeasured

    try:
        try:
            document = _dfm_brep.of_source(source, copy=False)
        except Unmeasured:
            raise
        except Exception as error:  # noqa: BLE001 - a document that does not read is the answer
            raise Unmeasured("document_unreadable", f"failed to read {read or 'the document'}: {error}") from None
        return {"content": _dfm_brep.content(document)}
    except Unmeasured as failure:
        return {"unmeasured": {"code": failure.code, "message": failure.message}}


def checked(shape: Any, process: str | None, given: dict[str, Any], *, candidates: bool = False,
            name: str | None = None, strict: bool = False) -> Any:
    """The check of a live build123d shape, as a ``CheckResult``: its options resolved as a STEP's are, its
    findings at refs of the document the engine would make of it. With no ``process``, the one its parts
    declare (``manufacturing.declared``). ``ArgumentRefused`` naming the parameter for what is no shape, and
    for an option's value (a Python caller's words: ``manufacturing.parameters``)."""
    from cad._internal import manufacturing
    from cad._internal.dfm import Unmeasured, _common
    from cad._internal.refused import ArgumentRefused

    if not hasattr(getattr(shape, "wrapped", None), "ShapeType"):
        raise ArgumentRefused(f"shape is a build123d shape (a Part, a Solid, a Compound of labelled parts), not "
                              f"{'None' if shape is None else 'a ' + type(shape).__name__}")
    try:
        _common.require_bool("strict", strict)
        if process is None:
            # A live shape keeps its parts' materials, as a model's document does (a STEP does not): read as a
            # model's.
            manufacturing.options("model", None, given, candidates=candidates)
            document = _dfm_brep.parts_of(shape, name=name)
            label = Path(document.name or "shape")
            try:
                process, resolved, measured = _declared(document, "step", given, candidates, "shape")
            except Unmeasured as failure:
                return manufacturing.not_checked(label, failure.message, failure.code)
            return manufacturing.finish(label, {"process": process, **measured}, process, resolved, candidates,
                                        strict)
        resolved = manufacturing.options("step", process, given, candidates=candidates)
    except ArgumentRefused as refused:
        raise ArgumentRefused(manufacturing.parameters(str(refused))) from None
    assert resolved is not None
    document = _dfm_brep.parts_of(shape, name=name)
    label = Path(document.name or "shape")
    try:
        report = {"process": process, **_measured(document, "shape", process, resolved, candidates)}
    except Unmeasured as failure:
        return manufacturing.not_checked(label, failure.message, failure.code)
    return manufacturing.finish(label, report, process, resolved, candidates, strict)


def dfm(shape: Any, *, process: str | None = None, candidates: bool = False, strict: bool = False,
        **options: Any) -> Any:
    """The manufacturing check of a live build123d ``shape`` (a part, or an assembly's every part), as
    ``cad.step.dfm`` checks a file: ``process`` is ``cnc``, ``sheet``, ``molding`` or ``printing`` -- with
    none, the one the parts declare (``part.material = metals.aluminum(process=machined())``) -- and the
    options are that process's, by the names ``cad.step.dfm`` takes (``tools=[3, 6]``, ``pull="z"``,
    ``technology="sla"``); ``candidates`` ranks molding's pulls or printing's orientations instead, and
    ``strict`` fails the check on a warning too. A ``CheckResult``: its ``status`` (``ok``, ``failed``,
    ``not_checked``), its findings at refs (``plate/face 7``), each rule's verdict with its figure and its
    limit, and its ``measurements``, the report. ``TypeError`` for an option no process takes."""
    from cad._internal import manufacturing

    unknown = sorted(set(options) - set(manufacturing.KINDS) | ({"units"} & set(options)))
    if unknown:
        raise TypeError(f"dfm() got an unexpected keyword argument {unknown[0]!r}")
    return checked(shape, process, options, candidates=candidates, strict=strict)


def cnc(shape: Any, *, material: str | None = None, axes: int | None = None,
        turning: bool = False, tools: Any = None, stock: Any = None, strict: bool = False) -> Any:
    """CNC machining's check of ``shape``: ``dfm(shape, process="cnc", ...)``."""
    return checked(shape, "cnc", {"material": material, "axes": axes, "turning": turning,
                                  "tools": tools, "stock": stock}, strict=strict)


def sheet_metal(shape: Any, *, material: str | None = None,
                thickness: float | None = None, k_factor: float | None = None, bend_radius: float | None = None,
                kerf: float | None = None, sheet_size: Any = None, strict: bool = False) -> Any:
    """Sheet metal's check of ``shape``: ``dfm(shape, process="sheet", ...)``."""
    return checked(shape, "sheet", {"material": material, "thickness": thickness,
                                    "k_factor": k_factor, "bend_radius": bend_radius, "kerf": kerf,
                                    "sheet_size": sheet_size}, strict=strict)


def molding(shape: Any, *, material: str | None = None, pull: Any = None,
            wall_limit: float | None = None, zero_tol: float | None = None, cavities: int | None = None,
            candidates: bool = False, strict: bool = False) -> Any:
    """Injection molding's check of ``shape``: ``dfm(shape, process="molding", ...)``."""
    return checked(shape, "molding", {"material": material, "pull": pull,
                                      "wall_limit": wall_limit, "zero_tol": zero_tol, "cavities": cavities},
                   candidates=candidates, strict=strict)


def printing(shape: Any, *, material: str | None = None, technology: str | None = None,
             build_volume: Any = None, angle_limit: float | None = None, layer_height: float | None = None,
             nozzle: float | None = None, printer: Any = None, candidates: bool = False,
             strict: bool = False) -> Any:
    """3D printing's check of ``shape``: ``dfm(shape, process="printing", ...)``."""
    return checked(shape, "printing", {"material": material, "technology": technology,
                                       "build_volume": build_volume, "angle_limit": angle_limit,
                                       "layer_height": layer_height, "nozzle": nozzle,
                                       "printer": printer}, candidates=candidates,
                   strict=strict)
