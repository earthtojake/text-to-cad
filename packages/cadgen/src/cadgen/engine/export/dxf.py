"""DXF: a planar document drawn on the XY plane by build123d's own exporter.

A DXF is a translation of a 2D document -- what a model makes when its body returns a sketch, a
face, wires or edges -- written by build123d's ``ExportDXF`` through ezdxf, which build123d brings
with it: millimetres, every edge of every placed part one LINE, ARC, CIRCLE, ELLIPSE or SPLINE
entity, so a curve stays a curve.

**A part per layer.** A document placing one part -- a model returning one shape -- is the layer
``CUT``. Any other is a layer per part, named by its occurrence's name (the shape's label in the
compound returned: ``cut.label, bend.label = "CUT", "BEND"``); parts of one name share a layer,
and a layer of several shapes is one part of them all (``bd.Compound([a, b], label="ENGRAVE")``).
A layer name holding a character DXF reserves is refused by name.

**Planar or refused.** A document holding a solid is refused before anything is written
(``tom.xbf is 3D``), and so is an edge with a point off z=0, by its element name: exporting either
would write its XY shadow, silently wrong.

**The bytes are a function of the geometry.** Layers are written in name order and each layer's
edges in an order of their content -- curve kind, then points sampled along it and its length,
rounded first and exact after -- never in the kernel's traversal order, which an OCCT upgrade or
another boolean route to the same profile changes. ezdxf's provenance is pinned (its fixed
metadata: two GUIDs, four Julian dates and two version markers) and its CLASSES registry, filled
from a set and so in hash-seed order, is sorted; a pin that stops holding fails the write
(``DxfDeterminismError``) rather than letting the bytes drift. Each part's geometry is its shape
bytes read once (``Source.shape_data``), the form its document holds, so a build's file and
``cadgen export model.xbf model.dxf`` are the same bytes.

**The drawing checks** run on the document the bytes are written from, before they are written:
units set, no zero-length or degenerate entity, no exact duplicate (a double cut), cut profiles
closed (polylines, circles, and line, arc and spline chains whose every endpoint is shared an even
number of times), and something drawn. Open geometry is allowed on a layer whose name says it is
not a cut path (``layer_intent``: bend, engrave, reference, by whole tokens). An error refuses the
file, saying which. ``validate_dxf_file`` runs the same checks on any DXF on disk, one no model
wrote too, where the file itself says whether it is a dimensioned drawing (dimensions, viewports,
paper space) or a cut layout, and which layers are construction (not plotted, or a dashed line
type).

The file is replaced only when its bytes change: the same drawing again leaves the file, and its
stat, as they were.
"""

from __future__ import annotations

import contextlib
import io
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from cadgen.engine.atomic_replace import put
from cadgen.engine.export import ExportRefused

__all__ = ["DEFAULT_LAYER", "DrawingFinding", "DrawingValidationError", "DxfDeterminismError", "document_is_drawing",
           "drawing_apparatus", "dxf_bytes", "layer_allows_open_geometry", "layer_intent", "layer_table_intents",
           "raise_on_error_findings", "validate_drawing_document", "validate_dxf_file", "write"]

# The layer of a document of one part. Layers are CAM operations (CUT, ENGRAVE, SCORE); a
# drawing of one need not name it.
DEFAULT_LAYER = "CUT"
# Where along an edge it is sampled, for its order and the plane: its ends and three points
# between, which tell apart any two edges sharing their ends (an arc and its chord, two arcs of
# opposite bulge).
_SAMPLES = (0.0, 0.25, 0.5, 0.75, 1.0)
_KEY_DECIMALS = 9
# ExportDXF's own test of a point off the plane.
_PLANAR = 1e-6
# Characters a DXF layer name may not hold.
_RESERVED = set('<>/\\":;?*|=`')
# ezdxf's metadata option is process-wide: one pinned write at a time.
_PIN = threading.Lock()


class DxfDeterminismError(RuntimeError):
    """The writer could not hold its bytes to the drawing: an ezdxf mechanism it pins is gone."""


# --- the drawing: layers, edges, bytes ---------------------------------------------------------


def write(view: Any, path: Path) -> None:
    """The view's drawing at ``path``: written beside it and moved over it, or, when the file
    holds these bytes already, left as it is."""
    data = dxf_bytes(view)
    path = Path(path)
    try:
        if path.stat().st_size == len(data) and path.read_bytes() == data:
            return
    except OSError:
        pass
    put(path, lambda temporary: temporary.write_bytes(data), compare=False)


