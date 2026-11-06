"""The manufacturing check of a 3D document, measured with trimesh: what ``cad.<type>.dfm(source,
process=...)`` runs once its options are resolved (``cad._internal.manufacturing``).

**The mesh.** An STL is measured as it is; a 3MF or a GLB is read by the library's own readers (its
objects placed by its build, its units -- a 3MF's declared unit, a GLB's glTF metres, Y up -- made
millimetres, Z up, as the viewer reads it) and written as one STL in a temporary folder, with no CAD
kernel; a STEP, an xbf or a document the engine holds is exported to that STL by the engine, which
tessellates it in its own kernel processes. The temporary folder is gone when the check returns: the
check writes nothing beside its source.

**The result** is a ``CheckResult``: ``measurements`` the report the measurement made (``_molding``,
``_printing``: every family, ``partial`` and ``partial_sections``), and findings from it -- an error for
each family that could not be measured, for a mesh that could not be read and for a figure that is no
finite number (the result is then without measurements, which would not be JSON); a warning for what
the figures show (``zero_draft_walls``, ``undercut_candidates``, ``overhangs``, ``units_suspect``,
``not_watertight``, ``several_bodies``, ``coarse_curved_face``); an info for what bounds a figure
(``probe_resolution``). Its location is the place a figure was measured at, ``x, y, z`` in
millimetres, or the family's name. It passes while every family measured: nothing here compares a figure
against a process's limit.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cad.results import CheckFinding, CheckResult

__all__ = ["check"]

_DOCUMENTS = (".step", ".stp", ".xbf")
_MESHES = (".3mf", ".glb")


def _where(xyz: Any) -> str | None:
    return ", ".join(f"{float(value):g}" for value in xyz) if xyz else None


def _target(source: Any) -> tuple[Path | None, Any]:
    """The source's file (None for a document the engine holds) and what the engine reads it as."""
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        path = Path(os.fspath(source)).expanduser().resolve()
        return path, path
    return None, source


def _mesh_file(path: Path | None, source: Any, folder: Path) -> Path:
    """The STL the check measures: the source's own, else one the library writes of it in ``folder``."""
    from cad.engine.api import export

    if path is not None and path.suffix.lower() == ".stl":
        return path
    written = folder / "measured.stl"
    if path is not None and path.suffix.lower() in _MESHES:
        export(path, written, daemon=False, progress=False)  # numpy alone: no kernel, no engine
    else:
        export(source, written, progress=False)  # the engine tessellates it
    return written


def _label(path: Path | None, source: Any) -> Path:
    if path is not None:
        return path
    ident = getattr(source, "id", None)  # a document's handle; a model, by its name
    if ident is None and isinstance(source, (str, os.PathLike)):
        ident = os.fspath(source)
    return Path(str(ident or getattr(source, "name", None) or source))


def check(document_type: str, source: Any, *, process: str, candidates: bool = False, **options: Any) -> CheckResult:
    """Measure ``source`` for ``process`` with ``options`` resolved (see the module)."""
    from cad.trimesh import _molding, _printing

    path, read = _target(source)
    label = _label(path, source)
    if path is not None and not path.is_file():
        return _failed(label, "file not found", "invalid_target")
    pull = _molding._pull_vector(options["pull"]) if process == "molding" and not candidates else None
    with tempfile.TemporaryDirectory(prefix="cad-check-") as folder:
        try:
            stl = _mesh_file(path, read, Path(folder))
            if process == "molding":
                mesh = _molding._load(str(stl), options["units"])
            else:
                mesh = _printing._load(str(stl))
                if options["units"] != "mm":
                    mesh.apply_scale(_molding._UNITS_MM[options["units"]])
        except Exception as error:  # noqa: BLE001 - a mesh that does not read is the check's answer
            return _failed(label, f"failed to load mesh: {error}", "mesh_unreadable")
        if process == "molding":
            if candidates:
                report = _molding.pulls(mesh, options["wall_limit"], options["zero_tol"])
            else:
                report = _molding.measure(mesh, pull, options["wall_limit"], options["zero_tol"])
        else:  # the part as it stands, and with candidates the orientations ranked beside it
            report = _printing.measure(mesh, options["samples"], options["angle_limit"], orientations=candidates)
    report = {"process": process, **report}
    try:
        # allow_nan=False: a NaN is not JSON, and a report a parser rejects is worse than one that says it failed.
        json.dumps(report, allow_nan=False)
    except ValueError as error:
        return _failed(label, f"a measurement was not a finite number, so the report is not JSON: {error}",
                       "not_finite")
    findings = _findings(report, process, candidates)
    ok = not any(finding.severity == "error" for finding in findings)
    return CheckResult(ok=ok, path=label, findings=findings, summary=_summary(label, report, process, candidates) if ok
                       else "", measurements=report)


