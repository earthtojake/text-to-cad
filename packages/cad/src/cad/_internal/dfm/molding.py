"""Injection molding: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured along one pull (``pull``), on exact geometry (``cad.build123d._dfm_molding``) or a mesh
(``cad.trimesh._molding``), one schema either way:

- ``draft``: every wall face's draft and which way it opens (``+pull``, ``-pull``, ``none``, ``split``);
- ``undercuts``: the trapped features, each with what releases it (``side_action`` and its directions and
  stroke, ``lifter``, ``collapsible_core``, ``none``) and whether it faces outside or in;
- ``thickness``: the nominal wall, each face's (or region's) thin and thick readings, and whether it is a
  wall's or a rib's or boss's (``feature``: their rules judge those, the wall's range does not);
- ``transitions``: each step in the wall, its run over its change, read on the stepped side (a free-form
  face's from the rolling ball);
- ``ribs`` and ``bosses``: their thickness, height, fillet and spacing against the wall they stand on (a
  rib with a barb is a snap arm, ``kind``: snap);
- ``corners``: the internal corners, their radius against the wall;
- ``projection`` and ``envelope``: the projected area along the pull, the part's spans and depths;
- ``parting``: whether one flat parting plane takes the outline, its height, what it does not take;
- ``clamp``: the clamp force the projected area needs (added here: a resin's factor, ``CLAMP_FACTORS``,
  times the area, the cavities and a safety margin -- an estimate, its source named).

With ``candidates`` the pulls are ranked (x, y, z and the part's principal axes) instead (``ranked``); where
the pull looks wrong (``pull_doubtful``) the measurement ranks them too (``pull_check``) and the hint names the
one ranked first.
"""

from __future__ import annotations

from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, where
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["CLAMP_FACTORS", "MEASURED_FROM", "OPTIONS", "RULE_SETS", "WALL_RANGES", "clamp", "context", "findings",
           "pull_doubtful", "ranked", "summary", "validate"]

OPTIONS: dict[str, Any] = {"pull": "z", "wall_limit": 45.0, "zero_tol": 0.05, "cavities": None}
MEASURED_FROM = ("brep", "mesh")
_ACCESSED = "2026-11-03"
_VERSION = "2026-11-06"

HUBS = Source("hubs-im", "Protolabs Network (Hubs)", "Injection molding design guide",
              "https://www.hubs.com/guides/injection-molding/", _ACCESSED)
PROTOLABS = Source("protolabs-im", "Protolabs", "Plastic injection molding design guidelines",
                   "https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/",
                   _ACCESSED)
PROTOLABS_WALLS = Source("protolabs-walls", "Protolabs", "Improving part design with uniform wall thickness",
                         "https://www.protolabs.com/resources/design-tips/improving-part-design-with-uniform-wall-thickness/",
                         _ACCESSED)
XOMETRY = Source("xometry-im", "Xometry", "Custom plastic injection molding services (design guidelines)",
                 "https://www.xometry.com/capabilities/injection-molding-service/", _ACCESSED)
XOMETRY_RIBS = Source("xometry-ribs", "Xometry", "Plastic ribs for injection-molding design",
                      "https://www.xometry.com/resources/injection-molding/plastic-ribs-for-injection-molding-design/",
                      _ACCESSED)
MOLDMINDS = Source("moldminds-clamp", "Moldminds", "Clamp force calculator (material tonnage factors)",
                   "https://moldminds.com/clamp-force-calculator/", _ACCESSED)
RJC = Source("rjc-tonnage", "RJC Mold", "Injection molding machine tonnage",
             "https://rjcmold.com/guides/injection-molding-machine-tonnage/", _ACCESSED)
PT = Source("pt-tonnage", "Plastics Technology", "Clamp tonnage: more is better, right?",
            "https://www.ptonline.com/columns/clamp-tonnage-more-is-betterright", _ACCESSED)

