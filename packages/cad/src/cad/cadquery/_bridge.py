"""A CadQuery value described portably, for the engine to make a document of in a kernel process of its own.

CadQuery's OCP (7.9) and the kernel's (8.0) cannot share a process, so ``model(value, name=...)`` in a
CadQuery program sends the engine a description, not an object: ``portable(value, name)`` answers the header
the engine's STEP reader answers for a file (``cad.engine.reader.describe``: ``products``, each a part with
its shape's index or an assembly with its components, and ``roots``, each a component placed by a location)
and one BinTools dump of every part's shape and every location (``cad.engine.reader.pack``), written by this
environment's OCP -- BinTools format 4, which OCCT 8.0 reads as 7.9 wrote it. The engine's kernel process
reads it back (``cad.engine.portable``) and makes the document as it makes one of any shape handed over.

What is described:

* a ``Shape`` (``cadquery.occ_impl.shapes``): one part, named by its ``label`` where it has one;
* a ``Workplane``: the shapes on its stack, one part (several make one compound); a stack with no shape
  (points, vectors, locations) is refused;
* a ``Sketch``: its faces, one part;
* an ``Assembly``: its tree. A node with children is an assembly product, its own shape (``obj``) a part
  component of it named as the node; a leaf with a shape is a part product. Names are the nodes' ``name``,
  colours their ``color`` (``toTuple()``: linear RGBA, as the document holds them), placements their
  ``loc`` as CadQuery solved them, relative to the parent, as the document's are.

Materials, element names and painted faces are none of CadQuery's; none is described. The header carries a
format marker (``cad.engine.portable.FORMAT``) and the count of shapes, which the reader checks first.
Importing this module imports no CadQuery and no OCP: ``is_cadquery`` and ``kind_of`` read type names alone,
and the OCP calls run only inside ``portable``, in the environment that holds the value.
"""

from __future__ import annotations

from typing import Any

__all__ = ["KINDS", "describe", "is_cadquery", "kind_of", "portable"]

#: The CadQuery classes a value is handed over as, by name, anywhere in its class's ancestry.
KINDS = ("Workplane", "Shape", "Sketch", "Assembly")


def kind_of(value: Any) -> str | None:
    """Which of ``KINDS`` ``value`` is, by its class's ancestry -- a class of that name whose module is
    CadQuery's -- or None for a value that is no CadQuery's."""
    for cls in type(value).__mro__:
        if cls.__name__ in KINDS and str(cls.__module__).split(".")[0] == "cadquery":
            return cls.__name__
    return None


def is_cadquery(value: Any) -> bool:
    """Whether ``value`` is a CadQuery ``Workplane``, ``Shape``, ``Sketch`` or ``Assembly`` (``kind_of``)."""
    return kind_of(value) is not None


def _topods(shape: Any, where: str) -> Any:
    found = getattr(shape, "wrapped", None)
    if found is None or found.IsNull():
        raise ValueError(f"{where}: the shape is empty")
    return found


def _shapes_of(value: Any, where: str) -> list[Any]:
    """The TopoDS shapes ``value`` holds: a ``Shape``'s own, a ``Workplane``'s stack's, a ``Sketch``'s faces."""
    kind = kind_of(value)
    if kind == "Shape":
        return [_topods(value, where)]
    if kind == "Workplane":
        held = [item for item in value.vals() if kind_of(item) == "Shape"]
        if not held:
            others = sorted({type(item).__name__ for item in value.vals()})
            what = f"holds {', '.join(others)}" if others else "is empty"
            raise ValueError(f"{where}: the Workplane's stack {what}, and no shape: end the chain on a solid, a face "
                             "or a compound")
        return [_topods(item, where) for item in held]
    if kind == "Sketch":
        faces = getattr(value, "_faces", None)
        if faces is None or getattr(faces, "wrapped", None) is None or faces.wrapped.IsNull():
            raise ValueError(f"{where}: the Sketch has no faces")
        return [faces.wrapped]
    raise TypeError(f"{where}: {type(value).__name__} holds no shape")


