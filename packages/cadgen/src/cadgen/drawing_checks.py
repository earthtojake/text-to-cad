"""Deterministic DXF drawing validation.

Validation happens IN generation, not after: every gen_dxf() build runs these
checks on the in-memory ezdxf document before the drawing package (or any
export) is written, and a build with error findings fails. The same checks run
post-hoc on existing ``.dxf`` files via ``scripts/gen --validate``.

Layer intent follows the skill conventions: geometry on a layer whose name
contains "bend" is bend/fold lines (open geometry allowed); layers matching
engrave/reference/annotation intents may also carry open contours; every other
geometry layer holds cut profiles, which must be closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Layer intent is decided by WHOLE tokens of the layer name (split on
# non-alphanumerics), never substrings — "PREFORM" must not match "ref".
# This is the single classifier: drawing_render (and the viewer's parseDxf)
# follow the same token rule so validation, snapshots, and rendering agree.
_LAYER_INTENT_BY_TOKEN = {
    # An explicit cut token WINS: a layer called CUT_SECTION is a cut path whose name happens
    # to mention a view, and classifying it as annotation would skip the closure check on the
    # one layer that most needs it.
    "cut": "cut",
    "profile": "cut",
    "bend": "bend",
    "fold": "bend",
    "engrave": "engrave",
    "etch": "engrave",
    "ref": "reference",
    "reference": "reference",
    "note": "reference",
    "notes": "reference",
    "annotation": "reference",
    "construction": "reference",
    # A dimensioned drawing's furniture. None of it is a cut path, and every one of these was
    # previously classified as one, so a plan-and-sections drawing could not generate at all
    # (issue #246). Whole tokens still, so PREFORM does not match ref and SECTIONAL does not
    # match section.
    "dim": "reference",
    "dims": "reference",
    "dimension": "reference",
    "dimensions": "reference",
    "section": "reference",
    "sections": "reference",
    "hidden": "reference",
    "center": "reference",
    "centre": "reference",
    "centerline": "reference",
    "centreline": "reference",
    "phantom": "reference",
    "title": "reference",
    "titleblock": "reference",
    "border": "reference",
    "frame": "reference",
    "viewport": "reference",
    "hatch": "reference",
    "text": "reference",
    "label": "reference",
    "labels": "reference",
    "leader": "reference",
    "axis": "reference",
}
_LAYER_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_ANNOTATION_ENTITY_TYPES = frozenset({"TEXT", "MTEXT", "DIMENSION", "LEADER", "MULTILEADER", "HATCH"})
_COORDINATE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class DrawingFinding:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


class DrawingValidationError(ValueError):
    def __init__(self, findings: list[DrawingFinding], *, label: str = "") -> None:
        self.findings = findings
        prefix = f"{label}: " if label else ""
        details = "; ".join(finding.render() for finding in findings)
        super().__init__(f"{prefix}DXF drawing validation failed: {details}")


def layer_intent(layer_name: str) -> str:
    """Classify a layer name into ``cut`` | ``bend`` | ``engrave`` | ``reference``."""
    tokens = [t for t in _LAYER_TOKEN_SPLIT.split(str(layer_name or "").strip().lower()) if t]
    for intent in ("cut", "bend", "engrave", "reference"):
        if any(_LAYER_INTENT_BY_TOKEN.get(token) == intent for token in tokens):
            return intent
    return "cut"


def layer_allows_open_geometry(layer_name: str) -> bool:
    return layer_intent(layer_name) != "cut"



# --- is this file a DRAWING or a cut layout? ------------------------------------------
# Answered from the FILE, using the format's own constructs, rather than from a field a
# generator sets: the same rule then holds for a .dxf that came out of AutoCAD and is being
# validated post-hoc, which is the case that matters (issue #246 -- a workshop drawing already
# sitting with the cabinetmaker).
#
# The apparatus below is what a dimensioned drawing has and a laser-cut layout never does. A
# cut file is model-space geometry at 1:1 with no dimensions, no viewports and nothing to plot
# a title block into: it is a toolpath, not a document.
_DRAWING_APPARATUS_ENTITY_TYPES = frozenset({"DIMENSION", "LEADER", "MULTILEADER", "ARC_DIMENSION"})
# Standard DXF linetypes with an ISO 128 / ASME Y14.2 meaning that is not "cut here".
_ANNOTATION_LINETYPE_TOKENS = frozenset({
    "hidden", "hidden2", "hiddenx2",
    "center", "center2", "centerx2", "centre",
    "phantom", "phantom2", "phantomx2",
    "dashdot", "dashdot2", "dashdotx2", "divide", "dot",
})


def _linetype_is_annotation(linetype: object) -> bool:
    tokens = [t for t in _LAYER_TOKEN_SPLIT.split(str(linetype or "").strip().lower()) if t]
    return any(token in _ANNOTATION_LINETYPE_TOKENS for token in tokens)


def layer_table_intents(document: object) -> dict[str, str]:
    """Layer intents the FILE itself declares, by layer name.

    Two standard DXF properties say "this layer is not a cut path" without anyone having to
    name it so:

    * ``plot = 0`` -- a non-plotting layer. Construction geometry, by the convention every CAD
      package writes and reads.
    * a dashed/centre/phantom linetype -- ISO 128 line types for hidden edges, axes and
      break lines. A cut path is continuous.
    """
    intents: dict[str, str] = {}
    try:
        layers = list(document.layers)
    except Exception:  # noqa: BLE001 - a document with no readable layer table simply declares no intents
        return intents
    for layer in layers:
        name = str(getattr(getattr(layer, "dxf", None), "name", "") or "").strip()
        if not name:
            continue
        plot = getattr(getattr(layer, "dxf", None), "plot", 1)
        linetype = getattr(getattr(layer, "dxf", None), "linetype", "")
        if _linetype_is_annotation(linetype):
            # A BEND layer is conventionally dashed too, and bend keeps its own intent: it is
            # not a cut path either, and the bend checks want to know it is a bend.
            intents[name] = "bend" if layer_intent(name) == "bend" else "reference"
        elif str(plot) in {"0", "False"}:
            intents[name] = "reference"
    return intents


def drawing_apparatus(document: object) -> dict[str, int]:
    """Counts of the constructs that make a DXF a drawing rather than a cut layout."""
    counts = {"dimensions": 0, "viewports": 0, "paperspace_entities": 0}
    try:
        for entity in document.entitydb.values() if hasattr(document, "entitydb") else []:
            kind = entity.dxftype()
            if kind in _DRAWING_APPARATUS_ENTITY_TYPES:
                counts["dimensions"] += 1
            elif kind == "VIEWPORT":
                counts["viewports"] += 1
    except Exception:  # noqa: BLE001 - ezdxf entity reads can raise per entity; a partial count still classifies
        pass
    try:
        for layout in document.layouts:
            if layout.name.lower() == "model":
                continue
            counts["paperspace_entities"] += sum(1 for _ in layout)
    except Exception:  # noqa: BLE001 - same, for layouts: an unreadable layout contributes nothing
        pass
    return counts


def document_is_drawing(document: object) -> tuple[bool, str]:
    """Whether this file is a dimensioned drawing, and the evidence for saying so.

    Positive evidence only. "Nothing closes, so it must be a drawing" would excuse a genuinely
    broken cut layout, which is the one thing this check exists to catch.
    """
    counts = drawing_apparatus(document)
    reasons = []
    if counts["dimensions"]:
        reasons.append(f"{counts['dimensions']} dimension/leader entities")
    if counts["viewports"]:
        reasons.append(f"{counts['viewports']} paper-space viewports")
    if counts["paperspace_entities"] and not counts["viewports"]:
        reasons.append(f"{counts['paperspace_entities']} paper-space entities")
    return bool(reasons), ", ".join(reasons)


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _point_key(point) -> tuple[float, float]:
    return (_rounded(point[0]), _rounded(point[1]))


def _entity_layer(entity) -> str:
    return str(getattr(entity.dxf, "layer", "0") or "0")


def _lwpolyline_points(entity) -> list[tuple[float, float]]:
    return [(float(p[0]), float(p[1])) for p in entity.get_points()]


def _is_effectively_closed_polyline(entity) -> bool:
    points = _lwpolyline_points(entity)
    if len(points) < 3:
        return False
    if bool(entity.closed):
        return True
    return _point_key(points[0]) == _point_key(points[-1])


def _open_endpoints(entity) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Start/end of an open curve entity, or None for closed/whole shapes."""
    kind = entity.dxftype()
    if kind == "LINE":
        return (_point_key(entity.dxf.start), _point_key(entity.dxf.end))
    if kind == "ARC":
        return (_point_key(entity.start_point), _point_key(entity.end_point))
    if kind == "SPLINE":
        try:
            if bool(entity.closed):
                return None
            control_points = list(entity.control_points)
            if len(control_points) < 2:
                return None
            return (_point_key(control_points[0]), _point_key(control_points[-1]))
        except (AttributeError, TypeError, IndexError):  # a malformed SPLINE has no usable endpoints
            return None
    return None


