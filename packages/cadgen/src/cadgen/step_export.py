from __future__ import annotations

import os
import re
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen._internal.atomic_replace import (
    open_with_ladder,
    read_bytes_with_ladder,
    write_bytes_atomic,
)
from cadgen._internal.step_scene import LoadedStepScene, load_step_scene_from_xcaf_doc, step_file_hash


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
    # compound_from_instances bakes placements at the OCCT level, so the
    # compound has no build123d children and _create_bin_xcaf_doc flattens it
    # to a single shape. Its assembly hierarchy lives in the explicit
    # occurrence tree; attach it so scene consumers (interference) can walk
    # the same occurrence namespace the packager and the on-disk STEP use.
    occurrence_tree = getattr(shape, "_occurrence_tree", None)
    if occurrence_tree is not None:
        scene.instance_occurrence_tree = occurrence_tree
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


def quantity_color_rgba_from_color(color: object) -> object | None:
    """Return a Quantity_ColorRGBA carrying the colour's CHANNEL values as linear RGB.

    cadgen's colour contract (``cadgen.color``): a Color's channels -- the
    numbers ``tuple(color)`` yields, the ones ``srgb()`` computed -- ARE the
    linear RGB the renderer displays. The render package stores exactly those
    (``component_package._occurrence_color``), so the STEP document must carry
    the same numbers or the two views of one model disagree.

    They did. This used to read ``GetRGB()``, the Quantity_Color's INTERNAL
    value, which is not the channel: build123d's constructor treats its
    arguments as sRGB and linearizes them once more on the way in, so for
    ``srgb("#808080")`` (channels 0.216) the internal value is 0.038. Written
    as linear, that reached the file as sRGB 0.216 and came back through the
    reader -- ``inspect``, ``read_step``, the Viewer's STEP import, any other
    CAD tool -- two and a half stops darker than the package renders the same
    part. Normalizing the channel values through Quantity_TOC_RGB puts the
    intended sRGB byte in the file.
    """
    if color is None:
        return None
    if not isinstance(color, tuple) and getattr(color, "wrapped", None) is not None:
        try:
            channels = tuple(float(component) for component in color)
        except Exception:  # noqa: BLE001 - not an iterable Color; fall through to the wrapped read
            channels = ()
        if len(channels) >= 3:
            color = channels
    if isinstance(color, tuple):
        values = tuple(max(0.0, min(1.0, float(component))) for component in color)
        if len(values) == 3:
            rgba = (values[0], values[1], values[2], 1.0)
        elif len(values) >= 4:
            rgba = (values[0], values[1], values[2], values[3])
        else:
            return None
    else:
        wrapped = getattr(color, "wrapped", None)
        if wrapped is None:
            return None
        try:
            rgb = wrapped.GetRGB()
            rgba = (
                max(0.0, min(1.0, float(rgb.Red()))),
                max(0.0, min(1.0, float(rgb.Green()))),
                max(0.0, min(1.0, float(rgb.Blue()))),
                max(0.0, min(1.0, float(wrapped.Alpha()))),
            )
        except Exception:  # noqa: BLE001 - OCP Quantity color reads can raise C++ exceptions; fall back to the wrapped color
            return wrapped

    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

    rgb_color = Quantity_Color(rgba[0], rgba[1], rgba[2], Quantity_TOC_RGB)
    wrapped_rgba = Quantity_ColorRGBA(rgb_color)
    wrapped_rgba.SetAlpha(rgba[3])
    return wrapped_rgba