_IN = 25.4
#: Protolabs' recommended wall thickness by resin (its table, in inches, "adapted from
#: manufacturingcenter.com"), in millimetres, keyed by ``materials``' names (its polyethylene row stands for
#: HDPE and LDPE too).
WALL_RANGES: dict[str, tuple[float, float]] = {
    "abs": (0.045 * _IN, 0.140 * _IN), "pom": (0.030 * _IN, 0.120 * _IN), "pmma": (0.025 * _IN, 0.500 * _IN),
    "lcp": (0.030 * _IN, 0.120 * _IN), "nylon": (0.030 * _IN, 0.115 * _IN), "pc": (0.040 * _IN, 0.150 * _IN),
    "pbt": (0.025 * _IN, 0.125 * _IN), "petg": (0.025 * _IN, 0.125 * _IN), "pe": (0.030 * _IN, 0.200 * _IN),
    "pp": (0.035 * _IN, 0.150 * _IN), "ps": (0.035 * _IN, 0.150 * _IN),
    "hdpe": (0.030 * _IN, 0.200 * _IN), "ldpe": (0.030 * _IN, 0.200 * _IN), "pps": (0.020 * _IN, 0.180 * _IN),
    "pu": (0.080 * _IN, 0.750 * _IN), "lft": (0.075 * _IN, 1.000 * _IN),
}
#: Moldminds' clamp tonnage factor by resin, US tons per square inch of projected area (its "pe" is HDPE's,
#: 2.0; LDPE's is 1.5).
CLAMP_FACTORS: dict[str, float] = {"abs": 3.25, "pe": 2.0, "hdpe": 2.0, "ldpe": 1.5, "nylon": 4.5, "nylon_gf": 5.0, "pc": 4.0, "pp": 2.0,
                                   "ps": 1.5, "pom": 3.5, "tpu": 2.5}
#: A resin the table lacks: RJC Mold's usual range, 2 to 5 tons per square inch, estimated at Plastics
#: Technology's starting point, 3.
CLAMP_RANGE = (2.0, 5.0)
CLAMP_START = 3.0
#: Moldminds' default safety margin (10-15% general; 20-25% thin-wall, optical, medical).
CLAMP_SAFETY = 0.15
_KN_PER_TON = 8.896443  # a US (short) ton-force in kilonewtons

_MOLDED = ("+pull", "-pull", "none")
_RELEASED = ("side_action", "lifter", "collapsible_core", "unknown")


#: Hubs' and Protolabs' recommended draft, in their words.
_DRAFT_NOTE = ("Hubs: \"A minimum draft angle of 2\u00b0 is recommended.\" (its 1-2 deg is the extra a textured face "
               "adds); Protolabs: \"Most situations: 2\u00b0\"")


def _draft_rules(source: str, least: float, severity: str, preferred: tuple[float, str] | None = None,
                 note: str = "") -> tuple[Rule, ...]:
    rules = [Rule("molding.draft_min", "draft", "draft_deg", "min", least, "deg", "wall draft", source,
                  severity=severity, item_when={"opens": _MOLDED},
                  fix="draft this wall at least {limit:g} deg along the pull (more on tall or textured walls)")]
    if preferred:
        value, cited = preferred
        rules.append(Rule("molding.draft", "draft", "draft_deg", "min", value, "deg", "wall draft", cited,
                          severity="warning", item_when={"opens": _MOLDED}, note=note,
                          fix="draft this wall {limit:g} deg if the design allows: it ejects cleanly and wears less"))
    return tuple(rules)


def _undercut_rules(source: str) -> tuple[Rule, ...]:
    return (
        Rule("molding.undercut", "undercuts", "trapped_area_mm2", "max", 0.0, "mm2", "undercut area", source,
             severity="warning", item_when={"release": _RELEASED},
             fix="the undercut needs the side action, lifter or core the finding names (tooling cost): make it pull "
                 "straight -- a pass-through core, a slot, a shut-off -- or keep it and budget the action"),
        Rule("molding.undercut_unreleasable", "undercuts", "trapped_area_mm2", "max", 0.0, "mm2", "trapped area",
             source, item_when={"release": "none"},
             fix="no slide, lifter or core frees this feature: open it to one side or split the part"),
    )


def _wall_rules() -> tuple[Rule, ...]:
    # A wall's face (``feature``: wall): a rib's and a boss's are judged by their own rules. Both read the face's
    # wall (its area median); its thickest point, a junction's, is thick_section's.
    return (
        Rule("molding.wall_min", "thickness", "thickness_mm", "min", {k: v[0] for k, v in WALL_RANGES.items()}, "mm",
             "wall thickness", "protolabs-im", severity="warning", by="resin", item_when={"feature": "wall"},
             fix="thicken this wall to at least {limit:.3g} mm for the resin, or choose an easier-flowing one"),
        Rule("molding.wall_max", "thickness", "thickness_mm", "max", {k: v[1] for k, v in WALL_RANGES.items()}, "mm",
             "wall thickness", "protolabs-im", severity="warning", by="resin", item_when={"feature": "wall"},
             fix="core this section out to {limit:.3g} mm or less, keeping the wall uniform"),
    )


