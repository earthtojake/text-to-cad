"""``leaves(tree)``: every leaf of a build123d tree, placed where it stands, out of the tree.

A tree is what ``step.read``, ``xbf.read`` and a model's ``.shape`` return: each node's ``location``
is relative to its parent. build123d's ``located`` and ``moved`` deep-copy the node they are asked of
WITH its parent, so placing one leaf of a read assembly copies the whole assembly's Python nodes (and,
outside the engine's memo, every B-rep in it: seconds and hundreds of megabytes a call on a robot's
STEP). A leaf here is a new object of the leaf's class with the leaf's attributes (its label, colour,
material and what it declares), no parent, and its TopoDS shape the leaf's own placed at the composed
world placement: the same B-rep (the same ``TShape``), no kernel copy, nothing else of the tree touched.
"""

from __future__ import annotations

from typing import Any

__all__ = ["leaves"]


def leaves(tree: Any, *, paths: bool = False) -> list[Any]:
    """Every leaf of ``tree`` (a node with no children), in tree order, placed in the tree's frame.

    Each is a new shape of the leaf's own class, label, colour and material, detached from the tree (no
    parent), its location the product of its ancestors' and its own: what ``leaf.located(world)`` gives,
    without copying the tree. It shares its B-rep with the tree's leaf, so it costs no kernel copy however
    large the assembly. ``paths=True`` gives ``(path, leaf)`` pairs instead, ``path`` the labels from the
    root to the leaf (a label never given is ``""``), so a leaf is found by where it is in the assembly as
    well as by its name."""
    import build123d as bd

    from cad.engine.model import _instance

    found: list[Any] = []
    pending = [(tree, bd.Location(), ())]
    while pending:
        node, parent, path = pending.pop()
        world = parent * node.location
        here = (*path, node.label or "")
        children = list(node.children)
        if children:
            pending.extend((child, world, here) for child in reversed(children))
            continue
        placed = _instance(node, {})
        if getattr(placed, "_wrapped", None) is not None:
            from build123d.topology.shape_core import downcast

            placed._wrapped = downcast(node.wrapped.Located(world.wrapped))
        found.append((here, placed) if paths else placed)
    return found
