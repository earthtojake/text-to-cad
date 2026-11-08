"""3D printing: its options, rules, findings and summary (``cad._internal.dfm``).

Measured as the part stands on the plate (its lowest point, Z up), for one technology (``technology``):
fused filament (``fdm``), selective laser sintering (``sls``), stereolithography and DLP (``sla``), multi
jet fusion (``mjf``) and metal powder bed fusion (``pbf``: DMLS, SLM). The families (each ``items`` at a
ref, on a mesh at ``x, y, z``): ``solid`` (validity; a mesh's ``mesh``), ``overhangs``, ``bridges``,
``wall_thickness``, ``pins``, ``holes``, ``details`` (embossed and engraved), ``gaps`` (narrow slots in one
part), ``clearances`` (between parts), ``trapped_volumes`` (cavities and their escape holes), ``build_volume``,
``bed`` (plate contact, warping), ``knife_edges`` (convex edges under 45 deg), ``stair_stepping``, ``support_volume``, ``sections`` (thick sections and
cross-sections) and ``scale``; with ``candidates`` the orientations ranked (``orientations``).

The powder processes (SLS, MJF) need no support: their overhangs are facts, never verdicts, and their
trapped powder is. The verdicts are the rules' (``RULES``): general practice, per technology the figure of
the first published design guide that gives one (Protolabs Network's -- it publishes guides for all five --
then Protolabs's, then Xometry's), each rule citing its page as the evidence, not as a printer's or a shop's
limit; each limit is keyed by the technology (a rule gives no limit for a technology no guide covers, and
says so: never a pass). The build volume is the printer's given (``--build-volume``), else a typical
machine of the technology's, assumed and said.
"""

from __future__ import annotations

from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, where
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["BUILD_VOLUMES", "DEFAULT_ANGLE", "DEFAULT_LAYER", "MEASURED_FROM", "OPTIONS", "RULES", "TECHNOLOGIES",
           "angle_limit", "build_volume", "context", "findings", "layer_height", "machine_volume", "summary",
           "validate", "wall_minimum"]

#: The printing technologies: fused filament, selective laser sintering, stereolithography and DLP,
#: multi jet fusion, metal powder bed fusion (DMLS, SLM).
TECHNOLOGIES = ("fdm", "sls", "sla", "mjf", "pbf")
#: The technologies whose loose powder holds the part as it builds: no support, but powder to get out.
POWDER = ("sls", "mjf")
OPTIONS: dict[str, Any] = {"technology": "fdm", "build_volume": None, "angle_limit": None, "samples": 2000,
                           "layer_height": None, "nozzle": None}
MEASURED_FROM = ("brep", "mesh")
#: The overhang angle (from horizontal) each technology counts as needing support when none is given: the
#: rules' (Hubs FDM 45, Hubs SLA 19 from level, Protolabs metal 45 to the plate; powder none).
DEFAULT_ANGLE = {"fdm": 45.0, "sla": 19.0, "sls": 0.0, "mjf": 0.0, "pbf": 45.0}
#: The layer height each technology's stair-stepping is measured with when none is given, mm: FDM's common
#: 0.2, SLA's 0.1 standard (Xometry), SLS's 0.1, MJF's 0.08 (Hubs), metal's 0.03 (Protolabs, 20 to 30 um).
DEFAULT_LAYER = {"fdm": 0.2, "sla": 0.1, "sls": 0.1, "mjf": 0.08, "pbf": 0.03}
#: FDM's horizontal round holes print unsupported up to this diameter, mm (their arch stands layer on layer
#: but the crown's last few): above it ``printing.horizontal_hole`` warns. The owner's figure -- Hubs's FDM
#: guide gives none, only that support in a horizontal hole is hard to remove and that turning the part 90
#: deg removes it.
HORIZONTAL_HOLE_MM = 10.0
#: What a finding on an assembly measured: the parts as printed together, where they stand.
IN_PLACE = ("the check measures the parts as printed together, in place (print-in-place); a part printed on its "
            "own is checked by its own id")
#: Materials that warp on an FDM plate (shrinking as they cool): a long flat contact is a risk.
WARP_PRONE = ("abs", "nylon", "nylon_gf", "pc", "pc_abs", "pp", "peek", "pei", "pom", "pbt")

_ACCESSED = "2026-11-03"
#: The rules' own version (``RuleSet.version``), bumped when a rule changes.
_VERSION = "2026-11-08"


def _src(ident: str, publisher: str, title: str, url: str) -> Source:
    return Source(ident, publisher, title, url, _ACCESSED)


