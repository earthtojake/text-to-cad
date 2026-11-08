"""Sheet metal, cut and bent: its options, rules, findings and summary (``cad._internal.dfm``).

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

**The rules** (``RULES``) are general practice, each from a published sheet metal design guide (cited as the
evidence, not as a shop's limit). A shop's own figures -- its gauges, its tooled radius per gauge, its die
widths, its brake's angles and lengths, its smallest and largest parts -- are no rule here: give the ones it
publishes (``--thickness``, ``--bend-radius``, ``--k-factor``, ``--kerf``, ``--sheet-size``), or compare the
measurements with them.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["DEFAULT_SHEET", "MEASURED_FROM", "OPTIONS", "RULES", "context", "findings", "k_factor", "sheet_size",
           "summary", "validate"]

OPTIONS: dict[str, Any] = {"thickness": None, "k_factor": None, "bend_radius": None, "kerf": None,
                           "sheet_size": None}
MEASURED_FROM = ("brep",)
ACCESSED = "2026-11-03"

# --- sources ---------------------------------------------------------------------------------------------

HUBS = Source("hubs-sheet", "Protolabs Network (Hubs)", "Sheet metal fabrication design guide",
              "https://www.hubs.com/guides/sheet-metal-fabrication/", ACCESSED)
PROTOLABS = Source("protolabs-sheet", "Protolabs", "Sheet metal fabrication design guidelines",
                   "https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/", ACCESSED)
XOMETRY = Source("xometry-sheet", "Xometry", "Sheet metal fabrication service (design guidelines)",
                 "https://www.xometry.com/capabilities/sheet-metal-fabrication/", ACCESSED)

# --- tables the rules read through ``context`` ------------------------------------------------------------

#: Hubs's K-factor chart, air bending: (inside radius up to 1 t, 1 to 3 t, over 3 t) per hardness.
HUBS_K_AIR = {"soft": (0.33, 0.40, 0.50), "medium": (0.38, 0.43, 0.50), "hard": (0.40, 0.45, 0.50)}
_HARDNESS = {"aluminum": "soft", "copper": "soft", "brass": "soft", "steel": "medium", "galvanized": "medium",
             "stainless": "hard", "titanium": "hard"}

#: The sheet a flat pattern is held to where no --sheet-size names the shop's (long x short, mm): a 5 x 10 ft
#: blank, the largest of the standard sheet sizes (4 x 8, 4 x 10, 5 x 10 ft).
DEFAULT_SHEET = (3048.0, 1524.0)


def sheet_size(text: str | None) -> tuple[float, float] | None:
    """``1219x2438``: the largest sheet in millimetres, long side first; None for ``DEFAULT_SHEET``."""
    if text is None:
        return None
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 2 or not all(value > 0 and math.isfinite(value) for value in values):
        raise ArgumentRefused(f"--sheet-size is two lengths in millimetres, X x Y (1219x2438), not {text!r}")
    return (max(values), min(values))


def k_factor(material: str | None, inside_radius: float, thickness: float) -> tuple[float, str]:
    """The K-factor a bend is unfolded with when none is given (``--k-factor``, the shop's), and where it comes
    from: Hubs's air-bending chart by the material's hardness and the bend's radius over thickness (medium,
    steel's, for a material not given)."""
    resolved = materials.resolve(material) if material else None
    hardness = _HARDNESS.get(resolved or "", "medium")
    ratio = inside_radius / thickness if thickness > 0 else 0.0
    column = 0 if ratio <= 1.0 + 1e-6 else 1 if ratio <= 3.0 + 1e-6 else 2  # a band's edge is in the band
    band = ("inside radius up to 1 t", "inside radius 1 to 3 t", "inside radius over 3 t")[column]
    said = f"{resolved}'s" if resolved in _HARDNESS else "no material given: medium (steel)"
    return HUBS_K_AIR[hardness][column], f"Hubs's K-factor chart, air bending, {hardness} ({said}), {band}"


# --- the rules -------------------------------------------------------------------------------------------

def _r(ident: str, family: str, field: str, op: str, limit: Any, unit: str, what: str, source: Source, **more: Any
       ) -> Rule:
    return Rule(f"sheet.{ident}", family, field, op, limit, unit, what, source.id, **more)


_SCALED = {"when": {"scale_known": True}}


def _uniform(source: Source, note: str) -> tuple[Rule, ...]:
    """One thickness throughout, judged on the faces of sheet parts that depart from it (``not_sheet`` items
    with ``judged``): a stretch thicker or thinner than the sheet against the sheet's own thickness where the
    document's sheet parts share one (the message gives both), else by how far it departs; a face with no
    opposite face a thickness across (a round, a boss's side) by how far it departs."""
    thicker = {"kind": "thicker", "judged": True}
    thinner = {"kind": "thinner", "judged": True}
    fix_thicker = ("make it the sheet's {limit:.4g} mm: no boss, rib, second plate or doubled layer on the sheet "
                   "(or give --thickness for thicker stock)")
    fix_thinner = "make it the sheet's {limit:.4g} mm: no pocket, step or partial cut into the sheet"
    return (
        _r("uniform_thickness", "not_sheet", "local_thickness_mm", "max", 1.0, "mm",
           "local thickness (the sheet's is the maximum)", source, scale_by="sheet_thickness_mm",
           when={"one_thickness": True}, item_when=thicker, fix=fix_thicker, note=note),
        _r("uniform_thickness", "not_sheet", "local_thickness_mm", "min", 1.0, "mm",
           "local thickness (the sheet's is the minimum)", source, scale_by="sheet_thickness_mm",
           when={"one_thickness": True}, item_when=thinner, fix=fix_thinner, note=note),
        _r("uniform_thickness", "not_sheet", "deviation_mm", "max", 0.0, "mm",
           "thickness above the sheet's (parts of several thicknesses)", source, when={"one_thickness": False},
           item_when=thicker, fix="make it its sheet's thickness: no boss, rib, second plate or doubled layer",
           note=note),
        _r("uniform_thickness", "not_sheet", "deviation_mm", "max", 0.0, "mm",
           "thickness below the sheet's (parts of several thicknesses)", source, when={"one_thickness": False},
           item_when=thinner, fix="make it its sheet's thickness: no pocket, step or partial cut", note=note),
        _r("uniform_thickness", "not_sheet", "deviation_mm", "max", 0.0, "mm",
           "departure of a face with no opposite face a thickness across", source,
           item_when={"kind": "unpaired", "judged": True},
           fix="make the part one thickness throughout: every face of the sheet has its opposite face a thickness "
               "across (a bend: an inside radius r and an outside radius r + t about one axis)", note=note),
    )


def _holes(source: Source, *, diameter: float | None, diameter_severity: str = "error", edge: float | None = None,
           spacing: float | None = None, note: str = "", edge_note: str = "") -> tuple[Rule, ...]:
    rules = []
    if diameter is not None:
        rules.append(_r("hole_diameter", "holes", "size_mm", "min", diameter, "mm", "hole or slot size", source,
                        scale_by="thickness", severity=diameter_severity, note=note,
                        fix="open it to at least {limit:.3g} mm (the thickness times the source's ratio), "
                            "or drill it after cutting", **_SCALED))
    if edge is not None:
        # a recommendation, a warning: "Holes should be at least the sheet's thickness from the edge"
        rules.append(_r("hole_to_edge", "holes", "edge_distance_mm", "min", edge, "mm", "hole-to-edge distance",
                        source, scale_by="thickness", severity="warning", note=edge_note,
                        fix="move the hole in to at least {limit:.3g} mm from the edge", **_SCALED))
    if spacing is not None:
        rules.append(_r("hole_spacing", "hole_spacing", "distance_mm", "min", spacing, "mm",
                        "hole-to-hole distance (edge to edge)", source, scale_by="thickness",
                        fix="space the holes at least {limit:.3g} mm apart, edge to edge", **_SCALED))
    return tuple(rules)


def _notches_tabs(source: Source) -> tuple[Rule, ...]:
    # recommendations, warnings: notches "should be at least the greater of material thickness or 0.04 in.
    # (1.016mm), and no longer than 5 times its width"; tabs likewise (punch tooling's proportions)
    notch = ("notches should be at least the greater of the thickness or 0.04 in and no longer than five times "
             "their width (a recommendation)")
    tab = ("tabs should be at least the greater of twice the thickness or 0.126 in and no longer than five times "
           "their width (a recommendation)")
    return (
        _r("notch_width", "notches", "width_mm", "min", 1.0, "mm", "notch width", source, severity="warning",
           scale_by="notch_min_mm", note=notch, fix="widen the notch to at least {limit:.3g} mm (the greater of the "
                                                    "thickness and 1.016 mm)", **_SCALED),
        _r("notch_length", "notches", "length_to_width", "max", 5.0, "ratio", "notch length over its width",
           source, severity="warning", note=notch,
           fix="shorten the notch or widen it: its length at most five times its width"),
        _r("tab_width", "tabs", "width_mm", "min", 1.0, "mm", "tab width", source, scale_by="tab_min_mm",
           severity="warning", note=tab,
           fix="widen the tab to at least {limit:.3g} mm (the greater of twice the thickness and 3.2 mm)",
           **_SCALED),
        _r("tab_length", "tabs", "length_to_width", "max", 5.0, "ratio", "tab length over its width", source,
           severity="warning", note=tab, fix="shorten the tab or widen it: its length at most five times its width"),
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
    """The flat pattern on the sheet: an error against the sheet given (``--sheet-size``, the shop's), a
    warning against the standard sheet assumed (``DEFAULT_SHEET``), which is no shop's limit."""
    rules = []
    for given, severity, said in ((True, "error", "the {limit:.4g} mm sheet given"),
                                  (False, "warning", "the {limit:.4g} mm standard sheet assumed: give --sheet-size")):
        rules += [
            _r("flat_length", "parts", "flat_length_mm", "max", 1.0, "mm", "flat pattern's long side", source,
               scale_by="sheet_long_mm", severity=severity, note=note,
               when={"scale_known": True, "sheet_given": given},
               fix="split the part or nest it on a larger sheet: the flat pattern is longer than " + said),
            _r("flat_width", "parts", "flat_width_mm", "max", 1.0, "mm", "flat pattern's short side", source,
               scale_by="sheet_short_mm", severity=severity, note=note,
               when={"scale_known": True, "sheet_given": given},
               fix="split the part: the flat pattern is wider than " + said)]
    return tuple(rules)


def _hubs_rules(source: Source) -> tuple[Rule, ...]:
    return (
        # a recommendation, a warning: "We recommend a sheet metal thickness range between 0.5-10 mm"
        _r("thickness_max", "parts", "thickness_mm", "max", 6.0, "mm", "sheet thickness", source,
           when={"bent": True}, item_when={"is_sheet": True}, severity="warning",
           fix="bend sheet no thicker than {limit:g} mm", note="recommended for bending: 0.5 to 6 mm"),
        _r("thickness_max", "parts", "thickness_mm", "max", 10.0, "mm", "sheet thickness", source,
           when={"bent": False}, item_when={"is_sheet": True}, severity="warning",
           fix="laser cut sheet no thicker than {limit:g} mm", note="recommended for laser cutting: 0.5 to 10 mm"),
        _r("thickness_min", "parts", "thickness_mm", "min", 0.5, "mm", "sheet thickness", source,
           item_when={"is_sheet": True}, severity="warning", fix="use sheet at least {limit:g} mm thick",
           note="recommended: at least 0.5 mm"),
        _r("bend_radius", "bends", "inside_radius_mm", "min", 1.0, "mm", "inside bend radius", source,
           scale_by="thickness", severity="warning", item_when={"kind": "bend"},  # a hem's is hem_diameter's
           fix="open the inside radius to at least the thickness, {limit:.3g} mm", **_SCALED),
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
                note="smaller holes are possible, with more risk of distortion",
                edge_note="holes should be at least the sheet's thickness from the edge (a recommendation)"),
        _r("web_width", "webs", "width_mm", "min", 1.0, "mm", "material between cuts", source,
           scale_by="thickness", severity="warning",
           fix="leave at least {limit:.3g} mm of material between the cuts",
           note="Hubs's hole-to-edge minimum, applied to any web of material between two cut edges", **_SCALED),
    )


_RULES = (*_uniform(PROTOLABS, "material thickness uniform throughout"), *_hubs_rules(HUBS),
          *_notches_tabs(PROTOLABS), *_hems(PROTOLABS),
          *_flat_size(XOMETRY, "the flat blank fits the sheet it is cut from; standard blanks run to 5 x 10 ft "
                               "(1524 x 3048 mm), unless --sheet-size names the shop's sheet"))


def _guarded(rule_set: RuleSet) -> RuleSet:
    """Every rule on a length withheld where the source's units are not known (a DXF without $INSUNITS)."""
    rules = tuple(rule if rule.unit not in ("mm", "mm2") or "scale_known" in rule.when
                  else replace(rule, when={**rule.when, "scale_known": True}) for rule in rule_set.rules)
    return replace(rule_set, rules=rules)


RULES = _guarded(RuleSet(
    "sheet", "text-to-cad general rules", "2026-11-08", _RULES, (HUBS, PROTOLABS, XOMETRY),
    note="general practice from published sheet metal design guides, no shop's limits: Hubs's bending and laser "
         "rules, the uniform-thickness, notch, tab and hem rules of Protolabs' guide, a standard 5 x 10 ft sheet "
         "unless --sheet-size names the shop's; a shop's gauges, tooled radii, dies and part sizes are compared "
         "with the measurements"))


# --- the type side's functions ---------------------------------------------------------------------------

def validate(resolved: dict[str, Any], document_type: str) -> None:
    for name in ("thickness", "bend_radius"):
        if resolved.get(name) is not None and not float(resolved[name]) > 0:
            raise ArgumentRefused(f"--{name.replace('_', '-')} is a length in millimetres above 0, not {resolved[name]}")
    if resolved.get("kerf") is not None and not float(resolved["kerf"]) >= 0:
        raise ArgumentRefused(f"--kerf is a width in millimetres from 0, not {resolved['kerf']}")
    if resolved.get("k_factor") is not None and not 0.0 < float(resolved["k_factor"]) <= 0.5:
        raise ArgumentRefused(f"--k-factor is the neutral axis's place in the thickness, above 0 and at most 0.5, "
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
    scale = report.get("scale") or {}
    found: dict[str, Any] = {"material": material, "material_class": materials.material_class(material),
                             "thickness": thickness, "bent": bent, "kerf": resolved.get("kerf"),
                             "scale_known": not scale.get("units_unknown", False),
                             "cut_file": "cut_file" in report}  # a DXF's: a cut file's own rules apply
    # the sheet's own thickness, what a stretch off it is judged against: one where the document's sheet parts
    # share it (a part that is not sheet is judged by none), else None and each part's departure judges
    parts = (report.get("parts") or {}).get("items") or []
    measured = [float(part["thickness_mm"]) for part in parts
                if part.get("is_sheet", True) and isinstance(part.get("thickness_mm"), (int, float))] or \
        [float(part["thickness_mm"]) for part in parts if isinstance(part.get("thickness_mm"), (int, float))]
    one = bool(measured) and max(measured) - min(measured) <= max(0.005, 0.002 * max(measured))
    found["one_thickness"] = one or not measured
    found["sheet_thickness_mm"] = measured[0] if one else None
    given = sheet_size(resolved.get("sheet_size"))
    found["sheet_given"] = given is not None
    found["sheet_long_mm"], found["sheet_short_mm"] = given or DEFAULT_SHEET
    if thickness is not None:
        found["notch_min_mm"] = max(thickness, 1.016)
        found["tab_min_mm"] = max(2.0 * thickness, 3.2)
    # a sharp bend already says why the flat pattern is short: sheet.flat_incomplete is left to it
    found["sharp_bends_found"] = bool(_items(report, "sharp_bends"))
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


#: The flat pattern holds the part's material to this fraction (its area at K = 0.5 over volume / thickness):
#: past it a flange, a bend or a stretch of material is not in the flat (``sheet.flat_incomplete``).
FLAT_MATERIAL_SLACK = 0.03


def _sharp_message(corner: dict[str, Any]) -> str:
    t = corner.get("thickness_mm") or 0.0
    kind = corner.get("kind")
    if kind == "sharp":
        return (f"a {corner.get('angle_deg') or 0:.0f} degree corner modelled sharp, with no bend radius: a brake "
                "bend has an inside and an outside radius, and this corner's flange is not in the flat pattern")
    if kind == "inside_only":
        r = float(corner.get("inside_radius_mm") or 0.0)
        return (f"an inside radius of {r:.4g} mm with no outside radius of {r + t:.4g} mm about its axis: the "
                "corner's outside is sharp, or a round not concentric with it or not a thickness out")
    if kind == "outside_only":
        r = float(corner.get("outside_radius_mm") or 0.0)
        return (f"an outside radius of {r:.4g} mm with no inside radius of {r - t:.4g} mm about its axis: the "
                "corner's inside is sharp, or a round not concentric with it or not a thickness in")
    return (f"{len(corner.get('faces') or [])} face(s) of the sheet are joined to the unfolded flange by no bend: "
            "not in the flat pattern")


def _sharp_hint(corner: dict[str, Any]) -> str:
    t = float(corner.get("thickness_mm") or 0.0)
    rule = "model an inside radius r >= t and an outside radius r + t at the corner, about one axis"
    kind = corner.get("kind")
    if kind == "inside_only":
        r = float(corner.get("inside_radius_mm") or 0.0)
        return (f"{rule}: keep the {r:.4g} mm inside radius and add a {r + t:.4g} mm outside radius about the same "
                "axis" if r >= t - 1e-9 else f"{rule}: here r {t:.4g} mm, outside {2 * t:.4g} mm")
    if kind == "outside_only":
        r = float(corner.get("outside_radius_mm") or 0.0)
        return (f"{rule}: keep the {r:.4g} mm outside radius and add a {r - t:.4g} mm inside radius about the same "
                "axis" if r - t >= t - 1e-9 else f"{rule}: here r {t:.4g} mm, outside {2 * t:.4g} mm")
    return f"{rule} (t = {t:.4g} mm: r {t:.4g} mm, outside {2 * t:.4g} mm)"


def _faces_said(here: list[dict[str, Any]]) -> str:
    refs = [str(item.get("location", "")).rsplit("/", 1)[-1] for item in here]
    return ", ".join(refs[:6]) + (f" and {len(refs) - 6} more" if len(refs) > 6 else "")


def _surface_findings(report: dict[str, Any]) -> list[CheckFinding]:
    """One finding per part for its formed faces (``sheet.formed_surface``) and one for its chamfered or
    rounded cut edges (``sheet.edge_break``), each naming its faces."""
    found: list[CheckFinding] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in _items(report, "not_sheet"):
        if item.get("judged") and item.get("kind") in ("formed", "edge_break"):
            part = str(item.get("location", "")).rsplit("/", 1)[0]
            groups.setdefault((item["kind"], part), []).append(item)
    for (kind, _), here in groups.items():
        if kind == "formed":
            surfaces = sorted({str(item.get("surface")) for item in here})
            found.append(CheckFinding(
                "error", "sheet.formed_surface",
                f"{len(here)} face(s) of the sheet are formed to a {' and '.join(surfaces)} surface "
                f"({_faces_said(here)}): a cone or a torus is rolled, spun or stamped, not brake-bent",
                here[0].get("location"),
                "make each bend a cylinder about a straight axis between flat flanges, or quote the part as formed "
                "(rolled, spun or stamped)"))
        else:
            deepest = max(float(item.get("break_mm") or 0.0) for item in here)
            found.append(CheckFinding(
                "warning", "sheet.edge_break",
                f"{len(here)} face(s) chamfer or round the cut edges ({_faces_said(here)}; up to {deepest:.3g} mm "
                "deep): a laser or waterjet cuts a square edge, so a chamfer or a round is a second operation "
                "(deburring, an edge-break pass)", here[0].get("location"),
                "leave the cut edges square and call for deburring, or quote the chamfers as a second operation"))
    return found


def _thickness_unknown(report: dict[str, Any], resolved: dict[str, Any]) -> list[CheckFinding]:
    """A cut file checked with no --thickness: how many of the rules scale with it, so were not
    evaluated -- an OK is not a pass of them."""
    if "cut_file" not in report or resolved.get("thickness") is not None:
        return []
    rule_set = RULES
    without = context(report, resolved)
    given = context(report, {**resolved, "thickness": 1.0})
    waiting = sorted({rule.id for rule in rule_set.rules if isinstance(report.get(rule.family), dict)
                      and rule.applies(given) and rule.limit_for(given) is not None
                      and (not rule.applies(without) or rule.limit_for(without) is None)})
    if not waiting:
        return []
    names = ", ".join(ident.removeprefix("sheet.") for ident in waiting)
    return [CheckFinding("warning", "sheet.thickness_unknown",
                         f"a cut file carries no thickness: {len(waiting)} rule(s) that scale with it were not "
                         f"evaluated ({names})", "rules", "give --thickness (the stock's, in mm)")]


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
        fraction = part.get("flat_material_fraction")
        # where a sharp_bend or a judged not_sheet face already says why the flat is short, that error is the
        # finding; this one fires where nothing else explains it
        explained = bool(_items(report, "sharp_bends")) or any(
            item.get("judged") and item.get("kind") != "edge_break" for item in _items(report, "not_sheet"))
        if isinstance(fraction, (int, float)) and abs(float(fraction) - 1.0) > FLAT_MATERIAL_SLACK and not explained:
            why = "a flange or a bend did not unfold"
            found.append(CheckFinding(
                "error", "sheet.flat_incomplete",
                f"the flat pattern holds {100 * float(fraction):.0f}% of the part's material: {why}; it is not the "
                "part's blank", where, "fix what the other findings name, then check again: the flat pattern "
                "and every distance measured on it follow"))
        if part.get("flat_overlap_mm2"):
            found.append(CheckFinding("error", "sheet.flat_overlap",
                                      f"the flat pattern overlaps itself by {part['flat_overlap_mm2']:.4g} mm2: "
                                      "it cannot be cut in one piece", where,
                                      "shorten or cut back the flanges that collide when unfolded"))
        if part.get("unfold_note"):
            found.append(CheckFinding("warning", "sheet.not_unfolded", str(part["unfold_note"]), where))
    found.extend(_surface_findings(report))
    corners: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for corner in _items(report, "sharp_bends"):  # one finding per place and kind, the rest counted
        corners.setdefault((corner.get("location"), corner.get("kind"), corner.get("angle_deg")), []).append(corner)
    for (location, _, _), here in corners.items():
        more = f" (and {len(here) - 1} more at this ref)" if len(here) > 1 else ""
        found.append(CheckFinding("error", "sheet.sharp_bend", _sharp_message(here[0]) + more, location,
                                  _sharp_hint(here[0])))
    # the shop's radius (--bend-radius) against the modelled one: one finding a bend
    radius = resolved.get("bend_radius")
    bends = _items(report, "bends")
    if radius is not None:
        radius = float(radius)
        for bend in bends:
            value = bend.get("inside_radius_mm")
            limit = max(0.01, 0.01 * radius)
            if isinstance(value, (int, float)) and abs(value - radius) > limit:
                found.append(CheckFinding(
                    "warning", "sheet.bend_radius_differs",
                    f"the bend's inside radius is {value:.4g} mm, the shop's {radius:.4g} mm: the part and its "
                    "flat pattern will come out differently", bend.get("location"),
                    f"model the bend at the shop's {radius:.4g} mm inside radius"))
    radii = sorted({round(float(bend["inside_radius_mm"]), 3) for bend in bends  # hems and curls: their own tools
                    if bend.get("kind", "bend") == "bend" and isinstance(bend.get("inside_radius_mm"), (int, float))})
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
    found.extend(_thickness_unknown(report, resolved))
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
        unscaled = ("; no --thickness: the rules that scale with it not evaluated"
                    if resolved.get("thickness") is None else "")
        return f"cut file: {len(parts)} part(s), {cut.get('contour_count', 0)} contour(s){size}{unscaled}"
    parts = _items(report, "parts")
    bends = _items(report, "bends")
    thickness = parts[0].get("thickness_mm") if parts else None
    flat = (f", flat {mm(parts[0].get('flat_length_mm'))} x {mm(parts[0].get('flat_width_mm'))} mm"
            if len(parts) == 1 and parts[0].get("flat_length_mm") is not None else "")
    return f"{mm(thickness)} mm, {len(bends)} bend(s){flat}"
