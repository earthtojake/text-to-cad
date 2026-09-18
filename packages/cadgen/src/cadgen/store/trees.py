"""Trees: a model's result as a content-addressed object.

A tree holds the geometry a model made itself (``components``, placed by its
``occurrences``) and ``links`` to its children's trees. Two placements of one
child are two links to one tree. Nothing of a child is copied::

    {
      "kind": "geometry-tree", "schemaVersion": 2,
      "label": "robot", "entryKind": "assembly",
      "components": {"<cid>": {"kind": "native", "codec": "bintools-v4", "brep": "<object>", "faceColors": {}, "contentHash": "…"}},
      "occurrences": [{"id": "o1.1", "name": "housing", "component": "<cid>", "transform": [16 floats]}],
      "links":       [{"id": "o1.2", "name": "arm", "tree": "<object>", "transform": [16 floats]}],
      "assembly": {"root": {"id": "o1", "name": "robot", "nodeType": "assembly", "children": [...]}},
      "bbox": {...}, "stats": {...}
    }

Occurrence and link transforms are WORLD placements within this tree. In the
structure under ``assembly.root`` a link appears as a node with
``nodeType: "link"`` and its ``id``; ``flatten`` expands it into the child's
structure, re-rooting the child's ids under the link's id and composing the
child's world transforms with the link's placement.

``flatten(tree_hash)`` returns the ASSEMBLY.JSON SHAPE (``kind:
"assembly-package"``, a flat component map, flat world-placed occurrences, a
nested ``assembly.root``) with component refs as object hashes. Every reader
that used to open ``assembly.json`` reads this instead; every path it used to
join under a view directory becomes ``object_path(hash)``.
"""

from __future__ import annotations

import copy
from collections import OrderedDict
import json
import math
import threading
import time
from typing import Any

from cadgen.store.objects import object_path, put_object, read_verified_object

TREE_KIND = "geometry-tree"
TREE_SCHEMA = 2
FLAT_KIND = "assembly-package"

# Metadata readers need an independently owned flattened descriptor but not the
# native bytes that produced it. Re-reading and revalidating every BREP on each
# viewer poll made a many-component document quadratic in practice. Keep only
# compact JSON here: callers still parse a private result, while the cache never
# owns native payloads or mutable descriptor objects.
#
# A hit is admitted only while every required immutable object has the same file
# identity observed on both sides of its verified read. Deletion, in-place
# damage and atomic repair/replacement all change the fingerprint and force the
# ordinary full verification path. The resolved store root is part of the key
# because tests and long-lived embedding processes may switch CADGEN_CACHE_DIR.
#
# A fingerprint only reports damage when a later write could not reproduce it,
# and a filesystem stamps writes from a clock of its own resolution: ~15.6 ms on
# Windows (whose ``st_ctime`` is the CREATION time and never moves for a rewrite
# at all), whole seconds on NFS and two whole seconds on FAT. A same-size
# rewrite inside the tick the
# verified read observed is therefore invisible to every stat field. Such a read
# is never remembered: :func:`_stamp_is_settled` admits an object only once the
# read is far enough past its write that the next write must stamp differently.
_METADATA_CAPTURE_CACHE_CAPACITY = 64 * 1024 * 1024
_METADATA_CAPTURE_CACHE: OrderedDict[tuple[str, str], tuple[bytes, tuple, int]] = OrderedDict()
_METADATA_CAPTURE_CACHE_SIZE = 0
_METADATA_CAPTURE_CACHE_LOCK = threading.Lock()
_METADATA_CAPTURE_FLIGHTS: dict[tuple[str, str], dict] = {}
_METADATA_CAPTURE_STAMP_BYTES = 512

IDENTITY_16 = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def put_tree(tree: dict[str, Any], *, repair: bool = False) -> str:
    from cadgen._internal.component_package import canonical_json_bytes

    body = dict(tree)
    body["kind"] = TREE_KIND
    body["schemaVersion"] = TREE_SCHEMA
    _validate_structure(body)
    return put_object(canonical_json_bytes(body), repair=repair)