HUBS = "Protolabs Network (Hubs)"
#: The source of a rule that is text-to-cad's own (no guide states it): ``printing.knife_edge``,
#: ``printing.horizontal_hole``.
OWN = "text-to-cad-own"
SOURCES = {source.id: source for source in (
    _src("hubs-thin-walls", HUBS, "DFM tips for 3D printed parts with thin walls",
         "https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/"),
    _src("hubs-geometry", HUBS, "3D printing geometry restrictions",
         "https://www.hubs.com/knowledge-base/3d-printing-geometry-restrictions/"),
    _src("hubs-fdm", HUBS, "How to design parts for FDM 3D printing",
         "https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/"),
    _src("hubs-sla", HUBS, "How to design parts for SLA 3D printing",
         "https://www.hubs.com/knowledge-base/how-design-parts-sla-3d-printing/"),
    _src("hubs-sls", HUBS, "How to design parts for SLS 3D printing",
         "https://www.hubs.com/knowledge-base/how-design-parts-sls-3d-printing/"),
    _src("hubs-mjf", HUBS, "How to design parts for MJF 3D printing",
         "https://www.hubs.com/knowledge-base/how-to-design-parts-for-mjf/"),
    _src("hubs-metal", HUBS, "Metal 3D printing design guide",
         "https://www.hubs.com/knowledge-base/how-design-parts-metal-3d-printing/"),
    _src("protolabs-toolkit", "Protolabs", "Design for 3D printing toolkit",
         "https://www.protolabs.com/resources/design-for-3d-printing-toolkit/"),
    _src("protolabs-metal", "Protolabs", "Getting started with metal additive manufacturing",
         "https://www.protolabs.com/resources/design-tips/how-to-design-and-manufacture-metal-3d-printed-parts/"),
    _src("protolabs-7mistakes", "Protolabs", "7 mistakes to avoid when designing 3D-printed parts",
         "https://www.protolabs.com/resources/design-tips/7-mistakes-to-avoid-when-designing-3d-printed-parts/"),
    _src("xometry-fdm", "Xometry", "FDM 3D printing mini guide",
         "https://www.xometry.com/resources/3d-printing/mini-guide-fdm-3d-printing/"),
    _src("xometry-sla", "Xometry (Xometry Pro)", "Quick design reference for SLA",
         "https://xometry.pro/en/3d-printing-design-guide/quick-guide/stereolithography/"),
    _src("xometry-3dp", "Xometry", "3D printing service: general guidelines",
         "https://www.xometry.com/capabilities/3d-printing-service/"),
    _src("xometry-guide", "Xometry (Xometry Pro)", "Ultimate 3D printing design guide",
         "https://xometry.pro/en-uk/3d-printing-design-guide/"),
    # a rule no fetched guide states: text-to-cad's own figure, said as such in every verdict of it
    Source(OWN, "text-to-cad", "text-to-cad's own figure; no fetched guide states one",
           "https://github.com/earthtojake/text-to-cad/blob/main/packages/cad/src/cad/_internal/dfm/README.md",
           _VERSION),
)}

#: A typical machine per technology, mm, and the source it is read from: the build volume the fit is
#: measured against when ``build_volume`` is not given (Hubs's typical machine: a desktop printer for FDM and
#: SLA), assumed and said in every verdict of it.
BUILD_VOLUMES: dict[str, tuple[tuple[float, float, float], str]] = {
    "fdm": ((200, 200, 200), "hubs-geometry"), "sla": ((145, 145, 175), "hubs-geometry"),
    "sls": ((300, 300, 300), "hubs-geometry"), "mjf": ((380, 285, 380), "hubs-geometry"),
    "pbf": ((250, 150, 150), "hubs-geometry")}

# --- the rules ----------------------------------------------------------------------------------------------
# Each rule: (technology, limit, source, severity) rows of one figure. One Rule per source (a rule cites one
# page), its limit keyed by technology.

_SUPPORT_KINDS = ("slope", "ceiling", "cantilever")  # overhangs a bridge or a hole's arch does not cover


Row = tuple[str, float, str, str, str]  # technology, limit, source, severity, the source's sentence


