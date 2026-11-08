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
finding at a ref ``cad xbf inspect`` resolves (``plate/face 7``) -- through the engine, in the kernel process
that holds the document (``_held``, ``cad.engine.api.check``), a file in this process only where no engine can
be reached; an STL, a 3MF and a GLB by the trimesh integration (``cad.trimesh._check``), in this process, each
finding at ``x, y, z``. The report is the result's
``measurements``, facts alone. The verdicts are the process's rules (``dfm.<process>.RULES``): general
practice, no shop's -- every rule a limit on one measured figure with the published guide that states it, a
failing one a finding whose code is the rule's id and whose hint says what to change; the record of every
rule is ``measurements["rules"]``. A shop's own limits are no option here: they are compared with the
measurements (a shop's skill does), and what a person knows of their own shop is a plain option (the
tools, the bend radius, the sheet, the build volume).

Each option belongs to a process (``dfm.<process>.OPTIONS``) or to all (``dfm.COMMON``), and one given to
another process is refused by name before anything is read, as an option the check does not take would be
(law 16), and so is a value of another kind (``KINDS``: never coerced, law 17). Each type's ``dfm`` takes the
processes it can be checked for (``processes_for``: a mesh molding and printing, a DXF sheet) and their
options alone. The standard library alone: the server's command resolves the options here before it starts
an environment that holds the integration. An xbf or a model given no process is checked for the one its
parts declare (``part.material = metals.aluminum(process=machined())``): the options every process shares
are checked here, and the integration reads the document, takes the declared process and resolves the rest
(``declared``) before it measures. A STEP keeps no process, so one given none is refused here.
"""

from __future__ import annotations

import inspect
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Literal, get_args

from cad._internal import dfm
from cad._internal.refused import ArgumentRefused
from cad.results import CheckFinding, CheckResult

__all__ = ["BREP_TYPES", "DEFAULTS", "KINDS", "OPTIONS", "PROCESSES", "UNITS_MM", "declared", "dfm_for", "finish", "options",
           "processes_for"]

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
#: Length units a mesh file may carry, as a factor to millimetres. An STL is unitless, so the caller says
#: which one; the other types declare theirs.
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
    from triangles (molding, printing: no exact radius, axis or thickness is needed); a DXF's sheet alone."""
    if document_type in CUT_TYPES:
        return ("sheet",)
    if document_type in BREP_TYPES:
        return PROCESSES
    return tuple(process for process in PROCESSES if "mesh" in dfm.module(process).MEASURED_FROM)
# The types that declare their own units, read as millimetres: a units option is the STL's alone.
_DECLARED = {"threemf": "a 3MF declares its unit", "glb": "a GLB is in glTF's metres",
             "step": "a STEP declares its units", "xbf": "an xbf is in millimetres",
             "model": "a model is in millimetres",
             "dxf": "a DXF declares its units ($INSUNITS)"}
# The processes that rank candidates: the pulls, the orientations.
_RANKED = ("molding", "printing")


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _give_process(document_type: str, why: str = "") -> ArgumentRefused:
    named = processes_for(document_type)
    return ArgumentRefused(f"cad.{document_type}.dfm measures for a process{why}: give --process "
                           + (f"{', '.join(named[:-1])} or {named[-1]}" if len(named) > 1 else named[0]))


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
    _kinds(given, candidates)
    if process is None and len(processes_for(document_type)) == 1:
        process = processes_for(document_type)[0]
    if process is None:
        if document_type not in BREP_TYPES:
            raise _give_process(document_type)
        return _preflight(document_type, given, candidates)
    module = dfm.module(process)
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
    units = resolved["units"]
    if units not in UNITS_MM:
        raise ArgumentRefused(f"--units is one of {', '.join(UNITS_MM)}, not {units!r}")
    if units != "mm" and document_type in _DECLARED:
        raise ArgumentRefused(f"{_DECLARED[document_type]}, read as millimetres: --units is an STL's, which declares none")
    from cad._internal.dfm import materials

    materials.resolve(resolved.get("material"))
    if "mesh" not in module.MEASURED_FROM and document_type not in (*BREP_TYPES, *CUT_TYPES):
        raise ArgumentRefused(f"a {process} check measures exact geometry -- radii, axes, thicknesses -- that a mesh "
                         f"does not hold: check the part's STEP, xbf or model (cad step dfm, cad xbf dfm, cad model dfm)")
    module.validate(resolved, document_type)
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
        raise ArgumentRefused(f"{_DECLARED[document_type]}, read as millimetres: --units is an STL's, which declares none")
    from cad._internal.dfm import materials

    materials.resolve(given.get("material"))
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
#: What puts every other figure in doubt, said before the errors whatever its severity: a mesh not watertight
#: or not sound (its walls, voids and volume are of an open or broken surface), a family that could not be
#: measured, units that look wrong (every length off by a factor).
_FIRST = frozenset({"not_watertight", "not_sound", "measurement_failed", "units_suspect"})