def _create_bin_xcaf_doc(to_export: Any) -> Any:
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
        wrapped = quantity_color_rgba_from_color(color)
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
        except Exception:  # noqa: BLE001 - OCP Location() can raise; degrade to the identity location
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
        except Exception:  # noqa: BLE001 - OCP Located() can raise on unusual shapes; keep the unlocated shape
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
                # A bare `Compound` leaf (a boolean/chamfer chain that came
                # back as plain Compound rather than Part/Sketch/Curve) still
                # holds valid colored geometry. Warning and skipping here
                # silently exported it uncolored — the per-component doc path
                # ships each leaf alone, so the model rendered washed-out.
                # Color whatever the compound actually contains, most solid
                # content first.
                explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_SOLID)
                if not explorer.More():
                    explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_FACE)
                if not explorer.More():
                    explorer = TopExp_Explorer(node.wrapped, ta.TopAbs_EDGE)

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
    originating_system: str = "cadgen",
    logger: object | None = None,
) -> LoadedStepScene:
    step_hash = write_xcaf_doc_step_file(
        doc,
        output_path,
        label=label,
        originating_system=originating_system,
        logger=logger,
    )
    with (logger.timed(f"load scene from XCAF {output_path.name}") if logger is not None else nullcontext()):
        return load_step_scene_from_xcaf_doc(
            output_path,
            doc,
            step_hash=step_hash,
        )


def _renumber_nauo_ids(model: Any) -> None:
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence
    from OCP.TCollection import TCollection_HAsciiString

    # SelectType filters C++-side; a Python isinstance scan over every entity
    # costs ~1s on multi-million-entity models.
    iterator = model.Entities()
    iterator.SelectType(StepRepr_NextAssemblyUsageOccurrence.get_type_descriptor_s(), True)
    count = 0
    iterator.Start()
    while iterator.More():
        count += 1
        iterator.Value().SetId(TCollection_HAsciiString(str(count)))
        iterator.Next()


_MDGPR_TYPE = "StepVisual_MechanicalDesignGeometricPresentationRepresentation"

# The complete entity family OCCT's writeColors() appends per styled product
# (STEPCAFControl_Writer.cxx, MakeSTEPStyles + "register all MDGPRs in model").
# _style_tail_plan only orders a tail made entirely of these;
# an unexpected type in the tail means the writer changed shape, and the
# canonicalization steps aside rather than guess.
_STYLE_TAIL_FAMILY = frozenset({
    _MDGPR_TYPE,
    "StepVisual_StyledItem",
    "StepVisual_OverRidingStyledItem",
    "StepVisual_PresentationStyleAssignment",
    "StepVisual_PresentationStyleByContext",
    "StepVisual_SurfaceStyleUsage",
    "StepVisual_SurfaceSideStyle",
    "StepVisual_SurfaceStyleFillArea",
    # Emitted only for a part whose colour carries alpha: the transparency rides
    # a rendering entity hanging off the same SurfaceSideStyle as the fill area.
    # Without these two the tail-family check below rejected every model with a
    # single transparent part and left it writing address-ordered bytes.
    "StepVisual_SurfaceStyleRendering",
    "StepVisual_SurfaceStyleRenderingWithProperties",
    "StepVisual_SurfaceStyleTransparent",
    "StepVisual_FillAreaStyle",
    "StepVisual_FillAreaStyleColour",
    "StepVisual_ColourRgb",
    "StepVisual_Colour",
    "StepVisual_PreDefinedColour",
    "StepVisual_DraughtingPreDefinedColour",
    "StepVisual_CurveStyle",
    "StepVisual_DraughtingPreDefinedCurveFont",
})


def _style_entity_children(ent: Any) -> list:
    """One style-tail entity's referenced entities, in FIELD order — the same
    order AddWithRefs traverses, so a canonical DFS reproduces each closure's
    internal layout exactly."""
    name = ent.DynamicType().Name()
    out: list = []

    def add(value: object) -> None:
        if value is not None:
            out.append(value)

    def add_select(select: object) -> None:
        value = getattr(select, "Value", None)
        add(value() if callable(value) else select)

    def add_array(array: object) -> None:
        if array is not None:
            for index in range(1, array.Length() + 1):
                add_select(array.Value(index))

    if name == _MDGPR_TYPE:
        add_array(ent.Items())
    elif name in ("StepVisual_StyledItem", "StepVisual_OverRidingStyledItem"):
        add(ent.Item())
        add_array(ent.Styles())
        if name == "StepVisual_OverRidingStyledItem":
            add(ent.OverRiddenStyle())
    elif name in ("StepVisual_PresentationStyleAssignment", "StepVisual_PresentationStyleByContext"):
        add_array(ent.Styles())
        if name == "StepVisual_PresentationStyleByContext":
            add_select(ent.StyleContext())
    elif name == "StepVisual_SurfaceStyleUsage":
        add(ent.Style())
    elif name == "StepVisual_SurfaceSideStyle":
        add_array(ent.Styles())
    elif name == "StepVisual_SurfaceStyleFillArea":
        add(ent.FillArea())
    elif name == "StepVisual_FillAreaStyle":
        add_array(ent.FillStyles())
    elif name == "StepVisual_FillAreaStyleColour":
        add(ent.FillColour())
    elif name in (
        "StepVisual_SurfaceStyleRendering",
        "StepVisual_SurfaceStyleRenderingWithProperties",
    ):
        # SURFACE_STYLE_RENDERING[_WITH_PROPERTIES](rendering_method, surface_colour
        # [, properties]): the method is an enum, not an entity, so the DFS starts at
        # the colour. `properties` is a select array whose members are the
        # SurfaceStyleTransparent leaves.
        add(ent.SurfaceColour())
        if name == "StepVisual_SurfaceStyleRenderingWithProperties":
            add_array(ent.Properties())
    # Colours, transparency values, and predefined fonts are leaves.
    return out