def _one(shapes: list[Any]) -> Any:
    """One TopoDS shape of ``shapes``: the shape itself, or a compound of several."""
    if len(shapes) == 1:
        return shapes[0]
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _rgba(color: Any) -> list[float] | None:
    """A CadQuery ``Color`` as the document's linear RGBA, or None for none."""
    if color is None:
        return None
    return [float(channel) for channel in color.toTuple()]


def describe(value: Any, name: str) -> tuple[dict[str, Any], list[Any], list[Any]]:
    """``value`` as the engine's reader describes a document: the header (``products``, ``roots``), the
    parts' TopoDS shapes and the components' ``TopLoc_Location`` placements, in the order the header indexes
    them (``cad.engine.reader.assemble`` reads the same). ``name`` names a part that has no name of its own.
    ``ValueError`` for a value with no shape in it."""
    from OCP.TopLoc import TopLoc_Location

    kind = kind_of(value)
    if kind is None:
        raise TypeError(f"model(value, name={name!r}): {type(value).__name__} is no CadQuery Workplane, Shape, Sketch "
                        "or Assembly")
    where = f"model(value, name={name!r})"
    products: list[dict[str, Any]] = []
    shapes: list[Any] = []
    locations: list[Any] = []

    def part(topods: Any, label: str, color: list[float] | None) -> int:
        products.append({"name": label, "color": color, "assembly": False, "shape": len(shapes), "names": {},
                         "material": None, "face_materials": {}, "paints": {}})
        shapes.append(topods)
        return len(products) - 1

    def placed(location: Any) -> int:
        locations.append(location)
        return len(locations) - 1

    def assembly(node: Any, path: str) -> int:
        """A CadQuery ``Assembly`` node as a product: a part where it is a leaf with a shape, else an assembly
        of its own shape (a part named as the node) and its children."""
        label = str(getattr(node, "name", "") or "")
        color = _rgba(getattr(node, "color", None))
        obj = getattr(node, "obj", None)
        children = list(getattr(node, "children", None) or ())
        if obj is not None and not children:
            return part(_one(_shapes_of(obj, f"{where}: {path}")), label, color)
        record: dict[str, Any] = {"name": label, "color": color, "assembly": True, "components": []}
        products.append(record)
        index = len(products) - 1
        components: list[dict[str, Any]] = []
        if obj is not None:
            components.append({"product": part(_one(_shapes_of(obj, f"{where}: {path}")), label, None), "name": "",
                               "color": None, "location": placed(TopLoc_Location())})
        for child in children:
            child_name = str(getattr(child, "name", "") or "")
            components.append({"product": assembly(child, f"{path}/{child_name}"), "name": "", "color": None,
                               "location": placed(child.loc.wrapped)})
        if not components:
            raise ValueError(f"{where}: {path} holds no shape")
        record["components"] = components
        return index

    if kind == "Assembly":
        root = assembly(value, str(getattr(value, "name", "") or name))
        roots = [{"product": root, "name": "", "color": None, "location": placed(value.loc.wrapped)}]
    else:
        label = str(getattr(value, "label", "") or "") if kind == "Shape" else ""
        root = part(_one(_shapes_of(value, where)), label or name, None)
        roots = [{"product": root, "name": "", "color": None, "location": placed(TopLoc_Location())}]
    return {"products": products, "roots": roots}, shapes, locations


def _kernel() -> str:
    """The OCP build this environment runs CadQuery on, in words (``cadquery-ocp 7.9.3``), for the header."""
    import importlib.metadata

    for distribution in ("cadquery-ocp", "cadquery-ocp-novtk"):
        try:
            return f"{distribution} {importlib.metadata.version(distribution)}"
        except importlib.metadata.PackageNotFoundError:
            continue
    return "OCP"


def portable(value: Any, name: str) -> tuple[dict[str, Any], bytes]:
    """``value`` handed over: the header -- ``describe``'s, with the format marker, the integration, the OCP
    build that wrote it and the counts of shapes and locations -- and the one BinTools dump of its shapes and
    locations (``cad.engine.reader.pack``), written by this environment's OCP."""
    from cad.engine import portable as wire
    from cad.engine.reader import pack

    header, shapes, locations = describe(value, name)
    header.update({"format": wire.FORMAT, "integration": "cadquery", "kernel": _kernel(), "shapes": len(shapes),
                   "locations": len(locations)})
    return header, pack(shapes, locations)
