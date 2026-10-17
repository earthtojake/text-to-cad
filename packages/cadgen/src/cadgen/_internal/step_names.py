"""The names a STEP file carries: each component's part key, on its product, and each
face's and edge's name, on the entity the file writes for it (README law 20).

What one component is named by is a :class:`ComponentNames`: its part key and, per
element ordinal (``TopExp.MapShapes_s`` of the unlocated component, the order its lineage
counts by), each face's and edge's name or None. The writer names an XCAF definition's
faces and edges on sub-shape labels -- or, where the component is itself one face or edge,
in the definition's ``Element`` property -- and puts the part key in its ``Description``
property; once OCCT has transferred the document, :func:`write_names` writes each name as
the name of the entity written for that face or edge (an ADVANCED_FACE, an EDGE_CURVE, the
GEOMETRIC_CURVE_SET of a free edge), and the key as its PRODUCT's description. A reader
takes them back from the same places: each named entity through the transfer's own map
from entities to the shapes it made of them (:func:`read_file_names`), and a product's
description from its label's properties (product metadata); :func:`read_component_names`
turns them into a component's names by the read shape's own ordinals. Nothing here
measures geometry: a name travels with the entity it was written on, so every reader of the
file gets the same names from the file alone. A reader's ordinals are its own -- OCCT
rebuilds each wire as it reads, so an edge's ordinal does not survive -- and a name is what
finds an element again, never its ordinal.

OCCT rebuilds every face on an indirect (left-handed) elementary surface before it writes
it, and every edge of such a face with it (``ToSTEP``'s DirectFaces), and a rebuilt element
no longer finds the name it was given. A named component is rebuilt first
(:func:`direct_faces`), so what the writer is given is what it writes, and its file is the
unnamed component's, byte for byte, but for the names.

What a file cannot name is known by construction (:func:`unnameable`): STEP has no entity
for a degenerate edge (a sphere's pole, a cone's apex), OCCT writes a face bounded by one
seam alone (a whole sphere) with its natural bounds and no edges, and a free wire as one
curve set with no entity per edge. The writer names none of those and every other face and
edge; a verifier expects exactly that. Named export never fails where plain export
succeeds: a name the transfer gave no entity, or a key whose product it did not map, is
not written, which verifying the file reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

# A part key: a sha256 digest, versioned as the store versions its keys (``<digest>-v<n>``).
# A product's description is read as one only when it is spelled so, which no free-text
# description is.
PART_KEY_PATTERN = r"[0-9a-f]{64}-v[1-9][0-9]*"
_PART_KEY = re.compile(PART_KEY_PATTERN)
# The label properties: the one OCCT's reader fills from a product's description, which
# :func:`write_names` writes a product's description from; and the name of the element a
# definition's shape itself is (a component that is one face or one edge).
DESCRIPTION = "Description"
ELEMENT = "Element"


def is_part_key(value: object) -> bool:
    """Whether ``value`` is spelled as a part key."""
    return isinstance(value, str) and _PART_KEY.fullmatch(value) is not None


@dataclass(frozen=True)
class ComponentNames:
    """What one component is named by: its part key and each face's and edge's name, by
    its ordinal in ``TopExp.MapShapes_s`` of the unlocated component (None where an
    element has no name). An empty tuple names none of that kind."""

    part: str | None = None
    faces: tuple[str | None, ...] = ()
    edges: tuple[str | None, ...] = ()


def _elements(shape: Any, kind: str) -> Any:
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE if kind == "face" else TopAbs_EDGE, found)
    return found


def unnameable(shape: Any) -> tuple[frozenset[int], frozenset[int]]:
    """The ordinals of the faces and of the edges of the unlocated component ``shape`` that
    no STEP file names, by construction: a degenerate edge, which STEP has no entity for;
    every edge of a wire that is, degenerate edges aside, one seam of its face (a whole
    sphere's), which OCCT writes with its natural bounds and no edges; and every edge of a
    wire that bounds no face, which OCCT writes as one curve set with no entity per edge.
    Every face is named."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    edges = _elements(shape, "edge")
    unnamed = {ordinal for ordinal in range(1, edges.Extent() + 1)
               if BRep_Tool.Degenerated_s(TopoDS.Edge_s(edges.FindKey(ordinal)))}
    bounding = TopTools_IndexedMapOfShape()
    faces = _elements(shape, "face")
    for face_ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face_s(faces.FindKey(face_ordinal))
        wires = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(face, TopAbs_WIRE, wires)
        for wire_ordinal in range(1, wires.Extent() + 1):
            wire = wires.FindKey(wire_ordinal)
            bounding.Add(wire)
            in_wire = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(wire, TopAbs_EDGE, in_wire)
            real = [TopoDS.Edge_s(in_wire.FindKey(index)) for index in range(1, in_wire.Extent() + 1)
                    if not BRep_Tool.Degenerated_s(TopoDS.Edge_s(in_wire.FindKey(index)))]
            if len(real) == 1 and BRep_Tool.IsClosed_s(real[0], face):
                unnamed.update(edges.FindIndex(in_wire.FindKey(index)) for index in range(1, in_wire.Extent() + 1))
    wires = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_WIRE, wires)
    for wire_ordinal in range(1, wires.Extent() + 1):
        wire = wires.FindKey(wire_ordinal)
        if bounding.Contains(wire):
            continue
        in_wire = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(wire, TopAbs_EDGE, in_wire)
        unnamed.update(edges.FindIndex(in_wire.FindKey(index)) for index in range(1, in_wire.Extent() + 1))
    unnamed.discard(0)
    return frozenset(), frozenset(unnamed)