_STYLED_ITEM_TYPES = ("StepVisual_StyledItem", "StepVisual_OverRidingStyledItem")


@dataclass(frozen=True, slots=True)
class _StyleTailScan:
    """What the canonical style-tail order needs from the model, read from the
    TAIL ENTITIES ONLY -- never from the millions of geometry entities before
    them (see ``_style_tail_scan``).

    ``children[n]`` lists the tail entities entity ``n`` references, in field
    order, with everything outside the tail already dropped. ``styled_items[m]``
    is MDGPR ``m``'s items that are styled items, in Items order, as
    ``(tail_number, entity)``; the tail number is None for a styled item that
    lives outside the tail (never seen from OCCT, handled by the full plan).
    """

    tail_start: int
    total: int
    children: dict[int, list[int]]
    mdgpr_nums: list[int]
    styled_items: dict[int, list[tuple[int | None, Any]]]

    @property
    def size(self) -> int:
        return self.total - self.tail_start + 1

    @property
    def targets_need_full_plan(self) -> bool:
        return any(num is None for items in self.styled_items.values() for num, _ent in items)


def _style_tail_scan(model: Any) -> _StyleTailScan | None:
    """Read the style tail's structure from the model, touching tail entities only.

    OCCT registers each styled product's presentation graph by iterating an
    ADDRESS-hashed shape map (STEPCAFControl_Writer::transfer's myMapCompMDGPR,
    still address-hashed on master), so with two or more styled products the
    MDGPR closures — and every entity number after them — land in heap-address
    order: byte-different files for identical models, varying per process and
    even per call. Everything before the style tail is deterministic transfer
    order (see _renumber_nauo_ids, which leans on the same property).

    The tail is the suffix of the model from the first MDGPR to the last entity,
    and it is made entirely of ``_STYLE_TAIL_FAMILY`` types (OCCT registers the
    MDGPRs last, after layers, SHUOs and properties). So it is found by walking
    BACKWARDS from the last entity while the type stays in the family: a few
    ten-thousand ``Entity(i)`` calls on the largest assemblies instead of one per
    entity in the model, which made the old forward scan cost seconds per write.

    Returns None when there is nothing to permute (at most one MDGPR), when the
    tail holds an unexpected type (the writer changed shape; the canonicalization
    steps aside rather than guess), or when the closures do not cover the whole
    tail. Every None leaves the file exactly as OCCT wrote it: nondeterministically
    ordered, never corrupt.
    """
    from OCP.StepVisual import (
        StepVisual_MechanicalDesignGeometricPresentationRepresentation as _MDGPR,
    )

    # Cheap C++-side count first: parts and single-product assemblies have at
    # most one MDGPR, one closure, nothing to permute — skip the Python scan.
    iterator = model.Entities()
    iterator.SelectType(_MDGPR.get_type_descriptor_s(), True)
    mdgpr_count = 0
    iterator.Start()
    while iterator.More():
        mdgpr_count += 1
        iterator.Next()
    if mdgpr_count <= 1:
        return None

    # OCP's model.Number() binding returns 0 for every entity, so numbers come
    # from Entity(i); it returns an identity-stable wrapper, so id() keys are
    # sound while `entities` holds the references.
    total = model.NbEntities()
    entities: dict[int, Any] = {}
    mdgpr_nums: list[int] = []
    number = total
    while number >= 1:
        ent = model.Entity(number)
        name = ent.DynamicType().Name()
        if name not in _STYLE_TAIL_FAMILY:
            break
        entities[number] = ent
        if name == _MDGPR_TYPE:
            mdgpr_nums.append(number)
        number -= 1
    if len(mdgpr_nums) != mdgpr_count:
        # An MDGPR sits before a non-family entity: the tail is not the pure
        # style suffix this expects.
        return None
    mdgpr_nums.reverse()
    tail_start = mdgpr_nums[0]
    for number in range(min(entities), tail_start):
        del entities[number]
    number_of = {id(ent): number for number, ent in entities.items()}
    referenced = {number: _style_entity_children(ent) for number, ent in entities.items()}
    children = {
        number: [number_of[id(child)] for child in refs if id(child) in number_of]
        for number, refs in referenced.items()
    }
    styled_items = {
        mdgpr_num: [
            (number_of.get(id(item)), item)
            for item in referenced[mdgpr_num]
            if item.DynamicType().Name() in _STYLED_ITEM_TYPES
        ]
        for mdgpr_num in mdgpr_nums
    }
    scan = _StyleTailScan(tail_start, total, children, mdgpr_nums, styled_items)
    # Coverage does not depend on block order (the closures' union is the
    # same whichever MDGPR is visited first), so a tail the DFS cannot reach
    # completely is known here, before the write.
    if _style_tail_order(scan, {n: [] for n in mdgpr_nums}) is None:
        return None
    return scan


