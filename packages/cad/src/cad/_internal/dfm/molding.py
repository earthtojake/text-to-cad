"""Injection molding: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured along one pull (``pull``): draft, undercut candidates and the projected area; with ``candidates``
the pulls ranked (x, y, z and the part's principal axes).
"""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, where
from cad._internal.dfm.rules import RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "context", "findings", "summary", "validate"]

OPTIONS: dict[str, Any] = {"pull": "z", "wall_limit": 45.0, "zero_tol": 0.05, "cavities": None}
MEASURED_FROM = ("brep", "mesh")

_GENERIC_SOURCES = (
    Source("hubs-im", "Protolabs Network (Hubs)", "Injection molding design guide",
           "https://www.hubs.com/guides/injection-molding/", "2026-11-03"),
)
RULE_SETS: dict[str, RuleSet] = {
    "generic": RuleSet("generic", "molding", "text-to-cad generic", "0", (), _GENERIC_SOURCES, generic=True,
                       note="a starting point drawn from published guides, no shop's limits"),
}


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if not 0.0 < float(resolved["wall_limit"]) <= 90.0:
        raise ValueError(f"--wall-limit is an angle in degrees above 0 and at most 90, not {resolved['wall_limit']}")
    if not 0.0 <= float(resolved["zero_tol"]) < 90.0:
        raise ValueError(f"--zero-tol is an angle in degrees from 0 below 90, not {resolved['zero_tol']}")
    if resolved.get("cavities") is not None and int(resolved["cavities"]) < 1:
        raise ValueError(f"--cavities is a count of at least 1, not {resolved['cavities']}")


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    return {"material": material, "material_class": materials.material_class(material)}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    mesh = report.get("mesh") or {}
    if mesh.get("note"):
        found.append(CheckFinding("warning", "several_bodies", mesh["note"], "mesh"))
    if candidates:
        return found
    draft = report.get("draft") or {}
    if (draft.get("zero_draft_wall_area_mm2") or 0) > 0:
        faces = draft.get("largest_zero_draft_faces") or [{}]
        found.append(CheckFinding(
            "warning", "zero_draft_walls",
            f"{draft['zero_draft_wall_area_mm2']:g} mm2 of wall has no draft along the pull (under "
            f"{draft['zero_tol_deg']:g} deg), {draft['zero_draft_face_count']} faces; the largest is "
            f"{faces[0].get('area_mm2', 0):g} mm2", faces[0].get("location") or where(faces[0].get("centroid_xyz"))))
    reading = draft.get("min_wall_draft") or {}
    if reading.get("reading_note"):
        found.append(CheckFinding("warning", "coarse_curved_face", reading["reading_note"],
                                  where(reading.get("location_xyz"))))
    undercuts = report.get("undercuts") or {}
    if (undercuts.get("candidate_area_mm2") or 0) > 0:
        faces = undercuts.get("largest_candidate_faces") or [{}]
        found.append(CheckFinding(
            "warning", "undercut_candidates",
            f"{undercuts['candidate_area_mm2']:g} mm2 ({undercuts['candidate_area_pct_of_surface']:g}% of the "
            f"surface) does not withdraw along a straight two-half pull, {undercuts['candidate_face_count']} "
            f"faces; the largest is {faces[0].get('area_mm2', 0):g} mm2",
            faces[0].get("location") or where(faces[0].get("centroid_xyz"))))
    if undercuts.get("probe_resolution_note"):
        found.append(CheckFinding("info", "probe_resolution", undercuts["probe_resolution_note"], "undercuts"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if candidates:
        rows = sorted((row for row in report["pulls"]["candidates"] if "error" not in row),
                      key=lambda row: (row["undercut_candidate_area_mm2"], row["zero_draft_wall_area_mm2"]))
        return "pulls by undercut then zero-draft area: " + "; ".join(
            f"{row['pull']} {mm(row['undercut_candidate_area_mm2'])} mm2 undercut, "
            f"{mm(row['zero_draft_wall_area_mm2'])} mm2 zero-draft, min draft {mm(row['min_wall_draft_deg'])} deg"
            for row in rows)
    draft, undercuts, projection = report["draft"], report["undercuts"], report["projection"]
    least = (draft.get("min_wall_draft") or {}).get("draft_deg")
    return (f"along {','.join(f'{value:g}' for value in draft['pull_axis'])}: walls "
            f"{mm(draft['wall_area_mm2'])} mm2, zero-draft {mm(draft['zero_draft_wall_area_mm2'])} mm2, min "
            f"wall draft {mm(least)} deg, undercut candidates {mm(undercuts['candidate_area_mm2'])} mm2, "
            f"projected {mm(projection['projected_area_mm2'])} mm2, depth {mm(projection['depth_along_pull_mm'])} mm")
