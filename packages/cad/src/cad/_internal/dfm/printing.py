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
from cad._internal.dfm._common import mm, not_applicable, where
from cad._internal.dfm.rules import OWN, Rule, RuleSet, Source
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

_ACCESSED = "2026-11-10"
#: The rules' own version (``RuleSet.version``), bumped when a rule changes.
_VERSION = "2026-11-10"


def _src(ident: str, publisher: str, title: str, url: str) -> Source:
    return Source(ident, publisher, title, url, _ACCESSED)


HUBS = "Protolabs Network (Hubs)"
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
    _src("xometry-fdm-tips", "Xometry (Xometry Pro)",
         "FDM 3D printing design tips: best practices and techniques for stronger prints",
         "https://xometry.pro/en/articles/fdm-design-tips/"),
    # a rule no fetched guide states (``printing.knife_edge``, ``printing.horizontal_hole``, a wall by the nozzle
    # given): text-to-cad's own figure, said as such in every verdict of it
    OWN,
)}

#: A typical machine per technology, mm, and the source it is read from: the build volume the fit is
#: measured against when ``build_volume`` is not given (Hubs's typical machine: a desktop printer for FDM and
#: SLA), assumed and said in every verdict of it.
BUILD_VOLUMES: dict[str, tuple[tuple[float, float, float], str]] = {
    "fdm": ((200, 200, 200), "hubs-geometry"), "sla": ((145, 145, 175), "hubs-geometry"),
    "sls": ((300, 300, 300), "hubs-geometry"), "mjf": ((380, 285, 380), "hubs-geometry"),
    "pbf": ((250, 150, 150), "hubs-geometry")}
#: The largest machine the same page lists per technology, mm ("up to ..."; MJF's one machine): a part no
#: orientation of which fits it is made by no machine of the technology -- ``printing.build_volume``'s error
#: where no ``build_volume`` is given, as the typical machine is its warning.
LARGEST_VOLUMES: dict[str, tuple[float, float, float]] = {
    "fdm": (900, 600, 900), "sla": (1500, 750, 500), "sls": (750, 550, 550), "mjf": (380, 285, 380),
    "pbf": (500, 280, 360)}
#: The nozzle Hubs's FDM wall minimum (0.8 mm) is two beads of: the common one. With ``--nozzle`` given the
#: minimum is two beads of that nozzle (``NOZZLE_BEADS``), text-to-cad's own scaling of the cited figure (Hubs:
#: "wall thickness depends on nozzle diameter and how well passes fuse together").
COMMON_NOZZLE_MM = 0.4
NOZZLE_BEADS = 2.0

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


def _context(resolved: dict[str, Any]) -> dict[str, Any]:
    """What the wall rules read of the options: the technology and the nozzle, where one is given."""
    nozzle = resolved.get("nozzle")
    return {"technology": resolved["technology"], "nozzle": float(nozzle) if nozzle is not None else None,
            "nozzle_given": nozzle is not None}


def _overhang(rows: list[Row], kinds_by_tech: dict[str, tuple[str, ...]]) -> list[Rule]:
    found = []
    for technology, limit, source, severity, said in rows:
        found.append(Rule("printing.overhang_angle", "overhangs", "angle_deg", "min", {technology: limit}, "deg",
                          "down-facing surface angle from horizontal", source, severity=severity, by="technology",
                          when={"technology": technology, "angle_given": False},
                          item_when={"kind": kinds_by_tech[technology], "counted": True},
                          fix="support it, chamfer it to at least {limit:g} deg from horizontal, or turn the part",
                          note=said))
        # the person's printer, declared (--angle-limit), as --tools declares a shop's cutters: its own angle
        found.append(Rule("printing.overhang_angle", "overhangs", "angle_deg", "min", {technology: 1.0}, "deg",
                          "down-facing surface angle from horizontal", source, severity=severity, by="technology",
                          scale_by="angle_limit", when={"technology": technology, "angle_given": True},
                          item_when={"kind": kinds_by_tech[technology], "counted": True},
                          fix="support it, chamfer it to at least {limit:g} deg from horizontal (the --angle-limit "
                              "given), or turn the part",
                          note="the printer's own self-supporting angle, given (--angle-limit)"))
    return found


