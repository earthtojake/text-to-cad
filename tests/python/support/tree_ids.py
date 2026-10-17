"""Occurrence tokens for tests.

A tree names its nodes by tokens minted from its structure
(``cadgen._internal.tree_tokens``), so a test never writes an occurrence id
down: it tokenises the tree it hand-builds (``tokenized``), or finds a built
tree's node by its name (``node_id``) and reads the token off the tree."""

from __future__ import annotations

from typing import Any, Mapping


def tokenized(tree: dict[str, Any], *, link_leaf: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """``tree`` (hand-built, with provisional ids) with every id a token, and the
    provisional-id -> token mapping it was rewritten through."""
    from cadgen._internal.tree_tokens import assign_tokens, retoken

    root = tree["assembly"]["root"]
    mapping = assign_tokens(root, tree.get("occurrences") or [], tree.get("links") or [],
                            label=tree.get("label"), link_leaf=dict(link_leaf or {}))
    return retoken(tree, mapping), mapping


def nodes(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every node of the descriptor's assembly tree, root first, in tree order."""
    root = (descriptor.get("assembly") or {}).get("root")
    found: list[dict[str, Any]] = []
    stack = [root] if isinstance(root, dict) else []
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(reversed([child for child in node.get("children") or [] if isinstance(child, dict)]))
    return found


def node_id(descriptor: Mapping[str, Any], name: str) -> str:
    """The token of the one node named ``name`` in the descriptor's tree."""
    matches = [str(node["id"]) for node in nodes(descriptor) if str(node.get("name") or "") == name]
    if len(matches) != 1:
        raise KeyError(f"{name!r} names {len(matches)} nodes: {matches}")
    return matches[0]


def node_ids(descriptor: Mapping[str, Any], *names: str) -> list[str]:
    return [node_id(descriptor, name) for name in names]


def leaf_ids(descriptor: Mapping[str, Any]) -> list[str]:
    """The tokens of the descriptor's occurrence rows, in row order."""
    return [str(row["id"]) for row in descriptor.get("occurrences") or []]


def leaf_id(descriptor: Mapping[str, Any], name: str) -> str:
    """The token of the one occurrence row named ``name``."""
    matches = [str(row["id"]) for row in descriptor.get("occurrences") or [] if str(row.get("name") or "") == name]
    if len(matches) != 1:
        raise KeyError(f"{name!r} names {len(matches)} occurrences: {matches}")
    return matches[0]


def root_id(descriptor: Mapping[str, Any]) -> str:
    return str(descriptor["assembly"]["root"]["id"])
