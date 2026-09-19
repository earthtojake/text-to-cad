"""Canonical native selector ordinals, independent of display extraction."""
from __future__ import annotations


def shape_entities(shape):
    """The selector's sN decomposition: solids, else shells, else the shape."""
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer

    for kind in (TopAbs_SOLID, TopAbs_SHELL):
        found = []
        explorer = TopExp_Explorer(shape, kind)
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
        if found:
            return tuple(found)
    return (shape,)


def entity_map(shape, kind):
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    entities = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, {"face": TopAbs_FACE, "edge": TopAbs_EDGE, "vertex": TopAbs_VERTEX}[kind], entities)
    return entities
