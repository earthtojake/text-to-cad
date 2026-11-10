"""Injection molding: its options, rules, findings and summary (``cad._internal.dfm``).

Measured along one pull (``pull``), on exact geometry alone (``cad.build123d._dfm_molding``): a mesh's chords
misread draft, undercuts and walls, so a mesh is refused (``manufacturing._MESH_REFUSED``). The families:

- ``draft``: every wall face's draft and which way it opens (``+pull``, ``-pull``, ``none``, ``split``);
- ``undercuts``: the trapped features, each with what releases it (``side_action`` and its directions and
  stroke, ``lifter``, ``collapsible_core``, ``bump_off`` -- at most ``BUMP_OFF_MM`` deep, stripped as it
  ejects -- ``none``), how deep it is and whether it faces outside or in; the part's slides (its features'
  distinct directions), and the crevices no steel fills, which are no undercut;
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

With ``candidates`` the pulls are ranked (x, y, z and the part's principal axes) instead (``ranked``). A check
of one pull always asks whether another does better (``pull_check``, ``better_pull``): where one traps no more,
needs no more actions and leaves no more wall without draft, and is better on one of them, a warning names it.

The rules (``RULES``) are general practice from published injection molding design guides (cited as the
evidence, not as a shop's limit): recommendations, warnings. Beside them stand the floors, errors -- what
cannot be molded as drawn, or what a general shop sends back: a feature nothing releases, a deep wall with no
draft at all, a wall far outside the resin's range. A floor no guide states is text-to-cad's own and says so
(``_OWN``). A press's or a mold's own limits -- its projected area, its part size, its side actions' travel --
are no rule here: the measurements (``projection``, ``envelope``, ``undercuts``) are compared with them.
"""

from __future__ import annotations

from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, where
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["CLAMP_FACTORS", "DEFAULT_PULL", "MEASURED_FROM", "OPTIONS", "RULES", "WALL_RANGES", "better_pull",
           "clamp", "context", "dominates", "findings", "ranked", "summary", "validate"]

#: ``pull``: None is not given -- measured along ``DEFAULT_PULL``, and said to be the default.
OPTIONS: dict[str, Any] = {"pull": None, "wall_limit": 45.0, "zero_tol": 0.05, "cavities": None}
DEFAULT_PULL = "z"
MEASURED_FROM = ("brep",)  # a mesh's chords misread draft, undercuts and walls: judged on exact geometry alone
_ACCESSED = "2026-11-03"
_VERSION = "2026-11-10"

HUBS = Source("hubs-im", "Protolabs Network (Hubs)", "Injection molding design guide",
              "https://www.hubs.com/guides/injection-molding/", _ACCESSED)
PROTOLABS = Source("protolabs-im", "Protolabs", "Plastic injection molding design guidelines",
                   "https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/",
                   "2026-11-10")
PROTOLABS_WALLS = Source("protolabs-walls", "Protolabs", "Improving part design with uniform wall thickness",
                         "https://www.protolabs.com/resources/design-tips/improving-part-design-with-uniform-wall-thickness/",
                         _ACCESSED)
XOMETRY_RIBS = Source("xometry-ribs", "Xometry", "Plastic ribs for injection-molding design",
                      "https://www.xometry.com/resources/injection-molding/plastic-ribs-for-injection-molding-design/",
                      _ACCESSED)
BUMP_OFFS = Source("protolabs-bumpoff", "Protolabs", "Creating complex undercuts with bumpoffs",
                   "https://www.protolabs.com/resources/design-tips/creating-complex-undercuts-with-bumpoffs/",
                   "2026-11-09")
MOLDMINDS = Source("moldminds-clamp", "Moldminds", "Clamp force calculator (material tonnage factors)",
                   "https://moldminds.com/clamp-force-calculator/", _ACCESSED)
RJC = Source("rjc-tonnage", "RJC Mold", "Injection molding machine tonnage",
             "https://rjcmold.com/guides/injection-molding-machine-tonnage/", _ACCESSED)
PT = Source("pt-tonnage", "Plastics Technology", "Clamp tonnage: more is better, right?",
            "https://www.ptonline.com/columns/clamp-tonnage-more-is-betterright", _ACCESSED)
