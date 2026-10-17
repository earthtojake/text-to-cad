"""Bounding boxes of stored geometry, remembered by the bytes they measure.

A tight box costs ~0.08 ms per face, and an unchanged assembly asks for the
same boxes on every save. Each publication path that measures one keys it by
the geometry it measures (a component's BREP object hash, or the BinTools
digest of a leaf) plus the placement it is measured in, names the algorithm,
and this module adds the loaded OCP build. A box is a pure function of those
inputs, so a remembered one can never differ from a new measurement. Values
live in this process and in the store's ``index/bounds``; they are derived
facts about stored bytes (README law 2), never results of a model run.

Beside the boxes, and keyed the same way, the index remembers each
component's LEAF LAYOUT: how many leaves its encoded BREP holds and whether
every one of them sits at the prototype's own placement (no leaf carries a
location of its own). Publication records it while it measures those leaves,
and :func:`composed_bounds` reads it back to name the exact per-leaf box keys
of a placed component without decoding its BREP: a parent's bounds over its
children's components, the animation bake's leaf boxes.

It also remembers each component's TOPOLOGY: its face and edge counts, how many
of each are curved, and its loose box, the per-component facts the adaptive
edge policy classifies a result by (``step_scene_mesh.prototype_topology``,
``store.build._edge_rendering``): a build measures its own components as it
walks them and reads a linked child's here, decoding one only where its entry
is missing.

Keyed by a component's codec and BREP object under the geometric token scheme, it
remembers the GEOMETRIC TOKENS of its faces, edges and vertices
(``_internal/geometric_tokens``): the fallback matcher's names, measured on
demand -- where a part's display data is derived, or a reader resolves a ref in
that form -- and once.

Last, keyed by a component's codec, BREP object and a face's ordinal, it remembers
that FACE'S EXACT AREA AND CENTROID (``store.parts.measure_face``): measured when a
view asks (its Reference panel, its measure tool) or a mate's axis falls back to a
face's centroid, by one build-pool job, and once.
"""
from __future__ import annotations

import hashlib
import math
import struct
import threading
from collections import OrderedDict
from typing import Any, Callable, Mapping

from cadgen.store.parts import kernel_versions

_RAM_ENTRIES = 1 << 16
_ram: OrderedDict[str, Any] = OrderedDict()
_lock = threading.Lock()

LEAF_LAYOUT_ALGORITHM = "component_leaf_layout.algorithm2"
#: The box of one leaf of a placed component, measured untranslated under the leaf's own
#: rotation: keyed by the component's codec and BREP object, the leaf's ordinal and that
#: rotation, so the same body at the same rotation is measured once wherever it is translated
#: to, by a build's result and a compiled document alike
#: (``component_package.placed_prototype_bounds``), and a composed reader
#: (:func:`composed_bounds`) finds what the publication measured from the occurrence's
#: transform and the leaf layout alone.
PREPARED_OCCURRENCE_BOUNDS_ALGORITHM = "component_bbox.canonical_native_rotation.algorithm1"
#: Names ``step_scene_mesh.prototype_topology``: change what it counts or how
#: it measures the loose box, and change this name with it.
TOPOLOGY_ALGORITHM = "component_topology.faces_edges_curved_loose_box.algorithm1"
#: Names ``store.parts.measure_face``: a face's area and centroid by GProps over the face of
#: the decoded component. Change what it measures and change this name with it.
FACE_MEASURE_ALGORITHM = "face_area_centroid.gprops.algorithm1"


def _is_box(value: Any) -> bool:
    if value is None:
        return True
    if type(value) not in (list, tuple) or len(value) != 6:
        return False
    try:
        # An int beyond float range (a hand-edited entry) overflows here.
        finite = all(type(v) in (float, int) and math.isfinite(v) for v in value)
    except OverflowError:
        return False
    return finite and all(value[axis] <= value[axis + 3] for axis in range(3))


def _is_leaf_layout(value: Any) -> bool:
    if type(value) is not dict or set(value) != {"leaves", "inner"}:
        return False
    leaves, inner = value["leaves"], value["inner"]
    if type(leaves) is not int or leaves < 1 or type(inner) is not list or len(inner) != leaves:
        return False
    try:
        return all(type(row) is list and len(row) == 12
                   and all(type(v) in (float, int) and math.isfinite(v) for v in row) for row in inner)
    except OverflowError:
        return False


def _is_topology(value: Any) -> bool:
    counts = ("faces", "edges", "curvedFaces", "curvedEdges")
    if type(value) is not dict or set(value) != {*counts, "looseBox"}:
        return False
    if not all(type(value[key]) is int and value[key] >= 0 for key in counts):
        return False
    return value["curvedFaces"] <= value["faces"] and value["curvedEdges"] <= value["edges"] \
        and value["looseBox"] is not None and _is_box(value["looseBox"])


def bounds_key(algorithm: str, parts: tuple) -> str:
    """The ``index/bounds`` entry name for ``algorithm`` over ``parts`` on this
    OCP build. Raises ValueError when the OCP build is unknown."""
    return hashlib.sha256(repr((algorithm, parts, kernel_versions())).encode()).hexdigest()


