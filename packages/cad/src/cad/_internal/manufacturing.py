"""The manufacturing check every 3D document type shares: ``cad.<type>.dfm(source, process=...)``.

``model``, ``stl``, ``threemf``, ``glb``, ``step``, ``xbf`` and, as a sheet's cut file, ``dxf`` each answer
``dfm`` with the same function, made for the type here (``dfm_for``): its signature takes a path (or, for a
model, its document id or handle) and plain values alone, so it is the type's (the signature rule). Four processes, each a
module of ``cad._internal.dfm`` (its options, rule sets, findings and summary):

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
finding at a ref ``cad xbf inspect`` resolves (``plate/face 7``); an STL, a 3MF and a GLB by the trimesh
integration (``cad.trimesh._check``), each finding at ``x, y, z``. The report is the result's
``measurements``, facts alone. The verdicts are the rule set's (``rules``, ``generic`` by default, ``none``
for facts alone): every rule a limit on one measured figure with its source, a failing one a finding whose
code is the rule's id and whose hint says what to change; the record of every rule is
``measurements["rules"]``.

Each option belongs to a process (``dfm.<process>.OPTIONS``) or to all (``dfm.COMMON``), and one given to
another process is refused by name before anything is read, as an option the check does not take would be
(law 16). The standard library alone: the server's command resolves the options here before it starts an
environment that holds the integration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cad._internal import dfm
from cad.results import CheckFinding, CheckResult

__all__ = ["BREP_TYPES", "DEFAULTS", "OPTIONS", "PROCESSES", "UNITS_MM", "dfm_for", "finish", "options"]

PROCESSES = dfm.PROCESSES
#: The types measured on their B-rep (the build123d integration); the rest are meshes (trimesh), but a DXF,
#: a sheet's cut file, checked by the build123d integration's DXF library (ezdxf).
BREP_TYPES = ("model", "step", "xbf")
CUT_TYPES = ("dxf",)
#: Length units a mesh file may carry, as a factor to millimetres. An STL is unitless, so the caller says
#: which one; the other types declare theirs.
UNITS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}


def _options() -> dict[str, dict[str, Any]]:
    return {process: dict(dfm.module(process).OPTIONS) for process in PROCESSES}


#: Each process's own options and their defaults (``dfm.COMMON``'s are every process's, ``candidates`` too).
OPTIONS: dict[str, dict[str, Any]] = _options()
DEFAULTS = {**dfm.COMMON, **{name: value for given in OPTIONS.values() for name, value in given.items()}}
# The types that declare their own units, read as millimetres: a units option is the STL's alone.
_DECLARED = {"threemf": "a 3MF declares its unit", "glb": "a GLB is in glTF's metres",
             "step": "a STEP declares its units", "xbf": "an xbf is in millimetres",
             "model": "a model is in millimetres",
             "dxf": "a DXF declares its units ($INSUNITS)"}
# The processes that rank candidates: the pulls, the orientations.
_RANKED = ("molding", "printing")


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def options(document_type: str, process: str | None, given: dict[str, Any], *, candidates: bool = False) -> dict[str, Any]:
    """The options a check of ``process`` runs with: those ``given`` (None, or False for a flag: not given),
    the defaults for the rest. ``ValueError`` naming the fix for no process or another, an option of another
    process, a pull beside ``candidates`` (which ranks every pull), ``candidates`` of a process that ranks
    none, a units the type does not take, a rule set the process has not, or a value out of range."""
    if process is None:
        raise ValueError(f"cad.{document_type}.dfm measures for a process: give --process "
                         f"{', '.join(PROCESSES[:-1])} or {PROCESSES[-1]}")
    module = dfm.module(process)
    if document_type in CUT_TYPES and process != "sheet":
        raise ValueError(f"a DXF is checked as a sheet's cut file: --process sheet, not {process}")
    own = {**dfm.COMMON, **module.OPTIONS}
    foreign = [name for name, value in given.items() if value is not None and value is not False and name not in own]
    if foreign:
        takes = ", ".join(_flag(name) for name in (*module.OPTIONS, *dfm.COMMON,
                                                    *(("candidates",) if process in _RANKED else ())))
        raise ValueError(f"{', '.join(_flag(name) for name in foreign)} {'is' if len(foreign) == 1 else 'are'} not "
                         f"{process}'s: a {process} check takes {takes}")
    if candidates and process not in _RANKED:
        raise ValueError(f"--candidates ranks molding's pulls or printing's orientations; a {process} check has none")
    if candidates and given.get("pull") is not None:
        raise ValueError("--candidates ranks every pull: give it no --pull")
    resolved = {name: given[name] if given.get(name) is not None else default for name, default in own.items()}
    units = resolved["units"]
    if units not in UNITS_MM:
        raise ValueError(f"--units is one of {', '.join(UNITS_MM)}, not {units!r}")
    if units != "mm" and document_type in _DECLARED:
        raise ValueError(f"{_DECLARED[document_type]}, read as millimetres: --units is an STL's, which declares none")
    if resolved["rules"] != "none" and resolved["rules"] not in module.RULE_SETS:
        raise ValueError(f"--rules for {process} is one of {', '.join((*module.RULE_SETS, 'none'))}, "
                         f"not {resolved['rules']!r}")
    from cad._internal.dfm import materials

    materials.resolve(resolved.get("material"))
    if "mesh" not in module.MEASURED_FROM and document_type not in (*BREP_TYPES, *CUT_TYPES):
        raise ValueError(f"a {process} check measures exact geometry -- radii, axes, thicknesses -- that a mesh "
                         f"does not hold: check the part's STEP, xbf or model (cad step dfm, cad xbf dfm, cad model dfm)")
    module.validate(resolved, document_type)
    return resolved


def _label(source: Any) -> Path:
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        return Path(os.fspath(source)).expanduser().resolve()
    ident = getattr(source, "id", None)  # a document's handle; a model, by its name
    if ident is None and isinstance(source, (str, os.PathLike)):
        ident = os.fspath(source)
    return Path(str(ident or getattr(source, "name", None) or source))


def _failed(path: Path, message: str, code: str) -> CheckResult:
    return CheckResult(ok=False, path=path, findings=(CheckFinding("error", code, message),))


def finish(label: Path, report: dict[str, Any], process: str, resolved: dict[str, Any],
           candidates: bool) -> CheckResult:
    """The result of a measured ``report``: the measurement's findings, the process's, and the rule set's
    verdicts, which the report records (``measurements["rules"]``)."""
    from cad._internal.dfm import _common, rules

    module = dfm.module(process)
    found: list[CheckFinding] = [*_common.partial_findings(report), *_common.scale_findings(report),
                                 *(CheckFinding(**finding) for finding in report.pop("findings", None) or ()),
                                 *module.findings(report, resolved, candidates)]
    chosen = resolved.get("rules", "generic")
    if not candidates and chosen != "none":
        rule_set = module.RULE_SETS[chosen]
        verdicts, record = rules.evaluate(report, rule_set, module.context(report, resolved))
        report["rules"] = record
        found.extend(verdicts)
        if rule_set.generic:
            found.append(CheckFinding(
                "info", "rules_generic",
                f"the verdicts are {rule_set.title}'s rules (version {rule_set.version}), a starting point drawn "
                f"from published guides, not a shop's limits", "rules",
                f"give --rules {' or '.join(name for name in module.RULE_SETS if name != 'generic') or 'none'}, "
                f"or compare measurements with the shop's own limits"))
    try:
        # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse than one that says it failed.
        json.dumps(report, allow_nan=False)
    except ValueError as error:
        return _failed(label, f"a measurement was not a finite number, so the report is not JSON: {error}",
                       "not_finite")
    ok = not any(finding.severity == "error" for finding in found)
    from cad._internal.validation_door import display_path

    head = f"OK {display_path(label) if label.is_absolute() else label}: {process}"
    line = f"{head} {module.summary(report, resolved, candidates)}" if ok else ""
    return CheckResult(ok=ok, path=label, findings=tuple(found), summary=line, measurements=report)


def measure(document_type: str, source: Any, process: str, resolved: dict[str, Any], candidates: bool) -> CheckResult:
    """Measure ``source`` with its integration, then ``finish`` it."""
    label = _label(source)
    if isinstance(source, (str, os.PathLike)) and label.is_absolute() and not label.is_file():
        return _failed(label, "file not found", "invalid_target")
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


def dfm_for(document_type: str) -> Any:
    """``cad.<document_type>.dfm``: the manufacturing check, for a source of that type."""

    def dfm(
        source: Path,
        *,
        process: str | None = None,
        rules: str | None = None,
        material: str | None = None,
        units: str | None = None,
        axes: int | None = None,
        turning: bool = False,
        tools: str | None = None,
        stock: str | None = None,
        thickness: float | None = None,
        k_factor: float | None = None,
        bend_radius: float | None = None,
        kerf: float | None = None,
        sheet_size: str | None = None,
        pull: str | None = None,
        wall_limit: float | None = None,
        zero_tol: float | None = None,
        cavities: int | None = None,
        technology: str | None = None,
        build_volume: str | None = None,
        angle_limit: float | None = None,
        samples: int | None = None,
        layer_height: float | None = None,
        nozzle: float | None = None,
        candidates: bool = False,
    ) -> CheckResult:
        """Check a part for a manufacturing process: CNC machining, sheet metal, injection molding or 3D printing.

        A STEP, an xbf or a model's document is measured on its exact geometry, each finding at a face ref
        (cad xbf inspect DOC REF resolves it); a mesh (STL, 3MF, GLB) as triangles, at x, y, z; a DXF as a
        sheet's cut file. The
        measurements are facts; the verdicts are a rule set's (--rules, generic by default: a starting
        point, no shop's limits), each finding coded by its rule, with the limit, the source and what to
        change. A rule broken is an error, as is a family that could not be measured; --rules none reports
        facts alone. --json carries every measurement and every rule's outcome.

        source: what to check: a file of the type (a .step, .xbf, .stl, .3mf, .glb, or a .dxf cut file), or a
          model's document id the engine holds (cad model dfm), or the handle its call returns.
        process: cnc, sheet, molding or printing.
        rules: the rule set the verdicts come from: generic (default), a shop's (protolabs, hubs, xometry, sendcutsend: those the process has), or none.
        material: the part's material (aluminum, steel, stainless, abs, pc, nylon, ...): picks the material's limits.
        units: the file's length units (mm, cm, m, in, ft), an STL's alone; default mm.
        axes: cnc: the milling machine's axes, 3, 4 or 5; default 3.
        turning: cnc: the part is turned on a lathe (its axis found), not milled.
        tools: cnc: the end mill diameters available, in mm, comma separated (3,6,10); default the rule set's.
        stock: cnc: the stock's size in mm (100x60x25); default the part's box.
        thickness: sheet: the stock's thickness in mm; default measured.
        k_factor: sheet: the neutral axis's place in the thickness, for the flat pattern; default the rule set's.
        bend_radius: sheet: the shop's inside bend radius in mm, compared with the part's.
        kerf: sheet: the cutting kerf in mm, for small features.
        sheet_size: sheet: the largest sheet in mm (1219x2438); default the rule set's.
        pull: molding: the pull direction, an axis (z, -y) or x,y,z components; default z.
        wall_limit: molding: faces at or above this many degrees from the pull are not walls; default 45.
        zero_tol: molding: draft under this many degrees is zero draft; default 0.05.
        cavities: molding: cavities in the mold, for the clamp force; default 1.
        technology: printing: fdm, sls, sla, mjf or pbf (metal powder bed); default fdm.
        build_volume: printing: the printer's build volume in mm (256x256x256); default the technology's.
        angle_limit: printing: down-facing faces under this many degrees from horizontal need support; default the technology's.
        samples: printing: rays cast for the wall-thickness field on a mesh; default 2000.
        layer_height: printing: the layer height in mm, for stair-stepping; default the technology's.
        nozzle: printing: fdm's nozzle diameter in mm; default 0.4.
        candidates: rank the candidates instead: molding the pulls (x, y, z and the part's principal axes),
          printing the orientations.
        """
        given = {"rules": rules, "material": material, "units": units, "axes": axes, "turning": turning,
                 "tools": tools, "stock": stock, "thickness": thickness, "k_factor": k_factor,
                 "bend_radius": bend_radius, "kerf": kerf, "sheet_size": sheet_size, "pull": pull,
                 "wall_limit": wall_limit, "zero_tol": zero_tol, "cavities": cavities, "technology": technology,
                 "build_volume": build_volume, "angle_limit": angle_limit, "samples": samples,
                 "layer_height": layer_height, "nozzle": nozzle}
        resolved = options(document_type, process, given, candidates=candidates)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        assert process is not None
        try:
            return measure(document_type, source, process, resolved, candidates)
        except ModuleNotFoundError as error:
            from cad._internal.integrations import missing

            said = missing(error)
            if said is None:
                raise
            raise ModuleNotFoundError(said, name=error.name) from None

    if document_type in CUT_TYPES:
        # A cut file's own help: what it checks and what it is; the options stay every type's (one signature).
        doc = dfm.__doc__ or ""
        summary = doc.split("\n\n", 2)
        dfm.__doc__ = "\n\n".join([
            "Check a sheet's cut file (a DXF) for laser, waterjet or router cutting: --process sheet.",
            "        Its units, closed contours on the cut layers, curves cut twice (overlapping, crossing, zero-area),\n"
            "        annotation on a cut layer, curves drawn as short lines, and holes, slots, webs and spacing against the\n"
            "        kerf and the thickness, judged against a cited rule set (--rules); each finding at a layer and an\n"
            "        entity handle. Only the sheet process's options apply.",
            summary[2] if len(summary) > 2 else ""]).replace(
            "        source: what to check: a file of the type (a .step, .xbf, .stl, .3mf, .glb, or a .dxf cut file), or a\n"
            "          model's document id the engine holds (cad model dfm), or the handle its call returns.",
            "        source: the .dxf cut file to check.")
    dfm.__module__ = f"cad.{document_type}"
    dfm.__qualname__ = dfm.__name__ = "dfm"
    return dfm
