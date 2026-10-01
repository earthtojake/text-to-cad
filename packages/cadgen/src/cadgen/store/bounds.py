"""Bounding boxes of stored geometry, remembered by the bytes they measure.

A tight box costs ~0.08 ms per face, and an unchanged assembly asks for the
same boxes on every save. Each publication path that measures one keys it by
the geometry it measures (a component's BREP object hash, or the BinTools
digest of a leaf) plus the placement it is measured in, names the algorithm,
and this module adds the loaded OCP build. A box is a pure function of those
inputs, so a remembered one can never differ from a new measurement. Values
live in this process and in the store's ``index/bounds``; they are derived
facts about stored bytes (README law 2), never results of a model run.
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


def bounds_key(algorithm: str, parts: tuple) -> str:
    """The ``index/bounds`` entry name for ``algorithm`` over ``parts`` on this
    OCP build. Raises ValueError when the OCP build is unknown."""
    return hashlib.sha256(repr((algorithm, parts, kernel_versions())).encode()).hexdigest()


def cached_box(algorithm: str, parts: tuple, measure: Callable[[], Any]) -> Any:
    """``measure()``, remembered under ``algorithm`` and ``parts``.

    ``measure`` returns a box, six finite numbers (min xyz, max xyz), or None
    for geometry without bounds. ``parts`` holds strings, integers and bytes
    that state the measured geometry and its placement exactly. An unknown OCP
    build, an unreadable or unwritable store, or a stored value that is not a
    box just measures: correctness never depends on a hit.
    """
    try:
        key = bounds_key(algorithm, parts)
    except ValueError:
        return measure()
    with _lock:
        if key in _ram:
            _ram.move_to_end(key)
            return _ram[key]
    from cadgen.store.index import read_entry, write_entry
    from cadgen.store.paths import StoreUnwritableError

    entry = read_entry("bounds", key)
    if entry is not None and "value" in entry and _is_box(entry["value"]):
        value = entry["value"]
    else:
        value = measure()
        if not _is_box(value):
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


def clear() -> None:
    """Forget this process's remembered boxes; the store's entries stay."""
    with _lock:
        _ram.clear()