def _checked(names: ComponentNames, shape: Any) -> list[tuple[str, Any, tuple[str | None, ...]]]:
    """Each kind ``names`` names, with the elements of ``shape`` it names them by; ValueError
    for names that do not fit ``shape``: a part key not spelled as one, a name not of its
    kind or given twice, or a kind not named one name (or None) per element."""
    from cadgen.cad_ref_syntax import is_element_name

    if names.part is not None and not is_part_key(names.part):
        raise ValueError(f"{names.part!r} is not a part key")
    named = []
    for kind, given in (("face", names.faces), ("edge", names.edges)):
        if not given:
            continue
        elements = _elements(shape, kind)
        if len(given) != elements.Extent():
            raise ValueError(f"{len(given)} {kind} names for a component of {elements.Extent()} {kind}s")
        present = [name for name in given if name is not None]
        wrong = next((name for name in present if not is_element_name(name, kind)), None)
        if wrong is not None:
            raise ValueError(f"{wrong!r} is not a {kind} name")
        if len(set(present)) != len(present):
            raise ValueError(f"a {kind} name is given twice")
        named.append((kind, elements, given))
    return named


def direct_faces(shape: Any) -> tuple[Any, Callable[[Any], Any] | None]:
    """``shape`` with every face on an indirect elementary surface rebuilt on a direct one,
    as OCCT's STEP writer rebuilds it before it writes it, and the map from each sub-shape of
    ``shape`` to the one that stands for it in the result; ``(shape, None)`` when no face
    needs it, which is every shape not mirrored, or when the rebuild fails (OCCT then
    rebuilds those faces itself, and their names do not reach the file)."""
    from OCP.BRepTools import BRepTools_Modifier
    from OCP.ShapeCustom import ShapeCustom_DirectModification
    from OCP.TopAbs import TopAbs_FORWARD

    try:
        forward = shape.Oriented(TopAbs_FORWARD)
        modifier = BRepTools_Modifier(forward, ShapeCustom_DirectModification())
        if not modifier.IsDone():
            return shape, None
        result = modifier.ModifiedShape(forward)
    except Exception:  # noqa: BLE001 - a component the kernel cannot rebuild is written as it is
        return shape, None
    if result.IsSame(forward):
        return shape, None
    return result.Oriented(shape.Orientation()), modifier.ModifiedShape


