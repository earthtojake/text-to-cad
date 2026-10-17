"""A part's display data: ONE index record per part, naming its two objects -- the display
mesh (a GLB body, ``cadgen.store.meshes``) and the selector table
(``cadgen._internal.selector_table``) -- derived from captured immutable geometry inputs,
and read by every view of it.

A part is a component under one producer, the kernel that derives it. Its key,
``index/part/<digest>-v<PART_VERSION>``, carries no tolerance: the digest hashes what
made the component -- its **construction key** (``_internal/kernel_memo``, README law 20),
or, for geometry no construction of a run made, its ``contentHash`` -- with the lineage
object that names its elements, its intrinsic face colours and the producer. So a
component a run remakes with the same construction is the same part however its bytes
fall, and the same body under another name is another part: a part's selector table
carries its elements' names. The version is bumped by any change to the extractor, the
selector table, the mesher, the GLB payload or the geometric token scheme, or in how the
digest is hashed.
The record is ``{"glb": {...}, "selectors": {...}}``: each object's address and byte
length and what a reader sizes it by without opening it -- the mesh's decoded-bytes
estimate and counts (and ``unmeshedFaceCount`` when a face could not be meshed), the
table's counts. One probe answers whether a part's display data is stored.

Derivation extracts the component's topology facts in memory (an eager-only component's
are the object its tree pins), meshes the component from them and its face colours, builds
the selector table from the facts, the component's element names -- its lineage's, and the
geometric token of each element no lineage names (``_internal/geometric_tokens``) -- and the
mesh's boxes of its faces and edges, writes the two objects and then the record, so a record
always names complete objects. Nothing stores the facts. A mesh export at another tolerance
extracts the facts of the bytes it decodes, the same way, meshes from them and stores
nothing (``mesh_at``).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
from functools import lru_cache
from typing import Any, Callable

from cadgen.store.index import entry_path, versioned_key, write_entry
from cadgen.store.objects import is_object_hash, object_path, put_object, read_verified_object

# 1: one record per part names its display GLB and its selector table (the surface,
# selector and mesh kinds before it are retired).
# 2: the producer key's tag and the selector table's edge-line algorithm name a producer
# and edge lines: every part has a new key, and its table new bytes.
# 3: the mesher measures each cylinder, cone, sphere and torus against its surface and
# meshes a part again where one strays: a part whose round OCCT gridded off it has a new mesh.
# 4 and 5: two tessellators of cadgen's own that never shipped (a grid over each face's
# parameters, in Python and then as a native library), retired before a release: a part at
# either key is swept like any obsolete one.
# 6: a part keyed by its component's geometry fingerprint, its table naming every element by a
# geometric token. 7: a part is keyed by its component's construction key (or its content, for
# geometry no construction made) and lineage, and its selector table names every element by its
# lineage, or its geometric token where it has none (README law 20). 8: the selector table carries no
# solid volume. 9: its face and edge boxes are the display mesh's. 10: it carries no face area,
# centroid, relevance or flags (a view measures a face where it shows it, ``measure_face``), and
# the mesher decides which faces must have triangles from its own first pass.
PART_VERSION = 10
INDEX_KIND = "part"
MAX_INDEX_BYTES = 16 * 1024
_KEY = re.compile(rf"[0-9a-f]{{64}}-v{PART_VERSION}")
# Any version's key, this cadgen's or another's (``obsolete_key``).
_ANY_KEY = re.compile(r"[0-9a-f]{64}-v(\d+)")
ROLES = ("glb", "selectors")
_GLB_FIELDS = {"object", "byteLength", "decodedBytes", "vertexCount", "indexCount", "faceCount", "edgeCount",
               "edgePointCount"}
_UNMESHED_COUNT = "unmeshedFaceCount"
_SELECTOR_FIELDS = {"object", "byteLength", "faceCount", "edgeCount", "vertexCount"}
_PRODUCER_FIELDS = {"build123d", "ocp", "cadqueryOcp"}


class ProducerUnavailable(ValueError):
    """This runtime cannot implement the producer the request pins.

    A caller that holds a replacement producer recovers from this and only
    this; every other failure is a failure. Routing it by a substring of the
    message, retyped at each catch site, made that distinction a typo away
    from wrong, so the refusal has a type and one declared marker text.
    """

    MARKER = "worker cannot implement the request's pinned producer"

    def __init__(self, message: str = MARKER) -> None:
        super().__init__(message)


def producer_unavailable(error: object) -> bool:
    """Whether ``error`` is that refusal, however it reached the caller.

    In-process the type answers. Derivation also runs in a POOLED WORKER, and
    a worker's refusal arrives as an ArtifactJobError carrying its text, so the
    marker is matched too -- one constant, declared beside the raise.
    """
    return isinstance(error, ProducerUnavailable) or ProducerUnavailable.MARKER in str(error)


def validate_producer(value: Any) -> None:
    if type(value) is not dict or set(value) not in (_PRODUCER_FIELDS, _PRODUCER_FIELDS | {"producerKey"}):
        raise ValueError("unsupported producer")
    for field in _PRODUCER_FIELDS:
        text = value[field]
        if type(text) is not str or not text.strip() or "unknown" in text.lower():
            raise ValueError("producer requires known runtime identity")
    if "producerKey" in value and value["producerKey"] != producer_key(value):
        raise ValueError("producer key mismatch")


def producer_key(value: dict) -> str:
    from cadgen._internal.component_package import canonical_json_bytes as canonical_bytes
    definition = {key: item for key, item in value.items() if key != "producerKey"}
    validate_producer(definition)
    # The tag's bytes are in every producer key, part key and view id: a new spelling
    # re-keys every stored part, and moves PART_VERSION with it so the parts at the
    # keys before it are obsolete (``obsolete_key``) and the sweeper retires them.
    return hashlib.sha256(b"cadgen-producer-v1\0" + canonical_bytes(definition)).hexdigest()


def producer_fields(value: dict) -> dict:
    validate_producer(value)
    return {key: item for key, item in value.items() if key != "producerKey"}


@lru_cache(maxsize=1)
def kernel_versions() -> tuple[str, str, str]:
    """The installed build123d, the loaded OCP and cadquery-ocp-novtk versions:
    who produced a derived fact (a part's display data, a measured box).

    OCP.__version__ is exported by the native extension, not inferred from
    build123d. build123d's is its installed metadata: importing build123d to
    read it was most of the start of a worker that derives and meshes, which
    never imports build123d otherwise (``component_package.NativeShape``). An
    unknown version is a ValueError: a derived fact must never share an
    identity with an unrelated kernel build.
    """
    from importlib.metadata import PackageNotFoundError, version

    import OCP

    try:
        build123d, distribution = version("build123d"), version("cadquery-ocp-novtk")
    except PackageNotFoundError as error:
        raise ValueError("a derived fact needs the build123d and cadquery-ocp-novtk distributions") from error
    versions = (build123d, getattr(OCP, "__version__", None), distribution)
    if any(not isinstance(value, str) or not value.strip() or "unknown" in value.lower() for value in versions):
        raise ValueError("a derived fact needs known build123d and OCP versions")
    return versions


def producer_identity() -> dict:
    build123d, ocp, distribution = kernel_versions()
    identity = {"build123d": build123d, "ocp": ocp, "cadqueryOcp": distribution}
    validate_producer(identity)
    return identity


def part_key(entry: dict, producer: dict) -> str:
    """The key of ``entry``'s part (a tree's component entry) under ``producer``."""
    return _part_key(entry, producer_key(producer))


def _part_key(entry: dict, producer: str) -> str:
    """``part_key`` under the producer whose key is ``producer``: what made the component
    (its construction key, else its content), its lineage, its face colours."""
    from cadgen._internal.component_package import _normalized_face_colors, canonical_json_bytes

    made = f"construction:{entry['construction']}" if entry.get("construction") else f"content:{entry['contentHash']}"
    colors = {str(ordinal): list(color) for ordinal, color in _normalized_face_colors(entry.get("faceColors")).items()}
    digest = hashlib.sha256(b"cadgen-part\0" + made.encode() + b"\0" + str(entry.get("lineage") or "").encode()
                            + b"\0" + canonical_json_bytes(colors) + b"\0" + producer.encode()).hexdigest()
    return versioned_key(digest, PART_VERSION)


def valid_key(key: Any) -> bool:
    return isinstance(key, str) and _KEY.fullmatch(key) is not None


def obsolete_key(key: Any) -> bool:
    """Whether a part entry's key is an older version's than this cadgen's: no reader asks
    for it again (STORE.md §8). A newer cadgen's is not."""
    match = _ANY_KEY.fullmatch(key) if isinstance(key, str) else None
    return match is not None and int(match[1]) < PART_VERSION


