"""Artifact-only surface derivation from captured immutable geometry inputs."""
from __future__ import annotations

import hashlib
import json
import struct
from typing import Any

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import put_object, read_verified_object

EXTRACTION_SCHEME = 19
SURF_FORMAT = 2
SURFACE_SCHEMA = 1


def validate_producer(value: Any) -> None:
    expected = {"scheme", "surfFormat", "build123d", "ocp", "cadqueryOcp"}
    if type(value) is not dict or set(value) not in (expected, expected | {"producerKey"}) or type(value.get("scheme")) is not int or type(value.get("surfFormat")) is not int or value.get("scheme") != EXTRACTION_SCHEME or value.get("surfFormat") != SURF_FORMAT:
        raise ValueError("unsupported surface producer")
    for field in ("build123d", "ocp", "cadqueryOcp"):
        text = value[field]
        if type(text) is not str or not text.strip() or "unknown" in text.lower():
            raise ValueError("surface producer requires known runtime identity")
    if "producerKey" in value and value["producerKey"] != producer_key(value):
        raise ValueError("surface producer key mismatch")


def producer_key(value: dict) -> str:
    from cadgen._internal.component_package import canonical_json_bytes as canonical_bytes
    definition = {key: item for key, item in value.items() if key != "producerKey"}
    validate_producer(definition)
    return hashlib.sha256(b"cadgen-surface-producer-v1\0" + canonical_bytes(definition)).hexdigest()


def producer_fields(value: dict) -> dict:
    validate_producer(value)
    return {key: item for key, item in value.items() if key != "producerKey"}


def producer_identity() -> dict:
    from cadgen._internal.op_memo import _runtime_versions
    build123d, ocp, distribution = _runtime_versions()
    identity = {"scheme": EXTRACTION_SCHEME, "surfFormat": SURF_FORMAT,
                "build123d": build123d, "ocp": ocp, "cadqueryOcp": distribution}
    validate_producer(identity)
    return identity


def surface_input(entry: dict, producer: dict) -> str:
    from cadgen._internal.component_package import canonical_json_bytes as canonical_bytes
    if entry.get("kind") == "eager-only":
        return hashlib.sha256(b"cadgen-pinned-surface-input-v1\0" + entry["eagerSurface"].encode()
                              + b"\0" + str(SURF_FORMAT).encode()).hexdigest()
    definition = {"kind": "native", "contentHash": entry["contentHash"],
                  "brepObject": entry["brep"], "codec": entry["codec"],
                  "faceColors": entry["faceColors"], "producerKey": producer_key(producer)}
    return hashlib.sha256(b"cadgen-surface-input-v1\0" + canonical_bytes(definition)).hexdigest()


