"""Sheet metal, cut and bent: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured on exact geometry (a STEP, an xbf, a document the engine holds; ``cad.build123d._dfm_sheet``):
the sheet's thickness and where the part is not sheet, its bends, flanges, holes and their distances (to
an edge, to each other, to a bend in each convention), reliefs, hems and curls, notches and tabs, and the
part unfolded to its flat pattern; and a cut file (a DXF; ``cad.build123d._dfm_dxf``) for its contours,
against the kerf and the thickness.

**Conventions.** A bend's ``angle_deg`` is the angle it is bent through (0 flat, 90 a right angle, 180 a
hem); ``included_angle_deg`` is 180 less it. A hole's distance to a bend is given four ways, each its own
field, and every rule names the one its source uses: ``distance_tangent_mm`` to the bend's tangent line
(where the bend's radius starts), ``distance_centerline_mm`` to the bend's centre line in the flat pattern
(half the bend allowance past the tangent line: where a press brake's die centres), ``distance_inside_mm``
and ``distance_outside_mm`` to the other flange's inside and outside faces (the inside and outside mold
lines, the tangent distance plus ``r * tan(angle / 2)`` and ``(r + t) * tan(angle / 2)``). A flange's
length is given the same three ways from the bend, the least along the bend (``length_*_mm``) and the
length at least half of the bend reaches (``length_*_half_mm``).
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "context", "findings", "k_factor", "scs_row", "sheet_size",
           "summary", "validate"]

OPTIONS: dict[str, Any] = {"thickness": None, "k_factor": None, "bend_radius": None, "kerf": None,
                           "sheet_size": None}
MEASURED_FROM = ("brep",)
ACCESSED = "2026-11-03"
IN = 25.4

# --- sources ---------------------------------------------------------------------------------------------

HUBS = Source("hubs-sheet", "Protolabs Network (Hubs)", "Sheet metal fabrication design guide",
              "https://www.hubs.com/guides/sheet-metal-fabrication/", ACCESSED)
PROTOLABS = Source("protolabs-sheet", "Protolabs", "Sheet metal fabrication design guidelines",
                   "https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/", ACCESSED)
PROTOLABS_TOOLKIT = Source("protolabs-toolkit", "Protolabs", "Design for sheet metal fabrication toolkit",
                           "https://www.protolabs.com/resources/design-for-sheet-metal-fabrication-toolkit/", ACCESSED)
XOMETRY = Source("xometry-sheet", "Xometry", "Sheet metal fabrication service (design guidelines)",
                 "https://www.xometry.com/capabilities/sheet-metal-fabrication/", ACCESSED)
SCS_CUTTING = Source("scs-cutting", "SendCutSend", "Sheet cutting guidelines",
                     "https://sendcutsend.com/guidelines/sheet-cutting/", ACCESSED)
SCS_BENDING = Source("scs-bending", "SendCutSend", "CNC bending service and guidelines",
                     "https://sendcutsend.com/services/cnc-bending/", ACCESSED)
SCS_DEFORMATION = Source("scs-deformation", "SendCutSend", "Bending deformation guidelines",
                         "https://sendcutsend.com/guidelines/bend-deformation/", ACCESSED)
SCS_CALCULATOR = Source("scs-calculator", "SendCutSend", "Bending calculator (per material and thickness)",
                        "https://sendcutsend.com/bending-calculator/", ACCESSED)
SCS_5052 = Source("scs-5052", "SendCutSend", "5052 aluminum material page",
                  "https://sendcutsend.com/materials/5052-aluminum/", ACCESSED)
SCS_MINMAX = Source("scs-minmax", "SendCutSend", "Min/max part sizes",
                    "https://sendcutsend.com/materials/min-max/", ACCESSED)

# --- tables the rules read through ``context`` ------------------------------------------------------------

#: Hubs's generic K-factor chart, air bending: (inside radius up to 1 t, 1 to 3 t, over 3 t) per hardness.
HUBS_K_AIR = {"soft": (0.33, 0.40, 0.50), "medium": (0.38, 0.43, 0.50), "hard": (0.40, 0.45, 0.50)}
_HARDNESS = {"aluminum": "soft", "copper": "soft", "brass": "soft", "steel": "medium", "galvanized": "medium",
             "stainless": "hard", "titanium": "hard"}

#: Protolabs toolkit: minimum flange length (and feature-to-bend distance) = multiplier * t + inside radius,
#: by material group and thickness band (inches: .024-.050, .060-.090, .100-.134, .160+).
PROTOLABS_FLANGE = {"al": (3.0, 2.5, 2.5, 3.0), "crs": (3.5, 2.75, 2.5, 3.5), "ss": (3.5, 2.75, 2.5, 4.0)}
_PROTOLABS_GROUP = {"aluminum": "al", "copper": "al", "steel": "crs", "galvanized": "crs", "stainless": "ss"}

#: SendCutSend's bending calculator, per material and thickness (inches): K factor, effective inside bend
#: radius at 90 degrees, die width, minimum formed flange at 90 degrees (measured from the bend's apex).
SCS_BEND_TABLE: dict[str, dict[float, tuple[float, float, float, float]]] = {
    "aluminum": {0.040: (0.45, 0.024, 0.472, 0.286), 0.063: (0.42, 0.035, 0.472, 0.303),
                 0.080: (0.48, 0.038, 0.472, 0.313), 0.090: (0.37, 0.032, 0.472, 0.326),
                 0.100: (0.40, 0.125, 0.630, 0.463), 0.125: (0.44, 0.125, 0.630, 0.476),
                 0.187: (0.43, 0.250, 0.984, 0.798), 0.250: (0.42, 0.250, 1.575, 1.371)},
    "steel": {0.030: (0.38, 0.045, 0.472, 0.286), 0.048: (0.38, 0.045, 0.472, 0.298),
              0.059: (0.40, 0.063, 0.472, 0.309), 0.074: (0.40, 0.063, 0.472, 0.320),
              0.104: (0.34, 0.063, 0.630, 0.459), 0.119: (0.38, 0.063, 0.630, 0.466),
              0.135: (0.32, 0.100, 0.984, 0.742), 0.187: (0.36, 0.125, 0.984, 0.781),
              0.250: (0.36, 0.150, 1.575, 1.361)},
    "stainless": {0.030: (0.36, 0.080, 0.472, 0.294), 0.048: (0.36, 0.080, 0.472, 0.307),
                  0.060: (0.34, 0.070, 0.472, 0.314), 0.074: (0.36, 0.075, 0.472, 0.324),
                  0.100: (0.36, 0.187, 0.984, 0.732), 0.125: (0.38, 0.150, 0.984, 0.740),
                  0.187: (0.35, 0.130, 0.984, 0.784), 0.250: (0.34, 0.225, 1.575, 1.381)},
    "brass": {0.040: (0.38, 0.040, 0.472, 0.292), 0.063: (0.38, 0.040, 0.472, 0.308),
              0.125: (0.36, 0.060, 0.630, 0.471), 0.187: (0.38, 0.095, 0.984, 0.782),
              0.250: (0.38, 0.130, 1.575, 1.362)},
    "copper": {0.040: (0.34, 0.052, 0.472, 0.296), 0.063: (0.36, 0.024, 0.472, 0.305),
               0.125: (0.34, 0.050, 0.630, 0.471), 0.187: (0.36, 0.118, 0.984, 0.780),
               0.250: (0.33, 0.140, 1.575, 1.365)},
    "galvanized": {0.030: (0.38, 0.045, 0.472, 0.286), 0.048: (0.38, 0.045, 0.472, 0.298),
                   0.059: (0.36, 0.063, 0.472, 0.311), 0.074: (0.40, 0.063, 0.472, 0.320)},
    "titanium": {0.040: (0.38, 0.045, 0.472, 0.295)},
}
#: A measured thickness within this many inches of a table's thickness is that gauge.
SCS_GAUGE_TOLERANCE_IN = 0.003

#: Each set's largest sheet (long x short, mm) where no --sheet-size is given, and where it comes from.
SHEETS: dict[str, tuple[tuple[float, float], str]] = {
    "generic": ((3050.0, 1520.0), "Xometry's largest blank, 5 x 10 ft"),
    "hubs": ((3050.0, 1520.0), "no sheet size published by Hubs; Xometry's largest blank, 5 x 10 ft"),
    "protolabs": ((1193.8, 990.6), "Protolabs' largest part, 39 x 47 in"),
    "sendcutsend": ((1727.2, 1117.6), "SendCutSend's largest laser-cut part, 44 x 68 in (5052, mild steel)"),
}
SCS_BENDING_SHEET = (1117.6, 762.0)  # the largest flat blank SendCutSend bends: 30 x 44 in


def sheet_size(text: str | None) -> tuple[float, float] | None:
    """``1219x2438``: the largest sheet in millimetres, long side first; None for the rule set's."""
    if text is None:
        return None
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 2 or not all(value > 0 and math.isfinite(value) for value in values):
        raise ValueError(f"--sheet-size is two lengths in millimetres, X x Y (1219x2438), not {text!r}")
    return (max(values), min(values))