def dxf_bytes(view: Any) -> bytes:
    """The view's DXF bytes, checked (see the module docstring)."""
    named = view.source.path.name if not view.source.live and view.source.path is not None else view.name
    shapes = _shapes(view, named)
    layers = [(name, _edges(view, placements, shapes, named)) for name, placements in _layers(view, named)]
    data, document = _emit(layers, named)
    errors = [finding for finding in validate_drawing_document(document) if finding.severity == "error"]
    if errors:
        raise ExportRefused(f"{named}: the drawing checks failed: {'; '.join(finding.render() for finding in errors)}")
    return data


def _shapes(view: Any, named: str) -> dict[int, Any]:
    """Each prototype the view places, by its index: its shape as its bytes read once (the form
    its document holds), at its own frame. A solid is refused: the document is 3D."""
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    from cadgen.engine.mesh import read_shape

    found = {}
    for index in view.used():
        shape = read_shape(view.source.shape_data(view.prototypes[index]["key"]))
        if TopExp_Explorer(shape, TopAbs_SOLID).More():
            where = "" if len(view.placements) == 1 else \
                f" ({'/'.join(next(p for p in view.placements if p.prototype == index).path)} is a solid)"
            raise ExportRefused(f"{named} is 3D: a DXF is drawn from 2D geometry a model returns{where}")
        found[index] = shape
    return found


def _layers(view: Any, named: str) -> list[tuple[str, list[Any]]]:
    """The view's placements by layer, in name order: one placed part is ``CUT``; several, a
    layer each, named by its occurrence's name."""
    if len(view.placements) == 1:
        return [(DEFAULT_LAYER, list(view.placements))]
    names: dict[int, str] = {}

    def visit(node: dict[str, Any]) -> None:
        for child in node.get("children") or ():
            visit(child)
        if "children" not in node:
            names[node["instance"]] = str(node["name"])

    visit(view.tree)
    found: dict[str, list[Any]] = {}
    for placed in view.placements:
        name = names.get(placed.instance, "").strip()
        bad = sorted(_RESERVED.intersection(name))
        if not name or bad:
            raise ExportRefused(f"{named}: {names.get(placed.instance)!r} names a layer, and a DXF layer name "
                                + (f"may not hold {''.join(bad)!r}" if bad else "is not empty")
                                + ": label it otherwise")
        found.setdefault(name, []).append(placed)
    return sorted(found.items())


def _edges(view: Any, placements: list[Any], shapes: dict[int, Any], named: str) -> list[Any]:
    """Every edge of the placed parts, where the document places them, in content order; an
    edge off the plane is refused by its element name."""
    import numpy as np
    from build123d import Edge
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    from cadgen.engine.export.tree import _located

    keyed = []
    for placed in placements:
        shape = shapes[placed.prototype]
        if not np.array_equal(placed.matrix, np.eye(4)):
            shape = shape.Moved(_located(placed.matrix))
        mapped = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, TopAbs_EDGE, mapped)
        for ordinal in range(1, mapped.Extent() + 1):
            topods = TopoDS.Edge(mapped.FindKey(ordinal))
            if BRep_Tool.Degenerated_s(topods):
                continue
            edge = Edge(topods)
            samples = _samples(edge)
            off = next((z for *_xy, z in samples if abs(z) > _PLANAR), None)
            if off is not None:
                prototype = view.prototypes[placed.prototype]
                name = (prototype.get("edgeNames") or {}).get(str(ordinal))
                where = f"edge {ordinal} of {'/'.join(placed.path)}"
                raise ExportRefused(f"{named}: {f'{name} ({where})' if name else where} is off the XY plane "
                                    f"(a point at z={off:.6g}): a DXF is 2D, and this would write its shadow; move "
                                    "it onto z=0 (bd.Pos(0, 0, -z) * shape)")
            keyed.append((_edge_key(edge, samples), edge))
    return [edge for _key, edge in sorted(keyed, key=lambda pair: pair[0])]


def _samples(edge: Any) -> tuple[tuple[float, float, float], ...]:
    found = []
    for at in _SAMPLES:
        point = edge.position_at(at)
        found.append((float(point.X), float(point.Y), float(point.Z)))
    return tuple(found)


