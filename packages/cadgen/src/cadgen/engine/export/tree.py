"""A view made a document again: the tree ``document.to_xcaf`` converts, for a STEP of a
document held without its XCAF document, and for an xbf written from a STEP.

Every prototype the view places is a part with the document's name, colour, face colours,
materials and element names; every assembly node of the view's tree is an assembly of its
own here, each component placed in its parent's frame. A part read from a STEP this engine
did not write takes the geometry key a build would give it, so an xbf of it caches like any.
The mechanism is the document's, whole, and so are its animations (``animations.record``): the
tree's occurrences are the view's, so their paths are the ones the tracks name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["tree_of", "write_xbf"]


def _material(value: Any) -> Any:
    from cadgen.engine.document import material_from_json

    return material_from_json(value)


def _names(prototype: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {"table": {}}
    for kind, field in (("faces", "faceNames"), ("edges", "edgeNames"), ("vertices", "vertexNames")):
        given = {int(ordinal): text for ordinal, text in (prototype.get(field) or {}).items()}
        found[kind] = [given.get(ordinal) for ordinal in range(1, max(given, default=0) + 1)]
    return found


def _located(matrix: np.ndarray) -> Any:
    """A component's placement, always a location of its own -- an identity one too, as a
    build's components are (``moved`` to the origin): a component placed by the empty
    location is the very shape of its prototype, and the shape tool and the STEP writer
    then take the one for the other (a STEP's occurrence names come out shifted)."""
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    trsf = gp_Trsf()
    trsf.SetValues(*(float(matrix[row, column]) for row in range(3) for column in range(4)))
    return TopLoc_Location(trsf)


def tree_of(view: Any) -> Any:
    """The ``document.Tree`` of a view (see the module docstring)."""
    from cadgen.engine import document

    source = view.source
    parts: dict[int, Any] = {}
    order: list = []

    def part(index: int) -> Any:
        found = parts.get(index)
        if found is None:
            prototype = view.prototypes[index]
            shape = source.shapes[prototype["key"]]
            if isinstance(shape, (bytes, bytearray)):
                from cadgen.engine.mesh import read_shape

                shape = read_shape(shape)
            key = prototype["key"]
            if source.foreign:
                shape = document.direct(shape)
                key = document.geometry_key(shape)
            found = parts[index] = document.Part(
                shape, prototype["name"], tuple(prototype["color"]) if prototype.get("color") else None,
                {int(ordinal): tuple(rgba) for ordinal, rgba in (prototype.get("faceColors") or {}).items()},
                key, _names(prototype), material=_material(prototype.get("material")),
                face_materials={int(ordinal): _material(given)
                                for ordinal, given in (prototype.get("faceMaterials") or {}).items() if given})
            order.append(found)
        return found

    def world(occurrence: tuple[int, ...]) -> np.ndarray:
        found = source.world(occurrence)
        return np.eye(4) if found is None else found

    def leaf(node: dict[str, Any], parent: np.ndarray) -> Any:
        instance = source.structure["instances"][node["instance"]]
        local = np.linalg.inv(parent) @ view.matrices[node["instance"]]
        color = tuple(instance["color"]) if instance.get("color") else None
        return document.Component(part(node["prototype"]), _located(local), node["name"], color)

    def assembly(node: dict[str, Any], occurrence: tuple[int, ...], frame: np.ndarray) -> Any:
        made = document.Assembly(node["name"])
        for at, child in enumerate(node["children"]):
            if "children" in child:
                below = world(occurrence + (at,))
                made.components.append(document.Component(assembly(child, occurrence + (at,), below),
                                                          _located(np.linalg.inv(frame) @ below), child["name"], None))
            else:
                made.components.append(leaf(child, frame))
        order.append(made)
        return made

    if "children" in view.tree:
        root = assembly(view.tree, (), np.eye(4))
    else:
        component = leaf(view.tree, np.eye(4))
        if np.allclose(view.matrices[view.tree["instance"]], np.eye(4), rtol=0, atol=1e-12) and component.color is None:
            root = component.prototype
        else:
            root = document.Assembly(view.tree["name"], [component])
            order.append(root)
    tree = document.Tree(root, order, list(parts.values()), ("exported", view.name))
    tree.mechanism = source.mechanism
    tree.animations = source.animations
    return tree


def write_xbf(view: Any, path: Path) -> None:
    """The view as an xbf of its own, saved atomically (``document.save``)."""
    from cadgen.engine import document

    doc = document.to_xcaf(tree_of(view))
    document.save(doc, Path(path), compare=True)