_KINDS = {"fdm": _SUPPORT_KINDS, "sla": _SUPPORT_KINDS, "pbf": (*_SUPPORT_KINDS, "bridge")}
_FIX_WALL = "thicken it to at least {limit:g} mm"


_AT_LIMIT = ("at the limit within the mesh's accuracy: its chords may depart from the surface by {chord_mm:.3g} mm "
             "there, read from its curvature and edge lengths")


def _walls(supported: list[Row], free: list[Row]) -> list[Rule]:
    """The wall rules: a wall's minimum by whether it is supported (joined to the part on two or more sides:
    ``wall_thickness.items[].supported``, read off the wall on both paths), each with its variant for a wall at
    the limit within a mesh's accuracy (a warning) and, for FDM with ``--nozzle`` given, two beads of that
    nozzle in place of Hubs's 0.8 mm. A wall whose support could not be read (``supported`` None) is judged as
    supported -- and, between the two minima, said: it fails if it is free."""
    found: list[Rule] = []
    unread = "wall thickness (whether it is supported could not be read: judged as supported)"
    for rid, what, rows, joined, fix, note in (
            ("printing.wall_supported", "supported wall thickness", supported, True, _FIX_WALL,
             "a wall joined to the part on two or more sides"),
            ("printing.wall_unsupported", "unsupported wall thickness", free, False,
             _FIX_WALL + ", or join it to the part on a second side", "a wall joined to the part on one side or none"),
            ("printing.wall", unread, supported, None, _FIX_WALL, "")):
        for near in (False, True):
            # a mesh's wall under the limit by no more than its chords may depart from the surface is at the
            # limit within the mesh's accuracy (``_at_limit``): a warning whatever the limit's own severity
            item_when = {"supported": joined, "at_limit": True if near else (False, None)}
            kept = [(tech, limit, source, "warning" if near else severity, said) for tech, limit, source, severity, said in rows]
            mended = fix + ("; or check the exact model (a STEP or the model): the mesh cannot tell" if near else "")
            # FDM's figure is two beads of the common nozzle: its verdicts say the nozzle assumed
            for chosen, assumed in (([row for row in kept if row[0] != "fdm"], ""),
                                    ([row for row in kept if row[0] == "fdm"],
                                     f"assuming the common {COMMON_NOZZLE_MM:g} mm nozzle: give --nozzle for another")):
                found += _rules(rid, "wall_thickness", "thickness_mm", "min", "mm", what, chosen, mended, item_when, note,
                                when={"technology": tuple(row[0] for row in chosen), "nozzle_given": False},
                                detail="; ".join(part for part in (_AT_LIMIT if near else "", assumed) if part))
            found.append(Rule(
                rid, "wall_thickness", "thickness_mm", "min", {"fdm": NOZZLE_BEADS}, "mm", what, OWN.id,
                severity="warning" if near else "error", by="technology", scale_by="nozzle",
                when={"technology": "fdm", "nozzle_given": True}, item_when=item_when, fix=mended,
                note=f"{NOZZLE_BEADS:g} beads of the nozzle given (--nozzle): text-to-cad's own scaling of Hubs's 0.8 "
                     f"mm, two beads of the common {COMMON_NOZZLE_MM:g} mm nozzle",
                detail=(_AT_LIMIT + "; " if near else "") + f"{NOZZLE_BEADS:g} beads of the {{nozzle:g}} mm nozzle given"))
    # a wall whose support could not be read, between the two minima: it passes if it is supported and fails
    # if it is free -- said, never passed in silence
    found += _rules("printing.wall", "wall_thickness", "thickness_mm", "min", "mm",
                    "wall thickness, were it unsupported (whether it is could not be read)",
                    [(tech, limit, source, "warning", said) for tech, limit, source, _, said in free],
                    "thicken it to at least {limit:g} mm, or check the exact model (a STEP or the model), which "
                    "tells whether the wall is joined on two sides", {"supported": None},
                    when={"technology": tuple(row[0] for row in free), "nozzle_given": False})
    return found


