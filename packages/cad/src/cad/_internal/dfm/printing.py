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
says so: never a pass). The build volume is the printer's given (``--build-volume``, or the file of its
settings: ``--printer``), else a typical machine of the technology's, assumed and said.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm, not_applicable, where
from cad._internal.dfm.rules import OWN, Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["BUILD_VOLUMES", "DEFAULT_ANGLE", "DEFAULT_LAYER", "MEASURED_FROM", "OPTIONS", "RULES", "TECHNOLOGIES",
           "angle_limit", "build_volume", "context", "findings", "layer_height", "machine_volume",
           "printer_settings", "summary", "validate", "wall_minimum"]

#: The printing technologies: fused filament, selective laser sintering, stereolithography and DLP,
#: multi jet fusion, metal powder bed fusion (DMLS, SLM).
TECHNOLOGIES = ("fdm", "sls", "sla", "mjf", "pbf")
#: The technologies whose loose powder holds the part as it builds: no support, but powder to get out.
POWDER = ("sls", "mjf")
OPTIONS: dict[str, Any] = {"technology": "fdm", "build_volume": None, "angle_limit": None, "samples": 2000,
                           "layer_height": None, "nozzle": None, "printer": None}
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
#: What a mesh's result says of the families it does not hold (``summary``): its pins are walls, judged by the
#: wall rules, and its holes are read up to the gaps' reach (a larger hole's crown is an overhang).
MESH_UNREAD = {"pins": "pins' own minima (a pin is judged as a wall)", "details": "embossed and engraved details"}
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
    # given): cad's own figure, said as such in every verdict of it
    OWN,
)}

#: A typical machine per technology, mm, and the source it is read from: the build volume the fit is
#: measured against when ``build_volume`` is not given (Hubs's typical machine: a desktop printer for FDM and
#: SLA), assumed and said in every verdict of it.
BUILD_VOLUMES: dict[str, tuple[tuple[float, float, float], str]] = {
    "fdm": ((200, 200, 200), "hubs-geometry"), "sla": ((145, 145, 175), "hubs-geometry"),
    "sls": ((300, 300, 300), "hubs-geometry"), "mjf": ((380, 285, 380), "hubs-geometry"),
    "pbf": ((250, 150, 150), "hubs-geometry")}
#: The largest machine the same page lists per technology, mm ("up to ..."; MJF's one machine): a part that
#: fits it lying no way (on any side, turned any way on the bed: ``meshops_printing.lie``) is made by no machine
#: of the technology -- ``printing.build_volume``'s error
#: where no ``build_volume`` is given, as the typical machine is its warning.
LARGEST_VOLUMES: dict[str, tuple[float, float, float]] = {
    "fdm": (900, 600, 900), "sla": (1500, 750, 500), "sls": (750, 550, 550), "mjf": (380, 285, 380),
    "pbf": (500, 280, 360)}