def _failed(path: Path, message: str, code: str) -> CheckResult:
    return CheckResult(ok=False, path=path, findings=(CheckFinding("error", code, message),))


def _first_error(value: Any) -> str | None:
    if isinstance(value, dict):
        if "error" in value:
            return str(value["error"])
        return next((found for item in value.values() if (found := _first_error(item))), None)
    if isinstance(value, list):
        return next((found for item in value if (found := _first_error(item))), None)
    return None


def _findings(report: dict[str, Any], process: str, candidates: bool) -> tuple[CheckFinding, ...]:
    found: list[CheckFinding] = []
    for family in report.get("partial_sections") or []:
        found.append(CheckFinding("error", "measurement_failed", f"{family} was not measured: "
                                  f"{_first_error(report[family])}", family))
    scale = report.get("scale") or {}
    if scale.get("units_suspect"):
        found.append(CheckFinding("warning", "units_suspect", scale["note"], "scale"))
    mesh = report.get("mesh") or {}
    if process == "printing" and mesh and "error" not in mesh:
        if not mesh.get("watertight"):
            found.append(CheckFinding("warning", "not_watertight", "the mesh is not watertight: its volume, wall "
                                      "thickness and support volume are measured of an open surface", "mesh"))
        if (mesh.get("body_count") or 0) > 1:
            found.append(CheckFinding("info", "several_bodies", f"{mesh['body_count']} separate bodies: walls are "
                                      "measured per body", "mesh"))
    if process == "molding" and mesh.get("note"):
        found.append(CheckFinding("warning", "several_bodies", mesh["note"], "mesh"))
    if candidates and process == "molding":  # the pulls ranked: no one pull's draft or undercuts to say
        return tuple(found)
    if process == "molding":
        draft = report.get("draft") or {}
        if (draft.get("zero_draft_wall_area_mm2") or 0) > 0:
            faces = draft.get("largest_zero_draft_faces") or [{}]
            found.append(CheckFinding(
                "warning", "zero_draft_walls",
                f"{draft['zero_draft_wall_area_mm2']:g} mm2 of wall has no draft along the pull (under "
                f"{draft['zero_tol_deg']:g} deg), {draft['zero_draft_face_count']} triangles; the largest face is "
                f"{faces[0].get('area_mm2', 0):g} mm2", _where(faces[0].get("centroid_xyz"))))
        reading = (draft.get("min_wall_draft") or {})
        if reading.get("reading_note"):
            found.append(CheckFinding("warning", "coarse_curved_face", reading["reading_note"],
                                      _where(reading.get("location_xyz"))))
        undercuts = report.get("undercuts") or {}
        if (undercuts.get("candidate_area_mm2") or 0) > 0:
            faces = undercuts.get("largest_candidate_faces") or [{}]
            found.append(CheckFinding(
                "warning", "undercut_candidates",
                f"{undercuts['candidate_area_mm2']:g} mm2 ({undercuts['candidate_area_pct_of_surface']:g}% of the "
                f"surface) does not withdraw along a straight two-half pull, {undercuts['candidate_face_count']} "
                f"triangles; the largest face is {faces[0].get('area_mm2', 0):g} mm2", _where(faces[0].get("centroid_xyz"))))
        if undercuts.get("probe_resolution_note"):
            found.append(CheckFinding("info", "probe_resolution", undercuts["probe_resolution_note"], "undercuts"))
    else:
        overhangs = report.get("overhangs") or {}
        if (overhangs.get("down_facing_area_below_limit_mm2") or 0) > 0:
            faces = overhangs.get("largest_faces_below_limit") or [{}]
            found.append(CheckFinding(
                "warning", "overhangs",
                f"{overhangs['down_facing_area_below_limit_mm2']:g} mm2 ({overhangs['down_facing_area_below_limit_pct']:g}%"
                f" of the surface) faces down at under {overhangs['angle_limit_used_deg']:g} deg from horizontal, off "
                f"the plate, {overhangs['face_count_below_limit']} triangles", _where(faces[0].get("location_xyz"))))
        walls = report.get("wall_thickness") or {}
        if walls.get("note"):
            found.append(CheckFinding("info", "walls_not_measured", walls["note"], "wall_thickness"))
    return tuple(found)