def name_definition(shape_tool: Any, label: Any, shape: Any, names: ComponentNames,
                    replaced: Callable[[Any], Any] | None = None) -> None:
    """Name what the XCAF definition ``label`` holds as ``names`` says: each named face and
    edge of ``shape`` (the component as given, whose ordinals ``names`` counts by) on a
    sub-shape label of the element that stands for it in the definition (``replaced``,
    :func:`direct_faces`'s map, where the component was rebuilt) -- or in the definition's
    ``Element`` property, where that element is the definition's shape itself -- and the part
    key as the definition's description. What no file can name (:func:`unnameable`) is left
    unnamed. ValueError for names that do not fit ``shape``, before anything is named."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    named = _checked(names, shape)
    held = XCAFDoc_ShapeTool.GetShape_s(label)
    if named:
        _faces, unnamed_edges = unnameable(shape)
    for kind, elements, given in named:
        for ordinal, name in enumerate(given, start=1):
            if name is None or (kind == "edge" and ordinal in unnamed_edges):
                continue
            element = elements.FindKey(ordinal)
            target = element if replaced is None else replaced(element)
            if target.IsSame(held):
                shape_tool.GetNamedProperties(label, True).SetString(
                    TCollection_ExtendedString(ELEMENT), TCollection_ExtendedString(name))
                continue
            sub = shape_tool.AddSubShape(label, target)
            if not sub.IsNull():
                TDataStd_Name.Set_s(sub, TCollection_ExtendedString(name))
    if names.part is not None:
        shape_tool.GetNamedProperties(label, True).SetString(
            TCollection_ExtendedString(DESCRIPTION), TCollection_ExtendedString(names.part)
        )


def write_names(step_writer: Any, doc: Any) -> None:
    """After ``doc`` is transferred by ``step_writer`` (a ``STEPControl_Writer``), what each
    of its part definitions names: each named face's and edge's name on the STEP entity
    written for it, and the definition's ``Description`` property as the description of the
    PRODUCT it was written as. OCCT writes neither as a file needs it: it leaves a product's
    description empty, and its own sub-shape pass (``write.stepcaf.subshapes.name``) names
    the item of every named label it can map, so an occurrence's or a group's name lands on
    the body it places. A document that names nothing is written as it always was, and a
    name or key the transfer gave nothing to carry it is not written.

    A definition's product is the one whose shape representation holds the STEP item of
    the definition's shape -- the shape itself, or the first sub-shape of it the transfer
    mapped (a compound's first solid): its MANIFOLD_SOLID_BREP, its SHELL_BASED_SURFACE_MODEL
    or one of that model's faces, or its GEOMETRIC_CURVE_SET -- else, for a compound that
    holds no such item (an empty one), the product the transfer made its definition.
    OCP numbers no STEP entity (``Number`` answers 0), so the items are matched by the
    identity of their wrappers, which is one object for one entity while the wrapper lives."""
    from OCP.STEPConstruct import STEPConstruct
    from OCP.StepShape import StepShape_ShapeDefinitionRepresentation
    from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_ChildIterator, TDF_LabelSequence
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Iterator
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    finder = step_writer.WS().TransferWriter().FinderProcess()
    labels = TDF_LabelSequence()
    shape_tool.GetShapes(labels)
    key = TCollection_ExtendedString(DESCRIPTION)
    element_key = TCollection_ExtendedString(ELEMENT)

    def name_entity(shape: Any, name: str) -> None:
        item = STEPConstruct.FindEntity_s(finder, shape, TopLoc_Location())
        if item is not None:
            item.SetName(TCollection_HAsciiString(name))

    described = []
    for index in range(1, labels.Length() + 1):
        label = labels.Value(index)
        if not XCAFDoc_ShapeTool.IsSimpleShape_s(label):
            continue
        children = TDF_ChildIterator(label, False)
        while children.More():
            sub = children.Value()
            children.Next()
            # IsAttribute first: FindAttribute crashes in this OCP build where the attribute is absent.
            if not sub.IsAttribute(TDataStd_Name.GetID_s()):
                continue
            attribute = TDataStd_Name()
            sub.FindAttribute(TDataStd_Name.GetID_s(), attribute)
            name_entity(XCAFDoc_ShapeTool.GetShape_s(sub), attribute.Get().ToExtString())
        properties = shape_tool.GetNamedProperties(label, False)
        if properties is None:
            continue
        if properties.HasString(element_key):
            name_entity(XCAFDoc_ShapeTool.GetShape_s(label), properties.GetString(element_key).ToExtString())
        if properties.HasString(key):
            described.append((XCAFDoc_ShapeTool.GetShape_s(label), properties.GetString(key).ToExtString()))
    if not described:
        return

    holders: dict[int, tuple[Any, Any]] = {}
    representations = step_writer.Model().Entities()
    representations.SelectType(StepShape_ShapeDefinitionRepresentation.get_type_descriptor_s(), True)
    representations.Start()
    while representations.More():
        definition = representations.Value()
        representations.Next()
        product = _product(definition)
        if product is None:
            continue
        items = definition.UsedRepresentation().Items()
        for index in range(1, items.Length() + 1):
            item = items.Value(index)
            holders[id(item)] = (item, product)
            if item.DynamicType().Name() == "StepShape_ShellBasedSurfaceModel":
                boundary = item.SbsmBoundary()
                for shell_index in range(1, boundary.Length() + 1):
                    faces = boundary.Value(shell_index).Value().CfsFaces()
                    for face_index in range(1, faces.Length() + 1):
                        face = faces.Value(face_index)
                        holders[id(face)] = (face, product)

    for shape, description in described:
        product = None
        pending = [shape]
        while pending:
            current = pending.pop()
            item = STEPConstruct.FindEntity_s(finder, current, TopLoc_Location())
            held = holders.get(id(item)) if item is not None else None
            if held is not None:
                product = held[1]
                break
            children = []
            iterator = TopoDS_Iterator(current)
            while iterator.More():
                children.append(iterator.Value())
                iterator.Next()
            pending.extend(reversed(children))
        if product is None and shape.ShapeType() == TopAbs_COMPOUND:
            product = _compound_product(step_writer, shape)
        if product is not None:
            product.SetDescription(TCollection_HAsciiString(description))


def _compound_product(step_writer: Any, shape: Any) -> Any:
    """The PRODUCT the transfer made of the compound ``shape``'s definition, found through the
    product definition it bound the compound to, or None. Only a compound is looked up so:
    for any other shape ``FindTarget`` would add a SHAPE_ASPECT to the model."""
    from OCP.STEPConstruct import STEPConstruct_ValidationProps
    from OCP.StepRepr import StepRepr_CharacterizedDefinition, StepRepr_RepresentationContext

    target = StepRepr_CharacterizedDefinition()
    found = STEPConstruct_ValidationProps(step_writer.WS()).FindTarget(
        shape, target, StepRepr_RepresentationContext(), False)
    value = target.Value() if found else None
    if value is None or value.DynamicType().Name() != "StepRepr_ProductDefinitionShape":
        return None
    for step in ("Definition", "ProductDefinition", "Formation", "OfProduct"):
        value = getattr(value, step)()
        if value is None:
            return None
    return value


def _product(definition: Any) -> Any:
    """The PRODUCT a SHAPE_DEFINITION_REPRESENTATION gives a shape, or None for one that
    defines no product's shape."""
    for step in ("Definition", "PropertyDefinition", "Definition", "ProductDefinition", "Formation", "OfProduct"):
        if definition is None:
            return None
        definition = getattr(definition, step)()
    return definition


@dataclass(frozen=True)
class FileNames:
    """Each element a read STEP file names: the shapes a reader made of the named entities,
    and each one's name, by its index in ``elements`` (a ``TopTools_IndexedMapOfShape``)."""

    elements: Any
    names: tuple[str, ...]

    def name_of(self, element: Any) -> str | None:
        index = self.elements.FindIndex(element)
        return self.names[index - 1] if index else None


def read_file_names(reader: Any) -> FileNames | None:
    """Every face and edge name a STEP file carries, once ``reader`` (a
    ``STEPCAFControl_Reader``) has transferred it: each ADVANCED_FACE, EDGE_CURVE and
    GEOMETRIC_CURVE_SET (a free edge's) named as an element of its kind, mapped to the face
    or edge the transfer made of it -- the faces of an internal void and a free edge as
    well, which XCAF's sub-shape expansion does not reach. A name that is not an element
    name is another writer's, and the first name an element is given is its name. None for
    a file that names no element."""
    from OCP.STEPConstruct import STEPConstruct
    from OCP.StepShape import StepShape_EdgeCurve, StepShape_FaceSurface, StepShape_GeometricCurveSet
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopTools import TopTools_IndexedMapOfShape

    from cadgen.cad_ref_syntax import is_element_name

    step = reader.Reader()
    model = step.Model()
    process = step.WS().TransferReader().TransientProcess()
    if model is None or process is None:
        return None
    elements = TopTools_IndexedMapOfShape()
    names: list[str] = []
    for kind, entity_type, shape_kind in (("face", StepShape_FaceSurface, TopAbs_FACE),
                                          ("edge", StepShape_EdgeCurve, TopAbs_EDGE),
                                          ("edge", StepShape_GeometricCurveSet, TopAbs_EDGE)):
        entities = model.Entities()
        entities.SelectType(entity_type.get_type_descriptor_s(), True)
        entities.Start()
        while entities.More():
            entity = entities.Value()
            entities.Next()
            text = entity.Name()
            if text is None or text.Length() == 0:
                continue
            name = text.ToCString()
            if not is_element_name(name, kind):
                continue
            element = _only(STEPConstruct.FindShape_s(process, entity), shape_kind)
            if element is None or elements.Contains(element):
                continue
            elements.Add(element)
            names.append(name)
    return FileNames(elements, tuple(names)) if names else None


def _only(shape: Any, kind: Any) -> Any:
    """``shape`` where it is of ``kind``, else its one element of ``kind``, else None."""
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    if shape is None or shape.IsNull():
        return None
    if shape.ShapeType() == kind:
        return shape
    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, found)
    return found.FindKey(1) if found.Extent() == 1 else None


