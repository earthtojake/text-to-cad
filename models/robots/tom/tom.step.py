from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
TOM_DIR = V2_DIR
ASSEMBLIES_DIR = V2_DIR / "assemblies"
PARTS_DIR = V2_DIR / "parts"
for path in (TOM_DIR, V2_DIR, PARTS_DIR, ASSEMBLIES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robot_common import robot_arm
from robot_common.materials import BLACK_ALUMINUM_RGBA, GRAY_ALUMINUM_RGBA
from robot_common.step_entry import load_step_entry

servo_end_mount = load_step_entry("servo_end_mount")
servo_horn_yoke = load_step_entry("servo_horn_yoke")
from v2_roll_link_common import (
    invert_rigid_transform,
    multiply_transforms,
    roll_link_mates,
    roll_link_instances,
)


LINK_ASSEMBLY_MODULES = {
    "base_link": ASSEMBLIES_DIR / "base_link.step.py",
    "shoulder_yaw_link": ASSEMBLIES_DIR / "shoulder_yaw_link.step.py",
    "shoulder_pitch_link": ASSEMBLIES_DIR / "pitch_link_sts3250.step.py",
    "elbow_pitch_link": ASSEMBLIES_DIR / "pitch_link_sts3215.step.py",
    "wrist_pitch_link": ASSEMBLIES_DIR / "pitch_link_sts3215.step.py",
}

ROLL_LINK_REPLACEMENTS = {
    "shoulder_roll_link": "shoulder",
    "elbow_roll_link": "elbow",
}

GRIPPER_CHILD_NAME = "parallel_gripper"
# The wrist's terminal sts3215 servo (#o1.33) is removed; the gripper mounts
# directly to the wrist servo_horn_yoke (#o1.32) where that servo used to seat.
V2_WRIST_TERMINAL_SERVO_INSTANCE_NAME = "wrist_pitch_link__sts3215"
V2_GRIPPER_MOUNT_INSTANCE_NAME = "wrist_pitch_link__servo_horn_yoke"
# Snap the gripper mount face (#o1.25.1.5.f82) flush onto the yoke face (#o1.24.f1): both are
# planes at y=-237.8 with opposite normals, offset by (yoke - gripper) face centers in the
# home-pose frame. Re-derive via inspect if the wrist geometry changes.
GRIPPER_FACE_TO_YOKE_FACE_OFFSET_MM = (-1.45148, 0.0, 35.61)

NEXT_PITCH_LINK_BY_ROLL_LINK = {
    "shoulder": "elbow_pitch_link",
    "elbow": "wrist_pitch_link",
}

# Source STEP face datums for the terminal gripper mate:
# - sts3215 #o1.16.f14 is the rear horn face at local y=-27.4.
# - gripper #o1.5.f82 is the mounting face at local z=-52.
STS3215_HORN_AXIS_LOCAL_X_MM = -25.5
STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM = 9.2
STS3215_REAR_HORN_FACE_LOCAL_Y_MM = -27.4
GRIPPER_MOUNT_FACE_CENTER_LOCAL_MM = (0.032382, 0.002077, -52.0)
BASE_TO_SHOULDER_YAW_HORN_CLEARANCE_MM = 0.0
SERVO_END_MOUNT_FRONT_HORN_FACE_CENTER_LOCAL_MM = (
    servo_end_mount.front_horn_mount_face_center_local_mm()
)
YOKE_180_ABOUT_WEB_AXIS_TRANSFORM = tuple(
    servo_horn_yoke.YOKE_180_ABOUT_WEB_AXIS_DESIGN_TRANSFORM
)
PITCH_MODULE_STANDALONE_TO_DESIGN_TRANSFORM = tuple(
    servo_horn_yoke.STANDALONE_TO_DESIGN_TRANSFORM
)

URDF_MATERIALS = {
    "aluminum_5052": GRAY_ALUMINUM_RGBA,
    "dark_servo": BLACK_ALUMINUM_RGBA,
    "silver_aluminum_alloy": (0.78, 0.80, 0.82, 1.0),
    "circuit_board_green": (0.07, 0.36, 0.17, 1.0),
}

URDF_MESH_BY_STEP_BASENAME = {
    "base_plate.step": "3MF/base_plate.3mf",
    "servo_end_mount.step": "3MF/servo_end_mount.3mf",
    "servo_horn_yoke.step": "3MF/servo_horn_yoke.3mf",
    "link_bracket_right.step": "3MF/link_bracket_right.3mf",
    "link_bracket_left.step": "3MF/link_bracket_left.3mf",
    "link_standoff_m3_35.step": "3MF/link_standoff_m3_35.3mf",
    "sts3250.step": "3MF/sts3250.3mf",
    "sts3215.step": "3MF/sts3215.3mf",
    "base_clamp.step": "3MF/base_clamp.3mf",
    "m2_spacer_5mm.step": "3MF/m2_spacer_5mm.3mf",
    "m2_5_hex_spacer_6mm.step": "3MF/m2_5_hex_spacer_6mm.3mf",
    "waveshare_bus_servo_adapter_a.step": "3MF/waveshare_bus_servo_adapter_a.3mf",
}

URDF_MATERIAL_BY_STEP_BASENAME = {
    "base_plate.step": "aluminum_5052",
    "servo_end_mount.step": "aluminum_5052",
    "servo_horn_yoke.step": "aluminum_5052",
    "link_bracket_right.step": "aluminum_5052",
    "link_bracket_left.step": "aluminum_5052",
    "link_standoff_m3_35.step": "silver_aluminum_alloy",
    "sts3250.step": "dark_servo",
    "sts3215.step": "dark_servo",
    "base_clamp.step": "aluminum_5052",
    "m2_spacer_5mm.step": "silver_aluminum_alloy",
    "m2_5_hex_spacer_6mm.step": "silver_aluminum_alloy",
    "waveshare_bus_servo_adapter_a.step": "circuit_board_green",
}

V2_HOME_ELBOW_PITCH_DEG = -90.0

URDF_SERVO_AXIS_INSTANCE_BY_JOINT = {
    "base_yaw": "base_link__sts3250_3",
    "shoulder_pitch": "shoulder_yaw_link__sts3250_1",
    "shoulder_roll": "shoulder_pitch_link__sts3250",
    "elbow_pitch": "shoulder_roll_link__sts3250_4",
    "elbow_roll": "elbow_pitch_link__sts3215",
    "wrist_pitch": "elbow_roll_link__sts3215_6",
}

URDF_PITCH_MODULE_SERVO_BY_LINK = {
    "shoulder_pitch_link": "sts3250",
    "elbow_pitch_link": "sts3215",
    "wrist_pitch_link": "sts3215",
}


def _mate(
    source_label: str,
    *,
    fixed: str,
    moving: str,
    relation: str = "rigid",
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    fixed_part, fixed_frame = fixed.split(":", 1)
    moving_part, moving_frame = moving.split(":", 1)
    return {
        "sourceLabel": source_label,
        "type": relation,
        "relation": relation,
        "fixed": fixed,
        "moving": moving,
        "parameters": dict(parameters or {}),
        "fixedEndpoint": {
            "part": fixed_part,
            "frame": fixed_frame,
        },
        "movingEndpoint": {
            "part": moving_part,
            "frame": moving_frame,
        },
    }


def _assembly_mates(*, include_gripper: bool) -> list[dict[str, object]]:
    mates = [
        _mate(
            "base_servo_to_base_clamp",
            fixed="base_link__base_clamp:top_servo_face",
            moving="base_link__sts3250_3:base_plate_face",
        ),
        _mate(
            "base_servo_horn_to_shoulder_yaw_mount",
            fixed="base_link__sts3250_3:output_horn_face",
            moving="shoulder_yaw_link__servo_end_mount:front_horn_mount_face",
            parameters={"clearance_mm": BASE_TO_SHOULDER_YAW_HORN_CLEARANCE_MM},
        ),
        _mate(
            "shoulder_yaw_mount_to_servo",
            fixed="shoulder_yaw_link__sts3250_1:rear_case",
            moving="shoulder_yaw_link__servo_end_mount:servo_face",
        ),
        _mate(
            "shoulder_pitch_yoke_to_servo",
            fixed="shoulder_pitch_link__servo_horn_yoke:horn_axis",
            moving="shoulder_pitch_link__sts3250:horn_axis",
        ),
        _mate(
            "shoulder_pitch_servo_to_roll_bracket_right",
            fixed="shoulder_pitch_link__sts3250:upstream_case",
            moving="shoulder_roll_link__shoulder_link_bracket_right:bottom_servo_mount",
        ),
        _mate(
            "shoulder_pitch_servo_to_roll_bracket_left",
            fixed="shoulder_pitch_link__sts3250:upstream_case",
            moving="shoulder_roll_link__shoulder_link_bracket_left:bottom_servo_mount",
        ),
        _mate(
            "shoulder_roll_bracket_right_to_servo",
            fixed="shoulder_roll_link__shoulder_link_bracket_right:top_servo_mount",
            moving="shoulder_roll_link__sts3250_4:case_mount",
        ),
        _mate(
            "shoulder_roll_bracket_left_to_servo",
            fixed="shoulder_roll_link__shoulder_link_bracket_left:top_servo_mount",
            moving="shoulder_roll_link__sts3250_4:case_mount",
        ),
        _mate(
            "elbow_pitch_yoke_to_shoulder_roll_servo",
            fixed="shoulder_roll_link__sts3250_4:horn_axis",
            moving="elbow_pitch_link__servo_horn_yoke:horn_axis",
        ),
        _mate(
            "elbow_pitch_servo_to_roll_bracket_right",
            fixed="elbow_pitch_link__sts3215:upstream_case",
            moving="elbow_roll_link__elbow_link_bracket_right:bottom_servo_mount",
        ),
        _mate(
            "elbow_pitch_servo_to_roll_bracket_left",
            fixed="elbow_pitch_link__sts3215:upstream_case",
            moving="elbow_roll_link__elbow_link_bracket_left:bottom_servo_mount",
        ),
        _mate(
            "elbow_roll_bracket_right_to_servo",
            fixed="elbow_roll_link__elbow_link_bracket_right:top_servo_mount",
            moving="elbow_roll_link__sts3215_6:case_mount",
        ),
        _mate(
            "elbow_roll_bracket_left_to_servo",
            fixed="elbow_roll_link__elbow_link_bracket_left:top_servo_mount",
            moving="elbow_roll_link__sts3215_6:case_mount",
        ),
        _mate(
            "wrist_pitch_yoke_to_elbow_roll_servo",
            fixed="elbow_roll_link__sts3215_6:horn_axis",
            moving="wrist_pitch_link__servo_horn_yoke:horn_axis",
        ),
    ]
    # The gripper seats on the wrist yoke (terminal servo removed); its placement is set by
    # _mate_gripper_to_yoke_mount, so there is no servo-horn mate, and the link-bracket
    # standoffs are gone, so they add no assembly mates here either.
    return mates


def _module_gen_step(module_path: Path) -> dict[str, object]:
    module_name = f"_tom_v2_{module_path.stem}_{abs(hash(module_path))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    # Links expose their flat instance list via assembly_instances() so tom can
    # compose them, while their gen_step() returns a shape for the pipeline. During
    # migration, fall back to a legacy gen_step() that still returns instances.
    source = getattr(module, "assembly_instances", None)
    if not callable(source):
        source = getattr(module, "gen_step", None)
    if not callable(source):
        raise RuntimeError(f"{module_path} must define assembly_instances()")
    envelope = source()
    if not isinstance(envelope, dict) or "instances" not in envelope:
        raise RuntimeError(f"{module_path} must define an instances assembly via assembly_instances()")
    instances = envelope["instances"]
    if not isinstance(instances, list) or not instances:
        raise RuntimeError(f"{module_path} returned no instances")
    return envelope


def _instances_from_module(module_path: Path) -> list[dict[str, object]]:
    return [
        dict(instance)
        for instance in _module_gen_step(module_path)["instances"]  # type: ignore[index]
    ]


def _rebase_step_path(path: str, *, source_dir: Path) -> str:
    resolved = (source_dir / path).resolve()
    try:
        return resolved.relative_to(V2_DIR.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"{path} resolves outside the v2 assembly folder") from exc


def _v2_source_child_path(path: str) -> str:
    source_path = Path(path)
    if source_path.parts and source_path.parts[0] in {"imports", "gripper"}:
        return (Path("parts") / source_path).as_posix()
    return source_path.as_posix()


def _flatten_instances(
    *,
    parent_name: str,
    parent_transform: list[float],
    local_instances: list[dict[str, object]],
    local_source_dir: Path,
    instance_transform_overrides: dict[str, list[float]] | None = None,
) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []
    transform_overrides = instance_transform_overrides or {}
    for local in local_instances:
        local_name = str(local["name"])
        local_transform = [float(value) for value in local["transform"]]
        world_transform = transform_overrides.get(local_name)
        if world_transform is None:
            world_transform = multiply_transforms(parent_transform, local_transform)
        flattened.append(
            {
                "path": _rebase_step_path(str(local["path"]), source_dir=local_source_dir),
                "name": f"{parent_name}__{local_name}",
                "transform": world_transform,
                "use_source_colors": bool(local.get("use_source_colors", True)),
            }
        )
    return flattened


def _flat_child_instances(
    *,
    child_name: str,
    child_transform: list[float],
    instance_transform_overrides: dict[str, list[float]] | None = None,
) -> list[dict[str, object]]:
    replacement_kind = ROLL_LINK_REPLACEMENTS.get(child_name)
    if replacement_kind is not None:
        return _flatten_instances(
            parent_name=child_name,
            parent_transform=child_transform,
            local_instances=roll_link_instances(replacement_kind),
            local_source_dir=ASSEMBLIES_DIR,
            instance_transform_overrides=instance_transform_overrides,
        )

    module_path = LINK_ASSEMBLY_MODULES[child_name]
    return _flatten_instances(
        parent_name=child_name,
        parent_transform=child_transform,
        local_instances=_instances_from_module(module_path),
        local_source_dir=module_path.parent,
        instance_transform_overrides=instance_transform_overrides,
    )


def _module_transform_for_child(
    *,
    child_name: str,
    design_child_transform: list[float],
) -> list[float]:
    if child_name in URDF_PITCH_MODULE_SERVO_BY_LINK:
        return list(
            multiply_transforms(
                design_child_transform,
                PITCH_MODULE_STANDALONE_TO_DESIGN_TRANSFORM,
            )
        )
    return design_child_transform


def _yoke_transform_for_servo_horn(
    *,
    upstream_servo_transform: list[float],
) -> list[float]:
    return multiply_transforms(
        upstream_servo_transform,
        YOKE_180_ABOUT_WEB_AXIS_TRANSFORM,
    )


def _identity_transform() -> list[float]:
    return [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ]


def _transform_point(
    transform: list[float],
    point: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = point
    return (
        transform[0] * x + transform[1] * y + transform[2] * z + transform[3],
        transform[4] * x + transform[5] * y + transform[6] * z + transform[7],
        transform[8] * x + transform[9] * y + transform[10] * z + transform[11],
    )


def _transform_direction(
    transform: list[float],
    direction: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = direction
    return (
        transform[0] * x + transform[1] * y + transform[2] * z,
        transform[4] * x + transform[5] * y + transform[6] * z,
        transform[8] * x + transform[9] * y + transform[10] * z,
    )


def _axis_angle_transform(
    *,
    axis_point_mm: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
) -> list[float]:
    ux, uy, uz = _normalized_vector(axis_direction)
    theta = math.radians(angle_deg)
    c = math.cos(theta)
    s = math.sin(theta)
    one_minus_c = 1.0 - c
    rotation = (
        (
            c + ux * ux * one_minus_c,
            ux * uy * one_minus_c - uz * s,
            ux * uz * one_minus_c + uy * s,
        ),
        (
            uy * ux * one_minus_c + uz * s,
            c + uy * uy * one_minus_c,
            uy * uz * one_minus_c - ux * s,
        ),
        (
            uz * ux * one_minus_c - uy * s,
            uz * uy * one_minus_c + ux * s,
            c + uz * uz * one_minus_c,
        ),
    )
    px, py, pz = axis_point_mm
    rotated_point = (
        rotation[0][0] * px + rotation[0][1] * py + rotation[0][2] * pz,
        rotation[1][0] * px + rotation[1][1] * py + rotation[1][2] * pz,
        rotation[2][0] * px + rotation[2][1] * py + rotation[2][2] * pz,
    )
    translation = (
        px - rotated_point[0],
        py - rotated_point[1],
        pz - rotated_point[2],
    )
    return [
        rotation[0][0], rotation[0][1], rotation[0][2], translation[0],
        rotation[1][0], rotation[1][1], rotation[1][2], translation[1],
        rotation[2][0], rotation[2][1], rotation[2][2], translation[2],
        0.0, 0.0, 0.0, 1.0,
    ]


def _rotate_transform_about_axis(
    transform: list[float],
    *,
    axis_point_mm: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle_deg: float,
) -> list[float]:
    if abs(angle_deg) <= 1e-9:
        return list(transform)
    return multiply_transforms(
        _axis_angle_transform(
            axis_point_mm=axis_point_mm,
            axis_direction=axis_direction,
            angle_deg=angle_deg,
        ),
        transform,
    )


def _apply_v2_step_home_pose_to_elbow_pitch(
    *,
    child_transform: list[float],
    instance_transforms_by_name: dict[str, list[float]],
) -> list[float]:
    elbow_pitch_servo = instance_transforms_by_name.get(
        URDF_SERVO_AXIS_INSTANCE_BY_JOINT["elbow_pitch"]
    )
    if elbow_pitch_servo is None:
        raise RuntimeError("Cannot apply v2 STEP elbow home pose before elbow servo exists")
    axis_center_world, axis_direction_world = _servo_horn_axis_from_transform(
        elbow_pitch_servo
    )
    return _rotate_transform_about_axis(
        child_transform,
        axis_point_mm=axis_center_world,
        axis_direction=axis_direction_world,
        angle_deg=V2_HOME_ELBOW_PITCH_DEG,
    )


def _translate_transform(
    transform: list[float],
    delta: tuple[float, float, float],
) -> list[float]:
    adjusted = list(transform)
    adjusted[3] += delta[0]
    adjusted[7] += delta[1]
    adjusted[11] += delta[2]
    return adjusted


def _mate_shoulder_yaw_mount_to_base_servo_horn(
    *,
    shoulder_yaw_transform: list[float],
    base_servo_transform: list[float],
) -> list[float]:
    base_horn_face_center = _transform_point(
        base_servo_transform,
        (
            STS3215_HORN_AXIS_LOCAL_X_MM,
            STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM,
            0.0,
        ),
    )
    base_horn_face_normal = _transform_direction(base_servo_transform, (0.0, 1.0, 0.0))
    target = tuple(
        base_horn_face_center[index]
        + (BASE_TO_SHOULDER_YAW_HORN_CLEARANCE_MM * base_horn_face_normal[index])
        for index in range(3)
    )
    moving = _transform_point(
        shoulder_yaw_transform,
        SERVO_END_MOUNT_FRONT_HORN_FACE_CENTER_LOCAL_MM,
    )
    return _translate_transform(
        shoulder_yaw_transform,
        (
            target[0] - moving[0],
            target[1] - moving[1],
            target[2] - moving[2],
        ),
    )


def _mate_gripper_to_yoke_mount(
    *,
    gripper_transform: list[float],
    yoke_transform: list[float],
) -> list[float]:
    # The gripper now seats on the wrist yoke's servo-reference face (where the
    # removed terminal sts3215 used to mount). Translate-only, preserving orientation.
    target = _transform_point(
        yoke_transform,
        servo_horn_yoke.SERVO_REFERENCE_FACE_TARGET_CENTER_MM,
    )
    moving = _transform_point(gripper_transform, GRIPPER_MOUNT_FACE_CENTER_LOCAL_MM)
    base = _translate_transform(
        gripper_transform,
        (
            target[0] - moving[0],
            target[1] - moving[1],
            target[2] - moving[2],
        ),
    )
    # Snap the gripper mount face flush onto the yoke face (see GRIPPER_FACE_TO_YOKE_FACE_OFFSET_MM).
    return _translate_transform(base, GRIPPER_FACE_TO_YOKE_FACE_OFFSET_MM)


def gen_step_with_options(*, include_gripper: bool = False) -> dict[str, object]:
    instances: list[dict[str, object]] = []
    instance_transforms_by_name: dict[str, list[float]] = {}
    downstream_correction = _identity_transform()
    pending_child_transform_overrides: dict[str, list[float]] = {}

    for source_child in robot_arm.robot_arm_assembly_children():
        child_name = str(source_child["name"])
        source_child_transform = [float(value) for value in source_child["transform"]]
        child_transform = pending_child_transform_overrides.pop(child_name, None)
        if child_transform is not None:
            downstream_correction = multiply_transforms(
                child_transform,
                invert_rigid_transform(source_child_transform),
            )
        else:
            child_transform = multiply_transforms(
                downstream_correction,
                source_child_transform,
            )

        if child_name == "shoulder_yaw_link":
            base_servo_transform = instance_transforms_by_name.get("base_link__sts3250_3")
            if base_servo_transform is not None:
                child_transform = _mate_shoulder_yaw_mount_to_base_servo_horn(
                    shoulder_yaw_transform=child_transform,
                    base_servo_transform=base_servo_transform,
                )
                downstream_correction = multiply_transforms(
                    child_transform,
                    invert_rigid_transform(source_child_transform),
                )

        if child_name == "elbow_pitch_link":
            child_transform = _apply_v2_step_home_pose_to_elbow_pitch(
                child_transform=child_transform,
                instance_transforms_by_name=instance_transforms_by_name,
            )
            downstream_correction = multiply_transforms(
                child_transform,
                invert_rigid_transform(source_child_transform),
            )

        if child_name == GRIPPER_CHILD_NAME:
            if not include_gripper:
                continue
            yoke_transform = instance_transforms_by_name.get(
                V2_GRIPPER_MOUNT_INSTANCE_NAME
            )
            if yoke_transform is not None:
                child_transform = _mate_gripper_to_yoke_mount(
                    gripper_transform=child_transform,
                    yoke_transform=yoke_transform,
                )
            instances.append(
                {
                    "path": _v2_source_child_path(str(source_child["path"])),
                    "name": child_name,
                    "transform": child_transform,
                    "use_source_colors": bool(source_child.get("use_source_colors", True)),
                }
            )
            instance_transforms_by_name[child_name] = child_transform
            continue

        module_child_transform = _module_transform_for_child(
            child_name=child_name,
            design_child_transform=child_transform,
        )
        child_instances = _flat_child_instances(
            child_name=child_name,
            child_transform=module_child_transform,
        )
        if include_gripper:
            # Drop the wrist's terminal servo; the gripper takes its place on the yoke.
            child_instances = [
                instance
                for instance in child_instances
                if str(instance["name"]) != V2_WRIST_TERMINAL_SERVO_INSTANCE_NAME
            ]
        instances.extend(child_instances)
        for instance in child_instances:
            instance_transforms_by_name[str(instance["name"])] = [
                float(value) for value in instance["transform"]
            ]

        replacement_kind = ROLL_LINK_REPLACEMENTS.get(child_name)
        if replacement_kind is not None:
            mates = roll_link_mates(replacement_kind)
            next_pitch_child_name = NEXT_PITCH_LINK_BY_ROLL_LINK.get(replacement_kind)
            if next_pitch_child_name is not None:
                upstream_servo_transform = multiply_transforms(
                    child_transform,
                    mates.downstream_servo_local,
                )
                pending_child_transform_overrides[next_pitch_child_name] = (
                    _yoke_transform_for_servo_horn(
                        upstream_servo_transform=upstream_servo_transform,
                    )
                )

    return {
        "instances": instances,
        "assembly_mates": _assembly_mates(include_gripper=include_gripper),
    }


# Drop the whole model so the clamp underside (face #o1.6.f2, the large down-facing plate
# at world z=63.175 in the un-grounded build) sits on the z=0 floor. Applied to the gen_step
# instances AND the URDF frame solver so the STEP and the URDF/SRDF stay co-located on the
# floor. The offset only shifts occurrence placements, not local part geometry, so the
# content-addressed components are unchanged and reused on rebuild.
STEP_GROUND_OFFSET_MM = -63.175


def _with_ground_offset(transform: list[float]) -> list[float]:
    shifted = [float(value) for value in transform]
    shifted[11] += STEP_GROUND_OFFSET_MM
    return shifted


def gen_step() -> dict[str, object]:
    from robot_common.link_assembly import compound_from_instances

    envelope = gen_step_with_options(include_gripper=True)
    grounded = [
        {**instance, "transform": _with_ground_offset(instance["transform"])}
        for instance in envelope["instances"]
    ]
    return {
        "shape": compound_from_instances(
            "tom",
            grounded,
            base_dir=V2_DIR,
            assembly_mates=envelope.get("assembly_mates", []),
        ),
    }

def _normalized_vector(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        raise RuntimeError("Cannot normalize a zero-length vector")
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _servo_horn_axis_from_transform(
    transform: list[float] | tuple[float, ...],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    rear = _transform_point(
        list(transform),
        (
            STS3215_HORN_AXIS_LOCAL_X_MM,
            STS3215_REAR_HORN_FACE_LOCAL_Y_MM,
            0.0,
        ),
    )
    front = _transform_point(
        list(transform),
        (
            STS3215_HORN_AXIS_LOCAL_X_MM,
            STS3250_OUTPUT_HORN_FACE_LOCAL_Y_MM,
            0.0,
        ),
    )
    center = tuple(0.5 * (rear[index] + front[index]) for index in range(3))
    direction = _normalized_vector(
        tuple(front[index] - rear[index] for index in range(3))
    )
    return center, direction