def _uniform_rules() -> tuple[Rule, ...]:
    return (
        Rule("molding.thick_section", "thickness", "ratio_to_nominal", "max", round(1 / 0.6, 4), "ratio",
             "local thickness over the nominal wall", "protolabs-walls", severity="warning",
             fix="core this section out: a wall no thinner than 40-60% of the walls beside it keeps sink away"),
        Rule("molding.boss_wall", "bosses", "wall_ratio", "max", 0.6, "ratio", "boss wall over the wall it stands on",
             "protolabs-walls", severity="warning",
             fix="thin the boss wall to 40-60% of the wall it stands on (core it deeper or narrow it) to stop sink"),
    )


_RIB = {"kind": "rib"}  # a rib's height and spacing: a snap arm (``kind``: snap) is judged by the snap rule
#: Hubs states both, the wall's and the rib's: the generic and hubs sets take the first.
_RIB_HEIGHT_NOTE = ("Hubs: \"max. height equal to 3x the wall thickness\" and \"Define a height smaller than 3 \u00d7 "
                    "rib thickness\"")


def _rib_rules(thickness: tuple[float, str], height: tuple[str, float, str], fillet: tuple[str, float, str] | None,
               gap: tuple[str, float, str] | None, draft: tuple[float, str] | tuple[float, str, str] | None
               ) -> tuple[Rule, ...]:
    rules = [Rule("molding.rib_thickness", "ribs", "thickness_ratio", "max", thickness[0], "ratio",
                  "rib thickness over the wall it stands on", thickness[1], severity="warning",
                  fix="thin the rib to {limit:g} of the wall or less: a thick rib sinks the face behind it")]
    field, limit, cited = height
    what = "rib height over the wall" if field == "height_ratio" else "rib height over its thickness"
    rules.append(Rule("molding.rib_height", "ribs", field, "max", limit, "ratio", what, cited, severity="warning",
                      item_when=_RIB, note=_RIB_HEIGHT_NOTE if cited == "hubs-im" else "",
                      fix="lower the rib, or use two ribs: a tall thin rib fills poorly and sticks"))
    if fillet:
        field, limit, cited = fillet
        what = "rib base fillet over the rib's thickness" if field == "base_fillet_ratio" else \
            "rib base fillet over the wall"
        rules.append(Rule("molding.rib_base_fillet", "ribs", field, "min", limit, "ratio", what, cited,
                          severity="warning", fix="fillet the rib's root, {limit:g} of the reference or more"))
    if gap:
        field, limit, cited = gap
        what = "gap to the next rib or wall over the rib's thickness" if field == "gap_to_thickness" else \
            "gap to the next rib or wall over the wall"
        rules.append(Rule("molding.rib_gap", "ribs", field, "min", limit, "ratio", what, cited, severity="warning",
                          item_when=_RIB,
                          fix="space the ribs wider: a narrow steel blade between them cools and wears badly"))
    if draft:
        rules.append(Rule("molding.rib_draft", "ribs", "draft_deg", "min", draft[0], "deg", "rib draft", draft[1],
                          severity="warning", note=draft[2] if len(draft) > 2 else "",
                          fix="draft the rib's sides {limit:g} deg or more"))
    return tuple(rules)


#: Hubs' snap-fit and vertical-feature sentences: a snap arm's thickness, a boss's root (no source gives a radius).
_SNAP = Rule("molding.snap_thickness", "ribs", "thickness_ratio", "min", 0.5, "ratio",
             "snap arm thickness over the wall it stands on", "hubs-im", severity="warning",
             item_when={"kind": "snap"},
             note="Hubs: \"Design snap-fits with thickness greater than 0.5x the wall thickness\"; the barb is an "
                  "undercut too (\"snap-fit joints are another example of undercuts\")",
             fix="thicken the snap arm to more than {limit:g} of the wall it stands on")