#: The floors no guide states (``_OWN``): what they cite, so no finding puts text-to-cad's number in a publisher's
#: mouth. Each rule's note says what the floor rests on.
OWN = Source("text-to-cad", "text-to-cad", "its own feasibility floor, no published guide's",
             "https://github.com/earthtojake/text-to-cad", "2026-11-10")

_IN = 25.4
#: Protolabs' recommended wall thickness by resin (its table, in inches, "adapted from
#: manufacturingcenter.com"; read again on 2026-11-10, every row as here), in millimetres, keyed by
#: ``materials``' names. Its rows are resin families: polyethylene's stands for HDPE and LDPE too, and its
#: "Polyester" row for PBT and PETG, the two polyesters ``materials`` names. A resin it has no row for (PC/ABS,
#: TPU, glass-filled nylon, PEEK) has no range here: its walls are not judged by resin, and the check says so.
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
#: The deepest lip (mm) taken as stripped off as the part ejects (a bump-off) -- against the straight pull, or
#: against the slide of a feature no slide frees cleanly: text-to-cad's own figure, no guide's. Protolabs gives
#: none; it says a bump-off works on a flexible resin over a ramped or rounded leading edge (``BUMP_OFFS``).
BUMP_OFF_MM = 0.1


#: How the note of a floor of text-to-cad's own begins: no publisher's number (it cites ``OWN``).
_OWN = "text-to-cad's own floor, no guide's: "
#: A wall with no draft at all (under ``zero_tol``) fails where it runs deeper than this along the pull. The
#: guides only recommend (Protolabs 0.5 deg on vertical faces, Hubs 2 deg) and say what no draft does (Hubs:
#: "Parts with vertical walls (and no draft angle) are most prone to drag marks"); none gives a depth under which
#: none is accepted. The floor is ours: a short undrafted face (a logo's edge, a low rib) is molded every day, a
#: deep one drags its whole way out and sticks.
DRAFT_FLOOR_DEPTH_MM = 10.0
#: A wall fails where it is under this share of the resin's recommended minimum, or over this multiple of its
#: recommended maximum (Protolabs' table gives the recommended range alone: the shares are ours).
WALL_FLOOR_SHARE = 0.5
WALL_CEILING_MULTIPLE = 2.0

#: Hubs' and Protolabs' recommended draft, in their words.
_DRAFT_NOTE = ("Hubs: \"A minimum draft angle of 2\u00b0 is recommended.\" (its 1-2 deg is the extra a textured face "
               "adds); Protolabs: \"Most situations: 2\u00b0\"")
#: Protolabs' draft table, in its words: only its shut-off and texture rows are minimums, so its vertical-face
#: figure is a recommendation (a warning), no feasibility limit.
_DRAFT_MIN_NOTE = ("Protolabs' draft table: \"VERTICAL FACES 0.5\u00b0\", \"MOST SITUATIONS 2\u00b0\"; only its "
                   "\"MINIMUM FOR SHUT OFF 3\u00b0\" and texture rows are labelled minimums: a recommendation, so a "
                   "warning")
#: A wall's draft rules judge a wall's faces: a rib's sides are ``molding.rib_draft``'s (``feature``: the draft
#: item of a rib's side says ``rib`` or ``snap``), one finding for one face's draft.
_WALL_FACE = {"opens": _MOLDED, "feature": ("wall", None)}
_DRAFT_FLOOR_NOTE = (_OWN + f"no draft at all (under --zero-tol) on a face deeper than {DRAFT_FLOOR_DEPTH_MM:g} mm "
                     "along the pull drags on the steel its whole way out; the guides recommend draft (Protolabs "
                     "0.5 deg on vertical faces, Hubs 2 deg) and give no depth under which none is accepted")