def _rules(rid: str, family: str, field: str, op: str, unit: str, what: str, rows: list[Row],
           fix: str, item_when: dict[str, Any] | None = None, note: str = "", when: dict[str, Any] | None = None,
           detail: str = "") -> list[Rule]:
    """One Rule per (source, severity) of ``rows``, keyed by technology; its note the rule's own (``note``) and
    the sentences its rows cite. It applies where the technology is one its rows name, or, given ``when``, where
    ``when`` holds: a technology no row names then has no limit there (``not_evaluated``, as the selector
    has it), whichever variant applies."""
    groups: dict[tuple[str, str], tuple[dict[str, float], list[str]]] = {}
    for technology, limit, source, severity, said in rows:
        limits, notes = groups.setdefault((source, severity), ({}, [note] if note else []))
        limits[technology] = float(limit)
        if said and said not in notes:
            notes.append(said)
    return [Rule(rid, family, field, op, limits, unit, what, source, severity=severity, by="technology",
                 when=when if when is not None else {"technology": tuple(limits)}, item_when=item_when or {}, fix=fix,
                 note="; ".join(notes), detail=detail)
            for (source, severity), (limits, notes) in groups.items()]


def _overhang(rows: list[Row], kinds_by_tech: dict[str, tuple[str, ...]]) -> list[Rule]:
    found = []
    for technology, limit, source, severity, said in rows:
        found.append(Rule("printing.overhang_angle", "overhangs", "angle_deg", "min", {technology: limit}, "deg",
                          "down-facing surface angle from horizontal", source, severity=severity, by="technology",
                          when={"technology": technology},
                          item_when={"kind": kinds_by_tech[technology], "counted": True},
                          fix="support it, chamfer it to at least {limit:g} deg from horizontal, or turn the part",
                          note=said))
    return found


_KINDS = {"fdm": _SUPPORT_KINDS, "sla": _SUPPORT_KINDS, "pbf": (*_SUPPORT_KINDS, "bridge")}
_FIX_WALL = "thicken it to at least {limit:g} mm"