def _style_tail_order(scan: _StyleTailScan, targets: dict[int, list[int]]) -> list[int] | None:
    """The canonical order of the tail, as OLD entity numbers: ``result[i]`` is
    the entity that must end up numbered ``tail_start + i``.

    MDGPR blocks sort by the styled targets they reference (``targets[m]``: the
    head-entity numbers the block's styled items point at, which ARE stable),
    ties broken by the MDGPR's own number; each closure is laid out in
    field-order DFS, the order AddWithRefs traverses, so a closure's internal
    layout is reproduced exactly. Entities shared between closures (deduplicated
    colours) land with the first canonical owner. None when the closures do not
    cover the tail.
    """
    children = scan.children
    desired: list[int] = []
    seen: set[int] = set()

    def visit(number: int) -> None:
        if number in seen:
            return
        seen.add(number)
        desired.append(number)
        for child in children[number]:
            visit(child)

    for mdgpr_num in sorted(scan.mdgpr_nums, key=lambda m: (tuple(sorted(targets[m])), m)):
        visit(mdgpr_num)
    if len(desired) != scan.size:
        return None
    return desired


def _style_tail_plan(model: Any) -> tuple[int, int, list[int]] | None:
    """The full canonical plan from the model alone: ``(tail_start, total,
    old_numbers)``, for the in-model applier.

    This is the SLOW route. The styled targets are geometry entities before the
    tail, and OCP cannot number an entity directly (``model.Number()`` returns
    0), so finding them means wrapping every entity in the model — seconds on a
    large assembly. The text route avoids that by reading the target numbers
    from the written records instead (``_canonicalize_style_tail_in_file``); the
    byte-identity test pins the two routes to the same output.
    """
    scan = _style_tail_scan(model)
    if scan is None:
        return None
    entities = [None] + [model.Entity(index) for index in range(1, scan.total + 1)]
    number_of = {id(ent): index for index, ent in enumerate(entities[1:], start=1)}
    targets: dict[int, list[int]] = {}
    for mdgpr_num, items in scan.styled_items.items():
        block: list[int] = []
        for _tail_number, item in items:
            target_num = number_of.get(id(item.Item()))
            if target_num is not None and target_num < scan.tail_start:
                block.append(target_num)
        targets[mdgpr_num] = block
    old_numbers = _style_tail_order(scan, targets)
    if old_numbers is None:
        return None
    return scan.tail_start, scan.total, old_numbers