def validate_surface_bytes(payload: bytes) -> dict:
    if len(payload) < 12 or payload[:4] != b"SURF":
        raise ValueError("invalid SURF container")
    version, size = struct.unpack_from("<II", payload, 4)
    if version != SURF_FORMAT or size > len(payload) - 12 or (len(payload) - 12 - size) % 4:
        raise ValueError("invalid SURF version/length")
    index = json.loads(payload[12:12 + size])
    if type(index) is not dict or index.get("version") != SURF_FORMAT:
        raise ValueError("invalid SURF index")
    for name in ("faces", "edges"):
        rows = index.get(name)
        if type(rows) is not list or any(type(row) is not dict for row in rows) or [row.get("ord") for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("invalid SURF ordinal table")
        if type(index.get("counts")) is not dict or index["counts"].get(name) != len(rows):
            raise ValueError("invalid SURF counts")
    return index


def _expected(entry: dict, producer: dict) -> dict:
    return {"schemaVersion": SURFACE_SCHEMA, "surfaceInput": surface_input(entry, producer),
            "component": entry["contentHash"], "brep": entry["brep"],
            "codec": entry["codec"], "faceColors": entry["faceColors"],
            "producer": None if entry["kind"] == "eager-only" else producer_fields(producer)}


def request_view(tree_hash: str, *, producer: dict | None = None) -> dict:
    """Owned request descriptor; never written into canonical geometry."""
    from cadgen.store.trees import capture_tree as capture
    descriptor, _ = capture(tree_hash, retain_payloads=False)
    return _view_from_geometry(tree_hash, descriptor, producer=producer)


def _view_id(tree_hash: str, producer: dict) -> str:
    key = producer_key(producer)
    return hashlib.sha256(
        b"cadgen-runtime-view-v1\0" + tree_hash.encode() + b"\0" + key.encode()
    ).hexdigest()


def _view_from_geometry(tree_hash: str, descriptor: dict, *, producer: dict | None = None) -> dict:
    """Consume an owned descriptor from this call's verified geometry capture.

    Internal metadata paths use this after verification to avoid rereading the
    same closure. Callers retaining canonical metadata pass a private copy.
    """
    selected = producer_identity() if producer is None else producer_fields(producer)
    key = producer_key(selected)
    descriptor["viewSchemaVersion"] = 1
    descriptor["tree"] = tree_hash
    descriptor["viewId"] = _view_id(tree_hash, selected)
    descriptor["surfaceProducer"] = {**selected, "producerKey": key}
    for entry in descriptor["components"].values():
        entry["surfaceInput"] = surface_input(entry, selected)
        entry["brepObject"] = entry.pop("brep")
    return descriptor


def lookup(entry: dict, producer: dict) -> dict | None:
    from cadgen._internal.component_package import canonical_json_bytes as canonical_bytes
    expected = _expected(entry, producer)
    actual = read_entry("surface", expected["surfaceInput"])
    if not actual or set(actual) != {*expected, "object"}:
        return None
    try:
        if any(canonical_bytes(actual[field]) != canonical_bytes(value) for field, value in expected.items()):
            return None
        validate_surface_bytes(read_verified_object(actual["object"]))
    except (OSError, ValueError, TypeError, KeyError, struct.error):
        return None
    return actual


def derive(tree_hash: str, cids: list[str] | None = None, *, force: bool = False,
           expected_objects: dict[str, str] | None = None, producer: dict | None = None) -> dict:
    from cadgen.store.trees import capture_tree as capture
    from cadgen._internal.component_package import decode_geometry_component, canonical_json_bytes as canonical_bytes
    from cadgen._internal.surface_extract import extract_surface_component

    # Surface work still admits only a complete verified geometry graph. It
    # does not need to retain every BREP in that graph when the request names a
    # bounded CID subset: metadata capture verifies the whole closure, then an
    # extraction reads the exact selected CAS payload immediately before decode.
    # This keeps capture_tree()'s native-owner contract unchanged for consumers
    # that actually materialize the complete graph.
    descriptor, _ = capture(tree_hash, retain_payloads=False)
    producer = producer_identity() if producer is None else producer_fields(producer)
    if producer != producer_identity():
        raise ValueError("worker cannot implement the request's pinned surface producer")
    requested = list(descriptor["components"]) if cids is None else list(dict.fromkeys(cids))
    if any(cid not in descriptor["components"] for cid in requested):
        raise ValueError("surface request names an unpinned component")
    result = {}
    for cid in requested:
        entry = descriptor["components"][cid]
        expected = _expected(entry, producer)
        prior = lookup(entry, producer)
        expected_object = (expected_objects or {}).get(expected["surfaceInput"])
        if expected_object is None and force and prior is not None:
            expected_object = prior["object"]
        if entry["kind"] == "eager-only":
            payload = read_verified_object(entry["eagerSurface"])
            validate_surface_bytes(payload)
            actual = {**expected, "object": entry["eagerSurface"]}
        else:
            actual = None if force else prior
            if actual is None:
                shape = decode_geometry_component(entry, read_verified_object(entry["brep"]))
                payload = extract_surface_component(shape.wrapped, face_colors=shape.cad_face_ordinal_colors)
                validate_surface_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                if expected_object is not None and digest != expected_object:
                    raise ValueError("surface producer conflict for the pinned input")
                actual = {**expected, "object": put_object(payload, repair=True)}
        if expected_object is not None and actual["object"] != expected_object:
            raise ValueError("surface producer conflict for the pinned input")
        # The complete verified object is durable first; failure earlier cannot
        # create a readiness marker. Concurrent writers derive identical bytes.
        write_entry("surface", expected["surfaceInput"], actual)
        result[cid] = actual
    return result


def validate_surface_record(value: Any, *, surface_input_key: str | None = None) -> None:
    """Verify a surface index independently of geometry-object availability.

    The index owns its surface; its geometry fields describe the immutable
    derivation input but do not add GC ownership of a BREP or geometry tree.
    """
    from cadgen._internal.component_package import _normalized_face_colors, canonical_json_bytes
    from cadgen.store.objects import is_object_hash

    fields = {"schemaVersion", "surfaceInput", "component", "brep", "codec", "faceColors", "producer", "object"}
    if type(value) is not dict or set(value) != fields or value["schemaVersion"] != SURFACE_SCHEMA:
        raise ValueError("invalid surface index")
    if any(not is_object_hash(value[field]) for field in ("surfaceInput", "component", "brep", "object")):
        raise ValueError("invalid surface index identity")
    from cadgen._internal.component_package import GEOMETRY_CODECS
    if value["codec"] not in GEOMETRY_CODECS:
        raise ValueError("invalid surface geometry codec")
    colors = _normalized_face_colors(value["faceColors"])
    if canonical_json_bytes(colors) != canonical_json_bytes(value["faceColors"]):
        raise ValueError("invalid surface appearance recipe")
    entry = {"kind": "native", "contentHash": value["component"], "brep": value["brep"],
             "codec": value["codec"], "faceColors": value["faceColors"]}
    if value["producer"] is None:
        entry.update(kind="eager-only", eagerSurface=value["object"])
    else:
        validate_producer(value["producer"])
    expected = surface_input(entry, value["producer"])
    if value["surfaceInput"] != expected or (surface_input_key is not None and expected != surface_input_key):
        raise ValueError("surface index input mismatch")
    validate_surface_bytes(read_verified_object(value["object"]))
