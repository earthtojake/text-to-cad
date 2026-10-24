"""What a STEP file names the elements of one of its products: the names its sub-shape
labels carry (the reader's ``read.stepcaf.subshapes.name``), by kind and ordinal in the
product's own shape. ``document.read_step_shape`` puts them on each leaf it builds, under
``ELEMENT_NAMES``, and the trace prefers them to ordinals when it names what a file read
made (``trace._read_structure``)."""

from __future__ import annotations

from typing import Any

__all__ = ["ELEMENT_NAMES", "names"]

# The attribute of a shape read from a STEP file holding its elements' names:
# ``{kind: {ordinal: name}}``, kinds 0 vertex, 1 edge, 2 face.
ELEMENT_NAMES = "xbf_element_names"


def names(label: Any, shape: Any, held: dict[Any, dict]) -> dict[int, dict[int, str]]:
    """The names product ``label``'s sub-shape labels give the elements of ``shape`` (its
    shape), by kind and ordinal: none where it has none. ``held`` keeps each product's,
    read once however often it is placed."""
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_LabelSequence, TDF_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    key = entry.ToCString()
    found = held.get(key)
    if found is not None:
        return found
    found = held[key] = {}
    subs = TDF_LabelSequence()
    XCAFDoc_ShapeTool.GetSubShapes_s(label, subs)
    if not subs.Length():
        return found
    kinds = {TopAbs_VERTEX: 0, TopAbs_EDGE: 1, TopAbs_FACE: 2}
    maps: dict[int, Any] = {}
    guid = TDataStd_Name.GetID_s()
    for at in range(1, subs.Length() + 1):
        sub = subs.Value(at)
        element = XCAFDoc_ShapeTool.GetShape_s(sub)
        kind = None if element.IsNull() else kinds.get(element.ShapeType())
        if kind is None or not sub.IsAttribute(guid):
            continue
        name = TDataStd_Name()
        if not sub.FindAttribute(guid, name):
            continue
        text = name.Get().ToExtString()
        if not text:
            continue
        elements = maps.get(kind)
        if elements is None:
            elements = maps[kind] = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, element.ShapeType(), elements)
        ordinal = elements.FindIndex(element)
        if ordinal:
            found.setdefault(kind, {})[ordinal] = text
    return found