def get_tree(tree_hash: str) -> dict[str, Any] | None:
    try:
        data = json.loads(read_verified_object(tree_hash))
        _validate_structure(data)
        return data
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def tree_objects(tree_hash: str, *, _seen: set[str] | None = None) -> set[str]:
    """Available verified closure, even when another required object is absent."""
    seen = _seen if _seen is not None else set()
    pending, visited = [tree_hash], set()
    while pending:
        digest = pending.pop()
        if digest in visited:
            continue
        visited.add(digest)
        tree = get_tree(digest)
        if tree is None:
            continue
        seen.add(digest)
        for entry in tree["components"].values():
            if not isinstance(entry, dict):
                continue
            for field in ("brep", "eagerSurface"):
                if entry.get(field):
                    try:
                        read_verified_object(entry[field])
                    except (OSError, ValueError, TypeError):
                        continue
                    seen.add(entry[field])
        pending.extend(link["tree"] for link in tree["links"])
    return seen


def tree_complete(tree_hash: str) -> bool:
    """Full verified geometry closure; disposable surfaces are not required."""
    try:
        capture_tree(tree_hash)
        return True
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
        return False


# --- transforms ---------------------------------------------------------------


def _as16(values: object) -> list[float]:
    if isinstance(values, (list, tuple)) and len(values) == 16:
        return [float(v) for v in values]
    if isinstance(values, (list, tuple)) and len(values) == 12:
        # gp_Trsf row-major 3x4 -> 4x4
        v = [float(x) for x in values]
        return [*v[0:4], *v[4:8], *v[8:12], 0.0, 0.0, 0.0, 1.0]
    return list(IDENTITY_16)


def compose_transforms(parent: object, child: object) -> list[float]:
    """Row-major 4x4 product ``parent @ child`` (child placed inside parent)."""
    a = _as16(parent)
    b = _as16(child)
    out = [0.0] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
    return out


# --- flatten ------------------------------------------------------------------


def _rebase_id(link_id: str, child_id: str) -> str:
    """``o1.2`` + child ``o1.3.1`` -> ``o1.2.3.1``: the child's root IS the link."""
    child_id = str(child_id or "o1")
    if child_id in ("o1", "o"):
        return link_id
    suffix = child_id[len("o1") :] if child_id.startswith("o1") else "." + child_id.lstrip("o")
    return f"{link_id}{suffix}"


def tree_kind(tree: dict[str, Any] | None) -> str:
    """``"assembly"`` or ``"part"``, read off the TREE and nowhere else.

    A tree with links, or with more than one own occurrence, is an assembly; one
    occurrence and no links is a part. The authored ``kind=`` (or the static
    inference from a model's return) only steers how a build packages its own
    geometry; what a run reports, what ``inspect`` reports, and what
    ``inspect diff`` compares is this, so the three can never disagree.
    """
    if not isinstance(tree, dict):
        return "part"
    if tree.get("links"):
        return "assembly"
    return "assembly" if len(tree.get("occurrences") or []) > 1 else "part"


def tree_kind_for(tree_hash: str | None) -> str | None:
    """:func:`tree_kind` of a stored tree, or None when there is no such tree."""
    if not tree_hash:
        return None
    tree = get_tree(tree_hash)
    return tree_kind(tree) if tree is not None else None