_BOSS_ROOT = Rule("molding.boss_root_fillet", "bosses", "base_fillet_mm", "min", 0.01, "mm",
                  "boss root fillet radius (any rounding)", "hubs-im", severity="warning",
                  note="Hubs: \"the base of vertical features (like ribs, bosses, snap-fits) must also always be "
                       "rounded\"; no source gives a radius, so the limit (0.01 mm) stands for rounded at all",
                  fix="fillet the boss's root where it meets the wall: a sharp root concentrates stress")


_CORNER = Rule("molding.inside_corner_radius", "corners", "ratio_to_wall", "min", 0.5, "ratio",
               "internal corner radius over the wall", "hubs-im", severity="warning",
               fix="round this internal corner to at least half the wall: a sharp one concentrates stress and "
                   "stalls the flow")
_TRANSITION = Rule("molding.wall_transition", "transitions", "transition_ratio", "min", 3.0, "ratio",
                   "thickness transition's length over its change", "hubs-im", severity="warning",
                   fix="taper the change in thickness over at least {limit:g} times the change (a chamfer or fillet)")

_GENERIC = RuleSet(
    "generic", "molding", "text-to-cad generic", _VERSION,
    (*_draft_rules("protolabs-im", 0.5, "error", (2.0, "hubs-im"), note=_DRAFT_NOTE), *_undercut_rules("hubs-im"),
     *_wall_rules(), *_uniform_rules(), _TRANSITION,
     *_rib_rules((0.6, "xometry-ribs"), ("height_ratio", 3.0, "hubs-im"), ("base_fillet_ratio", 0.25, "hubs-im"),
                 ("gap_to_wall", 2.5, "xometry-ribs"), (0.5, "xometry-ribs")),
     _SNAP, _BOSS_ROOT, _CORNER),
    (HUBS, PROTOLABS, PROTOLABS_WALLS, XOMETRY_RIBS), generic=True,
    note="a starting point drawn from published guides, no shop's limits: Protolabs' 0.5 deg draft minimum and its "
         "wall table, 2 deg recommended (Hubs and Protolabs both), Hubs' corner, transition, undercut, snap-fit and "
         "root guidance, Xometry's and Protolabs' rib and boss proportions")

_PROTOLABS = RuleSet(
    "protolabs", "molding", "Protolabs", _VERSION,
    (*_draft_rules("protolabs-im", 0.5, "error", (2.0, "protolabs-im")), *_undercut_rules("protolabs-im"),
     *_wall_rules(), *_uniform_rules(),
     Rule("molding.side_action_stroke", "undercuts", "stroke_mm", "max", 2.875 * _IN, "mm", "side-action pull",
          "protolabs-im", item_when={"release": "side_action"},
          fix="shorten the slide's travel (a shallower undercut) to under {limit:.4g} mm"),
     Rule("molding.side_action_height", "undercuts", "height_mm", "max", 2.377 * _IN, "mm", "side-action height",
          "protolabs-im", item_when={"release": "side_action"}, fix="a side action is at most {limit:.4g} mm tall"),
     Rule("molding.side_action_width", "undercuts", "width_mm", "max", 8.419 * _IN, "mm", "side-action width",
          "protolabs-im", item_when={"release": "side_action"}, fix="a side action is at most {limit:.4g} mm wide"),
     Rule("molding.projected_area", "projection", "projected_area_mm2", "max", 175.0 * _IN * _IN, "mm2",
          "projected area", "protolabs-im", fix="the press takes {limit:.6g} mm2 of projected area at most"),
     Rule("molding.part_length", "envelope", "span_major_mm", "max", 29.6 * _IN, "mm", "part length across the pull",
          "protolabs-im", fix="the mold takes parts {limit:.4g} mm long at most"),
     Rule("molding.part_width", "envelope", "span_minor_mm", "max", 18.9 * _IN, "mm", "part width across the pull",
          "protolabs-im", fix="the mold takes parts {limit:.4g} mm wide at most"),
     Rule("molding.part_depth", "envelope", "depth_along_pull_mm", "max", 8.0 * _IN, "mm", "part depth along the pull",
          "protolabs-im", fix="the mold takes parts {limit:.4g} mm deep at most"),
     Rule("molding.depth_from_parting", "envelope", "depth_from_parting_mm", "max", 4.0 * _IN, "mm",
          "depth from the parting line", "protolabs-im",
          fix="move the parting line toward the middle: each half reaches {limit:.4g} mm from it at most"),
     Rule("molding.part_volume", "envelope", "volume_mm3", "max", 59.0 * _IN ** 3, "mm3", "part volume",
          "protolabs-im", note="Protolabs: \"Volume: 59 cu. in.\"",
          fix="the press shoots parts of {limit:.6g} mm3 at most: core the part out or split it")),
    (PROTOLABS, PROTOLABS_WALLS),
    note="Protolabs' published limits: its draft, side-action, size and projected-area limits are its feasibility "
         "limits (errors); its wall table and uniform-wall guidance are recommendations (warnings)")

