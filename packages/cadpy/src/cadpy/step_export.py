from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from cadpy.step_scene import LoadedStepScene, load_step_scene_from_xcaf_doc, step_file_hash
from cadpy.step_metadata import TEXT_TO_CAD_GENERATOR, inject_text_to_cad_step_metadata


def _collect_assembly_mates(shape: Any) -> list[dict[str, Any]]:
    mates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        raw_mates = getattr(node, "assembly_mates", None)
        if isinstance(raw_mates, list):
            for raw_mate in raw_mates:
                if not isinstance(raw_mate, dict):
                    continue
                key = repr(raw_mate)
                if key in seen:
                    continue
                seen.add(key)
                mate = dict(raw_mate)
                mate_id = f"m{len(mates) + 1}"
                source_label = str(
                    mate.get("sourceLabel") or
                    mate.get("name") or
                    mate.get("label") or
                    mate.get("id") or
                    ""
                ).strip()
                mate["id"] = mate_id
                mate["label"] = mate_id
                if source_label and source_label != mate_id:
                    mate["sourceLabel"] = source_label
                mates.append(mate)
        for child in list(getattr(node, "children", []) or []):
            visit(child)

    visit(shape)
    return mates


def _attach_assembly_mates(scene: LoadedStepScene, shape: Any) -> LoadedStepScene:
    assembly_mates = _collect_assembly_mates(shape)
    if assembly_mates:
        scene.assembly_mates = assembly_mates
    return scene


def create_bin_xcaf_doc() -> Any:
    from OCP.BinXCAFDrivers import BinXCAFDrivers
    from build123d.exporters3d import (
        TCollection_ExtendedString,
        TDocStd_Document,
        UNITS_PER_METER,
        Unit,
        XCAFApp_Application,
        XCAFDoc_DocumentTool,
    )

    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    application = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(application)
    application.NewDocument(TCollection_ExtendedString("BinXCAF"), doc)
    application.InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1 / UNITS_PER_METER[Unit.MM])
    return doc


def _create_bin_xcaf_doc(to_export: Any) -> Any:
    import warnings

    from OCP.TopLoc import TopLoc_Location
    from build123d.exporters3d import (
        Compound,
        Curve,
        Part,
        PreOrderIter,
        Sketch,
        TCollection_ExtendedString,
        TDataStd_Name,
        TopExp_Explorer,
        XCAFDoc_ColorType,
        XCAFDoc_DocumentTool,
        ta,
    )

    doc = create_bin_xcaf_doc()
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    is_assembly = isinstance(to_export, Compound) and len(to_export.children) > 0
    shape_definitions: dict[int, object] = {}

    def set_label_name(label: object, name: str | None) -> None:
        if name and not label.IsNull():
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(str(name)))

    def set_label_color(label: object, color: object | None) -> None:
        if color is None or label.IsNull():
            return
        wrapped = getattr(color, "wrapped", None)
        if wrapped is None:
            return
        color_tool.SetColor(
            label,
            wrapped,
            XCAFDoc_ColorType.XCAFDoc_ColorSurf,
        )

    def shape_location(shape: object) -> object:
        wrapped = getattr(shape, "wrapped", None)
        if wrapped is None:
            return TopLoc_Location()
        location = getattr(wrapped, "Location", None)
        if not callable(location):
            return TopLoc_Location()
        try:
            return location()
        except Exception:
            return TopLoc_Location()

    def shape_without_location(shape: object) -> object:
        wrapped = getattr(shape, "wrapped", None)
        if wrapped is None:
            return shape
        located = getattr(wrapped, "Located", None)
        if not callable(located):
            return wrapped
        try:
            return located(TopLoc_Location())
        except Exception:
            return wrapped

    def shape_definition_for_tree(shape: object) -> object:
        key = id(shape)
        cached = shape_definitions.get(key)
        if cached is not None:
            return cached

        children = list(getattr(shape, "children", []) or [])
        if children:
            definition_label = shape_tool.NewShape()
            shape_definitions[key] = definition_label
            set_label_name(definition_label, getattr(shape, "label", None))
            set_label_color(definition_label, getattr(shape, "color", None))
            for child in children:
                child_definition = shape_definition_for_tree(child)
                child_component = shape_tool.AddComponent(
                    definition_label,
                    child_definition,
                    shape_location(child),
                )
                set_label_name(child_component, getattr(child, "label", None))
                set_label_color(child_component, getattr(child, "color", None))
            return definition_label

        definition_label = shape_tool.AddShape(shape_without_location(shape), False)
        shape_definitions[key] = definition_label
        set_label_name(definition_label, getattr(shape, "label", None))
        set_label_color(definition_label, getattr(shape, "color", None))
        return definition_label

    if is_assembly:
        shape_definition_for_tree(to_export)
        shape_tool.UpdateAssemblies()
        return doc

    shape_tool.AddShape(to_export.wrapped, is_assembly)

    for node in PreOrderIter(to_export):
        if not node.label and node.color is None:
            continue

        node_label = shape_tool.FindShape(node.wrapped, findInstance=False)
        sub_node_labels = []
        if node.color is not None and isinstance(node, Compound) and not node.children:
            sub_nodes = []
            if isinstance(node, Part):
                explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_SOLID)
            elif isinstance(node, Sketch):
                explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_FACE)
            elif isinstance(node, Curve):
                explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_EDGE)
            else:
                warnings.warn("Unknown Compound type, color not set", stacklevel=2)
                explorer = TopExp_Explorer()

            while explorer.More():
                sub_nodes.append(explorer.Current())
                explorer.Next()

            sub_node_labels = [
                shape_tool.FindShape(sub_node, findInstance=False)
                for sub_node in sub_nodes
            ]
        set_label_name(node_label, node.label)

        if node.color is not None:
            for label in [node_label] + sub_node_labels:
                set_label_color(label, node.color)

    shape_tool.UpdateAssemblies()
    return doc