def _general() -> tuple[Rule, ...]:
    """The table: per figure and technology the one row a guide gives it -- Hubs's where Hubs gives one, else
    Protolabs's, else Xometry's. Each row was read on its page on ``_ACCESSED``."""
    rows: dict[str, list[Row]] = {key: [] for key in (
        "wall_s", "wall_u", "hole", "pin", "pin_aspect", "overhang", "bridge", "cantilever", "hhole", "clear", "gap",
        "escape_n", "escape_d", "escape_n_applied", "escape_d_applied", "hollow", "fit", "emboss", "engrave_d",
        "engrave_w", "warp", "section", "hround")}

    def add(key: str, technology: str, limit: float, source: str, severity: str, said: str = "") -> None:
        # one source a technology a figure; a source may give one a recommendation and a limit (Hubs SLA holes:
        # a warning at 0.8, an error at 0.5)
        assert not any(row[0] == technology and row[2] != source for row in rows[key]), (key, technology, source)
        rows[key].append((technology, limit, source, severity, said))

    # Hubs's table, "Min wall (supported / free)"; DMLS's row is a range each (0.4-0.8 / 0.8-1.5): its least
    for tech, supported, free in (("sla", 0.5, 1.0), ("sls", 0.8, 1.0), ("mjf", 0.7, 1.0), ("pbf", 0.4, 0.8)):
        add("wall_s", tech, supported, "hubs-thin-walls", "error")
        add("wall_u", tech, free, "hubs-thin-walls", "error")
    for key in ("wall_s", "wall_u"):
        add(key, "fdm", NOZZLE_BEADS * COMMON_NOZZLE_MM, "hubs-thin-walls", "error")
    # Hubs SLA: holes "less than 0.8mm ... may close off" (a risk), its table's "Minimum diameter of 0.5mm"
    add("hole", "sla", 0.8, "hubs-sla", "warning", "holes less than 0.8 mm may close off")
    add("hole", "sla", 0.5, "hubs-sla", "error", "minimum diameter of 0.5 mm")
    add("hole", "sls", 1.5, "hubs-sls", "error", "all holes should be larger than 1.5 mm")
    add("hole", "pbf", 1.5, "hubs-metal", "error", "minimum hole diameter DMLS/SLM: 1.5 mm")
    add("hole", "fdm", 1.0, "xometry-fdm", "warning", "greater than 0.04 in (1 mm) to retain a circular shape")
    # Hubs FDM gives pins no minimum (under 5 mm they "can be made up of only perimeter prints"): FDM's is
    # Xometry's "Pins should be at least 1 mm in diameter and kept as short as possible." -- a should: a warning
    add("pin", "fdm", 1.0, "xometry-fdm-tips", "warning", "pins should be at least 1 mm in diameter")
    add("pin", "sla", 0.5, "xometry-sla", "error", "minimum shaft diameter 0.5 mm")
    add("pin", "sls", 0.8, "hubs-sls", "warning", "a minimum of 0.8 mm is recommended")
    add("pin", "mjf", 0.5, "hubs-mjf", "warning", "minimum feature size 0.5 mm")
    add("pin", "pbf", 0.6, "hubs-metal", "error", "minimum feature size DMLS/SLM 0.6 mm")
    add("pin_aspect", "pbf", 8.0, "hubs-metal", "warning", "maximum aspect ratio 8:1")
    add("overhang", "fdm", 45.0, "hubs-fdm", "warning", "overhangs up to 45 deg print without support")
    add("overhang", "sla", 19.0, "hubs-sla", "warning", "at least 19 deg from level")
    # the rules keep Protolabs's 45 for metal: Hubs's metal guide lists "maximum overhang angle DMLS/SLM: 50
    # deg" without saying from which axis, so no Hubs row stands for it
    add("overhang", "pbf", 45.0, "protolabs-metal", "warning", "avoid overhangs less than 45 deg; Hubs metal "
        "lists 50 deg, its reference unstated, and is not used")
    add("bridge", "fdm", 5.0, "hubs-fdm", "warning")
    add("bridge", "sla", 21.0, "hubs-sla", "warning")
    add("cantilever", "sla", 1.0, "hubs-sla", "warning")
    add("cantilever", "pbf", 0.5, "hubs-metal", "warning")
    add("hhole", "pbf", 8.0, "protolabs-metal", "warning")
    add("clear", "fdm", 0.762, "xometry-3dp", "warning", "clearance between features: at least 0.030 in")
    add("clear", "sla", 0.5, "hubs-sla", "warning")
    add("clear", "sls", 0.3, "hubs-sls", "warning")
    add("clear", "mjf", 0.9, "hubs-mjf", "warning")
    add("clear", "pbf", 0.635, "protolabs-toolkit", "warning")
    # FDM's gap: Xometry's general "clearance between features" line, no FDM limit -- a warning
    add("gap", "fdm", 0.762, "xometry-3dp", "warning", "clearance between features: at least 0.030 in")
    for tech, gap in (("sla", 0.635), ("sls", 0.762), ("mjf", 0.508), ("pbf", 0.635)):
        add("gap", tech, gap, "protolabs-toolkit", "error")
    add("escape_n", "sla", 1, "hubs-sla", "error")
    add("escape_d", "sla", 3.5, "hubs-sla", "warning")
    add("escape_n", "sls", 1, "hubs-sls", "error")
    add("escape_d", "sls", 3.5, "hubs-sls", "warning")
    # Hubs's SLS escape-hole figure, and the need for one per cavity, for the other powder beds: their loose
    # powder is trapped the same way (the rules' own reading, no page says it for them -- and every verdict of
    # it says so)
    for tech in ("mjf", "pbf"):
        add("escape_n_applied", tech, 1, "hubs-sls", "error")
        add("escape_d_applied", tech, 3.5, "hubs-sls", "warning")
    add("hollow", "sla", 2.0, "hubs-sla", "warning")
    for tech in TECHNOLOGIES:
        add("fit", tech, 1.0, "hubs-geometry", "error")
    add("emboss", "fdm", 1.0, "xometry-fdm", "warning")
    add("emboss", "sla", 0.1, "hubs-sla", "warning")
    add("emboss", "sls", 1.0, "hubs-sls", "warning")
    add("emboss", "mjf", 0.3048, "protolabs-toolkit", "warning")
    add("emboss", "pbf", 0.4, "hubs-metal", "warning")
    add("engrave_d", "sla", 0.4, "hubs-sla", "warning")
    add("engrave_d", "sls", 1.0, "hubs-sls", "warning")
    add("engrave_w", "sla", 0.4, "hubs-sla", "warning")
    add("engrave_w", "pbf", 0.4, "hubs-metal", "warning")
    for tech in ("sls", "mjf"):
        add("warp", tech, 177.8, "protolabs-7mistakes", "warning")
    add("section", "pbf", 10.0, "hubs-metal", "warning")
    # text-to-cad's own threshold for FDM's horizontal holes (HORIZONTAL_HOLE_MM): no guide gives one
    add("hround", "fdm", HORIZONTAL_HOLE_MM, OWN.id, "warning")
    found: list[Rule] = _walls(rows["wall_s"], rows["wall_u"])
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
                    "is hard to remove and turning the part 90 deg removes it")
    # the rule judges a gap or a contact; bodies that pass through each other are their own finding
    found += _rules("printing.clearance", "clearances", "distance_mm", "min", "mm", "clearance between parts",
                    rows["clear"], "open the clearance to at least {limit:g} mm (parts printed together fuse); "
                    + IN_PLACE, {"kind": ("gap", "near", "contact")})
    found += _rules("printing.gap", "gaps", "gap_mm", "min", "mm", "gap between faces", rows["gap"],
                    "open the gap to at least {limit:g} mm or close it")
    applied = "Hubs's SLS figure, applied: no fetched guide states one for {technology}"
    # a hole under the limit by no more than its reading's own error (a mesh's round hole is a polygon inside
    # the circle) is at the limit (``_at_limit``): no verdict turns on it
    for count, diameter, detail in ((rows["escape_n"], rows["escape_d"], ""),
                                    (rows["escape_n_applied"], rows["escape_d_applied"], applied)):
        found += _rules("printing.escape_holes", "trapped_volumes", "escape_holes", "min", "count",
                        "escape holes of a cavity", count,
                        "add an escape hole of at least 3.5 mm (two, opposite, drain best), or fill the cavity",
                        detail=detail)
        found += _rules("printing.escape_hole_diameter", "trapped_volumes", "min_escape_hole_mm", "min", "mm",
                        "smallest escape hole of a cavity", diameter, "open it to at least {limit:g} mm",
                        {"escape_at_limit": (False, None)}, detail=detail)
    found += _rules("printing.hollow_wall", "trapped_volumes", "min_wall_mm", "min", "mm",
                    "wall around a hollow", rows["hollow"], "thicken the hollow's wall to at least {limit:g} mm")
    # The machine given (--build-volume) is the printer's: a part over it is not made, an error. With none
    # given: over the typical machine assumed (no printer of the user's) is a warning that names it; over the
    # largest machine the same page lists, in every orientation, no machine of the technology makes it: an error.
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (best axis orientation)", rows["fit"],
                    "split the part, or print it on a larger machine", when={"machine_given": True},
                    detail="against the {machine} mm machine given")
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (best axis orientation)",
                    [(*row[:3], "warning", row[4]) for row in rows["fit"]],
                    "give the machine it prints on (--build-volume XxYxZ), or split the part",
                    when={"machine_given": False, "beyond_largest": False},
                    detail="against an assumed typical {technology} machine, {machine} mm: give --build-volume")
    found += _rules("printing.build_volume", "build_volume", "largest_fill_ratio", "max", "ratio",
                    "part size over the largest machine listed (best axis orientation)", rows["fit"],
                    "split the part into pieces a machine holds (--build-volume XxYxZ checks one)",
                    when={"machine_given": False, "beyond_largest": True},
                    detail="the largest {technology} machine the guide lists is {largest} mm, a typical one {machine} mm")
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
                    [(technology, limit, OWN.id, "warning", "") for technology, limit, *_ in rows["wall_u"]],
                    "blunt it -- a flat or round at least {limit:g} mm across -- or open its angle to 45 deg or more",
                    note="the material thins to nothing at an acute edge: judged against the unsupported-wall "
                         "minimum; the tip prints rounded (Hubs SLS: a radius under 0.4 mm prints as 0.4 mm)",
                    detail="the tip prints rounded")
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
#: The overhang angle ``printing.overhang_angle`` judges each face against, per technology, where no
#: ``--angle-limit`` is given (given, the rule judges against it).
OVERHANG_JUDGED: dict[str, float] = {technology: float(limit) for rule in RULES.rules
                                     if rule.id == "printing.overhang_angle" and isinstance(rule.limit, dict)
                                     and rule.scale_by is None for technology, limit in rule.limit.items()}