def _apply_style_tail_plan_in_model(model: Any, tail_start: int, old_numbers: list[int]) -> None:
    """Permute the model itself, one ``ChangeOrder`` per tail entity.

    Exact, and quadratic: each call renumbers a model that holds ~10^5-10^6
    entities, so juno's ~3400-entity tail costs ~110 s. It survives only as the
    backstop for the one case the text applier below refuses (a tail whose
    entity numbers do not all have the same digit width); the byte-identity
    test pins the two appliers to the same output.
    """
    total = tail_start + len(old_numbers) - 1
    order = list(range(tail_start, total + 1))
    for offset, old_number in enumerate(old_numbers):
        current = tail_start + order.index(old_number)
        target = tail_start + offset
        if current != target:
            model.ChangeOrder(current, target)
            order.remove(old_number)
            order.insert(offset, old_number)


# A STEP record header: `#123 = TYPE(...)`, always at the start of a line. A
# wrapped continuation line can also begin with `#`, but only a header carries
# the ` = `, so this cannot mistake one for the other.
_STEP_RECORD_START = re.compile(rb"(?m)^#(\d+) = ")
# A quoted STEP string OR an entity reference. The string alternative comes
# first and consumes the whole literal (`''` is an escaped quote), so a `#` that
# happens to sit inside a part name is never rewritten as a reference.
_STEP_STRING_OR_REF = re.compile(rb"'(?:[^']|'')*'|#(\d+)")


def _digit_range_regex(low: str, high: str) -> str:
    """A regex matching exactly the decimal strings of ``len(low)`` digits in
    ``[low, high]`` (both the same width, ``low <= high``)."""
    if low == high:
        return low
    if low[0] == high[0]:
        return low[0] + _digit_range_regex(low[1:], high[1:])

    def at_least(digits: str) -> str:  # same-width strings >= digits
        if len(digits) == 1:
            return f"[{digits}-9]"
        parts = [digits[0] + at_least(digits[1:])]
        if digits[0] != "9":
            parts.append(f"[{int(digits[0]) + 1}-9]" + r"\d" * (len(digits) - 1))
        return "(?:" + "|".join(parts) + ")"

    def at_most(digits: str) -> str:  # same-width strings <= digits
        if len(digits) == 1:
            return f"[0-{digits}]"
        parts = [digits[0] + at_most(digits[1:])]
        if digits[0] != "0":
            parts.append(f"[0-{int(digits[0]) - 1}]" + r"\d" * (len(digits) - 1))
        return "(?:" + "|".join(parts) + ")"

    parts = [low[0] + at_least(low[1:])]
    if int(high[0]) - int(low[0]) > 1:
        parts.append(f"[{int(low[0]) + 1}-{int(high[0]) - 1}]" + r"\d" * (len(low) - 1))
    parts.append(high[0] + at_most(high[1:]))
    return "(?:" + "|".join(parts) + ")"


def _tail_reference_pattern(tail_start: int, total: int) -> "re.Pattern[bytes]":
    """Matches any `#N` token whose integer value is a tail number — including
    a leading-zero spelling, which ``int()`` would also map into the tail."""
    body = _digit_range_regex(str(tail_start), str(total)).encode()
    return re.compile(rb"#0*" + body + rb"(?!\d)")


def _step_record_fields(record: bytes) -> list[bytes]:
    """The top-level parameters of one `#N = TYPE(...)` record, whitespace
    (including OCCT's line wrapping) removed. An aggregate parameter comes back
    as one field, parentheses included."""
    start = record.find(b"(")
    if start < 0:
        return []
    fields: list[bytes] = []
    current: list[bytes] = []
    depth = 0
    for match in re.finditer(rb"'(?:[^']|'')*'|[(),]|[^'(),\s]+", record[start:]):
        token = match.group(0)
        if token == b"(":
            depth += 1
            if depth > 1:
                current.append(token)
        elif token == b")":
            depth -= 1
            if depth == 0:
                fields.append(b"".join(current))
                break
            current.append(token)
        elif token == b"," and depth == 1:
            fields.append(b"".join(current))
            current = []
        else:
            current.append(token)
    return fields