def flatten(tree_hash: str, *, memo: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """The assembly.json for a tree, links expanded. None when the tree is missing."""
    memo = memo if memo is not None else {}
    cached = memo.get(tree_hash)
    if cached is not None:
        return json.loads(json.dumps(cached))
    tree = get_tree(tree_hash)
    if tree is None:
        return None
    return flatten_tree(tree, tree_hash=tree_hash, memo=memo)


def flatten_tree(
    tree: dict[str, Any],
    *,
    tree_hash: str | None = None,
    memo: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """:func:`flatten` of a tree held in memory — one not (yet) in the store.

    The build flattens its own result before it is published, to assemble the
    STEP it then re-reads (``cadgen.store.build``); the links inside it resolve
    against the store as usual. ``tree_hash`` is recorded on the descriptor when
    known and memoizes the result."""
    memo = memo if memo is not None else {}

    components: dict[str, Any] = {cid: dict(entry) for cid, entry in (tree.get("components") or {}).items()}
    occurrences: list[dict[str, Any]] = [dict(occ) for occ in tree.get("occurrences") or []]
    links = {str(link.get("id")): link for link in (tree.get("links") or []) if isinstance(link, dict)}
    # A published model tree carries its complete resolved intrinsic appearance.
    # An unpublished draft does not, so flattening it composes child libraries
    # and rebases their assignments before the parent declaration is resolved.
    from cadgen._internal.source_sidecar import normalize_appearance

    appearance_authoritative = tree.get("appearance") is not None
    own_appearance = normalize_appearance(tree.get("appearance"))
    if own_appearance is None:
        inline_materials: dict[str, Any] = {}
        inline_assignments: dict[str, str] = {}
        for occurrence in occurrences:
            material = occurrence.get("material")
            material_id = occurrence.get("materialId")
            if isinstance(material, dict) and isinstance(material_id, str) and material_id:
                inline_materials[material_id] = dict(material)
                inline_assignments[str(occurrence.get("id") or "")] = material_id
        if inline_assignments:
            own_appearance = normalize_appearance({
                "materials": inline_materials, "assignments": inline_assignments,
            })
    appearance_materials = dict((own_appearance or {}).get("materials") or {})
    appearance_assignments = dict((own_appearance or {}).get("assignments") or {})

    def inherit_appearance(child: dict[str, Any], link_id: str) -> None:
        if appearance_authoritative:
            return
        child_appearance = normalize_appearance(child.get("appearance"))
        if child_appearance is None:
            return
        remapped: dict[str, str] = {}
        for material_id, definition in child_appearance["materials"].items():
            if material_id not in appearance_materials or appearance_materials[material_id] == definition:
                inherited_id = material_id
            else:
                inherited_id = f"{link_id}/{material_id}"
                suffix = 2
                while inherited_id in appearance_materials and appearance_materials[inherited_id] != definition:
                    inherited_id = f"{link_id}-{suffix}/{material_id}"
                    suffix += 1
            appearance_materials.setdefault(inherited_id, dict(definition))
            remapped[material_id] = inherited_id
        for occurrence_id, material_id in child_appearance["assignments"].items():
            appearance_assignments[_rebase_id(link_id, occurrence_id)] = remapped[material_id]

    def expand(node: dict[str, Any]) -> dict[str, Any] | None:
        node_type = str(node.get("nodeType") or "")
        node_id = str(node.get("id") or "")
        if node_type == "link" or node_id in links:
            link = links.get(node_id) or {}
            child_hash = str(link.get("tree") or "")
            child = flatten(child_hash, memo=memo) if child_hash else None
            if child is None:
                raise FileNotFoundError(
                    f"tree {tree_hash or '<unpublished>'}: linked tree object missing: "
                    f"{child_hash or '<empty>'}"
                )
            inherit_appearance(child, node_id)
            placement = _as16(link.get("transform"))
            for cid, entry in (child.get("components") or {}).items():
                components.setdefault(cid, dict(entry))
            link_name = str(link.get("name") or node.get("name") or node_id)
            link_color = link.get("color")
            child_is_part = str(child.get("entryKind") or "") == "part"
            for occ in child.get("occurrences") or []:
                placed = dict(occ)
                occ_id = str(occ.get("id") or "o1")
                placed["id"] = _rebase_id(node_id, occ_id)
                placed["transform"] = compose_transforms(placement, occ.get("transform"))
                component = (child.get("components") or {}).get(str(occ.get("component") or "")) or {}
                # A root color on a materialized Compound is inherited only by
                # descendants with no explicit color of their own. Component
                # color is the occurrence fallback used by materialize/render,
                # so it is an authored color for the same purpose here.
                if link_color is not None and (
                    child_is_part or (occ.get("color") is None and component.get("color") is None)
                ):
                    placed["color"] = link_color
                if occ_id == "o1":
                    # A part child is ONE occurrence, its root: it takes the
                    # link's name (the label the parent gave the placement).
                    placed["name"] = link_name
                occurrences.append(placed)

            def rebase(sub: dict[str, Any]) -> dict[str, Any]:
                out = dict(sub)
                out["id"] = _rebase_id(node_id, str(sub.get("id") or "o1"))
                if sub.get("children"):
                    out["children"] = [rebase(c) for c in sub["children"]]
                    out["leafPartIds"] = [leaf for c in out["children"] for leaf in c.get("leafPartIds", [c["id"]])]
                else:
                    out["leafPartIds"] = [out["id"]]
                return out

            child_root = (child.get("assembly") or {}).get("root")
            if isinstance(child_root, dict):
                rebased = rebase(child_root)
                rebased["name"] = str(link.get("name") or node.get("name") or rebased.get("name") or node_id)
                rebased["nodeType"] = "subassembly" if rebased.get("children") else "part"
                rebased["id"] = node_id
                return rebased
            # A part child: one leaf occurrence, rebased to the link id.
            return {"id": node_id, "name": str(link.get("name") or node.get("name") or node_id), "nodeType": "part", "leafPartIds": [node_id], "children": []}
        children = [expand(c) for c in node.get("children") or [] if isinstance(c, dict)]
        children = [c for c in children if c is not None]
        out = dict(node)
        if children:
            out["children"] = children
            out["leafPartIds"] = [leaf for c in children for leaf in c.get("leafPartIds", [c["id"]])]
        return out

    descriptor: dict[str, Any] = {
        key: value
        for key, value in tree.items()
        if key not in {"kind", "components", "occurrences", "links", "assembly"}
    }
    descriptor["kind"] = FLAT_KIND
    if tree_hash is not None:
        descriptor["tree"] = tree_hash
    descriptor["entryKind"] = tree_kind(tree)
    descriptor["components"] = components
    root = (tree.get("assembly") or {}).get("root")
    expanded_root = expand(root) if isinstance(root, dict) else None
    descriptor["occurrences"] = occurrences
    appearance = normalize_appearance({
        "materials": appearance_materials,
        "assignments": appearance_assignments,
    }) if (appearance_materials or appearance_assignments) else None
    if appearance is not None:
        descriptor["appearance"] = appearance
    else:
        descriptor.pop("appearance", None)
    if expanded_root is not None:
        descriptor["assembly"] = {"root": expanded_root}
    stats = dict(descriptor.get("stats") or {})
    stats["occurrenceCount"] = len(occurrences)
    stats["shapeCount"] = len(occurrences)
    descriptor["stats"] = stats
    if tree_hash is not None:
        memo[tree_hash] = json.loads(json.dumps(descriptor))
    return descriptor


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _validate_structure(tree: Any, *, native: bool = False) -> None:
    if type(tree) is not dict or tree.get("kind") != TREE_KIND or tree.get("schemaVersion") != TREE_SCHEMA:
        raise ValueError("unsupported geometry tree schema")
    if "surfaceProducer" in tree:
        raise ValueError("geometry tree contains a surface producer")
    if "appearance" in tree:
        from cadgen._internal.source_sidecar import normalize_appearance

        appearance = normalize_appearance(tree["appearance"])
        if appearance is None or appearance != tree["appearance"]:
            raise ValueError("invalid geometry tree appearance")
    if tree.get("units") != "mm" or tree.get("entryKind") not in {"part", "assembly"}:
        raise ValueError("invalid geometry tree metadata")
    if type(tree.get("components")) is not dict or type(tree.get("occurrences")) is not list or type(tree.get("links")) is not list:
        raise ValueError("invalid geometry tree tables")
    from cadgen.store.objects import is_object_hash
    for link in tree["links"]:
        if type(link) is not dict or not is_object_hash(link.get("tree")):
            raise ValueError("invalid linked tree identity")
    ids = set()
    occurrence_ids = {row.get("id") for row in tree["occurrences"] if type(row) is dict and type(row.get("id")) is str}
    for row in [*tree["occurrences"], *tree["links"]]:
        if type(row) is not dict or type(row.get("id")) is not str or not row["id"] or row["id"] in ids:
            raise ValueError("invalid or duplicate occurrence/link ID")
        ids.add(row["id"])
        transform = row.get("transform")
        if type(transform) is not list or len(transform) != 16 or any(
            type(value) not in (float, int) or not _finite_number(value) for value in transform
        ) or transform[12:] != [0, 0, 0, 1]:
            raise ValueError("invalid geometry transform")
        if native:
            from cadgen.store.materialize import _native_location_from_matrix
            _native_location_from_matrix(transform)
    for row in tree["occurrences"]:
        if row.get("component") not in tree["components"]:
            raise ValueError("unknown occurrence component")
    root = (tree.get("assembly") or {}).get("root")
    if type(root) is not dict:
        raise ValueError("missing assembly root")
    pending, seen = [root], set()
    represented = set()
    while pending:
        node = pending.pop()
        if type(node) is not dict or type(node.get("id")) is not str or not node["id"] or node["id"] in seen or node.get("nodeType") not in {"part", "assembly", "subassembly", "link"}:
            raise ValueError("invalid assembly structure")
        seen.add(node.get("id"))
        children = node.get("children")
        if type(children) is not list:
            raise ValueError("invalid assembly children")
        if node["id"] in ids:
            if children or node["nodeType"] != ("part" if node["id"] in occurrence_ids else "link"):
                raise ValueError("geometry occurrence is not an exact assembly leaf")
            represented.add(node["id"])
        if not children and node.get("id") not in ids:
            raise ValueError("assembly leaf has no geometry")
        pending.extend(children)
    if represented != ids:
        raise ValueError("geometry rows absent from assembly structure")


_STAMP_MTIME_NS = 4
# A clock that ticks every T ns can only stamp multiples of T, so an observed
# stamp's trailing zeros bound the resolution that produced it from below.
# Coarsest first: a stamp is attributed to the coarsest clock that could have
# produced it, because over-estimating the tick costs one cache miss while
# under-estimating certifies a read a later write can still reproduce. FAT's
# 2 s write time divides by 1 s, so it needs an entry of its own -- read as a
# 1 s clock it would admit a rewrite in the back half of its own tick.
_TIMESTAMP_TICKS_NS = (2_000_000_000, 1_000_000_000, 15_625_000, 1_000_000)


def _object_stamp(digest: str) -> tuple:
    stat = object_path(digest).stat()
    return (digest, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _timestamp_resolution_ns(mtime_ns: int) -> int:
    """How coarsely the filesystem that produced ``mtime_ns`` stamps a write."""
    for tick in _TIMESTAMP_TICKS_NS:
        if mtime_ns % tick == 0:
            return tick
    return 1


def _stamp_is_settled(stamp: tuple) -> bool:
    """True when a write made from here on cannot reproduce ``stamp``.

    The read happened at least one timestamp tick after the write it observed,
    so any later write lands in a tick the fingerprint does not already hold.
    A nanosecond-resolution filesystem settles immediately; a coarse one (or a
    clock that ran backwards) leaves a short window in which the bytes may still
    change silently, and nothing read in it is remembered.
    """
    mtime_ns = stamp[_STAMP_MTIME_NS]
    return time.time_ns() - mtime_ns >= _timestamp_resolution_ns(mtime_ns)


def _metadata_capture_key(tree_hash: str) -> tuple[str, str]:
    from cadgen.store.paths import store_root

    return str(store_root().resolve()), str(tree_hash)


def _metadata_capture_hit(key: tuple[str, str]) -> dict | None:
    with _METADATA_CAPTURE_CACHE_LOCK:
        cached = _METADATA_CAPTURE_CACHE.get(key)
    if cached is None:
        return None
    body, stamps, _weight = cached
    try:
        current = tuple(_object_stamp(stamp[0]) for stamp in stamps)
    except (OSError, ValueError):
        current = None
    if current != stamps:
        global _METADATA_CAPTURE_CACHE_SIZE
        with _METADATA_CAPTURE_CACHE_LOCK:
            if _METADATA_CAPTURE_CACHE.get(key) is cached:
                _METADATA_CAPTURE_CACHE.pop(key)
                _METADATA_CAPTURE_CACHE_SIZE -= cached[2]
        return None
    with _METADATA_CAPTURE_CACHE_LOCK:
        if _METADATA_CAPTURE_CACHE.get(key) is cached:
            _METADATA_CAPTURE_CACHE.move_to_end(key)
    return json.loads(body)


def _remember_metadata_capture(key: tuple[str, str], descriptor: dict, stamps: dict[str, tuple]) -> None:
    global _METADATA_CAPTURE_CACHE_SIZE
    body = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ordered_stamps = tuple(stamps[digest] for digest in sorted(stamps))
    weight = len(body) + len(ordered_stamps) * _METADATA_CAPTURE_STAMP_BYTES
    if weight > _METADATA_CAPTURE_CACHE_CAPACITY:
        return
    with _METADATA_CAPTURE_CACHE_LOCK:
        previous = _METADATA_CAPTURE_CACHE.pop(key, None)
        if previous is not None:
            _METADATA_CAPTURE_CACHE_SIZE -= previous[2]
        _METADATA_CAPTURE_CACHE[key] = (body, ordered_stamps, weight)
        _METADATA_CAPTURE_CACHE_SIZE += weight
        while _METADATA_CAPTURE_CACHE_SIZE > _METADATA_CAPTURE_CACHE_CAPACITY:
            _old_key, (_old_body, _old_stamps, old_weight) = _METADATA_CAPTURE_CACHE.popitem(last=False)
            _METADATA_CAPTURE_CACHE_SIZE -= old_weight


def _reset_metadata_capture_cache() -> None:
    """Release process-owned verified metadata snapshots (tests and embedding)."""
    global _METADATA_CAPTURE_CACHE_SIZE
    with _METADATA_CAPTURE_CACHE_LOCK:
        _METADATA_CAPTURE_CACHE.clear()
        _METADATA_CAPTURE_CACHE_SIZE = 0


def _begin_metadata_capture(key: tuple[str, str]) -> tuple[dict, bool]:
    """Join one exact metadata verification already running in this process."""
    with _METADATA_CAPTURE_CACHE_LOCK:
        flight = _METADATA_CAPTURE_FLIGHTS.get(key)
        if flight is not None:
            return flight, False
        flight = {"event": threading.Event(), "body": None, "failure": None}
        _METADATA_CAPTURE_FLIGHTS[key] = flight
        return flight, True


def _finish_metadata_capture(key: tuple[str, str], flight: dict) -> None:
    with _METADATA_CAPTURE_CACHE_LOCK:
        if _METADATA_CAPTURE_FLIGHTS.get(key) is flight:
            _METADATA_CAPTURE_FLIGHTS.pop(key)
        flight["event"].set()

def capture_tree(tree_hash: str, *, retain_payloads: bool = True) -> tuple[dict, dict[str, bytes]]:
    """One verified graph snapshot with independently owned metadata.

    Native consumers retain the complete immutable byte closure by default.
    Metadata-only callers may discard payloads after the same full verification.
    Later calls reuse compact metadata only while the complete immutable object
    closure retains the exact file identities observed during verified reads.
    """
    from cadgen._internal.component_package import canonical_json_bytes, validate_geometry_component
    from cadgen.store.surfaces import validate_surface_bytes

    cache_key = _metadata_capture_key(tree_hash)
    flight = None
    if not retain_payloads:
        flight, leader = _begin_metadata_capture(cache_key)
        if not leader:
            flight["event"].wait()
            if flight["failure"] is not None:
                error_type, error_args = flight["failure"]
                try:
                    cloned_error = error_type(*error_args)
                except Exception:
                    cloned_error = RuntimeError(str(
                        error_args[0] if error_args else "metadata capture failed"
                    ))
                raise cloned_error
            if flight["body"] is None:
                raise RuntimeError("metadata capture ended without a result")
            return json.loads(flight["body"]), {}
        try:
            cached = _metadata_capture_hit(cache_key)
            if cached is not None:
                flight["body"] = json.dumps(cached, sort_keys=True, separators=(",", ":")).encode("utf-8")
                return cached, {}
        except BaseException as error:
            flight["failure"] = (type(error), error.args)
            raise
        finally:
            if flight["body"] is not None or flight["failure"] is not None:
                _finish_metadata_capture(cache_key, flight)

    captured, memo, active = {}, {}, set()
    stamps: dict[str, tuple] = {}
    cacheable = True

    def verified(digest):
        nonlocal cacheable
        try:
            before = _object_stamp(digest)
        except (OSError, ValueError):
            before = None
        payload = read_verified_object(digest)
        try:
            after = _object_stamp(digest)
        except (OSError, ValueError):
            after = None
        if before is None or after is None or before != after or not _stamp_is_settled(after):
            cacheable = False
        else:
            stamps[digest] = after
        return payload

    def visit(digest):
        if digest in memo:
            return
        if digest in active:
            raise ValueError("cyclic geometry tree")
        payload = verified(digest)
        tree = json.loads(payload)
        _validate_structure(tree)
        if retain_payloads:
            captured[digest] = payload
        del payload
        active.add(digest)
        for cid, entry in tree["components"].items():
            if type(entry) is not dict:
                raise ValueError("invalid geometry component")
            brep = verified(entry["brep"])
            validate_geometry_component(entry, brep, cid=cid)
            if retain_payloads:
                captured[entry["brep"]] = brep
            del brep
            if entry["kind"] == "eager-only":
                surf = verified(entry["eagerSurface"])
                validate_surface_bytes(surf)
                if retain_payloads:
                    captured[entry["eagerSurface"]] = surf
                del surf
        for link in tree["links"]:
            visit(link["tree"])
        merged = dict(tree["components"])
        for link in tree["links"]:
            for cid, entry in memo[link["tree"]]["components"].items():
                previous = merged.setdefault(cid, entry)
                # Component-level display color is an occurrence fallback; all
                # intrinsic identity/producer/required-object fields must agree.
                a = {key: value for key, value in previous.items() if key != "color"}
                b = {key: value for key, value in entry.items() if key != "color"}
                if canonical_json_bytes(a) != canonical_json_bytes(b):
                    raise ValueError("linked component identity conflict")
        # Child descriptors are already verified and memoized, so the stock
        # flattener cannot reread a root or escape this exact graph snapshot.
        descriptor = flatten_tree(tree, tree_hash=digest, memo=memo)
        memo[digest] = descriptor
        active.remove(digest)

    try:
        visit(tree_hash)
        descriptor = copy.deepcopy(memo[tree_hash])
        if not retain_payloads and cacheable:
            _remember_metadata_capture(cache_key, descriptor, stamps)
        if flight is not None:
            flight["body"] = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return descriptor, dict(captured)
    except BaseException as error:
        if flight is not None:
            flight["failure"] = (type(error), error.args)
        raise
    finally:
        if flight is not None:
            _finish_metadata_capture(cache_key, flight)
