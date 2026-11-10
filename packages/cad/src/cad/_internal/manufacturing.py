"""The manufacturing check every 3D document type shares: ``cad.<type>.dfm(source, process=...)``.

``model``, ``stl``, ``threemf``, ``glb``, ``step``, ``xbf`` and, as a sheet's cut file, ``dxf`` each answer
``dfm`` with the same function, made for the type here (``dfm_for``): its signature takes a path (or, for a
model, its document id or handle) and plain values alone, so it is the type's (the signature rule). Four processes, each a
module of ``cad._internal.dfm`` (its options, rules, findings and summary):

- ``cnc``, milling and turning: internal corners, pockets and slots, walls, holes, tool access per setup,
  stock, and with ``turning`` the turned features;
- ``sheet``, sheet cut and bent: thickness, bends, flanges, holes and their distances, reliefs, hems, the
  flat pattern;
- ``molding``, injection molding: draft, undercuts, walls, ribs and bosses, projected area and clamp
  force along one pull, or with ``candidates`` the pulls ranked;
- ``printing``, 3D printing by a technology: walls, features, overhangs, bridges, holes, trapped volumes,
  build volume and support, or with ``candidates`` the orientations ranked.

**Two layers.** The measurement is an integration's: a STEP, an xbf and a model's document are
measured on their B-rep, exactly, by the build123d integration (``cad.build123d._dfm_check``), each
finding at a ref ``cad xbf inspect`` resolves (``plate/face 7``) -- through the engine, in one of its checks
processes (``_held``, ``cad.engine.api.check``), a file by this caller only where no engine can be reached;
an STL, a 3MF and a GLB by the trimesh integration (``cad.trimesh._check``), by this caller, each finding at
``x, y, z``. What a caller measures itself it measures in a process of its own that it holds to a check's
limits (``_watched``), the engine's: no check runs unwatched. The report is the result's ``measurements``,
facts alone. The verdicts are the process's rules (``dfm.<process>.RULES``): general
practice, no shop's -- every rule a limit on one measured figure with the published guide that states it, a
failing one a finding whose code is the rule's id and whose hint says what to change; the record of every
rule is ``measurements["rules"]``. A shop's own limits are no option here: they are compared with the
measurements (a shop's skill does), and what a person knows of their own shop is a plain option (the
tools, the bend radius, the sheet, the build volume).

**Three states** (``CheckResult.status``, ``finish``). ``ok``: everything was judged and no finding is an
error (warnings are recommendations: the part is made, at a cost or a risk). ``failed``: a finding is an
error -- the part cannot be made by this process as drawn -- or, with ``strict``, a warning. ``not_checked``:
the check did not judge what it was asked to -- a source that does not read or holds no solid
(``Unmeasured``), a family that could not be measured (``measurement_failed``), faces the kernel failed to
intersect rays with (``rays_unintersected``), a rule whose items lack a figure that should have been measured
(``rule_partly_judged``), rules that judged nothing (``rules_none_evaluated``) -- which is
no verdict and never a pass; ``reason`` is the code of the finding that says so. A failure wins over what
was not checked: an error found is the part's whatever else was not judged. ``ok`` is True for ``ok`` alone.

Each option belongs to a process (``dfm.<process>.OPTIONS``) or to all (``dfm.COMMON``), and one given to
another process is refused by name before anything is read, as an option the check does not take would be
(law 16), and so is a value of another kind (``KINDS``: never coerced, law 17). Each type's ``dfm`` takes the
processes it can be checked for (``processes_for``: a mesh printing, a DXF sheet) and their options alone;
a mesh asked for another is refused with the reason and the fix (``_MESH_REFUSED``: check the STEP or the model). The standard library alone: the server's command resolves the options here before it starts
an environment that holds the integration. An xbf or a model given no process is checked for the one its
parts declare (``part.material = metals.aluminum(process=machined())``): the options every process shares
are checked here, and the integration reads the document, takes the declared process and resolves the rest
(``declared``) before it measures. A STEP keeps no process, so one given none is refused here.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal, get_args

from cad._internal import dfm
from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding, CheckResult

__all__ = ["BREP_TYPES", "DEFAULTS", "KINDS", "NOT_CHECKED", "OPTIONS", "PROCESSES", "UNITS_MM", "declared", "dfm_for",
           "finish", "not_checked", "options", "parameters", "processes_for", "through_engine"]

#: The enumerations ``process``, ``units`` and ``technology`` take, so the command's generated parser takes
#: their values alone (each flag's choices); each is held to the modules that define it (below).
Process = Literal["cnc", "sheet", "molding", "printing"]
Unit = Literal["mm", "cm", "m", "in", "ft"]
Technology = Literal["fdm", "sls", "sla", "mjf", "pbf"]
PROCESSES = dfm.PROCESSES
#: The types measured on their B-rep (the build123d integration); the rest are meshes (trimesh), but a DXF,
#: a sheet's cut file, checked by the build123d integration's DXF library (ezdxf).
BREP_TYPES = ("model", "step", "xbf")
CUT_TYPES = ("dxf",)
#: Length units a file may carry, as a factor to millimetres. An STL is unitless, so the caller says which
#: one (millimetres unless said); a DXF may declare none (``$INSUNITS`` unset: every R12 file), and is then
#: read in the one the caller says, or not measured. The other types declare theirs.
UNITS_MM = dict(zip(get_args(Unit), (1.0, 10.0, 1000.0, 25.4, 304.8), strict=True))


def _options() -> dict[str, dict[str, Any]]:
    return {process: dict(dfm.module(process).OPTIONS) for process in PROCESSES}


#: Each process's own options and their defaults (``dfm.COMMON``'s are every process's, ``candidates`` too).
OPTIONS: dict[str, dict[str, Any]] = _options()
DEFAULTS = {**dfm.COMMON, **{name: value for given in OPTIONS.values() for name, value in given.items()}}
#: Every option's kind, in the order the signature and the help list them: a value of another kind is refused
#: by name (``_common.require``), never coerced -- ``axes=3.7`` is not 3 axes, ``turning="no"`` is no flag.
KINDS: dict[str, type] = {
    "material": str, "units": str, "axes": int, "turning": bool, "tools": str, "stock": str,
    "thickness": float, "k_factor": float, "bend_radius": float, "kerf": float, "sheet_size": str, "pull": str,
    "wall_limit": float, "zero_tol": float, "cavities": int, "technology": str, "build_volume": str,
    "angle_limit": float, "samples": int, "layer_height": float, "nozzle": float}
# Raised, not asserted: the signature and the command's choices are these, under ``python -O`` too.
if get_args(Process) != PROCESSES:
    raise RuntimeError(f"manufacturing.Process {get_args(Process)} is not dfm.PROCESSES {PROCESSES}")
if get_args(Technology) != dfm.module("printing").TECHNOLOGIES:
    raise RuntimeError("manufacturing.Technology is not dfm.printing.TECHNOLOGIES")
if set(KINDS) != set(DEFAULTS):
    raise RuntimeError(f"manufacturing.KINDS names {sorted(set(KINDS) ^ set(DEFAULTS))} unlike the options")


def processes_for(document_type: str) -> tuple[str, ...]:
    """The processes a source of ``document_type`` is checked for: a B-rep's every one; a mesh's those measured
    from triangles (printing); a DXF's sheet alone."""
    if document_type in CUT_TYPES:
        return ("sheet",)
    if document_type in BREP_TYPES:
        return PROCESSES
    return tuple(process for process in PROCESSES if "mesh" in dfm.module(process).MEASURED_FROM)
