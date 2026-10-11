"""The SECTION index: one component's exact cut by one plane.

An input-addressed derivation like ``mesh`` and ``drawing`` (``STORE.md`` §2):
the key hashes this module's scheme, the component's encoded BREP (its codec
and object hash) and the plane, in the component's own coordinates; the entry
points at the object holding the cut's loops as JSON -- the material the plane
cuts from the BREP's solids, and the curves it cuts from its sheets
(``cadgen._internal.brep_section``). The same BREP cut by the same plane
anywhere -- every occurrence of a part placed so the plane meets it the same
way -- is one entry, and a scheme change lands on new keys instead of
invalidating old ones in place.

Reads are kernel-free. The cutting is build-pool work (``sections`` artifact
jobs, ``cadgen.daemon.artifacts``): :func:`produce` runs in a worker. Every
store failure is best effort -- losing an entry costs a recomputation, never an
answer.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Callable
from typing import Any

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import is_object_hash, put_object, read_verified_object
from cadgen.store.paths import StoreUnwritableError

__all__ = [
    "SECTION_ENTRY_SCHEMA_VERSION",
    "SECTION_SCHEME",
    "SectionProductionError",
    "canonical_plane",
    "produce",
    "read",
    "section_key",
]

INDEX_KIND = "section"
SECTION_ENTRY_SCHEMA_VERSION = 1
# What the cut IS: the loops' JSON shape and how they are made. Hashed into
# every key, so a change here retires every entry by never asking for it again.
SECTION_SCHEME = "cadgen-brep-section-v3"
# Planes are rounded before they key or cut anything, so the same plane reached
# through two placements (one exact, one carrying 1e-16 of rotation noise) is
# one entry, and the cut is made with exactly the plane the key names.
_NORMAL_DECIMALS = 12
_OFFSET_DECIMALS = 9
# A normal whose rounded length is this close to 1 is already a unit normal.
# Rounding to 12 places moves a unit vector's length by about 1e-12, far inside it.
_UNIT_TOLERANCE = 1e-9
# The geometry fields a component entry carries in a tree (``validate_geometry_component``).
_COMPONENT_FIELDS = frozenset({"kind", "codec", "brep", "faceColors", "contentHash", "color", "eagerSurface"})


class SectionProductionError(ValueError):
    """A component OCCT could not cut, named with why."""


def _rounded(value: float, decimals: int) -> float:
    number = round(float(value), decimals)
    return 0.0 if number == 0 else number


def canonical_plane(normal, offset) -> tuple[tuple[float, float, float], float]:
    """``(unit normal, offset)`` rounded to the precision every key and cut uses.

    Idempotent, exactly: a request's items are canonical when the client keys
    them and are canonicalized again where they are checked, and the two must
    name the same plane bit for bit. So a normal is divided by its length only
    when its rounded form is not already a unit normal -- dividing a rounded
    normal by its length (1 +- 1e-12) again would move a 1.5 m offset by 1e-9
    every time -- and what is left is rounding, which rounding does not change.
    """
    values = [float(component) for component in normal]
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError("a section plane's normal is three finite numbers")
    length = math.sqrt(sum(value * value for value in values))
    if not length > 1e-12 or not math.isfinite(float(offset)):
        raise ValueError("a section plane needs a nonzero normal and a finite offset")
    unit = tuple(_rounded(value, _NORMAL_DECIMALS) for value in values)
    if abs(math.sqrt(sum(value * value for value in unit)) - 1.0) <= _UNIT_TOLERANCE:
        return unit, _rounded(float(offset), _OFFSET_DECIMALS)
    unit = tuple(_rounded(value / length, _NORMAL_DECIMALS) for value in values)
    return unit, _rounded(float(offset) / length, _OFFSET_DECIMALS)


def _hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def section_key(component: dict, normal, offset) -> str:
    """The index key for ``component``'s BREP cut by the plane ``normal . p == offset``."""
    brep = str(component.get("brep") or "")
    codec = str(component.get("codec") or "")
    if not is_object_hash(brep) or not codec:
        raise ValueError("a section key needs the component's codec and BREP object")
    unit, distance = canonical_plane(normal, offset)
    text = "\0".join((SECTION_SCHEME, codec, brep, *map(_hex, unit), _hex(distance)))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def component_entry(entry: dict) -> dict:
    """The tree form of a component (``brep`` is its object hash), from a view descriptor's."""
    tree_form = {key: entry[key] for key in _COMPONENT_FIELDS if key in entry and key != "brep"}
    tree_form["brep"] = entry.get("brepObject") or entry.get("brep")
    return tree_form