def scs_row(material: str | None, thickness: float | None) -> tuple[float, tuple[float, float, float, float]] | None:
    """SendCutSend's calculator row for a material and a thickness (mm): (gauge in inches, (K, radius in,
    die in, flange in)), or None where it lists none."""
    table = SCS_BEND_TABLE.get(material or "")
    if not table or thickness is None:
        return None
    inches = thickness / IN
    gauge = min(table, key=lambda value: abs(value - inches))
    if abs(gauge - inches) > SCS_GAUGE_TOLERANCE_IN:
        return None
    return gauge, table[gauge]


def k_factor(material: str | None, rules: str | None, inside_radius: float, thickness: float) -> tuple[float, str]:
    """The K-factor a bend is unfolded with when none is given, and where it comes from: SendCutSend's
    calculator for its own gauges (``--rules sendcutsend``), else Hubs's generic air-bending chart by the
    material's hardness and the bend's radius over thickness (medium, steel's, for a material not given)."""
    resolved = materials.resolve(material) if material else None
    if rules == "sendcutsend":
        row = scs_row(resolved, thickness)
        if row is not None:
            return row[1][0], f"SendCutSend's calculator, {resolved} {row[0]:.3f} in"
    hardness = _HARDNESS.get(resolved or "", "medium")
    ratio = inside_radius / thickness if thickness > 0 else 0.0
    column = 0 if ratio <= 1.0 + 1e-6 else 1 if ratio <= 3.0 + 1e-6 else 2  # a band's edge is in the band
    band = ("inside radius up to 1 t", "inside radius 1 to 3 t", "inside radius over 3 t")[column]
    said = f"{resolved}'s" if resolved in _HARDNESS else "no material given: medium (steel)"
    return HUBS_K_AIR[hardness][column], f"Hubs's K-factor chart, air bending, {hardness} ({said}), {band}"