def _edge_key(edge: Any, samples: tuple[tuple[float, float, float], ...]) -> tuple:
    """An order of edges by their content alone: ``(curve kind, rounded samples and length,
    exact samples and length)``. Rounding absorbs the last bits two routes to one edge differ
    by; the exact tail leaves a tie only between edges equal bit for bit, whose entities are
    the same either way."""
    try:
        length = float(edge.length)
    except Exception:  # noqa: BLE001 - a degenerate edge has no length: its samples order it
        length = 0.0
    exact = (*[value for point in samples for value in point], length)
    return (str(edge.geom_type), tuple(round(value, _KEY_DECIMALS) for value in exact), exact)


@contextlib.contextmanager
def _pinned() -> Any:
    """ezdxf's fixed metadata, for one document's making and writing (it stamps a created-by
    marker as it makes one and a written-by marker as it saves), restored after."""
    import ezdxf

    with _PIN:
        options = ezdxf.options
        previous = bool(getattr(options, "write_fixed_meta_data_for_testing", False))
        options.write_fixed_meta_data_for_testing = True
        try:
            yield
        finally:
            options.write_fixed_meta_data_for_testing = previous


def _emit(layers: list[tuple[str, list[Any]]], named: str) -> tuple[bytes, Any]:
    """``ExportDXF`` of the layers, in their order: the bytes, and the ezdxf document they were
    written from."""
    from build123d import ExportDXF, Unit

    buffer = io.BytesIO()
    with _pinned():
        exporter = ExportDXF(unit=Unit.MM)
        for name, edges in layers:
            if name != "0":
                exporter.add_layer(name)
            # ExportDXF warns of points off the plane on stdout; those are refused above.
            with contextlib.redirect_stdout(io.StringIO()):
                exporter.add_shape(edges, layer=name)
        if getattr(exporter, "_non_planar_point_count", 0):
            raise ExportRefused(f"{named}: {exporter._non_planar_point_count} exported point(s) lie off the XY plane")
        document = getattr(exporter, "_document", None)
        if document is None:
            raise DxfDeterminismError("build123d's ExportDXF no longer holds the ezdxf document the writer orders "
                                      "and checks")
        _sorted_classes(document)
        exporter.write(buffer)
    data = buffer.getvalue()
    _check_pinned(data.decode("utf-8"), named)
    return data, document


def _sorted_classes(document: Any) -> None:
    """The CLASSES section in class-name order. ezdxf fills it as it saves, from a set of entity
    types, so its order follows ``PYTHONHASHSEED``; registered early and sorted, the save's own
    registration skips what is there and this order reaches the file."""
    section = getattr(document, "classes", None)
    registry = getattr(section, "classes", None)
    if section is None or not isinstance(registry, dict):
        raise DxfDeterminismError(f"ezdxf's CLASSES registry is no mapping the writer can order (a "
                                  f"{type(registry).__name__}): unsorted, the bytes follow the hash seed")
    section.add_required_classes(document.dxfversion)
    ordered = sorted(registry.items())
    registry.clear()
    registry.update(ordered)


_PINNED_GUID = "{00000000-0000-0000-0000-000000000000}"
_PINNED_JULIAN = "2451545.0"
_PINNED_MARKER = "0.0 @ 2000-01-01T00:00:00.000000+00:00"
# Header variable -> (its value's group code, the pinned value).
_PINNED_HEADER = {"$FINGERPRINTGUID": ("2", _PINNED_GUID), "$VERSIONGUID": ("2", _PINNED_GUID),
                  "$TDCREATE": ("40", _PINNED_JULIAN), "$TDUCREATE": ("40", _PINNED_JULIAN),
                  "$TDUPDATE": ("40", _PINNED_JULIAN), "$TDUUPDATE": ("40", _PINNED_JULIAN)}
# ezdxf's created-by and written-by markers ("1.4.4 @ 2026-08-30T18:14:31.649023+00:00"), group-1
# values on DICTIONARYVAR objects.
_MARKER = re.compile(r"^\d+\.\d+(?:\.\d+)? @ \d{4}-\d{2}-\d{2}T[\d:.+\-]+$")