def _view_id(tree_hash: str, producer: dict) -> str:
    key = producer_key(producer)
    return hashlib.sha256(
        b"cadgen-runtime-view-v1\0" + tree_hash.encode() + b"\0" + key.encode()
    ).hexdigest()


def view_from_geometry(tree_hash: str, descriptor: dict, *, producer: dict | None = None) -> dict:
    """Consume an owned descriptor from this call's verified geometry capture: each
    component gains its part key (``part``), and the view its id and producer.

    Internal metadata paths use this after verification to avoid rereading the
    same closure. Callers retaining canonical metadata pass a private copy.
    """
    selected = producer_identity() if producer is None else producer_fields(producer)
    key = producer_key(selected)
    descriptor["viewSchemaVersion"] = 1
    descriptor["tree"] = tree_hash
    descriptor["viewId"] = _view_id(tree_hash, selected)
    descriptor["producer"] = {**selected, "producerKey": key}
    for entry in descriptor["components"].values():
        entry["part"] = _part_key(entry, key)
        entry["brepObject"] = entry.pop("brep")
    return descriptor


def geometry_entry(view_entry: dict) -> dict:
    """The canonical tree entry behind a view's component (``view_from_geometry``)."""
    entry = {"kind": view_entry["kind"], "codec": view_entry["codec"], "brep": view_entry["brepObject"],
             "faceColors": view_entry["faceColors"], "contentHash": view_entry["contentHash"]}
    for field in ("topology", "construction", "lineage"):
        if view_entry.get(field):
            entry[field] = view_entry[field]
    return entry