def _protolabs_band(thickness: float) -> int:
    inches = thickness / IN
    return 0 if inches < 0.055 else 1 if inches < 0.095 else 2 if inches < 0.147 else 3


# --- rule sets -------------------------------------------------------------------------------------------

def _r(ident: str, family: str, field: str, op: str, limit: Any, unit: str, what: str, source: Source, **more: Any
       ) -> Rule:
    return Rule(f"sheet.{ident}", family, field, op, limit, unit, what, source.id, **more)


_SCALED = {"when": {"scale_known": True}}


def _uniform(source: Source, note: str) -> Rule:
    return _r("uniform_thickness", "not_sheet", "deviation_mm", "max", 0.0, "mm",
              "departure from the sheet's one thickness", source,
              fix="make the part one thickness throughout: no bosses, pockets or rounds off the sheet", note=note)


def _holes(source: Source, *, diameter: float | None, diameter_severity: str = "error", edge: float | None = None,
           spacing: float | None = None, note: str = "") -> tuple[Rule, ...]:
    rules = []
    if diameter is not None:
        rules.append(_r("hole_diameter", "holes", "size_mm", "min", diameter, "mm", "hole or slot size", source,
                        scale_by="thickness", severity=diameter_severity, note=note,
                        fix="open it to at least {limit:.3g} mm (the thickness times the source's ratio), "
                            "or drill it after cutting", **_SCALED))
    if edge is not None:
        rules.append(_r("hole_to_edge", "holes", "edge_distance_mm", "min", edge, "mm", "hole-to-edge distance",
                        source, scale_by="thickness", fix="move the hole in to at least {limit:.3g} mm from the edge",
                        **_SCALED))
    if spacing is not None:
        rules.append(_r("hole_spacing", "hole_spacing", "distance_mm", "min", spacing, "mm",
                        "hole-to-hole distance (edge to edge)", source, scale_by="thickness",
                        fix="space the holes at least {limit:.3g} mm apart, edge to edge", **_SCALED))
    return tuple(rules)


def _notches_tabs(source: Source) -> tuple[Rule, ...]:
    return (
        _r("notch_width", "notches", "width_mm", "min", 1.0, "mm", "notch width", source,
           scale_by="notch_min_mm", fix="widen the notch to at least {limit:.3g} mm (the greater of the "
                                        "thickness and 1.016 mm)", **_SCALED),
        _r("notch_length", "notches", "length_to_width", "max", 5.0, "ratio", "notch length over its width",
           source, fix="shorten the notch or widen it: its length at most five times its width"),
        _r("tab_width", "tabs", "width_mm", "min", 1.0, "mm", "tab width", source, scale_by="tab_min_mm",
           fix="widen the tab to at least {limit:.3g} mm (the greater of twice the thickness and 3.2 mm)",
           **_SCALED),
        _r("tab_length", "tabs", "length_to_width", "max", 5.0, "ratio", "tab length over its width", source,
           fix="shorten the tab or widen it: its length at most five times its width"),
    )


def _hems(source: Source) -> tuple[Rule, ...]:
    return (
        _r("hem_diameter", "hems", "inside_diameter_mm", "min", 1.0, "mm", "hem inside diameter", source,
           scale_by="thickness", fix="open the hem to an inside diameter of at least {limit:.3g} mm", **_SCALED),
        _r("hem_return", "hems", "return_length_mm", "min", 6.0, "mm", "hem return length", source,
           scale_by="thickness", severity="warning", fix="lengthen the hem's return to at least {limit:.3g} mm",
           **_SCALED),
    )


def _flat_size(source: Source, note: str) -> tuple[Rule, ...]:
    return (
        _r("flat_length", "parts", "flat_length_mm", "max", 1.0, "mm", "flat pattern's long side", source,
           scale_by="sheet_long_mm", note=note, fix="split the part or nest it on a larger sheet: the flat "
                                                    "pattern is longer than the {limit:.4g} mm sheet", **_SCALED),
        _r("flat_width", "parts", "flat_width_mm", "max", 1.0, "mm", "flat pattern's short side", source,
           scale_by="sheet_short_mm", note=note, fix="split the part: the flat pattern is wider than the "
                                                     "{limit:.4g} mm sheet", **_SCALED),
    )