#: The nozzle Hubs's FDM wall minimum (0.8 mm) is two beads of: the common one. With ``--nozzle`` given the
#: minimum is two beads of that nozzle (``NOZZLE_BEADS``), cad's own scaling of the cited figure (Hubs:
#: "wall thickness depends on nozzle diameter and how well passes fuse together").
COMMON_NOZZLE_MM = 0.4
NOZZLE_BEADS = 2.0
#: FDM's skins lying in the layer plane (a wall whose faces lie within 45 deg of it: ``lying``) are laid layer on
#: layer: under ``SKIN_LAYERS_MIN`` layers one is not laid at all (the floor, an error), under ``SKIN_LAYERS``
#: it is one layer alone (a recommendation). cad's own: no guide states a figure for them.
SKIN_LAYERS_MIN = 1.0
SKIN_LAYERS = 2.0

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
    supported -- and, between the two minima, said: it fails if it is free. FDM's figure is a standing wall's,
    laid bead beside bead: a skin lying in the layer plane (``lying``: a tray's floor, a living hinge) is laid
    layer on layer and judged by its layers (``printing.skin_layer``, ``printing.skin_layers``)."""
    found: list[Rule] = []
    standing = {"lying": (False, None)}
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
            for chosen, assumed, which in (
                    ([row for row in kept if row[0] != "fdm"], "", item_when),
                    ([row for row in kept if row[0] == "fdm"],
                     f"assuming the common {COMMON_NOZZLE_MM:g} mm nozzle: give --nozzle for another",
                     {**item_when, **standing})):
                found += _rules(rid, "wall_thickness", "thickness_mm", "min", "mm", what, chosen, mended, which, note,
                                when={"technology": tuple(row[0] for row in chosen), "nozzle_given": False},
                                detail="; ".join(part for part in (_AT_LIMIT if near else "", assumed) if part))
            found.append(Rule(
                rid, "wall_thickness", "thickness_mm", "min", {"fdm": NOZZLE_BEADS}, "mm", what, OWN.id,
                severity="warning" if near else "error", by="technology", scale_by="nozzle",
                when={"technology": "fdm", "nozzle_given": True}, item_when={**item_when, **standing}, fix=mended,
                note=f"{NOZZLE_BEADS:g} beads of the nozzle given (--nozzle): cad's own scaling of Hubs's 0.8 "
                     f"mm, two beads of the common {COMMON_NOZZLE_MM:g} mm nozzle",
                detail=(_AT_LIMIT + "; " if near else "") + f"{NOZZLE_BEADS:g} beads of the {{nozzle:g}} mm nozzle given"))
    # a wall whose support could not be read, between the two minima: it passes if it is supported and fails
    # if it is free -- said, never passed in silence
    found += _rules("printing.wall", "wall_thickness", "thickness_mm", "min", "mm",
                    "wall thickness, were it unsupported (whether it is could not be read)",
                    [(tech, limit, source, "warning", said) for tech, limit, source, _, said in free],
                    "thicken it to at least {limit:g} mm, or check the exact model (a STEP or the model), which "
                    "tells whether the wall is joined on two sides", {"supported": None, "between_minima": True},
                    when={"technology": tuple(row[0] for row in free), "nozzle_given": False})
    # FDM lays a skin that lies in the layer plane layer on layer: one thinner than a layer is not laid at all
    # (the floor), one of a single layer has no second to tie its beads (the recommendation). cad's
    # own figures: the guides' wall minimum is of standing walls ("depends on nozzle diameter").
    for rid, layers, severity, said in (
            ("printing.skin_layer", SKIN_LAYERS_MIN, "error", "a skin thinner than one layer is not laid at all"),
            ("printing.skin_layers", SKIN_LAYERS, "warning", "a skin of one layer alone has no second to tie its beads")):
        found.append(Rule(
            rid, "wall_thickness", "thickness_mm", "min", {"fdm": layers}, "mm",
            "thickness of a skin lying in the layer plane", OWN.id, severity=severity, by="technology",
            scale_by="layer_height", when={"technology": "fdm"}, item_when={"lying": True},
            fix="thicken it to at least {limit:g} mm, or print finer layers (--layer-height)",
            note=f"cad's own: {said}; FDM's two-bead wall minimum is a standing wall's",
            detail=f"{layers:g} layer(s) of {{layer_height:g}} mm"))
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
    # cad's own threshold for FDM's horizontal holes (HORIZONTAL_HOLE_MM): no guide gives one
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
                    "cad's own threshold: Hubs FDM gives no diameter, only that a horizontal hole's support "
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
                    "wall around a hollow", rows["hollow"], "thicken the hollow's wall to at least {limit:g} mm",
                    {"wall_at_limit": (False, None)})
    # The machine given (--build-volume, or the volume of the printer's file, --printer) is the printer's: a
    # part over it is not made, an error. With none given: over the typical machine assumed (no printer of the
    # user's) is a warning that names it; over the largest machine the same page lists, in every orientation,
    # no machine of the technology makes it: an error.
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (lying the best way in it)", rows["fit"],
                    "split the part, or print it on a larger machine", when={"machine_given": True},
                    detail="against {machine_said}")
    found += _rules("printing.build_volume", "build_volume", "fill_ratio", "max", "ratio",
                    "part size over the build volume (lying the best way in it)",
                    [(*row[:3], "warning", row[4]) for row in rows["fit"]],
                    "give the machine it prints on (--build-volume XxYxZ), or split the part",
                    when={"machine_given": False, "beyond_largest": False},
                    detail="against an assumed typical {technology} machine, {machine} mm: give --build-volume")
    found += _rules("printing.build_volume", "build_volume", "largest_fill_ratio", "max", "ratio",
                    "part size over the largest machine listed (lying the best way in it)", rows["fit"],
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
    # cad's own rule (no guide defines a knife edge), a warning: the tip prints rounded (Hubs SLS: "a
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
    return RuleSet("printing", "cad general rules", _VERSION, rules, tuple(SOURCES[ident] for ident in cited),
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
    """The build volume the fit is measured against: ``build_volume`` given (or a ``printer``'s, which names
    itself the origin), else a typical machine of the technology's (``BUILD_VOLUMES``), assumed -- with the
    largest the same page lists (``LARGEST_VOLUMES``)."""
    if resolved.get("build_volume") is not None:
        printer = resolved.get("printer")
        origin = "given" if not isinstance(printer, dict) or "build_volume" not in printer["supplied"] else (
            f"printer {printer['name']} ({printer['file']}, bed bounding box)")
        return {"volume_mm": list(build_volume(resolved["build_volume"])), "origin": origin}
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
    if resolved.get("printer") is not None:
        if technology != "fdm":
            raise ArgumentRefused(f"--printer is FDM's (a filament printer's settings file), not {technology}'s")
        _take_printer(resolved)
    for name in ("layer_height", "nozzle"):
        if resolved.get(name) is not None and not float(resolved[name]) > 0:
            raise ArgumentRefused(f"--{name.replace('_', '-')} is a length in millimetres above 0, not {resolved[name]}")
    if resolved.get("nozzle") is not None and resolved["technology"] != "fdm":
        raise ArgumentRefused(f"--nozzle is FDM's (a filament printer's nozzle), not {resolved['technology']}'s")
    if resolved.get("build_volume") is not None:
        build_volume(resolved["build_volume"])


#: Where a slicer's 3MF keeps the settings of the printer, filament and process a project was saved with (JSON).
PROJECT_SETTINGS = "Metadata/project_settings.config"


def printer_settings(path: str | Path) -> dict[str, Any]:
    """What ``--printer`` names of a printer, read once: ``name``, ``file``, ``volume_mm`` (the bed polygon's
    bounding box by ``printable_height``) and ``nozzle`` (the first extruder's, or None where the file gives
    none). The file is a 3MF a slicer saved (OrcaSlicer, Bambu Studio: ``PROJECT_SETTINGS``) or a JSON of a
    printer's complete settings (an exported machine preset, or the project settings themselves).
    ``ArgumentRefused`` naming the file for one that is none of these or lacks the bed or the height."""
    file = Path(path)
    settings = _printer_file(file)
    missing = [key for key in ("printable_area", "printable_height") if settings.get(key) in (None, "", [])]
    if missing:
        inherits = settings.get("inherits")
        why = (f"is a preset holding only its differences from {inherits!r}, not the printer's settings: give a 3MF "
               "the slicer saved (it holds them whole), or --build-volume and --nozzle"
               if inherits else f"holds no {', '.join(missing)}: give a 3MF the slicer saved, or a complete machine "
                                "preset")
        raise ArgumentRefused(f"--printer {file} {why}")
    try:
        points = [tuple(float(part) for part in point.strip().lower().split("x"))
                  for point in _listed(settings["printable_area"])]
        height = float(settings["printable_height"])
        if not points or any(len(point) != 2 for point in points):
            raise ValueError("a point is XxY")
    except ValueError:
        raise ArgumentRefused(f"--printer {file}: printable_area is points written 0x0, 256x0, ... and "
                              f"printable_height a number, not {settings['printable_area']!r} and "
                              f"{settings['printable_height']!r}") from None
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    volume = (max(xs) - min(xs), max(ys) - min(ys), height)
    if not all(value > 0 for value in volume):
        raise ArgumentRefused(f"--printer {file}: its bed and height make a volume of "
                              f"{' x '.join(f'{value:g}' for value in volume)} mm, not three lengths above 0")
    nozzles = _listed(settings.get("nozzle_diameter"))
    try:
        nozzle = float(nozzles[0]) if nozzles else None
    except ValueError:
        raise ArgumentRefused(f"--printer {file}: nozzle_diameter is a length in millimetres, not "
                              f"{settings['nozzle_diameter']!r}") from None
    name = next((str(settings[key]) for key in ("printer_settings_id", "name") if settings.get(key)), file.name)
    return {"name": name, "file": str(file), "volume_mm": list(volume), "nozzle": nozzle}


def _printer_file(file: Path) -> dict[str, Any]:
    if not file.is_file():
        raise ArgumentRefused(f"--printer {file} is not a file: give a 3MF a slicer saved or a machine preset JSON")
    try:
        if zipfile.is_zipfile(file):
            with zipfile.ZipFile(file) as archive:
                if PROJECT_SETTINGS not in archive.namelist():
                    raise ArgumentRefused(f"--printer {file} holds no {PROJECT_SETTINGS}: give a 3MF a slicer saved "
                                          "(OrcaSlicer, Bambu Studio), not one made another way")
                text = archive.read(PROJECT_SETTINGS)
        else:
            text = file.read_bytes()
        settings = json.loads(text)
    except ArgumentRefused:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise ArgumentRefused(f"--printer {file} is neither a 3MF a slicer saved nor a JSON of printer settings "
                              f"({type(error).__name__}: {error})") from None
    if not isinstance(settings, dict):
        raise ArgumentRefused(f"--printer {file} is JSON but not an object of settings")
    return settings


def _listed(value: Any) -> list[str]:
    """A slicer's setting as its strings: a list, one comma-joined string, or a scalar."""
    if value is None:
        return []
    parts = value if isinstance(value, (list, tuple)) else str(value).split(",")
    return [str(part).strip() for part in parts if str(part).strip()]


def _take_printer(resolved: dict[str, Any]) -> None:
    """``printer`` (a path) read once into ``resolved``: its volume and nozzle where none is given -- they are
    then the printer's, judged as ``--build-volume`` and ``--nozzle`` are -- and ``printer`` the plain facts
    (name, file, what it supplied) for the report to name it by."""
    if isinstance(resolved["printer"], dict):
        return
    printer = printer_settings(resolved["printer"])
    supplied = []
    if resolved.get("build_volume") is None:
        resolved["build_volume"] = "x".join(f"{value:g}" for value in printer["volume_mm"])
        supplied.append("build_volume")
    if resolved.get("nozzle") is None and printer["nozzle"] is not None:
        resolved["nozzle"] = printer["nozzle"]
        supplied.append("nozzle")
    resolved["printer"] = {"name": printer["name"], "file": printer["file"], "supplied": supplied}


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
            "machine_given": not machine["origin"].startswith("assumed"),
            "machine": " x ".join(f"{value:g}" for value in machine["volume_mm"]),
            "machine_said": (f"the {' x '.join(f'{value:g}' for value in machine['volume_mm'])} mm machine given"
                             if machine["origin"] == "given" else
                             f"the {' x '.join(f'{value:g}' for value in machine['volume_mm'])} mm volume of "
                             f"{machine['origin']}")}


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
    least = _limits("printing.wall_supported", resolved, "error", True)
    most = _limits("printing.wall_unsupported", resolved, "error", False)
    for item in walls.get("items") or ():
        chord, value = item.get("chord_mm"), item.get("thickness_mm")
        if isinstance(value, (int, float)) and item.get("supported") is None and "between_minima" not in item:
            # between the two minima: it passes if it is supported and fails if it is free
            item["between_minima"] = bool(least) and bool(most) and min(least) <= value < max(most)
        if not isinstance(chord, (int, float)) or not isinstance(value, (int, float)) or "at_limit" in item:
            continue
        limits = _limits(rule_of[item.get("supported")], resolved, "error", item.get("supported"))
        under = [limit for limit in limits if value < limit]
        item["at_limit"] = bool(under) and all(limit <= value + chord for limit in under)
    limits = _limits("printing.escape_hole_diameter", resolved)
    hollow = _limits("printing.hollow_wall", resolved)
    for item in _ok(report.get("trapped_volumes")).get("items") or ():
        # a mesh's wall round a hollow under the limit by no more than its chords stand off the surface: at it
        wall, chord = item.get("min_wall_mm"), item.get("min_wall_chord_mm")
        if isinstance(wall, (int, float)) and isinstance(chord, (int, float)) and "wall_at_limit" not in item:
            under = [limit for limit in hollow if wall < limit]
            item["wall_at_limit"] = bool(under) and all(limit <= wall + chord for limit in under)
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
    # A clearance the measurement's budget cut short (``exact`` false) is the least it found, and may be less by
    # its ``uncertainty_mm``: where a limit lies between the two, the rule cannot tell and the distance is not
    # measured (None; kept as ``distance_at_most_mm``) -- never a pass.
    limits = _limits("printing.clearance", resolved)
    for item in _ok(report.get("clearances")).get("items") or ():
        value, slack = item.get("distance_mm"), item.get("uncertainty_mm")
        if item.get("exact") is False and isinstance(value, (int, float)) and isinstance(slack, (int, float)) and \
                any(value - slack < limit <= value for limit in limits):
            item.update(distance_mm=None, distance_at_most_mm=value)


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
            # as a STEP's part of several solids is said (a mesh names no parts: its bodies are one part's)
            found.append(CheckFinding("warning", "several_solids", f"the mesh is {mesh['body_count']} separate "
                                      "bodies: a process makes a part of one solid; each is measured on its own, "
                                      "their clearances between", "mesh",
                                      "join them into one body (a union) if they are one piece; parts printed "
                                      "together in place are checked so"))
        for body in mesh.get("self_intersecting") or ():
            found.append(CheckFinding("error", "not_sound", f"the surface passes through itself (body "
                                      f"{body['body'] + 1}: {body['columns']} of {body['of']} lines up through it "
                         …10102 tokens truncated… mesh_result, check(tip, "tip", technology="sla")):
                with self.subTest(angle=angle, measured_as=result.measurements["source"]["measured_as"],
                                  technology=result.measurements.get("technology")):
                    self.assertEqual("printing.knife_edge" in codes(result), knife)
                    self.assertEqual(self.wall_failures(result), [])

    def test_a_curved_edge_is_a_knife_over_its_stretch_under_45_deg(self) -> None:
        # a 10 mm rod cut by a plane 60 deg from its axis: the edge's angle runs from 30 deg at the low side to 150
        # at the high side, a knife where it is under 45 deg alone, its sliver no wall
        rod = bd.Cylinder(5, 30, align=A)
        cut = rod - bd.Pos(0, 0, 20) * bd.Rotation(0, 60, 0) * bd.Box(80, 80, 40, align=A)
        result = check(cut, "rod")
        [knife] = items(result, "knife_edges")
        self.assertAlmostEqual(knife["angle_deg"], 30.0, delta=0.5)
        self.assertLess(knife["length_mm"], 0.5 * knife["edge_length_mm"])
        self.assertEqual(self.wall_failures(result), [])
        self.assertIn("printing.knife_edge", codes(result))

    def test_a_knife_s_least_angle_and_its_sliver_read_alike_on_every_technology_and_its_mesh(self) -> None:
        # a 10 mm rod cut 25 deg off its axis: its edge runs from 25 deg at the tip; the least is found between
        # the samples, whatever each technology's sampling, and its STL's walls leave the tip's sliver to the knife
        # though the edge's creases run on to 60 deg (each crease its own thin depth)
        rod = bd.Cylinder(5, 60) - bd.Rotation(0, 65, 0) * bd.Box(200, 200, 40,
                                                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        for technology in ("fdm", "sla", "sls"):
            [knife] = items(check(rod, "rod", technology=technology), "knife_edges")
            self.assertAlmostEqual(knife["angle_deg"], 25.0, delta=1e-3, msg=technology)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rod.stl"
            bd.export_stl(rod, str(path), tolerance=0.01, angular_tolerance=0.1)
            result = _dfm(str(path), process="printing", technology="fdm")
        self.assertEqual(self.wall_failures(result), [])
        self.assertIn("printing.knife_edge", codes(result))


class WallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cup = bd.Box(30, 30, 20, align=A) - bd.Pos(0, 0, 2) * bd.Box(28.8, 28.8, 20, align=A)
        fin = bd.Pos(40, 0, 0) * (bd.Box(20, 20, 2, align=A) + bd.Pos(0, 0, 2) * bd.Box(0.6, 15, 10, align=A))
        cls.result = check(cup + fin, "walls")

    def test_a_wall_joined_on_its_sides_is_supported_and_measured_exactly(self) -> None:
        wall = items(self.result, "wall_thickness", supported=True)[0]
        self.assertAlmostEqual(wall["thickness_mm"], 0.6, places=6)
        self.assertGreaterEqual(wall["joined_sides"], 2)
        self.assertIn("printing.wall_supported", codes(self.result))

    def test_a_wall_just_under_the_limit_fails_unrounded(self) -> None:
        part = bd.Box(20, 20, 2, align=A) + bd.Pos(0, 0, 2) * bd.Box(0.79996, 15, 10, align=A)
        result = check(part, "fin")
        fin = near(result, "wall_thickness", (0, 0, 7), 9.0, supported=False)
        self.assertAlmostEqual(fin["thickness_mm"], 0.79996, places=7)
        self.assertIn("printing.wall_unsupported", codes(result), "0.79996 mm is under 0.8, not rounded to it")

    def test_a_free_fin_is_unsupported(self) -> None:
        fin = near(self.result, "wall_thickness", (40, 0, 7), 9.0, supported=False)
        self.assertAlmostEqual(fin["thickness_mm"], 0.6, places=6)
        self.assertEqual(fin["joined_sides"], 1)
        self.assertIn("printing.wall_unsupported", codes(self.result))
        self.assertFalse(self.result.ok)

    def test_a_skin_over_a_cavity_is_supported(self) -> None:
        # 0.7 mm of material between a round cavity and the face above it: joined to the part all round, though
        # that face has no concave edge to count -- a supported wall (SLA's 0.5 mm), not a free one under 1.0 mm
        part = bd.Box(30, 30, 30) - bd.Pos(2.3, -3.1, 3.3) * bd.Sphere(11)
        result = check(part, "skin", technology="sla")
        skin = min(items(result, "wall_thickness"), key=lambda item: item["thickness_mm"])
        self.assertAlmostEqual(skin["thickness_mm"], 0.7, places=3)
        self.assertEqual((skin["supported"], skin["joined_sides"]), (True, 2))
        self.assertFalse([code for code in codes(result) if code.startswith("printing.wall")])


class ExactWallTest(unittest.TestCase):
    def test_a_face_at_45_deg_across_a_wall_is_its_far_side_in_every_placement(self) -> None:
        # a fin whose far side leans at exactly 45 degrees: a ray from its upright side lands on a face turned
        # KNIFE_DEG from it, a wall's far side however the part is turned about the plate's normal
        section = bd.make_face(bd.Polyline((0, 0), (1, 0), (11, 10), (0, 10), close=True))
        fin = bd.Box(30, 30, 2, align=A) + bd.Pos(-5, 0, 2) * bd.extrude(bd.Plane.XZ * section, 6, both=True)
        found = set()
        for turn in (0.0, 77.0, 88.0, 220.0):
            result = check(bd.Pos(11.1, -7.3, 0) * bd.Rotation(0, 0, turn) * fin, "lean")
            thinnest = min(item["thickness_mm"] for item in items(result, "wall_thickness"))
            found.add(round(thinnest, 6))
        self.assertEqual(len(found), 1, found)

    def test_a_web_between_two_holes_is_its_exact_least(self) -> None:
        # two 4 mm holes 5 mm apart: a 1 mm web the samples read wider; the gap between two 4 mm pins likewise
        plate = bd.Box(30, 20, 6, align=A) - bd.Pos(-2.5, 0, 0) * bd.Cylinder(2, 20) - bd.Pos(2.5, 0, 0) * bd.Cylinder(2, 20)
        web = min(items(check(plate, "web"), "wall_thickness"), key=lambda item: item["thickness_mm"])
        self.assertAlmostEqual(web["thickness_mm"], 1.0, places=6)
        self.assertTrue(web["refined"])
        pins = bd.Box(30, 20, 2, align=A) + bd.Pos(-1.3, 0, 2) * bd.Cylinder(2, 8, align=A) \
            + bd.Pos(3.3, 0, 2) * bd.Cylinder(2.2, 8, align=A)
        gap = min(items(check(pins, "pins"), "gaps"), key=lambda item: item["gap_mm"])
        self.assertAlmostEqual(gap["gap_mm"], 0.4, places=6)


class FeatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        block = bd.Box(60, 20, 20, align=A)
        across = bd.Pos(-20, 0, 10) * bd.Rotation(90, 0, 0) * bd.Cylinder(5, 40)
        drop = bd.Pos(0, 0, 10) * bd.Rotation(90, 0, 0) * (
            bd.Cylinder(3, 40) + bd.Rotation(0, 0, 45) * bd.Box(4.2426, 4.2426, 40, align=(bd.Align.MIN, bd.Align.MIN,
                                                                                         bd.Align.CENTER)))
        small = bd.Pos(20, 5, 0) * bd.Cylinder(0.4, 50)
        blind = bd.Pos(20, -5, 20) * bd.Cylinder(1, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        pin = bd.Pos(25, 0, 20) * bd.Cylinder(0.75, 13.5, align=A)
        cls.part = block - across - drop - small - blind + pin
        cls.fdm = check(cls.part, "features")
        cls.pbf = check(cls.part, "features", technology="pbf")

    def test_holes_are_cylinders_round_an_axis(self) -> None:
        small = near(self.fdm, "holes", (20, 5, 10), 1.0)
        self.assertEqual((small["diameter_mm"], small["orientation"], small["through"]), (0.8, "vertical", True))
        blind = near(self.fdm, "holes", (20, -5, 16), 1.0)
        self.assertEqual((blind["depth_mm"], blind["through"]), (8.0, False))
        self.assertIn("printing.hole_diameter", codes(self.fdm))

    def test_a_horizontal_hole_needs_a_teardrop_top_above_metals_limit(self) -> None:
        across = near(self.pbf, "holes", (-20, 0, 10), 1.0)
        drop = near(self.pbf, "holes", (0, 0, 10), 1.0)
        self.assertEqual((across["orientation"], across["teardrop"], drop["teardrop"]), ("horizontal", False, True))
        self.assertAlmostEqual(drop["coverage_deg"], 270.0, places=3)
        failing = [f for f in self.pbf.findings if f.code == "printing.horizontal_hole_diameter"]
        self.assertEqual([f.location for f in failing], [across["location"]], "Protolabs: 8 mm, teardrop above")

    def test_a_horizontal_hole_is_judged_by_its_diameter_not_as_a_bridge(self) -> None:
        hole = near(self.fdm, "holes", (-20, 0, 10), 1.0)
        self.assertEqual(items(self.fdm, "overhangs", location=hole["location"])[0]["kind"], "hole")
        self.assertEqual(items(self.fdm, "bridges"), [], "an arch stands layer on layer: no span")
        self.assertNotIn("printing.horizontal_hole", codes(self.fdm), "10 mm prints unsupported")
        wide = check(bd.Box(30, 10, 25, align=A) - bd.Pos(0, 0, 12) * bd.Rotation(90, 0, 0) * bd.Cylinder(7, 20), "wide")
        finding = next(f for f in wide.findings if f.code == "printing.horizontal_hole")
        self.assertEqual(finding.severity, "warning")
        self.assertRegex(finding.hint, "teardrop")
        self.assertNotIn("pillar", finding.hint)
        self.assertNotIn("printing.bridge_length", codes(wide))

    def test_a_pin_is_a_convex_cylinder_with_its_aspect(self) -> None:
        pin = near(self.pbf, "pins", (25, 0, 26.75), 1.0)
        self.assertEqual((pin["diameter_mm"], pin["height_mm"], pin["aspect_ratio"]), (1.5, 13.5, 9.0))
        self.assertIn("printing.pin_aspect", codes(self.pbf), "Hubs metal: 8:1")
        # Hubs FDM gives pins no minimum; Xometry's FDM tips do: "Pins should be at least 1 mm in diameter" --
        # a recommendation, a warning: this 1.5 mm pin passes, a 0.8 mm one is warned
        self.assertEqual([o["status"] for o in outcome(self.fdm, "printing.pin_diameter")], ["passed"])
        thin = check(bd.Box(20, 20, 3, align=A) + bd.Pos(0, 0, 3) * bd.Cylinder(0.4, 6, align=A), "thin_pin")
        finding = next(f for f in thin.findings if f.code == "printing.pin_diameter")
        self.assertEqual(finding.severity, "warning")
        self.assertIn("Xometry", finding.source)  # where the limit comes from is the finding's own field


class DetailAndGapTest(unittest.TestCase):
    def test_embossed_and_engraved_steps_and_a_slot(self) -> None:
        base = bd.Box(60, 20, 4, align=A)
        raised = bd.Pos(-20, 0, 4) * bd.Box(2, 10, 0.5, align=A)
        groove = bd.Pos(0, 0, 4) * bd.Box(0.3, 10, 0.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        slot = bd.Pos(20, 0, 4) * bd.Box(0.4, 30, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        part = base + raised - groove - slot
        sla, sls = check(part, "details", technology="sla"), check(part, "details", technology="sls")
        emboss = items(sla, "details", kind="emboss")[0]
        self.assertEqual((emboss["height_mm"], emboss["width_mm"]), (0.5, 2.0))
        engrave = near(sla, "details", (0, 0, 3.5), 6.0, kind="engrave")
        self.assertEqual((engrave["height_mm"], engrave["width_mm"]), (0.5, 0.3))
        self.assertIn("printing.engrave_width", codes(sla), "Hubs SLA: 0.4 mm wide")
        self.assertIn("printing.emboss_height", codes(sls), "Hubs SLS: 1 mm high")
        widths = sorted(item["gap_mm"] for item in items(sla, "gaps"))
        self.assertEqual(widths[:2], [0.3, 0.4])
        self.assertEqual(codes(sla).count("printing.gap"), 2, "Protolabs SLA: 0.635 mm")

    def test_a_wide_step_is_geometry_not_a_detail(self) -> None:
        # a 30 mm locating land 0.8 high and a 6 mm groove 0.5 deep: the part's shape, not text
        land = bd.Box(40, 40, 3, align=A) + bd.Pos(0, 0, 3) * bd.Box(30, 30, 0.8, align=A)
        land -= bd.Pos(0, 0, 3.8) * bd.Box(6, 20, 0.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        result = check(land, "land", technology="sls")
        self.assertEqual(items(result, "details"), [])
        self.assertNotIn("printing.emboss_height", codes(result))

    def test_a_narrow_step_running_across_the_face_is_geometry_not_a_detail(self) -> None:
        # a 2 mm strip 0.2 high from one side of the block to the other (a hinge knuckle's shoulder), beside a
        # 2 mm island of the same height: only the island is raised text
        part = bd.Box(30, 10, 4, align=A) + bd.Pos(-8, 0, 4) * bd.Box(2, 10, 0.2, align=A)
        part += bd.Pos(8, 0, 4) * bd.Box(2, 4, 0.2, align=A)
        found = items(check(part, "strip", technology="sls"), "details")
        self.assertEqual([(item["kind"], item["xyz"][0] > 0) for item in found], [("emboss", True)])


    def test_a_detail_with_round_sides_is_a_detail(self) -> None:
        # a 2 mm square island with 0.4 mm corner rounds and a 2.4 mm dot, both 0.5 high, and a 0.3 mm round-ended
        # groove 0.5 deep: their sides are cylinders, and each is raised or sunk text all the same
        part = bd.Box(40, 12, 4, align=A)
        part += bd.Pos(-12, 0, 4) * bd.fillet(bd.Box(2, 2, 0.5, align=A).edges().filter_by(bd.Axis.Z), 0.4)
        part += bd.Pos(0, 0, 4) * bd.Cylinder(1.2, 0.5, align=A)
        part -= bd.Pos(12, 0, 4) * bd.extrude(bd.SlotCenterToCenter(6, 0.3), amount=-0.5)
        found = sorted((item["kind"], round(item["xyz"][0] / 12)) for item in items(check(part, "dots", technology="sls"),
                                                                                     "details"))
        self.assertEqual(found, [("emboss", -1), ("emboss", 0), ("engrave", 1)])


class AssemblyTest(unittest.TestCase):
    def test_the_least_distance_between_parts(self) -> None:
        a, b, c = bd.Box(10, 10, 10, align=A), bd.Pos(10.2, 0, 0) * bd.Box(10, 10, 10, align=A), \
            bd.Pos(0, 10, 0) * bd.Box(10, 10, 10, align=A)
        a.label, b.label, c.label = "a", "b", "c"
        result = check(bd.Compound(children=[a, b, c]), "pair", technology="mjf")
        found = {tuple(item["parts"]): item for item in result.measurements["clearances"]["items"]}
        self.assertAlmostEqual(found[("a", "b")]["distance_mm"], 0.2, places=6)
        self.assertEqual(found[("a", "c")]["kind"], "contact")
        self.assertGreaterEqual(codes(result).count("printing.clearance"), 2, "Hubs MJF: 0.9 mm printed assembled")
        clearance = next(f for f in result.findings if f.code == "printing.clearance")
        self.assertIn("print-in-place", clearance.hint)
        self.assertIn("checked by its own id", clearance.hint)

    def test_an_assemblys_overhangs_are_said_to_be_measured_in_place(self) -> None:
        post, arm = bd.Box(10, 10, 20, align=A), bd.Pos(12, 0, 20) * bd.Box(14, 10, 3, align=A)
        post.label, arm.label = "post", "arm"
        result = check(bd.Compound(children=[post, arm]), "pair")
        overhangs = next(f for f in result.findings if f.code == "overhangs")
        self.assertIn("print-in-place", overhangs.message)
        self.assertRegex(overhangs.hint, "turn the part")


class TrappedTest(unittest.TestCase):
    sealed = bd.Box(30, 30, 30, align=A) - bd.Pos(0, 0, 3) * bd.Box(24, 24, 24, align=A)

    def test_one_cut_through_two_walls_is_two_exact_holes(self) -> None:
        # a 40 mm hollow, 2.5 mm walls, drained by one 3.4 mm cylinder through both: two holes of 3.4, exactly,
        # and no voxel crumb at an inner corner read as a sealed cavity
        hollow = bd.Box(40, 40, 40, align=A) - bd.Pos(0, 0, 2.5) * bd.Box(35, 35, 35, align=A)
        for diameter in (3.0, 3.4):
            drained = hollow - bd.Pos(0, 0, 20) * bd.Rotation(0, 90, 0) * bd.Cylinder(diameter / 2, 50)
            result = check(drained, "drained", technology="sls")
            cavities = items(result, "trapped_volumes")
            self.assertEqual(len(cavities), 1, cavities)
            self.assertEqual(cavities[0]["escape_hole_diameters_mm"], [diameter, diameter])
            self.assertNotIn("printing.escape_holes", codes(result))
            self.assertIn("printing.escape_hole_diameter", codes(result), "Hubs SLS: 3.5 mm")

    def test_an_inner_shell_is_a_sealed_void_measured_exactly(self) -> None:
        result = check(self.sealed, "sealed", technology="sls")
        void = items(result, "trapped_volumes")[0]
        self.assertEqual((void["exact"], void["sealed"], void["escape_holes"]), (True, True, 0))
        self.assertAlmostEqual(void["volume_mm3"], 24 ** 3, places=3)
        self.assertAlmostEqual(void["min_wall_mm"], 3.0, places=6)
        self.assertIn("printing.escape_holes", codes(result))
        self.assertFalse(result.ok, "powder sealed in is no part")
        fdm = check(self.sealed, "sealed")
        self.assertIn("internal_void", codes(fdm))
        self.assertNotIn("printing.escape_holes", codes(fdm))

    def test_a_hollow_drains_through_its_exact_holes(self) -> None:
        drained = self.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2, 5, align=A) - bd.Pos(0, 0, 26) * bd.Cylinder(1, 6, align=A)
        result = check(drained, "drained", technology="sla")
        hollow = items(result, "trapped_volumes")[0]
        self.assertEqual((hollow["sealed"], hollow["escape_holes"], hollow["escape_hole_diameters_mm"]),
                         (False, 2, [2.0, 4.0]))
        self.assertAlmostEqual(hollow["volume_mm3"], 24 ** 3, delta=0.15 * 24 ** 3)
        self.assertIn("printing.escape_hole_diameter", codes(result), "Hubs SLA: 3.5 mm")
        self.assertNotIn("printing.escape_holes", codes(result))

    def test_a_flat_hollow_behind_a_small_vent_is_a_cavity_whatever_its_shape(self) -> None:
        # 40 x 40 x 6 mm of air behind one 2 mm vent: a ball a fifth of the part across does not fit in it, and
        # it holds 9600 mm3 of powder all the same -- a cavity is air wider than its way out
        block = bd.Box(50, 50, 16) - bd.Box(40, 40, 6)
        for vent, read in ((bd.Pos(0, 0, 5) * bd.Cylinder(1, 8), "its exact hole"),
                           (bd.Pos(0, 0, 5) * bd.Box(2, 2, 8), "a square vent, its throat measured")):
            with self.subTest(opening=read):
                result = check(block - vent, "hollow", technology="sls")
                [cavity] = items(result, "trapped_volumes")
                self.assertEqual((cavity["sealed"], cavity["escape_holes"]), (False, 1))
                self.assertAlmostEqual(cavity["min_escape_hole_mm"], 2.0, delta=0.03)
                self.assertAlmostEqual(cavity["volume_mm3"], 40 * 40 * 6, delta=0.05 * 9600)
                self.assertEqual([f.severity for f in result.findings if f.code == "printing.escape_hole_diameter"],
                                 ["warning"])
                self.assertNotIn("printing.escape_holes", codes(result))

    def test_powder_beds_other_than_sls_say_the_figure_is_applied(self) -> None:
        for technology, applied in (("sls", False), ("mjf", True), ("pbf", True)):
            failed = next(f for f in check(self.sealed, "sealed", technology=technology).findings
                          if f.code == "printing.escape_holes")
            self.assertEqual("Hubs's SLS figure, applied" in failed.message, applied, technology)


class PlateTest(unittest.TestCase):
    def test_the_build_volume_lying_the_best_way(self) -> None:
        # a 250 mm bar lies across the corners of a 200 x 200 bed, turned 45 deg -- smallest on its 10 mm side
        fit = check(bd.Box(250, 20, 10, align=A), "bar").measurements["build_volume"]
        self.assertEqual((fit["fits"], fit["upright"], fit["turn_deg"], fit["volume_mm"]),
                         (True, "y", 45.0, [200.0, 200.0, 200.0]))
        self.assertAlmostEqual(fit["fill_ratio"], (250 + 10) / math.sqrt(2) / 200, places=6)
        self.assertEqual((fit["as_placed_fill_ratio"], fit["max_dimension_mm"]), (1.25, 250.0))
        # a 400 mm one fits no way, not from corner to corner of the volume (346 mm)
        bar = bd.Box(400, 20, 10, align=A)
        result = check(bar, "bar")
        fit = result.measurements["build_volume"]
        self.assertFalse(fit["fits"])
        self.assertGreater(fit["fill_ratio"], 1.1)
        # against a typical machine assumed, a warning that names it; against the machine given, an error
        assumed = next(f for f in result.findings if f.code == "printing.build_volume")
        self.assertEqual(assumed.severity, "warning")
        self.assertIn("an assumed typical fdm machine, 200 x 200 x 200 mm: give --build-volume", assumed.message)
        given = check(bar, "bar", build_volume="200x200x200")
        self.assertEqual([f.severity for f in given.findings if f.code == "printing.build_volume"], ["error"])
        self.assertFalse(given.ok)
        self.assertTrue(check(bar, "bar", build_volume="100x100x450").measurements["build_volume"]["fits"])
        self.assertTrue(check(bar, "bar", build_volume="900x600x900").ok, "an industrial FDM machine")

    def test_a_part_past_the_largest_machine_listed_is_an_error(self) -> None:
        # no machine given: over the typical machine is a warning (give yours), over the largest the guide lists
        # lying every way is no part any machine of the technology makes -- one finding either way. A bed has
        # no preferred diagonal: a 950 mm rod lies across the 900 x 600 bed's corners (1081 mm), a 1300 mm one
        # from a corner of the volume to the one opposite (1407 mm), a 1500 mm one no way
        for length, severity, said in ((850, "warning", "an assumed typical fdm machine"),
                                       (950, "warning", "an assumed typical fdm machine"),
                                       (1300, "warning", "an assumed typical fdm machine"),
                                       (1500, "error", "the largest fdm machine the guide lists is 900 x 600 x 900")):
            result = check(bd.Box(length, 20, 10, align=A), "bar")
            [found] = [f for f in result.findings if f.code == "printing.build_volume"]
            self.assertEqual(found.severity, severity, length)
            self.assertIn(said, found.message)
            self.assertEqual(result.ok, severity == "warning")
            self.assertEqual(result.measurements["build_volume"]["fits_largest"], severity == "warning")
        self.assertTrue(check(bd.Box(950, 20, 10, align=A), "bar", build_volume="1000x500x500").ok)

    def test_the_fit_does_not_turn_with_how_the_part_stands(self) -> None:
        # a 370 x 280 x 5 plate in MJF's 380 x 285 x 380: it fits flat however it is turned about the plate's
        # axis or tilted in space, its length (the longest side of its tightest box) is 370 either way, and a
        # cube exactly the volume's size fits it at any tilt
        plate = bd.Box(370, 280, 5, align=A)
        odd = bd.Axis((0, 0, 0), (1, 2, 3))
        for name, shape in (("flat", plate), ("turned", plate.rotate(bd.Axis.Z, 45)),
                            ("turned oddly", plate.rotate(bd.Axis.Z, 12.3456)), ("tilted", plate.rotate(odd, 37))):
            result = check(shape, "plate", technology="mjf")
            fit = result.measurements["build_volume"]
            with self.subTest(way=name):
                self.assertNotIn("printing.build_volume", codes(result))
                self.assertTrue(fit["fits"])
                self.assertAlmostEqual(fit["max_dimension_mm"], 370.0, delta=1e-3)
                self.assertEqual([f.value for f in result.findings if f.code == "printing.warp_length"],
                                 [fit["max_dimension_mm"]])
        cube = bd.Box(200, 200, 200, align=A)
        for shape in (cube, cube.rotate(bd.Axis.Z, 30), cube.rotate(odd, 37)):
            fit = measured.measure(brep.parts_of(shape, "cube"), {**rules.OPTIONS, "technology": "fdm"}, False)["build_volume"]
            self.assertEqual((fit["fill_ratio"], fit["fits"]), (1.0, True))

    def test_bed_contact_and_warping(self) -> None:
        result = check(bd.Box(150, 40, 3, align=A), "flat", material="abs")
        bed = result.measurements["bed"]
        self.assertAlmostEqual(bed["contact_area_mm2"], 6000.0, places=3)
        self.assertEqual(bed["contact_length_mm"], 150.0)
        self.assertIn("warping_risk", codes(result))
        self.assertNotIn("warping_risk", codes(check(bd.Box(150, 40, 3, align=A), "flat", material="pla")))

    def test_a_shallow_slope_stair_steps(self) -> None:
        ramp = bd.Rotation(90, 0, 0) * bd.extrude(bd.make_face(bd.Polyline(
            (0, 0), (40, 0), (40, 40 * math.tan(math.radians(10))), (0, 0))), 10)
        result = check(ramp, "ramp", layer_height=0.3)
        step = items(result, "stair_stepping")[0]
        self.assertAlmostEqual(step["angle_deg"], 10.0, places=6)
        self.assertAlmostEqual(step["cusp_mm"], 0.3 * math.cos(math.radians(10)), places=4)
        self.assertAlmostEqual(result.measurements["stair_stepping"]["area_mm2"], 400 / math.cos(math.radians(10)),
                               delta=0.5)

    def test_an_unsound_part_names_the_kernel_s_status_and_every_face_it_faults(self) -> None:
        # two boxes overlapping in one part: the boolean check's BOPAlgo_SelfIntersect, on the faces that cross
        box = bd.Solid.make_box(10, 10, 10)
        for place in (bd.Pos(0, 0, 0), bd.Rot(0, 0, 30) * bd.Pos(3, -2, 0)):
            pair = bd.Compound([place * box, place * bd.Pos(5, 0, 0) * box])
            result = check(pair, "pair")
            (item,) = result.measurements["solid"]["items"]
            self.assertEqual((item["sound"], item["issues"]), (False, ["BOPAlgo_SelfIntersect"]), place)
            self.assertGreaterEqual(len(item["faulty_faces"]), 2)
            finding = next(f for f in result.findings if f.code == "not_sound")
            self.assertEqual(finding.location, item["faulty_faces"][0])
            named = ", ".join(face.rsplit("/", 1)[-1] for face in item["faulty_faces"])
            self.assertIn(f"(BOPAlgo_SelfIntersect on {named})", finding.message)

    def test_an_open_or_unsound_part_is_an_error(self) -> None:
        report = {"solid": {"items": [{"part": "lid", "location": "lid/face 1", "closed": False, "sound": False,
                                       "issues": ["BRepCheck_NotClosed"]}], "body_count": 1, "part_count": 1}}
        found = {f.code: f for f in rules.findings(report, {"technology": "fdm"}, False)}
        self.assertEqual((found["not_watertight"].severity, found["not_sound"].severity), ("error", "error"))
        mesh = {"mesh": {"watertight": False, "open_body_count": 1, "body_count": 1,
                         "open_bodies": [{"xyz": [1.0, 2.0, 3.0], "boundary_edges": 4, "area_mm2": 500.0}]}}
        said = next(f for f in rules.findings(mesh, {"technology": "fdm"}, False) if f.code == "not_watertight")
        self.assertEqual((said.severity, said.location), ("error", "1, 2, 3"))
        self.assertIn("4 open edge(s)", said.message)

    def test_a_sound_closed_solid(self) -> None:
        solid = check(bd.Box(10, 10, 10), "box").measurements["solid"]
        self.assertEqual((solid["watertight"], solid["sound"], solid["body_count"]), (True, True, 1))
        self.assertAlmostEqual(solid["volume_mm3"], 1000.0, places=6)


class TurnedOnThePlateTest(unittest.TestCase):
    def test_a_part_turned_about_z_reads_the_same_on_both_paths(self) -> None:
        # turned on the plate, nothing it stands on changes: the verdicts, the overhangs, the walls, the support
        part = tee() + bd.Pos(-12, 3, 20) * bd.Box(0.6, 4, 4, align=A)

        def read(result):
            m = result.measurements
            return (result.ok, sorted({f.code for f in result.findings if f.severity != "info"}),
                    m["overhangs"]["down_facing_area_below_limit_mm2"], m["wall_thickness"]["min_mm"],
                    m["support_volume"]["estimated_support_volume_mm3"])

        with tempfile.TemporaryDirectory() as folder:
            seen = {}
            for turn in (0, 30, 90, -17):
                shape = bd.Rot(0, 0, turn) * part
                path = Path(folder) / f"tee{turn}.stl"
                bd.export_stl(shape, str(path))
                seen[turn] = (read(check(shape, "tee")), read(_dfm(path, process="printing")))
        for turn, paths in seen.items():
            for at, (base, turned) in enumerate(zip(seen[0], paths)):
                with self.subTest(turn=turn, path=("brep", "mesh")[at]):
                    self.assertEqual(turned[:2], base[:2])
                    for value, reference in zip(turned[2:], base[2:]):
                        self.assertAlmostEqual(value, reference, delta=0.01 * reference + 0.05)


class OrientationTest(unittest.TestCase):
    def test_candidates_rank_by_the_stated_weighting(self) -> None:
        result = cad.build123d.printing(wedge(30.0), candidates=True)
        ranked = result.measurements["orientations"]
        rows = ranked["candidates"]
        self.assertGreaterEqual(len(rows), 6)
        self.assertEqual(ranked["weights"], mo.WEIGHTS["support"])
        self.assertEqual(rows[0]["support_volume_mm3"], 0.0)
        current = next(row for row in rows if row["orientation"] == "current_plus_z")
        self.assertGreater(current["support_volume_mm3"], 0.0)
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertIn("orientations ranked", result.summary)
        for row in rows:  # each row's rotation, pasteable: bd.Rot(...) makes its matrix
            placed = eval(row["rotate"], {"bd": bd}).wrapped.Transformation()
            matrix = [[placed.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]
            np.testing.assert_allclose(matrix, row["rotation"], atol=1e-4, err_msg=row["rotate"])
            self.assertIn(row["rotate"], result.summary)


class StepTest(unittest.TestCase):
    def test_a_step_is_measured_on_its_b_rep_at_refs_the_engine_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tunnel.step"
            part = tunnel(8.0)
            part.label = "tunnel"
            bd.export_step(part, str(path))
            result = cad.step.dfm(path, process="printing", technology="sla")
        self.assertEqual(result.measurements["source"]["measured_as"], "brep")
        bridge = items(result, "bridges", kind="bridge")[0]
        self.assertAlmostEqual(bridge["length_mm"], 8.0, places=4)
        self.assertRegex(bridge["location"], r"^tunnel/face \d+$")


class RulesTest(unittest.TestCase):
    def test_the_rules_cite_every_rule_and_key_their_limits_by_technology(self) -> None:
        cited = {source.id for source in rules.RULES.sources}
        for rule in rules.RULES.rules:
            self.assertIn(rule.source, cited)
            self.assertTrue(rule.id.startswith("printing."))
            self.assertEqual(rule.by, "technology")
            self.assertTrue(set(rule.limit) <= set(rules.TECHNOLOGIES), rule.id)

    def test_one_guide_gives_a_technology_each_figure(self) -> None:
        # no row a rule can never apply: per rule id and technology, one source (the table's dead rows are gone)
        sources: dict[tuple[str, str], set[str]] = {}
        for rule in rules.RULES.rules:
            if rule.scale_by is None:  # --angle-limit's and --nozzle's own variants restate the same rows
                for technology in rule.limit:
                    sources.setdefault((rule.id, technology), set()).add(rule.source)
        self.assertEqual({key: found for key, found in sources.items() if len(found) > 1}, {})
        self.assertEqual({source.id for source in rules.RULES.sources},
                         {rule.source for rule in rules.RULES.rules} | {"hubs-geometry"}, "every source cited is used")

    def test_fdm_s_wall_is_two_beads_of_the_nozzle(self) -> None:
        # Hubs's 0.8 mm is two beads of the common 0.4 mm nozzle, and says so; with the nozzle given, two of its
        fin = bd.Box(20, 20, 2, align=A) + bd.Pos(0, 0, 2) * bd.Box(0.6, 15, 10, align=A)
        for nozzle, limit in ((None, 0.8), (0.25, 0.5), (0.6, 1.2)):
            result = check(fin, "fin") if nozzle is None else check(fin, "fin", nozzle=nozzle)
            walls = [f for f in result.findings if f.code == "printing.wall_unsupported"]
            with self.subTest(nozzle=nozzle):
                self.assertEqual(bool(walls), 0.6 < limit)
                self.assertEqual(result.measurements["knife_edges"]["min_wall_mm"], limit)
                # where the limit comes from is the finding's ``source``, never its message
                if nozzle is None:
                    self.assertIn("assuming the common 0.4 mm nozzle: give --nozzle", walls[0].message)
                    self.assertTrue(walls[0].source.startswith("Protolabs Network (Hubs), "), walls[0].source)
                    self.assertEqual((walls[0].value, walls[0].limit, walls[0].unit, walls[0].op), (0.6, 0.8, "mm", "min"))
                elif walls:
                    self.assertIn("2 beads of the 0.6 mm nozzle given", walls[0].message)
                    self.assertTrue(walls[0].source.startswith("cad, its own figure"), walls[0].source)
                    self.assertEqual((walls[0].value, walls[0].limit), (0.6, 1.2))

    def test_rules_with_no_figure_for_the_technology_judge_nothing_and_say_so(self) -> None:
        import dataclasses
        from unittest import mock

        # rules for every technology but FDM: an FDM part is judged by none of them
        others = dataclasses.replace(rules.RULES, rules=tuple(rule for rule in rules.RULES.rules
                                                              if "fdm" not in rule.limit))
        plate = bd.Pos(0, 0, 2.5) * (bd.Box(20, 20, 5) - bd.Cylinder(0.4, 5))
        with mock.patch.object(rules, "RULES", others):
            result = check(plate, "plate", technology="fdm")
        self.assertEqual([o["status"] for o in outcome(result, "printing.hole_diameter")], ["not_evaluated"])
        self.assertEqual(result.measurements["rules"]["evaluated"], 0)
        self.assertNotIn("passed", {o["status"] for o in result.measurements["rules"]["outcomes"]})
        warned = next(f for f in result.findings if f.code == "rules_none_evaluated")
        self.assertEqual(warned.severity, "warning")
        self.assertEqual(result.findings[0].code, "rules_none_evaluated", "said first")
        self.assertIn("nothing judged", result.summary)

    def test_a_technology_a_source_does_not_cover_is_not_evaluated_never_passed(self) -> None:
        result = check(bd.Box(20, 20, 5) - bd.Cylinder(0.3, 10), "plate", technology="mjf")
        hole = outcome(result, "printing.hole_diameter")
        self.assertTrue(all(o["status"] in ("not_evaluated", "not_applicable") for o in hole) or not hole)
        self.assertNotIn("printing.hole_diameter", codes(result))

    def test_options_are_refused_by_name(self) -> None:
        for given, said in (({"technology": "sla", "nozzle": 0.4}, "--nozzle is FDM's"),
                            ({"build_volume": "200x200"}, "--build-volume is three lengths"),
                            ({"angle_limit": 91}, "--angle-limit is an angle"),
                            ({"layer_height": 0}, "--layer-height is a length"),
                            ({"material": "aluminum"}, "aluminum is a metal, and --technology fdm prints a plastic"),
                            ({"material": "pla", "technology": "pbf"}, "--technology pbf prints a metal")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("step", "printing", given)
        self.assertIsNotNone(manufacturing.options("step", "printing", {"material": "titanium", "technology": "pbf"}))
        assumed = rules.machine_volume({"technology": "pbf"})
        self.assertEqual(assumed["volume_mm"], [250.0, 150.0, 150.0])
        self.assertTrue(assumed["origin"].startswith("assumed"))


class PrinterFileTest(unittest.TestCase):
    """``--printer FILE``: the printer's volume and nozzle read from a slicer's 3MF or a machine preset JSON."""

    SETTINGS = {"printable_area": ["0x0", "256x0", "256x256", "0x256"], "printable_height": "250",
                "nozzle_diameter": ["0.4"], "printer_settings_id": "Test X1 0.4 nozzle"}

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def threemf(self, settings: dict, name: str = "job.gcode.3mf") -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("3D/3dmodel.model", "<model/>")
            archive.writestr("Metadata/project_settings.config", json.dumps(settings))
        return path

    def preset(self, settings: dict, name: str = "machine.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(settings), encoding="utf-8")
        return path

    def test_a_3mf_and_a_json_give_the_volume_and_the_nozzle(self) -> None:
        preset = {"name": "Test preset", **{k: v for k, v in self.SETTINGS.items() if k != "printer_settings_id"}}
        for path, name in ((self.threemf(self.SETTINGS), "Test X1 0.4 nozzle"),
                           (self.preset(self.SETTINGS), "Test X1 0.4 nozzle"),
                           (self.preset(preset, "named.json"), "Test preset")):
            resolved = manufacturing.options("stl", "printing", {"printer": path})
            with self.subTest(path=path.name):
                self.assertEqual((resolved["build_volume"], resolved["nozzle"]), ("256x256x250", 0.4))
                self.assertEqual(resolved["printer"], {"name": name, "file": str(path),
                                                       "supplied": ["build_volume", "nozzle"]})
                machine = rules.machine_volume(resolved)
                self.assertEqual(machine["volume_mm"], [256.0, 256.0, 250.0])
                self.assertEqual(machine["origin"], f"printer {name} ({path}, bed bounding box)")
        self.assertEqual(rules.printer_settings(self.preset({**self.SETTINGS, "name": "", "printer_settings_id": ""},
                                                            "bare.json"))["name"], "bare.json")

    def test_the_bed_polygon_and_the_comma_joined_forms(self) -> None:
        settings = {"printable_area": "10x5,266x5,266x261,10x261", "printable_height": 300,
                    "nozzle_diameter": "0.6,0.4"}
        printer = rules.printer_settings(self.preset(settings))
        self.assertEqual((printer["volume_mm"], printer["nozzle"]), ([256.0, 256.0, 300.0], 0.6))
        no_nozzle = rules.printer_settings(self.preset({k: v for k, v in settings.items() if k != "nozzle_diameter"}))
        self.assertIsNone(no_nozzle["nozzle"])
        resolved = manufacturing.options("stl", "printing", {"printer": self.preset(settings, "b.json")})
        self.assertEqual(resolved["nozzle"], 0.6)

    def test_over_the_printer_s_volume_is_an_error_naming_the_printer(self) -> None:
        path = self.threemf(self.SETTINGS)
        long_bar = bd.Box(500, 20, 10, align=A)
        result = check(long_bar, "bar", printer=path)
        fit = result.measurements["build_volume"]
        self.assertEqual((fit["fits"], fit["volume_mm"]), (False, [256.0, 256.0, 250.0]))
        self.assertEqual(fit["volume_origin"], f"printer Test X1 0.4 nozzle ({path}, bed bounding box)")
        [found] = [f for f in result.findings if f.code == "printing.build_volume"]
        self.assertEqual(found.severity, "error")
        self.assertIn("256 x 256 x 250 mm volume of printer Test X1 0.4 nozzle", found.message)
        self.assertNotIn("machine given", found.message)
        self.assertFalse(result.ok)
        self.assertTrue(check(bd.Box(240, 20, 10, align=A), "bar", printer=str(path)).ok)

    def test_build_volume_and_nozzle_given_win(self) -> None:
        path = self.threemf({**self.SETTINGS, "nozzle_diameter": ["0.6"]})
        resolved = manufacturing.options("stl", "printing", {"printer": path, "build_volume": "100x100x100",
                                                              "nozzle": 0.25})
        self.assertEqual((resolved["build_volume"], resolved["nozzle"], resolved["printer"]["supplied"]),
                         ("100x100x100", 0.25, []))
        bar = bd.Box(150, 20, 10, align=A)
        result = check(bar, "bar", printer=path, build_volume="100x100x100")
        self.assertEqual(result.measurements["build_volume"]["volume_origin"], "given")
        self.assertIn("machine given", next(f for f in result.findings if f.code == "printing.build_volume").message)
        self.assertTrue(check(bar, "bar", printer=path).ok, "150 mm fits the printer's 256")

    def test_the_printer_s_nozzle_is_a_nozzle_given(self) -> None:
        fin = bd.Box(20, 20, 2, align=A) + bd.Pos(0, 0, 2) * bd.Box(0.6, 15, 10, align=A)
        result = check(fin, "fin", printer=self.threemf({**self.SETTINGS, "nozzle_diameter": ["0.6"]}))
        self.assertEqual(result.measurements["knife_edges"]["min_wall_mm"], 1.2)
        [wall] = [f for f in result.findings if f.code == "printing.wall_unsupported"]
        self.assertIn("2 beads of the 0.6 mm nozzle given", wall.message)

    def test_a_file_that_is_no_printer_is_refused_naming_it(self) -> None:
        plain = self.root / "plain.3mf"
        with zipfile.ZipFile(plain, "w") as archive:
            archive.writestr("3D/3dmodel.model", "<model/>")
        text = self.root / "notes.txt"
        text.write_text("not json", encoding="utf-8")
        listed = self.root / "list.json"
        listed.write_text("[1]", encoding="utf-8")
        child = self.preset({"name": "child", "inherits": "Parent 0.4", "nozzle_diameter": ["0.4"]}, "child.json")
        for path, said in ((self.root / "gone.3mf", "gone.3mf is not a file"),
                           (plain, "plain.3mf holds no Metadata/project_settings.config"),
                           (text, "notes.txt is neither a 3MF"), (listed, "list.json is JSON but not an object"),
                           (self.preset({"nozzle_diameter": ["0.4"]}, "bare.json"),
                            "bare.json holds no printable_area, printable_height"),
                           (self.preset({"printable_area": ["0x0", "9"], "printable_height": "5"}, "points.json"),
                            "points.json: printable_area is points"),
                           (self.preset({**self.SETTINGS, "nozzle_diameter": ["wide"]}, "nozzle.json"),
                            "nozzle.json: nozzle_diameter is a length"),
                           (self.preset({**self.SETTINGS, "printable_height": "0"}, "flat.json"),
                            "not three lengths above 0")):
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("stl", "printing", {"printer": path})
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, re.escape(str(path))):
                manufacturing.options("stl", "printing", {"printer": path})
        with self.assertRaisesRegex(ValueError, r"a preset holding only its differences from 'Parent 0\.4'.*give a 3MF "
                                                r"the slicer saved.*--build-volume and --nozzle"):
            manufacturing.options("stl", "printing", {"printer": child})

    def test_only_fdm_takes_a_printer(self) -> None:
        with self.assertRaisesRegex(ValueError, "--printer is FDM's"):
            manufacturing.options("step", "printing", {"printer": self.threemf(self.SETTINGS), "technology": "sla"})
        with self.assertRaisesRegex(ValueError, "printer is FDM's"):
            check(bd.Box(10, 10, 10), "box", printer=self.threemf(self.SETTINGS), technology="mjf")
        with self.assertRaisesRegex(ValueError, "--printer is not cnc's"):
            manufacturing.options("step", "cnc", {"printer": self.threemf(self.SETTINGS)})

    def test_a_relative_path_is_made_absolute_where_it_is_given(self) -> None:
        path = self.threemf(self.SETTINGS)
        before = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, before)
        resolved = manufacturing.options("stl", "printing", {"printer": path.name})
        self.assertEqual(resolved["printer"]["file"], os.path.abspath(path.name))
        spelled = manufacturing._spelled({"printer": Path(path.name)})
        self.assertEqual(spelled["printer"], os.path.abspath(path.name), "an unresolved option sent on")
        with self.assertRaisesRegex(ValueError, "--printer is text, not 3"):
            manufacturing.options("stl", "printing", {"printer": 3})


class SeamTest(unittest.TestCase):
    def test_a_wall_ray_that_re_hits_its_neighbour_at_the_seam_is_no_wall(self) -> None:
        # B-spline robot parts give 0.0003-0.008 mm "walls" between faces sharing an edge: a sample on the
        # seam re-hitting the neighbour. A hit that near on a neighbour is dropped; on a far face it is a wall.
        ctx = measured.Context(brep.parts_of(bd.Box(10, 10, 10, align=A), "box"),
                               {**rules.OPTIONS, "technology": "fdm"})
        face = ctx.faces[0][0]
        neighbour = next(iter(ctx.adjacent(0, face.ordinal)))
        far = next(info.ordinal for info in ctx.faces[0]
                   if info.ordinal != face.ordinal and info.ordinal not in ctx.adjacent(0, face.ordinal))
        original = measured._first_hits

        from OCP.BRepTools import BRepTools

        def middle(ordinal):  # a crossing's (u, v): the face's middle, where its normal faces the ray
            umin, umax, vmin, vmax = BRepTools.UVBounds_s(ctx.info(0, ordinal).face.wrapped)
            return (umin + umax) / 2, (vmin + vmax) / 2

        def fake(rays, points, directions, start, end, chunk=64):
            if end < 1e6:  # the gap rays: none
                return [None] * len(points)
            owners = [(info.ordinal, k) for info in ctx.faces[0] for k in range(len(info.samples))]
            return [(0.001, neighbour - 1, *middle(neighbour)) if (o, k) == (face.ordinal, 0) else
                    (0.001, far - 1, *middle(far)) if (o, k) == (face.ordinal, 1) else None for o, k in owners]

        measured._first_hits = fake
        try:
            ctx.measure_rays()
        finally:
            measured._first_hits = original
        self.assertEqual([(t, k, other) for t, k, other in face.thickness], [(0.001, 1, far)])
        self.assertGreater(measured.SEAM_HIT_MM, 0.001)
        self.assertLess(measured.SEAM_HIT_MM, 0.3, "under every published minimum wall")


class MeshopsTest(unittest.TestCase):
    def test_support_and_cavities_of_a_triangulation(self) -> None:
        V, F, _ = brep.triangles(tee(), 0.05)
        self.assertAlmostEqual(mo.support(V, F, 45.0, 0.5)["volume_mm3"], 4000.0, delta=1.0)
        hollow = TrappedTest.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2, 5, align=A) - \
            bd.Pos(8, 8, -1) * bd.Cylinder(2, 5, align=A)
        V, F, _ = brep.triangles(hollow, 0.02)
        pitch, ball = mo.field_pitch(V.max(axis=0) - V.min(axis=0))
        found, labels = mo.cavities(mo.voxels(V, F, pitch, pad=mo.ball_pad(ball, pitch)), ball)
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].openings), 2)
        self.assertFalse(found[0].sealed)
        for opening in found[0].openings:
            self.assertAlmostEqual(opening["diameter_mm"], 4.0, delta=2 * pitch)
            self.assertFalse(opening["exact"], "the voxels' reading, to two voxels")
        # with the triangles' rays each throat is measured: the hole's own 4 mm, its chords' sag its uncertainty
        grid = mo.voxels(V, F, pitch, pad=mo.ball_pad(ball, pitch))
        [measured], labels = mo.cavities(grid, ball, caster=mo.Caster(V, F))
        for opening in measured.openings:
            self.assertTrue(opening["exact"])
            self.assertLessEqual(abs(opening["diameter_mm"] - 4.0), opening["uncertainty_mm"] + 0.02)
            self.assertLess(opening["uncertainty_mm"], 0.1)
        self.assertAlmostEqual(measured.volume_mm3, 24 ** 3, delta=0.03 * 24 ** 3)
        self.assertEqual(set(np.unique(labels)), {-2, -1, 0}, "material, air that is no cavity, the cavity")

    def test_a_wall_s_support_is_read_off_the_wall(self) -> None:
        # the outline of the wall's thin region: where it runs into the part, and on how many sides
        def read(shape, point, normal, thickness: float) -> tuple:
            V, F, _ = brep.triangles(shape, 0.05)
            caster = mo.Caster(V, F)

            def cast(origins, directions):
                distance, hit = caster.first(origins, directions)
                normals = np.zeros((len(distance), 3))
                normals[hit >= 0] = caster.normals_of(hit[hit >= 0])
                return distance, normals

            found = mo.wall_support(cast, np.array(point, dtype=float), np.array(normal, dtype=float), thickness)
            self.assertEqual(found["unread_links"], 0, found)
            return found["supported"], found["joined_sides"]

        base = bd.Box(30, 20, 2, align=A)
        fin = base + bd.Pos(0, 0, 2) * bd.Box(20, 0.7, 10, align=A)
        self.assertEqual(read(fin, (0, 0.35, 7), (0, 1, 0), 0.7), (False, 1), "a fin on its base: one side")
        self.assertEqual(read(fin, (9.5, 0.35, 2.3), (0, 1, 0), 0.7), (False, 1), "read from beside its foot too")
        corner = fin + bd.Pos(10, 0, 2) * bd.Box(2, 8, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
        self.assertEqual(read(corner, (0, 0.35, 7), (0, 1, 0), 0.7), (True, 2), "its base and a rib: round a corner")
        posts = bd.Pos(-12, 0, 0) * bd.Box(4, 8, 10, align=A) + bd.Pos(12, 0, 0) * bd.Box(4, 8, 10, align=A)
        web = posts + bd.Pos(0, 0, 3) * bd.Box(20, 0.7, 4, align=A)
        self.assertEqual(read(web, (0, 0.35, 5), (0, 1, 0), 0.7), (True, 2), "a web between two posts: two sides")
        tube = bd.Cylinder(10, 20, align=A) - bd.Cylinder(9.3, 20, align=A)
        self.assertEqual(read(tube, (10, 0, 6), (1, 0, 0), 0.7), (True, 2), "a tube's wall: a ring")
        skin = bd.Box(30, 30, 30) - bd.Pos(0, 0, 3.3) * bd.Sphere(11)
        self.assertEqual(read(skin, (0, 0, 15), (0, 0, 1), 0.7), (True, 2), "a skin over a cavity: all round")
        self.assertEqual(read(bd.Box(20, 20, 0.5), (1, 2, 0.25), (0, 0, 1), 0.5), (False, 0), "a plate alone: none")
        pin = base + bd.Pos(0, 0, 2) * bd.Cylinder(0.25, 10, align=A)
        self.assertEqual(read(pin, (0.25, 0, 7), (1, 0, 0), 0.5), (False, 1), "a pin on its foot: one side")
        cup = bd.Cylinder(10, 20, align=A) - bd.Pos(0, 0, 2) * bd.Cylinder(9.3, 20, align=A)
        self.assertEqual(read(cup, (10, 0, 12), (1, 0, 0), 0.7), (True, 2), "a cup's wall: its floor all round")
        # the land a 90 deg countersink leaves round a hole, 0.6 mm: joined to the plate round its whole rim,
        # whichever of its faces it is read from and whichever side of the hole
        land = bd.Box(30, 20, 3, align=A) - bd.Cylinder(1.7, 3, align=A) - bd.Pos(0, 0, 0.6) * bd.Cone(1.7, 4.1, 2.4, align=A)
        for x in (1.75, -1.75):
            self.assertEqual(read(land, (x, 0, 0), (0, 0, -1), 0.65), (True, 2), "a countersink's land, from below")
        slope = np.array([-1.0, 0.0, 1.0]) / math.sqrt(2.0)
        self.assertEqual(read(land, (1.9, 0, 0.8), slope, 0.8 * math.sqrt(2.0) / 2.0), (True, 2), "from its cone")

    def test_the_mesh_check_answers_the_same_families(self) -> None:
        drained = TrappedTest.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2.5, 5, align=A)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "drained.stl"
            bd.export_stl(tunnel(8.0) + bd.Pos(50, 0, 0) * drained, str(path), tolerance=0.01)
            result = _dfm(path, process="printing", technology="sla")
        report = result.measurements
        bridge = near(result, "bridges", (0, 0, 6), 12.0, kind="bridge")
        self.assertAlmostEqual(bridge["length_mm"], 8.0, delta=0.05)
        hollow = items(result, "trapped_volumes")[0]
        self.assertEqual((hollow["sealed"], hollow["escape_holes"]), (False, 1))
        self.assertAlmostEqual(hollow["min_wall_mm"], 3.0, delta=0.05)
        # a mesh holds no cylinder: its holes up to the gaps' reach are the gaps whose rays cross a round hole
        # (the 5 mm drain is past it, and no hole here); its pins and details are exact geometry's
        self.assertEqual((report["holes"]["items"], report["holes"]["read_below_mm"]), ([], 3.0))
        self.assertEqual(outcome(result, "printing.hole_diameter")[0]["status"], "passed")
        self.assertEqual(sorted(report["not_measured"]), ["details", "pins"])
        self.assertEqual(outcome(result, "printing.pin_diameter")[0]["status"], "not_evaluated")
        self.assertIn("not judged on a mesh: holes over 3 mm as holes", result.summary)
        json.dumps(report, allow_nan=False)

    def test_a_sliver_is_sampled_along_its_length_and_spans_read_far_from_the_origin(self) -> None:
        # a 100 x 0.01 mm facet (a lattice strut's): points along its length at the cap's spacing, not a square
        # grid by its longest side (1891 points a facet, 183000 on a 97-triangle region)
        sliver = np.array([[[0, 0, 0], [100, 0, 0], [100, 0.01, 0]]], dtype=float)
        points = mo.spread_points(np.vstack([sliver, sliver + [0, 1, 0]]), cap=200)
        self.assertLess(len(points), 400)
        self.assertAlmostEqual(float(np.ptp(points[:, 0])), 100.0, places=9)
        # the distances to the supports, by products, keep their digits 1000 mm off the origin
        far = np.array([1000.0, -700.0, 300.0])
        ring = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], dtype=float) + far
        found = mo.span(np.array([[5.0, 5.0, 0.0]]) + far, ring, np.roll(ring, -1, axis=0))
        self.assertEqual((found["kind"], found["length_mm"]), ("bridge", 10.0))


if __name__ == "__main__":
    unittest.main()