def _styled_item_target(record: bytes) -> int | None:
    """The entity a written STYLED_ITEM / OVER_RIDING_STYLED_ITEM record styles:
    its third parameter (name, styles, item[, over_ridden_style])."""
    fields = _step_record_fields(record)
    if len(fields) < 3:
        return None
    match = re.fullmatch(rb"#(\d+)", fields[2])
    return int(match.group(1)) if match else None


def _apply_style_tail_plan_in_text(
    text: bytes, tail_start: int, old_numbers: list[int]
) -> bytes | None:
    """The same permutation, applied to the WRITTEN file instead of the model.

    Two linear passes over the text: renumber every reference through the
    old->new map (the regex skips string literals), then reorder the tail
    records, which are a contiguous suffix of the DATA section. Returns None if
    the text does not have the shape this expects.

    ``text`` is the whole file, or any suffix of it that begins at a record
    header: the fast path hands it the file from the first tail record on
    (``_canonicalize_style_tail_in_file``), the fallback the entire file.

    This is byte-identical to the in-model applier only because the caller
    guarantees every rewritten number keeps its digit width: OCCT wraps long
    records at a fixed column, so a number that grew a digit would shift the
    wrapping and produce a differently-formatted (though semantically equal)
    file. Same width in, same bytes out.
    """
    new_of = {old: tail_start + offset for offset, old in enumerate(old_numbers)}
    if all(old == new for old, new in new_of.items()):
        return text

    def renumber(match: "re.Match[bytes]") -> bytes:
        digits = match.group(1)
        if digits is None:  # a string literal — leave it exactly as written
            return match.group(0)
        replacement = new_of.get(int(digits))
        return match.group(0) if replacement is None else b"#%d" % replacement

    renumbered = _STEP_STRING_OR_REF.sub(renumber, text)

    # Record starts, so the tail records can be sorted into their new order.
    # After the substitution above each header carries its NEW number.
    headers = list(_STEP_RECORD_START.finditer(renumbered))
    if not headers:
        return None
    first_tail = next(
        (i for i, m in enumerate(headers) if int(m.group(1)) >= tail_start), None
    )
    if first_tail is None or len(headers) - first_tail != len(old_numbers):
        return None
    region_start = headers[first_tail].start()
    end_marker = renumbered.find(b"\nENDSEC;", region_start)
    if end_marker < 0:
        return None
    region_end = end_marker + 1  # the last record keeps its trailing newline
    bounds = [m.start() for m in headers[first_tail:]] + [region_end]
    records = [
        (int(headers[first_tail + i].group(1)), renumbered[bounds[i]:bounds[i + 1]])
        for i in range(len(bounds) - 1)
    ]
    records.sort(key=lambda record: record[0])
    return (
        renumbered[:region_start]
        + b"".join(body for _number, body in records)
        + renumbered[region_end:]
    )