def _hubs_rules(source: Source) -> tuple[Rule, ...]:
    return (
        _r("thickness_max", "parts", "thickness_mm", "max", 6.0, "mm", "sheet thickness", source,
           when={"bent": True}, fix="bend sheet no thicker than {limit:g} mm", note="bending: 0.5 to 6 mm"),
        _r("thickness_max", "parts", "thickness_mm", "max", 10.0, "mm", "sheet thickness", source,
           when={"bent": False}, fix="laser cut sheet no thicker than {limit:g} mm", note="laser: 0.5 to 10 mm"),
        _r("thickness_min", "parts", "thickness_mm", "min", 0.5, "mm", "sheet thickness", source,
           fix="use sheet at least {limit:g} mm thick"),
        _r("bend_radius", "bends", "inside_radius_mm", "min", 1.0, "mm", "inside bend radius", source,
           scale_by="thickness", severity="warning", fix="open the inside radius to at least the thickness, "
                                                         "{limit:.3g} mm", **_SCALED),
        _r("flange_length", "flanges", "length_outside_minus_radius_mm", "min", 2.0, "mm",
           "flange height less the inside radius (from the outside of the bend)", source, scale_by="thickness",
           fix="lengthen the flange: its height from the outside of the bend at least twice the thickness plus "
               "the inside radius ({limit:.3g} mm plus the radius)",
           note="minimum bend height 2 t + r; the page does not say where the height is measured, read here "
                "from the outside mold line", **_SCALED),
        _r("bend_relief_width", "reliefs", "width_mm", "min", 1.0, "mm", "bend relief width", source,
           scale_by="thickness", item_when={"kind": "bend"}, fix="cut a relief at the bend's end at least {limit:.3g} mm wide, past the "
                                     "bend's tangent line", **_SCALED),
        _r("hole_to_bend", "hole_to_bend", "distance_tangent_mm", "min", 2.0, "mm",
           "hole-to-bend distance from the bend's tangent line", source, scale_by="thickness",
           fix="move the hole at least {limit:.3g} mm from where the bend's radius starts",
           note="measured from the start of the bend radius (the tangent line)", **_SCALED),
        *_holes(source, diameter=1.0, diameter_severity="warning", edge=1.0, spacing=2.0,
                note="smaller holes are possible, with more risk of distortion"),
        _r("web_width", "webs", "width_mm", "min", 1.0, "mm", "material between cuts", source,
           scale_by="thickness", severity="warning",
           fix="leave at least {limit:.3g} mm of material between the cuts",
           note="Hubs's hole-to-edge minimum, applied to any web of material between two cut edges", **_SCALED),
    )


_GENERIC = RuleSet(
    "generic", "sheet", "text-to-cad generic", "2026-11-03",
    (_uniform(PROTOLABS, "Protolabs: material thickness uniform throughout"), *_hubs_rules(HUBS),
     *_notches_tabs(PROTOLABS), *_hems(PROTOLABS),
     *_flat_size(XOMETRY, "Xometry's largest blank, 5 x 10 ft, unless --sheet-size names the sheet")),
    (HUBS, PROTOLABS, XOMETRY), generic=True,
    note="a starting point: Hubs's bending and laser rules, Protolabs' notch, tab, hem and uniform-thickness "
         "rules and Xometry's largest blank, no one shop's limits")

_HUBS = RuleSet(
    "hubs", "sheet", "Protolabs Network (Hubs)", "2026-11-03",
    (_uniform(HUBS, "sheet stock is one thickness"), *_hubs_rules(HUBS),
     *_flat_size(XOMETRY, "no sheet size published by Hubs: Xometry's largest blank, unless --sheet-size names "
                          "the sheet")),
    (HUBS, XOMETRY), note="Hubs's sheet metal guide")