_HUBS = RuleSet(
    "hubs", "molding", "Protolabs Network (Hubs)", _VERSION,
    (Rule("molding.draft", "draft", "draft_deg", "min", 2.0, "deg", "wall draft", "hubs-im", severity="warning",
          item_when={"opens": _MOLDED}, note=_DRAFT_NOTE, fix="draft this wall {limit:g} deg (Hubs' recommended minimum)"),
     *_undercut_rules("hubs-im"), _TRANSITION,
     *_rib_rules((0.5, "hubs-im"), ("height_ratio", 3.0, "hubs-im"), ("base_fillet_ratio", 0.25, "hubs-im"),
                 ("gap_to_thickness", 4.0, "hubs-im"),
                 (0.25, "hubs-im", "Hubs: ribs drafted \"at least 0.25\u00b0 - 0.5\u00b0\": the low end")),
     _SNAP, _BOSS_ROOT, _CORNER),
    (HUBS,),
    note="Hubs' design guide: its numbers are recommendations (warnings) but for an undercut nothing releases")

_XOMETRY = RuleSet(
    "xometry", "molding", "Xometry", _VERSION,
    (*_draft_rules("xometry-im", 0.5, "error"), *_undercut_rules("xometry-im"),
     *_rib_rules((0.6, "xometry-ribs"), ("height_to_thickness", 3.0, "xometry-ribs"),
                 ("base_fillet_wall_ratio", 0.5, "xometry-ribs"), ("gap_to_wall", 2.5, "xometry-ribs"),
                 (0.5, "xometry-ribs"))),
    (XOMETRY, XOMETRY_RIBS),
    note="Xometry's published guidance: its 0.5 deg draft is a minimum (an error), its rib proportions "
         "recommendations")

RULE_SETS: dict[str, RuleSet] = {"generic": _GENERIC, "protolabs": _PROTOLABS, "hubs": _HUBS, "xometry": _XOMETRY}


_AXES = ("x", "y", "z")


def pull(spec: str) -> None:
    """A pull as the measurement reads it (``meshops_molding.pull_vector``), checked with the standard library
    alone: an axis by its name (``z``, ``-y``, ``+x``) or three comma-separated components, not all zero."""
    text = str(spec).strip().lower()
    if (text[1:] if text[:1] in "+-" else text) in _AXES:
        return
    try:
        parts = [float(value) for value in text.split(",")]
    except ValueError:
        parts = []
    if len(parts) != 3:
        raise ArgumentRefused(f"--pull is an axis (x, y, z, -z) or three comma-separated components, not {spec!r}")
    if not all(part == part and abs(part) != float("inf") for part in parts) or not any(parts):
        raise ArgumentRefused(f"--pull {spec!r} has no direction: give components that are finite and not all zero")


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if resolved.get("pull") is not None:
        pull(resolved["pull"])
    material = materials.resolve(resolved.get("material"))
    if materials.material_class(material) == "metal":
        resins = ", ".join(sorted(WALL_RANGES))
        raise ArgumentRefused(f"--material for molding is a resin: {material} is a metal (a resin: {resins})")
    if not 0.0 < float(resolved["wall_limit"]) <= 90.0:
        raise ArgumentRefused(f"--wall-limit is an angle in degrees above 0 and at most 90, not {resolved['wall_limit']}")
    if not 0.0 <= float(resolved["zero_tol"]) < 90.0:
        raise ArgumentRefused(f"--zero-tol is an angle in degrees from 0 below 90, not {resolved['zero_tol']}")
    if resolved.get("cavities") is not None and int(resolved["cavities"]) < 1:
        raise ArgumentRefused(f"--cavities is a count of at least 1, not {resolved['cavities']}")


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    return {"material": material, "material_class": materials.material_class(material), "resin": material,
            "cavities": int(resolved.get("cavities") or 1),
            "nominal_wall_mm": (report.get("thickness") or {}).get("nominal_mm")}


