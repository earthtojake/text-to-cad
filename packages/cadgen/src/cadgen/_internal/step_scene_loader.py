from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import time
from typing import Any

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_ColorRGBA
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_ChildIterator
from OCP.TDF import TDF_Label
from OCP.TDF import TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorCurv
from OCP.XCAFDoc import XCAFDoc_ColorGen
from OCP.XCAFDoc import XCAFDoc_ColorSurf
from OCP.XCAFDoc import XCAFDoc_ColorTool
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.XCAFDoc import XCAFDoc_ShapeTool

from cadgen._internal.step_hash import step_file_hash

from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode, _identity_transform_matrix


def _shape_hash(shape: Any) -> int:
    return hash(shape)


def _shape_location(topods_shape: object) -> object | None:
    location = getattr(topods_shape, "Location", None)
    if not callable(location):
        return None
    try:
        return location()
    except Exception:  # noqa: BLE001 - OCP Location() can raise; no location is the identity
        return None


def _compose_locations(parent_location: object | None, child_location: object | None) -> object | None:
    if parent_location is None:
        return child_location
    if child_location is None:
        return parent_location
    try:
        return parent_location.Multiplied(child_location)
    except Exception:  # noqa: BLE001 - OCP transform multiply can raise; the child location alone is a safe fallback
        return child_location


def _located_shape(topods_shape: object, location: object | None) -> object:
    if location is None:
        return topods_shape
    located = getattr(topods_shape, "Located", None)
    if not callable(located):
        return topods_shape
    try:
        return located(location)
    except Exception:  # noqa: BLE001 - OCP Located() can raise; keep the shape as-is
        return topods_shape


def _unlocated_shape(topods_shape: object) -> object:
    located = getattr(topods_shape, "Located", None)
    if not callable(located):
        return topods_shape
    try:
        return located(TopLoc_Location())
    except Exception:  # noqa: BLE001 - OCP Located() can raise; keep the shape unlocated
        return topods_shape


def _location_transform_matrix(location: object | None) -> tuple[float, ...]:
    if location is None:
        return _identity_transform_matrix()
    transformation = getattr(location, "Transformation", None)
    if not callable(transformation):
        return _identity_transform_matrix()
    try:
        trsf = transformation()
    except Exception:  # noqa: BLE001 - OCP Transformation() can raise; identity transform fallback
        return _identity_transform_matrix()
    rows: list[float] = []
    try:
        for row in range(1, 4):
            rows.extend(float(trsf.Value(row, column)) for column in range(1, 5))
    except Exception:  # noqa: BLE001 - OCP matrix reads can raise; identity transform fallback
        return _identity_transform_matrix()
    rows.extend((0.0, 0.0, 0.0, 1.0))
    return tuple(rows)


@lru_cache(maxsize=8192)
def _location_from_transform_matrix(transform: tuple[float, ...]) -> TopLoc_Location:
    from OCP.gp import gp_Trsf

    if len(transform) != 16:
        return TopLoc_Location()
    trsf = gp_Trsf()
    trsf.SetValues(
        transform[0],
        transform[1],
        transform[2],
        transform[3],
        transform[4],
        transform[5],
        transform[6],
        transform[7],
        transform[8],
        transform[9],
        transform[10],
        transform[11],
    )
    return TopLoc_Location(trsf)


def _xcaf_children(shape_tool: Any, label: object) -> list[object]:
    sequence = TDF_LabelSequence()
    shape_tool.GetComponents_s(label, sequence)
    if sequence.Length() > 0:
        return [sequence.Value(index) for index in range(1, sequence.Length() + 1)]
    return []


def _normalize_label_name(raw_name: object) -> str | None:
    if raw_name is None:
        return None
    text = " ".join(str(raw_name).split())
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("open cascade step translator"):
        return None
    if lowered in {"assembly", "solid", "compound", "compsolid", "shell", "face", "wire", "edge", "vertex"}:
        return None
    if text.isdigit():
        return None
    return text


def _label_name(label: object) -> str | None:
    # IsAttribute first, and it is not belt-and-braces: TDF_Label.FindAttribute SEGFAULTS in
    # this OCP build when the attribute is ABSENT, rather than returning false. The label
    # itself is valid (IsNull() is False) -- it simply carries no name.
    #
    # Any shape whose labels are not all named reaches this, which is every assembly built as
    # a plain `Compound(children=[...])` rather than through AssemblyHelper: XCAF creates a
    # child label per solid and leaves the unnamed ones without TDataStd_Name. A 3-solid
    # compound was enough. The crash is uncatchable -- SIGSEGV, no traceback, exit 139 -- so
    # it read as a hang or a mysterious kill rather than an unnamed label.
    if not label.IsAttribute(TDataStd_Name.GetID_s()):
        return None
    name = TDataStd_Name()
    if not label.FindAttribute(TDataStd_Name.GetID_s(), name):
        return None
    return _normalize_label_name(name.Get().ToExtString())


def _resolve_referred_label(shape_tool: Any, label: object) -> object:
    if not shape_tool.IsReference_s(label):
        return label
    referred = TDF_Label()
    if shape_tool.GetReferredShape_s(label, referred):
        return referred
    return label