_PROTOLABS = RuleSet(
    "protolabs", "sheet", "Protolabs", "2026-11-03",
    (
        _uniform(PROTOLABS, "material thickness uniform throughout"),
        _r("thickness_max", "parts", "thickness_mm", "max", 6.35, "mm", "sheet thickness", PROTOLABS,
           fix="use sheet no thicker than 0.250 in ({limit:g} mm)"),
        _r("thickness_min", "parts", "thickness_mm", "min", 0.609, "mm", "sheet thickness", PROTOLABS,
           fix="use sheet at least 0.024 in ({limit:g} mm) thick"),
        _r("bend_radius", "bends", "inside_radius_mm", "min", 0.254, "mm", "inside bend radius", PROTOLABS_TOOLKIT,
           fix="use a tooled inside radius, 0.01 to 1 in", note="tooling radii 0.01 to 1 in (0.254 to 25.4 mm); "
                                                               "standard 0.030, 0.060, 0.090, 0.120 in"),
        _r("bend_radius_max", "bends", "inside_radius_mm", "max", 25.4, "mm", "inside bend radius",
           PROTOLABS_TOOLKIT, severity="warning", fix="a radius over 1 in is bump formed: quote it as such"),
        _r("flange_length", "flanges", "length_outside_minus_radius_mm", "min", 1.0, "mm",
           "flange length less the inside radius (from the outside of the bend)", PROTOLABS_TOOLKIT,
           scale_by="protolabs_flange_t", when={"protolabs_toolkit": True, "scale_known": True},
           fix="lengthen the flange to the toolkit's multiplier times the thickness ({limit:.3g} mm) plus the "
               "inside radius", note="multiplier x t + r by material and thickness; the toolkit does not say "
                                     "where the length is measured, read here from the outside mold line"),
        _r("flange_length", "flanges", "length_outside_mm", "min", 4.0, "mm", "flange length (from the "
           "outside of the bend)", PROTOLABS, scale_by="thickness",
           when={"protolabs_toolkit": False, "scale_known": True},
           fix="lengthen the flange to at least four times the thickness, {limit:.3g} mm",
           note="the guidelines page's 4 t, for a material the toolkit's table does not list"),
        _r("hole_to_bend", "hole_to_bend", "distance_outside_minus_radius_mm", "min", 1.0, "mm",
           "feature-to-bend distance less the inside radius (from the outside of the bend)", PROTOLABS_TOOLKIT,
           scale_by="protolabs_flange_t", when={"protolabs_toolkit": True, "scale_known": True},
           fix="move the feature to the toolkit's multiplier times the thickness ({limit:.3g} mm) plus the "
               "inside radius from the bend", note="the flange table's multipliers; reference unstated, read "
                                                   "here from the outside mold line"),
        _r("hole_to_bend", "hole_to_bend", "distance_tangent_mm", "min", 4.0, "mm",
           "feature-to-bend distance from the bend's tangent line", PROTOLABS, scale_by="thickness",
           severity="warning", when={"protolabs_toolkit": False, "scale_known": True},
           fix="move the feature at least four thicknesses, {limit:.3g} mm, from the bend",
           note="features within about 4 t of a bend risk deformation; reference unstated, read here from the "
                "tangent line"),
        *_holes(PROTOLABS, diameter=1.0),
        _r("hole_to_edge", "holes", "edge_distance_mm", "min", {"thin": 1.574, "thick": 3.175}, "mm",
           "hole-to-edge distance", PROTOLABS, by="protolabs_edge_band",
           fix="move the hole in to at least {limit:.4g} mm from the edge (0.062 in to 0.036 in sheet, "
               "0.125 in above)"),
        *_notches_tabs(PROTOLABS), *_hems(PROTOLABS),
        _r("countersink_diameter", "holes", "countersink_diameter_mm", "min", 2.286, "mm",
           "countersink major diameter", PROTOLABS, item_when={"countersunk": True}),
        _r("countersink_diameter", "holes", "countersink_diameter_mm", "max", 12.7, "mm",
           "countersink major diameter", PROTOLABS, item_when={"countersunk": True}),
        *_flat_size(PROTOLABS, "Protolabs' largest part, 39 x 47 in, unless --sheet-size names the sheet"),
        _r("flat_min", "parts", "flat_width_mm", "min", 6.35, "mm", "flat pattern's short side", PROTOLABS,
           when={"bent": False}, fix="make the part at least 0.25 x 0.25 in"),
        _r("formed_min", "parts", "box_short_mm", "min", 12.7, "mm", "formed part's smaller side", PROTOLABS,
           when={"bent": True}, fix="make the formed part at least 0.5 x 0.5 in"),
        _r("bend_length", "bends", "length_mm", "max", 1193.8, "mm", "bend length", PROTOLABS,
           fix="bends are at most 47 in long"),
    ),
    (PROTOLABS, PROTOLABS_TOOLKIT),
    note="Protolabs' guidelines page and its sheet metal toolkit")