def _general() -> tuple[Rule, ...]:
    rows: dict[str, list[Row]] = {key: [] for key in (
        "wall_s", "wall_u", "hole", "pin", "pin_aspect", "overhang", "bridge", "cantilever", "hhole", "clear", "gap",
        "escape_n", "escape_d", "hollow", "fit", "emboss", "engrave_d", "engrave_w", "warp", "section", "hround")}

    def add(key: str, technology: str, limit: float, source: str, severity: str, said: str = "") -> None:
        # the first source to give a technology a figure wins (Hubs, then Protolabs, then Xometry); a source may
        # give one a recommendation and a limit (Hubs SLA holes: a warning at 0.8, an error at 0.5)
        if any(row[0] == technology and row[2] != source for row in rows[key]):
            return
        rows[key].append((technology, limit, source, severity, said))

    for tech, supported, free in (("fdm", 0.8, 0.8), ("sla", 0.5, 1.0), ("sls", 0.8, 1.0), ("mjf", 0.7, 1.0),
                                  ("pbf", 0.4, 0.8)):
        add("wall_s", tech, supported, "hubs-thin-walls", "error")
        add("wall_u", tech, free, "hubs-thin-walls", "error")
    # Hubs SLA: holes "less than 0.8mm ... may close off" (a risk), its table's "Minimum diameter of 0.5mm"
    add("hole", "sla", 0.8, "hubs-sla", "warning", "holes less than 0.8 mm may close off")
    add("hole", "sla", 0.5, "hubs-sla", "error", "minimum diameter of 0.5 mm")
    add("hole", "sls", 1.5, "hubs-sls", "error", "all holes should be larger than 1.5 mm")
    add("hole", "pbf", 1.5, "hubs-metal", "error", "minimum hole diameter DMLS/SLM: 1.5 mm")
    # no FDM pin row: Hubs FDM says pins under 5 mm "can be made up of only perimeter prints", no minimum
    add("pin", "sls", 0.8, "hubs-sls", "warning", "a minimum of 0.8 mm is recommended")
    add("pin", "mjf", 0.5, "hubs-mjf", "warning", "minimum feature size 0.5 mm")
    add("pin", "pbf", 0.6, "hubs-metal", "error", "minimum feature size DMLS/SLM 0.6 mm")
    add("pin_aspect", "pbf", 8.0, "hubs-metal", "warning", "maximum aspect ratio 8:1")
    add("overhang", "fdm", 45.0, "hubs-fdm", "warning", "overhangs up to 45 deg print without support")
    add("overhang", "sla", 19.0, "hubs-sla", "warning", "at least 19 deg from level")
    add("bridge", "fdm", 5.0, "hubs-fdm", "warning")
    add("bridge", "sla", 21.0, "hubs-sla", "warning")
    add("cantilever", "sla", 1.0, "hubs-sla", "warning")
    add("cantilever", "pbf", 0.5, "hubs-metal", "warning")
    add("clear", "sla", 0.5, "hubs-sla", "warning")
    add("clear", "sls", 0.3, "hubs-sls", "warning")
    add("clear", "mjf", 0.9, "hubs-mjf", "warning")
    add("escape_n", "sla", 1, "hubs-sla", "error")
    add("escape_d", "sla", 3.5, "hubs-sla", "warning")
    add("escape_d", "sls", 3.5, "hubs-sls", "warning")
    add("hollow", "sla", 2.0, "hubs-sla", "warning")
    for tech in TECHNOLOGIES:
        add("fit", tech, 1.0, "hubs-geometry", "error")
    add("emboss", "sla", 0.1, "hubs-sla", "warning")
    add("emboss", "sls", 1.0, "hubs-sls", "warning")
    add("emboss", "pbf", 0.4, "hubs-metal", "warning")
    add("engrave_d", "sla", 0.4, "hubs-sla", "warning")
    add("engrave_d", "sls", 1.0, "hubs-sls", "warning")
    add("engrave_w", "sla", 0.4, "hubs-sla", "warning")
    add("engrave_w", "pbf", 0.4, "hubs-metal", "warning")
    add("section", "pbf", 10.0, "hubs-metal", "warning")
    # Hubs's SLS escape-hole figure, and the need for one per cavity, for the other powder beds: their loose
    # powder is trapped the same way (the rules' own reading, no page says it for them).
    add("escape_n", "sls", 1, "hubs-sls", "error")
    add("escape_n", "mjf", 1, "hubs-sls", "error")
    add("escape_n", "pbf", 1, "hubs-sls", "error")
    add("escape_d", "mjf", 3.5, "hubs-sls", "warning")
    add("escape_d", "pbf", 3.5, "hubs-sls", "warning")
    # text-to-cad's own threshold for FDM's horizontal holes (HORIZONTAL_HOLE_MM): no guide gives one
    add("hround", "fdm", HORIZONTAL_HOLE_MM, OWN, "warning")
    for tech, wall in (("sla", 0.305), ("sls", 0.762), ("mjf", 0.508), ("pbf", 0.381)):
        add("wall_s", tech, wall, "protolabs-toolkit", "error")
        add("wall_u", tech, wall, "protolabs-toolkit", "error")
    for tech, gap in (("sla", 0.635), ("sls", 0.762), ("mjf", 0.508), ("pbf", 0.635)):
        add("gap", tech, gap, "protolabs-toolkit", "error")
    add("hole", "sla", 0.508, "protolabs-7mistakes", "error")
    add("hole", "pbf", 0.635, "protolabs-7mistakes", "error")
    # the rules keep Protolabs's 45 for metal: Hubs's metal guide lists "maximum overhang angle DMLS/SLM: 50
    # deg" without saying from which axis, so no Hubs row stands for it
    add("overhang", "pbf", 45.0, "protolabs-metal", "warning", "avoid overhangs less than 45 deg; Hubs metal "
        "lists 50 deg, its reference unstated, and is not used")
    add("cantilever", "pbf", 0.5, "protolabs-metal", "warning")
    add("hhole", "pbf", 8.0, "protolabs-metal", "warning")
    add("clear", "pbf", 0.635, "protolabs-toolkit", "warning")
    for tech in ("sls", "mjf"):
        add("warp", tech, 177.8, "protolabs-7mistakes", "warning")
    for tech in ("sla", "sls", "mjf", "pbf"):
        add("fit", tech, 1.0, "protolabs-toolkit", "error")
        add("emboss", tech, 0.3048, "protolabs-toolkit", "warning")
    add("wall_s", "fdm", 1.2, "xometry-fdm", "warning", "recommended at least 1.2-1.5 mm for supporting walls")
    add("wall_u", "fdm", 1.2, "xometry-fdm", "warning", "recommended at least 1.2-1.5 mm for supporting walls")
    add("hole", "fdm", 1.0, "xometry-fdm", "warning", "greater than 0.04 in (1 mm) to retain a circular shape")
    add("emboss", "fdm", 1.0, "xometry-fdm", "warning")
    add("fit", "fdm", 1.0, "xometry-fdm", "error")
    add("wall_s", "sla", 0.4, "xometry-sla", "error")
    add("wall_u", "sla", 0.6, "xometry-sla", "error")
    add("gap", "sla", 0.5, "xometry-sla", "error")
    add("hole", "sla", 0.75, "xometry-sla", "error")
    add("pin", "sla", 0.5, "xometry-sla", "error")
    add("emboss", "sla", 0.3, "xometry-sla", "warning")
    add("engrave_d", "sla", 0.5, "xometry-sla", "warning")
    add("bridge", "sla", 20.0, "xometry-sla", "warning")
    add("cantilever", "sla", 1.0, "xometry-sla", "warning")
    add("clear", "sla", 0.5, "xometry-sla", "warning")
    add("fit", "sla", 1.0, "xometry-sla", "error")
    for tech in ("fdm", "sls", "mjf", "pbf"):
        add("clear", tech, 0.762, "xometry-3dp", "warning", "clearance between features: at least 0.030 in")
        # FDM's: the general line, no FDM limit -- a warning
        add("gap", tech, 0.762, "xometry-3dp", "warning" if tech == "fdm" else "error",
            "clearance between features: at least 0.030 in")
    for tech in ("sls", "mjf", "pbf"):
        add("wall_s", tech, 0.508, "xometry-3dp", "error")
        add("wall_u", tech, 0.508, "xometry-3dp", "error")
    for tech in ("sls", "mjf"):
        add("fit", tech, 1.0, "xometry-guide", "error")
    found: list[Rule] = []
    found += _rules("printing.wall_supported", "wall_thickness", "thickness_mm", "min", "mm",
                    "supported wall thickness", rows["wall_s"], _FIX_WALL, {"supported": True},
                    "a wall joined to the part on two or more sides")
    found += _rules("printing.wall_unsupported", "wall_thickness", "thickness_mm", "min", "mm",
                    "unsupported wall thickness", rows["wall_u"], _FIX_WALL + ", or join it to the part on a second side",
                    {"supported": False}, "a wall joined to the part on one side or none")
    found += _rules("printing.wall", "wall_thickness", "thickness_mm", "min", "mm",
                    "wall thickness (a mesh: whether supported is not known, judged as supported)", rows["wall_s"],
                    _FIX_WALL, {"supported": None})
    found += _rules("printing.hole_diameter", "holes", "diameter_mm", "min", "mm", "hole diameter", rows["hole"],
                    "open it to at least {limit:g} mm, or drill it after printing")
    found += _rules("printing.pin_diameter", "pins", "diameter_mm", "min", "mm", "pin diameter", rows["pin"],
                    "thicken the pin to at least {limit:g} mm")
    found += _rules("printing.pin_aspect", "pins", "aspect_ratio", "max", "ratio", "pin height to diameter",
                    rows["pin_aspect"], "shorten or thicken it to at most {limit:g}:1")
    found += _overhang(rows["overhang"], _KINDS)
    found += _rules("printing.bridge_length", "bridges", "length_mm", "max", "mm", "bridge span", rows["bridge"],
                    "add a support or a pillar so no span exceeds {limit:g} mm", {"kind": "bridge"})
    found += _rules("printing.cantilever_length", "bridges", "length_mm", "max", "mm", "unsupported overhang reach",
                    rows["cantilever"], "support it or shorten it to {limit:g} mm", {"kind": "cantilever"})
    found += _rules("printing.horizontal_hole_diameter", "holes", "diameter_mm", "max", "mm",
                    "horizontal hole diameter", rows["hhole"],
                    "give it a teardrop or diamond top, or keep it to {limit:g} mm",
                    {"orientation": "horizontal", "teardrop": False})
    found += _rules("printing.horizontal_hole", "holes", "diameter_mm", "max", "mm", "horizontal round hole diameter",
                    rows["hround"], "give it a teardrop or flat top, or turn the part so the hole stands vertical: "
                    "above {limit:g} mm its crown sags", {"orientation": "horizontal", "teardrop": False},
                    "text-to-cad's own threshold: Hubs FDM gives no diameter, only that a horizontal hole's support "
                    "is hard to remove and turning the part 90 deg removes it",
                    detail="text-to-cad's own figure: no fetched guide states one")
    found += _rules("printing.clearance", "clearances", "distance_mm", "min", "mm", "clearance between parts",
                    rows["clear"], "open the clearance to at least {limit:g} mm (parts printed together fuse); "
                    + IN_PLACE)
    found += _rules("printing.gap", "gaps", "gap_mm", "min", "mm", "gap between faces", rows["gap"],
                    "open the gap to at least {limit:g} mm or close it")
    found += _rules("printing.escape_holes", "trapped_volumes", "escape_holes", "min", "count",
                    "escape holes of a cavity", rows["escape_n"],
                    "add an escape hole of at least 3.5 mm (two, opposite, drain best), or fill the cavity")
    found += _rules("printing.escape_hole_diameter", "trapped_volumes", "min_escape_hole_mm", "min", "mm",
                    "smallest escape hole of a cavity", rows["escape_d"], "open it to at least {limit:g} mm")
    found += _rules("printing.hollow_wall", "trapped_volumes", "min_wall_mm", "min", "mm",
                    "wall around a hollow", rows["hollow"], "thicken the hollow's wall to at least {limit:g} mm")
    # the machine given (--build-volume) is the printer's: a part over it is not made, an error; the assumed
    # typical machine is no printer of the user's: a warning that names it
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (best axis orientation)", rows["fit"],
                    "split the part, or print it on a larger machine", when={"machine_given": True},
                    detail="against the {machine} mm machine given")
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (best axis orientation)",
                    [(*row[:3], "warning", row[4]) for row in rows["fit"]],
                    "give the machine it prints on (--build-volume XxYxZ), or split the part",
                    when={"machine_given": False},
                    detail="against an assumed typical {technology} machine, {machine} mm: give --build-volume")
    found += _rules("printing.emboss_height", "details", "height_mm", "min", "mm", "embossed detail height",
                    rows["emboss"], "raise it to at least {limit:g} mm", {"kind": "emboss"})
    found += _rules("printing.engrave_depth", "details", "height_mm", "min", "mm", "engraved detail depth",
                    rows["engrave_d"], "cut it to at least {limit:g} mm deep", {"kind": "engrave"})
    found += _rules("printing.engrave_width", "details", "width_mm", "min", "mm", "engraved detail width",
                    rows["engrave_w"], "widen it to at least {limit:g} mm", {"kind": "engrave"})
    found += _rules("printing.warp_length", "build_volume", "max_dimension_mm", "max", "mm", "part length",
                    rows["warp"], "keep walls near a uniform 3.2 mm and hollow thick sections; parts this long warp")
    # text-to-cad's own rule (no guide defines a knife edge), a warning: the tip prints rounded (Hubs SLS: "a
    # radius of less than 0.4mm on a design is printed as 0.4mm") and the part is still made
    found += _rules("printing.knife_edge", "knife_edges", "thickness_mm", "min", "mm",
                    "material at a knife edge (a convex edge under 45 deg)",
                    [(technology, limit, OWN, "warning", "") for technology, limit, *_ in rows["wall_u"]],
                    "blunt it -- a flat or round at least {limit:g} mm across -- or open its angle to 45 deg or more",
                    note="the material thins to nothing at an acute edge: judged against the unsupported-wall "
                         "minimum; the tip prints rounded (Hubs SLS: a radius under 0.4 mm prints as 0.4 mm)",
                    detail="text-to-cad's own figure: no fetched guide states one; the tip prints rounded")
    found += _rules("printing.section_thickness", "sections", "thickness_mm", "max", "mm", "solid section thickness",
                    rows["section"], "hollow or lattice it under {limit:g} mm: thick metal sections warp")
    return tuple(found)