# --- options ------------------------------------------------------------------------------------------------


def angle_limit(resolved: dict[str, Any]) -> float:
    """The overhang angle the check counts support for: the one given, else the technology's."""
    given = resolved.get("angle_limit")
    return float(given) if given is not None else DEFAULT_ANGLE[resolved["technology"]]


def wall_minimum(resolved: dict[str, Any]) -> float | None:
    """The rules' unsupported-wall minimum for the technology (and the nozzle, where one is given): what a
    knife edge's thin depth is measured against, and the thickness under which a wall's support is read."""
    return max(_limits("printing.wall_unsupported", resolved, "error"), default=None)


def layer_height(resolved: dict[str, Any]) -> float:
    given = resolved.get("layer_height")
    return float(given) if given is not None else DEFAULT_LAYER[resolved["technology"]]


def machine_volume(resolved: dict[str, Any]) -> dict[str, Any]:
    """The build volume the fit is measured against: ``build_volume`` given, else a typical machine of the
    technology's (``BUILD_VOLUMES``), assumed -- with the largest the same page lists (``LARGEST_VOLUMES``)."""
    if resolved.get("build_volume") is not None:
        return {"volume_mm": list(build_volume(resolved["build_volume"])), "origin": "given"}
    volume, source = BUILD_VOLUMES[resolved["technology"]]
    return {"volume_mm": [float(value) for value in volume], "origin": f"assumed ({SOURCES[source].url})",
            "largest_mm": [float(value) for value in LARGEST_VOLUMES[resolved["technology"]]]}