def _canonicalize_style_tail_in_file(path: Path, scan: _StyleTailScan) -> bool:
    """Apply the canonical order to the file OCCT just wrote, touching only the
    tail records — a shortcut of ``_apply_style_tail_plan_in_text`` over the
    whole file that is proven, not assumed, to produce the same bytes.

    The style tail is the last ``scan.size`` records of the DATA section, and
    nothing before it references into it (OCCT registers the MDGPR closures
    last; a reference can only point at an entity that existed when its owner
    was added). So the permutation runs on the file's suffix from the first
    tail record on, and the styled TARGET numbers the block order needs are
    read from the styled-item records themselves — a lookup OCP cannot do in
    the model without wrapping every entity. Two checks make skipping the
    pre-tail bytes exact rather than a bet:

    - the headers from the first tail record to ENDSEC are exactly the tail
      numbers, so the suffix IS what the whole-file pass would have sorted;
    - no `#N` token before it — reference, header, or even inside a string —
      spells a tail number (one precompiled range pattern over the bytes, no
      Python per match), so the whole-file renumber would have changed nothing
      there. A pre-tail header numbered above ``total`` is the one shape this
      does not rule out, and a file written from a ``total``-entity model
      cannot have one.

    There is deliberately no line-count check: OCCT wraps COMPLEX entity records
    with continuation lines that begin at column 0 with `#`, so counting `\n#`
    over-counts headers on any real model.

    Returns False when a check fails; the caller then runs the whole-file pass,
    which is exact for any shape and costs what every write used to cost.
    """
    tail_start, total, size = scan.tail_start, scan.total, scan.size
    data = read_bytes_with_ladder(path)
    # OCCT writes entities in number order, so the tail begins at #tail_start;
    # the header check below holds this to account rather than trusting it.
    first_header = data.rfind(b"\n#%d = " % tail_start)
    if first_header < 0:
        return False
    region_start = first_header + 1
    suffix = data[region_start:]
    headers = list(_STEP_RECORD_START.finditer(suffix))
    if len(headers) != size or sorted(int(m.group(1)) for m in headers) != list(
        range(tail_start, total + 1)
    ):
        return False
    if _tail_reference_pattern(tail_start, total).search(data, 0, region_start):
        return False

    end_marker = suffix.find(b"\nENDSEC;")
    if end_marker < 0:
        return False
    bounds = [m.start() for m in headers] + [end_marker + 1]
    records = {int(headers[i].group(1)): suffix[bounds[i]:bounds[i + 1]] for i in range(size)}
    targets: dict[int, list[int]] = {}
    for mdgpr_num, items in scan.styled_items.items():
        block: list[int] = []
        for tail_number, _item in items:
            target_num = _styled_item_target(records[tail_number])
            # `#0` is OCCT's spelling of an entity outside the model; the
            # model-side lookup finds no number for it either.
            if target_num is not None and 0 < target_num < tail_start:
                block.append(target_num)
        targets[mdgpr_num] = block
    old_numbers = _style_tail_order(scan, targets)
    if old_numbers is None:
        return False
    canonical = _apply_style_tail_plan_in_text(suffix, tail_start, old_numbers)
    if canonical is None:
        return False
    if canonical != suffix:
        with open_with_ladder(path, "r+b") as handle:
            handle.seek(region_start)
            handle.write(canonical)
            handle.truncate()
    return True