def read(key: str) -> dict | None:
    """The cut's loops, or ``None`` for a miss (or an entry whose object does not verify)."""
    entry = read_entry(INDEX_KIND, key)
    if not entry or entry.get("schemaVersion") != SECTION_ENTRY_SCHEMA_VERSION:
        return None
    digest = entry.get("object")
    if not is_object_hash(digest):
        return None
    try:
        value = json.loads(read_verified_object(str(digest)).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("loops"), list) else None


def write(key: str, value: dict) -> None:
    """Publish the cut and point the entry at it. Best effort."""
    data = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
    try:
        digest = put_object(data)
        write_entry(INDEX_KIND, key, {"schemaVersion": SECTION_ENTRY_SCHEMA_VERSION, "object": digest})
    except (OSError, StoreUnwritableError):
        pass


def normalize_item(item: Any) -> dict:
    """One ``sections`` request item, closed and canonical: a component and a plane."""
    if type(item) is not dict or set(item) != {"component", "normal", "offset"}:
        raise ValueError("a section item is exactly {component, normal, offset}")
    component = item["component"]
    if type(component) is not dict or set(component) - _COMPONENT_FIELDS:
        raise ValueError("a section item's component is a tree's geometry entry")
    if not is_object_hash(component.get("brep")) or not isinstance(component.get("codec"), str):
        raise ValueError("a section item's component names its codec and BREP object")
    if type(item["normal"]) not in (list, tuple) or len(item["normal"]) != 3 or any(
        type(value) not in (int, float) for value in item["normal"]
    ) or type(item["offset"]) not in (int, float):
        raise ValueError("a section item's plane is a normal of three numbers and an offset")
    unit, distance = canonical_plane(item["normal"], item["offset"])
    return {"component": dict(sorted(component.items())), "normal": list(unit), "offset": distance}


def produce(items: list[dict], *, keep_going: Callable[[], bool] | None = None) -> dict:
    """Cut every item the store lacks; ``{"keys": [...]}`` of the entries now present.

    Worker-only: decoding and cutting import the kernel. A component that fails
    to cut does not stop the others; :class:`SectionProductionError` names each
    once the rest are stored.
    """
    from cadgen._internal.brep_section import section_loops
    from cadgen._internal.component_package import decode_display_shape

    present, failed = [], []
    for item in items:
        key = section_key(item["component"], item["normal"], item["offset"])
        if read(key) is None:
            if keep_going is not None and not keep_going():
                break
            try:
                payload = read_verified_object(item["component"]["brep"])
                shape = decode_display_shape(item["component"], payload, native=True)
                loops = section_loops(getattr(shape, "wrapped", shape),
                                      normal=tuple(item["normal"]), offset=item["offset"])
            except Exception as error:  # noqa: BLE001 - the component's failure, reported by name
                failed.append(f"component {str(item['component'].get('contentHash'))[:16]}: "
                              f"{type(error).__name__}: {error}")
                continue
            write(key, {"schemaVersion": SECTION_ENTRY_SCHEMA_VERSION, **loops})
        present.append(key)
    if failed:
        raise SectionProductionError("; ".join(failed))
    return {"keys": present}