def _failed(path: Path, message: str, code: str) -> CheckResult:
    return CheckResult(ok=False, path=path, findings=(CheckFinding("error", code, message),))


def finish(label: Path, report: dict[str, Any], process: str, resolved: dict[str, Any],
           candidates: bool) -> CheckResult:
    """The result of a measured ``report``: the measurement's findings, the process's, and the verdicts of its
    rules, which the report records (``measurements["rules"]``)."""
    from cad._internal.dfm import _common, rules

    module = dfm.module(process)
    resolved = _declared_material(report, resolved)
    found: list[CheckFinding] = [*_common.partial_findings(report), *_common.scale_findings(report),
                                 *(CheckFinding(**finding) for finding in report.pop("findings", None) or ()),
                                 *module.findings(report, resolved, candidates)]
    if not candidates:
        rule_set = module.RULES
        verdicts, record = rules.evaluate(report, rule_set, module.context(report, resolved))
        report["rules"] = record
        found.extend(verdicts)
        if not record["evaluated"] and record["outcomes"]:
            found.append(CheckFinding(
                "warning", "rules_none_evaluated",
                "the rules judged nothing here: none has a limit for this part's context (every outcome is "
                "not_evaluated or not_applicable), so nothing is verified", "rules",
                "read the measurements against the process's published limits"))
        found.append(CheckFinding(
            "info", "rules_general",
            f"the verdicts are {rule_set.title} (version {rule_set.version}): general practice drawn from "
            f"published design guides, no shop's limits", "rules",
            "for a named shop, compare the measurements with its own published limits, or use its skill"))
    try:
        # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse than one that says it failed.
        json.dumps(report, allow_nan=False)
    except ValueError as error:
        return _failed(label, f"a measurement was not a finite number, so the report is not JSON: {error}",
                       "not_finite")
    # What puts every figure in doubt first (``_FIRST``, whatever its severity), then errors, warnings, and the
    # facts and assumptions: what a reader acts on comes first.
    found.sort(key=lambda finding: (finding.code not in _FIRST, _ORDER.get(finding.severity, 3)))
    ok = not any(finding.severity == "error" for finding in found)
    from cad._internal.validation_door import display_path

    measured = module.summary(report, resolved, candidates)
    if ok:
        line = f"OK {display_path(label) if label.is_absolute() else label}: {process} {measured}"
        rules_record = report.get("rules") or {}
        if rules_record and not rules_record.get("evaluated") and rules_record.get("outcomes"):
            line += "; nothing judged: the rules have no limit for this part's context"
        warned = sum(1 for finding in found if finding.severity == "warning")
        if warned:
            line += f" ({warned} warning(s))"
    else:
        # The failed line's digest: what was measured, then each failing rule with its count of failures (the
        # record's, not the findings shown), then every other error by its code, so one line says what to fix
        # before the findings are read.
        failed: Counter[str] = Counter()
        for outcome in (report.get("rules") or {}).get("outcomes") or ():
            if outcome.get("status") == "failed":
                failed[outcome["rule"]] += sum(1 for failure in outcome.get("failures") or ()
                                               if failure.get("severity", outcome.get("severity")) == "error")
        failed = Counter({code: count for code, count in failed.items() if count})
        for finding in found:
            if finding.severity == "error" and finding.code and finding.code not in failed:
                failed[finding.code] += 1
        line = f"{process} {measured}; failed: " + ", ".join(f"{code} x{count}" for code, count in failed.most_common())
    return CheckResult(ok=ok, path=label, findings=tuple(found), summary=line, measurements=report)