# The types that always declare their own units, read as millimetres: a units option is the STL's and the
# DXF's.
_DECLARED = {"threemf": "a 3MF declares its unit", "glb": "a GLB is in glTF's metres",
             "step": "a STEP declares its units", "xbf": "an xbf is in millimetres",
             "model": "a model is in millimetres"}
_UNITS_OF = "--units is an STL's or a DXF's, which may declare none"
# Why a mesh is not checked for each process measured on exact geometry alone, and what to check instead.
_MESH_REFUSED = {
    "cnc": "a cnc check measures exact geometry -- radii, axes, thicknesses -- that a mesh does not hold",
    "sheet": "a sheet check measures exact geometry -- radii, axes, thicknesses -- that a mesh does not hold",
    "molding": "a molding check is judged on exact geometry (a mesh's chords misread its draft, undercuts and walls)",
}
# The processes that rank candidates: the pulls, the orientations.
_RANKED = ("molding", "printing")


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _give_process(document_type: str, why: str = "") -> ArgumentRefused:
    named = processes_for(document_type)
    return ArgumentRefused(f"cad.{document_type}.dfm measures for a process{why}: give --process "
                           + (f"{', '.join(named[:-1])} or {named[-1]}" if len(named) > 1 else named[0]))


#: The options written out as text (``3,6,10``, ``100x60x25``) that a Python caller may give as numbers: each
#: with what joins them.
_SEQUENCES = {"tools": ",", "stock": "x", "build_volume": "x", "sheet_size": "x", "pull": ","}


def _spelled(given: dict[str, Any]) -> dict[str, Any]:
    """``given`` with each option a Python caller gave as numbers (``tools=[3, 6]``, ``stock=(100, 60, 25)``,
    ``pull=(0, 0, 1)``, one tool as ``tools=6``) written out as the command line writes it, and the material
    by its name in the table (``_material``). Anything else is as given, for ``_kinds`` to refuse by name."""
    spelled = dict(given)
    for name, joint in _SEQUENCES.items():
        value = spelled.get(name)
        if name == "tools" and isinstance(value, (int, float)) and not isinstance(value, bool):
            value = [value]
        if isinstance(value, (list, tuple)) and value and all(
                isinstance(part, (int, float)) and not isinstance(part, bool) for part in value):
            spelled[name] = joint.join(repr(part) for part in value)
    if isinstance(spelled.get("material"), str):
        spelled["material"] = _material(spelled["material"])
    return spelled


def _material(name: str) -> str:
    """The table's name for a material as a person writes it: the name or an alias (``materials.resolve``),
    or the longest run of its words that is one -- ``Aluminium 6061`` is aluminum, ``stainless steel 304``
    stainless -- the earliest of the longest. ``ArgumentRefused`` listing the table for none."""
    from cad._internal.dfm import materials

    try:
        return str(materials.resolve(name))
    except ArgumentRefused:
        words = [word for word in re.split(r"[\s_\-/,]+", name.strip().lower()) if word]
        for length in range(len(words) - 1, 0, -1):
            for start in range(len(words) - length + 1):
                try:
                    return str(materials.resolve("_".join(words[start:start + length])))
                except ArgumentRefused:
                    continue
        raise


#: An end mill over this across (mm) is none a mill holds: a value above it is a mistake of units or a typo
#: (text-to-cad's own bound: standard end mills end near 50 mm, the widest indexable ones under 100).
TOOL_MAX_MM = 100.0
#: A powder or resin machine lays no layer over this (mm; text-to-cad's own bound: SLA, SLS, MJF and metal
#: powder bed fusion layers are 0.02 to 0.3 mm). FDM's is its nozzle's diameter.
LAYER_MAX_MM = 0.5
FDM_NOZZLE_MM = 0.4


def _plausible(process: str, resolved: dict[str, Any]) -> None:
    """``ArgumentRefused`` for a value in range that no machine has, which would judge the part against
    nothing: an end mill a thousand kilometres across passes every corner, a 5 mm layer every wall."""
    if process == "cnc" and resolved.get("tools") is not None:
        widest = max(dfm.module("cnc").tools(resolved["tools"]))
        if widest > TOOL_MAX_MM:
            raise ArgumentRefused(f"--tools names an end mill {widest:g} mm across: diameters are in millimetres, "
                                  f"at most {TOOL_MAX_MM:g}")
    if process == "printing" and resolved.get("layer_height") is not None:
        layer = float(resolved["layer_height"])
        if resolved.get("technology") == "fdm":
            nozzle = float(resolved.get("nozzle") or FDM_NOZZLE_MM)
            if layer > nozzle:
                raise ArgumentRefused(f"--layer-height {layer:g} mm is taller than the {nozzle:g} mm nozzle: an FDM "
                                      "layer is at most the nozzle's diameter (give --nozzle for a wider one)")
        elif layer > LAYER_MAX_MM:
            raise ArgumentRefused(f"--layer-height {layer:g} mm is no {resolved.get('technology')} layer: at most "
                                  f"{LAYER_MAX_MM:g} mm")


def _kinds(given: dict[str, Any], candidates: Any) -> None:
    """Each option given (not None; a flag's False is not given) of its kind (``KINDS``), and ``candidates`` a
    flag: ``ArgumentRefused`` naming the flag else."""
    from cad._internal.dfm import _common

    for name, value in given.items():
        if value is not None and name in KINDS and not (KINDS[name] is bool and value is False):
            _common.require(KINDS[name], name, value)
    _common.require_bool("candidates", candidates)