def _counts(value: Any, fields: set[str]) -> bool:
    return all(type(value[name]) is int and value[name] >= 0 for name in fields - {"object"})


def _valid_record(record: Any) -> bool:
    """A part record's shape: ``{"glb": {...}, "selectors": {...}}`` (module docstring)."""
    from cadgen.store.meshes import decoded_bytes

    try:
        if type(record) is not dict or set(record) != set(ROLES):
            return False
        glb, table = record["glb"], record["selectors"]
        if (type(glb) is not dict or set(glb) not in (_GLB_FIELDS, _GLB_FIELDS | {_UNMESHED_COUNT})
                or not is_object_hash(glb["object"]) or not _counts(glb, set(glb))):
            return False
        if _UNMESHED_COUNT in glb and not 0 < glb[_UNMESHED_COUNT] <= glb["faceCount"]:
            return False
        if (glb["byteLength"] < 20 or glb["byteLength"] % 4 or glb["decodedBytes"] != decoded_bytes(glb)
                or glb["edgePointCount"] < 2 * glb["edgeCount"]
                or (glb["edgeCount"] == 0) != (glb["edgePointCount"] == 0)):
            return False
        return (type(table) is dict and set(table) == _SELECTOR_FIELDS and is_object_hash(table["object"])
                and _counts(table, _SELECTOR_FIELDS) and table["byteLength"] > 0)
    except (TypeError, KeyError):
        return False


def probe(key: str) -> dict | None:
    """The part's record, when it is valid and both objects it names are stored at their
    sizes; None otherwise. Bounded metadata only: no body, no kernel import."""
    if not valid_key(key):
        return None
    try:
        with entry_path(INDEX_KIND, key).open("rb") as stream:
            raw = stream.read(MAX_INDEX_BYTES + 1)
        if len(raw) > MAX_INDEX_BYTES:
            return None
        record = json.loads(raw.decode("utf-8"))
        if not _valid_record(record):
            return None
        if any(object_path(record[role]["object"]).stat().st_size != record[role]["byteLength"] for role in ROLES):
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None


