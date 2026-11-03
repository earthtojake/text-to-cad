"""3D printing: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured as the part stands on the plate (its lowest point, Z up): the mesh, overhangs, walls and support;
with ``candidates`` the orientations ranked.
"""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, where
from cad._internal.dfm.rules import RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "TECHNOLOGIES", "context", "findings", "summary", "validate"]

#: The printing technologies: fused filament, selective laser sintering, stereolithography and DLP,
#: multi jet fusion, metal powder bed fusion (DMLS, SLM).
TECHNOLOGIES = ("fdm", "sls", "sla", "mjf", "pbf")
OPTIONS: dict[str, Any] = {"technology": "fdm", "build_volume": None, "angle_limit": None, "samples": 2000,
                           "layer_height": None, "nozzle": None}
MEASURED_FROM = ("brep", "mesh")
#: The overhang angle (from horizontal) each technology counts as needing support when none is given.
DEFAULT_ANGLE = {"fdm": 45.0, "sla": 45.0, "sls": 0.0, "mjf": 0.0, "pbf": 45.0}

_GENERIC_SOURCES = (
    Source("hubs-3dp", "Protolabs Network (Hubs)", "Key design considerations for 3D printing",
           "https://www.hubs.com/knowledge-base/key-design-considerations-3d-printing/", "2026-11-03"),
)
RULE_SETS: dict[str, RuleSet] = {
    "generic": RuleSet("generic", "printing", "text-to-cad generic", "0", (), _GENERIC_SOURCES, generic=True,
                       note="a starting point drawn from published guides, no printer's limits"),
}


def angle_limit(resolved: dict[str, Any]) -> float:
    """The overhang angle the check counts support for: the one given, else the technology's."""
    given = resolved.get("angle_limit")
    return float(given) if given is not None else DEFAULT_ANGLE[resolved["technology"]]


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if resolved["technology"] not in TECHNOLOGIES:
        raise ValueError(f"--technology is one of {', '.join(TECHNOLOGIES)}, not {resolved['technology']!r}")
    given = resolved.get("angle_limit")
    if given is not None and not 0.0 <= float(given) <= 90.0:
        raise ValueError(f"--angle-limit is an angle in degrees from 0 to 90, not {given}")
    if int(resolved["samples"]) < 1:
        raise ValueError(f"--samples is a count of at least 1, not {resolved['samples']}")
    for name in ("layer_height", "nozzle"):
        if resolved.get(name) is not None and not float(resolved[name]) > 0:
            raise ValueError(f"--{name.replace('_', '-')} is a length in millimetres above 0, not {resolved[name]}")
    if resolved.get("build_volume") is not None:
        build_volume(resolved["build_volume"])


def build_volume(text: str) -> tuple[float, float, float]:
    """``256x256x256`` (or ``256,256,256``) as three lengths in millimetres."""
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 3 or not all(value > 0 for value in values):
        raise ValueError(f"--build-volume is three lengths in millimetres, X x Y x Z (256x256x256), not {text!r}")
    return values  # type: ignore[return-value]


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    return {"technology": resolved["technology"], "material": material,
            "material_class": materials.material_class(material)}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    mesh = report.get("mesh") or {}
    if mesh and "error" not in mesh:
        if mesh.get("watertight") is False:
            found.append(CheckFinding("warning", "not_watertight", "the mesh is not watertight: its volume, wall "
                                      "thickness and support volume are measured of an open surface", "mesh"))
        if (mesh.get("body_count") or 0) > 1:
            found.append(CheckFinding("info", "several_bodies", f"{mesh['body_count']} separate bodies: walls are "
                                      "measured per body", "mesh"))
    if candidates:
        return found
    overhangs = report.get("overhangs") or {}
    if (overhangs.get("down_facing_area_below_limit_mm2") or 0) > 0:
        faces = overhangs.get("largest_faces_below_limit") or [{}]
        found.append(CheckFinding(
            "warning", "overhangs",
            f"{overhangs['down_facing_area_below_limit_mm2']:g} mm2 ({overhangs['down_facing_area_below_limit_pct']:g}%"
            f" of the surface) faces down at under {overhangs['angle_limit_used_deg']:g} deg from horizontal, off "
            f"the plate, {overhangs['face_count_below_limit']} faces",
            faces[0].get("location") or where(faces[0].get("location_xyz"))))
    walls = report.get("wall_thickness") or {}
    if walls.get("note"):
        found.append(CheckFinding("info", "walls_not_measured", walls["note"], "wall_thickness"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if candidates:
        rows = sorted(report["orientations"]["candidates"], key=lambda row: row["support_area_mm2"])
        return "orientations by support area: " + "; ".join(
            f"{row['orientation']} {mm(row['support_area_mm2'])} mm2, {mm(row['build_height_mm'])} mm tall"
            for row in rows)
    mesh, overhangs, walls, support = (report["mesh"], report["overhangs"], report["wall_thickness"],
                                       report["support_volume"])
    return (f"{resolved['technology']}: {mm(mesh['volume_mm3'])} mm3, {mesh['body_count']} body(ies); overhangs "
            f"under {overhangs['angle_limit_used_deg']:g} deg {mm(overhangs['down_facing_area_below_limit_mm2'])} mm2; "
            f"walls min {mm(walls.get('min_mm'))}, p05 {mm(walls.get('p05_mm'))}, median {mm(walls.get('median_mm'))} "
            f"mm; support ~{mm(support['estimated_support_volume_mm3'])} mm3")