def options(document_type: str, process: str | None, given: dict[str, Any], *,
            candidates: bool = False) -> dict[str, Any] | None:
    """The options a check of ``process`` runs with: those ``given`` (None, or False for a flag: not given),
    the defaults for the rest. ``ArgumentRefused`` (a ``ValueError``; the command says it as the command
    line's mistake, exit 2) naming the fix for no process or another, an option of another process, a value
    of another kind (``KINDS``: a float for a count, a word for a flag, an infinite length), a pull beside
    ``candidates`` (which ranks every pull), ``candidates`` of a process that ranks none, a units the type does
    not take, or a value out of range.

    With no process, a type checked for one process alone takes it (a DXF: sheet), and a B-rep type's
    (``BREP_TYPES``) check the one its parts declare, read with the document: what holds for every process
    is checked here (``_preflight``) and None is answered; the integration resolves the rest once it has read
    the parts (``declared``). A mesh refuses it, as a STEP does: its parts' materials are not in it."""
    given = _spelled(given)
    _kinds(given, candidates)
    if process is None and len(processes_for(document_type)) == 1:
        process = processes_for(document_type)[0]
    if process is None:
        if document_type not in BREP_TYPES:
            raise _give_process(document_type)
        return _preflight(document_type, given, candidates)
    module = dfm.module(process)
    if "mesh" not in module.MEASURED_FROM and document_type not in (*BREP_TYPES, *CUT_TYPES):
        reason = _MESH_REFUSED.get(process, f"a {process} check measures exact geometry, which a mesh does not hold")
        raise ArgumentRefused(f"{reason}: check the part's STEP or model instead (cad step dfm part.step --process "
                              f"{process}, or cad model dfm <id> --process {process})")
    if document_type in CUT_TYPES and process != "sheet":
        raise ArgumentRefused(f"a DXF is checked as a sheet's cut file: --process sheet, not {process}")
    own = {**dfm.COMMON, **module.OPTIONS}
    foreign = [name for name, value in given.items() if value is not None and value is not False and name not in own]
    if foreign:
        takes = ", ".join(_flag(name) for name in (*module.OPTIONS, *dfm.COMMON,
                                                    *(("candidates",) if process in _RANKED else ())))
        raise ArgumentRefused(f"{', '.join(_flag(name) for name in foreign)} {'is' if len(foreign) == 1 else 'are'} not "
                         f"{process}'s: a {process} check takes {takes}")
    if candidates and process not in _RANKED:
        raise ArgumentRefused(f"--candidates ranks molding's pulls or printing's orientations; a {process} check has none")
    if candidates and given.get("pull") is not None:
        raise ArgumentRefused("--candidates ranks every pull: give it no --pull")
    resolved = {name: given[name] if given.get(name) is not None else default for name, default in own.items()}
    if document_type in CUT_TYPES:
        resolved["units"] = given.get("units")  # a DXF's default is its own ($INSUNITS): none here
    units = resolved["units"]
    if units is not None and units not in UNITS_MM:
        raise ArgumentRefused(f"--units is one of {', '.join(UNITS_MM)}, not {units!r}")
    if units != "mm" and document_type in _DECLARED:
        raise ArgumentRefused(f"{_DECLARED[document_type]}, read as millimetres: {_UNITS_OF}")
    module.validate(resolved, document_type)
    _plausible(process, resolved)
    return resolved


def _preflight(document_type: str, given: dict[str, Any], candidates: bool) -> None:
    """What ``options`` refuses of a B-rep type's check before its process is known: a STEP's (its parts'
    declared materials are not written to it, so it never declares a process: refused before any environment
    is made, not after the file is read), a units, a material, a pull beside
    ``candidates``. Each option of one process is judged once the declared process is read (``declared``)."""
    if document_type == "step":
        raise ArgumentRefused(f"a STEP keeps no process: give --process {', '.join(PROCESSES[:-1])} or {PROCESSES[-1]}")
    if candidates and given.get("pull") is not None:
        raise ArgumentRefused("--candidates ranks every pull: give it no --pull")
    units = given.get("units")
    if units is not None and units != "mm":
        if units not in UNITS_MM:
            raise ArgumentRefused(f"--units is one of {', '.join(UNITS_MM)}, not {units!r}")
        raise ArgumentRefused(f"{_DECLARED[document_type]}, read as millimetres: {_UNITS_OF}")
    return None


