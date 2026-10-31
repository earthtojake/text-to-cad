"""PMI over a still: an engine document's manufacturing annotations (``structure["pmi"]``, which
``cadgen.engine.pmi`` writes into the document and serves with it) painted over the finished
picture as the CAD Viewer draws them over its page.

A port, operation for operation, of the viewer's own: what a callout says (``@text-to-cad/core``'s
``lib/xbf/xbfPmi.js``, ``readXbfPmi`` and ``pmiCallout``), where it stands in the model
(``lib/xbf/xbfPmiLayout.js``, ``pmiConstruction``, from a face's nodes and surface as
``lib/xbf/xbfEntities.js`` reads them off the part's mesh buffer, the one the viewer reads), how a
part's named view is seen (``@text-to-cad/ui``'s ``renderers/xbf/pmi/pmiViews.js``), and how it is
drawn (``renderers/xbf/pmi/PmiOverlay.jsx`` and ``PmiLabel.jsx``: the label a few words at the UI's
size in a ruled box, a leader to its feature with an arrow (a datum's on its filled triangle), a
distance's dimension and extension lines; every label over every line). One golden made by the
viewer's own code (``lib/xbf/__fixtures__/pmi_plate/constructions.json``) holds both to one layout.

A reference is resolved as the engine resolves one (``refs.resolve_structure``); one the engine
found broken (``missing``, ``ambiguous``, ``invalid``) is drawn where its code placed it, dashed in
its status colour with an open ring where it was anchored, its nominal ``?``. A leader or extension
line whose start the model hides from the camera is faint, its marker hollow (what a clip cut away
hides nothing). An annotation is drawn at its part's first placement the picture shows. Only the
supported subset is drawn: distance (a basic one exact, its number boxed, measured to a hole's
centre line; one given its limits says them alone, stacked), diameter, datum, flatness, position,
surface profile and a flag note (its flag and its number, out from its first face). A general note,
the general profile (its part's Note 1) and a flag note on annotations alone are said in the
viewer's notes and drawn as nothing on the part. What is not drawn -- another kind, a note, a part
the picture hides, a broken reference its code never placed -- is said, and why (``left_out``). A
view (``views``, ``view_at``) is seen down its camera from its part's first placement shown, cut by
its section where that placement keeps the section's axis a world axis, showing its own PMI at its
own placements. Everything in the scene's coordinates (the document's millimetres), at rest: a still
drawn exploded or posed draws none (``snapshot.py`` refuses asking for it).
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np

__all__ = ["Hidden", "NOTE", "callout", "construction", "constructions", "decimals", "dimension_places",
           "drawn_on_part", "element", "entries", "face_nodes", "face_surface", "feature_point", "key", "left_out",
           "number", "paint", "placed_section", "placement", "reach", "rest_bounds", "separate", "to_scene",
           "tolerance_text", "view_at", "view_shows", "views"]

KINDS = ("dimension", "datum", "geometric_tolerance", "note")
DIMENSION_TYPES = ("distance", "diameter")
CHARACTERISTICS = ("flatness", "position", "surface_profile")
CHARACTERISTIC_NAMES = {"flatness": "Flatness", "position": "Position", "surface_profile": "Surface profile"}
DIMENSION_NAMES = {"distance": "Distance", "diameter": "Diameter"}
SECTION_AXES = ("x", "y", "z")
STATUSES = ("ok", "ambiguous", "missing", "invalid")
MINUS = "−"
EN_DASH = "–"
# Why a still leaves out what the viewer says in its notes alone (``drawn_on_part``).
NOTE = "a note: the viewer lists it, a still does not draw it"

# --- the words (xbfPmi.js) -------------------------------------------------------------------


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _status(value: Any) -> str:
    return value if value in STATUSES else "missing"


def _words(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _tolerance(value: Any) -> dict[str, Any] | None:
    """``readTolerance``: a plus-minus tolerance (signed deviations from the nominal) or limits (the
    least size and the greatest, absolute), or None."""
    if not isinstance(value, dict) or value.get("type") not in ("plus_minus", "limits"):
        return None
    upper, lower = _finite(value.get("upper")), _finite(value.get("lower"))
    return None if upper is None or lower is None else {"type": value["type"], "upper": upper, "lower": lower}


def _point3(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3 or any(_finite(v) is None for v in value):
        return None
    return [float(v) for v in value]


def _ref(ref: Any) -> dict[str, str]:
    ref = ref or {}
    written = _text(ref.get("written")) or _text(ref.get("ref"))
    return {"role": _text(ref.get("role")) or "feature", "ref": _text(ref.get("ref")) or written, "written": written,
            "status": _status(ref.get("status"))}


def _dimension(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    basic = value.get("basic") is True
    # A basic dimension is exact: a tolerance on one is not read as one.
    tolerance = None if basic else _tolerance(value.get("tolerance"))
    given = value.get("nominal") if isinstance(value.get("nominal"), dict) else {}
    return {"type": _text(value.get("type")), "basic": basic, "nominal": _finite(given.get("value")),
            "unit": _text(given.get("unit")) or "mm", "tolerance": tolerance}


def _datum(value: Any) -> dict[str, str] | None:
    letter = _text(value.get("letter")) if isinstance(value, dict) else ""
    return {"letter": letter} if letter else None


def _geometric_tolerance(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    # ``general``: the part's general profile, on the faces nothing else controls this build (its refs).
    return {"characteristic": _text(value.get("characteristic")), "value": _finite(value.get("value")),
            "unit": _text(value.get("unit")) or "mm", "zone": _text(value.get("zone")) or None,
            "datums": _words(value.get("datums")), "general": value.get("general") is True}


def _note(value: Any) -> dict[str, Any] | None:
    """``readNote``: a note's number (the engine's: Note 1 is its part's general profile where it has
    one), its words, whether it is general (it names no face and no annotation) and the ids it names."""
    if not isinstance(value, dict):
        return None
    number = value.get("number")
    whole = isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) \
        and float(number).is_integer() and number > 0
    return {"number": int(number) if whole else None, "text": _text(value.get("text")),
            "general": value.get("general") is True, "annotations": _words(value.get("annotations"))}


def _presentation(value: Any) -> dict[str, list[float]] | None:
    if not isinstance(value, dict):
        return None
    anchor, offset = _point3(value.get("anchor")), _point3(value.get("offset"))
    return {"anchor": anchor, "offset": offset} if anchor and offset else None


def key(part: int | None, ident: str) -> str:
    """What an annotation is known by in its document (``pmiKey``): its part and its id, an id being
    the author's and unique only on its part."""
    return f"{'' if part is None else part}:{ident}"


def entries(structure: dict[str, Any]) -> list[dict[str, Any]]:
    """The document's PMI as the viewer reads it (``readXbfPmi``): each entry with what its kind
    carries, a field missing or of the wrong type read as nothing, what it is known by (``key``),
    whether it is drawn (``supported``) and, where it is not, why (``unsupported``)."""
    found, seen = [], set()
    # Counted as the viewer counts them (``keyedByPart``): among the document's objects.
    items = [item for item in structure.get("pmi") or [] if isinstance(item, dict)]
    for index, item in enumerate(items):
        part = item.get("part")
        part = part if isinstance(part, int) and not isinstance(part, bool) else None
        # One the document lacks an id for, or repeats on a part, is kept apart by its place.
        ident = _text(item.get("id")) or f"#{index + 1}"
        known = key(part, ident)
        if known in seen:
            known = f"{known}#{index + 1}"
        seen.add(known)
        entry = {"key": known, "id": ident, "kind": _text(item.get("kind")), "label": _text(item.get("label")),
                 "status": _status(item.get("status")), "problem": _text(item.get("problem")), "part": part,
                 "refs": [_ref(ref) for ref in item.get("refs") or []],
                 "dimension": _dimension(item.get("dimension")), "datum": _datum(item.get("datum")),
                 "tolerance": _geometric_tolerance(item.get("geometric_tolerance")), "note": _note(item.get("note")),
                 "presentation": _presentation(item.get("presentation")), "xcaf_type": _text(item.get("xcaf_type"))}
        # Why it is not drawn in the document's own words where it has them (``reason``), else the viewer's.
        unsupported = _unsupported(entry)
        entry["unsupported"] = (_text(item.get("reason")) or unsupported) if unsupported else ""
        entry["supported"] = not entry["unsupported"]
        found.append(entry)
    return found