def write_xcaf_doc_step_file(
    doc: Any,
    output_path: Path,
    *,
    label: str | None = None,
    originating_system: str = "cadgen",
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

    STEPCAFControl_Controller.Init_s()
    STEPControl_Controller.Init_s()
    IGESControl_Controller.Init_s()
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    Interface_Static.SetIVal_s("write.precision.mode", PrecisionMode.AVERAGE.value)
    with (logger.timed(f"transfer XCAF to STEP model {output_path.name}") if logger is not None else nullcontext()):
        writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)

    # NAUO instance ids come from a process-global OCCT counter, so a warm
    # process that has exported before writes different ids than a cold one
    # for the same model. Renumber them 1..N in model-entity order (which is
    # deterministic transfer order) so identical models write identical bytes.
    with (logger.timed("renumber NAUO ids") if logger is not None else nullcontext()):
        _renumber_nauo_ids(writer.Writer().Model())
    # Same contract, other direction: OCCT appends multi-product style graphs
    # in heap-address order. Reorder them into content order.
    #
    # The tail's STRUCTURE is read here, from the model, because model entity
    # numbers ARE the numbers Write() is about to emit; the scan touches only
    # the tail entities, so it costs tens of milliseconds on a model whose
    # geometry runs to millions of entities. WHERE the permutation gets applied
    # is a performance decision, not a correctness one:
    #
    #   - in the written FILE (the normal path): the tail records alone are
    #     renumbered and reordered in place, after two checks that the rest
    #     of the file could not have been touched by a whole-file rewrite
    #     (which remains the fallback when a check fails);
    #   - in the MODEL, before writing: exact but quadratic — ~110 s on juno,
    #     because each ChangeOrder renumbers the whole model — and it needs the
    #     full plan, whose target lookup wraps every entity in the model.
    #
    # The in-file applier is byte-identical to the model applier only while
    # every number it rewrites keeps its digit width (OCCT wraps records at a
    # fixed column, so a number that gained a digit would shift the wrapping).
    # A tail that straddles a power of ten is rare and cannot be made
    # width-safe, so it takes the slow path rather than writing
    # differently-formatted bytes.
    with (logger.timed("plan style tail order") if logger is not None else nullcontext()):
        scan = _style_tail_scan(writer.Writer().Model())
    if scan is not None and (
        len(str(scan.tail_start)) != len(str(scan.total))
        or scan.targets_need_full_plan
        or os.environ.get("CADGEN_STEP_STYLE_REORDER", "").strip() == "model"
    ):
        with (logger.timed("canonicalize style tail (in model)") if logger is not None else nullcontext()):
            plan = _style_tail_plan(writer.Writer().Model())
            if plan is not None:
                tail_start, _total, old_numbers = plan
                _apply_style_tail_plan_in_model(
                    writer.Writer().Model(), tail_start, old_numbers
                )
        scan = None

    # The header must be edited AFTER Transfer: Transfer rebuilds the writer's
    # model, discarding anything set on the pre-transfer header.
    header = APIHeaderSection_MakeHeader(writer.Writer().Model())
    if label:
        header.SetName(TCollection_HAsciiString(label))
    header.SetOriginatingSystem(TCollection_HAsciiString(originating_system))
    # Byte-determinism: the only nondeterministic bytes in a written STEP are
    # FILE_NAME's wall-clock time_stamp. Exports are content-addressed
    # end-to-end (export records verify by sha256, identical models must
    # produce identical files), so the stamp is pinned. The real generation
    # time lives in the package descriptor, not the interchange file.
    header.SetTimeStamp(TCollection_HAsciiString("2000-01-01T00:00:00"))

    with (logger.timed(f"write STEP file {output_path.name}") if logger is not None else nullcontext()):
        if writer.Write(os.fspath(output_path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise RuntimeError(f"Failed to write STEP file: {output_path}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"STEP export did not create {output_path}")
    if scan is not None:
        with (logger.timed("canonicalize style tail (in file)") if logger is not None else nullcontext()):
            canonicalized = _canonicalize_style_tail_in_file(output_path, scan)
        if not canonicalized:
            # A file shape the fast path did not recognize. Never seen from
            # OCCT; the exact route is the whole-file pass with the full plan
            # — what every write cost before the fast path, never the
            # quadratic model route, which on a large model would run for hours.
            if logger is not None:
                logger.warning(
                    f"style tail of {output_path.name} was not the expected file "
                    "shape; canonicalizing with a whole-file pass"
                )
            with (logger.timed("canonicalize style tail (whole file)") if logger is not None else nullcontext()):
                plan = _style_tail_plan(writer.Writer().Model())
                if plan is not None:
                    tail_start, _total, old_numbers = plan
                    canonical = _apply_style_tail_plan_in_text(
                        read_bytes_with_ladder(output_path), tail_start, old_numbers
                    )
                    # A text shape this did not recognize either leaves the file
                    # exactly as OCCT wrote it: nondeterministically ordered,
                    # never corrupt.
                    if canonical is not None:
                        # Atomic, not a truncating rewrite in place: this is a user
                        # artifact, and a whole-file `wb` that dies midway leaves a
                        # half-written STEP where the tail rewrite above cannot.
                        write_bytes_atomic(output_path, canonical)
    return step_file_hash(output_path)


def export_build123d_step_scene(
    to_export: Any,
    output_path: Path,
) -> LoadedStepScene:
    doc = _create_bin_xcaf_doc(to_export)
    scene = export_xcaf_doc_step_scene(
        doc,
        output_path,
        label=getattr(to_export, "label", None),
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


def export_build123d_step_file(
    to_export: Any,
    output_path: Path,
    *,
    logger: object | None = None,
) -> str:
    """Write a build123d shape to a text STEP file (no scene), returning its hash.

    The write-only counterpart to :func:`export_build123d_step_scene`, used by the
    on-demand ``--step`` export: the build already holds the in-memory scene/compound,
    so STEP export only needs to serialize the shape, not rebuild a scene."""
    with (logger.timed("build XCAF document") if logger is not None else nullcontext()):
        doc = _create_bin_xcaf_doc(to_export)
    return write_xcaf_doc_step_file(
        doc,
        output_path,
        label=getattr(to_export, "label", None),
        logger=logger,
    )
