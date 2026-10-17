"""Occurrence tokens: every occurrence, link and node of a tree is named by
``o:`` and twelve hexadecimal characters (STORE.md §3, README law 20).

A token is a hash of the node's place in ITS tree and of nothing outside it:
its parent's token, its name and -- for a leaf -- its placement rounded
(translation, as a STEP file states it, to ``TRANSLATION_QUANTUM`` mm, the
linear part to ``ROTATION_QUANTUM``); a group and a link have no placement of their own (a
document places groups at the identity), so theirs hash the parent and the
name alone. The root's token is hashed from the tree's label. When siblings
share all of that (two unnamed pins at one placement), the second and later
hash their rank among those siblings as well, in tree order.

So inserting, removing or reordering a sibling changes no other token; the
flattened tree re-roots a child's nodes under its link's token with their
composed placements (``cadgen.store.trees.flatten``), which is what the saved
document's own hierarchy names them by; and a compile of the STEP, with its own
names and placements, mints the same tokens from them.
A link's token is the token its node has once flattened: a part child's one
leaf (name, composed placement), an assembly child's group (name).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

__all__ = [
    "OCCURRENCE_TOKEN_RE",
    "TRANSLATION_QUANTUM",
    "ROTATION_QUANTUM",
    "assign_tokens",
    "child_token",
    "is_occurrence_token",
    "root_token",
    "rounded_placement",
]

_SCHEME = "cadgen-tree-token-v1"
_HEX = 12
OCCURRENCE_TOKEN_RE = re.compile(r"^o:[0-9a-f]{12}$")
# A placement is rounded absolutely: a translation to a micron, a rotation entry
# to a nanoradian's worth. A STEP file states a real to twelve decimals below a
# thousand in magnitude and to thirteen significant digits from a thousand up
# (``step_reals``), which near a rounding boundary can round otherwise than the
# number written; a reader returns exactly the number stated. So a translation
# is rounded as the file states it, and a translation written and read rounds
# alike by construction. A rotation entry is not stated -- a reader rebuilds it from
# two stated directions -- so one written and read can round otherwise; a writer
# that names its occurrences keeps every rotation it writes from being read as
# another token (``step_placements``).
TRANSLATION_QUANTUM = 1e-6
ROTATION_QUANTUM = 1e-9


def is_occurrence_token(value: object) -> bool:
    return isinstance(value, str) and OCCURRENCE_TOKEN_RE.match(value) is not None


def _token(material: list) -> str:
    payload = json.dumps(material, separators=(",", ":"), allow_nan=False)
    return "o:" + hashlib.sha256(f"{_SCHEME}\0{payload}".encode()).hexdigest()[:_HEX]


def rounded_placement(transform: Any) -> list[int] | None:
    """The 12 placement numbers of a 16-float row-major transform, rounded to
    the quanta, as integers -- each translation as a STEP file states it;
    None for no placement (a group, a link)."""
    from cadgen._internal.step_reals import stated_real

    if transform is None:
        return None
    values = [float(v) for v in transform]
    if len(values) == 12:
        values = [*values, 0.0, 0.0, 0.0, 1.0]
    if len(values) != 16:
        raise ValueError("a placement is 16 numbers")
    out: list[int] = []
    for row in range(3):
        for column in range(4):
            value = values[row * 4 + column]
            if column == 3:
                out.append(int(round(stated_real(value) / TRANSLATION_QUANTUM)))
            else:
                out.append(int(round(value / ROTATION_QUANTUM)))
    return out


def root_token(label: Any) -> str:
    return _token(["root", str(label or "")])


def child_token(parent: str, name: Any, transform: Any = None, rank: int = 0) -> str:
    """The token of a child of ``parent``: its ``name``, its rounded placement
    (None for a group or a link) and, when siblings share both, its rank among
    them (0 for the first)."""
    material: list = [parent, str(name or ""), rounded_placement(transform)]
    if rank:
        material.append(rank)
    return _token(material)


def _sibling_tokens(parent: str, children: list[tuple[Any, Any]]) -> list[str]:
    """Tokens for ``children`` (``(name, transform)`` pairs, in tree order),
    identical siblings ranked."""
    seen: dict[str, int] = {}
    tokens = []
    for name, transform in children:
        plain = child_token(parent, name, transform)
        rank = seen.get(plain, 0)
        seen[plain] = rank + 1
        tokens.append(plain if rank == 0 else child_token(parent, name, transform, rank))
    return tokens


def assign_tokens(
    root: dict[str, Any],
    occurrences: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    label: Any,
    link_leaf: dict[str, Any] | None = None,
) -> dict[str, str]:
    """The token of every node of ``root`` (keyed by the node's current id),
    minted from the tree's structure, names and placements alone.

    ``occurrences`` and ``links`` are the tree's rows, whose ``id`` the nodes
    share; a leaf's placement is its occurrence row's ``transform``. A link
    node is tokened as a group unless ``link_leaf`` maps its id to the
    placement of the one leaf it will be once flattened (a part child), in
    which case it is tokened as that leaf. Nothing here rewrites the tree:
    :func:`retoken` does, with the mapping this returns."""
    placements = {str(row["id"]): row.get("transform") for row in occurrences}
    link_ids = {str(row["id"]) for row in links}
    leaf_placement = dict(link_leaf or {})
    mapping: dict[str, str] = {}

    def visit(node: dict[str, Any], token: str) -> None:
        mapping[str(node["id"])] = token
        children = [child for child in node.get("children") or [] if isinstance(child, dict)]
        pairs = []
        for child in children:
            child_id = str(child["id"])
            if child_id in placements:
                transform = placements[child_id]
            elif child_id in link_ids:
                transform = leaf_placement.get(child_id)
            else:
                transform = None
            pairs.append((child.get("name"), transform))
        for child, child_tok in zip(children, _sibling_tokens(token, pairs)):
            visit(child, child_tok)

    visit(root, root_token(label))
    return mapping


def positional_paths(root: dict[str, Any]) -> dict[str, tuple[int, ...]]:
    """Each node's position in ``root``'s hierarchy, by id: the root is ``(1,)``,
    its children ``(1, 1)``, ``(1, 2)``, ... in tree order. The STEP reader
    names a parsed product by such a path (``step_scene_loader``); this is how
    a tree's token is joined to the product written for it, and it is never a
    name anything keeps."""
    paths: dict[str, tuple[int, ...]] = {}

    def visit(node: dict[str, Any], path: tuple[int, ...]) -> None:
        paths[str(node["id"])] = path
        for index, child in enumerate(node.get("children") or [], start=1):
            if isinstance(child, dict):
                visit(child, (*path, index))

    visit(root, (1,))
    return paths


def retoken(tree: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """``tree`` with every id (nodes, ``leafPartIds``, occurrence and link
    rows, appearance assignments) replaced through ``mapping``. An id the
    mapping lacks is a ``KeyError``: a tree names nothing it does not hold."""
    def node(value: dict[str, Any]) -> dict[str, Any]:
        out = dict(value)
        out["id"] = mapping[str(value["id"])]
        if "children" in value:
            out["children"] = [node(child) for child in value["children"]]
        if "leafPartIds" in value:
            out["leafPartIds"] = [mapping[str(leaf)] for leaf in value["leafPartIds"]]
        return out

    out = dict(tree)
    out["occurrences"] = [{**row, "id": mapping[str(row["id"])]} for row in tree.get("occurrences") or []]
    out["links"] = [{**row, "id": mapping[str(row["id"])]} for row in tree.get("links") or []]
    root = (tree.get("assembly") or {}).get("root")
    if isinstance(root, dict):
        out["assembly"] = {**tree["assembly"], "root": node(root)}
    appearance = tree.get("appearance")
    if isinstance(appearance, dict) and isinstance(appearance.get("assignments"), dict):
        out["appearance"] = {**appearance, "assignments": {
            mapping[str(occurrence_id)]: material for occurrence_id, material in appearance["assignments"].items()
        }}
    return out