def _unsupported(entry: dict[str, Any]) -> str:
    """Why the viewer does not draw an entry (``unsupportedReason``), or "" for one it draws: an
    unknown kind, a dimension of a type it does not draw, a characteristic it does not draw, or the
    values its kind needs missing."""
    kind = entry["kind"]
    if kind == "unsupported":
        return f"{entry['xcaf_type']} is not one the viewer draws" if entry["xcaf_type"] else "not one the viewer draws"
    if kind not in KINDS:
        return f"{kind or 'an annotation'} is not one the viewer draws"
    if kind == "dimension":
        dimension = entry["dimension"] or {}
        if dimension.get("type") not in DIMENSION_TYPES:
            return f"a {dimension.get('type') or 'dimension'} dimension is not one the viewer draws"
        if dimension["basic"] and dimension["type"] != "distance":
            return f"a basic {dimension['type']} is not one the viewer draws"
        # A broken reference leaves nothing to measure (its nominal said as ``?``); one that resolved
        # has one, but where its limits say its sizes, which need none (a file states limits alone).
        limits = (dimension["tolerance"] or {}).get("type") == "limits"
        if dimension["nominal"] is None and entry["status"] == "ok" and not limits:
            return "it has no nominal"
    if kind == "datum" and entry["datum"] is None:
        return "it has no letter"
    if kind == "geometric_tolerance":
        tolerance = entry["tolerance"] or {}
        if tolerance.get("characteristic") not in CHARACTERISTICS:
            return f"{tolerance.get('characteristic') or 'this characteristic'} is not one the viewer draws"
        if tolerance["value"] is None:
            return "it has no tolerance value"
        if tolerance["general"] and tolerance["characteristic"] != "surface_profile":
            return f"a general {tolerance['characteristic']} is not one the viewer draws"
    if kind == "note":
        if not (entry["note"] or {}).get("text", "").strip():
            return "it has no text"
        if entry["note"]["number"] is None:
            return "it has no number"
    return ""