def validate(resolved: dict[str, Any], document_type: str) -> None:
    technology = resolved["technology"]
    if technology not in TECHNOLOGIES:
        raise ArgumentRefused(f"--technology is one of {', '.join(TECHNOLOGIES)}, not {technology!r}")
    # A technology prints one class of material: metal powder bed fusion a metal, the others a plastic (a
    # filament, a resin, a polymer powder). A material of the other class is a mistake, refused as molding
    # refuses a metal.
    material = materials.resolve(resolved.get("material"))
    wanted = "metal" if technology == "pbf" else "plastic"
    if material is not None and materials.material_class(material) != wanted:
        other = ("give --technology pbf (metal powder bed fusion) to print a metal" if wanted == "plastic"
                 else "give --technology fdm, sla, sls or mjf to print a plastic")
        raise ArgumentRefused(f"--material {material} is a {materials.material_class(material)}, and "
                              f"--technology {technology} prints a {wanted}: {other}, or give a {wanted}")
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
    fit = _ok(report.get("build_volume"))
    return {**_context(resolved), "material": material,
            # no orientation of the part fits the largest machine the guide lists (no build volume given)
            "beyond_largest": fit.get("fits_largest") is False,
            "largest": " x ".join(f"{value:g}" for value in machine.get("largest_mm") or ()) or None,
            "material_class": materials.material_class(material), "angle_limit": angle_limit(resolved),
            "angle_given": resolved.get("angle_limit") is not None,
            "layer_height": layer_height(resolved),
            # the build volume's: given (an error to pass it) or a typical machine assumed (a warning naming it)
            "machine_given": machine["origin"] == "given",
            "machine": " x ".join(f"{value:g}" for value in machine["volume_mm"])}