def _draft_rules(source: str, least: float, severity: str, preferred: tuple[float, str] | None = None,
                 note: str = "", least_note: str = "") -> tuple[Rule, ...]:
    rules = [
        # The floor: a deep wall, or a deep rib, with no draft at all. Its limit is --zero-tol (``scale_by``).
        Rule("molding.draft_zero", "draft", "draft_deg", "min", 1.0, "deg", "draft of a deep wall", "text-to-cad",
             scale_by="zero_tol_deg", item_when={**_WALL_FACE, "deep": True}, note=_DRAFT_FLOOR_NOTE,
             detail=f"no draft on a wall {{zero_draft_depth_mm:g}} mm deep along the pull, over "
                    f"{DRAFT_FLOOR_DEPTH_MM:g} mm",
             fix="draft this wall: {taper}; " + f"{least:g} deg at least, 2 deg where the design allows"),
        Rule("molding.draft_zero", "ribs", "draft_deg", "min", 1.0, "deg", "draft of a tall rib", "text-to-cad",
             scale_by="zero_tol_deg", item_when={"deep": True}, note=_DRAFT_FLOOR_NOTE,
             detail=f"no draft on a rib {{height_mm:g}} mm tall, over {DRAFT_FLOOR_DEPTH_MM:g} mm",
             fix="draft the rib's sides, the rib thinner toward its tip"),
        Rule("molding.draft_min", "draft", "draft_deg", "min", least, "deg", "wall draft", source,
             severity=severity, item_when=_WALL_FACE, note=least_note,
             fix="draft this wall at least {limit:g} deg: {taper} (more on tall or textured walls)")]
    if preferred:
        value, cited = preferred
        rules.append(Rule("molding.draft", "draft", "draft_deg", "min", value, "deg", "wall draft", cited,
                          severity="warning", item_when=_WALL_FACE, note=note,
                          fix="draft this wall {limit:g} deg if the design allows -- {taper}: it ejects cleanly and "
                              "wears less"))
    return tuple(rules)


def _undercut_rules(source: str) -> tuple[Rule, ...]:
    return (
        Rule("molding.undercut", "undercuts", "trapped_area_mm2", "max", 0.0, "mm2", "undercut area", source,
             severity="warning", item_when={"release": _RELEASED}, detail="{leaning} leaning, {release_said}",
             fix="the undercut needs the side action, lifter or core the finding names (tooling cost): make it pull "
                 "straight -- a pass-through core, a slot, a shut-off -- or keep it and budget the action"),
        Rule("molding.undercut_bump_off", "undercuts", "trapped_area_mm2", "max", 0.0, "mm2", "undercut area",
             "protolabs-bumpoff", severity="warning", item_when={"release": "bump_off"},
             detail="{leaning} leaning, {depth_said}: a {interference_mm:.3g} mm lip over {bump_off_over}, stripped off "
                    f"as the part ejects (a bump-off: {BUMP_OFF_MM:g} mm at most, text-to-cad's own figure); a "
                    "bump-off depends on the resin's flexibility",
             note="a bump-off depends on the resin's flexibility: TPE, unfilled PE or PP, not glass-filled nylon or PC",
             fix="round or ramp the lip's leading edge and mold it in a flexible resin, or open the lip"),
        # A feature whose release was not searched (the part's release budget spent) carries no such figure: it
        # is counted not measured here, never passed.
        Rule("molding.undercut_unreleasable", "undercuts", "unreleasable_area_mm2", "max", 0.0, "mm2", "trapped area",
             source, item_when={"release": ("none", "unknown")},
             detail=f"{{leaning}} leaning, {{depth_said}}: over the {BUMP_OFF_MM:g} mm a bump-off takes "
                    "(text-to-cad's own figure)",
             fix="no slide, lifter or core frees this feature: open it to one side or split the part"),
    )