def _remembered(key: str, valid: Callable[[Any], bool]) -> tuple[bool, Any]:
    """``(found, value)`` for an entry already in RAM or in ``index/bounds``."""
    with _lock:
        if key in _ram:
            _ram.move_to_end(key)
            return True, _ram[key]
    from cadgen.store.index import read_entry

    entry = read_entry("bounds", key)
    if entry is None or "value" not in entry or not valid(entry["value"]):
        return False, None
    with _lock:
        _ram[key] = entry["value"]
        while len(_ram) > _RAM_ENTRIES:
            _ram.popitem(last=False)
    return True, entry["value"]


def _remember(algorithm: str, parts: tuple, measure: Callable[[], Any], valid: Callable[[Any], bool]) -> Any:
    try:
        key = bounds_key(algorithm, parts)
    except ValueError:
        return measure()
    found, value = _remembered(key, valid)
    if found:
        return value
    from cadgen.store.index import write_entry
    from cadgen.store.paths import StoreUnwritableError

    value = measure()
    if not valid(value):
        return value
    try:
        write_entry("bounds", key, {"value": value})
    except (OSError, StoreUnwritableError):
        pass
    with _lock:
        _ram[key] = value
        while len(_ram) > _RAM_ENTRIES:
            _ram.popitem(last=False)
    return value


def cached_box(algorithm: str, parts: tuple, measure: Callable[[], Any]) -> Any:
    """``measure()``, remembered under ``algorithm`` and ``parts``.

    ``measure`` returns a box, six finite numbers (min xyz, max xyz), or None
    for geometry without bounds. ``parts`` holds strings, integers and bytes
    that state the measured geometry and its placement exactly. An unknown OCP
    build, an unreadable or unwritable store, or a stored value that is not a
    box just measures: correctness never depends on a hit.
    """
    return _remember(algorithm, parts, measure, _is_box)


def remembered_box(algorithm: str, parts: tuple) -> tuple[bool, Any]:
    """``(found, box)`` for a box already measured under ``algorithm`` and
    ``parts``, without measuring. ``found`` is False for an unknown OCP build."""
    try:
        key = bounds_key(algorithm, parts)
    except ValueError:
        return False, None
    return _remembered(key, _is_box)


def cached_leaf_layout(codec: str, brep: str, measure: Callable[[], Any]) -> Any:
    """A component's leaf layout, ``{"leaves": n, "inner": [...]}`` (``component_package.
    component_leaf_layout``), remembered by the encoded BREP it describes (its codec and
    object hash)."""
    return _remember(LEAF_LAYOUT_ALGORITHM, (str(codec), str(brep)), measure, _is_leaf_layout)


def cached_component_topology(codec: str, brep: str, measure: Callable[[], Any]) -> Any:
    """A component's topology facts (``step_scene_mesh.prototype_topology``),
    remembered by the encoded BREP they count (its codec and object hash)."""
    return _remember(TOPOLOGY_ALGORITHM, (str(codec), str(brep)), measure, _is_topology)


def _is_tokens(value: Any) -> bool:
    from cadgen._internal.geometric_tokens import TOKEN_RE

    return (type(value) is dict and set(value) == {"faces", "edges", "vertices"}
            and all(type(names) is list and all(type(name) is str and TOKEN_RE.fullmatch(name) for name in names)
                    for names in value.values()))


def cached_tokens(codec: str, brep: str, measure: Callable[[], dict]) -> dict:
    """The geometric tokens of a stored component's elements (``measure()``,
    ``geometric_tokens.element_tokens``), remembered by its codec and BREP object under
    the token scheme."""
    from cadgen._internal.geometric_tokens import GEOMETRIC_TOKEN_SCHEME

    return _remember(f"element_tokens.{GEOMETRIC_TOKEN_SCHEME}", (str(codec), str(brep)), measure, _is_tokens)


def _is_face_measure(value: Any) -> bool:
    if type(value) is not dict or set(value) != {"area", "center"}:
        return False
    area, center = value["area"], value["center"]
    try:
        return (type(area) in (float, int) and math.isfinite(area) and area >= 0 and type(center) is list
                and len(center) == 3 and all(type(v) in (float, int) and math.isfinite(v) for v in center))
    except OverflowError:
        return False


def cached_face_measure(codec: str, brep: str, face: int, measure: Callable[[], dict]) -> dict:
    """A stored component's face's exact area and centroid, ``{"area": a, "center": [x, y, z]}``
    (``measure()``, ``store.parts.measure_face``), remembered by the component's codec, its BREP
    object and the face's ordinal."""
    return _remember(FACE_MEASURE_ALGORITHM, (str(codec), str(brep), int(face)), measure, _is_face_measure)


def remembered_face_measure(codec: str, brep: str, face: int) -> dict | None:
    """The face's area and centroid when the store already holds them: read without measuring, and
    without the kernel (a view's route asks before it starts a job)."""
    try:
        key = bounds_key(FACE_MEASURE_ALGORITHM, (str(codec), str(brep), int(face)))
    except ValueError:
        return None
    found, value = _remembered(key, _is_face_measure)
    return value if found else None