def read_component_names(shape_tool: Any, label: Any, shape: Any,
                         file_names: FileNames | None = None) -> ComponentNames | None:
    """What a read document names the component ``label`` defines: its product's
    description where it is spelled as a part key, and each face and edge the file names
    (``file_names``, :func:`read_file_names`) -- or, for a document no file was read into,
    its sub-shape labels and ``Element`` property name -- by its ordinal in ``shape`` (the
    label's shape). A name that is not an element name of its element's kind is a name some
    other writer gave, not one of these. None when the document names nothing of it."""
    from OCP.TCollection import TCollection_ExtendedString

    part = None
    properties = shape_tool.GetNamedProperties(label, False)
    key = TCollection_ExtendedString(DESCRIPTION)
    if properties is not None and properties.HasString(key):
        description = properties.GetString(key).ToExtString()
        part = description if is_part_key(description) else None

    names: dict[str, tuple[str | None, ...]] = {}
    for kind in ("face", "edge"):
        elements = _elements(shape, kind)
        if file_names is not None:
            given = tuple(file_names.name_of(elements.FindKey(ordinal)) for ordinal in range(1, elements.Extent() + 1))
        else:
            given = _labelled_names(shape_tool, label, shape, kind, elements, properties)
        if any(name is not None for name in given):
            names[kind] = given
    if part is None and not names:
        return None
    return ComponentNames(part=part, faces=names.get("face", ()), edges=names.get("edge", ()))