def export_xcaf_doc_step_scene(
    doc: Any,
    output_path: Path,
    *,
    label: str | None = None,
    originating_system: str = "build123d",
    text_to_cad_entry_kind: str | None = None,
    source_path: str | None = None,
    source_hash: str | None = None,
    logger: object | None = None,
) -> LoadedStepScene:
    step_hash = write_xcaf_doc_step_file(
        doc,
        output_path,
        label=label,
        originating_system=originating_system,
        text_to_cad_entry_kind=text_to_cad_entry_kind,
        source_path=source_path,
        source_hash=source_hash,
        logger=logger,
    )
    with (logger.timed(f"load scene from XCAF {output_path.name}") if logger is not None else nullcontext()):
        return load_step_scene_from_xcaf_doc(
            output_path,
            doc,
            step_hash=step_hash,
        )


def write_xcaf_doc_step_file(
    doc: Any,
    output_path: Path,
    *,
    label: str | None = None,
    originating_system: str = "build123d",
    text_to_cad_entry_kind: str | None = None,
    source_path: str | None = None,
    source_hash: str | None = None,
    logger: object | None = None,
) -> str:
    from build123d.exporters3d import (
        APIHeaderSection_MakeHeader,
        IFSelect_ReturnStatus,
        IGESControl_Controller,
        Interface_Static,
        Message,
        Message_Gravity,
        PrecisionMode,
        STEPCAFControl_Controller,
        STEPCAFControl_Writer,
        STEPControl_Controller,
        STEPControl_StepModelType,
        TCollection_HAsciiString,
        XSControl_WorkSession,
    )

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    messenger = Message.DefaultMessenger_s()
    for printer in messenger.Printers():
        printer.SetTraceLevel(Message_Gravity(Message_Gravity.Message_Fail))

    session = XSControl_WorkSession()
    writer = STEPCAFControl_Writer(session, False)
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)

    header = APIHeaderSection_MakeHeader(writer.Writer().Model())
    if label:
        header.SetName(TCollection_HAsciiString(label))
    header.SetOriginatingSystem(
        TCollection_HAsciiString(TEXT_TO_CAD_GENERATOR if text_to_cad_entry_kind else originating_system)
    )

    STEPCAFControl_Controller.Init_s()
    STEPControl_Controller.Init_s()
    IGESControl_Controller.Init_s()
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    Interface_Static.SetIVal_s("write.precision.mode", PrecisionMode.AVERAGE.value)
    with (logger.timed(f"transfer XCAF to STEP model {output_path.name}") if logger is not None else nullcontext()):
        writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)

    with (logger.timed(f"write STEP file {output_path.name}") if logger is not None else nullcontext()):
        if writer.Write(os.fspath(output_path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise RuntimeError(f"Failed to write STEP file: {output_path}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"STEP export did not create {output_path}")
    if text_to_cad_entry_kind:
        with (logger.timed(f"inject STEP metadata {output_path.name}") if logger is not None else nullcontext()):
            inject_text_to_cad_step_metadata(
                output_path,
                entry_kind=text_to_cad_entry_kind,
                source_path=source_path,
                source_hash=source_hash,
            )
    return step_file_hash(output_path)


def export_build123d_step_scene(
    to_export: Any,
    output_path: Path,
    *,
    text_to_cad_entry_kind: str | None = None,
    source_path: str | None = None,
    source_hash: str | None = None,
) -> LoadedStepScene:
    doc = _create_bin_xcaf_doc(to_export)
    scene = export_xcaf_doc_step_scene(
        doc,
        output_path,
        label=getattr(to_export, "label", None),
        text_to_cad_entry_kind=text_to_cad_entry_kind,
        source_path=source_path,
        source_hash=source_hash,
    )
    return _attach_assembly_mates(scene, to_export)


def build_build123d_step_scene(
    to_export: Any,
    output_path: Path,
    *,
    source_kind: str = "step",
    source_hash: str | None = None,
) -> LoadedStepScene:
    doc = _create_bin_xcaf_doc(to_export)
    scene = load_step_scene_from_xcaf_doc(
        output_path,
        doc,
        source_kind=source_kind,
        source_hash=source_hash,
    )
    return _attach_assembly_mates(scene, to_export)