def measure(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None,
            candidates: bool, given: dict[str, Any] | None = None) -> CheckResult:
    """Measure ``source`` with its integration, then ``finish`` it. With no ``process`` (a B-rep type's, its
    options ``given`` unresolved) the integration reads the document, takes the process its parts declare and
    resolves the options for it (``declared``) before it measures."""
    label = _label(source)
    if isinstance(source, (str, os.PathLike)) and label.is_absolute() and not label.is_file():
        return _failed(label, "file not found", "invalid_target")
    if document_type in BREP_TYPES:
        found = _held(document_type, source, process, resolved, candidates, given, label)
        if found is not None:
            return found
    if process is None:
        from cad.build123d._dfm_check import measure_declared

        try:
            process, resolved, report = measure_declared(document_type, source, given or {}, candidates)
        except dfm.Unmeasured as failure:
            return _failed(label, failure.message, failure.code)
        return finish(label, {"process": process, **report}, process, resolved, candidates)
    assert resolved is not None
    if document_type in BREP_TYPES:
        from cad.build123d._dfm_check import measure as measured
    elif document_type in CUT_TYPES:
        from cad.build123d._dfm_dxf import measure as measured
    else:
        from cad.trimesh._check import measure as measured
    try:
        report = measured(document_type, source, process, resolved, candidates)
    except dfm.Unmeasured as failure:
        return _failed(label, failure.message, failure.code)
    return finish(label, {"process": process, **report}, process, resolved, candidates)