def clamp(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any] | None:
    """The clamp force the projected area needs: per part, area (in2) x the resin's factor x the cavities x
    (1 + the safety margin), in US tons, kN and tonnes. A resin the table lacks gets the usual range."""
    projection = report.get("projection")
    if not isinstance(projection, dict) or "error" in projection:
        return None
    material = materials.resolve(resolved.get("material"))
    cavities = int(resolved.get("cavities") or 1)
    factor = CLAMP_FACTORS.get(material or "")
    low, high = (factor, factor) if factor else CLAMP_RANGE
    estimate = factor or CLAMP_START
    parts = projection.get("items") or [projection]
    items = []
    for part in parts:
        area = float(part.get("projected_area_mm2") or 0.0)
        square_inches = area / (_IN * _IN)
        base = square_inches * cavities * (1 + CLAMP_SAFETY)
        tons = base * estimate
        items.append({"location": part.get("location") or "projection", "projected_area_mm2": round(area, 2),
                      "projected_area_in2": round(square_inches, 3), "cavities": cavities,
                      "factor_tons_per_in2": estimate, "tons": round(tons, 2), "tons_low": round(base * low, 2),
                      "tons_high": round(base * high, 2), "kN": round(tons * _KN_PER_TON, 1),
                      "tonnes": round(tons * 0.90718474, 2), **({"xyz": part["xyz"]} if part.get("xyz") else {})})
    return {
        "material": material, "cavities": cavities, "safety_factor": CLAMP_SAFETY,
        "factor_tons_per_in2": estimate, "factor_range_tons_per_in2": [low, high],
        "factor_source": (f"{MOLDMINDS.publisher}, {MOLDMINDS.title} ({MOLDMINDS.url})" if factor else
                          f"no factor for {material or 'an unnamed resin'}: {RJC.publisher}'s usual {low:g}-{high:g} "
                          f"tons/in2 ({RJC.url}), estimated at {PT.publisher}'s starting {CLAMP_START:g} ({PT.url})"),
        "tons": round(sum(item["tons"] for item in items), 2), "items": items,
        "method": ("projected area (in2) x tonnage factor (tons/in2) x cavities x (1 + safety); the area is the "
                   "part's alone (runners and sprues add to it), the factor a molder's table, not a resin "
                   "supplier's cavity pressure: an estimate for choosing a press, not a mold design"),
    }


def _location(face: dict[str, Any]) -> str | None:
    return face.get("location") or where(face.get("centroid_xyz"))


#: The pull is doubtful where this share of the wall reads zero draft along it (most of it: a box modelled
#: on its side) ...
DOUBTFUL_ZERO_SHARE = 0.5
#: ... or this percentage of the surface is trapped along it: an engineering trigger, no source's (a drafted
#: cup modelled along x reads 42% trapped along z, and a part pulled along its own axis rarely a quarter).
DOUBTFUL_UNDERCUT_PCT = 25.0


def pull_doubtful(draft: dict[str, Any], undercuts: dict[str, Any]) -> tuple[bool, bool]:
    """Whether the pull looks like the wrong one: (most of the wall reads zero draft, a quarter of the surface
    is trapped) -- where either holds on one part, the measurement ranks the pulls (``pull_check``) for the
    hint (an assembly's parts, or a part's several solids, each open their own way: its hint names no pull)."""
    zero = (draft.get("zero_draft_wall_area_mm2") or 0) > 0 and \
        draft["zero_draft_wall_area_mm2"] >= DOUBTFUL_ZERO_SHARE * float(draft.get("wall_area_mm2") or 0.0)
    trapped = float(undercuts.get("candidate_area_pct_of_surface") or 0.0) >= DOUBTFUL_UNDERCUT_PCT
    return zero, trapped