def _check_pinned(text: str, named: str) -> None:
    """Nothing volatile in the written text: checked, never rewritten (a rewrite once took a
    layer named ``$TDCREATE`` for the header variable). A group is two lines, code then value,
    so a header field is matched by its name and its code, inside the HEADER section only."""
    lines = [line.strip() for line in text.split("\n")]
    try:
        end = lines.index("ENDSEC")
    except ValueError:
        end = len(lines)
    unpinned = []
    for at in range(end):
        field = _PINNED_HEADER.get(lines[at])
        if field is not None and at + 2 < end and lines[at + 1] == field[0] and lines[at + 2] != field[1]:
            unpinned.append(f"{lines[at]}={lines[at + 2]!r}")
    for at in range(1, len(lines)):
        if lines[at - 1] == "1" and _MARKER.match(lines[at]) and lines[at] != _PINNED_MARKER:
            unpinned.append(f"ezdxf marker={lines[at]!r}")
    if unpinned:
        raise DxfDeterminismError(f"{named}: ezdxf wrote provenance its fixed-metadata mode should pin "
                                  f"({', '.join(sorted(unpinned))}): the same drawing would not be the same bytes")


# --- the drawing checks ------------------------------------------------------------------------

# Layer intent, by WHOLE tokens of the name (split on non-alphanumerics), never substrings:
# PREFORM is not "ref". An explicit cut token wins: CUT_SECTION is a cut path whose name mentions
# a view. A dimensioned drawing's furniture is reference (dimensions, sections, hidden and centre
# lines, title blocks, text).
_INTENT_BY_TOKEN = {
    "cut": "cut", "profile": "cut",
    "bend": "bend", "fold": "bend",
    "engrave": "engrave", "etch": "engrave",
    **{token: "reference" for token in (
        "ref", "reference", "note", "notes", "annotation", "construction", "dim", "dims", "dimension",
        "dimensions", "section", "sections", "hidden", "center", "centre", "centerline", "centreline",
        "phantom", "title", "titleblock", "border", "frame", "viewport", "hatch", "text", "label", "labels",
        "leader", "axis")},
}
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_ANNOTATION_TYPES = frozenset({"TEXT", "MTEXT", "DIMENSION", "LEADER", "MULTILEADER", "HATCH"})
_TOLERANCE = 1e-6
# What a dimensioned drawing has and a cut layout never does.
_APPARATUS_TYPES = frozenset({"DIMENSION", "LEADER", "MULTILEADER", "ARC_DIMENSION"})
# Standard line types with an ISO 128 / ASME Y14.2 meaning other than "cut here".
_ANNOTATION_LINETYPES = frozenset({"hidden", "hidden2", "hiddenx2", "center", "center2", "centerx2", "centre",
                                   "phantom", "phantom2", "phantomx2", "dashdot", "dashdot2", "dashdotx2", "divide",
                                   "dot"})


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
        super().__init__(f"{prefix}DXF drawing validation failed: {'; '.join(f.render() for f in findings)}")


def layer_intent(layer_name: str) -> str:
    """A layer name's intent: ``cut``, ``bend``, ``engrave`` or ``reference`` (``cut`` when no
    token says otherwise)."""
    tokens = [token for token in _TOKEN_SPLIT.split(str(layer_name or "").strip().lower()) if token]
    for intent in ("cut", "bend", "engrave", "reference"):
        if any(_INTENT_BY_TOKEN.get(token) == intent for token in tokens):
            return intent
    return "cut"


def layer_allows_open_geometry(layer_name: str) -> bool:
    return layer_intent(layer_name) != "cut"


def _annotation_linetype(linetype: object) -> bool:
    return any(token in _ANNOTATION_LINETYPES
               for token in _TOKEN_SPLIT.split(str(linetype or "").strip().lower()) if token)


def layer_table_intents(document: Any) -> dict[str, str]:
    """The intents a file's own layer table declares: a layer not plotted (``plot = 0``) is
    construction, and one in a dashed, centre or phantom line type is no cut path (a bend layer
    stays a bend)."""
    intents: dict[str, str] = {}
    try:
        layers = list(document.layers)
    except Exception:  # noqa: BLE001 - a layer table that does not read declares nothing
        return intents
    for layer in layers:
        dxf = getattr(layer, "dxf", None)
        name = str(getattr(dxf, "name", "") or "").strip()
        if not name:
            continue
        if _annotation_linetype(getattr(dxf, "linetype", "")):
            intents[name] = "bend" if layer_intent(name) == "bend" else "reference"
        elif str(getattr(dxf, "plot", 1)) in {"0", "False"}:
            intents[name] = "reference"
    return intents