def _ruled() -> RuleSet:
    rules = _general()
    cited = sorted({rule.source for rule in rules} | {source for _, source in BUILD_VOLUMES.values()})
    return RuleSet("printing", "text-to-cad general rules", _VERSION, rules, tuple(SOURCES[ident] for ident in cited),
                   note="general practice: per technology the first published design guide's figure (Hubs, then "
                        "Protolabs, then Xometry); the build volume the printer's given, else a typical machine "
                        "(Hubs's: a desktop FDM or SLA printer), assumed; no printer's or shop's own limits",
                   selector="technology")


RULES = _ruled()


# --- options ------------------------------------------------------------------------------------------------


def angle_limit(resolved: dict[str, Any]) -> float:
    """The overhang angle the check counts support for: the one given, else the technology's."""
    given = resolved.get("angle_limit")
    return float(given) if given is not None else DEFAULT_ANGLE[resolved["technology"]]


def wall_minimum(resolved: dict[str, Any]) -> float | None:
    """The rules' unsupported-wall minimum for the technology: what a knife edge's thin depth is measured
    against."""
    for rule in RULES.rules:
        if rule.id == "printing.wall_unsupported":
            limit = rule.limit_for({"technology": resolved["technology"]})
            if limit is not None:
                return limit
    return None


def layer_height(resolved: dict[str, Any]) -> float:
    given = resolved.get("layer_height")
    return float(given) if given is not None else DEFAULT_LAYER[resolved["technology"]]