def ranked(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The candidate pulls, best first: the fewest features nothing releases, then the least undercut area, the
    fewest side actions, the least zero-draft wall, the most draft at its least, a flat parting before a stepped
    one. Areas are sampled, so two within a hundredth of the largest wall area (1 mm2 at least) tie."""
    rows = [row for row in rows if "error" not in row]
    tie = max([1.0] + [0.01 * float(row.get("wall_area_mm2") or 0.0) for row in rows])

    def key(row: dict[str, Any]) -> tuple:
        return (row.get("unreleasable_count") or 0, round(float(row.get("undercut_candidate_area_mm2") or 0.0) / tie),
                row.get("side_action_count") or 0, round(float(row.get("zero_draft_wall_area_mm2") or 0.0) / tie),
                -float(row.get("min_wall_draft_deg") or 0.0), row.get("flat_parting") is False)

    return sorted(rows, key=key)


def _pull_hint(report: dict[str, Any], why: str) -> str:
    """The hint where the pull looks wrong: what --candidates ranks first (``pull_check``, measured only then)."""
    rows = ranked(((report.get("pull_check") or {}).get("candidates")) or [])
    if not rows:
        return f"{why}: the pull may be the wrong one -- --candidates ranks the pulls; "
    first = rows[0]
    axis = [float(value) for value in first.get("axis") or (0.0, 0.0, 0.0)]
    along = [float(value) for value in (report.get("draft") or {}).get("pull_axis") or (0.0, 0.0, 0.0)]
    if abs(sum(a * b for a, b in zip(axis, along))) > 0.9999:
        return f"{why}, yet --candidates ranks this pull ({first['pull']}) first: "
    return f"{why}: the pull may be the wrong one -- --candidates ranks {first['pull']} first; "


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    mesh = report.get("mesh") or {}
    if mesh.get("note"):
        found.append(CheckFinding("warning", "several_bodies", mesh["note"], "mesh"))
    bodies = report.get("bodies") or []
    if len(bodies) > 1:
        found.append(CheckFinding("warning", "several_bodies",
                                  f"{len(bodies)} parts: an assembly, not one molded part; each is measured on its "
                                  f"own, none shadows another", "bodies"))
    for body in bodies:
        if isinstance(body, dict) and (body.get("solid_count") or 0) > 1:
            found.append(CheckFinding(
                "warning", "several_bodies",
                f"{body['solid_count']} solids in one part shadow each other: its undercuts, walls and bosses are "
                f"read across them", body.get("owner") or body.get("name") or "bodies",
                "check the molded solid alone (a component model's housing without its contacts)"))
    if candidates:
        return found
    estimate = clamp(report, resolved)
    if estimate is not None:
        report["clamp"] = estimate
    draft = report.get("draft") or {}
    undercuts = report.get("undercuts") or {}
    zero_doubt, trapped_doubt = pull_doubtful(draft, undercuts) if "error" not in draft and "error" not in undercuts \
        else (False, False)
    if (draft.get("zero_draft_wall_area_mm2") or 0) > 0:
        faces = draft.get("largest_zero_draft_faces") or [{}]
        found.append(CheckFinding(
            "warning", "zero_draft_walls",
            f"{draft['zero_draft_wall_area_mm2']:g} mm2 of wall has no draft along the pull (under "
            f"{draft['zero_tol_deg']:g} deg), {draft['zero_draft_face_count']} faces; the largest is "
            f"{faces[0].get('area_mm2', 0):g} mm2", _location(faces[0]),
            (_pull_hint(report, "most of the wall area reads zero draft along this pull") if zero_doubt else "")
            + "draft each of these walls along the pull the part is confirmed to open along"))
    reading = draft.get("min_wall_draft") or {}
    if reading.get("reading_note"):
        # Info: a curved face's reading off its chords, said with its spread; the draft rules judge the figure.
        found.append(CheckFinding("info", "coarse_curved_face", reading["reading_note"],
                                  where(reading.get("location_xyz"))))
    if (undercuts.get("candidate_area_mm2") or 0) > 0:
        faces = undercuts.get("largest_candidate_faces") or [{}]
        counts = ", ".join(f"{undercuts[key]} {words}" for key, words in
                           (("side_action_count", "side action(s)"), ("lifter_count", "lifter(s)"),
                            ("collapsible_core_count", "collapsible core(s)"),
                            ("unreleasable_count", "with no release"),
                            ("unsearched_count", "not searched (the part's release budget spent)"))
                           if undercuts.get(key))
        found.append(CheckFinding(
            "warning", "undercut_candidates",
            f"{undercuts['candidate_area_mm2']:g} mm2 ({undercuts['candidate_area_pct_of_surface']:g}% of the "
            f"surface) does not withdraw along a straight two-half pull, {undercuts['candidate_face_count']} "
            f"faces; the largest is {faces[0].get('area_mm2', 0):g} mm2"
            + (f"; {undercuts['undercut_count']} feature(s): {counts}" if undercuts.get("undercut_count") else ""),
            _location(faces[0]),
            (_pull_hint(report, f"{undercuts['candidate_area_pct_of_surface']:g}% of the surface is trapped along "
                                f"this pull (a quarter or more: an engineering trigger, no source's)")
             + "confirm the pull before budgeting side actions") if trapped_doubt else None))
    if undercuts.get("probe_resolution_note"):
        found.append(CheckFinding("info", "probe_resolution", undercuts["probe_resolution_note"], "undercuts"))
    parting = report.get("parting") or {}
    if parting.get("flat_parting_possible") is False:
        off = [item for item in parting.get("items") or [] if not item.get("on_plane")]
        found.append(CheckFinding(
            "warning", "stepped_parting",
            f"no one flat parting plane takes the outline: {parting.get('off_plane_count', len(off))} silhouette "
            f"piece(s) lie off the best plane at {parting.get('parting_plane_height_mm')} mm along the pull; the "
            f"parting line steps or follows a contour (a costlier mold)",
            (off[0].get("location") or where(off[0].get("xyz"))) if off else "parting"))
    thickness = report.get("thickness") or {}
    if "error" not in thickness and thickness.get("nominal_mm") is None and "items" in thickness:
        found.append(CheckFinding("warning", "thickness_unmeasured",
                                  "no wall thickness was read (an open shell?): the wall rules are not evaluated",
                                  "thickness"))
    material = materials.resolve(resolved.get("material"))
    rules = resolved.get("rules", "generic")
    if rules != "none" and material not in WALL_RANGES:
        found.append(CheckFinding(
            "info", "resin_unknown",
            (f"no --material: " if material is None else f"{material} is not in Protolabs' wall table: ")
            + "the resin's wall range is not evaluated and the clamp force is a range", "material",
            f"give --material ({', '.join(sorted(WALL_RANGES))})"))
    if estimate is not None and estimate["items"]:
        found.append(CheckFinding(
            "info", "clamp_estimate",
            f"clamp force about {estimate['tons']:g} US tons ({sum(i['kN'] for i in estimate['items']):g} kN) for "
            f"{estimate['cavities']} cavit{'y' if estimate['cavities'] == 1 else 'ies'} at "
            f"{estimate['factor_tons_per_in2']:g} tons/in2 (range {estimate['factor_range_tons_per_in2'][0]:g}-"
            f"{estimate['factor_range_tons_per_in2'][1]:g}) plus {CLAMP_SAFETY:.0%}", "clamp"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if candidates:
        rows = ranked(report["pulls"]["candidates"])
        return "pulls best first (undercuts, side actions, zero-draft area, then draft and parting): " + "; ".join(
            f"{row['pull']} {mm(row['undercut_candidate_area_mm2'])} mm2 undercut"
            + (f" ({row.get('undercut_count')} feature(s), {row.get('side_action_count')} side action(s))"
               if row.get("undercut_count") else "")
            + f", {mm(row['zero_draft_wall_area_mm2'])} mm2 zero-draft, min draft {mm(row['min_wall_draft_deg'])} deg"
            + ("" if row.get("flat_parting") is not False else ", stepped parting")
            for row in rows)
    draft, undercuts, projection = report["draft"], report["undercuts"], report["projection"]
    least = (draft.get("min_wall_draft") or {}).get("draft_deg")
    line = (f"along {','.join(f'{value:g}' for value in draft['pull_axis'])}: walls "
            f"{mm(draft['wall_area_mm2'])} mm2, zero-draft {mm(draft['zero_draft_wall_area_mm2'])} mm2, min "
            f"wall draft {mm(least)} deg, undercut candidates {mm(undercuts['candidate_area_mm2'])} mm2, "
            f"projected {mm(projection['projected_area_mm2'])} mm2, depth {mm(projection['depth_along_pull_mm'])} mm")
    thickness = report.get("thickness") or {}
    if thickness.get("nominal_mm") is not None:
        line += f", nominal wall {mm(thickness['nominal_mm'])} mm"
    estimate = report.get("clamp") or {}
    if estimate.get("tons") is not None:
        line += f", clamp ~{mm(estimate['tons'])} tons"
    return line