# --- findings and summary -------------------------------------------------------------------------------------


def _ok(family: Any) -> dict[str, Any]:
    return family if isinstance(family, dict) and "error" not in family else {}


def _limits(rule_id: str, resolved: dict[str, Any], severity: str | None = None,
            supported: Any = ...) -> list[float]:
    """The limits ``rule_id``'s variants give this technology and nozzle (those of ``severity``, and for walls
    of this ``supported``, where given)."""
    context = _context(resolved)
    return [limit for rule in RULES.rules
            if rule.id == rule_id and severity in (None, rule.severity) and rule.applies(context)
            and (supported is ... or rule.item_when.get("supported", ...) is supported)
            for limit in [rule.limit_for(context)] if limit is not None]


def _at_limit(report: dict[str, Any], resolved: dict[str, Any]) -> None:
    """A figure under its limit by no more than its own reading may be off is at the limit (no tolerance
    cliff): the item says so, and its rule's variant for it judges it.

    - A mesh's wall (an item with ``chord_mm``) under its rule's limit (the supported, the unsupported or the
      unread wall's) by no more than its chords may depart from the surface there, and past no limit by more,
      is ``at_limit``: the rule's warning, not its error. Exact geometry's walls carry no ``chord_mm``.
    - A cavity's smallest escape hole under ``printing.escape_hole_diameter``'s limit by no more than its
      ``escape_hole_uncertainty_mm`` (a round hole's chords stand inside its circle) is ``escape_at_limit``:
      not judged under. One the voxels could only bound (``escape_hole_at_most``: narrower than a voxel) that
      does not put it under the limit is not measured (None), never a pass."""
    walls = _ok(report.get("wall_thickness"))
    rule_of = {True: "printing.wall_supported", False: "printing.wall_unsupported", None: "printing.wall"}
    for item in walls.get("items") or ():
        chord, value = item.get("chord_mm"), item.get("thickness_mm")
        if not isinstance(chord, (int, float)) or not isinstance(value, (int, float)) or "at_limit" in item:
            continue
        limits = _limits(rule_of[item.get("supported")], resolved, "error", item.get("supported"))
        under = [limit for limit in limits if value < limit]
        item["at_limit"] = bool(under) and all(limit <= value + chord for limit in under)
    limits = _limits("printing.escape_hole_diameter", resolved)
    for item in _ok(report.get("trapped_volumes")).get("items") or ():
        value, slack = item.get("min_escape_hole_mm"), item.get("escape_hole_uncertainty_mm")
        if value is None and item.get("escape_holes") == 0:
            not_applicable(item, "min_escape_hole_mm")  # a sealed cavity has no hole to size: escape_holes' to judge
        if not isinstance(value, (int, float)) or "escape_at_limit" in item:
            continue
        under = [limit for limit in limits if value < limit]
        if item.get("escape_hole_at_most") and limits and not under:
            item["min_escape_hole_mm"] = None  # under a voxel wide, and a voxel is no narrower than the limit
            continue
        item["escape_at_limit"] = bool(under) and isinstance(slack, (int, float)) and \
            all(limit <= value + slack for limit in under)


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    technology = resolved["technology"]
    _at_limit(report, resolved)
    mesh = _ok(report.get("mesh"))
    if mesh:
        if mesh.get("watertight") is False:
            # An open surface has no inside: a slicer cannot fill it, and every figure below is of a surface,
            # not a solid -- the part is not printable as it is (an error, as an open B-rep is).
            opened = mesh.get("open_bodies") or []
            named = "; ".join(f"one at {where(body.get('xyz'))} ({body.get('boundary_edges')} open edge(s))"
                              for body in opened[:3])
            count = mesh.get("open_body_count") or len(opened) or 1
            found.append(CheckFinding("error", "not_watertight", f"the mesh is not watertight: {count} open "
                                      f"body(ies){': ' + named if named else ''}. A slicer cannot tell its inside, "
                                      "and its volume, walls, cavities and support are measured of an open surface "
                                      "-- read every figure below with that",
                                      where(opened[0].get("xyz")) if opened else "mesh",
                                      "close the surface (repair the mesh), or export it again from the model"))
        repairs = [f"{mesh[key]} {said}" for key, said in (
            ("duplicate_faces_dropped", "triangle(s) doubled in place dropped"),
            ("faces_rewound", "triangle(s) wound against their neighbours turned"),
            ("shells_turned", "closed shell(s) wound inside out turned to face outward")) if mesh.get(key)]
        if repairs:
            # said, never silent: what was measured is the mesh repaired, and a slicer reads the file as it is
            found.append(CheckFinding("warning", "mesh_repaired", "the mesh was repaired before it was measured: "
                                      + "; ".join(repairs) + ". A slicer may read the file as it is differently",
                                      "mesh", "export it again from the model, or repair the file"))
        if (mesh.get("body_count") or 0) > 1:
            found.append(CheckFinding("info", "several_bodies", f"{mesh['body_count']} separate bodies: each is "
                                      "measured on its own, their clearances between", "mesh"))
        overlap = _ok(report.get("gaps")).get("overlap")
        if overlap:
            found.append(CheckFinding("warning", "mesh_overlap", f"faces lie on faces {overlap['gap_mm']:g} mm apart "
                                      f"({overlap['samples']} triangle(s)): doubled or overlapping triangles, a "
                                      "defect of the mesh, not a gap -- a slicer may misread it", where(overlap["xyz"]),
                                      "repair the mesh, or export it again from the model"))
    solid = _ok(report.get("solid"))
    for item in solid.get("items") or ():
        if item.get("closed") is False:
            found.append(CheckFinding("error", "not_watertight", f"{item['part']} is not closed (an open shell): "
                                      "a slicer cannot tell its inside, and every figure of it is of a surface",
                                      item.get("location"), "close the shell into a solid, or rebuild the part as one"))
        if item.get("sound") is False:
            faulty = item.get("faulty_faces") or []
            on = f" on {', '.join(ref.rsplit('/', 1)[-1] for ref in faulty)}" if faulty else ""
            found.append(CheckFinding("error", "not_sound", f"{item['part']} fails the kernel's validity check "
                                      f"({', '.join(item.get('issues') or ['invalid'])}{on}): a slicer may "
                                      "misread it",
                                      item.get("location"), "rebuild the faulty feature; export the STEP again"))
    # A soundness check that ran bounded is said, never read as a full pass: past the boolean check's budget a
    # part has its topology checked alone, and a part with a large free-form face its edges against faces alone.
    bounded = {"boolean_edges": [], "topology": []}
    for item in solid.get("items") or ():
        if item.get("sound") and item.get("check") in bounded:
            bounded[item["check"]].append(item)
    if bounded["boolean_edges"] or bounded["topology"]:
        said = []
        if bounded["boolean_edges"]:
            said.append(f"{_names(bounded['boolean_edges'])} had its self-intersections checked edges against faces "
                        "alone (a free-form face of over 2000 control points): two faces crossing inside both, no "
                        "edge of either meeting the other, are not found")
        if bounded["topology"]:
            said.append(f"{_names(bounded['topology'])} had its topology checked alone (the boolean check's budget, "
                        "200 faces, spent): a self-intersection is not found")
        first = (bounded["boolean_edges"] or bounded["topology"])[0]
        found.append(CheckFinding("warning", "soundness_bounded", "; ".join(said), first.get("location"),
                                  "check the parts in the slicer (or one at a time) where a self-intersection matters"))
    # Several parts, every occurrence one (a part of several solids is ``several_solids``, said alike in every
    # process where the document is read).
    if (solid.get("part_count") or 0) > 1:
        found.append(CheckFinding("info", "several_bodies", f"{solid['part_count']} parts: each is measured on its "
                                  "own, their clearances between", "solid"))
    # Bodies that pass through each other: one finding a pair (the clearance rule judges gaps and contacts).
    crossing = [item for item in _ok(report.get("clearances")).get("items") or () if item.get("kind") == "overlap"]
    for item in crossing[:8]:
        names = item.get("parts") or [f"body {index + 1}" for index in item.get("bodies") or ()]
        shared = f" ({item['overlap_mm3']:g} mm3 shared)" if item.get("overlap_mm3") else ""
        found.append(CheckFinding(
            "warning", "bodies_intersect", f"{' and '.join(str(name) for name in names) or 'two bodies'} pass "
            f"through each other{shared}: a slicer may join them or fill the overlap twice, and the volume given is "
            "the bodies' sum, their overlap counted twice", item.get("location") or where(item.get("xyz")),
            "join them into one body (a union), or move them apart"))
    if len(crossing) > 8:
        found.append(CheckFinding("warning", "bodies_intersect", f"{len(crossing) - 8} more pairs pass through "
                                  "each other (measurements.clearances lists every one)", "clearances"))
    if candidates:
        return found
    overhangs = _ok(report.get("overhangs"))
    parts = (solid.get("part_count") or 0) if solid else (mesh.get("body_count") or 0)
    if (overhangs.get("down_facing_area_below_limit_mm2") or 0) > 0:
        faces = overhangs.get("largest_faces_below_limit") or [{}]
        assembled = f"; {IN_PLACE}" if parts > 1 else ""
        # One cause, one finding: where printing.overhang_angle judges each face, this is the sum of them (info,
        # naming the rule); a warning only where no rule judges the faces and the technology needs support.
        judged = technology in OVERHANG_JUDGED  # at the angle used: the one given, else the rule's
        found.append(CheckFinding(
            "warning" if technology not in POWDER and not judged else "info", "overhangs",
            f"{overhangs['down_facing_area_below_limit_mm2']:g} mm2 ({overhangs['down_facing_area_below_limit_pct']:g}%"
            f" of the surface) faces down at under {overhangs['angle_limit_used_deg']:g} deg from horizontal, off "
            f"the plate, {overhangs['face_count_below_limit']} {'faces' if solid else 'triangles'}"
            f"{': printing.overhang_angle judges each' if judged else ''}{assembled}",
            faces[0].get("location") or where(faces[0].get("location_xyz")),
            "support it, chamfer the undersides to the angle or steeper, or turn the part (--candidates ranks the "
            "orientations; turn it in the model)" if technology not in POWDER else None))
    # What the mesh could not judge, said: surface and edges within its own angular deflection of a limit. The
    # exact model has the angle; a finer mesh narrows the band.
    knives = _ok(report.get("knife_edges"))
    near_area = overhangs.get("at_limit_area_mm2") or 0.0
    near_slope = near_area >= (overhangs.get("area_floor_mm2") or 0.0) and (overhangs.get("at_limit_tolerance_deg") or 0) >= 0.01
    if mesh and (near_slope or knives.get("at_limit_count")):
        said = []
        if near_slope:
            said.append(f"{near_area:g} mm2 of down-facing surface reads under the {overhangs['angle_limit_used_deg']:g} "
                        f"deg limit by less than the mesh's chords turn from the surface there (up to "
                        f"{overhangs['at_limit_tolerance_deg']:g} deg)")
        if knives.get("at_limit_count"):
            said.append(f"{knives['at_limit_count']} edge(s), {knives['at_limit_length_mm']:g} mm, read within "
                        f"{knives['at_limit_tolerance_deg']:g} deg of a knife edge's {knives.get('knife_below_deg', 45):g} deg")
        found.append(CheckFinding("info", "mesh_at_limit", "at the limit within the mesh's accuracy, not judged: "
                                  + "; ".join(said), "mesh",
                                  "check the exact model (its STEP), or export a finer mesh"))
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


def _names(items: list[dict[str, Any]]) -> str:
    names = [str(item.get("part")) for item in items]
    return ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