def _color_tuple(color: Quantity_ColorRGBA) -> ColorRGBA:
    rgb = color.GetRGB()
    return (
        float(rgb.Red()),
        float(rgb.Green()),
        float(rgb.Blue()),
        float(color.Alpha()),
    )


def _color_from_label(color_tool: Any, label: object) -> ColorRGBA | None:
    color = Quantity_ColorRGBA()
    for color_type in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
        try:
            if XCAFDoc_ColorTool.GetColor_s(label, color_type, color):
                return _color_tuple(color)
        except Exception:  # noqa: BLE001 - OCP color reads can raise per color type; try the next type
            continue
    return None


def _color_from_shape(color_tool: Any, shape: object) -> ColorRGBA | None:
    if getattr(shape, "IsNull", lambda: True)():
        return None
    color = Quantity_ColorRGBA()
    for color_type in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
        try:
            if color_tool.GetColor(shape, color_type, color):
                return _color_tuple(color)
        except Exception:  # noqa: BLE001 - OCP color reads can raise per color type; try the next type
            pass
        try:
            if color_tool.GetInstanceColor(shape, color_type, color):
                return _color_tuple(color)
        except Exception:  # noqa: BLE001 - OCP color reads can raise per color type; try the next type
            pass
    return None


def _face_color_map_from_label(shape_tool: Any, color_tool: Any, label: object) -> dict[int, ColorRGBA]:
    face_colors: dict[int, ColorRGBA] = {}

    def collect(colored_label: object) -> None:
        label_color = _color_from_label(color_tool, colored_label)
        if label_color is not None:
            try:
                shape = shape_tool.GetShape_s(colored_label)
            except Exception:  # noqa: BLE001 - OCP label-to-shape reads can raise; a missing shape is skipped
                shape = None
            if shape is not None and not shape.IsNull():
                explorer = TopExp_Explorer(shape, TopAbs_FACE)
                while explorer.More():
                    face_colors[_shape_hash(TopoDS.Face_s(explorer.Current()))] = label_color
                    explorer.Next()
        iterator = TDF_ChildIterator(colored_label, False)
        while iterator.More():
            collect(iterator.Value())
            iterator.Next()

    collect(label)
    return face_colors


def _xcaf_children(shape_tool: Any, label: object, resolved_label: object) -> list[object]:
    children = TDF_LabelSequence()
    has_children = XCAFDoc_ShapeTool.GetComponents_s(label, children, False)
    if (not has_children or children.Length() <= 0) and resolved_label != label:
        children = TDF_LabelSequence()
        has_children = XCAFDoc_ShapeTool.GetComponents_s(resolved_label, children, False)
    if not has_children or children.Length() <= 0:
        return []
    return [children.Value(index) for index in range(1, children.Length() + 1)]