def drawing_apparatus(document: Any) -> dict[str, int]:
    """How many of the constructs that make a DXF a drawing, not a cut layout, it holds."""
    counts = {"dimensions": 0, "viewports": 0, "paperspace_entities": 0}
    try:
        for entity in document.entitydb.values() if hasattr(document, "entitydb") else []:
            kind = entity.dxftype()
            if kind in _APPARATUS_TYPES:
                counts["dimensions"] += 1
            elif kind == "VIEWPORT":
                counts["viewports"] += 1
    except Exception:  # noqa: BLE001 - an entity that does not read counts nothing; the rest still classify
        pass
    try:
        for layout in document.layouts:
            if layout.name.lower() != "model":
                counts["paperspace_entities"] += sum(1 for _ in layout)
    except Exception:  # noqa: BLE001 - nor does a layout that does not read
        pass
    return counts


def document_is_drawing(document: Any) -> tuple[bool, str]:
    """Whether a file is a dimensioned drawing, and the evidence: positive evidence only, so a
    broken cut layout is never excused as a drawing because nothing in it closes."""
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


def _point(point: Any) -> tuple[float, float]:
    return (_rounded(point[0]), _rounded(point[1]))


def _layer(entity: Any) -> str:
    return str(getattr(entity.dxf, "layer", "0") or "0")


def _polyline_points(entity: Any) -> list[tuple[float, float]]:
    return [(float(p[0]), float(p[1])) for p in entity.get_points()]


def _closed_polyline(entity: Any) -> bool:
    points = _polyline_points(entity)
    return len(points) >= 3 and (bool(entity.closed) or _point(points[0]) == _point(points[-1]))


def _open_endpoints(entity: Any) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """An open curve's two ends, or None for a closed or whole one."""
    kind = entity.dxftype()
    if kind == "LINE":
        return (_point(entity.dxf.start), _point(entity.dxf.end))
    if kind == "ARC":
        return (_point(entity.start_point), _point(entity.end_point))
    if kind == "SPLINE":
        try:
            if bool(entity.closed):
                return None
            control = list(entity.control_points)
            if len(control) < 2:
                return None
            return (_point(control[0]), _point(control[-1]))
        except (AttributeError, TypeError, IndexError):  # a malformed SPLINE has no ends to chain
            return None
    return None


def _signature(entity: Any) -> tuple | None:
    """An entity's geometry, for exact duplicates: its type, layer and coordinates."""
    kind, layer = entity.dxftype(), _layer(entity)
    if kind == "LINE":
        return (kind, layer, tuple(sorted([_point(entity.dxf.start), _point(entity.dxf.end)])))
    if kind == "CIRCLE":
        return (kind, layer, _point(entity.dxf.center), _rounded(entity.dxf.radius))
    if kind == "ARC":
        return (kind, layer, _point(entity.dxf.center), _rounded(entity.dxf.radius), _rounded(entity.dxf.start_angle),
                _rounded(entity.dxf.end_angle))
    if kind == "LWPOLYLINE":
        return (kind, layer, bool(entity.closed), tuple(_point(p) for p in _polyline_points(entity)))
    return None


def _zero_length(entity: Any) -> DrawingFinding | None:
    kind, layer = entity.dxftype(), _layer(entity)
    if kind == "LINE" and _point(entity.dxf.start) == _point(entity.dxf.end):
        return DrawingFinding("error", "zero_length_entity", f"zero-length LINE on layer {layer!r}")
    # An ARC whose start is its end (mod 360) is DXF's full circle, not a zero sweep.
    if kind in ("CIRCLE", "ARC") and _rounded(entity.dxf.radius) <= 0:
        return DrawingFinding("error", "zero_length_entity", f"zero-radius {kind} on layer {layer!r}")
    if kind == "LWPOLYLINE" and len({_point(p) for p in _polyline_points(entity)}) < 2:
        return DrawingFinding("error", "zero_length_entity", f"degenerate LWPOLYLINE on layer {layer!r}")
    return None


def _clustered(points: Iterable[tuple[float, float]], tolerance: float) -> dict[tuple, tuple]:
    """Points within ``tolerance`` of one another, joined: each point's representative. Two edges
    that share a point can round it to either side of a boundary (``-68.150754`` and
    ``-68.150753``); each coordinate is snapped to an integer bucket at the tolerance's scale and
    points whose buckets are the same or adjacent are one, an integer comparison with no boundary
    left to land on."""
    unique = sorted(set(points))
    parent = {point: point for point in unique}

    def find(point: tuple) -> tuple:
        while parent[point] != point:
            parent[point] = parent[parent[point]]
            point = parent[point]
        return point

    scale = 1.0 / tolerance
    buckets = {point: (round(point[0] * scale), round(point[1] * scale)) for point in unique}
    for at, first in enumerate(unique):
        bucket = buckets[first]
        for second in unique[at + 1:]:
            other = buckets[second]
            if other[0] - bucket[0] > 1:
                break  # sorted by x first: no later point is nearer
            if abs(bucket[0] - other[0]) <= 1 and abs(bucket[1] - other[1]) <= 1:
                a, b = find(first), find(second)
                if a != b:
                    parent[b] = a
    return {point: find(point) for point in unique}