def read(key: str, role: str, *, expected_object: str | None = None, max_bytes: int | None = None) -> bytes | None:
    """One of the part's objects (``role``: ``glb`` or ``selectors``), at most ``max_bytes``,
    bound to its record: a body's framing and JSON name this part, a table's bytes hash to
    its address. None for anything else."""
    from cadgen.store.meshes import MAX_SAFE_INTEGER, body_facts

    record = probe(key)
    facts = record[role] if record is not None and role in ROLES else None
    if facts is None or (expected_object is not None and expected_object != facts["object"]):
        return None
    limit = facts["byteLength"] if max_bytes is None else max_bytes
    if type(limit) is not int or not 0 < limit <= MAX_SAFE_INTEGER or facts["byteLength"] > limit:
        return None
    try:
        with object_path(facts["object"]).open("rb") as stream:
            if os.fstat(stream.fileno()).st_size != facts["byteLength"]:
                return None
            payload = stream.read(facts["byteLength"] + 1)
        if len(payload) != facts["byteLength"]:
            return None
        if role == "glb":
            # The record's content address names the body ``_write`` validated whole; a read
            # checks the framing, the canonical JSON and the part again. The tables are for
            # the decoders that read them (``meshes.decode_payload``, tessellationCache.js).
            body = body_facts(payload)
            if body.pop("part") != key or body != {name: value for name, value in facts.items() if name != "object"}:
                return None
        elif hashlib.sha256(payload).hexdigest() != facts["object"]:
            return None
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        return None


def stored_unmeshed_faces(key: str) -> list[int]:
    """The faces the part's stored mesh leaves undrawn (``unmeshedFaces``): empty when the store
    lacks the part or its record counts none, so a reader asks every part it drew for the price of
    a probe."""
    from cadgen.store.meshes import unmeshed_faces

    record = probe(key)
    if record is None or not record["glb"].get(_UNMESHED_COUNT):
        return []
    payload = read(key, "glb")
    return unmeshed_faces(payload) if payload is not None else []


def unmeshed_face_names(key: str, ordinals: list[int]) -> list[str]:
    """The faces ``ordinals`` of the part's table as a reader names them: each face's
    name (``f:…``, the ref a person pastes), read off the part's stored selector table;
    ``face <ordinal>`` for a face the table does not hold or when the table does not read."""
    from cadgen._internal.selector_table import read_selector_table

    names: dict[int, str] = {}
    payload = read(key, "selectors") if valid_key(key) else None
    if payload is not None:
        try:
            table = read_selector_table(payload)
        except ValueError:
            table = None
        if table is not None:
            columns = table["tables"]["faceColumns"]
            name_at, ordinal_at = columns.index("name"), columns.index("ordinal")
            names = {int(row[ordinal_at]): str(row[name_at]) for row in table["faces"]}
    return [names.get(int(ordinal), f"face {ordinal}") for ordinal in ordinals]


def _write(key: str, glb: bytes, table: bytes) -> dict:
    """Store the part's two objects, then its record: a record names complete objects."""
    from cadgen._internal.selector_table import read_selector_table
    from cadgen.store.meshes import body_facts

    facts = body_facts(glb)
    if facts.pop("part") != key:
        raise ValueError("the part's mesh names another part")
    stats = read_selector_table(table)["stats"]
    record = {
        "glb": {"object": put_object(glb, repair=True), **facts},
        "selectors": {"object": put_object(table, repair=True), "byteLength": len(table),
                      **{name: stats[name] for name in ("faceCount", "edgeCount", "vertexCount")}},
    }
    if not _valid_record(record):
        raise ValueError("invalid part record")
    # A hit is a read and writes nothing (STORE.md §8); the caller probed first.
    write_entry(INDEX_KIND, key, record)
    return record


@contextlib.contextmanager
def _meshing():
    """Whatever fails inside, as the ``MeshProductionError`` that names it (its type
    and message): one component's failure, which its caller reports once the rest
    of the request is stored. An interrupt is not one."""
    from cadgen._internal.tessellate import MeshProductionError

    try:
        yield
    except Exception as error:  # noqa: BLE001 - the error is the component's, reported by name
        raise MeshProductionError(f"{type(error).__name__}: {error}") from error