def _wall_rules() -> tuple[Rule, ...]:
    # A wall's face (``feature``: wall): a rib's and a boss's are judged by their own rules. Both read the face's
    # wall (its area median); its thickest point, a junction's, is thick_section's.
    listed = {"feature": "wall"}
    note = (_OWN + f"under {WALL_FLOOR_SHARE:g} of the resin's recommended minimum, or over {WALL_CEILING_MULTIPLE:g} "
            "times its recommended maximum (Protolabs' table gives the recommended range, no limit); with no resin "
            "of the table named, outside every resin's recommended range")
    thin = min(low for low, _high in WALL_RANGES.values())
    thick = max(high for _low, high in WALL_RANGES.values())
    return (
        Rule("molding.wall_too_thin", "thickness", "thickness_mm", "min",
             {k: WALL_FLOOR_SHARE * v[0] for k, v in WALL_RANGES.items()}, "mm", "wall thickness", "text-to-cad",
             by="resin", when={"resin_listed": True}, item_when=listed, note=note,
             detail=f"{WALL_FLOOR_SHARE:g} of Protolabs' recommended minimum for {{resin}}",
             fix="thicken this wall: it is far under the resin's recommended {wall_range_said}"),
        Rule("molding.wall_too_thin", "thickness", "thickness_mm", "min", thin, "mm", "wall thickness", "text-to-cad",
             when={"resin_listed": False}, item_when=listed, note=note,
             detail="the least recommended minimum of any resin in Protolabs' table; no resin of it was named",
             fix="thicken this wall, or name the resin it is molded in (--material)"),
        Rule("molding.wall_too_thick", "thickness", "thickness_mm", "max",
             {k: WALL_CEILING_MULTIPLE * v[1] for k, v in WALL_RANGES.items()}, "mm", "wall thickness", "text-to-cad",
             by="resin", when={"resin_listed": True}, item_when=listed, note=note,
             detail=f"{WALL_CEILING_MULTIPLE:g} times Protolabs' recommended maximum for {{resin}}",
             fix="core this section out: it is far over the resin's recommended {wall_range_said}"),
        Rule("molding.wall_too_thick", "thickness", "thickness_mm", "max", thick, "mm", "wall thickness",
             "text-to-cad", when={"resin_listed": False}, item_when=listed, note=note,
             detail="the greatest recommended maximum of any resin in Protolabs' table; no resin of it was named",
             fix="core this section out, keeping the wall uniform"),
        Rule("molding.wall_min", "thickness", "thickness_mm", "min", {k: v[0] for k, v in WALL_RANGES.items()}, "mm",
             "wall thickness", "protolabs-im", severity="warning", by="resin", item_when={"feature": "wall"},
             fix="thicken this wall to at least {limit:.3g} mm for the resin, or choose an easier-flowing one"),
        Rule("molding.wall_max", "thickness", "thickness_mm", "max", {k: v[1] for k, v in WALL_RANGES.items()}, "mm",
             "wall thickness", "protolabs-im", severity="warning", by="resin", item_when={"feature": "wall"},
             fix="core this section out to {limit:.3g} mm or less, keeping the wall uniform"),
    )


def _uniform_rules() -> tuple[Rule, ...]:
    return (
        Rule("molding.thick_section", "thickness", "ratio_to_nominal", "max", 1 / 0.6, "ratio",
             "local thickness over the nominal wall", "protolabs-walls", severity="warning",
             fix="core this section out: a wall no thinner than 40-60% of the walls beside it keeps sink away"),
        Rule("molding.boss_wall", "bosses", "wall_ratio", "max", 0.6, "ratio", "boss wall over the wall it stands on",
             "protolabs-walls", severity="warning",
             fix="thin the boss wall to 40-60% of the wall it stands on (core it deeper or narrow it) to stop sink"),
    )


_RIB = {"kind": "rib"}  # a rib's height and spacing: a snap arm (``kind``: snap) is judged by the snap rule
#: Hubs states both, the wall's and the rib's: the rules take the first.
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
                          fix="draft the rib's sides {limit:g} deg or more, the rib thinner toward its tip"))
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
               fix="round this internal corner to {radius_target_mm:.3g} mm or more (at least {limit:g} of its "
                   "{wall_mm:.3g} mm wall): a sharp one concentrates stress and stalls the flow")
_TRANSITION = Rule("molding.wall_transition", "transitions", "transition_ratio", "min", 3.0, "ratio",
                   "thickness transition's length over its change", "hubs-im", severity="warning",
                   fix="taper the change in thickness over at least {limit:g} times the change (a chamfer or fillet)")