class NotRemembered(LookupError):
    """The box :func:`composed_bounds` is asked for is not one the index remembers exactly:
    the caller measures it."""


_IDENTITY_PLACEMENT = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]


def _composed_placement(occurrence: list, inner: list) -> tuple[tuple, tuple]:
    """The placement of a leaf sitting at ``inner`` inside a prototype placed at
    ``occurrence`` (16 numbers): its rotation's rows and its translation, as the kernel
    composes them (rotation times the inner translation, plus the occurrence's)."""
    rows = [(occurrence[0], occurrence[1], occurrence[2]), (occurrence[4], occurrence[5], occurrence[6]),
            (occurrence[8], occurrence[9], occurrence[10])]
    columns = [(inner[0], inner[4], inner[8]), (inner[1], inner[5], inner[9]), (inner[2], inner[6], inner[10])]
    rotation = tuple(row[0] * column[0] + row[1] * column[1] + row[2] * column[2]
                     for row in rows for column in columns)
    offset = (inner[3], inner[7], inner[11])
    translation = tuple(occurrence[3 + 4 * axis] + (row[0] * offset[0] + row[1] * offset[1] + row[2] * offset[2])
                        for axis, row in enumerate(rows))
    return rotation, translation


def composed_bounds(occurrences: list[dict[str, Any]], components: Mapping[str, Mapping[str, Any]], *,
                    exact: bool = True) -> dict[str, list[float]]:
    """The box publication measures for these occurrences, from the per-leaf boxes it
    already remembered (:data:`PREPARED_OCCURRENCE_BOUNDS_ALGORITHM`).

    Each leaf's key is its component's codec and BREP object, its ordinal and the leaf's
    rotation; the leaf layout says where the leaf sits inside its prototype, and a leaf
    at the prototype's own placement takes the occurrence's placement as the kernel holds
    it -- the rotation and translation of the transform the tree records, set on a
    ``gp_Trsf`` -- so its key and its box, the remembered one shifted by that translation,
    are exactly what ``component_package.placed_prototype_bounds`` measures for that
    occurrence. A leaf the prototype places inside itself composes its placement with the
    occurrence's here, in Python arithmetic the kernel's can differ from by ulps, so under
    ``exact`` -- a tree's bounds, which every path must measure alike -- it is
    :class:`NotRemembered`; a reader that wants a box, not THE box (the animation bake's
    pivots) passes ``exact=False``. A layout the index does not hold is measured from the
    component's bytes and remembered. A box it does not hold is :class:`NotRemembered`.
    """
    from cadgen._internal.component_package import component_leaf_layout, decode_geometry_component
    from cadgen.store.materialize import _native_location_from_matrix
    from cadgen.store.objects import read_verified_object

    layouts: dict[str, dict[str, Any]] = {}
    boxes: list[list[float]] = []
    for occurrence in occurrences:
        cid = str(occurrence["component"])
        entry = components[cid]
        codec, brep = str(entry["codec"]), str(entry["brep"])
        layout = layouts.get(cid)
        if layout is None:
            # A component published before layouts were recorded decodes once here;
            # the layout is a pure function of the bytes and is remembered.
            layout = cached_leaf_layout(codec, brep, lambda entry=entry: component_leaf_layout(
                decode_geometry_component(entry, read_verified_object(entry["brep"])).wrapped))
            layouts[cid] = layout
        transform = occurrence["transform"]
        placed = None
        for leaf_ordinal, inner in enumerate(layout["inner"], start=1):
            if inner == _IDENTITY_PLACEMENT:
                if placed is None:
                    trsf = _native_location_from_matrix(transform).Transformation()
                    placed = (tuple(float(trsf.Value(row, column)) for row in range(1, 4) for column in range(1, 4)),
                              tuple(float(value) for value in trsf.TranslationPart().Coord()))
                rotation, translation = placed
            elif exact:
                raise NotRemembered(f"component {cid} places a leaf of its own")
            else:
                rotation, translation = _composed_placement(transform, inner)
            linear = struct.pack("<12d", rotation[0], rotation[1], rotation[2], 0.0,
                                 rotation[3], rotation[4], rotation[5], 0.0,
                                 rotation[6], rotation[7], rotation[8], 0.0)
            found, box = remembered_box(PREPARED_OCCURRENCE_BOUNDS_ALGORITHM, (codec, brep, leaf_ordinal, linear))
            if not found:
                raise NotRemembered(f"leaf {leaf_ordinal} of component {cid} has no remembered box in this placement")
            if box is not None:
                boxes.append([float(value) + translation[index % 3] for index, value in enumerate(box)])
    if not boxes:
        raise NotRemembered("no leaf has bounds")
    return {
        "min": [min(box[axis] for box in boxes) for axis in range(3)],
        "max": [max(box[axis] for box in boxes) for axis in range(3, 6)],
    }


def clear() -> None:
    """Forget this process's remembered boxes; the store's entries stay."""
    with _lock:
        _ram.clear()
