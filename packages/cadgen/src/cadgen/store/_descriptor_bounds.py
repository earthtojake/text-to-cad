"""Exact bounds and private preparation for bounded pinned-link descriptors.

Only immutable numeric bounds enter the existing op index. Captured bytes,
appearance recipes and native prototypes belong to one build invocation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
import struct
import sys
from typing import Any

from cadgen.store.objects import object_path
from cadgen.store.trees import flatten_tree

OP = "component_bbox.canonical_full_placement.algorithm1"
MAX_TREE_BYTES = 64 * 1024
MAX_BREP_BYTES = 768 * 1024
MAX_SURF_BYTES = 4 * 1024 * 1024
MAX_COMPONENTS = 16
MAX_OCCURRENCES = 64
MAX_TREES = 32
MAX_DEPTH = 32
MAX_APPEARANCE_BYTES = 256 * 1024


class Ineligible(ValueError):
    """The ordinary whole-document path must handle this descriptor."""


@lru_cache(maxsize=1)
def _native_identity() -> str:
    # OCP.__version__ is exported by the loaded native extension, not inferred
    # from build123d. Include the required no-VTK provider identity too; an
    # installation using a different provider must not share this disk key.
    import OCP
    from importlib.metadata import PackageNotFoundError, version
    native = getattr(OCP, "__version__", None)
    try:
        binding = version("cadquery-ocp-novtk")
    except PackageNotFoundError as error:
        raise Ineligible("missing native binding identity") from error
    if type(native) is not str or not native or native == "unknown" or not binding:
        raise Ineligible("unsupported native identity")
    return f"native={native};provider=cadquery-ocp-novtk;binding={binding}"


def _box_values(value: Any) -> tuple[float, ...]:
    if type(value) not in (list, tuple) or len(value) != 6:
        raise Ineligible("missing bounds")
    if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) >= 1e90 for v in value):
        raise Ineligible("nonfinite/open bounds")
    if any(value[a] > value[a + 3] for a in range(3)):
        raise Ineligible("inverted bounds")
    return tuple(value)


def _read(digest: str, limit: int) -> bytes:
    # A racing oversized replacement never allocates more than the admission
    # remainder. Hash the exact consumed snapshot, not an earlier stat result.
    with object_path(digest).open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit or hashlib.sha256(payload).hexdigest() != digest:
        raise Ineligible("object size/digest mismatch")
    return payload


def _json_bytes(value: Any, limit: int = MAX_TREE_BYTES) -> bytes:
    # Bound native-free root metadata before a serializer can allocate an
    # oversized string/list representation. Tree-object JSON is bounded on read.
    nodes = 0

    def check(item, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 8192 or depth > MAX_DEPTH:
            raise Ineligible("metadata limit")
        if type(item) is str:
            if len(item) > limit:
                raise Ineligible("metadata string limit")
        elif type(item) is dict:
            if len(item) > 1024 or any(type(key) is not str for key in item):
                raise Ineligible("metadata map limit")
            for key, child in item.items():
                check(key, depth + 1)
                check(child, depth + 1)
        elif type(item) in (list, tuple):
            if len(item) > 1024:
                raise Ineligible("metadata list limit")
            for child in item:
                check(child, depth + 1)
        elif item is None or type(item) in (bool, int, float):
            if type(item) is float and not math.isfinite(item):
                raise Ineligible("nonfinite metadata")
        else:
            raise Ineligible("non-JSON metadata")

    check(value)
    chunks, total = [], 0
    for chunk in json.JSONEncoder(allow_nan=False).iterencode(value):
        data = chunk.encode()
        total += len(data)
        if total > limit:
            raise Ineligible("metadata byte limit")
        chunks.append(data)
    return b"".join(chunks)


def _ordered(descriptor: dict[str, Any]) -> tuple[tuple[str, tuple[float, ...]], ...]:
    occurrences = descriptor.get("occurrences")
    components = descriptor.get("components")
    if type(occurrences) is not list or not 1 <= len(occurrences) <= MAX_OCCURRENCES:
        raise Ineligible("occurrence limit")
    if type(components) is not dict or not 1 <= len(components) <= MAX_COMPONENTS:
        raise Ineligible("component limit")
    lookup = {}
    for occurrence in occurrences:
        identity = occurrence.get("id")
        if type(identity) is not str or identity in lookup or occurrence.get("component") not in components:
            raise Ineligible("ambiguous occurrence identity")
        matrix = occurrence.get("transform")
        if (type(matrix) is not list or len(matrix) != 16 or
                any(type(v) not in (float, int) or not math.isfinite(v) for v in matrix) or
                matrix[12:] != [0., 0., 0., 1.]):
            raise Ineligible("unsupported placement")
        lookup[identity] = occurrence
    result = []

    def visit(node, depth=0):
        if type(node) is not dict or depth > MAX_DEPTH:
            raise Ineligible("unsupported hierarchy")
        children = node.get("children", [])
        identity = node.get("id")
        if identity in lookup and not children:
            occurrence = lookup[identity]
            result.append((occurrence["component"], tuple(occurrence["transform"])))
        elif type(children) is list and children and identity not in lookup:
            # Matches _world_leaves' LIFO traversal, including tie order.
            for child in reversed(children):
                visit(child, depth + 1)
        else:
            raise Ineligible("unmaterialized hierarchy node")

    visit(descriptor.get("assembly", {}).get("root"))
    ids = []

    def collect(node):
        if not node.get("children"):
            ids.append(node["id"])
        else:
            for child in node["children"]:
                collect(child)

    collect(descriptor["assembly"]["root"])
    if len(ids) != len(lookup) or set(ids) != set(lookup):
        raise Ineligible("hierarchy/occurrence mismatch")
    return tuple(result)


@dataclass(frozen=True)
class Snapshot:
    descriptor_json: bytes
    objects: tuple[tuple[str, bytes], ...]
    occurrences: tuple[tuple[str, tuple[float, ...]], ...]
    component_breps: tuple[tuple[str, str], ...]
    face_colors: tuple[tuple[str, tuple[tuple[int, tuple[float, ...]], ...]], ...] = ()

    def descriptor(self) -> dict[str, Any]:
        return json.loads(self.descriptor_json)

    def verify(self) -> None:
        for digest, payload in self.objects:
            _read(digest, len(payload))

    def capture_appearance(self) -> Snapshot:
        """Own the captured intrinsic recipes before callback, without SURF reads."""
        from cadgen._internal.component_package import _normalized_face_colors
        colors, retained = [], 0
        for cid, entry in self.descriptor()["components"].items():
            recipe = tuple(sorted(_normalized_face_colors(entry["faceColors"]).items()))
            retained += 256 + sys.getsizeof(recipe) + sum(
                sys.getsizeof(row) + sys.getsizeof(row[0]) + sys.getsizeof(row[1])
                + sum(sys.getsizeof(channel) for channel in row[1]) for row in recipe
            )
            if retained > MAX_APPEARANCE_BYTES:
                raise Ineligible("appearance recipe limit")
            colors.append((cid, recipe))
        return replace(self, face_colors=tuple(colors))

    def prepare_document(self) -> PreparedDocument:
        """Validate native bytes/placements before any source callback.

        Decode once per BREP and privately copy topology for face-color variants,
        matching materialize_descriptor's ordinary native construction order.
        """
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from cadgen._internal.component_package import (
            decode_geometry_component,
            _build123d_shape_from_topods, effective_face_colors, canonical_json_bytes, NativeUnavailable,
        )
        from cadgen.store.materialize import _location_from_matrix
        descriptor, payloads, colors = self.descriptor(), dict(self.objects), dict(self.face_colors)
        shapes, decoded = {}, {}
        for cid, entry in descriptor["components"].items():
            if entry.get("kind") == "eager-only":
                raise NativeUnavailable("eager-only component has no admitted native representation")
            if entry.get("kind") != "native":
                raise ValueError("unsupported geometry component kind")
            brep = entry["brep"]
            shape = decoded.get(brep)
            if shape is None:
                shape = decode_geometry_component(entry, payloads[brep])
                decoded[brep] = shape
            else:
                shape = _build123d_shape_from_topods(BRepBuilderAPI_Copy(shape.wrapped, False, False).Shape())
            recipe = dict(colors[cid])
            if canonical_json_bytes(effective_face_colors(shape, recipe)) != canonical_json_bytes(recipe):
                raise ValueError("intrinsic recipe names an absent native face")
            if recipe:
                shape.cad_face_ordinal_colors = recipe
            shapes[cid] = shape
        for occurrence in descriptor["occurrences"]:
            _location_from_matrix(occurrence["transform"])
        return PreparedDocument(self.descriptor_json, shapes)

    def materialize(self, label: str) -> Any:
        return self.prepare_document().materialize(label)

    def bounds(self, *, shapes: dict[str, Any] | None = None) -> dict[str, list[float]]:
        from cadgen._internal import component_package as cp, op_memo
        from cadgen.store.materialize import _location_from_matrix
        payloads, breps = dict(self.objects), dict(self.component_breps)
        entries = self.descriptor()["components"]
        boxes = []
        for cid, transform in self.occurrences:
            brep = breps[cid]

            def compute():
                private = (
                    shapes[cid] if shapes is not None
                    else cp.decode_geometry_component(entries[cid], payloads[brep])
                )
                placed = private.moved(_location_from_matrix(list(transform)))
                box = cp._bbox_from_shape(placed)
                if type(box) is not dict:
                    raise Ineligible("native bounds unavailable")
                return _box_values([*box["min"], *box["max"]])

            values = op_memo.memoized_value(
                OP, (brep, struct.pack("<16d", *transform), _native_identity()), compute
            )
            boxes.append(_box_values(values))
        return {"min": [min(box[a] for box in boxes) for a in range(3)],
                "max": [max(box[a] for box in boxes) for a in range(3, 6)]}


@dataclass(frozen=True)
class PreparedDocument:
    """Invocation-owned, validated native prototypes; never an op-cache value."""
    descriptor_json: bytes
    _shapes: dict[str, Any]

    def materialize(self, label: str) -> Any:
        from cadgen.store.materialize import materialize_descriptor
        return materialize_descriptor(json.loads(self.descriptor_json), shapes=self._shapes, label=label)


def capture_links(draft: dict[str, Any]) -> Snapshot:
    """Capture only complete all-link composition; ordinary cases may miss.

    Verified children are flattened postorder into the existing memo. No global
    reader patch, latest model lookup, native shape or caller object is retained.
    """
    if draft.get("components") or draft.get("occurrences") or not draft.get("links"):
        raise Ineligible("only complete pinned links are supported")
    draft = json.loads(_json_bytes(draft))
    payloads, memo, active = {}, {}, set()
    used = {"tree": 0, "brep": 0, "surf": 0}
    limits = {"tree": MAX_TREE_BYTES, "brep": MAX_BREP_BYTES, "surf": MAX_SURF_BYTES}
    kinds = {}

    def flatten_checked(tree, digest=None):
        occurrences, components, links = (
            tree.get("occurrences", []), tree.get("components", {}), tree.get("links", [])
        )
        if type(occurrences) is not list or type(components) is not dict or type(links) is not list:
            raise Ineligible("invalid tree containers")
        if len(links) > MAX_OCCURRENCES:
            raise Ineligible("link count limit")
        total = len(occurrences)
        cids = set(components)
        for link in links:
            child = memo[link["tree"]]
            total += len(child["occurrences"])
            cids.update(child["components"])
        if total > MAX_OCCURRENCES or len(cids) > MAX_COMPONENTS:
            raise Ineligible("expanded descriptor limit")
        flat = flatten_tree(tree, tree_hash=digest, memo=memo)
        _ordered(flat)
        return flat

    def read(digest, kind):
        if digest in payloads:
            if kinds[digest] != kind:
                raise Ineligible("incompatible object kinds")
            return payloads[digest]
        data = _read(digest, limits[kind] - used[kind])
        used[kind] += len(data)
        payloads[digest], kinds[digest] = data, kind
        return data

    def visit(digest, depth=0):
        if digest in memo:
            return
        if digest in active or depth > MAX_DEPTH or len(active) + len(memo) >= MAX_TREES:
            raise Ineligible("tree graph limit")
        active.add(digest)
        tree = json.loads(read(digest, "tree"))
        from cadgen.store.trees import _validate_structure
        from cadgen._internal.component_package import validate_geometry_component
        from cadgen.store.surfaces import validate_surface_bytes
        _validate_structure(tree)
        for cid, entry in tree.get("components", {}).items():
            validate_geometry_component(entry, read(entry["brep"], "brep"), cid=cid)
            if entry.get("eagerSurface"):
                validate_surface_bytes(read(entry["eagerSurface"], "surf"))
        for link in tree.get("links", []):
            visit(link["tree"], depth + 1)
        flatten_checked(tree, digest)
        active.remove(digest)

    for link in draft["links"]:
        visit(link["tree"])
    descriptor = flatten_checked(draft)
    ordered = _ordered(descriptor)
    return Snapshot(_json_bytes(descriptor), tuple(payloads.items()), ordered,
                    tuple((cid, entry["brep"]) for cid, entry in descriptor["components"].items()))


def try_bounds(draft: dict[str, Any]) -> dict[str, list[float]] | None:
    try:
        return capture_links(draft).bounds()
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
        return None
