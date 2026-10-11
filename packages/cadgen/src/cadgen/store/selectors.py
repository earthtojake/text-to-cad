"""The SELECTOR index: a component's selector table, derived beside its surface.

An input-addressed derivation like ``surface`` and ``mesh`` (``STORE.md`` §2):
the key is the surface's input plus this cadgen's table SCHEME, and the entry
points at the object holding the table's exact bytes (``_internal/selector_table``,
the one producer of every selector fact). The page reads it with the surface
and joins it to the mesh; the CLI reads it from a view. A key an older scheme
wrote is obsolete (``obsolete_key``): no reader asks for it again, and the
sweeper retires it (§8). Keys, probes and reads are stdlib-only, for a process
that only serves stored tables (the CAD Viewer's server).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from cadgen.store.index import entry_path, write_entry
from cadgen.store.objects import object_path, put_object

# What the table holds and how it is laid out: bumped with
# _internal/selector_table.SELECTOR_TABLE_SCHEMA_VERSION, and alone for a change
# in what the same columns hold (a chain or relevance rule, say).
SELECTOR_SCHEME = 1
SELECTOR_INDEX_SCHEMA = 1
INDEX_KIND = "selector"
MAX_INDEX_BYTES = 16 * 1024
_KEY = re.compile(rf"([0-9a-f]{{64}})-s{SELECTOR_SCHEME}")
_ANY_KEY = re.compile(r"([0-9a-f]{64})-s(\d+)")
_COUNT_FIELDS = ("faceCount", "edgeCount", "vertexCount")
_RECORD_FIELDS = {"schemaVersion", "object", "byteLength", "surfaceInput", "surfaceObject", "scheme", *_COUNT_FIELDS}


class SelectorConflictError(ValueError):
    """One deterministic input produced different table bytes."""


def _digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def selector_key(surface_input: str) -> str:
    if not _digest(surface_input):
        raise ValueError("surface input must be a full lowercase content digest")
    return f"{surface_input}-s{SELECTOR_SCHEME}"


def parse_key(key: Any) -> str | None:
    """A valid key's surface input; None for anything else."""
    match = _KEY.fullmatch(key) if isinstance(key, str) else None
    return match[1] if match else None


def obsolete_key(key: Any) -> bool:
    """Whether a selector entry's key is an older scheme's than this cadgen's: no
    reader asks for it again (STORE.md §8). A newer cadgen's is not."""
    match = _ANY_KEY.fullmatch(key) if isinstance(key, str) else None
    return match is not None and int(match[2]) < SELECTOR_SCHEME


def _record(key: str, surface_object: str, payload: bytes) -> dict:
    from cadgen._internal.selector_table import read_selector_table

    surface_input = parse_key(key)
    if surface_input is None or not _digest(surface_object):
        raise ValueError("invalid selector input or surface object")
    table = read_selector_table(payload)
    record = {
        "schemaVersion": SELECTOR_INDEX_SCHEMA, "object": hashlib.sha256(payload).hexdigest(),
        "byteLength": len(payload), "surfaceInput": surface_input, "surfaceObject": surface_object,
        "scheme": SELECTOR_SCHEME,
        **{name: table["stats"][name] for name in _COUNT_FIELDS},
    }
    if not _valid_record(key, record):
        raise ValueError("invalid selector index facts")
    return record


def _valid_record(key: str, record: Any) -> bool:
    try:
        if type(record) is not dict or set(record) != _RECORD_FIELDS:
            return False
        surface_input = parse_key(key)
        if (surface_input is None or record["schemaVersion"] != SELECTOR_INDEX_SCHEMA
                or record["scheme"] != SELECTOR_SCHEME or record["surfaceInput"] != surface_input
                or not _digest(record["object"]) or not _digest(record["surfaceObject"])):
            return False
        return all(type(record[name]) is int and record[name] >= 0 for name in (*_COUNT_FIELDS, "byteLength")) \
            and record["byteLength"] > 0
    except (TypeError, KeyError):
        return False


def probe(key: str) -> dict | None:
    """Bounded metadata only; no body, native import or source lookup."""
    if parse_key(key) is None:
        return None
    try:
        with entry_path(INDEX_KIND, key).open("rb") as stream:
            raw = stream.read(MAX_INDEX_BYTES + 1)
        if len(raw) > MAX_INDEX_BYTES:
            return None
        record = json.loads(raw.decode("utf-8"))
        if not _valid_record(key, record):
            return None
        if object_path(record["object"]).stat().st_size != record["byteLength"]:
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None


def read(key: str, *, expected_object: str | None = None) -> bytes | None:
    """The table's bytes, verified against the record and the content address."""
    record = probe(key)
    if record is None or (expected_object is not None and expected_object != record["object"]):
        return None
    try:
        with object_path(record["object"]).open("rb") as stream:
            if os.fstat(stream.fileno()).st_size != record["byteLength"]:
                return None
            payload = stream.read(record["byteLength"] + 1)
        if len(payload) != record["byteLength"] or hashlib.sha256(payload).hexdigest() != record["object"]:
            return None
        return payload
    except OSError:
        return None


def write(key: str, surface_object: str, payload: bytes) -> dict:
    """Publish a verified table before its input index; observed conflicts fail."""
    record = _record(key, surface_object, payload)
    prior = probe(key)
    if prior is not None and (prior["object"] != record["object"] or prior["surfaceObject"] != record["surfaceObject"]):
        if read(key, expected_object=prior["object"]) is not None:
            raise SelectorConflictError("the selector table producer returned different bytes for the same immutable input")
    digest = put_object(payload, repair=True)
    if digest != record["object"]:
        raise ValueError("selector table object address mismatch")
    write_entry(INDEX_KIND, key, record)
    return record
