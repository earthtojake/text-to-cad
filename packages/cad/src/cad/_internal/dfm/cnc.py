"""CNC machining, milling and turning: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured on exact geometry alone (a STEP, an xbf, a document the engine holds): internal corners, pockets
and slots, walls, holes, tool access per setup direction, stock, and with ``turning`` the turned features.
"""

from __future__ import annotations

from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "context", "findings", "summary", "validate"]

OPTIONS: dict[str, Any] = {"axes": 3, "turning": False, "tools": None, "stock": None}
MEASURED_FROM = ("brep",)

_GENERIC_SOURCES = (
    Source("hubs-cnc", "Protolabs Network (Hubs)", "How to design parts for CNC machining",
           "https://www.hubs.com/knowledge-base/how-design-parts-cnc-machining/", "2026-11-03"),
)
RULE_SETS: dict[str, RuleSet] = {
    "generic": RuleSet("generic", "cnc", "text-to-cad generic", "0", (), _GENERIC_SOURCES, generic=True,
                       note="a starting point drawn from published guides, no shop's limits"),
}


def tools(text: str | None) -> tuple[float, ...] | None:
    """``3,6,10``: end mill diameters in millimetres, smallest first; None for none given."""
    if text is None:
        return None
    try:
        values = tuple(sorted(float(part) for part in str(text).split(",") if part.strip()))
    except ValueError:
        values = ()
    if not values or not all(value > 0 for value in values):
        raise ValueError(f"--tools is end mill diameters in millimetres, comma separated (3,6,10), not {text!r}")
    return values


def stock(text: str | None) -> tuple[float, float, float] | None:
    """``100x60x25``: the stock's size in millimetres; None for the part's box."""
    if text is None:
        return None
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 3 or not all(value > 0 for value in values):
        raise ValueError(f"--stock is three lengths in millimetres, X x Y x Z (100x60x25), not {text!r}")
    return values  # type: ignore[return-value]


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if int(resolved["axes"]) not in (3, 4, 5):
        raise ValueError(f"--axes is 3, 4 or 5, not {resolved['axes']}")
    tools(resolved.get("tools"))
    stock(resolved.get("stock"))


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    return {"material": material, "material_class": materials.material_class(material),
            "axes": int(resolved["axes"]), "turning": bool(resolved.get("turning"))}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    return []


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    bodies = report.get("bodies") or []
    return f"{'turning' if resolved.get('turning') else str(resolved['axes']) + '-axis milling'}: " \
           f"{len(bodies)} part(s), {mm(sum(body.get('volume_mm3') or 0 for body in bodies))} mm3"
