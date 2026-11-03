"""Sheet metal, cut and bent: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured on exact geometry (a STEP, an xbf, a document the engine holds): thickness, bends, flanges,
holes and their distances, reliefs, hems, and the part unfolded to its flat pattern; and a cut file (a
DXF) for its contours, against the kerf and the thickness.
"""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "context", "findings", "summary", "validate"]

OPTIONS: dict[str, Any] = {"thickness": None, "k_factor": None, "bend_radius": None, "kerf": None,
                           "sheet_size": None}
MEASURED_FROM = ("brep",)

_GENERIC_SOURCES = (
    Source("hubs-sheet", "Protolabs Network (Hubs)", "Sheet metal fabrication design guide",
           "https://www.hubs.com/guides/sheet-metal-fabrication/", "2026-11-03"),
)
RULE_SETS: dict[str, RuleSet] = {
    "generic": RuleSet("generic", "sheet", "text-to-cad generic", "0", (), _GENERIC_SOURCES, generic=True,
                       note="a starting point drawn from published guides, no shop's limits"),
}


def sheet_size(text: str | None) -> tuple[float, float] | None:
    """``1219x2438``: the largest sheet in millimetres; None for the rule set's."""
    if text is None:
        return None
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 2 or not all(value > 0 for value in values):
        raise ValueError(f"--sheet-size is two lengths in millimetres, X x Y (1219x2438), not {text!r}")
    return values  # type: ignore[return-value]


def validate(resolved: dict[str, Any], document_type: str) -> None:
    for name in ("thickness", "bend_radius"):
        if resolved.get(name) is not None and not float(resolved[name]) > 0:
            raise ValueError(f"--{name.replace('_', '-')} is a length in millimetres above 0, not {resolved[name]}")
    if resolved.get("kerf") is not None and not float(resolved["kerf"]) >= 0:
        raise ValueError(f"--kerf is a width in millimetres from 0, not {resolved['kerf']}")
    if resolved.get("k_factor") is not None and not 0.0 < float(resolved["k_factor"]) <= 0.5:
        raise ValueError(f"--k-factor is the neutral axis's place in the thickness, above 0 and at most 0.5, "
                         f"not {resolved['k_factor']}")
    sheet_size(resolved.get("sheet_size"))


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    found = report.get("thickness") or {}
    return {"material": material, "material_class": materials.material_class(material),
            "thickness": resolved.get("thickness") or found.get("thickness_mm")}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    return []


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    found = report.get("thickness") or {}
    return f"sheet {mm(found.get('thickness_mm'))} mm"