def _entity_signature(entity) -> tuple | None:
    """A geometry identity for exact-duplicate detection (same layer + coordinates)."""
    kind = entity.dxftype()
    layer = _entity_layer(entity)
    if kind == "LINE":
        ends = sorted([_point_key(entity.dxf.start), _point_key(entity.dxf.end)])
        return (kind, layer, tuple(ends))
    if kind == "CIRCLE":
        return (kind, layer, _point_key(entity.dxf.center), _rounded(entity.dxf.radius))
    if kind == "ARC":
        return (
            kind, layer, _point_key(entity.dxf.center), _rounded(entity.dxf.radius),
            _rounded(entity.dxf.start_angle), _rounded(entity.dxf.end_angle),
        )
    if kind == "LWPOLYLINE":
        return (kind, layer, bool(entity.closed), tuple(_point_key(p) for p in _lwpolyline_points(entity)))
    return None


def _zero_length_finding(entity) -> DrawingFinding | None:
    kind = entity.dxftype()
    layer = _entity_layer(entity)
    if kind == "LINE" and _point_key(entity.dxf.start) == _point_key(entity.dxf.end):
        return DrawingFinding("error", "zero_length_entity", f"zero-length LINE on layer {layer!r}")
    if kind == "CIRCLE" and _rounded(entity.dxf.radius) <= 0:
        return DrawingFinding("error", "zero_length_entity", f"zero-radius CIRCLE on layer {layer!r}")
    if kind == "ARC":
        # start == end (mod 360) is DXF's standard full-circle encoding, not a
        # zero sweep — the render side treats it as a 360-degree arc.
        if _rounded(entity.dxf.radius) <= 0:
            return DrawingFinding("error", "zero_length_entity", f"zero-radius ARC on layer {layer!r}")
    if kind == "LWPOLYLINE" and len({_point_key(p) for p in _lwpolyline_points(entity)}) < 2:
        return DrawingFinding("error", "zero_length_entity", f"degenerate LWPOLYLINE on layer {layer!r}")
    return None