_SCS = RuleSet(
    "sendcutsend", "sheet", "SendCutSend", "2026-11-03",
    (
        _uniform(SCS_CUTTING, "cut from stock sheet of one thickness"),
        _r("hole_diameter", "holes", "size_mm", "min", 0.5, "mm", "hole or cutout size (laser)", SCS_CUTTING,
           scale_by="thickness", when={"scs_5052": False, "scale_known": True},
           fix="open it to at least half the thickness, {limit:.3g} mm"),
        _r("hole_diameter", "holes", "size_mm", "min", 1.0, "mm", "hole size (5052 aluminum)", SCS_5052,
           scale_by="thickness", when={"scs_5052": True, "scale_known": True},
           fix="open it to at least the thickness, {limit:.3g} mm",
           note="the 5052 page's own minimum, stricter than the cutting guide's half thickness"),
        _r("hole_to_edge", "holes", "edge_distance_mm", "min", 2.0, "mm", "hole-to-edge distance (5052)",
           SCS_5052, scale_by="thickness", when={"scs_5052": True, "scale_known": True},
           fix="move the hole in to at least twice the thickness, {limit:.3g} mm, from the edge"),
        _r("bend_radius", "bends", "inside_radius_mm", "min", 1.0, "mm", "inside bend radius", SCS_5052,
           scale_by="thickness", severity="warning", when={"scs_5052": True, "scale_known": True},
           fix="5052 bends as tight as the thickness in many tempers, {limit:.3g} mm"),
        _r("bend_angle", "bends", "angle_deg", "max", 130.0, "deg", "bend angle", SCS_BENDING,
           fix="bend no more than 130 degrees from flat (no hems)",
           note="max bend angle 130 degrees, read as the angle bent from flat; no hemming"),
        _r("bend_angle_min", "bends", "angle_deg", "min", 5.0, "deg", "bend angle", SCS_BENDING,
           fix="a bend under 5 degrees is not bent: leave it flat or bend it more"),
        _r("flange_length", "flanges", "length_outside_half_mm", "min", 1.0, "mm",
           "formed flange length from the bend's apex (along half the bend)", SCS_CALCULATOR,
           scale_by="scs_min_flange_mm", when={"scs_gauge": True},
           fix="lengthen the flange to the calculator's minimum, {limit:.3g} mm from the bend's apex, over at "
               "least half the bend", note="minimum formed flange at 90 degrees; flanges must meet it over 50 to "
                                           "60% of the bend length"),
        _r("hole_to_bend", "hole_to_bend", "distance_centerline_mm", "min", 1.0, "mm",
           "feature distance from the bend centre line", SCS_DEFORMATION, scale_by="scs_half_die_mm",
           when={"scs_gauge": True}, fix="move the feature at least half the die width, {limit:.3g} mm, from "
                                         "the bend line", note="the die centres on the bend line"),
        _r("bend_relief_depth", "reliefs", "depth_centerline_minus_radius_mm", "min", 0.508, "mm",
           "relief depth past the bend line less the inside radius", SCS_DEFORMATION,
           when={"scs_thin": True, "scale_known": True}, item_when={"kind": "bend"},
           fix="cut the relief to the bend radius plus 0.020 in past the bend line",
           note="unsupported bends to 0.187 in: relief depth = effective bend radius + 0.020 in from the bend "
                "line"),
        _r("channel_base", "channels", "base_to_flange_ratio", "min", 2.0, "ratio",
           "U-channel base over flange length", SCS_BENDING, fix="make the channel's base at least twice its "
                                                                 "flange length"),
        _r("bend_length", "bends", "length_mm", "max", 1117.6, "mm", "bend length", SCS_BENDING,
           fix="bends are at most 44 in long, less for thick steel and stainless",
           note="16 to 44 in depending on thickness"),
        _r("flat_length", "parts", "flat_length_mm", "max", 1.0, "mm", "flat blank's long side to bend",
           SCS_BENDING, scale_by="sheet_long_mm", when={"bent": True, "scale_known": True},
           fix="a part to bend is at most 30 x 44 in flat"),
        _r("flat_width", "parts", "flat_width_mm", "max", 1.0, "mm", "flat blank's short side to bend",
           SCS_BENDING, scale_by="sheet_short_mm", when={"bent": True, "scale_known": True},
           fix="a part to bend is at most 30 x 44 in flat"),
        _r("flat_length", "parts", "flat_length_mm", "max", 1.0, "mm", "part's long side", SCS_MINMAX,
           scale_by="sheet_long_mm", when={"bent": False, "scale_known": True},
           fix="laser-cut parts are at most 44 x 68 in (5052, mild steel; 44 x 30 in for most other metals)"),
        _r("flat_width", "parts", "flat_width_mm", "max", 1.0, "mm", "part's short side", SCS_MINMAX,
           scale_by="sheet_short_mm", when={"bent": False, "scale_known": True},
           fix="laser-cut parts are at most 44 x 68 in (5052, mild steel; 44 x 30 in for most other metals)"),
        _r("flat_min", "parts", "flat_width_mm", "min", 6.35, "mm", "part's short side", SCS_MINMAX,
           when={"bent": False, "scale_known": True}, fix="the smallest laser-cut part is 0.25 x 0.375 in"),
        _r("flat_min", "parts", "flat_width_mm", "min", 9.525, "mm", "flat blank's short side to bend",
           SCS_BENDING, when={"bent": True, "scale_known": True},
           fix="the smallest part to bend is 0.375 x 1.5 in flat"),
        _r("flat_min_length", "parts", "flat_length_mm", "min", 38.1, "mm", "flat blank's long side to bend",
           SCS_BENDING, when={"bent": True, "scale_known": True},
           fix="the smallest part to bend is 0.375 x 1.5 in flat"),
        _r("cut_layers", "cut_file", "cut_layer_count", "max", 1.0, "layers", "layers holding cut geometry",
           SCS_CUTTING, severity="warning", fix="put all cut geometry on one layer"),
    ),
    (SCS_CUTTING, SCS_BENDING, SCS_DEFORMATION, SCS_CALCULATOR, SCS_5052, SCS_MINMAX),
    note="SendCutSend's cutting and bending guides and its bending calculator (per material and gauge: give "
         "--material)")

def _guarded(rule_set: RuleSet) -> RuleSet:
    """Every rule on a length withheld where the source's units are not known (a DXF without $INSUNITS)."""
    rules = tuple(rule if rule.unit not in ("mm", "mm2") or "scale_known" in rule.when
                  else replace(rule, when={**rule.when, "scale_known": True}) for rule in rule_set.rules)
    return replace(rule_set, rules=rules)