def declared(document_type: str, parts: list[tuple[str, Any]], given: dict[str, Any], *,
             candidates: bool = False) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The process the parts declare (``parts``: each part's name and its declared material, a
    ``bd_materials.FinishedMaterial`` or None), the options resolved for it (``options``) and the info finding
    that says so (``process_declared``). A declared technology or layer height is taken where none is
    given (``given``'s wins), and the finding says what was taken and what was not (a technology given in its
    place, layer heights the parts disagree on). ``ArgumentRefused`` naming the fix -- give ``--process`` --
    for parts that declare different routes, none declared or one no check measures (cast, wrought)."""
    from cad._internal.dfm import processes

    routes: dict[str, list[tuple[str, Any]]] = {}
    for name, material in parts:
        applied = getattr(material, "process", None)
        found = processes.route(applied)
        if found is not None:
            routes.setdefault(found, []).append((name, material))
    if not routes:
        raise _give_process(document_type, ", and no part declares one (part.material = "
                                           "metals.aluminum(process=machined()))")
    if len(routes) > 1:
        named = ", ".join(f"{route} ({', '.join(name for name, _ in held[:3])}"
                          f"{f' and {len(held) - 3} more' if len(held) > 3 else ''})"
                          for route, held in sorted(routes.items()))
        # The command line's to fix, as none declared is: --process says which.
        raise ArgumentRefused(f"the parts declare different processes -- {named} -- so none is taken: give "
                              f"--process, or check each part on its own")
    (route, held), = routes.items()
    materials = sorted({str(getattr(material, "name", None) or "a material") for _, material in held})
    said = f"{', '.join(materials[:3])}, {route}"
    mapped = [processes.declared(getattr(material, "process", None)) for _, material in held]
    if mapped[0] is None:
        raise _give_process(document_type, f", and the part's declared material ({said}) is made by a process "
                                           f"no check measures")
    process, technology, _ = mapped[0]
    layers = {layer for _, _, layer in mapped if layer is not None}
    chosen = dict(given)
    took: list[str] = []
    if technology is not None:
        if given.get("technology") is None:
            chosen["technology"] = technology
            took.append(f"technology {technology}")
        elif given["technology"] != technology:
            took.append(f"technology {given['technology']} as given, not the declared {technology}")
        # The layer height is the declared technology's: a technology given instead takes its own.
        if chosen.get("technology") == technology and given.get("layer_height") is None:
            if len(layers) == 1:
                chosen["layer_height"] = layers.pop()
                took.append(f"layer height {chosen['layer_height']:g} mm")
            elif len(layers) > 1:
                took.append(f"the technology's layer height: the parts declare "
                            f"{', '.join(f'{layer:g}' for layer in sorted(layers))} mm")
    try:
        resolved = options(document_type, process, chosen, candidates=candidates)
    except ValueError as error:
        raise ArgumentRefused(f"{error} (the process is {process}, the parts declare {route}: give --process to "
                              f"check another)") from None
    if resolved is None:
        raise RuntimeError(f"options({document_type!r}, {process!r}) resolved nothing")
    detail = f" ({', '.join(took)})" if took else ""
    finding = {"severity": "info", "code": "process_declared", "location": "bodies",
               "message": f"process {process}{detail}, read from the part's declared material ({said}): "
                          f"give --process to check another"}
    return process, resolved, finding


def _label(source: Any) -> Path:
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        return Path(os.fspath(source)).expanduser().resolve()
    ident = getattr(source, "id", None)  # a document's handle; a model, by its name
    if ident is None and isinstance(source, (str, os.PathLike)):
        ident = os.fspath(source)
    return Path(str(ident or getattr(source, "name", None) or source))


_ORDER = {"error": 0, "warning": 1, "info": 2}
#: The findings that say the check did not judge what it was asked to, whatever their severity: a family that
#: could not be measured, faces the kernel failed to intersect rays with (what is measured across them is
#: not), a rule whose items carry no figure that should have been measured, rules that judged nothing. Any of
#: them and the result is ``not_checked``, never ``ok``.
NOT_CHECKED = frozenset({"measurement_failed", "rays_unintersected", "rule_partly_judged", "rules_none_evaluated"})
#: What puts every other figure in doubt, said before the errors whatever its severity: what was not checked,
#: a mesh not watertight or not sound (its walls, voids and volume are of an open or broken surface), units
#: that look wrong (every length off by a factor).
_FIRST = NOT_CHECKED | {"not_watertight", "not_sound", "units_suspect"}


def _shown(label: Path) -> Any:
    from cad._internal.validation_door import display_path

    return display_path(label) if label.is_absolute() else label


def not_checked(path: Path, message: str, code: str) -> CheckResult:
    """The result of a check that judged nothing: ``not_checked``, its ``reason`` the ``code`` of the one
    finding that says why (``message``) -- a source that does not read or holds no solid, a file that is not
    there, a check that stopped or failed where it ran."""
    return CheckResult(ok=False, path=path, findings=(CheckFinding("error", code, message),),
                       summary=f"NOT CHECKED {_shown(path)}: {code}", status="not_checked", reason=code)


_failed = not_checked


def _digest(counts: "Counter[str]") -> str:
    return ", ".join(f"{code} x{count}" for code, count in counts.most_common())


def finish(label: Path, report: dict[str, Any], process: str, resolved: dict[str, Any],
           candidates: bool, strict: bool = False) -> CheckResult:
    """The result of a measured ``report``: the measurement's findings, the process's, and the verdicts of its
    rules, which the report records (``measurements["rules"]``); its state (the module's **Three states**),
    with ``strict`` failed by a warning too; and its one line, which leads with its state and its counts --
    features, as the findings count them (``rules.evaluate``'s ``failing``), so the line and the findings
    agree."""
    from cad._internal.dfm import _common, rules

    module = dfm.module(process)
    resolved = _declared_material(report, resolved)
    found: list[CheckFinding] = [*_common.partial_findings(report), *_common.scale_findings(report),
                                 *(CheckFinding(**finding) for finding in report.pop("findings", None) or ()),
                                 *module.findings(report, resolved, candidates)]
    failing: dict[str, dict[str, int]] = {"error": {}, "warning": {}}
    if not candidates:
        rule_set = module.RULES
        verdicts, record = rules.evaluate(report, rule_set, module.context(report, resolved))
        report["rules"] = record
        failing = record["failing"]
        found.extend(verdicts)
        found.extend(_unmeasured_families(report, record))
        lost = sorted({ref for outcome in record["outcomes"] for ref in outcome.get("unmeasured_faces") or ()})
        if lost and not any(finding.code == "rays_unintersected" for finding in found):
            named = ", ".join(lost[:8]) + (f" and {len(lost) - 8} more" if len(lost) > 8 else "")
            found.append(CheckFinding(
                "warning", "rays_unintersected",
                f"the kernel failed to intersect rays with {len(lost)} face(s) ({named}): what the rules judge "
                f"across them is not measured there", lost[0],
                "rebuild the faulty face (its surface has a degenerate patch the kernel cannot intersect), "
                "then check again"))
        if not record["evaluated"] and record["outcomes"]:
            found.append(CheckFinding(
                "warning", "rules_none_evaluated",
                "the rules judged nothing here: none has a limit for this part's context (every outcome is "
                "not_evaluated or not_applicable), so nothing is verified", "rules",
                "read the measurements against the process's published limits"))
        found.append(CheckFinding(
            "info", "rules_general",
            f"the verdicts are {rule_set.title} (version {rule_set.version}): general practice drawn from "
            f"published design guides, and text-to-cad's own floors where no guide states a limit (each "
            f"labelled by its source), no shop's limits", "rules",
            "for a named shop, compare the measurements with its own published limits, or use its skill"))
    try:
        # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse than one that says it failed.
        json.dumps(report, allow_nan=False)
    except ValueError as error:
        return not_checked(label, f"a measurement was not a finite number, so the report is not JSON: {error}",
                           "not_finite")
    # What puts every figure in doubt first (``_FIRST``, whatever its severity), then errors, warnings, and the
    # facts and assumptions: what a reader acts on comes first.
    found.sort(key=lambda finding: (finding.code not in _FIRST, _ORDER.get(finding.severity, 3)))
    # One count, the findings': a rule's failing features (those past the findings shown too), and every
    # other finding once. What was not checked is counted apart: it is no verdict on the part.
    counts: dict[str, Counter[str]] = {"error": Counter(failing["error"]), "warning": Counter(failing["warning"])}
    unchecked: Counter[str] = Counter()
    for finding in found:
        if finding.code in NOT_CHECKED:
            unchecked[str(finding.code)] += 1
        elif finding.rule is None and finding.severity in counts:
            counts[finding.severity][str(finding.code)] += 1
    errors, warnings = sum(counts["error"].values()), sum(counts["warning"].values())
    status = "failed" if errors or (strict and warnings) else "not_checked" if unchecked else "ok"
    measured = f"{process} {module.summary(report, resolved, candidates)}"
    rules_record = report.get("rules") or {}
    if rules_record and not rules_record.get("evaluated") and rules_record.get("outcomes"):
        measured += "; nothing judged: the rules have no limit for this part's context"
    warned = f"{warnings} warning(s)" if warnings else ""
    if status == "ok":
        line = f"OK {_shown(label)}: {warned + '; ' if warned else ''}{measured}"
    elif status == "not_checked":
        line = f"NOT CHECKED {_shown(label)}: {_digest(unchecked)}{', ' + warned if warned else ''}; {measured}"
    else:
        # The failed line's digest: the counts, what was measured, then each failing rule and every other error
        # by its code with its count, so one line says what to fix before the findings are read.
        failed = counts["error"] if errors else counts["warning"]
        said = f"{errors} error(s)" + (f", {warned}" if warned else "") + (" (--strict: a warning fails)" if not errors else "")
        line = (f"FAILED {_shown(label)}: {said}; {measured}; failed: {_digest(failed)}"
                + (f"; not checked: {_digest(unchecked)}" if unchecked else ""))
    return CheckResult(ok=status == "ok", path=label, findings=tuple(found), summary=line, measurements=report,
                       status=status, reason=next(iter(unchecked), None) if status == "not_checked" else None)


def _unmeasured_families(report: dict[str, Any], record: dict[str, Any]) -> list[CheckFinding]:
    """What the rules could not judge for want of a whole family: one this source does not measure by its nature
    (the report's ``not_measured``: a mesh's holes, a cut file's bends), said once as a fact with the rules it
    leaves unjudged (``families_not_measured``, info); and one the report lacks though a rule that applies
    reads it (the record's ``absent``), which no one has said: ``measurement_failed``, so the check is not
    checked."""
    found: list[CheckFinding] = []
    by_nature = report.get("not_measured") or {}
    unjudged: dict[str, list[str]] = record.get("not_measured") or {}
    absent: dict[str, list[str]] = record.get("absent") or {}
    if unjudged:
        reasons = "; ".join(dict.fromkeys(str(by_nature[family]) for family in unjudged))
        rules_said = ", ".join(dict.fromkeys(rule for rules_of in unjudged.values() for rule in rules_of))
        found.append(CheckFinding(
            "info", "families_not_measured",
            f"{', '.join(unjudged)} {'is' if len(unjudged) == 1 else 'are'} not measured on this source "
            f"({reasons}): {rules_said} judge nothing here, which is no pass", "rules",
            "check the part's exact geometry (its STEP or its model) for them"))
    for family, rules_of in absent.items():
        found.append(CheckFinding(
            "error", "measurement_failed",
            f"{family} was not measured: the report holds no such family, so {', '.join(rules_of)} "
            f"judge{'s' if len(rules_of) == 1 else ''} nothing", family))
    return found


def measure(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None,
            candidates: bool, given: dict[str, Any] | None = None, strict: bool = False) -> CheckResult:
    """Measure ``source`` with its integration, then ``finish`` it: a B-rep's through the engine, where the
    document is held (``_held``), else in this process (``_here``). With no ``process`` (a B-rep type's, its
    options ``given`` unresolved) the integration reads the document, takes the process its parts declare and
    resolves the options for it (``declared``) before it measures."""
    label = _label(source)
    if isinstance(source, (str, os.PathLike)) and label.is_absolute() and not label.is_file():
        return _failed(label, "file not found", "invalid_target")
    if document_type in BREP_TYPES:
        found = _held(document_type, source, process, resolved, candidates, given, label, strict=strict)
        if found is not None:
            return found
    return _here(document_type, source, process, resolved, candidates, given, label, strict)


def _here(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None, candidates: bool,
          given: dict[str, Any] | None, label: Path, strict: bool = False) -> CheckResult:
    """``source`` (a path) measured by its integration for this caller -- in a process of its own, held to a
    check's limits (``_watched``) -- and finished here. One stopped at a limit, or whose process was lost, is
    not checked (``over_time``, ``over_memory``, ``process_lost``: the engine's words for the same)."""
    found = _watched({"type": document_type, "source": os.fspath(source), "process": process, "resolved": resolved,
                      "candidates": bool(candidates), "given": (given or {}) if process is None else {}})
    if "refused" in found:
        raise ArgumentRefused(found["refused"])
    if "unmeasured" in found:
        return _failed(label, found["unmeasured"]["message"], found["unmeasured"]["code"])
    measured = found["measured"]
    return finish(label, {"process": measured["process"], **measured["report"]}, measured["process"],
                  measured["resolved"], candidates, strict)


def _measured_here(request: dict[str, Any]) -> dict[str, Any]:
    """A check of a file (``_watched``'s ``request``) measured in this process by its integration: plain data,
    as the engine's checks processes answer one (``_dfm_check.held``) -- ``{"measured": {"process", "resolved",
    "report"}}``, ``{"unmeasured": {"code", "message"}}`` or ``{"refused": words}`` (what ``declared`` refuses
    of a document given no process)."""
    document_type, source, process = request["type"], request["source"], request.get("process")
    resolved, candidates = request.get("resolved"), bool(request.get("candidates"))
    try:
        if process is None:
            from cad.build123d._dfm_check import measure_declared

            process, resolved, report = measure_declared(document_type, source, request.get("given") or {}, candidates)
        else:
            if document_type in BREP_TYPES:
                from cad.build123d._dfm_check import measure as measured
            elif document_type in CUT_TYPES:
                from cad.build123d._dfm_dxf import measure as measured
            else:
                from cad.trimesh._check import measure as measured
            report = measured(document_type, source, process, resolved, candidates)
    except dfm.Unmeasured as failure:
        return {"unmeasured": {"code": failure.code, "message": failure.message}}
    except ArgumentRefused as refused:
        return {"refused": str(refused)}
    return {"measured": {"process": process, "resolved": resolved, "report": report}}


#: How often a caller looks at the process that measures its check (``_watched``).
WATCH_SECONDS = 1.0
#: What a caller is told of a check it stopped, or lost, by the reason it is not checked for (the engine's
#: reasons, ``cad.engine.api.check``).
_STOPPED = {
    "over_time": "the manufacturing check was stopped after {seconds:.0f} s, over a check's time limit of "
                 "{limit:g} s: nothing was measured. Check a smaller part or fewer samples, or raise the limit "
                 "(CAD_ENGINE_CHECK_SECONDS, in this environment; 0 for none)",
    "over_memory": "the manufacturing check was stopped with its process at {resident:.0f} MB, over a check's "
                   "memory limit of {limit:.0f} MB: nothing was measured. The part may be too large to check on "
                   "this machine; check a smaller part, or raise the limit (CAD_ENGINE_CHECK_RSS_MB, in this "
                   "environment; 0 for none)",
    "process_lost": "the process measuring the manufacturing check exited ({code}) before it answered{why}: "
                    "nothing was measured",
}
# What the measuring process runs (``_child``): by this module's name, so nothing is run as ``__main__`` twice.
_CHILD = "from cad._internal.manufacturing import _child; _child()"


def _watched(request: dict[str, Any]) -> dict[str, Any]:
    """A check of a file this caller measures itself (``request``: ``{"type", "source", "process", "resolved",
    "candidates", "given"}``, plain data), measured in a process of its own (``_child``, this interpreter's)
    that this one starts and holds to a check's limits from outside, as the engine holds its checks processes:
    the same limits (``cad.engine.worker.check_limits``: ``CAD_ENGINE_CHECK_SECONDS``,
    ``CAD_ENGINE_CHECK_RSS_MB``, the same defaults), read each ``WATCH_SECONDS``, the time from the process's
    start and its memory as the system counts it. From outside, because nothing inside can stop it: a kernel
    call holds the interpreter until it returns, and one that never returns would hold a watchdog there too.
    The process ends with its caller: it holds the read end of a pipe this one keeps open, and leaves when
    that closes (a caller a shell's time limit killed leaves no check running on, measured for no one).

    Its answer, ``_measured_here``'s; or ``{"unmeasured": {"code", "message"}}`` for one stopped at a limit
    (``over_time``, ``over_memory``: its process killed), whose process exited with no answer
    (``process_lost``) or whose measuring itself failed there (``error``: what was raised, in one line) -- the
    engine's reasons for the same. An integration this environment lacks is raised here as there
    (``ModuleNotFoundError``, by the module's name). Where there is no interpreter to start
    (``sys.executable`` empty: an embedded one) the check is measured in this process, unwatched."""
    if not sys.executable:
        return _measured_here(request)
    import site
    import subprocess
    import tempfile
    import time

    from cad.engine.places import windowless
    from cad.engine.worker import check_limits, resident_of

    seconds, memory, notes = check_limits()
    for note in notes:
        print(f"cad: {note}", file=sys.stderr, flush=True)
    # This library first on the child's path where its interpreter would not find it by itself (a checkout, a
    # test's path); never a site-packages folder, which on PYTHONPATH would come before the standard library.
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    if root not in {Path(found).resolve() for found in (*site.getsitepackages(), site.getusersitepackages())}:
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root), env.get("PYTHONPATH")]))

    def stopped(reason: str, **said: Any) -> dict[str, Any]:
        return {"unmeasured": {"code": reason, "message": _STOPPED[reason].format(**said)}}

    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cad-check-") as folder:
        written = Path(folder) / "answer.json"
        process = subprocess.Popen([sys.executable, "-P", "-c", _CHILD, json.dumps(request), str(written)],
                                   stdin=subprocess.PIPE, env=env, **windowless())
        try:
            while True:
                try:
                    process.wait(timeout=WATCH_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                elapsed, limit = time.monotonic() - began, memory()
                resident = resident_of(process.pid) if limit is not None else None
                if seconds is not None and elapsed > seconds:
                    return stopped("over_time", seconds=elapsed, limit=seconds)
                if limit is not None and resident is not None and resident > limit:
                    return stopped("over_memory", resident=resident, limit=limit)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdin is not None:
                process.stdin.close()
        try:
            answer = json.loads(written.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            answer = None
    if not isinstance(answer, dict):
        killed = process.returncode is not None and process.returncode < 0
        return stopped("process_lost", code=process.returncode,
                       why=" (killed by the system, usually for memory -- the part may be too large to check on "
                           "this machine)" if killed else "")
    missing = answer.get("missing")
    if isinstance(missing, dict):
        raise ModuleNotFoundError(missing["words"], name=missing["name"])
    return answer


def _child() -> None:
    """The process ``_watched`` starts: the request in its first argument measured (``_measured_here``) and
    answered in the file its second names, written whole as it ends. Its standard output is its standard error's
    (the kernel's and a library's prints never reach its caller's answer), and its standard input the pipe its
    caller holds open: at its end of file the caller is gone, and so is this process, as soon as the interpreter
    runs. What the integration raised is the check's answer, not checked for ``error``: its type, its words and
    where it was raised, in one line; a module this environment lacks is answered as such (``missing``)."""
    import threading

    os.dup2(2, 1)

    def orphaned() -> None:
        try:
            while os.read(0, 4096):  # the descriptor itself: no lock of ``sys.stdin``'s is held as this process ends
                pass
        except OSError:
            pass
        os._exit(1)

    threading.Thread(target=orphaned, name="cad-check-caller", daemon=True).start()
    try:
        answer = _measured_here(json.loads(sys.argv[1]))
    except ModuleNotFoundError as error:
        answer = {"missing": {"words": str(error), "name": error.name}}
    except Exception as error:  # noqa: BLE001 - a measuring that failed is the check's answer: not checked
        import traceback

        raised = traceback.extract_tb(error.__traceback__)
        where = f" (raised in {Path(raised[-1].filename).name}:{raised[-1].lineno})" if raised else ""
        answer = {"unmeasured": {"code": "error", "message": "the manufacturing check failed where it was "
                                                             f"measured: {type(error).__name__}: {error}{where}"}}
    try:
        # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse than one that says it failed.
        line = json.dumps(answer, separators=(",", ":"), allow_nan=False)
    except ValueError as error:
        line = json.dumps({"unmeasured": {"code": "not_finite", "message": "a measurement was not a finite number, "
                                                                           f"so the report is not JSON: {error}"}})
    Path(sys.argv[2]).write_text(line, encoding="utf-8")


def _held(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None, candidates: bool,
          given: dict[str, Any] | None, label: Path, *, local: bool = True, strict: bool = False) -> CheckResult | None:
    """A B-rep's check through the engine (``cad.engine.api.check``): measured in memory in one of the
    engine's checks processes -- a model's from the bytes the engine holds of it, a STEP's or an xbf's from its
    file, each read once -- or answered from the result the engine kept for an unchanged document, then
    finished here.

    None -- measured by this caller instead (``_here``), as before the engine measured checks -- for a file when no
    engine can be reached, when the engine is of a release that measures no check in memory, or when another
    release of the library measured it (its report could differ from what this release finishes). A model's,
    then, is exported by the engine and read back here (``_exported``), as before; with no engine at all it
    fails to read, as it did. An id the engine does not hold is refused as its type. ``local`` False, for a
    command whose environment holds no kernel (``through_engine``): None for a model too, nothing measured here."""
    from cad.engine import api
    from cad.engine.contract import release

    check = {"type": document_type, "process": process, "resolved": resolved, "candidates": bool(candidates),
             **({"given": {name: value for name, value in (given or {}).items() if value is not None and value is not False}}
                if process is None else {})}
    is_file = isinstance(source, (str, os.PathLike)) and label.is_absolute()
    try:
        found: dict[str, Any] | None = api.check(source, check)
    except api.Unreached as error:
        if is_file:
            return None
        # no engine and nothing to measure here instead: its own reason where the engine's client gives one
        return _failed(label, f"failed to read the document: {error}",
                       str(getattr(error, "reason", None) or "document_unreadable"))
    except api.Unanswered:
        found = None
    except ValueError as error:
        if any(kind.__module__ == "cad.engine.serve" and kind.__name__ == "NotHeld" for kind in type(error).__mro__):
            raise  # the caller's mistake (the command's not_found), not the check's failure
        if is_file:
            return None  # an engine that refused the check: measured here, as before
        return _failed(label, f"failed to read the document: {error}", "document_unreadable")
    if found is None or found.get("release") != release():
        return (None if is_file or not local else
                _exported(document_type, source, process, resolved, candidates, given, label, strict))
    if "refused" in found:
        raise ArgumentRefused(found["refused"])
    if "unmeasured" in found:
        return _failed(label, found["unmeasured"]["message"], found["unmeasured"]["code"])
    measured = found["measured"]
    return finish(label, {"process": measured["process"], **measured["report"]}, measured["process"],
                  measured["resolved"], candidates, strict)


def through_engine(document_type: str, source: Any, process: str | None, given: dict[str, Any],
                   candidates: bool, strict: bool = False) -> CheckResult | None:
    """A B-rep's check asked of the engine by a command that holds no kernel: its result, or None where the
    engine measured nothing (none to reach, another release's), which the command runs in the environment of
    the integration (``cad_server.cli.document_types``), never here."""
    label = _label(source)
    if isinstance(source, (str, os.PathLike)) and label.is_absolute() and not label.is_file():
        return _failed(label, "file not found", "invalid_target")
    resolved = options(document_type, process, given, candidates=candidates)
    return _held(document_type, source, process, resolved, candidates, given, label, local=False, strict=strict)


def _exported(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None,
              candidates: bool, given: dict[str, Any] | None, label: Path, strict: bool = False) -> CheckResult:
    """A model's document checked as before the engine measured checks: exported by the engine to an xbf in a
    temporary folder, read back and measured here (``_here``). An id the engine does not hold is refused as
    its type; any other failure to export it is the check's ``document_unreadable``."""
    import tempfile

    from cad.engine import api

    with tempfile.TemporaryDirectory(prefix="cad-check-") as folder:
        written = Path(folder) / "document.xbf"
        try:
            api.export(source, written, progress=False)
        except Exception as error:  # noqa: BLE001 - a document that does not export is the check's answer
            if any(kind.__module__ == "cad.engine.serve" and kind.__name__ == "NotHeld" for kind in type(error).__mro__):
                raise
            return _failed(label, f"failed to read the document: {error}", "document_unreadable")
        return _here(document_type, written, process, resolved, candidates, given, label, strict)


def _declared_material(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    """``resolved`` with the material the parts declare (``part.material = metals.aluminum()``, carried by the
    document) where none was given and every part that declares one names the same material of the table;
    the report says so (``material_declared``), or that the parts disagree (``material_mixed``: judged as
    with no material). A material given wins, and where the parts declare another the report says so too."""
    bodies = [body for body in report.get("bodies") or () if isinstance(body, dict)]
    names = sorted({body["material_table"] for body in bodies if body.get("material_table")})
    if resolved.get("material") is not None:
        from cad._internal.dfm import materials

        given = materials.resolve(resolved["material"])
        if names and names != [given]:
            report.setdefault("findings", []).append(
                {"severity": "info", "code": "material_declared", "location": "bodies",
                 "message": f"material {given} as given, not the {', '.join(names)} the parts declare: "
                            f"judged as {given}"})
        return resolved
    found = report.setdefault("findings", [])
    if len(names) == 1:
        declared = sorted({str(body["material"]) for body in bodies if body.get("material")})
        found.append({"severity": "info", "code": "material_declared", "location": "bodies",
                      "message": f"material {names[0]}, read from the part's declared material "
                                 f"({', '.join(declared[:3])}): give --material to judge another"})
        return {**resolved, "material": names[0]}
    if len(names) > 1:
        found.append({"severity": "info", "code": "material_mixed", "location": "bodies",
                      "message": f"the parts declare different materials ({', '.join(names)}), so none is "
                                 f"taken: give --material, or check each part on its own"})
    return resolved



# --- the function each type answers ``dfm`` with -------------------------------------------------------------

#: Each option's help line (``name: text``, the convention the command's generated parser reads its help from):
#: the process it is of first, so a type's help names whose each flag is.
_HELP = {
    "material": "the part's material (aluminum, steel, stainless, abs, pc, nylon, ...): picks the material's "
                "limits; default the material the part declares (part.material = metals.aluminum()), when every "
                "part agrees.",
    "units": "the file's length units (mm, cm, m, in, ft): an STL's (default mm), or a DXF's (default the "
             "ones it declares; needed where it declares none, as an R12 file).",
    "axes": "cnc: the milling machine's axes, 3, 4 or 5; default 3.",
    "turning": "cnc: the part is turned on a lathe (its axis found), not milled.",
    "tools": "cnc: the end mill diameters available, in mm, comma separated (3,6,10); default none: a corner "
             "is held to the smallest tool that can exist (0.05 mm across, text-to-cad's own floor) and to how "
             "deep a tool of its size reaches; a radius of 1.25 mm or more (a 2.5 mm end mill's) is recommended.",
    "stock": "cnc: the stock's size in mm (100x60x25); default the part's box.",
    "thickness": "sheet: the stock's thickness in mm; default measured.",
    "k_factor": "sheet: the neutral axis's place in the thickness, for the flat pattern (the shop's bend "
                "table's); default a K-factor chart's, by the material and each bend's radius.",
    "bend_radius": "sheet: the shop's inside bend radius in mm, compared with the part's.",
    "kerf": "sheet: the cutting kerf in mm, for small features.",
    "sheet_size": "sheet: the shop's largest sheet in mm (1219x2438); default a standard 5 x 10 ft sheet "
                  "(3048x1524), assumed.",
    "pull": "molding: the pull direction, an axis (z, -y) or x,y,z components; default z.",
    "wall_limit": "molding: faces at or above this many degrees from the pull are not walls; default 45.",
    "zero_tol": "molding: draft under this many degrees is zero draft; default 0.05.",
    "cavities": "molding: cavities in the mold, for the clamp force; default 1.",
    "technology": "printing: fdm, sls, sla, mjf or pbf (metal powder bed); default fdm.",
    "build_volume": "printing: the printer's build volume in mm (256x256x256); default a typical machine of "
                    "the technology's, assumed.",
    "angle_limit": "printing: down-facing faces under this many degrees from horizontal need support; default "
                   "the technology's.",
    "samples": "printing: rays cast for the wall-thickness field on a mesh; default 2000.",
    "layer_height": "printing: the layer height in mm, for stair-stepping; default the technology's.",
    "nozzle": "printing: fdm's nozzle diameter in mm; default 0.4.",
}
# The enumerations among the options: the command's choices.
_ENUMS: dict[str, Any] = {"units": Unit, "technology": Technology}

_SUMMARY = {
    "brep": "Check a part for a manufacturing process: CNC machining, sheet metal, injection molding or 3D printing.",
    "mesh": "Check a mesh for 3D printing.",
    "cut": "Check a sheet's cut file (a DXF) for laser, waterjet or router cutting: the sheet process.",
}
# The exit statuses, in the summary the command's help shows.
_STATUSES = ("Exit 0: OK. Exit 1: FAILED, a finding is an error (with --strict, a warning too). Exit 3: NOT CHECKED, "
             "something was not judged: never a pass. Exit 2: the command line's mistake.")
# What the last line and the exit status say, under every type's help.
_EXITS = """The last line and the exit status are the check's state. OK, exit 0: everything was measured and no
finding is an error. FAILED, exit 1: a finding is an error (with --strict, a warning too): the part cannot be
made by this process as drawn. NOT CHECKED, exit 3: the check did not judge what it was asked to -- a source
that does not read or holds no solid, a family that could not be measured, an engine that stopped -- which
is no verdict and never a pass. Exit 2: the command line's mistake."""
_ABOUT = {
    "brep": """A STEP, an xbf or a model's document is measured on its exact geometry, each finding at a face ref
(cad xbf inspect DOC REF resolves it). The measurements are facts; the verdicts are general rules, each
from a published design guide and no shop's limit, each finding coded by its rule, with the limit, the source
and what to change. A rule's feasibility limit broken is an error; a recommendation is a warning. For a named
shop, compare the measurements with its own published limits. --json carries every measurement, every rule's
outcome and each verdict as data (value, limit, unit, refs).
""" + _EXITS,
    "mesh": """A mesh (STL, 3MF, GLB) is measured as triangles for 3D printing, each finding at x, y, z; CNC
machining and sheet metal need the exact radii, axes and thicknesses a mesh does not hold, and injection
molding's draft, undercuts and walls are judged on exact geometry: check the part's STEP or model for them. The measurements are facts; the verdicts are general rules, each from a published design guide and
no shop's limit, each finding coded by its rule, with the limit, the source and what to change. A rule's
feasibility limit broken is an error; a recommendation is a warning. For a named shop, compare the
measurements with its own published limits. --json carries every measurement, every rule's outcome and each
verdict as data (value, limit, unit).
""" + _EXITS,
    "cut": """Its units, closed contours on the cut layers, curves cut twice (overlapping, crossing, zero-area),
annotation on a cut layer, curves drawn as short lines, and holes, slots, webs and spacing against the kerf
and the thickness, judged against general rules, each cited; each finding at a layer and an entity handle.
A rule's feasibility limit broken is an error, a recommendation a warning; for a named shop, compare the
measurements with its own published limits. --json carries every measurement and every rule's outcome.
""" + _EXITS,
}


def _kind_of(document_type: str) -> str:
    return "cut" if document_type in CUT_TYPES else "brep" if document_type in BREP_TYPES else "mesh"


def _source_help(document_type: str) -> str:
    if document_type == "model":
        return "a model's document id the engine holds (cad run SCRIPT.py prints it), or the handle its call returns."
    from cad.registry import DOCUMENT_TYPES

    extensions = " or ".join(DOCUMENT_TYPES[document_type].extensions)
    return f"the {extensions} cut file to check." if document_type in CUT_TYPES else f"the {extensions} file to check."


def _process_help(document_type: str, processes: tuple[str, ...]) -> str:
    if len(processes) == 1 and document_type not in (*BREP_TYPES, *CUT_TYPES):
        return (f"{processes[0]}, the one process a mesh is checked for (the default); cnc, sheet and molding are "
                "judged on exact geometry: check the part's STEP or model for them.")
    if len(processes) == 1:
        return f"{processes[0]}, the one process a {document_type.upper()} is checked for (the default)."
    named = f"{', '.join(processes[:-1])} or {processes[-1]}"
    if document_type not in BREP_TYPES:
        return f"{named}; a mesh holds no exact radius, axis or thickness, so cnc and sheet check its STEP."
    declared = ("the process the parts declare (part.material = metals.aluminum(process=machined()): machined is "
                "cnc, molded molding, fdm, sls, mjf, slm and vat printing with technology fdm, sls, mjf, pbf and "
                "sla), when every part agrees")
    return f"{named}; default, for a STEP, an xbf or a model, " + (
        "none: a STEP keeps no process." if document_type == "step" else f"{declared}.")


def _signature(document_type: str) -> tuple[inspect.Signature, str]:
    """``cad.<document_type>.dfm``'s signature -- the source, the type's processes, and the options of those
    processes alone (a mesh's help offers no ``--axes``) -- and its docstring, built for the type."""
    processes = processes_for(document_type)
    # ``units`` is an STL's and a DXF's: a type that always declares its units takes no option it would refuse
    # every value of
    names = [name for name in KINDS if (name in dfm.COMMON and (name != "units" or document_type not in _DECLARED))
             or any(name in OPTIONS[process] for process in processes)]
    ranked = any(process in _RANKED for process in processes)
    # the type's processes, the parser's choices; a mesh's every process, the ones it is not checked for
    # refused by ``options`` with the reason and the fix
    offered = PROCESSES if _kind_of(document_type) == "mesh" else processes
    choice: Any = Literal[offered]  # type: ignore[valid-type]
    one = len(processes) == 1
    keyword = inspect.Parameter.KEYWORD_ONLY
    parameters = [inspect.Parameter("source", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Path),
                  inspect.Parameter("process", keyword, default=processes[0] if one else None,
                                    annotation=choice if one else choice | None)]
    for name in names:
        kind = KINDS[name]
        annotation = bool if kind is bool else _ENUMS.get(name, kind) | None
        parameters.append(inspect.Parameter(name, keyword, default=False if kind is bool else None,
                                            annotation=annotation))
    if ranked:
        parameters.append(inspect.Parameter("candidates", keyword, default=False, annotation=bool))
    parameters.append(inspect.Parameter("strict", keyword, default=False, annotation=bool))
    helps = {"source": _source_help(document_type), "process": _process_help(document_type, processes),
             **{name: _HELP[name] for name in names}}
    if ranked:
        helps["candidates"] = ("rank the candidates instead: " + ", ".join(
            {"molding": "molding the pulls (x, y, z and the part's principal axes)",
             "printing": "printing the orientations"}[process] for process in processes if process in _RANKED) + ".")
    helps["strict"] = "a warning fails the check too (exit 1): a gate that takes no recommendation broken."
    kind = _kind_of(document_type)
    doc = "\n\n".join([f"{_SUMMARY[kind]} {_STATUSES}", _ABOUT[kind],
                       "\n".join(f"{name}: {text}" for name, text in helps.items())])
    return inspect.Signature(parameters, return_annotation=CheckResult), doc


#: A flag in a refusal's words (``--layer-height``), but inside a command written out (``(cad step dfm ...)``).
_FLAG = re.compile(r"\((?:cad |a shop)[^)]*\)|--([a-z][a-z-]*[a-z])")


def parameters(words: str) -> str:
    """A refusal's ``words`` as a Python caller reads them: each option by its parameter's name (``tools``,
    ``layer_height``), not the command line's flag (``--tools``, ``--layer-height``). A command written out in
    brackets is left as it is."""
    known = {*KINDS, "process", "candidates", "strict"}

    def named(match: "re.Match[str]") -> str:
        name = (match.group(1) or "").replace("-", "_")
        return name if name in known else match.group(0)

    return _FLAG.sub(named, words)


def called(document_type: str, signature: inspect.Signature, args: tuple[Any, ...], kwargs: dict[str, Any]) -> CheckResult:
    """``cad.<document_type>.dfm(*args, **kwargs)``, run: its options resolved, its source measured, its result
    finished. A refusal names the command line's flags (``ArgumentRefused``), as the options' own words do."""
    bound = signature.bind(*args, **kwargs)  # TypeError for an option this type's check does not take
    bound.apply_defaults()
    given = dict(bound.arguments)
    source, process, candidates = given.pop("source"), given.pop("process"), given.pop("candidates", False)
    strict = given.pop("strict", False)
    from cad._internal.dfm import _common

    _common.require_bool("strict", strict)
    resolved = options(document_type, process, given, candidates=candidates)
    if process is None and resolved is not None:
        process = processes_for(document_type)[0]
    from cad._internal.document_type import refuse_other

    refuse_other(document_type, source)
    try:
        return measure(document_type, source, process, resolved, candidates, given, strict)
    except ModuleNotFoundError as error:
        from cad._internal.integrations import missing

        said = missing(error)
        if said is None:
            raise
        raise ModuleNotFoundError(said, name=error.name) from None


def dfm_for(document_type: str) -> Any:
    """``cad.<document_type>.dfm``: the manufacturing check, for a source of that type. Its signature is the
    type's (``_signature``): its processes the command's choices, and only their options, so ``cad stl dfm``
    offers no CNC flag and ``cad dxf dfm`` checks the sheet's cut file given no ``--process``.

    A Python caller's refusal names the parameter (``tools``, not ``--tools``: ``parameters``); the command
    calls it with ``_command=True`` -- a keyword of the command's own, in no signature -- and reads its flags."""
    signature, doc = _signature(document_type)

    def dfm(*args: Any, _command: bool = False, **kwargs: Any) -> CheckResult:
        if _command:
            return called(document_type, signature, args, kwargs)
        try:
            return called(document_type, signature, args, kwargs)
        except ArgumentRefused as refused:
            raise ArgumentRefused(parameters(str(refused))) from None

    dfm.__signature__ = signature  # type: ignore[attr-defined]
    dfm.__annotations__ = {**{name: parameter.annotation for name, parameter in signature.parameters.items()},
                           "return": CheckResult}
    dfm.__doc__ = doc
    dfm.__module__ = f"cad.{document_type}"
    dfm.__qualname__ = dfm.__name__ = "dfm"
    return dfm