def _open_chain_findings(open_curves_by_layer: dict[str, list]) -> list[DrawingFinding]:
    """LINE/ARC/SPLINE segments on cut layers must chain into closed loops:
    every endpoint must be shared by an even number of segment ends."""
    findings: list[DrawingFinding] = []
    for layer, endpoint_pairs in sorted(open_curves_by_layer.items()):
        endpoint_counts: dict[tuple[float, float], int] = {}
        for start, end in endpoint_pairs:
            endpoint_counts[start] = endpoint_counts.get(start, 0) + 1
            endpoint_counts[end] = endpoint_counts.get(end, 0) + 1
        dangling = [point for point, count in endpoint_counts.items() if count % 2 == 1]
        if dangling:
            sample = ", ".join(str(point) for point in sorted(dangling)[:3])
            findings.append(
                DrawingFinding(
                    "error",
                    "open_cut_profile",
                    f"cut layer {layer!r} has segment endpoints that do not close a loop "
                    f"(e.g. {sample}); move open geometry to a bend/engrave/reference layer "
                    "or close the contour",
                )
            )
    return findings


def validate_drawing_document(document: object) -> list[DrawingFinding]:
    """Run all drawing checks against an ezdxf document; returns the findings."""
    findings: list[DrawingFinding] = []
    header = getattr(document, "header", None)
    units = 0
    try:
        units = int(header.get("$INSUNITS", 0)) if header is not None else 0
    except (TypeError, ValueError):  # malformed or non-numeric $INSUNITS
        units = 0
    if units <= 0:
        findings.append(
            DrawingFinding(
                "error",
                "units_not_set",
                "document units are unset; set them explicitly (e.g. doc.units = ezdxf.units.MM)",
            )
        )

    # A drawing is not a cut layout, and the file says which it is. Closure is required of cut
    # paths; a plan-and-sections drawing has none, and failing it for that is what made issue
    # #246's workshop drawing ungeneratable.
    is_drawing, drawing_evidence = document_is_drawing(document)
    if is_drawing:
        findings.append(
            DrawingFinding(
                "info",
                "drawing_document",
                f"treated as a dimensioned drawing ({drawing_evidence}); cut-profile closure "
                "is not required. Cut layouts have no dimensions or viewports.",
            )
        )
    declared_layer_intents = layer_table_intents(document)

    modelspace = document.modelspace()
    geometry_count = 0
    seen_signatures: set[tuple] = set()
    open_curves_by_cut_layer: dict[str, list] = {}
    for entity in modelspace:
        kind = entity.dxftype()
        if kind in _ANNOTATION_ENTITY_TYPES:
            continue
        geometry_count += 1
        layer = _entity_layer(entity)

        zero_length = _zero_length_finding(entity)
        if zero_length is not None:
            findings.append(zero_length)
            continue

        signature = _entity_signature(entity)
        if signature is not None:
            if signature in seen_signatures:
                findings.append(
                    DrawingFinding(
                        "error",
                        "duplicate_entity",
                        f"exact duplicate {kind} on layer {layer!r} (double-cut risk)",
                    )
                )
                continue
            seen_signatures.add(signature)

        if is_drawing or declared_layer_intents.get(layer, "cut") != "cut":
            continue
        if layer_allows_open_geometry(layer):
            continue
        if kind == "LWPOLYLINE":
            if not _is_effectively_closed_polyline(entity):
                findings.append(
                    DrawingFinding(
                        "error",
                        "open_cut_profile",
                        f"open LWPOLYLINE on cut layer {layer!r}; close it or move it to a "
                        "bend/engrave/reference layer",
                    )
                )
            continue
        if kind in {"CIRCLE", "ELLIPSE"}:
            continue
        endpoints = _open_endpoints(entity)
        if endpoints is not None:
            open_curves_by_cut_layer.setdefault(layer, []).append(endpoints)

    findings.extend(_open_chain_findings(open_curves_by_cut_layer))

    if geometry_count == 0:
        findings.append(
            DrawingFinding("error", "empty_drawing", "modelspace contains no geometry entities")
        )
    return findings


def raise_on_error_findings(findings: list[DrawingFinding], *, label: str = "") -> None:
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        raise DrawingValidationError(errors, label=label)


def validate_dxf_file(path: Path | str) -> list[DrawingFinding]:
    """Post-hoc validation of an existing .dxf file with the same generation checks."""
    import ezdxf

    document = ezdxf.readfile(str(path))
    return validate_drawing_document(document)
