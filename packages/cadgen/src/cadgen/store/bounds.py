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
location of its own). Canonical publication records it while it measures
those leaves, and composing a parent's document tree from its children's
(``cadgen.store._compose_readback``) reads it back to name the exact per-leaf
box keys without decoding the BREP.

It also remembers each component's TOPOLOGY: its face and edge counts, how many
of each are curved, and its loose box, the per-prototype facts the adaptive
edge policy classifies a scene by (``step_scene_mesh.prototype_topology``). A
build of an all-link parent reads them by the BREP its pins name and decodes
only a component whose entry is missing (``cadgen.store._references``).
"""
from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from typing import Any, Callable

from cadgen.store.surfaces import kernel_versions

_RAM_ENTRIES = 1 << 16
_ram: OrderedDict[str, Any] = OrderedDict()
_lock = threading.Lock()

LEAF_LAYOUT_ALGORITHM = "component_leaf_layout.algorithm1"
#: Names ``step_scene_mesh.prototype_topology``: change what it counts or how
#: it measures the loose box, and change this name with it.
TOPOLOGY_ALGORITHM = "component_topology.faces_edges_curved_loose_box.algorithm1"


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
    return (type(value) is dict and set(value) == {"leaves", "placed"}
            and type(value["leaves"]) is int and value["leaves"] >= 1
            and type(value["placed"]) is bool)


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
    """A component's leaf layout, ``{"leaves": n, "placed": bool}``, remembered
    by the encoded BREP it describes (its codec and object hash)."""
    return _remember(LEAF_LAYOUT_ALGORITHM, (str(codec), str(brep)), measure, _is_leaf_layout)


def cached_component_topology(codec: str, brep: str, measure: Callable[[], Any]) -> Any:
    """A component's topology facts (``step_scene_mesh.prototype_topology``),
    remembered by the encoded BREP they count (its codec and object hash)."""
    return _remember(TOPOLOGY_ALGORITHM, (str(codec), str(brep)), measure, _is_topology)


def clear() -> None:
    """Forget this process's remembered boxes; the store's entries stay."""
    with _lock:
        _ram.clear()