def _labelled_names(shape_tool: Any, label: Any, shape: Any, kind: str, elements: Any,
                    properties: Any) -> tuple[str | None, ...]:
    """The names of ``kind`` an XCAF document gives ``label``'s elements: on sub-shape
    labels, and in the ``Element`` property for the element the label's shape itself is."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_ChildIterator
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

    from cadgen.cad_ref_syntax import is_element_name

    kinds = {TopAbs_FACE: "face", TopAbs_EDGE: "edge"}
    given: list[str | None] = [None] * elements.Extent()
    labelled = []
    children = TDF_ChildIterator(label, False)
    while children.More():
        sub = children.Value()
        children.Next()
        # IsAttribute first: FindAttribute crashes in this OCP build where the attribute is absent.
        if not sub.IsAttribute(TDataStd_Name.GetID_s()):
            continue
        attribute = TDataStd_Name()
        sub.FindAttribute(TDataStd_Name.GetID_s(), attribute)
        labelled.append((attribute.Get().ToExtString(), shape_tool.GetShape_s(sub)))
    element_key = TCollection_ExtendedString(ELEMENT)
    if properties is not None and properties.HasString(element_key):
        labelled.append((properties.GetString(element_key).ToExtString(), shape))
    for name, element in labelled:
        if element.IsNull() or kinds.get(element.ShapeType()) != kind or not is_element_name(name, kind):
            continue
        ordinal = elements.FindIndex(element)
        if ordinal:
            given[ordinal - 1] = name
    return tuple(given)