def _fixed(value: float, places: int) -> str:
    """JavaScript's ``toFixed`` of ``abs(value)``: the double itself rounded, a tie to the larger (8.35's
    double, a little under 8.35, is 8.3; Python's format rounds a tie to even)."""
    return str(Decimal(abs(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def decimals(value: float) -> int:
    fixed = _fixed(value, 4).rstrip("0")
    dot = fixed.find(".")
    return 0 if dot < 0 or dot == len(fixed) - 1 else len(fixed) - dot - 1


def number(value: float, places: int | None = None) -> str:
    """``pmiNumber``: at ``places`` decimals (what the value needs, up to four), a true minus sign."""
    places = decimals(value) if places is None else places
    fixed = _fixed(value, places)
    return fixed if float(fixed) == 0 else f"{MINUS if value < 0 else ''}{fixed}"


def _signed(value: float, places: int) -> str:
    if value == 0:
        return "0"
    return f"+{number(value, places)}" if value > 0 else number(value, places)


def tolerance_text(tolerance: dict[str, Any] | None) -> dict[str, Any] | None:
    """``pmiToleranceText``, at one number of places (what the more exact of its two numbers needs):
    a plus-minus one ``±0.2`` the same both ways, else each deviation signed, a zero bare; limits,
    the least size and the greatest, ``9.8–10.2`` (an en dash), stacked upper over lower where drawn."""
    if not tolerance:
        return None
    upper, lower = tolerance["upper"], tolerance["lower"]
    places = max(decimals(upper), decimals(lower))
    if tolerance.get("type") == "limits":
        upper_text, lower_text = number(upper, places), number(lower, places)
        return {"limits": True, "upper": upper_text, "lower": lower_text, "text": f"{lower_text}{EN_DASH}{upper_text}",
                "places": places}
    if upper > 0 and abs(upper + lower) < 1e-12:
        return {"symmetric": True, "text": f"±{number(upper, places)}", "upper": f"+{number(upper, places)}",
                "lower": f"{MINUS}{number(upper, places)}", "places": places}
    upper_text, lower_text = _signed(upper, places), _signed(lower, places)
    return {"symmetric": False, "text": f"{upper_text}/{lower_text}", "upper": upper_text, "lower": lower_text,
            "places": places}


def dimension_places(dimension: dict[str, Any]) -> int:
    """``pmiDimensionPlaces``: its tolerance's places (none without one) or what its nominal needs (up
    to four), whichever is more; limits given are its sizes, said at their own places."""
    tolerance = tolerance_text(dimension["tolerance"])
    if tolerance and tolerance.get("limits"):
        return tolerance["places"]
    nominal = dimension["nominal"]
    return max(tolerance["places"] if tolerance else 0, 0 if nominal is None else decimals(nominal))


def callout(entry: dict[str, Any]) -> dict[str, Any]:
    """``pmiCallout``: what a callout says, in the pieces its label draws and in words (``text``): a
    dimension's nominal and tolerance (its limits in place of a nominal, ``nominal`` None), a datum's
    letter, a frame's cells, a note's number (``flag`` for one on faces or annotations), the general
    profile as its part's Note 1 (drawn as no callout)."""
    if not entry.get("supported"):
        return {"kind": "unsupported", "title": entry.get("label") or entry["id"] or "",
                "text": entry["xcaf_type"] or entry["kind"] or "PMI"}
    if entry["kind"] == "dimension":
        dimension = entry["dimension"]
        tolerance = tolerance_text(dimension["tolerance"])
        diameter, basic = dimension["type"] == "diameter", dimension["basic"]
        head = {"kind": "dimension", "type": dimension["type"], "diameter": diameter, "basic": basic,
                "tolerance": tolerance, "unit": dimension["unit"],
                "title": "Basic distance" if basic else DIMENSION_NAMES.get(dimension["type"])}
        if tolerance and tolerance.get("limits"):
            return {**head, "nominal": None, "text": f"{'⌀' if diameter else ''}{tolerance['text']}"}
        # No nominal where the reference broke: there is nothing to measure it on.
        nominal = "?" if dimension["nominal"] is None else number(dimension["nominal"], dimension_places(dimension))
        within = f" {tolerance['text']}" if tolerance else ""
        said = f"{'⌀' if diameter else ''}{nominal}{within}{' basic' if basic else ''}"
        return {**head, "nominal": nominal, "text": said}
    if entry["kind"] == "datum":
        return {"kind": "datum", "letter": entry["datum"]["letter"], "title": "Datum",
                "text": f"Datum {entry['datum']['letter']}"}
    if entry["kind"] == "note":
        note = entry["note"]
        return {"kind": "note", "number": note["number"], "flag": not note["general"],
                "title": f"Note {note['number']}", "text": note["text"]}
    tolerance = entry["tolerance"]
    datums = list(tolerance["datums"])
    if tolerance["general"]:
        return {"kind": "general_profile", "number": 1, "title": "Note 1",
                "text": f"Unless otherwise noted, all surfaces profile {number(tolerance['value'])}"
                        f"{' to ' + '|'.join(datums) if datums else ''}"}
    diameter, shown = tolerance["zone"] == "diameter", number(tolerance["value"])
    name = CHARACTERISTIC_NAMES[tolerance["characteristic"]]
    return {"kind": "frame", "characteristic": tolerance["characteristic"], "diameter": diameter, "value": shown,
            "datums": datums, "unit": tolerance["unit"], "title": name,
            "text": " | ".join([f"{name} {'⌀' if diameter else ''}{shown}", *datums])}


# --- a face, from its part's mesh (xbfEntities.js) -------------------------------------------

PLANE_NORMAL = 1e-6
SQUARE = 1e-4
RADIAL = 1e-3
ROUND = 1e-3


def _dot(a: Any, b: Any) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Any, b: Any) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a: Any, b: Any) -> list[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _scale(a: Any, k: float) -> list[float]:
    return [a[0] * k, a[1] * k, a[2] * k]


def _cross(a: Any, b: Any) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _length(a: Any) -> float:
    return math.hypot(a[0], a[1], a[2])


def _unit(a: Any) -> list[float] | None:
    size = _length(a)
    return _scale(a, 1 / size) if size > 1e-12 else None


def _across(v: Any, n: Any) -> list[float]:
    return _sub(v, _scale(n, _dot(v, n)))


def face_nodes(mesh: Any, ordinal: int) -> tuple[list[list[float]], list[list[float]]] | None:
    """``xbfFaceNodes``: a face's nodes and their normals, each node once, in the order its
    triangles first name them; None for no such face."""
    rows = np.nonzero(np.asarray(mesh.faces)[:, 0] == ordinal)[0] if len(mesh.faces) else []
    if not len(rows):
        return None
    _ordinal, first, count = (int(v) for v in mesh.faces[rows[0]])
    seen, points, normals = set(), [], []
    for node in mesh.indices[first:first + count]:
        node = int(node)
        if node in seen:
            continue
        seen.add(node)
        points.append([float(v) for v in mesh.positions[node]])
        normals.append([float(v) for v in mesh.normals[node]])
    return points, normals


def _solve3(m: list[float], b: list[float]) -> list[float] | None:
    a, bb, c, d, e, f, g, h, i = m
    det = a * (e * i - f * h) - bb * (d * i - f * g) + c * (d * h - e * g)
    size = max(abs(v) for v in m)
    if not abs(det) > size * size * size * 1e-9:
        return None
    inverse = [e * i - f * h, c * h - bb * i, bb * f - c * e,
               f * g - d * i, a * i - c * g, c * d - a * f,
               d * h - e * g, bb * g - a * h, a * e - bb * d]
    return [(inverse[row * 3] * b[0] + inverse[row * 3 + 1] * b[1] + inverse[row * 3 + 2] * b[2]) / det
            for row in range(3)]


def _meeting_point(points: list[list[float]], directions: list[list[float]],
                   keep: list[float] | None = None) -> list[float] | None:
    m, b = [0.0] * 9, [0.0, 0.0, 0.0]
    for point, d in zip(points, directions):
        for row in range(3):
            for column in range(3):
                projector = (1 if row == column else 0) - d[row] * d[column]
                m[row * 3 + column] += projector
                b[row] += projector * point[column]
    if keep:
        for row in range(3):
            for column in range(3):
                m[row * 3 + column] += keep[row] * keep[column]
    return _solve3(m, b)


def _round_about(points: list[list[float]], normals: list[list[float]], center: list[float],
                 off: float) -> float | None:
    radii = [_length(_sub(point, center)) for point in points]
    radius = sum(radii) / len(radii)
    if not radius > off:
        return None
    if any(abs(value - radius) > max(radius * ROUND, off) for value in radii):
        return None
    radial = all(_length(_cross(_scale(_sub(point, center), 1 / radii[i]), normals[i])) <= RADIAL
                 for i, point in enumerate(points))
    return radius if radial else None


def face_surface(mesh: Any, ordinal: int) -> dict[str, Any] | None:
    """``xbfFaceSurface``, the readings a callout stands on: a plane (``normal``, ``origin``) or a
    cylinder (``axis``, ``origin``, ``radius``); ``{"type": "surface"}`` for anything else."""
    nodes = face_nodes(mesh, ordinal)
    if not nodes or len(nodes[0]) < 3:
        return None
    points = nodes[0]
    normals = [_unit(normal) or [0.0, 0.0, 0.0] for normal in nodes[1]]
    count = len(points)
    total = [0.0, 0.0, 0.0]
    for point in points:
        total = _add(total, point)
    middle = _scale(total, 1 / count)
    span = max(_length(_sub(point, middle)) for point in points)
    far = max(max(abs(point[0]), abs(point[1]), abs(point[2])) for point in points)
    off = max(span * 1e-4, far * 4e-6, 1e-7)
    first = normals[0]
    parallel = all(_dot(normal, first) >= 1 - PLANE_NORMAL for normal in normals)
    if parallel and all(abs(_dot(_sub(p, middle), first)) <= off for p in points):
        return {"type": "plane", "normal": first, "origin": middle}
    across = first
    for normal in normals:
        if abs(_dot(normal, first)) < abs(_dot(across, first)):
            across = normal
    axis = _unit(_cross(first, across))
    if axis and _length(_cross(first, across)) > 1e-3 and all(abs(_dot(normal, axis)) <= SQUARE for normal in normals):
        # Each node and normal flattened onto the plane square to the axis through the origin.
        flat = [_across(point, axis) for point in points]
        directions = [_unit(_across(normal, axis)) or normal for normal in normals]
        center = _meeting_point(flat, directions, axis)
        radius = center and _round_about(flat, directions, center, off)
        if radius:
            origin = _add(center, _scale(axis, _dot(middle, axis)))
            return {"type": "cylinder", "axis": axis, "origin": origin, "radius": radius}
    return {"type": "surface"}


def _place_point(m: list[float], p: Any) -> list[float]:
    return [m[row] * p[0] + m[4 + row] * p[1] + m[8 + row] * p[2] + m[12 + row] for row in range(3)]


def _place_direction(m: list[float], d: Any) -> list[float]:
    return _unit([m[row] * d[0] + m[4 + row] * d[1] + m[8 + row] * d[2] for row in range(3)]) or list(d)


def element(mesh: Any, ordinal: int, matrix: list[float]) -> dict[str, Any] | None:
    """A face where its instance stands (``elementGeometry(id, { points: true })``): its surface
    and its nodes, placed by the instance's matrix (column-major, the structure's)."""
    surface = face_surface(mesh, ordinal)
    nodes = face_nodes(mesh, ordinal)
    if surface is None or nodes is None:
        return None
    if surface["type"] == "plane":
        placed = {"type": "plane", "normal": _place_direction(matrix, surface["normal"]),
                  "origin": _place_point(matrix, surface["origin"])}
    elif surface["type"] == "cylinder":
        placed = {"type": "cylinder", "axis": _place_direction(matrix, surface["axis"]),
                  "origin": _place_point(matrix, surface["origin"]), "radius": surface["radius"]}
    else:
        placed = {"type": surface["type"]}
    return {"surface": placed, "points": [_place_point(matrix, point) for point in nodes[0]]}


# --- where it stands (xbfPmiLayout.js) -------------------------------------------------------

SPREAD = math.pi / 4.5
REACH_SHARE, REACH_MIN = 0.18, 4.0


def _turned(v: Any, n: Any, angle: float) -> list[float]:
    """``v`` turned by ``angle`` about the unit axis ``n`` (Rodrigues')."""
    along = _scale(n, _dot(n, v) * (1 - math.cos(angle)))
    return _add(_add(_scale(v, math.cos(angle)), _scale(_cross(n, v), math.sin(angle))), along)


def _any_perpendicular(n: Any) -> list[float] | None:
    return _unit(_cross(n, [1, 0, 0]) if abs(n[0]) < 0.9 else _cross(n, [0, 1, 0]))


def drawn_on_part(entry: dict[str, Any]) -> bool:
    """``pmiDrawnOnPart``: whether an annotation is drawn on the part -- all but what the viewer says
    in its notes alone: a general note, the general profile, and a flag note naming annotations and
    no face (it has no face of its own to stand on)."""
    if (entry.get("note") or {}).get("general") or (entry.get("tolerance") or {}).get("general"):
        return False
    return not (entry["kind"] == "note" and not entry["refs"])


def reach(bounds: tuple[Any, Any] | None) -> float:
    diagonal = _length(_sub(bounds[1], bounds[0])) if bounds else 0.0
    return max(REACH_MIN, diagonal * REACH_SHARE)


def feature_point(geometry: dict[str, Any] | None, centre: Any = (0, 0, 0)) -> list[float] | None:
    """``pmiFeaturePoint``: a node of the face nearest its nodes' middle; a cylinder's rim node at
    its axis's far end, the one farthest out from the model's middle."""
    points = (geometry or {}).get("points") or []
    if not points:
        origin = ((geometry or {}).get("surface") or {}).get("origin")
        return list(origin) if origin else None
    surface = geometry.get("surface") or {}
    if surface.get("type") == "cylinder" and surface.get("axis"):
        axis = surface["axis"]
        far = max(_dot(point, axis) for point in points)
        rim = [point for point in points if _dot(point, axis) > far - 1e-6 * max(1, abs(far))]
        best = rim[0]
        for point in rim:
            if _length(_sub(point, centre)) > _length(_sub(best, centre)) + 1e-9:
                best = point
        return list(best)
    total = [0.0, 0.0, 0.0]
    for point in points:
        total = _add(total, point)
    middle = _scale(total, 1 / len(points))
    best = points[0]
    for point in points:
        if _length(_sub(point, middle)) < _length(_sub(best, middle)) - 1e-9:
            best = point
    return list(best)


def _edge_point(geometry: dict[str, Any], centre: Any, n: Any) -> list[float] | None:
    points = geometry.get("points") or []
    if not points:
        origin = (geometry.get("surface") or {}).get("origin")
        return list(origin) if origin else None

    def out(point: Any) -> float:
        return _length(_across(_sub(point, centre), n))

    best = points[0]
    for point in points:
        if out(point) > out(best) + 1e-9:
            best = point
    return list(best)


def _outward(geometry: dict[str, Any] | None) -> list[float] | None:
    surface = (geometry or {}).get("surface") or {}
    if surface.get("type") == "plane" and surface.get("normal"):
        return _unit(surface["normal"])
    if surface.get("type") == "cylinder" and surface.get("axis"):
        return _unit(surface["axis"])
    return None


# How far an axis may lean off square to what a distance measures, or two axes off parallel (sin).
AXIS_SQUARE = 1e-3


def _distance_end(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """One end of a distance (``distanceEnd``): a flat face's plane or a round face's axis."""
    surface = (geometry or {}).get("surface") or {}
    if surface.get("type") == "plane" and surface.get("normal") and surface.get("origin"):
        return {"origin": surface["origin"], "normal": _unit(surface["normal"]), "axis": None}
    if surface.get("type") == "cylinder" and surface.get("axis") and surface.get("origin"):
        return {"origin": surface["origin"], "normal": None, "axis": _unit(surface["axis"])}
    return None


def _measured_along(source: dict[str, Any], target: dict[str, Any]) -> list[float] | None:
    """``measuredAlong``: the first plane's normal, else the other's; two axes, square to both."""
    if source["normal"]:
        n = source["normal"]
    elif target["normal"]:
        n = target["normal"]
    else:
        if _length(_cross(source["axis"], target["axis"])) > AXIS_SQUARE:
            return None
        n = _unit(_across(_sub(target["origin"], source["origin"]), source["axis"]))
    if not n:
        return None
    return n if all(not end["axis"] or abs(_dot(end["axis"], n)) <= AXIS_SQUARE for end in (source, target)) else None


def _on_level(point: Any, n: Any, end: dict[str, Any]) -> list[float]:
    """``point`` moved along what a distance measures (``n``) to the level of one of its ends."""
    return _sub(point, _scale(n, _dot(point, n) - _dot(end["origin"], n)))


def _on_axis(point: Any, end: dict[str, Any]) -> list[float]:
    """The point of a round end's axis nearest ``point``."""
    return _add(end["origin"], _scale(end["axis"], _dot(_sub(point, end["origin"]), end["axis"])))


def _broken(at: dict[str, Any] | None, placed: str) -> dict[str, Any] | None:
    """A callout whose feature cannot be found: drawn where its code placed it, else nowhere."""
    if not at:
        return None
    return {"anchor": at["anchor"], "label": _add(at["anchor"], at["offset"]), "dimension": None, "presentation": at,
            "placed": placed, "broken": True}


def construction(entry: dict[str, Any], geometry: dict[str, Any], bounds: tuple[Any, Any] | None,
                 turn: int = 0, placement: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """``pmiConstruction``: the scene points a callout is drawn from -- its anchor, its label, a
    distance's dimension and extension lines -- or None where it can be drawn nowhere or is said in
    the notes alone (``drawn_on_part``). ``placement``: one to draw it at in place of its code's (a
    view's own), in the scene's coordinates."""
    if not drawn_on_part(entry):
        return None
    centre = _scale(_add(bounds[0], bounds[1]), 0.5) if bounds else [0.0, 0.0, 0.0]
    far = reach(bounds)
    given = placement or entry["presentation"]
    at = {"anchor": list(given["anchor"]), "offset": list(given["offset"])} if given else None
    placed = "given" if given else "default"
    if entry["kind"] == "dimension" and entry["dimension"]["type"] == "distance":
        source, target = _distance_end(geometry.get("from")), _distance_end(geometry.get("to"))
        n = _measured_along(source, target) if source and target else None
        if not n:
            return _broken(at, placed)
        if at:
            anchor = at["anchor"]
        elif source["normal"]:
            anchor = _edge_point(geometry["from"], centre, n)
        else:
            anchor = _on_axis(feature_point(geometry["from"], centre), source)
        if at:
            offset = at["offset"]
        else:
            away = _unit(_across(_sub(anchor, centre), n)) or _any_perpendicular(n)
            side = _turned(away, n, turn * SPREAD)
            # Halfway between the ends, out to the side.
            offset = _add(_scale(n, (_dot(target["origin"], n) - _dot(anchor, n)) / 2), _scale(side, far * 0.5))
        label = _add(anchor, offset)
        on_from, on_to = _on_level(label, n, source), _on_level(label, n, target)
        # A plane's extension line runs square to it from the anchor's foot on it; an axis's from its
        # point nearest the dimension line's end.
        extensions = [[_on_level(anchor, n, end) if end["normal"] else _on_axis(on, end), on]
                      for end, on in ((source, on_from), (target, on_to))]
        return {"anchor": anchor, "label": label, "dimension": {"from": on_from, "to": on_to, "extensions": extensions},
                "presentation": {"anchor": anchor, "offset": offset}, "placed": placed}
    feature = geometry.get("feature")
    out = _outward(feature)
    if not feature or not out:
        return _broken(at, placed)
    anchor = at["anchor"] if at else feature_point(feature, centre)
    if at:
        offset = at["offset"]
    else:
        away = _unit(_across(_sub(anchor, centre), out)) or _any_perpendicular(out)
        side = _turned(away, out, turn * SPREAD)
        offset = _add(_scale(out, far), _scale(side, far * 0.6))
    return {"anchor": anchor, "label": _add(anchor, offset), "dimension": None,
            "presentation": {"anchor": anchor, "offset": offset}, "placed": placed}


def to_scene(presentation: dict[str, Any] | None, matrix: list[float] | None) -> dict[str, Any] | None:
    """``pmiPresentationToScene``: a placement in its part's frame where the part stands."""
    if not presentation or not matrix:
        return presentation
    return {"anchor": _place_point(matrix, presentation["anchor"]),
            "offset": [matrix[row] * presentation["offset"][0] + matrix[4 + row] * presentation["offset"][1]
                       + matrix[8 + row] * presentation["offset"][2] for row in range(3)]}


def rest_bounds(structure: dict[str, Any], meshes: dict[str, Any]) -> tuple[Any, Any]:
    """The box of the model at rest that its callouts are laid out by (the viewer's ``restBounds``):
    every placed part's, hidden or shown, as Explode's records measure it (``explode.instance_records``)."""
    from cadgen.engine.render.explode import instance_records, part_box

    boxes = [part_box(meshes[prototype["key"]]) for prototype in structure["prototypes"]]
    matrices = [np.array(instance["matrix"], float).reshape(4, 4).T for instance in structure["instances"]]
    return instance_records(structure, boxes, matrices)[1]


def placement(structure: dict[str, Any], part: int, hidden: frozenset[int] = frozenset()) -> int | None:
    """The instance a part's PMI is drawn at: the part's first placement the picture shows
    (``hidden``: the instances it leaves out, by ``display.hidden`` and ``display.isolated``); None
    where it shows none."""
    return next((index for index, instance in enumerate(structure["instances"])
                 if instance.get("prototype") == part and index not in hidden), None)


def constructions(structure: dict[str, Any], meshes: dict[str, Any], bounds: tuple[Any, Any] | None,
                  hidden: frozenset[int] = frozenset(),
                  view: dict[str, Any] | None = None) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Every supported entry drawn on the part with its construction (``useXbfPmi``'s), None where it
    is drawn nowhere: its references resolved as the engine resolves them, a role's first that names
    one face taken from its part's mesh where the part's first placement shown stands
    (``placement``), the placement its code gives it taken from that frame, and each later
    annotation of a feature turned from the one before it. An entry whose part the picture shows
    nowhere is drawn nowhere. ``bounds``: the model's at rest (``rest_bounds``); ``hidden``: the
    instances the picture leaves out; ``view`` (``views``'): what it shows alone, each it places
    where it places it (every entry turned as without it, as the viewer turns them)."""
    from cadgen.engine import refs

    prototypes, instances = structure["prototypes"], structure["instances"]
    placed_by = {key(view["part"], ident): at for ident, at in view["place"].items()} if view else {}
    found, turns = [], {}
    for entry in entries(structure):
        if not entry["supported"] or not drawn_on_part(entry):
            continue
        shown = None
        if entry["part"] is not None:
            shown = placement(structure, entry["part"], hidden)
            if shown is None:
                found.append((entry, None))
                continue
        geometry, first = {}, entry["key"]
        for at, ref in enumerate(entry["refs"]):
            if ref["role"] in geometry:  # a role stands on its first face (a profile's or a note's on several)
                continue
            face = None
            if ref["status"] == "ok":
                try:
                    hits = refs.resolve_structure(structure, ref["ref"])
                except refs.RefError:  # a ref the page cannot find names nothing here either
                    hits = []
                if len(hits) == 1 and hits[0].kind == "face":
                    # A ref names its part's first occurrence: its face is taken where the part is drawn.
                    instance = hits[0].node.payload["instance"] if shown is None else shown
                    prototype = prototypes[hits[0].node.payload["prototype"]]
                    face = element(meshes[prototype["key"]], int(hits[0].ordinal), instances[instance]["matrix"])
                    if at == 0:  # what a feature's turns count by: the first reference's element, as the viewer counts
                        first = f"i{instance}/face/{hits[0].ordinal}"
            geometry[ref["role"]] = face
        frame = None if shown is None else instances[shown]["matrix"]
        placed = {**entry, "presentation": to_scene(entry["presentation"], frame)}
        turn = turns.get(first, 0)
        turns[first] = turn + 1
        here = to_scene(placed_by.get(entry["key"]), frame)  # a view's own placement of it
        found.append((entry, construction(placed, geometry, bounds, turn, here)))
    # In a view, what it shows alone (``pmiViewShows``), as the viewer draws its items.
    return [(entry, made) for entry, made in found if view is None or view_shows(view, entry)]


def left_out(structure: dict[str, Any], found: list[tuple[dict[str, Any], dict[str, Any] | None]],
             hidden: frozenset[int] = frozenset(), view: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """What a picture leaves out of the document's PMI, and why, each ``{id, part, status, reason}``
    (``part`` its part's name, which with the id names it): an entry the viewer does not draw (as its
    PMI section says it is not shown), a note the viewer says in its notes alone (``NOTE``), one
    whose part the picture shows nowhere, and one with no feature to stand on and no placement in
    its code. In a view, only what it shows (what it does not is no part of it). ``found``: what
    ``constructions`` made, with the same ``hidden`` and ``view``."""
    made = {entry["key"]: construction for entry, construction in found}
    prototypes = structure["prototypes"]
    left = []
    for entry in entries(structure):
        if made.get(entry["key"]) is not None or (view is not None and not view_shows(view, entry)):
            continue
        if not entry["supported"]:
            reason = entry["unsupported"]
        elif not drawn_on_part(entry):
            reason = NOTE
        elif entry["part"] is not None and placement(structure, entry["part"], hidden) is None:
            reason = "no placement of its part is shown"
        else:
            reason = "no feature to stand it on and no placement in its code"
        part = prototypes[entry["part"]].get("name") if entry["part"] in range(len(prototypes)) else None
        left.append({"id": entry["id"], "part": part, "status": entry["status"], "reason": reason})
    return left


# --- a part's named views (xbfPmi.js readXbfPmi, pmiViews.js) ---------------------------------

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
# How near a world axis a placed section's normal must be: a placement's own rounding, no more.
ON_AXIS = 1e-9


def _camera(value: Any) -> dict[str, Any] | None:
    """``readCamera``: the side from the target toward the eye (``direction``, a preset's as the
    stills' are), its up, the preset it is (None for the code's own) and its projection; None
    without both vectors."""
    if not isinstance(value, dict) or not _point3(value.get("direction")) or not _point3(value.get("up")):
        return None
    return {"preset": _text(value.get("preset")) or None, "direction": _point3(value["direction"]),
            "up": _point3(value["up"]), "projection": _text(value.get("projection")) or None}


def _section(value: Any) -> dict[str, Any] | None:
    """``readSection``: the Clip's shape, one plane across ``axis`` at ``at`` keeping the lower side
    (``invert``: the upper); None for none, or for one that is not that."""
    if (not isinstance(value, dict) or value.get("axis") not in SECTION_AXES or _finite(value.get("at")) is None
            or not isinstance(value.get("invert"), bool)):
        return None
    return {"axis": value["axis"], "at": value["at"], "invert": value["invert"]}


def views(structure: dict[str, Any]) -> list[dict[str, Any]]:
    """Each part's named views as the viewer reads them (``readXbfPmi``'s ``views``, from
    ``structure["pmi_views"]``), in the code's order, known by part and name (``key``): ``camera``,
    ``section``, ``shows`` (ids, None for every one of its part's), ``place`` (its own placements by
    id, its part's frame), whether the viewer can apply it (``supported``) and, where not, why."""
    found, seen = [], set()
    items = [item for item in structure.get("pmi_views") or [] if isinstance(item, dict)]
    for index, item in enumerate(items):
        part = item.get("part")
        part = part if isinstance(part, int) and not isinstance(part, bool) else None
        name = _text(item.get("name")) or f"#{index + 1}"
        known = key(part, name)
        if known in seen:
            known = f"{known}#{index + 1}"
        seen.add(known)
        camera, section = _camera(item.get("camera")), _section(item.get("section"))
        place = item.get("place") if isinstance(item.get("place"), dict) else {}
        shows = item.get("shows")
        # One the viewer cannot apply says why: it is never seen down another camera, or uncut.
        unsupported = "it has no camera" if camera is None else ""
        if not unsupported and item.get("section") is not None and section is None:
            unsupported = "its section is not one the viewer applies"
        if not unsupported and shows is not None and not isinstance(shows, list):
            unsupported = "what it shows is not a list of ids"
        found.append({"key": known, "kind": "view", "part": part, "name": name, "label": _text(item.get("label")),
                      "camera": camera, "section": section, "shows": _words(shows) if isinstance(shows, list) else None,
                      "place": {ident: _presentation(at) for ident, at in place.items() if ident and _presentation(at)},
                      "supported": not unsupported, "unsupported": unsupported})
    return found


def _clean(value: float) -> float:
    """A coordinate free of the float noise a placement leaves, and of a negative zero."""
    return float(f"{value:.12g}") + 0.0


def placed_section(section: dict[str, Any], matrix: list[float]) -> dict[str, Any] | None:
    """``placedSection``: a view's section (its part's frame) where ``matrix`` (column-major) places
    the part -- the Clip's settings in the scene's -- or None where the placement turns its axis off
    every world axis. Its plane keeps the side it kept: turned to point down a world axis, its
    ``invert`` flips."""
    index = SECTION_AXES.index(section["axis"])
    along = [0.0, 0.0, 0.0]
    along[index] = 1.0
    normal = _place_direction(matrix, along)
    world = next((axis for axis, component in enumerate(normal) if abs(abs(component) - 1) <= ON_AXIS), None)
    if world is None:
        return None
    point = [0.0, 0.0, 0.0]
    point[index] = section["at"]
    return {"axis": SECTION_AXES[world], "at": _clean(_place_point(matrix, point)[world]),
            "invert": not section["invert"] if normal[world] < 0 else section["invert"]}


def view_at(view: dict[str, Any], structure: dict[str, Any],
            hidden: frozenset[int] = frozenset()) -> dict[str, Any] | None:
    """``pmiViewAt``: where a view is seen from -- its part's first placement shown (``instance``,
    ``placement``), its camera's ``direction`` (from the part toward the eye) and ``up`` placed by
    it, and its section as the Clip cuts it there (``section``), None where it has none or where the
    placement turns its axis off a world axis (``section_off``). None where no placement of its part
    is shown, or the view is one the viewer cannot apply."""
    if not view["supported"] or view["part"] is None:
        return None
    instance = placement(structure, view["part"], hidden)
    if instance is None:
        return None
    matrix = structure["instances"][instance].get("matrix") or IDENTITY
    section = placed_section(view["section"], matrix) if view["section"] else None
    return {"instance": instance, "direction": _place_direction(matrix, view["camera"]["direction"]),
            "up": _place_direction(matrix, view["camera"]["up"]), "section": section,
            "section_off": bool(view["section"]) and section is None}


def view_shows(view: dict[str, Any], entry: dict[str, Any]) -> bool:
    """``pmiViewShows``: one of its part's it names, or any of its part's where it names none."""
    return entry["part"] == view["part"] and (view["shows"] is None or entry["id"] in view["shows"])


# --- drawn over the picture (PmiOverlay.jsx, PmiLabel.jsx) -----------------------------------

# Ink on paper, the light theme's: the foreground on the background, as a label reads over any
# part. A document's picture is drawn on the light look's backdrop whatever its appearance (which
# only a drawing's paper takes), so its callouts are the light theme's too.
INK = (10, 10, 10)
PAPER = (255, 255, 255)
PAPER_ALPHA, BORDER_ALPHA, RULE_ALPHA, LEADER_ALPHA, BEHIND_ALPHA = 0.95, 0.6, 0.4, 0.85, 0.3
# A reference the engine could not stand the annotation on: it names nothing, or a face it cannot
# stand on (failed, red), or several (a warning, amber).
STATUS_COLOR = {"missing": (239, 68, 68), "invalid": (239, 68, 68), "ambiguous": (245, 158, 11)}
ARROW, ARROW_HALF, DATUM = 7.0, 2.6, 6.0
DASH, GAP = 4.0, 3.0
LABEL_CLEAR = 6.0
LABEL_MARGIN = 4.0
GAP_PX = 3.0
# The label: 11 px words (``text-tiny``) on 16 px lines, a 1 px rule and 1 px inside it, cells 4 px in;
# a datum's letter and a note's number medium (``font-medium``), a tolerance's two numbers 10 px.
TEXT, LETTER, SMALL, ROW, PAD, GLYPH = (400, 11), (500, 11), (400, 10), 16.0, 4.0, 12.0
# A basic dimension's box about its number: a 1 px rule 2 px out from it each side, 14 px words tall.
BOXED, BOXED_HEIGHT = 3.0, 16.0


def _glyph(painter: Any, name: str, x: float, middle: float, color: Any, alpha: float) -> None:
    """A GD&T symbol on the 24-unit grid the viewer's are drawn on (``pmiGlyphs.jsx``), 12 px."""
    k = GLYPH / 24

    def at(u: float, v: float) -> tuple[float, float]:
        return x + u * k, middle - GLYPH / 2 + v * k

    width = 2 * k
    if name == "diameter":
        painter.disc(at(12, 12), 6.5 * k, color, ring=width, alpha=alpha)
        painter.line(at(5.5, 18.5), at(18.5, 5.5), width, color, alpha)
    elif name == "flatness":
        corners = [at(3.5, 17), at(8, 7), at(20.5, 7), at(16, 17)]
        for index, corner in enumerate(corners):
            painter.line(corner, corners[(index + 1) % 4], width, color, alpha)
    elif name == "position":
        painter.disc(at(12, 12), 5.5 * k, color, ring=width, alpha=alpha)
        painter.line(at(12, 3), at(12, 21), width, color, alpha)
        painter.line(at(3, 12), at(21, 12), width, color, alpha)
    elif name == "surface_profile":
        # A half circle closed by its chord (``M3.5 16.5a8.5 8.5 0 0 1 17 0Z``).
        arc = [at(12 - 8.5 * math.cos(math.pi * step / 16), 16.5 - 8.5 * math.sin(math.pi * step / 16))
               for step in range(17)]
        for a, b in zip(arc, arc[1:]):
            painter.line(a, b, width, color, alpha)
        painter.line(arc[-1], arc[0], width, color, alpha)
    elif name == "flag":
        # A flag note's flag on its pole (``M6 21V4h11l-2.5 4.5L17 13H6``).
        flag = [at(6, 21), at(6, 4), at(17, 4), at(14.5, 8.5), at(17, 13), at(6, 13)]
        for a, b in zip(flag, flag[1:]):
            painter.line(a, b, width, color, alpha)


def _cells(said: dict[str, Any]) -> list[dict[str, Any]]:
    """A label's cells, each ``{glyphs, words, face, small}``: what ``PmiLabel`` lays out in a row."""
    from cadgen.engine.render.text import face

    words, small = face(*TEXT), face(*SMALL)
    if said["kind"] == "dimension":
        # Limits alone, in place of a nominal; deviations stacked beside it (``ml-0.5``), or ``±`` after it.
        cell = {"glyphs": ["diameter"] if said["diameter"] else [], "words": said["nominal"] or "", "face": words,
                "small": None, "boxed": said["basic"]}
        tolerance = said["tolerance"]
        if tolerance and tolerance.get("symmetric"):
            cell["words"] += f" {tolerance['text']}"
        elif tolerance:
            cell["small"] = (tolerance["upper"], tolerance["lower"])
            cell["beside"] = 0.0 if tolerance.get("limits") else 2.0
        cells = [cell]
    elif said["kind"] == "datum":
        cells = [{"glyphs": [], "words": said["letter"], "face": face(*LETTER), "small": None, "min": 20.0}]
    elif said["kind"] == "note":
        # A flag note's flag and its number (``gap-0.5``), its words the viewer's notes' to read.
        cells = [{"glyphs": ["flag"], "words": str(said["number"]), "face": face(*LETTER), "small": None, "gap": 2.0}]
    else:
        cells = [{"glyphs": [said["characteristic"]], "words": "", "face": words, "small": None},
                 {"glyphs": ["diameter"] if said["diameter"] else [], "words": said["value"], "face": words,
                  "small": None},
                 *({"glyphs": [], "words": datum, "face": words, "small": None} for datum in said["datums"])]
    for cell in cells:
        width = PAD * 2 + _content(cell)
        if cell["small"]:
            width += cell["beside"] + max(small.width(cell["small"][0]), small.width(cell["small"][1]))
        cell["width"] = max(width, cell.get("min", 0.0))
    return cells


def _content(cell: dict[str, Any]) -> float:
    """How wide a cell's glyphs and words are, a basic number's box about them: its padding and a
    tolerance's small words apart. A glyph and what follows it stand ``gap`` apart (``gap-px``)."""
    glyphs = len(cell["glyphs"]) * (GLYPH + cell.get("gap", 1.0))
    text = cell["face"].width(cell["words"]) if cell["words"] else 0
    return glyphs + text + (BOXED * 2 if cell.get("boxed") else 0)


def _label(painter: Any, box: dict[str, Any]) -> None:
    """A callout's label in its box: paper ruled in its colour (dashed, a broken reference's), its
    cells' glyphs and words."""
    from cadgen.engine.render.text import face

    small = face(*SMALL)
    x, y, w, h = box["x"] - box["w"] / 2, box["y"] - box["h"] / 2, box["w"], box["h"]
    painter.rounded_box(x, y, w, h, 2.0, PAPER, PAPER_ALPHA)
    if box["dashed"]:
        _dashed_box(painter, x, y, w, h, box["color"])
    else:
        painter.rounded_box(x, y, w, h, 2.0, box["color"], BORDER_ALPHA, stroke=1.0)
    at = x
    for index, cell in enumerate(box["cells"]):
        if index:
            painter.line((at, y + 1), (at, y + h - 1), 1.0, INK, RULE_ALPHA)
        # A datum's letter centred in its box (``min-w-5``); every other cell's content 4 px in.
        start = at + (cell["width"] - _content(cell)) / 2 if cell.get("min") else at + PAD
        for glyph in cell["glyphs"]:
            _glyph(painter, glyph, start, box["y"], INK, 1.0)
            start += GLYPH + cell.get("gap", 1.0)
        if cell.get("boxed"):
            # A basic dimension's number in its own box, ruled in the ink (``border px-0.5``).
            boxed = cell["face"].width(cell["words"]) + BOXED * 2
            painter.rounded_box(start, box["y"] - BOXED_HEIGHT / 2, boxed, BOXED_HEIGHT, 0.0, INK, 1.0, stroke=1.0)
            start += BOXED
        if cell["words"]:
            painter.words(cell["words"], cell["face"], start, box["y"], INK)
            start += cell["face"].width(cell["words"])
        if cell.get("boxed"):
            start += BOXED
        if cell["small"]:
            painter.words(cell["small"][0], small, start + cell["beside"], box["y"] - 5.6, INK)
            painter.words(cell["small"][1], small, start + cell["beside"], box["y"] + 5.6, INK)
        at += cell["width"]


def _dashed(painter: Any, a: Any, b: Any, width: float, color: Any, alpha: float) -> None:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if not length:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    at = 0.0
    while at < length:
        end = min(at + DASH, length)
        painter.line((a[0] + ux * at, a[1] + uy * at), (a[0] + ux * end, a[1] + uy * end), width, color, alpha)
        at = end + GAP


def _dashed_box(painter: Any, x: float, y: float, w: float, h: float, color: Any) -> None:
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    for index, corner in enumerate(corners):
        _dashed(painter, corner, corners[(index + 1) % 4], 1.0, color, 1.0)


def _arrow(painter: Any, tip: Any, toward: Any, color: Any, alpha: float, hollow: bool = False) -> None:
    angle = math.atan2(tip[1] - toward[1], tip[0] - toward[0])
    c, s = math.cos(angle), math.sin(angle)
    p = (tip[0] - ARROW * c + ARROW_HALF * s, tip[1] - ARROW * s - ARROW_HALF * c)
    q = (tip[0] - ARROW * c - ARROW_HALF * s, tip[1] - ARROW * s + ARROW_HALF * c)
    if hollow:
        for a, b in ((tip, p), (p, q), (q, tip)):
            painter.line(a, b, 1.0, color, alpha)
    else:
        painter.triangle(tip, p, q, color, alpha)


def _datum_triangle(painter: Any, base: Any, toward: Any, color: Any, alpha: float, hollow: bool = False) -> None:
    angle = math.atan2(toward[1] - base[1], toward[0] - base[0])
    along, side = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    corners = [(base[0] + side[0] * DATUM, base[1] + side[1] * DATUM),
               (base[0] - side[0] * DATUM, base[1] - side[1] * DATUM),
               (base[0] + along[0] * DATUM * 1.4, base[1] + along[1] * DATUM * 1.4)]
    if hollow:
        for index, corner in enumerate(corners):
            painter.line(corner, corners[(index + 1) % 3], 1.0, color, alpha)
    else:
        painter.triangle(*corners, color, alpha)


def _box_edge(start: Any, box: dict[str, float]) -> tuple[float, float]:
    dx, dy = start[0] - box["x"], start[1] - box["y"]
    if not dx and not dy:
        return box["x"], box["y"]
    s = min(box["w"] / 2 / abs(dx or 1e-9), box["h"] / 2 / abs(dy or 1e-9), 1)
    return box["x"] + dx * s, box["y"] + dy * s


def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return abs(a["x"] - b["x"]) * 2 < a["w"] + b["w"] and abs(a["y"] - b["y"]) * 2 < a["h"] + b["h"]


def separate(boxes: list[dict[str, Any]]) -> None:
    """``separateLabels``: a label the code never placed that covers one before it steps below it, a
    few pixels clear; one the code placed stays, and the others keep clear of it (in place)."""
    fixed = [box for box in boxes if not box["movable"]]
    placed: list[dict[str, Any]] = []
    for box in boxes:
        if box["movable"]:
            for _ in range(len(boxes) + 1):
                hit = next((other for other in [*fixed, *placed] if other is not box and _overlaps(box, other)), None)
                if hit is None:
                    break
                box["y"] = hit["y"] + (hit["h"] + box["h"]) / 2 + GAP_PX
        placed.append(box)


# How far nearer than a point the ray must meet the model to hide it: a thousandth of the model's
# size at rest, 0.05 mm at least, as the viewer's ``pmiHiddenAt`` (``XbfRenderer.jsx``). A leader
# starts on a node of its own face, which the ray meets at the point's depth.
HIDDEN_SHARE, HIDDEN_MIN = 1e-3, 0.05


class Hidden:
    """Whether the model hides a point from the camera (``pmiHidden.js``): a ray from the eye
    through the point meets a shown part's triangle nearer than the point by more than the
    tolerance, from ``bounds``, the model's at rest (``rest_bounds``); a triangle the clip cut away
    meets nothing, as the viewer's pick takes no hit the Clip's plane does not keep
    (``xbfScene.js``'s ``kept``). After the camera is framed."""

    def __init__(self, scene: Any, bounds: tuple[Any, Any] | None) -> None:
        triangles = []
        for index, instance in enumerate(scene.structure["instances"]):
            if index in scene.hidden:
                continue
            mesh = scene.meshes[scene.prototypes[instance["prototype"]]["key"]]
            if not len(mesh.indices):
                continue
            corners = np.asarray(mesh.positions, np.float64)[np.asarray(mesh.indices).reshape(-1, 3)]
            matrix = scene.matrices[index]
            triangles.append(corners @ matrix[:3, :3].T + matrix[:3, 3])
        self.triangles = np.concatenate(triangles) if triangles else np.zeros((0, 3, 3))
        camera = scene.camera
        self.eye = np.asarray(camera["eye"], float)
        self.direction = -np.asarray(camera["direction"], float)  # the camera's runs from the target to the eye
        self.perspective = camera["projection"] == "perspective"
        size = float(np.linalg.norm(np.subtract(bounds[1], bounds[0]))) if bounds else 0.0
        self.tolerance = max(HIDDEN_MIN, size * HIDDEN_SHARE)
        # The side of the clip's plane it keeps (``clip.plane``'s): the lower coordinates, ``invert`` the upper.
        clip = (getattr(scene, "display", None) or {}).get("clip")
        self.kept: tuple[int, float, float] | None = None
        if clip and clip.get("enabled") is not False:
            axis = SECTION_AXES.index(clip.get("axis", "x"))
            low, high = scene.rest_bounds() if clip.get("at") is None else (None, None)
            at = float(clip["at"]) if clip.get("at") is not None else (float(low[axis]) + float(high[axis])) / 2
            self.kept = (axis, at, 1.0 if clip.get("invert") else -1.0)

    def __call__(self, point: Any) -> bool:
        if not len(self.triangles):
            return False
        point = np.asarray(point, float)
        if self.perspective:
            direction = (point - self.eye) / (np.linalg.norm(point - self.eye) or 1.0)
            origin = self.eye
        else:
            direction = self.direction
            origin = point - direction * 1e6
        a, b, c = self.triangles[:, 0], self.triangles[:, 1], self.triangles[:, 2]
        e1, e2 = b - a, c - a
        p = np.cross(direction, e2)
        det = np.einsum("ij,ij->i", e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        t0 = origin - a
        u = np.einsum("ij,ij->i", t0, p) * inv
        q = np.cross(t0, e1)
        v = (q @ direction) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 0)
        if self.kept is not None:
            axis, at, side = self.kept
            hit &= side * (origin[axis] + t * direction[axis] - at) >= 0
        if not hit.any():
            return False
        return bool(t[hit].min() < float((point - origin) @ direction) - self.tolerance)


def _box(entry: dict[str, Any], made: dict[str, Any], to_px: Any) -> dict[str, Any]:
    """A callout's label box, in viewer pixels: at its label, a distance's beside its dimension line."""
    cells = _cells(callout(entry))
    label = to_px(made["label"])
    # A broken reference's callout dashed in its status's colour.
    box = {"x": label[0], "y": label[1], "w": sum(cell["width"] for cell in cells), "h": ROW + 4, "cells": cells,
           "movable": made["placed"] == "default" and not made["dimension"], "entry": entry, "made": made,
           "color": STATUS_COLOR.get(entry["status"], INK), "dashed": entry["status"] != "ok"}
    dimension = made["dimension"]
    if dimension:
        # A distance's words beside its dimension line, out from the part, clear of it.
        a, b, anchor = to_px(dimension["from"]), to_px(dimension["to"]), to_px(made["anchor"])
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        span = math.hypot(b[0] - a[0], b[1] - a[1])
        along = ((b[0] - a[0]) / span, (b[1] - a[1]) / span) if span > 1e-6 else (0.0, 0.0)
        out = (mid[0] - anchor[0], mid[1] - anchor[1])
        share = out[0] * along[0] + out[1] * along[1]
        out = (out[0] - along[0] * share, out[1] - along[1] * share)
        size = math.hypot(*out)
        if size < 1:
            out, size = (-(b[1] - a[1]), b[0] - a[0]), math.hypot(b[1] - a[1], b[0] - a[0]) or 1.0
        out = (out[0] / size, out[1] / size)
        far = abs(out[0]) * box["w"] / 2 + abs(out[1]) * box["h"] / 2 + LABEL_CLEAR
        box["x"], box["y"] = mid[0] + out[0] * far, mid[1] + out[1] * far
    return box


def _inside(at: float, size: float, edge: float) -> float:
    """``at`` moved, where it must be, to keep a label ``size`` across within 0..``edge``, 4 px in."""
    least = size / 2 + LABEL_MARGIN
    return min(max(at, least), max(least, edge - size / 2 - LABEL_MARGIN))


def _lines(painter: Any, box: dict[str, Any], to_px: Any, hidden: Any) -> None:
    """A callout's lines, to its box: a distance's extension and dimension lines and their arrows,
    any other's leader from its anchor to the label with its marker."""
    entry, made, color = box["entry"], box["made"], box["color"]

    def line(a: Any, b: Any, alpha: float) -> None:
        if box["dashed"]:
            _dashed(painter, a, b, 1.0, color, alpha)
        else:
            painter.line(a, b, 1.0, color, alpha)

    dimension = made["dimension"]
    if dimension:
        ends = [to_px(dimension["from"]), to_px(dimension["to"])]
        for start, end in dimension["extensions"]:
            line(to_px(start), to_px(end), LEADER_ALPHA * (BEHIND_ALPHA if hidden(start) else 1.0))
        line(ends[0], ends[1], LEADER_ALPHA)
        length = math.hypot(ends[1][0] - ends[0][0], ends[1][1] - ends[0][1])
        if length >= ARROW * 2.5:
            _arrow(painter, ends[0], ends[1], color, LEADER_ALPHA)
            _arrow(painter, ends[1], ends[0], color, LEADER_ALPHA)
        elif length > 1e-6:
            # Too short for its arrows between its ends: each outside its end, pointing in.
            ux, uy = (ends[1][0] - ends[0][0]) / length, (ends[1][1] - ends[0][1]) / length
            before = (ends[0][0] - ux * ARROW * 2, ends[0][1] - uy * ARROW * 2)
            after = (ends[1][0] + ux * ARROW * 2, ends[1][1] + uy * ARROW * 2)
            line(before, ends[0], LEADER_ALPHA)
            line(ends[1], after, LEADER_ALPHA)
            _arrow(painter, ends[0], before, color, LEADER_ALPHA)
            _arrow(painter, ends[1], after, color, LEADER_ALPHA)
    elif made["anchor"] is not None:
        anchor = to_px(made["anchor"])
        end = _box_edge(anchor, box)
        behind = not made.get("broken") and hidden(made["anchor"])
        alpha = LEADER_ALPHA * (BEHIND_ALPHA if behind else 1.0)
        line(anchor, end, alpha)
        if made.get("broken"):
            painter.disc(anchor, ARROW_HALF + 1, color, ring=1.0, alpha=alpha)
        elif entry["kind"] == "datum":
            _datum_triangle(painter, anchor, end, color, alpha, hollow=behind)
        else:
            _arrow(painter, anchor, end, color, alpha, hollow=behind)


def paint(frame: np.ndarray, drawn: list[tuple[dict[str, Any], dict[str, Any]]], project: Any, hidden: Any) -> None:
    """The callouts painted over ``frame`` (sRGB bytes, (h, w, 3), in place), as the viewer's
    overlay paints its canvas and lays its labels: ``drawn`` each entry with its construction,
    ``project`` world points to output pixels, ``hidden`` whether the model hides a world point."""
    from cadgen.engine.render.overlay import REFERENCE_HEIGHT, Painter

    height, width = frame.shape[:2]
    scale = height / REFERENCE_HEIGHT
    painter = Painter(frame, scale)

    def to_px(point: Any) -> tuple[float, ...]:
        return tuple(v / scale for v in project(np.array([point], float))[0])

    boxes = [_box(entry, made, to_px) for entry, made in drawn if made is not None]
    separate(boxes)
    # Every label inside the picture, 4 px in, as Measure's are kept (its leader follows it): a still
    # has no edge to pan past.
    for box in boxes:
        box["x"] = _inside(box["x"], box["w"], width / scale)
        box["y"] = _inside(box["y"], box["h"], height / scale)
    # Every label over every callout's lines, as the viewer's labels stand over its canvas.
    for box in boxes:
        _lines(painter, box, to_px, hidden)
    for box in boxes:
        _label(painter, box)