def _decoded(entry: dict) -> tuple[Any, dict]:
    """A decode of the component and its face colours by ordinal."""
    from cadgen._internal.component_package import decode_display_shape, effective_face_colors

    shape = decode_display_shape(entry, read_verified_object(entry["brep"]), native=True)
    topods = getattr(shape, "wrapped", shape)
    return topods, effective_face_colors(topods, entry["faceColors"])


def _topology(entry: dict, topods: Any) -> dict:
    """The component's topology facts: an eager-only component's are the object its tree
    pins, any other's are extracted here, in memory."""
    if entry["kind"] == "eager-only":
        from cadgen._internal.topology_facts import read_topology_facts

        return read_topology_facts(read_verified_object(entry["topology"]))
    from cadgen._internal.topology_extract import extract_topology_facts

    return extract_topology_facts(topods)


def element_names(entry: dict, topods: Any) -> dict[str, list[str]]:
    """Every face's, edge's and vertex's name in a decode of the component ``entry``
    describes, by ordinal: its lineage's (the object the entry names, read verified),
    and the geometric token of each element no lineage names (``geometric_tokens``,
    measured where one is needed and remembered by the component's bytes:
    ``geometric_tokens.component_tokens``)."""
    from cadgen._internal import geometric_tokens
    from cadgen._internal.component_package import read_lineage

    lineage = read_lineage(read_verified_object(entry["lineage"])) if entry.get("lineage") else None
    return geometric_tokens.element_names(lineage, topods, component=(entry["codec"], entry["brep"]))


def element_tokens(entry: dict) -> dict[str, list[str]]:
    """The geometric token of every face, edge and vertex of the component a tree's
    ``entry`` describes, by ordinal: what a ref by geometry is matched against
    (``cadgen.refs``), measured on the decode its selector table names
    (:func:`element_names`) once per body and remembered by its bytes."""
    from cadgen._internal.geometric_tokens import component_tokens

    topods, _ = _decoded(entry)
    return component_tokens(topods, (entry["codec"], entry["brep"]))


def measure_face(tree_hash: str, cid: str, face: int) -> dict:
    """Face ``face`` (its ordinal) of component ``cid`` of ``tree_hash`` (links expanded),
    measured exactly on the component's stored BREP: ``{"area": a, "center": [x, y, z]}``, its
    area and centroid by GProps, in the component's own frame. What a view shows a face's area
    by -- its Reference panel, its measure tool -- and what a mate's axis takes as its origin
    where nothing else gives one (``_internal/kinematics_resolve``): measured where asked -- a
    view's by one build-pool job (``kind: measure``), an axis's in the build resolving it --
    never with the part's display data, and remembered in ``index/bounds`` by the component's
    BREP and the face (``bounds.cached_face_measure``), so each face is measured once."""
    from cadgen.store.bounds import cached_face_measure

    descriptor, _producer = _captured(tree_hash, None)
    entry = descriptor["components"].get(cid)
    if entry is None:
        raise ValueError("measure request names an unpinned component")
    return cached_face_measure(entry["codec"], entry["brep"], face, lambda: _face_measure(entry, face))


def _face_measure(entry: dict, face: int) -> dict:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopoDS import TopoDS

    topods, _colors = _decoded(entry)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
    if not 1 <= face <= faces.Extent():
        raise ValueError(f"the component has {faces.Extent()} faces, not a face {face}")
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(TopoDS.Face_s(faces.FindKey(face)), props)
    center = props.CentreOfMass()
    return {"area": float(props.Mass()), "center": [float(center.X()), float(center.Y()), float(center.Z())]}


def remembered_face_measure(entry: dict, face: int) -> dict | None:
    """:func:`measure_face`'s answer for a tree's component ``entry`` when the store holds it,
    read without the kernel; None when it has yet to be measured."""
    from cadgen.store.bounds import remembered_face_measure as remembered

    return remembered(entry["codec"], entry["brep"], face)