def _held(document_type: str, source: Any, process: str | None, resolved: dict[str, Any] | None, candidates: bool,
          given: dict[str, Any] | None, label: Path) -> CheckResult | None:
    """A B-rep's check through the engine (``cad.engine.api.check``): measured in the kernel process that
    holds the document -- a model's in its warm worker, a STEP's or an xbf's in the documents worker, read
    once -- or answered from the engine's kept results for an unchanged document, then finished here. None
    for a file when no engine can be reached: it is measured in this process, as it always could be. A model
    with no engine fails to read, as it did; an id the engine does not hold is refused as its type."""
    from cad.engine import api

    check = {"type": document_type, "process": process, "resolved": resolved, "candidates": bool(candidates),
             **({"given": {name: value for name, value in (given or {}).items() if value is not None and value is not False}}
                if process is None else {})}
    is_file = isinstance(source, (str, os.PathLike)) and label.is_absolute()
    try:
        found = api.check(source, check)
    except api.Unreached as error:
        if is_file:
            return None
        return _failed(label, f"failed to read the document: {error}", "document_unreadable")
    except ValueError as error:
        if any(kind.__module__ == "cad.engine.serve" and kind.__name__ == "NotHeld" for kind in type(error).__mro__):
            raise  # the caller's mistake (the command's not_found), not the check's failure
        return _failed(label, f"failed to read the document: {error}", "document_unreadable")
    if "refused" in found:
        raise ArgumentRefused(found["refused"])
    if "unmeasured" in found:
        return _failed(label, found["unmeasured"]["message"], found["unmeasured"]["code"])
    measured = found["measured"]
    return finish(label, {"process": measured["process"], **measured["report"]}, measured["process"],
                  measured["resolved"], candidates)


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
    "units": "the file's length units (mm, cm, m, in, ft), an STL's alone; default mm.",
    "axes": "cnc: the milling machine's axes, 3, 4 or 5; default 3.",
    "turning": "cnc: the part is turned on a lathe (its axis found), not milled.",
    "tools": "cnc: the end mill diameters available, in mm, comma separated (3,6,10); default none: a sharp "
             "corner is held to the smallest standard end mill, 2.5 mm.",
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
    "mesh": "Check a mesh for a manufacturing process: injection molding or 3D printing.",
    "cut": "Check a sheet's cut file (a DXF) for laser, waterjet or router cutting: the sheet process.",
}
_ABOUT = {
    "brep": """A STEP, an xbf or a model's document is measured on its exact geometry, each finding at a face ref
(cad xbf inspect DOC REF resolves it). The measurements are facts; the verdicts are general rules, each
from a published design guide and no shop's limit, each finding coded by its rule, with the limit, the source
and what to change. A rule's feasibility limit broken is an error, as is a family that could not be measured;
a recommendation is a warning. For a named shop, compare the measurements with its own published limits.
--json carries every measurement and every rule's outcome.""",
    "mesh": """A mesh (STL, 3MF, GLB) is measured as triangles, each finding at x, y, z; CNC machining and sheet
metal need the exact radii, axes and thicknesses a mesh does not hold: check the part's STEP, xbf or model
for them. The measurements are facts; the verdicts are general rules, each from a published design guide and
no shop's limit, each finding coded by its rule, with the limit, the source and what to change. A rule's
feasibility limit broken is an error, as is a family that could not be measured; a recommendation is a
warning. For a named shop, compare the measurements with its own published limits. --json carries every
measurement and every rule's outcome.""",
    "cut": """Its units, closed contours on the cut layers, curves cut twice (overlapping, crossing, zero-area),
annotation on a cut layer, curves drawn as short lines, and holes, slots, webs and spacing against the kerf
and the thickness, judged against general rules, each cited; each finding at a layer and an entity handle.
A rule's feasibility limit broken is an error, a recommendation a warning; for a named shop, compare the
measurements with its own published limits. --json carries every measurement and every rule's outcome.""",
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
    names = [name for name in KINDS if name in dfm.COMMON or any(name in OPTIONS[process] for process in processes)]
    ranked = any(process in _RANKED for process in processes)
    choice: Any = Literal[processes]  # type: ignore[valid-type]  # the type's processes, the parser's choices
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
    helps = {"source": _source_help(document_type), "process": _process_help(document_type, processes),
             **{name: _HELP[name] for name in names}}
    if ranked:
        helps["candidates"] = ("rank the candidates instead: " + ", ".join(
            {"molding": "molding the pulls (x, y, z and the part's principal axes)",
             "printing": "printing the orientations"}[process] for process in processes if process in _RANKED) + ".")
    kind = _kind_of(document_type)
    doc = "\n\n".join([_SUMMARY[kind], _ABOUT[kind], "\n".join(f"{name}: {text}" for name, text in helps.items())])
    return inspect.Signature(parameters, return_annotation=CheckResult), doc


def dfm_for(document_type: str) -> Any:
    """``cad.<document_type>.dfm``: the manufacturing check, for a source of that type. Its signature is the
    type's (``_signature``): its processes the command's choices, and only their options, so ``cad stl dfm``
    offers no CNC flag and ``cad dxf dfm`` checks the sheet's cut file given no ``--process``."""
    signature, doc = _signature(document_type)

    def dfm(*args: Any, **kwargs: Any) -> CheckResult:
        bound = signature.bind(*args, **kwargs)  # TypeError for an option this type's check does not take
        bound.apply_defaults()
        given = dict(bound.arguments)
        source, process, candidates = given.pop("source"), given.pop("process"), given.pop("candidates", False)
        resolved = options(document_type, process, given, candidates=candidates)
        if process is None and resolved is not None:
            process = processes_for(document_type)[0]
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            return measure(document_type, source, process, resolved, candidates, given)
        except ModuleNotFoundError as error:
            from cad._internal.integrations import missing

            said = missing(error)
            if said is None:
                raise
            raise ModuleNotFoundError(said, name=error.name) from None

    dfm.__signature__ = signature  # type: ignore[attr-defined]
    dfm.__annotations__ = {**{name: parameter.annotation for name, parameter in signature.parameters.items()},
                           "return": CheckResult}
    dfm.__doc__ = doc
    dfm.__module__ = f"cad.{document_type}"
    dfm.__qualname__ = dfm.__name__ = "dfm"
    return dfm
