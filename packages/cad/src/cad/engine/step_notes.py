"""A STEP's general notes as AP242 writes them: what a drawing says of the whole part in its notes,
written by another system as properties of the part rather than as XCAF notes (Specify's, the
interview the ``specify`` skill runs, writes them so).

OCCT's XCAF reader keeps none of them: it reads a part's GD&T and its own notes, not a property's
words. So they are read here from the STEP itself, as the file is read (``document._read``), and kept
on the document (``NOTES_GUID``) for ``pmi.records_of_document``, which lists each as a general note
of the part, as the file says it and never guessed:

- ``material property`` (AP242's material designation): ``Material: Aluminium 6082-T6``;
- ``default tolerances``, its ``tolerance class``: ``General tolerance: ISO 2768-m``;
- ``surface_condition``, a surface texture parameter in micrometres: ``Surface finish: Ra 3.2``;
- ``semantic text``, each item by its name: ``Edges: Break sharp edges 0.2 max`` for an
  ``edge condition``, any other ``<Name>: <words>``.

The material is a note only beside the others: a file that declares a material and nothing else (OCCT's
writer declares one for every part with a material, this engine's STEP export among its users) has
its material as the part's, and no notes. A file without these properties is not looked through: its
bytes are asked first, since walking a STEP's entities from Python costs about a quarter of a
millisecond each.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NOTES_GUID = "7b1f3e9a-2c64-4d58-9e0b-5a8c1d6f2e47"
_MARKS = (b"'material property'", b"'default tolerances'", b"'surface_condition'", b"'semantic text'")
# A semantic text item's name as a drawing's note says it.
_SEMANTIC = {"edge condition": "Edges"}


def _text(value: Any) -> str:
    return value.ToCString().strip() if value is not None else ""


def _descriptive(items: list[Any]) -> list[tuple[str, str]]:
    """Each descriptive item's name and words."""
    return [(_text(item.Name()), _text(item.Description())) for item in items
            if item is not None and item.DynamicType().Name() == "StepRepr_DescriptiveRepresentationItem"]


def _typed(model: Any, kind: Any) -> list[Any]:
    entities = model.Entities()
    entities.SelectType(kind, True)
    found = []
    entities.Start()
    while entities.More():
        found.append(entities.Value())
        entities.Next()
    return found


def _surface_finish(model: Any) -> list[str]:
    """Each surface texture parameter the file gives in micrometres, ``Ra 3.2``. OCCT holds a
    ``SURFACE_TEXTURE_REPRESENTATION`` as an entity it does not know: its items are read from it."""
    from OCP.StepData import StepData_UndefinedEntity

    found = []
    for entity in _typed(model, StepData_UndefinedEntity.get_type_descriptor_s()):
        if entity.StepType() != "SURFACE_TEXTURE_REPRESENTATION":
            continue
        content = entity.UndefinedContent()
        if content.NbParams() < 2 or not content.IsParamEntity(2):
            continue
        listed = content.ParamEntity(2)
        items = listed.UndefinedContent() if listed.DynamicType().Name() == "StepData_UndefinedEntity" else None
        if items is None:
            continue
        values = [items.ParamEntity(at) for at in range(1, items.NbParams() + 1) if items.IsParamEntity(at)]
        method = dict(_descriptive(values)).get("measuring method", "")
        for value in values:
            if not hasattr(value, "GetMeasureWithUnit") or _text(value.Name()) != "characteristic value":
                continue
            measure = value.GetMeasureWithUnit()
            unit = measure.UnitComponent().NamedUnit() if measure is not None else None
            prefix = unit.Prefix().name if unit is not None and hasattr(unit, "HasPrefix") and unit.HasPrefix() else ""
            if method and prefix.endswith("Micro"):
                found.append(f"{method} {measure.ValueComponent():g}")
    return found


def read_general_notes(reader: Any, path: Any) -> list[str]:
    """The general notes of the STEP ``reader`` read from ``path``, in the order above."""
    if not any(mark in Path(path).read_bytes() for mark in _MARKS):
        return []
    from OCP.StepRepr import StepRepr_PropertyDefinitionRepresentation

    model = reader.ChangeReader().Model()
    material, tolerance, semantic = [], [], []
    for held in _typed(model, StepRepr_PropertyDefinitionRepresentation.get_type_descriptor_s()):
        definition = held.Definition().PropertyDefinition() if held.Definition() is not None else None
        represented = held.UsedRepresentation()
        if definition is None or represented is None:
            continue
        name = _text(definition.Name())
        items = _descriptive([represented.ItemsValue(at) for at in range(1, represented.NbItems() + 1)])
        if name == "material property":
            material += [words or item for item, words in items[:1]]
        elif name == "default tolerances":
            tolerance += [words for item, words in items if item == "tolerance class" and words]
        elif name == "semantic text":
            semantic += [f"{_SEMANTIC.get(item, item[:1].upper() + item[1:])}: {words}" for item, words in items if words]
    finish = _surface_finish(model) if b"'surface_condition'" in Path(path).read_bytes() else []
    if not (tolerance or finish or semantic):
        # A material alone is the part's material, not a drawing's notes: OCCT's writer (this engine's
        # STEP export among its users) declares one for every part that has a material.
        return []
    return ([f"Material: {named}" for named in material] + [f"General tolerance: {named}" for named in tolerance]
            + [f"Surface finish: {named}" for named in finish] + semantic)


def keep(doc: Any, notes: list[str]) -> None:
    """``notes`` kept on the document for ``held``; none, nothing kept."""
    if not notes:
        return
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString

    TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(NOTES_GUID), TCollection_AsciiString(json.dumps(notes)))


def held(doc: Any) -> list[str]:
    """The general notes ``keep`` kept on ``doc``, or none."""
    from OCP.Standard import Standard_GUID
    from OCP.TDataStd import TDataStd_AsciiString

    guid, found = Standard_GUID(NOTES_GUID), TDataStd_AsciiString()
    main = doc.Main()
    if main.IsAttribute(guid) and main.FindAttribute(guid, found):
        return [str(note) for note in json.loads(found.Get().ToCString())]
    return []


def name_materials(doc: Any, notes: list[str]) -> int:
    """The part's material named as the file declares it (``material property``), where OCCT's reader
    took another property's words for it and gave it no density: returns how many it named.

    OCCT reads a material from a part's properties without telling them apart, so a file that also
    holds a property of its own on the part (Specify's characteristic numbers, its ``history``) read
    as a material of that name. Only a file that declares one material is named so: an assembly whose
    parts declare several is left as it was read."""
    declared = {note.split(": ", 1)[1] for note in notes if note.startswith("Material: ")}
    if len(declared) != 1:
        return 0
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TDF import TDF_ChildIterator
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_Material

    (name,) = declared
    named = 0
    children = TDF_ChildIterator(XCAFDoc_DocumentTool.MaterialTool_s(doc.Main()).Label())
    while children.More():
        material = XCAFDoc_Material()
        if children.Value().FindAttribute(XCAFDoc_Material.GetID_s(), material) and not material.GetDensity() > 0:
            # On the label: ``FindAttribute`` fills a copy, and setting the copy changes nothing.
            XCAFDoc_Material.Set_s(children.Value(), TCollection_HAsciiString(name), TCollection_HAsciiString(name),
                                   0.0, TCollection_HAsciiString(""), TCollection_HAsciiString(""))
            named += 1
        children.Next()
    return named
