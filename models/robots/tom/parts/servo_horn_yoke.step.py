#!/usr/bin/env python3
"""
Generate the localized horn-mounted yoke.

This variant preserves the existing horn interface geometry while shortening
the horn-side end into a single flange that forks into two circular cap
flanges. The horn flanges carry the two outer M3 holes plus the inboard horn
hole, and intentionally omit the previous center clearance and far-side M3
hole.

Usage:
  python STEP/servo_horn_yoke.py
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Keep CAD library caches inside the workspace to avoid permission issues.
TOM_DIR = Path(__file__).resolve().parents[1]
V2_DIR = Path(__file__).resolve().parents[1]
_CACHE_HOME = V2_DIR / ".cache"
_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_HOME))
os.environ.setdefault("EZDXF_CACHE_HOME", str(_CACHE_HOME / "ezdxf"))

import ezdxf
import build123d
from ezdxf.units import MM as DXF_UNIT_MM

if str(TOM_DIR) not in sys.path:
    sys.path.insert(0, str(TOM_DIR))

from robot_common.booleans import as_single_shape, intersection_volume
from robot_common.materials import GRAY_ALUMINUM_COLOR
from robot_common.step_import import import_as_shape
from cadgen import flatten as dxf_topology


CAD_DIR = Path(__file__).resolve().parent
PART_NAME = Path(__file__).stem
DISPLAY_NAME = "Servo Horn Yoke"

SERVO_STEP = V2_DIR / "parts" / "imports" / "sts3250.step"

UPPER_HORN_SELECTOR = "xcaf:1.4"
LOWER_HORN_SELECTOR = "xcaf:1.5"
UPPER_HORN_NAME = "4"
LOWER_HORN_NAME = "5"

SERVO_HORN_AXIS_X_MM = -25.5
YOKE_HORN_SPAN_CENTER_Y_MM = -9.1
SERVO_REFERENCE_FACE_TARGET_CENTER_MM = (-35.61, -7.65, 0.0)
SERVO_REFERENCE_FACE_MAX_ERROR_MM = 0.5
HORN_FACE_GAP_MM = 0.0
MOUNT_HOLE_MIN_OFFSET_MM = 3.0
CUT_EXTENSION_MM = 2.0
M3_CLEARANCE_RADIUS_MM = 1.7
HORN_CENTER_CLEARANCE_RADIUS_MM = 3.25
YOKE_LENGTH_REDUCTION_MM = 6.5
HORN_CAP_FLANGE_RADIUS_MM = 10.0 - YOKE_LENGTH_REDUCTION_MM
YOKE_FULL_FLANGE_OUTER_LENGTH_MM = 30.0
# Keep the rotating web outside the primary servo's left-side corner sweep.
# This is measured from the flange servo horn axis to the yoke web's outer face.
YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM = (
    YOKE_FULL_FLANGE_OUTER_LENGTH_MM - HORN_CAP_FLANGE_RADIUS_MM
)
HORN_CAP_FLANGE_HOLE_X_TOLERANCE_MM = 0.25
HORN_FORK_SLOT_RADIUS_MM = HORN_CAP_FLANGE_RADIUS_MM
REFERENCE_SHEET_THICKNESS_MM = 25.4 * 0.080
BOTTOM_FACE_SLOT_WIDTH_MM = 3.0
# Keep the side-flange slot away from the bend/root so the yoke keeps a
# stronger uninterrupted load path into the base.
BOTTOM_FACE_SLOT_BEND_EDGE_CLEARANCE_MM = 10.0
BOTTOM_FACE_SLOT_END_GAP_MM = 4.0
STANDALONE_FLOOR_ROTATION_AXIS = build123d.Axis.Y
STANDALONE_FLOOR_ROTATION_DEG = -90.0
DESIGN_OUTER_WEB_X_MM = SERVO_HORN_AXIS_X_MM - YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM


def multiply_transforms(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> tuple[float, ...]:
    return tuple(
        sum(float(left[row * 4 + inner]) * float(right[inner * 4 + col]) for inner in range(4))
        for row in range(4)
        for col in range(4)
    )


# The standalone yoke STEP is rotated to sit on the floor for inspection.
# Assemblies still need the original horn/yoke design frame, so these matrices
# bridge standalone STEP coordinates and design coordinates.
STANDALONE_TO_DESIGN_TRANSFORM = (
    0.0, 0.0, 1.0, DESIGN_OUTER_WEB_X_MM,
    0.0, 1.0, 0.0, 0.0,
    -1.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)
DESIGN_TO_STANDALONE_TRANSFORM = (
    0.0, 0.0, -1.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    1.0, 0.0, 0.0, -DESIGN_OUTER_WEB_X_MM,
    0.0, 0.0, 0.0, 1.0,
)
YOKE_180_ABOUT_WEB_AXIS_DESIGN_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, -1.0, 0.0, 2.0 * YOKE_HORN_SPAN_CENTER_Y_MM,
    0.0, 0.0, -1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)
YOKE_180_ABOUT_WEB_AXIS_STANDALONE_TRANSFORM = multiply_transforms(
    DESIGN_TO_STANDALONE_TRANSFORM,
    multiply_transforms(
        YOKE_180_ABOUT_WEB_AXIS_DESIGN_TRANSFORM,
        STANDALONE_TO_DESIGN_TRANSFORM,
    ),
)
STANDALONE_YOKE_ON_SERVO_HORNS_TRANSFORM = multiply_transforms(
    YOKE_180_ABOUT_WEB_AXIS_DESIGN_TRANSFORM,
    STANDALONE_TO_DESIGN_TRANSFORM,
)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if parsed <= 0.0:
        raise ValueError(f"{name} must be positive, got {parsed!r}")
    return parsed


SHEET_THICKNESS_MM = _env_float("TOM_V2_SHEET_THICKNESS_MM", 25.4 * 0.063)
SHEET_RULE_SCALE = SHEET_THICKNESS_MM / REFERENCE_SHEET_THICKNESS_MM


@dataclass(frozen=True)
class BendRule:
    material_name: str
    thickness_mm: float
    effective_inside_radius_mm: float
    k_factor: float
    bend_deduction_90_mm: float
    half_die_width_mm: float
    min_flange_flat_mm: float
    min_flange_formed_mm: float
    min_acute_centerline_length_mm: float
    channel_one_to_one_max_flange_mm: float
    channel_narrow_min_base_mm: float
    channel_base_spacing_min_mm: float
    max_bend_angle_deg: float

    @property
    def outside_setback_90_mm(self) -> float:
        return self.effective_inside_radius_mm + self.thickness_mm

    @property
    def bend_allowance_90_mm(self) -> float:
        return (2.0 * self.outside_setback_90_mm) - self.bend_deduction_90_mm

    @property
    def outer_radius_mm(self) -> float:
        return self.effective_inside_radius_mm + self.thickness_mm

    def flat_length_from_outside_length_90(self, outside_length_mm: float) -> float:
        return outside_length_mm - self.outside_setback_90_mm


SHEET_RULE = BendRule(
    material_name="5052-H32 ALU-063",
    thickness_mm=SHEET_THICKNESS_MM,
    effective_inside_radius_mm=25.4 * 0.035,
    k_factor=0.42,
    bend_deduction_90_mm=25.4 * 0.096,
    half_die_width_mm=0.5 * (25.4 * 0.472),
    min_flange_flat_mm=25.4 * 0.255,
    min_flange_formed_mm=25.4 * 0.303,
    min_acute_centerline_length_mm=(25.4 * 0.332) * SHEET_RULE_SCALE,
    channel_one_to_one_max_flange_mm=25.4 * 3.000,
    channel_narrow_min_base_mm=25.4 * 1.000,
    channel_base_spacing_min_mm=2.0 * (25.4 * 0.255),
    max_bend_angle_deg=130.0,
)


@dataclass(frozen=True)
class HornMountSpec:
    name: str
    mount_face_y: float
    mount_face_center: build123d.Vector
    mount_face_bbox: build123d.BoundBox
    half_width_z: float
    center_clearance_radius: float
    mount_holes: tuple[tuple[build123d.Vector, float], ...]


@dataclass(frozen=True)
class BracketLayout:
    web_inner_x: float
    web_outer_x: float
    top_y_min: float
    top_y_max: float
    bottom_y_min: float
    bottom_y_max: float
    top_z_min: float
    top_z_max: float
    bottom_z_min: float
    bottom_z_max: float
    global_z_min: float
    global_z_max: float


@dataclass(frozen=True)
class BracketMetrics:
    min_flange_outside_length_mm: float
    min_flange_flat_length_mm: float
    bend_line_spacing_mm: float
    min_hole_edge_to_bend_mm: float
    min_slot_edge_to_bend_mm: float
    min_web_feature_edge_to_bend_mm: float
    base_to_flange_ratio: float
    bend_deduction_formula_mm: float


@dataclass(frozen=True)
class GeneratorInputs:
    servo_shape: build123d.Shape
    reference_face_x: float
    sheet_half_width_z: float
    upper_horn: HornMountSpec
    lower_horn: HornMountSpec


@dataclass(frozen=True)
class WebHoleSpec:
    center_y: float
    center_z: float
    radius: float


@dataclass(frozen=True)
class SlotSpec:
    center_x: float
    center_z: float
    length: float
    width: float


@dataclass(frozen=True)
class CircleProfileSpec:
    center_x: float
    center_y: float
    radius: float


@dataclass(frozen=True)
class SlotProfileSpec:
    center_x: float
    center_y: float
    length: float
    width: float


@dataclass(frozen=True)
class FlatPattern:
    total_length_mm: float
    width_mm: float
    cap_radius_mm: float
    bend_line_positions_mm: tuple[float, float]
    round_hole_profiles: tuple[CircleProfileSpec, ...]
    slot_profiles: tuple[SlotProfileSpec, ...]


def _cast_shape(obj: object) -> build123d.Shape:
    from build123d.topology import downcast
    from build123d.topology.shape_core import shapetype

    occt_shape = downcast(obj)
    shape_name = build123d.Shape.shape_LUT[shapetype(occt_shape)]
    shape_type = getattr(build123d, shape_name)
    return shape_type.cast(occt_shape)


def _geom_type_name(shape: build123d.Shape) -> str:
    geom_type = shape.geom_type
    return geom_type.name if hasattr(geom_type, "name") else str(geom_type)


def _face_from_wire(
    exterior: build123d.Wire,
    interior_wires: list[build123d.Wire] | None = None,
) -> build123d.Face:
    holes = list(interior_wires or [])
    return build123d.Face(exterior, holes) if holes else build123d.Face(exterior)


def _assemble_wire(edges: list[build123d.Edge]) -> build123d.Wire:
    wires = list(build123d.Wire.combine(edges))
    if len(wires) != 1:
        raise RuntimeError(f"Expected a single assembled wire, found {len(wires)}")
    return wires[0]


def _make_cylinder_along(
    *,
    radius: float,
    height: float,
    origin: build123d.Vector,
    direction: build123d.Vector,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        height,
        plane=build123d.Plane(origin=origin, z_dir=direction),
    )


def _vector_to_tuple(vector: build123d.Vector) -> tuple[float, float, float]:
    return (vector.X, vector.Y, vector.Z)


def _validate_bend_rule(rule: BendRule) -> None:
    bend_deduction_error = abs(rule.bend_deduction_90_mm - ((2.0 * rule.outside_setback_90_mm) - rule.bend_allowance_90_mm))
    if bend_deduction_error > 0.05:
        raise RuntimeError(
            "SendCutSend bend-rule constants are inconsistent: "
            f"bend deduction error {bend_deduction_error:.3f} mm is too large"
        )


def _extract_selector_shape(step_path: Path, selector: str) -> tuple[str, build123d.Shape]:
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    def _label_name(label: object) -> str:
        name = TDataStd_Name()
        if not label.FindAttribute(TDataStd_Name.GetID_s(), name):
            return "<unnamed>"
        return name.Get().ToExtString()

    def _resolve_label(shape_tool: object, label: object) -> object:
        if not shape_tool.IsReference_s(label):
            return label
        referred = TDF_Label()
        if shape_tool.GetReferredShape_s(label, referred):
            return referred
        return label

    def _child_components(shape_tool: object, label: object) -> list[object]:
        children = TDF_LabelSequence()
        ok = XCAFDoc_ShapeTool.GetComponents_s(label, children, False)
        resolved = _resolve_label(shape_tool, label)
        if (not ok or children.Length() <= 0) and resolved != label:
            children = TDF_LabelSequence()
            ok = XCAFDoc_ShapeTool.GetComponents_s(resolved, children, False)
        if not ok or children.Length() <= 0:
            return []
        return [children.Value(index) for index in range(1, children.Length() + 1)]

    def _shape_location(shape: object) -> build123d.Location:
        try:
            return build123d.Location(shape.Location().Transformation())
        except Exception:
            return build123d.Location()

    def located_shape(shape: object, location: build123d.Location | None) -> object:
        if location is None:
            return shape
        return shape.Located(location.wrapped)

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("servo_horn_yoke_doc"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    read_status = reader.ReadFile(str(step_path))
    if int(read_status) != 1:
        raise RuntimeError(f"Could not read {step_path} (status={int(read_status)})")
    if not reader.Transfer(doc):
        raise RuntimeError(f"Could not transfer STEP document from {step_path}")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    if free_labels.Length() <= 0:
        raise RuntimeError(f"No free shapes found in {step_path}")

    if not selector.startswith("xcaf:"):
        raise ValueError(f"Unsupported selector format: {selector}")
    segments = [int(value) for value in selector.split(":", 1)[1].split(".") if value]
    if not segments:
        raise ValueError(f"Selector does not contain XCAF path segments: {selector}")
    if segments[0] < 1 or segments[0] > free_labels.Length():
        raise RuntimeError(f"Selector root index is out of range for {step_path}: {selector}")

    label = free_labels.Value(segments[0])
    current_location: build123d.Location | None = None
    for index in segments[1:]:
        parent_location = _shape_location(shape_tool.GetShape_s(label))
        current_location = parent_location if current_location is None else current_location * parent_location
        children = _child_components(shape_tool, label)
        if index < 1 or index > len(children):
            raise RuntimeError(f"Selector segment {index} is out of range for {selector}")
        label = children[index - 1]

    resolved = _resolve_label(shape_tool, label)
    instance_shape = shape_tool.GetShape_s(label)
    resolved_shape = shape_tool.GetShape_s(resolved)
    base_shape = instance_shape if not instance_shape.IsNull() else resolved_shape
    if base_shape.IsNull():
        raise RuntimeError(f"Selector {selector} did not resolve to a shape")

    base_location = _shape_location(base_shape)
    current_location = base_location if current_location is None else current_location * base_location
    extracted = _cast_shape(located_shape(base_shape, current_location))
    return _label_name(label), extracted


def _wire_area(wire: build123d.Wire) -> float:
    return abs(_face_from_wire(wire).area)


def _outer_wire_and_inner_wires(face: build123d.Face) -> tuple[build123d.Wire, list[build123d.Wire]]:
    wires = list(face.wires())
    if not wires:
        raise RuntimeError("Face has no wires")

    outer_wire = max(wires, key=_wire_area)
    inner_wires = [wire for wire in wires if not wire.is_same(outer_wire)]
    return outer_wire, inner_wires


def _select_mount_face(shape: build123d.Shape, *, outward_sign: float) -> build123d.Face:
    shape_bb = shape.bounding_box()
    target_y = shape_bb.max.Y if outward_sign > 0.0 else shape_bb.min.Y
    candidates: list[tuple[float, build123d.Face]] = []
    for face in shape.faces():
        if face.geom_type.name != "PLANE":
            continue
        normal = face.normal_at()
        if outward_sign > 0.0 and normal.Y < 0.99:
            continue
        if outward_sign < 0.0 and normal.Y > -0.99:
            continue
        if abs(face.center().Y - target_y) > 0.25:
            continue
        candidates.append((face.area, face))

    if not candidates:
        raise RuntimeError(f"Could not find a horn mount face on y sign {outward_sign}")
    return max(candidates, key=lambda item: item[0])[1]


def _extract_circular_wire_profiles(face: build123d.Face) -> list[tuple[build123d.Vector, float]]:
    _outer_wire, inner_wires = _outer_wire_and_inner_wires(face)
    profiles: list[tuple[build123d.Vector, float]] = []
    for wire in inner_wires:
        circle_edges = [edge for edge in wire.edges() if edge.geom_type.name == "CIRCLE"]
        if not circle_edges:
            continue
        center = _face_from_wire(wire).center()
        radius = max(edge.radius for edge in circle_edges)
        profiles.append((center, radius))
    return profiles


def _extract_horn_mount_spec(shape: build123d.Shape, *, name: str, outward_sign: float) -> HornMountSpec:
    mount_face = _select_mount_face(shape, outward_sign=outward_sign)
    face_center = mount_face.center()
    shape_bbox = shape.bounding_box()
    profiles = _extract_circular_wire_profiles(mount_face)
    if not profiles:
        raise RuntimeError(f"No circular profiles found on horn mount face for {name}")

    center_profiles = [
        (center, radius)
        for center, radius in profiles
        if center.sub(face_center).length <= MOUNT_HOLE_MIN_OFFSET_MM
    ]
    if not center_profiles:
        raise RuntimeError(f"No center clearance profile found on horn mount face for {name}")
    center_clearance_radius = max(radius for _center, radius in center_profiles)

    mount_holes = [
        (center, radius)
        for center, radius in profiles
        if center.sub(face_center).length > MOUNT_HOLE_MIN_OFFSET_MM
    ]
    if len(mount_holes) != 4:
        raise RuntimeError(f"Expected 4 horn mount holes on {name}, found {len(mount_holes)}")

    mount_holes.sort(key=lambda item: (item[0].X, item[0].Z))
    return HornMountSpec(
        name=name,
        mount_face_y=face_center.Y,
        mount_face_center=face_center,
        mount_face_bbox=mount_face.bounding_box(),
        half_width_z=max(face_center.Z - shape_bbox.min.Z, shape_bbox.max.Z - face_center.Z),
        center_clearance_radius=center_clearance_radius,
        mount_holes=tuple(mount_holes),
    )


def _find_reference_face_x(shape: build123d.Shape) -> float:
    target = build123d.Vector(*SERVO_REFERENCE_FACE_TARGET_CENTER_MM)
    candidates: list[tuple[float, float, build123d.Face]] = []
    for face in shape.faces():
        if face.geom_type.name != "PLANE":
            continue
        normal = face.normal_at()
        if normal.X > -0.99:
            continue
        center = face.center()
        dist = center.sub(target).length
        candidates.append((dist, -face.area, face))

    if not candidates:
        raise RuntimeError("Could not find the requested negative-X reference face on the servo")

    dist, _neg_area, face = min(candidates, key=lambda item: (item[0], item[1]))
    if dist > SERVO_REFERENCE_FACE_MAX_ERROR_MM:
        raise RuntimeError(
            "Resolved servo reference face is too far from the requested target center: "
            f"{dist:.3f} mm > {SERVO_REFERENCE_FACE_MAX_ERROR_MM:.3f} mm"
        )
    return face.bounding_box().min.X


def _shape_half_width_z(shape: build123d.Shape) -> float:
    bbox = shape.bounding_box()
    return max(abs(bbox.min.Z), abs(bbox.max.Z))


def _load_generator_inputs() -> GeneratorInputs:
    _validate_bend_rule(SHEET_RULE)
    if not SERVO_STEP.exists():
        raise FileNotFoundError(f"Missing servo STEP: {SERVO_STEP}")

    servo_shape = import_as_shape(SERVO_STEP)
    reference_face_x = _find_reference_face_x(servo_shape)

    upper_label, upper_horn_shape = _extract_selector_shape(SERVO_STEP, UPPER_HORN_SELECTOR)
    lower_label, lower_horn_shape = _extract_selector_shape(SERVO_STEP, LOWER_HORN_SELECTOR)
    if upper_label != UPPER_HORN_NAME:
        raise RuntimeError(
            f"Expected upper horn selector {UPPER_HORN_SELECTOR} to resolve to {UPPER_HORN_NAME}, got {upper_label}"
        )
    if lower_label != LOWER_HORN_NAME:
        raise RuntimeError(
            f"Expected lower horn selector {LOWER_HORN_SELECTOR} to resolve to {LOWER_HORN_NAME}, got {lower_label}"
        )

    upper_horn = _extract_horn_mount_spec(upper_horn_shape, name=upper_label, outward_sign=1.0)
    lower_horn = _extract_horn_mount_spec(lower_horn_shape, name=lower_label, outward_sign=-1.0)
    return GeneratorInputs(
        servo_shape=servo_shape,
        reference_face_x=reference_face_x,
        sheet_half_width_z=_shape_half_width_z(servo_shape),
        upper_horn=upper_horn,
        lower_horn=lower_horn,
    )


def _make_box(*, x_min: float, x_max: float, y_min: float, y_max: float, z_min: float, z_max: float) -> build123d.Solid:
    return build123d.Solid.make_box(
        x_max - x_min,
        y_max - y_min,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y_min, z_min)),
    )


def _cap_hole_specs(horn: HornMountSpec) -> tuple[tuple[build123d.Vector, float], ...]:
    cap_holes = tuple(
        (center, M3_CLEARANCE_RADIUS_MM)
        for center, _radius in horn.mount_holes
        if abs(center.X - horn.mount_face_center.X) <= HORN_CAP_FLANGE_HOLE_X_TOLERANCE_MM
        and abs(center.Z - horn.mount_face_center.Z) > MOUNT_HOLE_MIN_OFFSET_MM
    )
    if len(cap_holes) != 2:
        raise RuntimeError(f"Expected 2 yoke cap holes on horn {horn.name}, found {len(cap_holes)}")
    return tuple(sorted(cap_holes, key=lambda item: item[0].Z))


def _web_side_hole_spec(horn: HornMountSpec) -> tuple[build123d.Vector, float]:
    side_holes = tuple(
        (center, radius)
        for center, radius in horn.mount_holes
        if center.X < horn.mount_face_center.X - HORN_CAP_FLANGE_HOLE_X_TOLERANCE_MM
        and abs(center.Z - horn.mount_face_center.Z) <= MOUNT_HOLE_MIN_OFFSET_MM
    )
    if len(side_holes) != 1:
        raise RuntimeError(f"Expected 1 web-side horn hole on horn {horn.name}, found {len(side_holes)}")
    return side_holes[0]


def _cap_z_bounds(horn: HornMountSpec, *, cap_radius: float) -> tuple[float, float]:
    cap_holes = _cap_hole_specs(horn)
    return (
        min(center.Z - cap_radius for center, _radius in cap_holes),
        max(center.Z + cap_radius for center, _radius in cap_holes),
    )


def _cap_end_x(horn: HornMountSpec, *, cap_radius: float) -> float:
    return max(center.X + cap_radius for center, _radius in _cap_hole_specs(horn))


def _capped_hole_flange_shapes(
    *,
    horn: HornMountSpec,
    web_inner_x: float,
    y_min: float,
    y_max: float,
    cap_radius: float,
) -> tuple[build123d.Shape, ...]:
    cap_holes = _cap_hole_specs(horn)
    side_center, _side_radius = _web_side_hole_spec(horn)
    slot_radius = HORN_FORK_SLOT_RADIUS_MM
    slot_center_x = horn.mount_face_center.X
    slot_left_x = slot_center_x - slot_radius
    cap_center_x = max(center.X for center, _radius in cap_holes)
    if abs(slot_center_x - cap_center_x) > HORN_CAP_FLANGE_HOLE_X_TOLERANCE_MM:
        raise RuntimeError(
            f"Expected yoke cap holes to share the fork slot center X on horn {horn.name}: "
            f"slot_center_x={slot_center_x:.3f}, cap_center_x={cap_center_x:.3f}"
        )
    if not web_inner_x < slot_left_x < slot_center_x:
        raise RuntimeError(
            f"Invalid yoke flange fork slot for horn {horn.name}: "
            f"web_inner_x={web_inner_x:.3f}, slot_left_x={slot_left_x:.3f}, "
            f"slot_center_x={slot_center_x:.3f}"
        )

    flange_shape: build123d.Shape = _make_box(
        x_min=web_inner_x,
        x_max=slot_center_x,
        y_min=y_min,
        y_max=y_max,
        z_min=min(center.Z - cap_radius for center, _radius in cap_holes),
        z_max=max(center.Z + cap_radius for center, _radius in cap_holes),
    )
    for center, _radius in cap_holes:
        cap = _make_cylinder_along(
            radius=cap_radius,
            height=y_max - y_min,
            origin=build123d.Vector(center.X, y_min, center.Z),
            direction=build123d.Vector(0.0, 1.0, 0.0),
        )
        flange_shape = flange_shape.fuse(cap)

    fork_slot = _make_cylinder_along(
        radius=slot_radius,
        height=(y_max - y_min) + (2.0 * CUT_EXTENSION_MM),
        origin=build123d.Vector(slot_center_x, y_min - CUT_EXTENSION_MM, side_center.Z),
        direction=build123d.Vector(0.0, 1.0, 0.0),
    )
    flange_shape = flange_shape.cut(fork_slot)
    return (flange_shape,)


def _web_pattern_center_from_values(
    *,
    web_outer_x: float,
    top_y_max: float,
    bottom_y_min: float,
    z_center: float,
) -> build123d.Vector:
    return build123d.Vector(
        web_outer_x,
        0.5 * (bottom_y_min + top_y_max),
        z_center,
    )


def _web_pattern_center(layout: BracketLayout) -> build123d.Vector:
    return _web_pattern_center_from_values(
        web_outer_x=layout.web_outer_x,
        top_y_max=layout.top_y_max,
        bottom_y_min=layout.bottom_y_min,
        z_center=0.5 * (layout.global_z_min + layout.global_z_max),
    )


def _center_hole_radius(horn: HornMountSpec) -> float:
    return max(HORN_CENTER_CLEARANCE_RADIUS_MM, horn.center_clearance_radius)


def _horn_face_hole_specs(horn: HornMountSpec) -> tuple[tuple[build123d.Vector, float], ...]:
    side_center, _side_radius = _web_side_hole_spec(horn)
    return (
        (side_center, M3_CLEARANCE_RADIUS_MM),
        *_cap_hole_specs(horn),
    )


def _web_round_hole_specs(
    layout: BracketLayout,
    *,
    horn: HornMountSpec,
) -> tuple[WebHoleSpec, ...]:
    center = _web_pattern_center(layout)
    specs = [
        WebHoleSpec(
            center_y=center.Y,
            center_z=center.Z,
            radius=_center_hole_radius(horn),
        )
    ]
    for mount_center, _radius in horn.mount_holes:
        specs.append(
            WebHoleSpec(
                center_y=center.Y + (mount_center.X - horn.mount_face_center.X),
                center_z=center.Z + (mount_center.Z - horn.mount_face_center.Z),
                radius=M3_CLEARANCE_RADIUS_MM,
            )
        )
    return tuple(specs)


def _bottom_face_slot_specs(layout: BracketLayout) -> tuple[SlotSpec, ...]:
    center_x = (
        layout.web_inner_x
        + BOTTOM_FACE_SLOT_BEND_EDGE_CLEARANCE_MM
        + (0.5 * BOTTOM_FACE_SLOT_WIDTH_MM)
    )
    slot_z_min = layout.global_z_min + BOTTOM_FACE_SLOT_END_GAP_MM
    slot_z_max = layout.global_z_max - BOTTOM_FACE_SLOT_END_GAP_MM
    slot_length = slot_z_max - slot_z_min
    if slot_length <= BOTTOM_FACE_SLOT_WIDTH_MM:
        raise ValueError(
            "Bottom face slot does not have enough length across the flange width "
            "after applying the flange-end gaps"
        )

    return (
        SlotSpec(
            center_x=center_x,
            center_z=0.5 * (slot_z_min + slot_z_max),
            length=slot_length,
            width=BOTTOM_FACE_SLOT_WIDTH_MM,
        ),
    )


def _make_y_slot_cut(
    *,
    slot: SlotSpec,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    radius = 0.5 * slot.width
    half_straight = 0.5 * slot.length - radius
    y_start = y_min - CUT_EXTENSION_MM
    y_height = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    body: build123d.Shape = _make_box(
        x_min=slot.center_x - radius,
        x_max=slot.center_x + radius,
        y_min=y_start,
        y_max=y_start + y_height,
        z_min=slot.center_z - half_straight,
        z_max=slot.center_z + half_straight,
    )
    for end_z in (slot.center_z - half_straight, slot.center_z + half_straight):
        cap = _make_cylinder_along(
            radius=radius,
            height=y_height,
            origin=build123d.Vector(slot.center_x, y_start, end_z),
            direction=build123d.Vector(0.0, 1.0, 0.0),
        )
        body = body.fuse(cap)
    return body


def _cut_round_horn_face_holes(
    shape: build123d.Shape,
    *,
    horn: HornMountSpec,
    start_y: float,
    direction_y: float,
    rule: BendRule,
) -> build123d.Shape:
    for center, radius in _horn_face_hole_specs(horn):
        cutter = _make_cylinder_along(
            radius=radius,
            height=rule.thickness_mm + (2.0 * CUT_EXTENSION_MM),
            origin=build123d.Vector(center.X, start_y, center.Z),
            direction=build123d.Vector(0.0, direction_y, 0.0),
        )
        shape = shape.cut(cutter)
    return shape


def _cut_bottom_face_slots(
    shape: build123d.Shape,
    *,
    layout: BracketLayout,
) -> build123d.Shape:
    for y_min, y_max in (
        (layout.top_y_min, layout.top_y_max),
        (layout.bottom_y_min, layout.bottom_y_max),
    ):
        for slot in _bottom_face_slot_specs(layout):
            shape = shape.cut(_make_y_slot_cut(slot=slot, y_min=y_min, y_max=y_max))
    return shape


def _cut_round_web_holes(
    shape: build123d.Shape,
    *,
    layout: BracketLayout,
    horn: HornMountSpec,
    rule: BendRule,
) -> build123d.Shape:
    start_x = layout.web_outer_x - CUT_EXTENSION_MM
    for hole in _web_round_hole_specs(layout, horn=horn):
        cutter = _make_cylinder_along(
            radius=hole.radius,
            height=rule.thickness_mm + (2.0 * CUT_EXTENSION_MM),
            origin=build123d.Vector(start_x, hole.center_y, hole.center_z),
            direction=build123d.Vector(1.0, 0.0, 0.0),
        )
        shape = shape.cut(cutter)
    return shape


def _make_bent_channel_body(
    *,
    top_end_x: float,
    bottom_end_x: float,
    layout: BracketLayout,
) -> build123d.Shape:
    # Build the channel body with sharp corners instead of formed bend radii.
    x_inner = layout.web_inner_x
    x_outer = layout.web_outer_x

    profile_points = [
        build123d.Vector(top_end_x, layout.top_y_max, 0.0),
        build123d.Vector(x_outer, layout.top_y_max, 0.0),
        build123d.Vector(x_outer, layout.bottom_y_min, 0.0),
        build123d.Vector(bottom_end_x, layout.bottom_y_min, 0.0),
        build123d.Vector(bottom_end_x, layout.bottom_y_max, 0.0),
        build123d.Vector(x_inner, layout.bottom_y_max, 0.0),
        build123d.Vector(x_inner, layout.top_y_min, 0.0),
        build123d.Vector(top_end_x, layout.top_y_min, 0.0),
    ]
    profile_edges = [
        build123d.Edge.make_line(profile_points[0], profile_points[1]),
        build123d.Edge.make_line(profile_points[1], profile_points[2]),
        build123d.Edge.make_line(profile_points[2], profile_points[3]),
        build123d.Edge.make_line(profile_points[3], profile_points[4]),
        build123d.Edge.make_line(profile_points[4], profile_points[5]),
        build123d.Edge.make_line(profile_points[5], profile_points[6]),
        build123d.Edge.make_line(profile_points[6], profile_points[7]),
        build123d.Edge.make_line(profile_points[7], profile_points[0]),
    ]
    face = _face_from_wire(_assemble_wire(profile_edges))
    return build123d.Solid.extrude(
        face,
        build123d.Vector(0.0, 0.0, layout.global_z_max - layout.global_z_min),
    ).translate((0.0, 0.0, layout.global_z_min))


def _min_horn_face_feature_edge_to_bend_line(
    horn: HornMountSpec,
    *,
    bend_line_u: float,
) -> float:
    return min(
        (center.X - radius) - bend_line_u
        for center, radius in _horn_face_hole_specs(horn)
    )


def _min_web_feature_edge_to_bend_lines(
    *,
    layout: BracketLayout,
    horn: HornMountSpec,
) -> float:
    distances: list[float] = []
    for hole in _web_round_hole_specs(layout, horn=horn):
        distances.append((hole.center_y - hole.radius) - layout.bottom_y_max)
        distances.append(layout.top_y_min - (hole.center_y + hole.radius))
    return min(distances)


def _min_bottom_face_slot_edge_to_bend_line(layout: BracketLayout) -> float:
    return min(
        (slot.center_x - (0.5 * slot.width)) - layout.web_inner_x
        for slot in _bottom_face_slot_specs(layout)
    )


def _build_metrics(
    *,
    upper_horn: HornMountSpec,
    lower_horn: HornMountSpec,
    layout: BracketLayout,
    rule: BendRule,
) -> BracketMetrics:
    upper_outside_length = upper_horn.mount_face_center.X - layout.web_outer_x
    lower_outside_length = lower_horn.mount_face_center.X - layout.web_outer_x
    min_flange_outside_length = min(upper_outside_length, lower_outside_length)
    min_flange_flat_length = rule.flat_length_from_outside_length_90(min_flange_outside_length)
    bend_line_spacing = layout.top_y_min - layout.bottom_y_max

    min_hole_edge_to_bend = min(
        _min_horn_face_feature_edge_to_bend_line(upper_horn, bend_line_u=layout.web_inner_x),
        _min_horn_face_feature_edge_to_bend_line(lower_horn, bend_line_u=layout.web_inner_x),
    )
    min_slot_edge_to_bend = _min_bottom_face_slot_edge_to_bend_line(layout)
    min_web_feature_edge_to_bend = _min_web_feature_edge_to_bend_lines(
        layout=layout,
        horn=upper_horn,
    )

    max_flange_outside = max(upper_outside_length, lower_outside_length)
    base_to_flange_ratio = bend_line_spacing / max_flange_outside

    return BracketMetrics(
        min_flange_outside_length_mm=min_flange_outside_length,
        min_flange_flat_length_mm=min_flange_flat_length,
        bend_line_spacing_mm=bend_line_spacing,
        min_hole_edge_to_bend_mm=min_hole_edge_to_bend,
        min_slot_edge_to_bend_mm=min_slot_edge_to_bend,
        min_web_feature_edge_to_bend_mm=min_web_feature_edge_to_bend,
        base_to_flange_ratio=base_to_flange_ratio,
        bend_deduction_formula_mm=(2.0 * rule.outside_setback_90_mm) - rule.bend_allowance_90_mm,
    )


def _validate_metrics(metrics: BracketMetrics, *, rule: BendRule) -> None:
    if metrics.min_flange_outside_length_mm < rule.min_flange_formed_mm:
        raise RuntimeError(
            "Flange is shorter than the configured bend-rule formed minimum: "
            f"{metrics.min_flange_outside_length_mm:.3f} mm < {rule.min_flange_formed_mm:.3f} mm"
        )
    if metrics.min_flange_flat_length_mm < rule.min_flange_flat_mm:
        raise RuntimeError(
            "Flat flange length implied by the bend rule is too short: "
            f"{metrics.min_flange_flat_length_mm:.3f} mm < {rule.min_flange_flat_mm:.3f} mm"
        )
    if metrics.bend_line_spacing_mm < rule.channel_base_spacing_min_mm:
        raise RuntimeError(
            "Channel base spacing is below the SendCutSend consecutive-bend minimum: "
            f"{metrics.bend_line_spacing_mm:.3f} mm < {rule.channel_base_spacing_min_mm:.3f} mm"
        )
    if metrics.min_hole_edge_to_bend_mm < rule.half_die_width_mm:
        raise RuntimeError(
            "Horn flange features are too close to the bend die region: "
            f"{metrics.min_hole_edge_to_bend_mm:.3f} mm < {rule.half_die_width_mm:.3f} mm"
        )
    if metrics.min_slot_edge_to_bend_mm < rule.half_die_width_mm:
        raise RuntimeError(
            "Horn flange bottom slots are too close to the bend die region: "
            f"{metrics.min_slot_edge_to_bend_mm:.3f} mm < {rule.half_die_width_mm:.3f} mm"
        )
    if metrics.min_web_feature_edge_to_bend_mm < rule.half_die_width_mm:
        raise RuntimeError(
            "Closing-face horn pattern is too close to a bend die region: "
            f"{metrics.min_web_feature_edge_to_bend_mm:.3f} mm < {rule.half_die_width_mm:.3f} mm"
        )
    if metrics.min_flange_outside_length_mm <= rule.channel_one_to_one_max_flange_mm and metrics.base_to_flange_ratio < 1.0:
        raise RuntimeError(
            "U-channel base-to-flange ratio is below the configured 1:1 manufacturing check for this stock: "
            f"{metrics.base_to_flange_ratio:.3f} < 1.000"
        )


def _build_layout(
    reference_face_x: float,
    *,
    sheet_half_width_z: float,
    upper_horn: HornMountSpec,
    lower_horn: HornMountSpec,
    rule: BendRule,
) -> tuple[BracketLayout, float]:
    web_outer_x = SERVO_HORN_AXIS_X_MM - YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM
    web_inner_x = web_outer_x + rule.thickness_mm

    top_y_min = upper_horn.mount_face_y + HORN_FACE_GAP_MM
    top_y_max = top_y_min + rule.thickness_mm
    bottom_y_max = lower_horn.mount_face_y - HORN_FACE_GAP_MM
    bottom_y_min = bottom_y_max - rule.thickness_mm

    cap_radius = HORN_CAP_FLANGE_RADIUS_MM

    top_z_min, top_z_max = _cap_z_bounds(upper_horn, cap_radius=cap_radius)
    bottom_z_min, bottom_z_max = _cap_z_bounds(lower_horn, cap_radius=cap_radius)
    global_z_min = min(top_z_min, bottom_z_min)
    global_z_max = max(top_z_max, bottom_z_max)

    layout = BracketLayout(
        web_inner_x=web_inner_x,
        web_outer_x=web_outer_x,
        top_y_min=top_y_min,
        top_y_max=top_y_max,
        bottom_y_min=bottom_y_min,
        bottom_y_max=bottom_y_max,
        top_z_min=top_z_min,
        top_z_max=top_z_max,
        bottom_z_min=bottom_z_min,
        bottom_z_max=bottom_z_max,
        global_z_min=global_z_min,
        global_z_max=global_z_max,
    )
    return layout, cap_radius


def build_bracket(
    reference_face_x: float,
    *,
    sheet_half_width_z: float,
    upper_horn: HornMountSpec,
    lower_horn: HornMountSpec,
    rule: BendRule,
    validate_metrics: bool = True,
) -> tuple[build123d.Shape, BracketLayout, BracketMetrics]:
    layout, cap_radius = _build_layout(
        reference_face_x,
        sheet_half_width_z=sheet_half_width_z,
        upper_horn=upper_horn,
        lower_horn=lower_horn,
        rule=rule,
    )
    web_inner_x = layout.web_inner_x
    web_outer_x = layout.web_outer_x
    top_y_min = layout.top_y_min
    top_y_max = layout.top_y_max
    bottom_y_min = layout.bottom_y_min
    bottom_y_max = layout.bottom_y_max
    global_z_min = layout.global_z_min
    global_z_max = layout.global_z_max

    bracket = _make_bent_channel_body(
        top_end_x=_cap_end_x(upper_horn, cap_radius=cap_radius),
        bottom_end_x=_cap_end_x(lower_horn, cap_radius=cap_radius),
        layout=layout,
    )
    cap_mask: build123d.Shape = _make_box(
        x_min=web_outer_x,
        x_max=web_inner_x,
        y_min=bottom_y_min,
        y_max=top_y_max,
        z_min=global_z_min,
        z_max=global_z_max,
    )
    for flange_shape in (
        *_capped_hole_flange_shapes(
            horn=upper_horn,
            web_inner_x=web_inner_x,
            y_min=top_y_min,
            y_max=top_y_max,
            cap_radius=cap_radius,
        ),
        *_capped_hole_flange_shapes(
            horn=lower_horn,
            web_inner_x=web_inner_x,
            y_min=bottom_y_min,
            y_max=bottom_y_max,
            cap_radius=cap_radius,
        ),
    ):
        cap_mask = cap_mask.fuse(flange_shape)
    bracket = as_single_shape(bracket.intersect(cap_mask))

    top_start_y = top_y_max + CUT_EXTENSION_MM
    bracket = _cut_round_horn_face_holes(
        bracket,
        horn=upper_horn,
        start_y=top_start_y,
        direction_y=-1.0,
        rule=rule,
    )

    bottom_start_y = bottom_y_min - CUT_EXTENSION_MM
    bracket = _cut_round_horn_face_holes(
        bracket,
        horn=lower_horn,
        start_y=bottom_start_y,
        direction_y=1.0,
        rule=rule,
    )

    bracket = _cut_bottom_face_slots(
        bracket,
        layout=layout,
    )

    bracket = _cut_round_web_holes(
        bracket,
        layout=layout,
        horn=upper_horn,
        rule=rule,
    )
    metrics = _build_metrics(
        upper_horn=upper_horn,
        lower_horn=lower_horn,
        layout=layout,
        rule=rule,
    )
    if validate_metrics:
        _validate_metrics(metrics, rule=rule)
    return bracket, layout, metrics


def build_flat_pattern(
    reference_face_x: float,
    *,
    sheet_half_width_z: float,
    upper_horn: HornMountSpec,
    lower_horn: HornMountSpec,
    rule: BendRule,
) -> tuple[FlatPattern, BracketMetrics]:
    if abs(upper_horn.mount_face_center.Z - lower_horn.mount_face_center.Z) > 1e-6:
        raise RuntimeError("Flat-pattern export currently requires the horn faces to share the same Z centerline")

    layout, cap_radius = _build_layout(
        reference_face_x,
        sheet_half_width_z=sheet_half_width_z,
        upper_horn=upper_horn,
        lower_horn=lower_horn,
        rule=rule,
    )
    metrics = _build_metrics(
        upper_horn=upper_horn,
        lower_horn=lower_horn,
        layout=layout,
        rule=rule,
    )
    _validate_metrics(metrics, rule=rule)

    top_end_x = _cap_end_x(upper_horn, cap_radius=cap_radius)
    bottom_end_x = _cap_end_x(lower_horn, cap_radius=cap_radius)
    top_outside_length = top_end_x - layout.web_outer_x
    bottom_outside_length = bottom_end_x - layout.web_outer_x
    top_flat_length = top_outside_length - rule.outside_setback_90_mm
    bottom_flat_length = bottom_outside_length - rule.outside_setback_90_mm

    bend_allowance = rule.bend_allowance_90_mm
    top_web_tangent_y = layout.top_y_min - rule.effective_inside_radius_mm
    bottom_web_tangent_y = layout.bottom_y_max + rule.effective_inside_radius_mm
    web_flat_length = top_web_tangent_y - bottom_web_tangent_y
    total_flat_length = top_flat_length + bend_allowance + web_flat_length + bend_allowance + bottom_flat_length
    flat_width = layout.global_z_max - layout.global_z_min
    top_bend_line_x = top_flat_length + (0.5 * bend_allowance)
    bottom_bend_line_x = top_flat_length + bend_allowance + web_flat_length + (0.5 * bend_allowance)

    upper_hole_profiles = tuple(
        CircleProfileSpec(
            center_x=top_end_x - center.X,
            center_y=center.Z - layout.global_z_min,
            radius=radius,
        )
        for center, radius in _horn_face_hole_specs(upper_horn)
    )
    web_hole_profiles = tuple(
        CircleProfileSpec(
            center_x=top_flat_length + bend_allowance + (top_web_tangent_y - hole.center_y),
            center_y=hole.center_z - layout.global_z_min,
            radius=hole.radius,
        )
        for hole in _web_round_hole_specs(layout, horn=upper_horn)
    )
    lower_hole_profiles = tuple(
        CircleProfileSpec(
            center_x=total_flat_length - (bottom_end_x - center.X),
            center_y=center.Z - layout.global_z_min,
            radius=radius,
        )
        for center, radius in _horn_face_hole_specs(lower_horn)
    )
    round_hole_profiles = upper_hole_profiles + web_hole_profiles + lower_hole_profiles
    upper_slot_profiles = tuple(
        SlotProfileSpec(
            center_x=top_end_x - slot.center_x,
            center_y=slot.center_z - layout.global_z_min,
            length=slot.length,
            width=slot.width,
        )
        for slot in _bottom_face_slot_specs(layout)
    )
    lower_slot_profiles = tuple(
        SlotProfileSpec(
            center_x=total_flat_length - (bottom_end_x - slot.center_x),
            center_y=slot.center_z - layout.global_z_min,
            length=slot.length,
            width=slot.width,
        )
        for slot in _bottom_face_slot_specs(layout)
    )

    return (
        FlatPattern(
            total_length_mm=total_flat_length,
            width_mm=flat_width,
            cap_radius_mm=cap_radius,
            bend_line_positions_mm=(top_bend_line_x, bottom_bend_line_x),
            round_hole_profiles=round_hole_profiles,
            slot_profiles=upper_slot_profiles + lower_slot_profiles,
        ),
        metrics,
    )


def _slot_profile_points(slot: SlotProfileSpec, *, segments_per_cap: int = 12) -> list[tuple[float, float]]:
    radius = 0.5 * slot.width
    half_straight = 0.5 * slot.length - radius
    bottom_y = slot.center_y - half_straight
    top_y = slot.center_y + half_straight

    points: list[tuple[float, float]] = []
    for index in range(segments_per_cap + 1):
        angle = 0.0 + (180.0 * index / segments_per_cap)
        points.append(
            (
                slot.center_x + radius * math.cos(math.radians(angle)),
                top_y + radius * math.sin(math.radians(angle)),
            )
        )
    for index in range(segments_per_cap + 1):
        angle = 180.0 + (180.0 * index / segments_per_cap)
        points.append(
            (
                slot.center_x + radius * math.cos(math.radians(angle)),
                bottom_y + radius * math.sin(math.radians(angle)),
            )
        )
    return points


def _arc_points_2d(
    *,
    center: tuple[float, float],
    radius: float,
    start_deg: float,
    end_deg: float,
    segments: int,
    include_start: bool = False,
) -> list[tuple[float, float]]:
    start_index = 0 if include_start else 1
    return [
        (
            center[0] + radius * math.cos(math.radians(start_deg + ((end_deg - start_deg) * index / segments))),
            center[1] + radius * math.sin(math.radians(start_deg + ((end_deg - start_deg) * index / segments))),
        )
        for index in range(start_index, segments + 1)
    ]


def _outer_outline_points(flat_pattern: FlatPattern, *, segments_per_lobe: int = 24) -> list[tuple[float, float]]:
    radius = flat_pattern.cap_radius_mm
    width = flat_pattern.width_mm
    total_length = flat_pattern.total_length_mm
    lower_lobe_top_y = 2.0 * radius
    upper_lobe_bottom_y = width - (2.0 * radius)
    if upper_lobe_bottom_y < lower_lobe_top_y - 1e-6:
        raise RuntimeError(
            "Yoke flat-pattern cap lobes overlap; closed outline export needs a wider flat pattern "
            f"or smaller cap radius (width={width:.3f}, radius={radius:.3f})"
        )

    right_x = total_length - radius
    left_x = radius
    points: list[tuple[float, float]] = [
        (left_x, 0.0),
        (right_x, 0.0),
    ]
    points.extend(
        _arc_points_2d(
            center=(right_x, radius),
            radius=radius,
            start_deg=-90.0,
            end_deg=90.0,
            segments=segments_per_lobe,
        )
    )
    if upper_lobe_bottom_y > lower_lobe_top_y + 1e-6:
        points.append((right_x, upper_lobe_bottom_y))
    points.extend(
        _arc_points_2d(
            center=(right_x, width - radius),
            radius=radius,
            start_deg=-90.0,
            end_deg=90.0,
            segments=segments_per_lobe,
        )
    )
    points.append((left_x, width))
    points.extend(
        _arc_points_2d(
            center=(left_x, width - radius),
            radius=radius,
            start_deg=90.0,
            end_deg=270.0,
            segments=segments_per_lobe,
        )
    )
    if upper_lobe_bottom_y > lower_lobe_top_y + 1e-6:
        points.append((left_x, lower_lobe_top_y))
    points.extend(
        _arc_points_2d(
            center=(left_x, radius),
            radius=radius,
            start_deg=90.0,
            end_deg=270.0,
            segments=segments_per_lobe,
        )
    )
    if points[-1] == points[0]:
        points.pop()
    return points


def _build_flat_pattern_dxf(flat_pattern: FlatPattern) -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = DXF_UNIT_MM
    if "CUT" not in doc.layers:
        doc.layers.add("CUT")
    if "BEND" not in doc.layers:
        doc.layers.add("BEND", linetype="DASHED")

    msp = doc.modelspace()
    msp.add_lwpolyline(
        _outer_outline_points(flat_pattern),
        close=True,
        dxfattribs={"layer": "CUT"},
    )

    for round_hole in flat_pattern.round_hole_profiles:
        msp.add_circle(
            (round_hole.center_x, round_hole.center_y),
            radius=round_hole.radius,
            dxfattribs={"layer": "CUT"},
        )
    for slot in flat_pattern.slot_profiles:
        msp.add_lwpolyline(
            _slot_profile_points(slot),
            close=True,
            dxfattribs={"layer": "CUT"},
        )

    for bend_line_x in flat_pattern.bend_line_positions_mm:
        msp.add_line(
            (bend_line_x, 0.0),
            (bend_line_x, flat_pattern.width_mm),
            dxfattribs={"layer": "BEND", "linetype": "DASHED"},
        )
    return doc


def _topology_flat_pattern_dxf(
    bracket: build123d.Shape,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
    *,
    upper_horn: HornMountSpec,
    lower_horn: HornMountSpec,
    rule: BendRule,
) -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = DXF_UNIT_MM
    if "CUT" not in doc.layers:
        doc.layers.add("CUT")
    if "BEND" not in doc.layers:
        doc.layers.add("BEND", linetype="DASHED")

    top_end_x = _cap_end_x(upper_horn, cap_radius=flat_pattern.cap_radius_mm)
    bottom_end_x = _cap_end_x(lower_horn, cap_radius=flat_pattern.cap_radius_mm)
    top_flat_length = (top_end_x - layout.web_outer_x) - rule.outside_setback_90_mm
    bottom_flat_length = (bottom_end_x - layout.web_outer_x) - rule.outside_setback_90_mm
    bottom_flat_start = flat_pattern.total_length_mm - bottom_flat_length
    web_source_span = layout.top_y_min - layout.bottom_y_max
    web_flat_span = bottom_flat_start - top_flat_length
    if top_flat_length <= 0.0 or bottom_flat_length <= 0.0 or web_source_span <= 0.0 or web_flat_span <= 0.0:
        raise RuntimeError("Yoke topology DXF has invalid flat-pattern spans")

    def project_top(point: build123d.Vector) -> tuple[float, float]:
        if abs(point.X - layout.web_outer_x) <= 1e-3:
            u = top_flat_length
        else:
            u = top_end_x - point.X
        return (u, point.Z - layout.global_z_min)

    def project_web(point: build123d.Vector) -> tuple[float, float]:
        t = (layout.top_y_min - point.Y) / web_source_span
        return (
            top_flat_length + (t * web_flat_span),
            point.Z - layout.global_z_min,
        )

    def project_bottom(point: build123d.Vector) -> tuple[float, float]:
        if abs(point.X - layout.web_outer_x) <= 1e-3:
            u = bottom_flat_start
        else:
            u = flat_pattern.total_length_mm - (bottom_end_x - point.X)
        return (u, point.Z - layout.global_z_min)

    top_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="y",
        normal_sign=1.0,
        coordinate_axis="y",
        coordinate=layout.top_y_max,
    )
    web_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="x",
        normal_sign=1.0,
        coordinate_axis="x",
        coordinate=layout.web_inner_x,
    )
    bottom_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="y",
        normal_sign=-1.0,
        coordinate_axis="y",
        coordinate=layout.bottom_y_min,
    )
    geometry = dxf_topology.union_projected_faces(
        (
            (top_faces, project_top),
            (web_faces, project_web),
            (bottom_faces, project_bottom),
        )
    )
    dxf_topology.add_shapely_geometry(doc.modelspace(), geometry, layer="CUT")

    for bend_line_x in flat_pattern.bend_line_positions_mm:
        doc.modelspace().add_line(
            (bend_line_x, 0.0),
            (bend_line_x, flat_pattern.width_mm),
            dxfattribs={"layer": "BEND", "linetype": "DASHED"},
        )
    return doc


def _orient_for_standalone_floor(shape: build123d.Shape) -> build123d.Shape:
    rotated = shape.rotate(STANDALONE_FLOOR_ROTATION_AXIS, STANDALONE_FLOOR_ROTATION_DEG)
    rotated_bb = rotated.bounding_box()
    return rotated.translate((0.0, 0.0, -rotated_bb.min.Z))


def build_step() -> build123d.Shape:
    CAD_DIR.mkdir(parents=True, exist_ok=True)
    inputs = _load_generator_inputs()
    bracket, layout, metrics = build_bracket(
        inputs.reference_face_x,
        sheet_half_width_z=inputs.sheet_half_width_z,
        upper_horn=inputs.upper_horn,
        lower_horn=inputs.lower_horn,
        rule=SHEET_RULE,
    )

    solids = bracket.solids()
    if len(solids) != 1:
        raise RuntimeError(f"Expected one connected bracket solid, found {len(solids)}")

    interference_volume = intersection_volume(inputs.servo_shape, bracket)
    if interference_volume > 1e-3:
        raise RuntimeError(f"Bracket intersects the servo by {interference_volume:.6f} mm^3")

    bracket_bb = bracket.bounding_box()
    bottom_slots = _bottom_face_slot_specs(layout)
    bottom_slot_length = bottom_slots[0].length if bottom_slots else 0.0
    print(
        "Bracket envelope "
        f"X={bracket_bb.size.X:.3f} mm, "
        f"Y={bracket_bb.size.Y:.3f} mm, "
        f"Z={bracket_bb.size.Z:.3f} mm"
    )
    print(
        "Connection features "
        f"face_patterns=3, "
        f"horn_flange_m3_holes_per_pattern={len(_horn_face_hole_specs(inputs.upper_horn))}x"
        f"{2.0 * M3_CLEARANCE_RADIUS_MM:.3f} mm, "
        f"cap_flange_radius={HORN_CAP_FLANGE_RADIUS_MM:.3f} mm, "
        f"fork_slot_radius={HORN_FORK_SLOT_RADIUS_MM:.3f} mm, "
        f"bottom_slots={2 * len(bottom_slots)}x"
        f"{bottom_slot_length:.3f}x{BOTTOM_FACE_SLOT_WIDTH_MM:.3f} mm, "
        f"removed_center_and_far_side_hole=true"
    )
    print(
        "SendCutSend bend rule "
        f"material={SHEET_RULE.material_name}, "
        f"thickness={SHEET_RULE.thickness_mm:.3f} mm, "
        f"inside_radius={SHEET_RULE.effective_inside_radius_mm:.3f} mm, "
        f"outer_radius={SHEET_RULE.outer_radius_mm:.3f} mm, "
        f"k_factor={SHEET_RULE.k_factor:.2f}, "
        f"bend_deduction_90={SHEET_RULE.bend_deduction_90_mm:.3f} mm"
    )
    print(
        "SendCutSend checks "
        f"flange_outside_min={metrics.min_flange_outside_length_mm:.3f} mm, "
        f"flange_flat_min={metrics.min_flange_flat_length_mm:.3f} mm, "
        f"bend_spacing={metrics.bend_line_spacing_mm:.3f} mm, "
        f"hole_edge_to_bend_min={metrics.min_hole_edge_to_bend_mm:.3f} mm, "
        f"slot_edge_to_bend_min={metrics.min_slot_edge_to_bend_mm:.3f} mm, "
        f"web_feature_edge_to_bend_min={metrics.min_web_feature_edge_to_bend_mm:.3f} mm, "
        f"base_to_flange_ratio={metrics.base_to_flange_ratio:.3f}"
    )
    print(
        "Bracket placement "
        f"inner_web_x={layout.web_inner_x:.3f} mm, "
        f"outer_web_x={layout.web_outer_x:.3f} mm, "
        f"outer_web_to_horn_axis={YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM:.3f} mm, "
        f"outer_web_to_cap_tip={bracket_bb.size.X:.3f} mm, "
        f"reference_face_x={inputs.reference_face_x:.3f} mm, "
        f"reference_clearance={inputs.reference_face_x - layout.web_inner_x:.3f} mm"
    )
    print(
        "Upper horn "
        f"selector={UPPER_HORN_SELECTOR}, face_y={inputs.upper_horn.mount_face_y:.3f} mm, "
        f"m3_holes={len(_horn_face_hole_specs(inputs.upper_horn))}, "
        f"cap_flange_radius={HORN_CAP_FLANGE_RADIUS_MM:.3f} mm"
    )
    print(
        "Lower horn "
        f"selector={LOWER_HORN_SELECTOR}, face_y={inputs.lower_horn.mount_face_y:.3f} mm, "
        f"m3_holes={len(_horn_face_hole_specs(inputs.lower_horn))}, "
        f"cap_flange_radius={HORN_CAP_FLANGE_RADIUS_MM:.3f} mm"
    )
    print(f"Servo/bracket interference volume (mm^3): {interference_volume:.6f}")

    oriented_bracket = _orient_for_standalone_floor(bracket)
    oriented_bb = oriented_bracket.bounding_box()
    print(
        "Standalone orientation "
        f"rotate_axis=Y, rotate={STANDALONE_FLOOR_ROTATION_DEG:.1f} deg, "
        f"floor_z={oriented_bb.min.Z:.3f} mm, "
        f"oriented_envelope X={oriented_bb.size.X:.3f} mm, "
        f"Y={oriented_bb.size.Y:.3f} mm, "
        f"Z={oriented_bb.size.Z:.3f} mm"
    )
    oriented_bracket.label = PART_NAME
    oriented_bracket.color = GRAY_ALUMINUM_COLOR
    return oriented_bracket


def build_dxf() -> ezdxf.document.Drawing:
    CAD_DIR.mkdir(parents=True, exist_ok=True)
    inputs = _load_generator_inputs()
    bracket, layout, metrics = build_bracket(
        inputs.reference_face_x,
        sheet_half_width_z=inputs.sheet_half_width_z,
        upper_horn=inputs.upper_horn,
        lower_horn=inputs.lower_horn,
        rule=SHEET_RULE,
    )
    flat_pattern, metrics = build_flat_pattern(
        inputs.reference_face_x,
        sheet_half_width_z=inputs.sheet_half_width_z,
        upper_horn=inputs.upper_horn,
        lower_horn=inputs.lower_horn,
        rule=SHEET_RULE,
    )
    doc = _topology_flat_pattern_dxf(
        bracket,
        layout,
        flat_pattern,
        upper_horn=inputs.upper_horn,
        lower_horn=inputs.lower_horn,
        rule=SHEET_RULE,
    )
    print(
        "Flat pattern "
        f"length={flat_pattern.total_length_mm:.3f} mm, "
        f"width={flat_pattern.width_mm:.3f} mm, "
        f"bend_lines=({flat_pattern.bend_line_positions_mm[0]:.3f}, {flat_pattern.bend_line_positions_mm[1]:.3f}) mm, "
        f"round_holes={len(flat_pattern.round_hole_profiles)}, "
        f"slots={len(flat_pattern.slot_profiles)}"
    )
    print(
        "DXF checks "
        f"flange_flat_min={metrics.min_flange_flat_length_mm:.3f} mm, "
        f"bend_spacing={metrics.bend_line_spacing_mm:.3f} mm, "
        f"hole_edge_to_bend_min={metrics.min_hole_edge_to_bend_mm:.3f} mm, "
        f"slot_edge_to_bend_min={metrics.min_slot_edge_to_bend_mm:.3f} mm, "
        f"web_feature_edge_to_bend_min={metrics.min_web_feature_edge_to_bend_mm:.3f} mm"
    )
    return doc


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