RULE_SETS: dict[str, RuleSet] = {name: _guarded(rule_set) for name, rule_set in (
    ("generic", _GENERIC), ("hubs", _HUBS), ("protolabs", _PROTOLABS), ("sendcutsend", _SCS))}


# --- the type side's functions ---------------------------------------------------------------------------

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


def _thickness(report: dict[str, Any], resolved: dict[str, Any]) -> float | None:
    if resolved.get("thickness") is not None:
        return float(resolved["thickness"])
    parts = (report.get("parts") or {}).get("items") or []
    values = [part.get("thickness_mm") for part in parts if isinstance(part.get("thickness_mm"), (int, float))]
    return float(values[0]) if values else None


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    thickness = _thickness(report, resolved)
    bends = (report.get("bends") or {}).get("items") or []
    bent = bool(bends) or bool(report.get("bent"))
    rules = resolved.get("rules")
    scale = report.get("scale") or {}
    found: dict[str, Any] = {"material": material, "material_class": materials.material_class(material),
                             "thickness": thickness, "bent": bent, "kerf": resolved.get("kerf"),
                             "scale_known": not scale.get("units_unknown", False)}
    given = sheet_size(resolved.get("sheet_size"))
    if given is None and rules == "sendcutsend" and bent:
        given = SCS_BENDING_SHEET
    sheet = given or SHEETS.get(str(rules), SHEETS["generic"])[0]
    found["sheet_long_mm"], found["sheet_short_mm"] = sheet
    if thickness is not None:
        found["protolabs_edge_band"] = "thin" if thickness <= 0.914 + 1e-9 else "thick"
        found["notch_min_mm"] = max(thickness, 1.016)
        found["tab_min_mm"] = max(2.0 * thickness, 3.2)
        group = _PROTOLABS_GROUP.get(material or "")
        found["protolabs_toolkit"] = group is not None
        if group is not None:
            found["protolabs_flange_t"] = PROTOLABS_FLANGE[group][_protolabs_band(thickness)] * thickness
        row = scs_row(material, thickness)
        found["scs_gauge"] = row is not None
        if row is not None:
            _, (_, radius, die, flange) = row
            found["scs_min_flange_mm"] = flange * IN
            found["scs_half_die_mm"] = die * IN / 2.0
            found["scs_radius_mm"] = radius * IN
        found["scs_thin"] = thickness <= 0.187 * IN + 1e-6
    else:
        found.update(protolabs_toolkit=False, scs_gauge=False, scs_thin=False)
    found["scs_5052"] = material == "aluminum"
    return found


def _items(report: dict[str, Any], family: str) -> list[dict[str, Any]]:
    value = report.get(family)
    if not isinstance(value, dict) or "error" in value:
        return []
    return [item for item in value.get("items") or [] if isinstance(item, dict)]


