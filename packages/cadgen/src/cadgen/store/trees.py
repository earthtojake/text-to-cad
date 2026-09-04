"""Trees: a model's result as a content-addressed object.

A tree holds the geometry a model made itself (``components``, placed by its
``occurrences``) and ``links`` to its children's trees. Two placements of one
child are two links to one tree. Nothing of a child is copied::

    {
      "kind": "tree",
      "label": "robot", "entryKind": "assembly",
      "components": {"<cid>": {"surf": "<object>", "brep": "<object>", "contentHash": "…", "color": [...]}},
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

import json
from typing import Any

from cadgen.store.objects import put_object, read_object

TREE_KIND = "tree"
FLAT_KIND = "assembly-package"

IDENTITY_16 = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def put_tree(tree: dict[str, Any]) -> str:
    body = dict(tree)
    body["kind"] = TREE_KIND
    data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return put_object(data)


def get_tree(tree_hash: str) -> dict[str, Any] | None:
    try:
        data = json.loads(read_object(tree_hash).decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") != TREE_KIND:
        return None
    return data


def tree_objects(tree_hash: str, *, _seen: set[str] | None = None) -> set[str]:
    """Every object hash a tree references, transitively (itself, its
    components' surf/brep objects, its linked trees and theirs)."""
    seen = _seen if _seen is not None else set()
    if tree_hash in seen:
        return seen
    seen.add(tree_hash)
    tree = get_tree(tree_hash)
    if tree is None:
        return seen
    for entry in (tree.get("components") or {}).values():
        for key in ("surf", "brep"):
            digest = str((entry or {}).get(key) or "")
            if digest:
                seen.add(digest)
    for link in tree.get("links") or []:
        child = str((link or {}).get("tree") or "")
        if child:
            tree_objects(child, _seen=seen)
    return seen


def tree_complete(tree_hash: str) -> bool:
    """Whether the tree object and every object it references exist."""
    from cadgen.store.objects import has_object

    if not has_object(tree_hash):
        return False
    return all(has_object(digest) for digest in tree_objects(tree_hash))


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


def flatten(tree_hash: str, *, memo: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """The assembly.json for a tree, links expanded. None when the tree is missing."""
    memo = memo if memo is not None else {}
    cached = memo.get(tree_hash)
    if cached is not None:
        return json.loads(json.dumps(cached))
    tree = get_tree(tree_hash)
    if tree is None:
        return None

    components: dict[str, Any] = {cid: dict(entry) for cid, entry in (tree.get("components") or {}).items()}
    occurrences: list[dict[str, Any]] = [dict(occ) for occ in tree.get("occurrences") or []]
    links = {str(link.get("id")): link for link in (tree.get("links") or []) if isinstance(link, dict)}

    def expand(node: dict[str, Any]) -> dict[str, Any] | None:
        node_type = str(node.get("nodeType") or "")
        node_id = str(node.get("id") or "")
        if node_type == "link" or node_id in links:
            link = links.get(node_id) or {}
            child_hash = str(link.get("tree") or "")
            child = flatten(child_hash, memo=memo) if child_hash else None
            if child is None:
                return None
            placement = _as16(link.get("transform"))
            for cid, entry in (child.get("components") or {}).items():
                components.setdefault(cid, dict(entry))
            link_name = str(link.get("name") or node.get("name") or node_id)
            for occ in child.get("occurrences") or []:
                placed = dict(occ)
                occ_id = str(occ.get("id") or "o1")
                placed["id"] = _rebase_id(node_id, occ_id)
                placed["transform"] = compose_transforms(placement, occ.get("transform"))
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
    descriptor["tree"] = tree_hash
    descriptor["components"] = components
    root = (tree.get("assembly") or {}).get("root")
    expanded_root = expand(root) if isinstance(root, dict) else None
    descriptor["occurrences"] = occurrences
    if expanded_root is not None:
        descriptor["assembly"] = {"root": expanded_root}
    stats = dict(descriptor.get("stats") or {})
    stats["occurrenceCount"] = len(occurrences)
    stats["shapeCount"] = len(occurrences)
    descriptor["stats"] = stats
    memo[tree_hash] = json.loads(json.dumps(descriptor))
    return descriptor