def _open_chains(open_by_layer: dict[str, list]) -> list[DrawingFinding]:
    """Line, arc and spline segments on a cut layer chain into closed loops: every endpoint is
    shared by an even number of segment ends."""
    findings = []
    for layer, pairs in sorted(open_by_layer.items()):
        counts: dict[tuple, int] = {}
        for start, end in pairs:
            counts[start] = counts.get(start, 0) + 1
            counts[end] = counts.get(end, 0) + 1
        representative = _clustered(counts, _TOLERANCE)
        merged: dict[tuple, int] = {}
        for point, count in counts.items():
            merged[representative[point]] = merged.get(representative[point], 0) + count
        dangling = sorted(point for point, count in merged.items() if count % 2)
        if dangling:
            sample = ", ".join(str(point) for point in dangling[:3])
            findings.append(DrawingFinding("error", "open_cut_profile",
                                           f"cut layer {layer!r} has segment endpoints that do not close a loop "
                                           f"(e.g. {sample}); move open geometry to a bend/engrave/reference layer "
                                           "or close the contour"))
    return findings


def validate_drawing_document(document: Any, *, drawing: bool | None = None) -> list[DrawingFinding]:
    """Every drawing check on an ezdxf document; the findings. ``drawing=True`` says its producer
    made a dimensioned drawing, so the cut-profile checks do not apply (an orthographic view's
    outline is open by nature); otherwise the file's own apparatus says (``document_is_drawing``)."""
    findings: list[DrawingFinding] = []
    header = getattr(document, "header", None)
    try:
        units = int(header.get("$INSUNITS", 0)) if header is not None else 0
    except (TypeError, ValueError):  # a malformed $INSUNITS is none
        units = 0
    if units <= 0:
        findings.append(DrawingFinding("error", "units_not_set", "document units are unset; set them explicitly "
                                                                 "(e.g. doc.units = ezdxf.units.MM)"))
    is_drawing, evidence = (True, "declared a drawing by its producer") if drawing else document_is_drawing(document)
    if is_drawing:
        findings.append(DrawingFinding("info", "drawing_document",
                                       f"treated as a dimensioned drawing ({evidence}); cut-profile closure is not "
                                       "required. Cut layouts have no dimensions or viewports."))
    declared = layer_table_intents(document)
    geometry = 0
    seen: set[tuple] = set()
    open_by_layer: dict[str, list] = {}
    for entity in document.modelspace():
        kind = entity.dxftype()
        if kind in _ANNOTATION_TYPES:
            continue
        geometry += 1
        layer = _layer(entity)
        zero = _zero_length(entity)
        if zero is not None:
            findings.append(zero)
            continue
        signature = _signature(entity)
        if signature is not None:
            if signature in seen:
                findings.append(DrawingFinding("error", "duplicate_entity",
                                               f"exact duplicate {kind} on layer {layer!r} (double-cut risk)"))
                continue
            seen.add(signature)
        if is_drawing or declared.get(layer, "cut") != "cut" or layer_allows_open_geometry(layer):
            continue
        if kind == "LWPOLYLINE":
            if not _closed_polyline(entity):
                findings.append(DrawingFinding("error", "open_cut_profile",
                                               f"open LWPOLYLINE on cut layer {layer!r}; close it or move it to a "
                                               "bend/engrave/reference layer"))
            continue
        if kind in {"CIRCLE", "ELLIPSE"}:
            continue
        ends = _open_endpoints(entity)
        if ends is not None:
            open_by_layer.setdefault(layer, []).append(ends)
    findings.extend(_open_chains(open_by_layer))
    if geometry == 0:
        findings.append(DrawingFinding("error", "empty_drawing", "modelspace contains no geometry entities"))
    return findings


def raise_on_error_findings(findings: list[DrawingFinding], *, label: str = "") -> None:
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        raise DrawingValidationError(errors, label=label)


def validate_dxf_file(path: Path | str) -> list[DrawingFinding]:
    """The drawing checks on a DXF on disk, whoever wrote it."""
    import ezdxf

    return validate_drawing_document(ezdxf.readfile(str(path)))