def _derive(entry: dict, key: str, keep_going: Callable[[], bool] | None = None) -> dict | None:
    """Store the part's display data when the store lacks it and return its record; None when
    ``keep_going`` said stop first. Any failure is the ``MeshProductionError`` naming it."""
    prior = probe(key)
    if prior is not None:
        return prior
    if keep_going is not None and not keep_going():
        return None
    from cadgen._internal.selector_table import build_selector_table, selector_table_bytes
    from cadgen._internal.tessellate import mesh_component
    from cadgen.tessellation_policy import DISPLAY_TESSELLATION

    with _meshing():
        topods, colors = _decoded(entry)
        facts = _topology(entry, topods)
        meshed = mesh_component(topods, facts, colors, part=key, chord=DISPLAY_TESSELLATION["chordTolerance"],
                                angle=DISPLAY_TESSELLATION["angleTolerance"])
        table = build_selector_table(topods, facts, element_names(entry, topods), boxes=meshed.boxes)
        return _write(key, meshed.body, selector_table_bytes(table))


def mesh_at(entry: dict, key: str, chord: float, angle: float) -> bytes:
    """The GLB body of the part ``key`` names, at ``chord``/``angle``, meshed in this process
    and stored nowhere: a mesh export at a tolerance other than the display one
    (``_internal/mesh_export.py``), whose file is the output. ``entry`` is the component's
    tree entry. The mesher reads what the display mesh's read -- the component's topology
    facts and its face colours -- with the facts extracted here for the bytes it decodes, as
    a derivation extracts them, so the export is the same whether or not the store holds the
    part (law 5)."""
    from cadgen._internal.tessellate import mesh_component

    with _meshing():
        topods, colors = _decoded(entry)
        return mesh_component(topods, _topology(entry, topods), colors, part=key, chord=chord, angle=angle).body


def _captured(tree_hash: str, producer: dict | None) -> tuple[dict, dict]:
    """The tree's verified descriptor, and the producer named (this runtime's when None)."""
    from cadgen.store.trees import capture_tree as capture

    # Display work admits only a complete verified geometry graph, but retains none
    # of its BREPs: each derivation reads the exact CAS payload it decodes.
    descriptor, _ = capture(tree_hash, retain_payloads=False)
    return descriptor, producer_identity() if producer is None else producer_fields(producer)


def derive(tree_hash: str, cids: list[str] | None = None, *, producer: dict | None = None,
           keep_going: Callable[[], bool] | None = None) -> dict:
    """Derive in this process the display data of ``cids`` (every component when None) the
    store lacks -- the job a view submits for the parts it found missing -- and return
    their records, ``{cid: record}``.

    ``keep_going``, when given, is asked before each part: False stops there, and the
    result holds the parts done so far (a daemon worker asks whether anyone still wants
    its job, ``daemon/worker.py``). A part that fails, however it fails, does not stop the
    others: they are stored, then ``MeshProductionError`` names each failure (the
    component, and the error's type and message).
    """
    from cadgen._internal.tessellate import MeshProductionError

    descriptor, producer = _captured(tree_hash, producer)
    components = descriptor["components"]
    if producer != producer_identity():
        raise ProducerUnavailable()
    requested = list(components) if cids is None else list(dict.fromkeys(cids))
    if any(cid not in components for cid in requested):
        raise ValueError("display request names an unpinned component")
    key = producer_key(producer)
    result, unmeshed = {}, []
    for cid in requested:
        try:
            record = _derive(components[cid], _part_key(components[cid], key), keep_going)
        except MeshProductionError as error:
            # One part's failure leaves the rest of the request to be done: they are
            # stored before the failure is reported, so a retry finds them.
            unmeshed.append(f"component {cid}: {error}")
            continue
        if record is None:
            break
        result[cid] = record
    if unmeshed:
        raise MeshProductionError("; ".join(unmeshed))
    return result


def all_stored(tree_hash: str, producer: dict) -> bool:
    """Whether the store holds the display data of every part of ``tree_hash`` under
    ``producer``: one probe a part, no kernel import."""
    descriptor, selected = _captured(tree_hash, producer)
    key = producer_key(selected)
    return all(probe(_part_key(entry, key)) is not None for entry in descriptor["components"].values())


def part_keys(tree_hash: str, *, producer: dict | None = None) -> tuple[dict[str, str], dict]:
    """The part key of every component of ``tree_hash`` (links expanded) under ``producer``
    (this runtime's when None), ``{cid: key}``, with the producer selected: what a build
    announces for its preview revision (STORE.md §9b). No kernel import."""
    descriptor, selected = _captured(tree_hash, producer)
    key = producer_key(selected)
    return {cid: _part_key(entry, key) for cid, entry in descriptor["components"].items()}, selected