_FILE_DEFECTS = {
    # family: (code, severity, what, fix)
    "open_geometry": ("sheet.open_contour", "error", "open geometry on a cut layer cuts nothing out",
                      "close the contour, or move the open geometry to a bend, engrave or reference layer"),
    "overlaps": ("sheet.overlapping_curves", "error", "curves lie on one another: the cutter goes over the line "
                                                      "twice", "delete the overlapping copy, or join the curves"),
    "self_intersections": ("sheet.self_intersecting", "error", "a contour crosses itself",
                           "redraw the contour so it does not cross itself"),
    "contour_crossings": ("sheet.crossing_contours", "error", "two contours cross: the cut leaves slivers",
                          "join or separate the contours"),
    "zero_area_loops": ("sheet.zero_area_loop", "error", "a closed loop encloses no area: a doubled-back line",
                        "delete the degenerate loop"),
    "annotations": ("sheet.annotation_on_cut_layer", "warning", "text, dimensions or other annotation on a cut "
                                                                 "layer", "move it to a reference layer, or turn "
                                                                          "engraved text into outlines on its own layer"),
    "floating_interiors": ("sheet.floating_interior", "warning", "a closed contour inside a hole: that piece "
                                                                 "falls out when cut", "bridge it to the part, "
                                                                                       "or delete it"),
    "short_line_runs": ("sheet.short_line_run", "warning", "a curve drawn as a run of short lines",
                        "export the curve as arcs or a spline, not chords"),
}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    given = resolved.get("thickness")
    for part in _items(report, "parts"):
        where = part.get("location")
        if not part.get("is_sheet", True):
            found.append(CheckFinding(
                "error", "sheet.not_sheet",
                f"{part.get('name') or 'the part'} is not one sheet: {part.get('why') or 'no constant thickness'}",
                where, "model it as one thickness of sheet, its bends as inside and outside radii a thickness apart"))
        measured = part.get("thickness_mm")
        if given is not None and isinstance(measured, (int, float)):
            tolerance = max(0.01, 0.005 * float(given))
            if abs(float(measured) - float(given)) > tolerance:
                found.append(CheckFinding("error", "sheet.thickness_mismatch",
                                          f"the part is {measured:.4g} mm thick, the stock {float(given):.4g} mm",
                                          where, "model the part at the stock's thickness, or order the part's"))
        if part.get("flat_overlap_mm2"):
            found.append(CheckFinding("error", "sheet.flat_overlap",
                                      f"the flat pattern overlaps itself by {part['flat_overlap_mm2']:.4g} mm2: "
                                      "it cannot be cut in one piece", where,
                                      "shorten or cut back the flanges that collide when unfolded"))
        if part.get("unfold_note"):
            found.append(CheckFinding("warning", "sheet.not_unfolded", str(part["unfold_note"]), where))
    radius = resolved.get("bend_radius")
    bends = _items(report, "bends")
    if radius is not None:
        for bend in bends:
            value = bend.get("inside_radius_mm")
            if isinstance(value, (int, float)) and abs(value - float(radius)) > max(0.01, 0.01 * float(radius)):
                found.append(CheckFinding(
                    "warning", "sheet.bend_radius_differs",
                    f"the bend's inside radius is {value:.4g} mm, the shop's {float(radius):.4g} mm: the part and "
                    "its flat pattern will come out differently", bend.get("location"),
                    f"model the bend at the shop's {float(radius):.4g} mm inside radius"))
    if resolved.get("rules") == "sendcutsend" and radius is None:
        expected = context(report, resolved).get("scs_radius_mm")
        if expected is not None:
            for bend in bends:
                value = bend.get("inside_radius_mm")
                if isinstance(value, (int, float)) and abs(value - expected) > max(0.05, 0.05 * expected):
                    found.append(CheckFinding(
                        "warning", "sheet.bend_radius_differs",
                        f"SendCutSend bends this gauge at a {expected:.3g} mm effective radius and offers no "
                        f"other; the model's bend is {value:.4g} mm", bend.get("location"),
                        f"model the bend at {expected:.3g} mm so the flat pattern matches"))
    radii = sorted({round(float(bend["inside_radius_mm"]), 3) for bend in bends
                    if isinstance(bend.get("inside_radius_mm"), (int, float))})
    if len(radii) > 1:
        found.append(CheckFinding("info", "sheet.bend_radii_mixed",
                                  f"the bends use {len(radii)} inside radii ({', '.join(f'{r:g}' for r in radii)} mm)",
                                  "bends", "one radius for every bend saves tool changes"))
    kerf = resolved.get("kerf")
    if kerf:
        for family, field, what in (("holes", "size_mm", "hole"), ("webs", "width_mm", "web"),
                                    ("gaps", "width_mm", "gap")):
            for item in _items(report, family):
                value = item.get(field)
                if isinstance(value, (int, float)) and value < float(kerf):
                    found.append(CheckFinding("error", "sheet.under_kerf",
                                              f"a {what} {value:.4g} mm wide is narrower than the {float(kerf):g} mm "
                                              "kerf: the cut takes it away", item.get("location"),
                                              f"make it wider than the kerf, {float(kerf):g} mm"))
    for hole in _items(report, "holes"):
        if hole.get("in_bend"):
            found.append(CheckFinding("warning", "sheet.hole_in_bend", "a hole cuts across a bend: it distorts "
                                      "as the bend forms", hole.get("location"),
                                      "move the hole out of the bend, or cut it after bending"))
    for family, (code, severity, what, fix) in _FILE_DEFECTS.items():
        items = _items(report, family)
        for item in items[:8]:
            found.append(CheckFinding(severity, code, f"{what} ({item.get('detail') or item.get('kind') or ''})"
                                      .replace(" ()", ""), item.get("location"), fix))
        if len(items) > 8:
            found.append(CheckFinding(severity, code, f"{len(items) - 8} more of the same", family))
    cut = report.get("cut_file") or {}
    if resolved.get("rules") == "sendcutsend" and cut.get("insunits") not in (None, 1, 4):
        found.append(CheckFinding("error", "sheet.units", f"the file's units are {cut.get('unit')}: SendCutSend "
                                  "takes inches or millimetres", "$INSUNITS", "save the file in inches or mm"))
    if resolved.get("k_factor") is None and bends:
        sources = sorted({str(bend.get("k_factor_source")) for bend in bends if bend.get("k_factor_source")})
        if sources:
            found.append(CheckFinding("info", "sheet.k_factor_assumed",
                                      f"the flat pattern unfolds with K from {'; '.join(sources)}", "bends",
                                      "give --k-factor from the shop's bend table for a production flat pattern"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if "cut_file" in report:
        cut = report.get("cut_file") or {}
        parts = _items(report, "parts")
        size = (f", {mm(parts[0].get('flat_length_mm'))} x {mm(parts[0].get('flat_width_mm'))} mm"
                if len(parts) == 1 else "")
        return f"cut file: {len(parts)} part(s), {cut.get('contour_count', 0)} contour(s){size}"
    parts = _items(report, "parts")
    bends = _items(report, "bends")
    thickness = parts[0].get("thickness_mm") if parts else None
    flat = (f", flat {mm(parts[0].get('flat_length_mm'))} x {mm(parts[0].get('flat_width_mm'))} mm"
            if len(parts) == 1 and parts[0].get("flat_length_mm") is not None else "")
    return f"sheet {mm(thickness)} mm, {len(bends)} bend(s){flat}"