def machine_volume(resolved: dict[str, Any]) -> dict[str, Any]:
    """The build volume the fit is measured against: ``build_volume`` given, else a typical machine of the
    technology's (``BUILD_VOLUMES``), assumed."""
    if resolved.get("build_volume") is not None:
        return {"volume_mm": list(build_volume(resolved["build_volume"])), "origin": "given"}
    volume, source = BUILD_VOLUMES[resolved["technology"]]
    return {"volume_mm": [float(value) for value in volume], "origin": f"assumed ({SOURCES[source].url})"}


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if resolved["technology"] not in TECHNOLOGIES:
        raise ArgumentRefused(f"--technology is one of {', '.join(TECHNOLOGIES)}, not {resolved['technology']!r}")
    given = resolved.get("angle_limit")
    if given is not None and not 0.0 <= float(given) <= 90.0:
        raise ArgumentRefused(f"--angle-limit is an angle in degrees from 0 to 90, not {given}")
    if int(resolved["samples"]) < 1:
        raise ArgumentRefused(f"--samples is a count of at least 1, not {resolved['samples']}")
    for name in ("layer_height", "nozzle"):
        if resolved.get(name) is not None and not float(resolved[name]) > 0:
            raise ArgumentRefused(f"--{name.replace('_', '-')} is a length in millimetres above 0, not {resolved[name]}")
    if resolved.get("nozzle") is not None and resolved["technology"] != "fdm":
        raise ArgumentRefused(f"--nozzle is FDM's (a filament printer's nozzle), not {resolved['technology']}'s")
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
        raise ArgumentRefused(f"--build-volume is three lengths in millimetres, X x Y x Z (256x256x256), not {text!r}")
    return values  # type: ignore[return-value]


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    machine = machine_volume(resolved)
    return {"technology": resolved["technology"], "material": material,
            "material_class": materials.material_class(material), "angle_limit": angle_limit(resolved),
            "layer_height": layer_height(resolved),
            # the build volume's: given (an error to pass it) or a typical machine assumed (a warning naming it)
            "machine_given": machine["origin"] == "given",
            "machine": " x ".join(f"{value:g}" for value in machine["volume_mm"])}