def _mm(value: Any) -> str:
    return "-" if value is None else f"{value:g}"


def _summary(path: Path, report: dict[str, Any], process: str, candidates: bool) -> str:
    from cad._internal.validation_door import display_path

    head = f"OK {display_path(path) if path.is_absolute() else path}: {process}"
    if process == "molding" and candidates:
        rows = sorted((row for row in report["pulls"]["candidates"] if "error" not in row),
                      key=lambda row: (row["undercut_candidate_area_mm2"], row["zero_draft_wall_area_mm2"]))
        return head + ", pulls by undercut then zero-draft area: " + "; ".join(
            f"{row['pull']} {_mm(row['undercut_candidate_area_mm2'])} mm2 undercut, "
            f"{_mm(row['zero_draft_wall_area_mm2'])} mm2 zero-draft, min draft {_mm(row['min_wall_draft_deg'])} deg"
            for row in rows)
    if process == "molding":
        draft, undercuts, projection = report["draft"], report["undercuts"], report["projection"]
        least = (draft.get("min_wall_draft") or {}).get("draft_deg")
        return (f"{head} along {','.join(f'{value:g}' for value in draft['pull_axis'])}: walls "
                f"{_mm(draft['wall_area_mm2'])} mm2, zero-draft {_mm(draft['zero_draft_wall_area_mm2'])} mm2, min "
                f"wall draft {_mm(least)} deg, undercut candidates {_mm(undercuts['candidate_area_mm2'])} mm2, "
                f"projected {_mm(projection['projected_area_mm2'])} mm2, depth {_mm(projection['depth_along_pull_mm'])} mm")
    mesh, overhangs, walls, support = (report["mesh"], report["overhangs"], report["wall_thickness"],
                                       report["support_volume"])
    said = (f"{head}: {_mm(mesh['volume_mm3'])} mm3, {mesh['body_count']} body(ies); overhangs under "
            f"{overhangs['angle_limit_used_deg']:g} deg {_mm(overhangs['down_facing_area_below_limit_mm2'])} mm2; walls "
            f"min {_mm(walls.get('min_mm'))}, p05 {_mm(walls.get('p05_mm'))}, median {_mm(walls.get('median_mm'))} mm; "
            f"support ~{_mm(support['estimated_support_volume_mm3'])} mm3")
    if candidates:
        rows = sorted(report["orientations"]["candidates"], key=lambda row: row["support_area_mm2"])
        said += "; orientations by support area: " + "; ".join(
            f"{row['orientation']} {_mm(row['support_area_mm2'])} mm2, {_mm(row['build_height_mm'])} mm tall"
            for row in rows)
    return said