def stored_keys(keys: dict[str, str]) -> dict[str, str]:
    """The entries of ``keys`` whose part the store holds: one probe each, no kernel."""
    return {cid: key for cid, key in keys.items() if probe(key) is not None}


# A batch of parts this large or larger, in BREP bytes, goes to the daemon's pool as more than
# one job, so free slots derive it together: about one job for each such share, at most one for
# each slot but the one the caller holds. A small batch -- an edit's, a view's -- is one job.
# With no daemon there is no pool of slots, only this process, and a batch is one job on one
# thread of it: the kernel holds the interpreter lock through each mesh (OCCT meshes the part's
# faces on threads of its own meanwhile), so a second thread would take turns with the first,
# never run beside it, and every other thread of the build would wait on both.
_BATCH_BYTES = 512 * 1024


def request_display(tree_hash: str, *, producer: dict | None = None,
                    cids: list[str] | None = None) -> "DisplayJob | None":
    """Have the build pool derive the display data of every part of ``tree_hash`` the store
    lacks -- jobs (``kind: display``, ``daemon/artifacts.py``) that run while the caller
    goes on: on daemon workers, one, or for a large batch one per share of it
    (``_BATCH_BYTES``), the shares balanced by BREP size; with no daemon, one, on a thread
    of this process -- and return them as one
    :class:`DisplayJob`; None when the store holds them all. A build submits it the moment
    its result exists and waits for it before it reports done
    (``_internal/generation.py``), so a view of what it built only reads.

    Which parts are missing is asked of the store alone (``probe``): a tree whose display
    data is all stored starts no job. ``producer`` is the one a view of the tree selects
    (its document's), this runtime's when None. ``cids`` restricts the work to those
    components (a parent's own: a child's build derives the child's), every component
    when None."""
    descriptor, producer = _captured(tree_hash, producer)
    components = descriptor["components"]
    key = producer_key(producer)
    wanted = list(components) if cids is None else list(dict.fromkeys(cids))
    if any(cid not in components for cid in wanted):
        raise ValueError("display request names an unpinned component")
    missing = {cid: _part_key(components[cid], key) for cid in wanted}
    missing = {cid: part for cid, part in missing.items() if probe(part) is None}
    if not missing:
        return None
    from cadgen.daemon.artifacts import submit_artifact
    from cadgen.store.meshes import placements

    jobs: list[tuple[Any, dict[str, str]]] = []
    try:
        for batch in _batches(missing, components):
            future = submit_artifact({"kind": "display", "tree": tree_hash, "cids": batch, "producer": producer})
            jobs.append((future, {cid: missing[cid] for cid in batch}))
    except BaseException:
        for future, _keys in jobs:
            future.detach()
        raise
    return DisplayJob(jobs, missing, placements(descriptor.get("occurrences")))


def _batches(missing: dict[str, str], components: dict) -> list[list[str]]:
    """``missing``'s components as the batches the pool derives: one, or one per
    ``_BATCH_BYTES`` of their BREP up to a slot each but the caller's -- the daemon's slots;
    with no daemon, one thread -- each component to the batch with the fewest bytes so far,
    largest first."""
    import math

    from cadgen.daemon.broker import job_limit
    from cadgen.daemon.executors import use_daemon

    sizes = {}
    for cid in missing:
        try:
            sizes[cid] = object_path(components[cid]["brep"]).stat().st_size
        except OSError:
            sizes[cid] = 0
    slots = job_limit() - 1 if use_daemon() else 1
    count = max(1, min(slots, len(missing), math.ceil(sum(sizes.values()) / _BATCH_BYTES)))
    batches: list[list[str]] = [[] for _ in range(count)]
    loads = [0] * count
    for cid in sorted(missing, key=lambda cid: (-sizes[cid], cid)):
        lightest = loads.index(min(loads))
        batches[lightest].append(cid)
        loads[lightest] += max(sizes[cid], 1)
    return [batch for batch in batches if batch]