RULES = RuleSet(
    "molding", "text-to-cad general rules", _VERSION,
    (*_draft_rules("protolabs-im", 0.5, "warning", (2.0, "hubs-im"), note=_DRAFT_NOTE, least_note=_DRAFT_MIN_NOTE),
     *_undercut_rules("hubs-im"),
     *_wall_rules(), *_uniform_rules(), _TRANSITION,
     *_rib_rules((0.6, "xometry-ribs"), ("height_ratio", 3.0, "hubs-im"), ("base_fillet_ratio", 0.25, "hubs-im"),
                 ("gap_to_wall", 2.5, "xometry-ribs"), (0.5, "xometry-ribs")),
     _SNAP, _BOSS_ROOT, _CORNER),
    (HUBS, PROTOLABS, PROTOLABS_WALLS, XOMETRY_RIBS, BUMP_OFFS, OWN),
    note="general practice from published design guides, no shop's limits: draft (0.5 deg on vertical faces, 2 "
         "deg recommended), a wall table per resin, corner, transition, undercut, snap-fit and root guidance, rib "
         "and boss proportions -- recommendations, warnings. The errors are floors: a feature nothing releases, a "
         f"wall or rib deeper than {DRAFT_FLOOR_DEPTH_MM:g} mm with no draft at all, a wall under "
         f"{WALL_FLOOR_SHARE:g} of the resin's recommended minimum or over {WALL_CEILING_MULTIPLE:g} times its "
         "maximum (text-to-cad's own floors, each rule's note says so). Not judged: the extra draft a textured or a "
         "tall wall takes (Hubs: 1 deg more per 25 mm over 50 mm; 1-2 deg more for texture), a shut-off's draft "
         "(Protolabs: 3 deg at least). A press's and a mold's own limits are compared with the measurements")


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
    low, high = WALL_RANGES.get(material or "", (None, None))
    return {"material": material, "material_class": materials.material_class(material), "resin": material,
            "resin_listed": material in WALL_RANGES,
            "wall_range_said": f"{low:.3g} to {high:.3g} mm" if low else "range",
            "zero_tol_deg": float(resolved.get("zero_tol") if resolved.get("zero_tol") is not None
                                  else OPTIONS["zero_tol"]),
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


def _standing(row: dict[str, Any], tie: float) -> tuple[int, int, int, int, int]:
    """What a pull is compared by: its features nothing releases, its trapped area, its actions (slides, lifters,
    cores), its wall with no draft -- the areas in units of ``tie`` (sampled: two within one tie) -- and a
    parting line that steps. A figure a row does not hold yet (a pull only screened) reads as its best, 0."""
    return (int(row.get("unreleasable_count") or 0), round(float(row.get("undercut_candidate_area_mm2") or 0.0) / tie),
            int(row.get("side_action_count") or 0) + int(row.get("lifter_count") or 0),
            round(float(row.get("zero_draft_wall_area_mm2") or 0.0) / tie), int(row.get("flat_parting") is False))


def dominates(row: dict[str, Any], chosen: dict[str, Any]) -> bool:
    """Whether the pull ``row`` does better than ``chosen``: no worse on any of the five it is compared by
    (``_standing``), better on one. Areas within a hundredth of the larger wall area (1 mm2 at least) tie."""
    tie = max(1.0, 0.01 * max(float(row.get("wall_area_mm2") or 0.0), float(chosen.get("wall_area_mm2") or 0.0)))
    mine, theirs = _standing(row, tie), _standing(chosen, tie)
    return mine != theirs and all(a <= b for a, b in zip(mine, theirs))


def better_pull(chosen: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The pull of ``rows`` that does better than ``chosen`` (``dominates``), the first as ``ranked`` ranks them;
    None where none does. Only a pull measured whole counts (``measured``: full)."""
    found = [row for row in rows if "error" not in row and row.get("measured") == "full" and dominates(row, chosen)]
    return ranked(found)[0] if found else None


def _pull_said(row: dict[str, Any]) -> str:
    """A pull's standing in words: what it traps, what releases that, its wall with no draft."""
    actions = ", ".join(f"{row[key]} {words}" for key, words in (
        ("side_action_count", "side action(s)"), ("lifter_count", "lifter(s) or core(s)"),
        ("unreleasable_count", "with no release")) if row.get(key))
    trapped = (f"{mm(row.get('undercut_candidate_area_mm2'))} mm2 trapped" + (f" ({actions})" if actions else "")
               if row.get("undercut_candidate_area_mm2") else "nothing trapped")
    parting = {True: ", a flat parting", False: ", a stepped parting"}.get(row.get("flat_parting"), "")
    return f"{trapped}, {mm(row.get('zero_draft_wall_area_mm2'))} mm2 of wall with no draft{parting}"


def _axis_text(axis: Any) -> str:
    """A pull's direction as the options name it: ``+z`` along an axis, else its components."""
    values = [float(value) for value in axis or (0.0, 0.0, 1.0)]
    for index, name in enumerate(_AXES):
        if abs(abs(values[index]) - 1.0) < 1e-6:
            return ("+" if values[index] > 0 else "-") + name
    return ",".join(f"{value:g}" for value in values)


def _taper(opens: Any, axis: Any) -> str:
    """Which way a wall's draft leans, for its hint: the end farther along the way its mold half pulls off sets
    back into the material (an outer wall narrows that way, a hole's wall widens)."""
    up = _axis_text(axis)
    down = up[1:] if up.startswith("-") else "-" + up.lstrip("+")
    if opens == "+pull":
        return f"lean it so its end farther along {up} sets back into the material (the mold half forming it pulls off along {up})"
    if opens == "-pull":
        return f"lean it so its end farther along {down} sets back into the material (the mold half forming it pulls off along {down})"
    if opens == "split":
        return "lean each side of the parting line crossing it back into the material, away from the parting line"
    return (f"set its end farther along {up} back into the material above the parting line, its end farther along "
            f"{down} below it")


def _hint_fields(report: dict[str, Any]) -> None:
    """What the rules read of an item beyond its measurement: for their hints (``Rule.fix``), a draft item's
    ``taper`` (which way to lean it) and a corner's ``radius_target_mm`` (the radius the rule asks, in
    millimetres); for the draft floor, whether a wall runs ``deep`` with no draft (``zero_draft_depth_mm`` over
    ``DRAFT_FLOOR_DEPTH_MM`` along the pull) or a rib stands that tall; for an undercut's message, what releases
    it in words (``release_said``)."""
    draft = report.get("draft")
    if isinstance(draft, dict) and "error" not in draft:
        for item in draft.get("items") or ():
            item["taper"] = _taper(item.get("opens"), draft.get("pull_axis"))
            item["deep"] = float(item.get("zero_draft_depth_mm") or 0.0) > DRAFT_FLOOR_DEPTH_MM
    ribs = report.get("ribs")
    if isinstance(ribs, dict) and "error" not in ribs:
        for item in ribs.get("items") or ():
            item["deep"] = float(item.get("height_mm") or 0.0) > DRAFT_FLOOR_DEPTH_MM
    undercuts = report.get("undercuts")
    if isinstance(undercuts, dict) and "error" not in undercuts:
        for item in undercuts.get("items") or ():
            item["release_said"] = _release_said(item)
    corners = report.get("corners")
    if isinstance(corners, dict) and "error" not in corners:
        least = float(_CORNER.limit) if isinstance(_CORNER.limit, (int, float)) else 0.5
        for item in corners.get("items") or ():
            if isinstance(item.get("wall_mm"), (int, float)):
                item["radius_target_mm"] = round(least * float(item["wall_mm"]), 3)


def _release_said(item: dict[str, Any]) -> str:
    """What releases an undercut, in words: its slides and their stroke, a lifter's move, a core's."""
    release = item.get("release")
    travel = f", {mm(item['stroke_mm'])} mm stroke" if item.get("stroke_mm") is not None else ""
    ways = " and ".join(item.get("side_actions") or ())
    if release == "side_action":
        return f"released by {'an angled' if item.get('angled') else 'a'} side action along {ways}{travel}"
    if release == "lifter":
        return f"released by a lifter (or an internal slide) moving {ways}{travel}"
    if release == "collapsible_core":
        return f"released by a collapsible core (or a lifter each way){travel}"
    if release == "unknown":
        return "its release not searched (the part's release budget spent)"
    return "released by nothing"


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    bodies = report.get("bodies") or []
    if len(bodies) > 1:
        found.append(CheckFinding("warning", "several_bodies",
                                  f"{len(bodies)} parts: an assembly, not one molded part; each is measured on its "
                                  f"own, none shadows another", "bodies"))
    touching = report.get("touching") or {}
    touched = {pair.get("part") for pair in touching.get("items") or ()}
    for pair in touching.get("items") or ():
        found.append(CheckFinding(
            "warning", "solids_touching",
            f"{pair['part']}: solids {pair['solids'][0]} and {pair['solids'][1]} touch over "
            f"{pair['contact_area_mm2']:g} mm2 without being fused ({', '.join(pair['faces'][:4])}): one molded part "
            "is one solid -- their contact is no surface of it and is left out of its draft and undercuts",
            pair.get("location"), "fuse them into one solid (`a + b` in build123d) before checking, or check each "
                                   "solid as its own part"))
    for body in bodies:
        if isinstance(body, dict) and (body.get("occurrences") or 1) > 1:
            # Said, never skipped in silence: the document gives a part's geometry where its first occurrence
            # stands, so an occurrence turned another way against the pull is not the part that was measured.
            found.append(CheckFinding(
                "warning", "occurrences_measured_once",
                f"{body.get('owner') or body.get('name')} occurs {body['occurrences']} times and is measured once, where "
                f"its first occurrence stands: an occurrence turned another way against the pull is not judged",
                body.get("owner") or body.get("name") or "bodies",
                "check the part on its own, along the pull its mold opens along"))
    for body in bodies:
        if isinstance(body, dict) and (body.get("solid_count") or 0) > 1 and \
                (body.get("owner") or body.get("name")) not in touched:
            found.append(CheckFinding(
                "warning", "several_bodies",
                f"{body['solid_count']} solids in one part shadow each other: its undercuts, walls and bosses are "
                f"read across them", body.get("owner") or body.get("name") or "bodies",
                "check the molded solid alone (a component model's housing without its contacts)"))
    if candidates:
        return found
    _hint_fields(report)
    estimate = clamp(report, resolved)
    if estimate is not None:
        report["clamp"] = estimate
    draft = report.get("draft") or {}
    undercuts = report.get("undercuts") or {}
    check = report.get("pull_check") or {}
    better = better_pull(check["chosen"], check.get("candidates") or []) if check.get("chosen") else None
    if better is not None:
        # Another pull does better: the one finding that says the pull may be the wrong one.
        axis = ",".join(f"{float(value):g}" for value in better.get("axis") or ())
        here = "this pull" + ("" if report.get("pull_given", True) else f" (the default, {DEFAULT_PULL}: none was given)")
        found.append(CheckFinding(
            "warning", "pull_better",
            f"another pull does better than {here}: along {better['pull']} ({axis}) {_pull_said(better)}; along this "
            f"one {_pull_said(check['chosen'])}", "pull_check",
            f"check it with --pull {axis} (--candidates ranks every pull), or keep this pull if it is the mold's"))
    if (draft.get("zero_draft_wall_area_mm2") or 0) > 0:
        faces = draft.get("largest_zero_draft_faces") or [{}]
        # One cause, one finding: each face is molding.draft_min's (a deep one molding.draft_zero's); this sums
        # them, a fact.
        found.append(CheckFinding(
            "info", "zero_draft_walls",
            f"{draft['zero_draft_wall_area_mm2']:g} mm2 of wall has no draft along the pull (under "
            f"{draft['zero_tol_deg']:g} deg), {draft['zero_draft_face_count']} faces; the largest is "
            f"{faces[0].get('area_mm2', 0):g} mm2 (each face judged by molding.draft_min, a deep one by "
            f"molding.draft_zero)", _location(faces[0]),
            "draft each of these walls along the pull the part is confirmed to open along"))
    if (undercuts.get("candidate_area_mm2") or 0) > 0:
        faces = undercuts.get("largest_candidate_faces") or [{}]
        counts = ", ".join(f"{undercuts[key]} {words}" for key, words in
                           (("side_action_count", "side action(s) (" + ", ".join(
                               undercuts.get("side_action_directions") or ()) + ")"), ("lifter_count", "lifter(s)"),
                            ("collapsible_core_count", "collapsible core(s)"),
                            ("bump_off_count", "bumped off"),
                            ("unreleasable_count", "with no release"),
                            ("unsearched_count", "not searched (the part's release budget spent)"))
                           if undercuts.get(key))
        # One cause, one finding: each feature is molding.undercut's or molding.undercut_unreleasable's; this sums
        # them, a fact.
        found.append(CheckFinding(
            "info", "undercut_candidates",
            f"{undercuts['candidate_area_mm2']:g} mm2 ({undercuts['candidate_area_pct_of_surface']:g}% of the "
            f"surface) does not withdraw along a straight two-half pull, {undercuts['candidate_face_count']} "
            f"faces; the largest is {faces[0].get('area_mm2', 0):g} mm2"
            + (f"; {undercuts['undercut_count']} feature(s): {counts} (each judged by molding.undercut, "
               "molding.undercut_bump_off or molding.undercut_unreleasable)" if undercuts.get("undercut_count") else ""),
            _location(faces[0])))
    if undercuts.get("unsearched_count"):
        found.append(CheckFinding(
            "warning", "undercuts_unsearched",
            f"{undercuts['unsearched_count']} undercut(s) were found but what releases them was not searched (the "
            f"part's release budget spent on the larger ones): whether a slide frees them is not judged",
            "undercuts", "check the part with fewer features at once (the housing without its contacts)"))
    crevices = undercuts.get("crevices") or []
    if crevices:
        first = crevices[0]
        # A fact, not a verdict: the samples that met a crevice say where one is, not every one there is.
        found.append(CheckFinding(
            "info", "crevices",
            f"{len(crevices)} place(s) where two faces stand closer than steel can stand between them (under "
            f"{first.get('gap_under_mm'):g} mm; the largest {' and '.join(first.get('faces') or ())}, over "
            f"{first.get('area_mm2'):g} mm2): no undercut, the mold leaves a web or a knife edge there", first.get("location"),
            "run the one feature into the other (a rib's end into the wall), or stand it clear"))
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
    if material not in WALL_RANGES:
        found.append(CheckFinding(
            "info", "resin_unknown",
            (f"no --material: " if material is None else f"{material} is not in the wall table by resin: ")
            + "the resin's recommended wall range is not evaluated (a wall outside every resin's range fails all the "
              "same) and the clamp force is a range", "material",
            f"give --material ({', '.join(sorted(WALL_RANGES))})"))
    if estimate is not None and estimate["items"]:
        found.append(CheckFinding(
            "info", "clamp_estimate",
            f"clamp force about {estimate['tons']:g} US tons ({sum(i['kN'] for i in estimate['items']):g} kN) for "
            f"{estimate['cavities']} cavit{'y' if estimate['cavities'] == 1 else 'ies'} at "
            f"{estimate['factor_tons_per_in2']:g} tons/in2 (range {estimate['factor_range_tons_per_in2'][0]:g}-"
            f"{estimate['factor_range_tons_per_in2'][1]:g}) plus {CLAMP_SAFETY:.0%}", "clamp"))
    return found


def _ok(family: Any) -> dict[str, Any]:
    """A family as it was measured, or nothing for one that could not be."""
    return family if isinstance(family, dict) and "error" not in family else {}


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if candidates:
        rows = ranked(_ok(report.get("pulls")).get("candidates") or [])
        return "pulls best first (undercuts, side actions, zero-draft area, then draft and parting): " + "; ".join(
            f"{row['pull']} {mm(row['undercut_candidate_area_mm2'])} mm2 undercut"
            + (f" ({row.get('undercut_count')} feature(s), {row.get('side_action_count')} side action(s))"
               if row.get("undercut_count") else "")
            + f", {mm(row['zero_draft_wall_area_mm2'])} mm2 zero-draft, min draft {mm(row['min_wall_draft_deg'])} deg"
            + ("" if row.get("flat_parting") is not False else ", stepped parting")
            for row in rows)
    # A family that could not be measured says "-" here; its own finding says why (``measurement_failed``).
    draft, undercuts, projection = (_ok(report.get(name)) for name in ("draft", "undercuts", "projection"))
    least = (draft.get("min_wall_draft") or {}).get("draft_deg")
    axis = draft.get("pull_axis") or undercuts.get("pull_axis")
    default = "" if report.get("pull_given", True) else " (the default pull)"
    line = (f"along {','.join(f'{value:g}' for value in axis) if axis else resolved.get('pull') or DEFAULT_PULL}"
            f"{default}: walls "
            f"{mm(draft.get('wall_area_mm2'))} mm2, zero-draft {mm(draft.get('zero_draft_wall_area_mm2'))} mm2, min "
            f"wall draft {mm(least)} deg, undercut candidates {mm(undercuts.get('candidate_area_mm2'))} mm2, "
            f"projected {mm(projection.get('projected_area_mm2'))} mm2, depth "
            f"{mm(projection.get('depth_along_pull_mm'))} mm")
    thickness = report.get("thickness") or {}
    if thickness.get("nominal_mm") is not None:
        line += f", nominal wall {mm(thickness['nominal_mm'])} mm"
    estimate = report.get("clamp") or {}
    if estimate.get("tons") is not None:
        line += f", clamp ~{mm(estimate['tons'])} tons"
    return line