def _load_occurrence_tree(
    step_path: Path,
) -> tuple[
    list[OccurrenceNode],
    dict[int, Any],
    dict[int, str | None],
    dict[int, ColorRGBA],
    dict[int, dict[int, ColorRGBA]],
    Any | None,
]:
    app = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(app)
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    app.NewDocument(TCollection_ExtendedString("BinXCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    for mode_name in ("SetMatMode", "SetLayerMode", "SetSHUOMode"):
        mode = getattr(reader, mode_name, None)
        if callable(mode):
            mode(True)
    read_status = reader.ReadFile(str(step_path))
    if int(read_status) != int(IFSelect_RetDone):
        return (*_load_fallback_occurrence_tree(step_path), None)
    if not reader.Transfer(doc):
        return (*_load_fallback_occurrence_tree(step_path), None)

    loaded = _load_occurrence_tree_from_xcaf_doc(step_path, doc)
    if loaded is None:
        return (*_load_fallback_occurrence_tree(step_path), None)
    return (*loaded, doc)


def _load_occurrence_tree_from_xcaf_doc(
    step_path: Path,
    doc: Any,
) -> tuple[
    list[OccurrenceNode],
    dict[int, Any],
    dict[int, str | None],
    dict[int, ColorRGBA],
    dict[int, dict[int, ColorRGBA]],
] | None:

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    if free_labels.Length() <= 0:
        return None

    prototypes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_colors: dict[int, ColorRGBA] = {}
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}

    def collect(label: object, *, path: tuple[int, ...], parent_location: object | None = None) -> OccurrenceNode | None:
        resolved_label = _resolve_referred_label(shape_tool, label)
        instance_shape = shape_tool.GetShape_s(label)
        resolved_shape = shape_tool.GetShape_s(resolved_label)
        base_shape = instance_shape if not instance_shape.IsNull() else resolved_shape
        local_location = _shape_location(base_shape)
        current_location = _compose_locations(parent_location, local_location)
        children = _xcaf_children(shape_tool, label, resolved_label)
        name = _label_name(label) or _label_name(resolved_label)
        source_name = _label_name(resolved_label) or name
        occurrence_color = (
            _color_from_label(color_tool, label)
            or _color_from_shape(color_tool, instance_shape)
            or _color_from_label(color_tool, resolved_label)
            or _color_from_shape(color_tool, resolved_shape)
        )
        prototype_key: int | None = None
        if not children and not resolved_shape.IsNull():
            prototype_shape = _unlocated_shape(resolved_shape)
            prototype_key = _shape_hash(prototype_shape)
            prototypes.setdefault(prototype_key, prototype_shape)
        elif not children and not base_shape.IsNull():
            prototype_shape = _unlocated_shape(base_shape)
            prototype_key = _shape_hash(prototype_shape)
            prototypes.setdefault(prototype_key, prototype_shape)
        if prototype_key is not None:
            prototype_names.setdefault(prototype_key, source_name or name)
            prototype_color = _color_from_label(color_tool, resolved_label) or _color_from_shape(color_tool, resolved_shape)
            if prototype_color is not None:
                prototype_colors.setdefault(prototype_key, prototype_color)
            face_colors = _face_color_map_from_label(shape_tool, color_tool, resolved_label)
            if label != resolved_label:
                face_colors.update(_face_color_map_from_label(shape_tool, color_tool, label))
            if face_colors:
                prototype_face_colors.setdefault(prototype_key, {}).update(face_colors)
        child_nodes = [
            child_node
            for index, child in enumerate(children, start=1)
            if (child_node := collect(child, path=(*path, index), parent_location=current_location)) is not None
        ]
        if prototype_key is None and not child_nodes:
            return None
        return OccurrenceNode(
            path=path,
            name=name,
            source_name=source_name,
            transform=_location_transform_matrix(current_location),
            prototype_key=prototype_key,
            local_transform=_location_transform_matrix(local_location),
            color=occurrence_color,
            location=current_location,
            children=child_nodes,
        )

    roots = [
        node
        for index in range(1, free_labels.Length() + 1)
        if (node := collect(free_labels.Value(index), path=(index,))) is not None
    ]
    if not roots:
        return None
    return roots, prototypes, prototype_names, prototype_colors, prototype_face_colors


def load_step_scene_from_xcaf_doc(
    step_path: Path,
    doc: Any,
    *,
    step_hash: str | None = None,
    source_kind: str = "step",
    source_hash: str | None = None,
    load_elapsed: float | None = None,
) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    load_started = time.perf_counter()
    loaded = _load_occurrence_tree_from_xcaf_doc(resolved_step_path, doc)
    if loaded is None:
        raise RuntimeError(f"XCAF document contains no STEP geometry: {resolved_step_path}")
    (
        roots,
        prototype_shapes,
        prototype_names,
        prototype_colors,
        prototype_face_colors,
    ) = loaded
    return LoadedStepScene(
        step_path=resolved_step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        load_elapsed=time.perf_counter() - load_started if load_elapsed is None else load_elapsed,
        step_hash=step_hash,
        source_kind=source_kind,
        source_hash=source_hash,
        doc=doc,
    )


def _load_fallback_occurrence_tree(
    step_path: Path,
) -> tuple[list[OccurrenceNode], dict[int, Any], dict[int, str | None], dict[int, ColorRGBA], dict[int, dict[int, ColorRGBA]]]:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"failed to read STEP file: {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError(f"STEP file produced no shape: {step_path}")
    prototype_key = _shape_hash(shape)
    return (
        [
            OccurrenceNode(
                path=(1,),
                name=step_path.stem,
                source_name=step_path.stem,
                transform=_identity_transform_matrix(),
                prototype_key=prototype_key,
                local_transform=_identity_transform_matrix(),
                location=None,
            )
        ],
        {prototype_key: shape},
        {prototype_key: step_path.stem},
        {},
        {},
    )


def load_step_scene(step_path: Path) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    load_started = time.perf_counter()
    (
        roots,
        prototype_shapes,
        prototype_names,
        prototype_colors,
        prototype_face_colors,
        doc,
    ) = _load_occurrence_tree(resolved_step_path)
    return LoadedStepScene(
        step_path=resolved_step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        load_elapsed=time.perf_counter() - load_started,
        doc=doc,
    )


# Inline scene-cache home, written beside each STEP like __pycache__ next to a .py.
# All STEPs in a directory share one __cadgen__ directory. Scene caches live under
# ``__cadgen__/models/<step-filename>/scene/`` so they sit inside the same per-model
# home as the component-GLB render package (``__cadgen__/models/<step-filename>/``)
# and its generation lock, rather than at the __cadgen__ root. Each is namespaced by
# STEP filename and keyed by schema + content hash; the ``scene`` subdir isolates the
# content-hash leaves so sibling pruning never touches ``assembly.json``/``components``.
def _scene_step_hash(scene: LoadedStepScene) -> str:
    if scene.step_hash is None:
        scene.step_hash = _step_hash(scene.step_path)
    return scene.step_hash


def _selector_id(path: tuple[int, ...]) -> str:
    return "o" + ".".join(str(segment) for segment in path)


def _relative_path_from_directory(path: Path, base_dir: Path) -> str:
    return os.path.relpath(
        path.expanduser().resolve(),
        start=base_dir.expanduser().resolve(),
    ).replace(os.sep, "/")


def _step_hash(step_path: Path) -> str:
    return step_file_hash(step_path)