# --- findings and summary -------------------------------------------------------------------------------------


def _ok(family: Any) -> dict[str, Any]:
    return family if isinstance(family, dict) and "error" not in family else {}


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    technology = resolved["technology"]
    mesh = _ok(report.get("mesh"))
    if mesh:
        if mesh.get("watertight") is False:
            found.append(CheckFinding("warning", "not_watertight", "the mesh is not watertight (holes or open edges): "
                                      "a slicer may misread it, and its volume, walls, cavities and support are "
                                      "measured of an open surface -- read every figure below with that",
                                      "mesh", "repair the mesh, or export it again from the model"))
        if (mesh.get("body_count") or 0) > 1:
            found.append(CheckFinding("info", "several_bodies", f"{mesh['body_count']} separate bodies: walls are "
                                      "measured per body", "mesh"))
        overlap = _ok(report.get("gaps")).get("overlap")
        if overlap:
            found.append(CheckFinding("warning", "mesh_overlap", f"faces lie on faces {overlap['gap_mm']:g} mm apart "
                                      f"({overlap['samples']} triangle(s)): doubled or overlapping triangles, a "
                                      "defect of the mesh, not a gap -- a slicer may misread it", where(overlap["xyz"]),
                                      "repair the mesh, or export it again from the model"))
    solid = _ok(report.get("solid"))
    for item in solid.get("items") or ():
        if item.get("closed") is False:
            found.append(CheckFinding("warning", "not_watertight", f"{item['part']} is not closed (an open shell): "
                                      "a slicer cannot tell its inside", item.get("location")))
        if item.get("sound") is False:
            found.append(CheckFinding("warning", "not_sound", f"{item['part']} fails the kernel's validity check "
                                      f"({', '.join(item.get('issues') or ['invalid'])}): a slicer may misread it",
                                      item.get("location"), "rebuild the faulty feature; export the STEP again"))
    if (solid.get("body_count") or 0) > 1:
        found.append(CheckFinding("info", "several_bodies", f"{solid['body_count']} solids in {solid['part_count']} "
                                  "part(s): each is measured on its own, their clearances between", "solid"))
    if candidates:
        return found
    overhangs = _ok(report.get("overhangs"))
    parts = (solid.get("part_count") or 0) if solid else (mesh.get("body_count") or 0)
    if (overhangs.get("down_facing_area_below_limit_mm2") or 0) > 0:
        faces = overhangs.get("largest_faces_below_limit") or [{}]
        assembled = f"; {IN_PLACE}" if parts > 1 else ""
        found.append(CheckFinding(
            "warning" if technology not in POWDER else "info", "overhangs",
            f"{overhangs['down_facing_area_below_limit_mm2']:g} mm2 ({overhangs['down_facing_area_below_limit_pct']:g}%"
            f" of the surface) faces down at under {overhangs['angle_limit_used_deg']:g} deg from horizontal, off "
            f"the plate, {overhangs['face_count_below_limit']} {'faces' if solid else 'triangles'}{assembled}",
            faces[0].get("location") or where(faces[0].get("location_xyz")),
            "support it, chamfer the undersides to the angle or steeper, or turn the part (--candidates ranks the "
            "orientations; turn it in the model)" if technology not in POWDER else None))
    # a face on the plate's edge that faces down under the limit (a 45 deg chamfer there is the cure, not one)
    edge = [item for item in overhangs.get("items") or ()
            if item.get("kind") == "plate_edge" and (item.get("area_below_limit_mm2") or 0) > 0]
    if edge and technology in ("fdm", "sla"):
        found.append(CheckFinding("info", "plate_edge_round", f"{len(edge)} rounded or sloped face(s) meet the plate "
                                  f"facing down: they sag on the first layers", edge[0].get("location"),
                                  "a 45 deg chamfer on the edges that touch the plate prints clean"))
    walls = report.get("wall_thickness") or {}
    if isinstance(walls, dict) and walls.get("note"):
        found.append(CheckFinding("info", "walls_not_measured", walls["note"], "wall_thickness"))
    trapped = _ok(report.get("trapped_volumes"))
    # an open mesh has no inside: the voxels' "voids" in it are its holes' artefacts
    if technology in ("fdm",) and not (mesh and mesh.get("watertight") is False):
        for item in trapped.get("items") or ():
            if item.get("sealed"):
                found.append(CheckFinding("info", "internal_void", f"a sealed void of {item['volume_mm3']:g} mm3: "
                                          "FDM prints it as it does infill",
                                          item.get("location") or where(item.get("xyz")) or "trapped_volumes"))
    bed = _ok(report.get("bed"))
    if bed and technology in ("fdm", "sla") and not (bed.get("contact_area_mm2") or 0) > 0:
        found.append(CheckFinding("warning", "no_bed_contact", "nothing flat rests on the plate: the part stands on "
                                  "an edge or a point", "bed", "add a flat face to stand on, or turn the part"))
    material = materials.resolve(resolved.get("material"))
    if bed and technology == "fdm" and material in WARP_PRONE and (bed.get("contact_length_mm") or 0) > 0:
        found.append(CheckFinding("warning", "warping_risk", f"{material} warps as it cools, and "
                                  f"{bed['contact_length_mm']:g} mm of flat bottom rests on the plate",
                                  (bed.get("items") or [{}])[0].get("location") or "bed",
                                  "print with an enclosure and a brim, round the bottom corners, or split long flats"))
    if bed and technology == "fdm" and bed.get("holes_on_plate"):
        found.append(CheckFinding("info", "elephant_foot", f"{bed['holes_on_plate']} hole(s) open on the plate: the "
                                  "first layers spread and close them a little", "bed",
                                  "a 0.3-0.5 mm chamfer at the hole's mouth keeps it to size"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    if candidates:
        rows = _ok(report.get("orientations")).get("candidates") or []
        return "orientations ranked (turn the part in its model with the rotation given): " + "; ".join(
            f"{row['orientation']} {row.get('rotate', '')} score {row.get('score', 0):g}: support "
            f"{mm(row.get('support_volume_mm3'))} mm3, "
            f"{mm(row['build_height_mm'])} mm tall" for row in rows)
    body = _ok(report.get("mesh")) or _ok(report.get("solid"))
    overhangs, walls = _ok(report.get("overhangs")), _ok(report.get("wall_thickness"))
    support = _ok(report.get("support_volume"))
    return (f"{resolved['technology']}: {mm(body.get('volume_mm3'))} mm3, {body.get('body_count')} body(ies); overhangs "
            f"under {mm(overhangs.get('angle_limit_used_deg'))} deg {mm(overhangs.get('down_facing_area_below_limit_mm2'))} "
            f"mm2; walls min {mm(walls.get('min_mm'))}, p05 {mm(walls.get('p05_mm'))}, median {mm(walls.get('median_mm'))} "
            f"mm; support ~{mm(support.get('estimated_support_volume_mm3'))} mm3")