class DisplayJob:
    """The build pool's work deriving the display data of the parts a tree's store lacked
    (:func:`request_display`), one job or several, waited for as one: ``keys``,
    ``{cid: part key}``, are those parts."""

    def __init__(self, jobs: list[tuple[Any, dict[str, str]]], keys: dict[str, str],
                 placed: dict[str, list[tuple[str, str]]]) -> None:
        self._jobs = jobs
        self.keys = keys
        self._placed = placed
        self._heard = threading.Event()
        self._heard.set()

    def when_done(self, callback: Callable[["DisplayJob"], None]) -> None:
        """Call ``callback(self)`` once every job has finished, however it finished: on the
        thread that finished the last, or here when they all have. :meth:`wait` and
        :meth:`settle` return once it has returned."""
        self._heard.clear()
        remaining = [len(self._jobs)]
        counting = threading.Lock()

        def done(_future: Any) -> None:
            with counting:
                remaining[0] -= 1
                last = remaining[0] == 0
            if not last:
                return
            try:
                callback(self)
            finally:
                self._heard.set()

        for future, _keys in self._jobs:
            future.add_done_callback(done)

    def settle(self) -> None:
        """Wait for every job to finish, however it finishes (:meth:`wait` says how)."""
        for future, _keys in self._jobs:
            with contextlib.suppress(Exception):
                future.result()
        self._heard.wait()

    def wait(self) -> list[str]:
        """Wait for the jobs -- yielding this thread's CPU lease to them meanwhile -- and
        return a line for each part they could not derive, naming the occurrences that place
        it and why (``#o:3f2a9c1d7e5b peg could not be meshed (MeshProductionError:
        ValueError: boom)``); the rest of the parts are stored. A failure that leaves no
        part missing for a reason of its own is raised."""
        from cadgen.store.meshes import failed_part

        lines: list[str] = []
        try:
            for future, keys in self._jobs:
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - a part's failure is a line; any other is raised
                    failed = failed_parts(keys, error)
                    if not failed:
                        raise
                    lines.extend(failed_part(self._placed.get(cid) or [], reason, component=cid)
                                 for cid, reason in failed.items())
        finally:
            self._heard.wait()
        return lines

    def abandon(self) -> None:
        """Leave the jobs: each one's worker stops once no one else wants it."""
        for future, _keys in self._jobs:
            future.detach()


# How a display job's failure names each part it could not derive, however the job ran
# (raised where it was submitted, or the text of a pooled worker's refusal):
# ``component <cid>: <that part's MeshProductionError>``, the parts joined by "; "
# (:func:`derive`).
_FAILED_COMPONENT = re.compile(r"component ([0-9a-f]{16}): ")
# What a pooled job's failure wraps its last line in (``daemon/artifacts.py``, ``daemon/client.py``).
_JOB_FAILURE_PREFIXES = ("artifact request failed: ", "artifact worker failed or returned no result: ",
                         "cadgen._internal.tessellate.MeshProductionError: ", "MeshProductionError: ")


def failed_parts(keys: dict[str, str], error: Exception) -> dict[str, str]:
    """The parts of ``keys`` (``{cid: part key}``) a display job that failed with ``error``
    left missing, each with its reason -- the part's own ``MeshProductionError``
    (``MeshProductionError: ValueError: boom``), or, where the failure names no part (a
    worker that died, a service that did not answer), the failure's last line. Never a
    component id or a worker's traceback. ``{}`` for any other failure, or when every part
    is stored after all."""
    from cadgen.daemon.artifacts import ArtifactJobError

    if not isinstance(error, ArtifactJobError) and type(error).__name__ != "MeshProductionError":
        return {}
    from cadgen._internal.tessellate import MeshProductionError

    failed = [cid for cid, key in keys.items() if probe(key) is None]
    if not failed:
        return {}
    text = str(error)
    own: dict[str, str] = {}
    for line in text.splitlines():
        named = list(_FAILED_COMPONENT.finditer(line))
        for index, match in enumerate(named):
            end = named[index + 1].start() if index + 1 < len(named) else len(line)
            own[match.group(1)] = f"{MeshProductionError.__name__}: {line[match.end():end].strip().removesuffix(';')}"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    reason = lines[-1] if lines else type(error).__name__
    for prefix in _JOB_FAILURE_PREFIXES:
        reason = reason.removeprefix(prefix)
    return {cid: own.get(cid, reason) for cid in failed}
