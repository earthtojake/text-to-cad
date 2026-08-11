from __future__ import annotations

from copy import deepcopy
import math
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET

from robot_common.materials import BLACK_ALUMINUM_RGBA

# Servo (sts3250) flush-mount offset on the base plate: plate top y minus the servo
# mounting-tab face local y. Fixed design constant matching the base_link source
# geometry; defined here so this shared module carries no v1/v2 link dependency.
BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM = -29.8002 - (-27.4)


EXTRUSION_2020_LENGTH_MM = 100.0
SECONDARY_EXTRUSION_2020_LENGTH_MM = 150.0
SECONDARY_EXTRUSION_EXTENSION_MM = SECONDARY_EXTRUSION_2020_LENGTH_MM - EXTRUSION_2020_LENGTH_MM
EXTRUSION_BRACKET_INSERTION_THICKNESS_MM = 1.6
HORN_YOKE_SWEEP_LIMIT_DEG = 135.0
HORN_YOKE_SWEEP_LIMIT_RAD = math.radians(HORN_YOKE_SWEEP_LIMIT_DEG)
BASE_PLATE_BOTTOM_LOCAL_Y_MM = -32.9752
ROLL_LINK_SERVO_END_MOUNT_FLUSH_Z_ADJUST_MM = 2.7308
KGF_CM_TO_NM = 0.0980665

# Mass and effort source values verified against online vendor/project data on
# 2026-04-27:
# - STS3250: https://www.feetechrc.com/en/562636.html
# - STS3215: https://www.feetechrc.com/525603.html
# - HFS5-2020: https://misumi.partcommunity.com/3d-cad-models/hfsmg5-2020-hfsfmg5-2020-hfs5-series-curved-extrusions-misumi
# - 5052-H32: https://sendcutsend.com/materials/5052-aluminum/
# - Robonine gripper: https://github.com/roboninecom/SO-ARM100-101-Parallel-Gripper
STS3250_MASS_KG = 0.0745
STS3215_MASS_KG = 0.055
STS3250_RATED_TORQUE_NM = 16.0 * KGF_CM_TO_NM
STS3215_RATED_TORQUE_NM = 10.0 * KGF_CM_TO_NM
STS3250_PEAK_STALL_TORQUE_NM = 50.0 * KGF_CM_TO_NM
STS3215_STALL_TORQUE_NM = 30.0 * KGF_CM_TO_NM
HFS5_2020_MASS_KG_PER_M = 0.5
HFS5_2020_100_MASS_KG = HFS5_2020_MASS_KG_PER_M * 0.100
HFS5_2020_150_MASS_KG = HFS5_2020_MASS_KG_PER_M * 0.150
ALUMINUM_5052_H32_DENSITY_KG_PER_MM3 = 0.097 * 0.45359237 / (0.0254**3) / 1e9
BASE_PLATE_MASS_KG = 5745.825053237387 * ALUMINUM_5052_H32_DENSITY_KG_PER_MM3
SERVO_END_MOUNT_MASS_KG = 1934.588542178479 * ALUMINUM_5052_H32_DENSITY_KG_PER_MM3
SERVO_HORN_YOKE_MASS_KG = 4126.128540235039 * ALUMINUM_5052_H32_DENSITY_KG_PER_MM3
EXTRUSION_BRACKET_2020_MASS_KG = 2335.413008330946 * ALUMINUM_5052_H32_DENSITY_KG_PER_MM3
GRIPPER_ASSEMBLY_MASS_KG = 0.250
STS3250_JOINT_EFFORT_TEXT = f"{STS3250_RATED_TORQUE_NM:.6f}"
STS3215_JOINT_EFFORT_TEXT = f"{STS3215_RATED_TORQUE_NM:.6f}"
GRIPPER_SERVO_EFFORT_TEXT = f"{STS3215_STALL_TORQUE_NM:.6f}"


def _translate_instance_world_vector(
    instance: dict[str, object],
    *,
    vector_xyz: tuple[float, float, float],
    distance_mm: float,
) -> dict[str, object]:
    transform = [float(value) for value in instance["transform"]]
    transform[3] += vector_xyz[0] * distance_mm
    transform[7] += vector_xyz[1] * distance_mm
    transform[11] += vector_xyz[2] * distance_mm
    return {**instance, "transform": transform}


def _instance_local_axis_world_vector(instance: dict[str, object], *, axis: str) -> tuple[float, float, float]:
    transform = [float(value) for value in instance["transform"]]
    return _transform_local_axis_world_vector(transform, axis=axis)


def _transform_local_axis_world_vector(transform: list[float], *, axis: str) -> tuple[float, float, float]:
    axis_column = {"x": 0, "y": 1, "z": 2}[axis]
    return (
        transform[axis_column],
        transform[4 + axis_column],
        transform[8 + axis_column],
    )


def _find_named_instance(instances: list[dict[str, object]], name: str) -> dict[str, object]:
    for instance in instances:
        if str(instance["name"]) == name:
            return instance
    raise RuntimeError(f"Missing assembly instance {name!r}")


def _translate_named_instances_world_vector(
    instances: list[dict[str, object]],
    names: frozenset[str],
    *,
    vector_xyz: tuple[float, float, float],
    distance_mm: float,
) -> None:
    for index, instance in enumerate(instances):
        if str(instance["name"]) in names:
            instances[index] = _translate_instance_world_vector(
                instance,
                vector_xyz=vector_xyz,
                distance_mm=distance_mm,
            )


def _replace_named_instance(
    instances: list[dict[str, object]],
    *,
    name: str,
    replacement: dict[str, object],
) -> None:
    for index, instance in enumerate(instances):
        if str(instance["name"]) == name:
            instances[index] = replacement
            return
    raise RuntimeError(f"Missing assembly instance {name!r}")


# The base mounts on the base_clamp_assembly desk clamp (see assemblies/base_link.step.py),
# whose grip face hangs this far below the legacy flat-plate ground plane once the
# clamp is M-aligned to the base servo. Lifting the whole robot by this amount seats
# base_footprint on the clamp's desk-grip surface (measured from the M-aligned clamp
# bounding box: lowest point at base_link-local Y = -72.518).
BASE_CLAMP_GROUND_LIFT_MM = 72.518


def _base_ground_y_offset_mm() -> float:
    base_plate = _find_named_instance(ASSEMBLY_INSTANCES, "base_plate")
    base_plate_transform = [float(value) for value in base_plate["transform"]]
    return -(base_plate_transform[7] + BASE_PLATE_BOTTOM_LOCAL_Y_MM) + BASE_CLAMP_GROUND_LIFT_MM


def _grounded_top_level_transform(
    transform: list[float],
    *,
    y_offset_mm: float = 0.0,
) -> list[float]:
    grounded = [float(value) for value in transform]
    grounded[7] += _base_ground_y_offset_mm() + y_offset_mm
    return grounded


def _y_up_to_z_up_transform(transform: list[float]) -> list[float]:
    # Rotate exported top-level assembly placements so old +Y becomes standard +Z.
    source = [float(value) for value in transform]
    return [
        source[0], source[1], source[2], source[3],
        -source[8], -source[9], -source[10], -source[11],
        source[4], source[5], source[6], source[7],
        0.0, 0.0, 0.0, 1.0,
    ]


def _standard_ground_top_level_transform(
    transform: list[float],
    *,
    y_offset_mm: float = 0.0,
) -> list[float]:
    return _y_up_to_z_up_transform(
        _grounded_top_level_transform(transform, y_offset_mm=y_offset_mm)
    )


def _translate_transform_world_offset(
    transform: list[float],
    offset_xyz_mm: tuple[float, float, float],
) -> list[float]:
    translated = [float(value) for value in transform]
    translated[3] += offset_xyz_mm[0]
    translated[7] += offset_xyz_mm[1]
    translated[11] += offset_xyz_mm[2]
    return translated


def _insert_named_instance_before(
    instances: list[dict[str, object]],
    *,
    before_name: str,
    instance: dict[str, object],
) -> None:
    for index, current in enumerate(instances):
        if str(current["name"]) == before_name:
            instances.insert(index, instance)
            return
    raise RuntimeError(f"Missing assembly instance {before_name!r}")


def _extrusion_bracket_transform_from_extrusion(
    extrusion_instance: dict[str, object],
) -> list[float]:
    transform = [float(value) for value in extrusion_instance["transform"]]
    # The wrap bracket uses the extrusion's frame, flipped 180 degrees around its
    # local x axis so the horn plate sits at the extrusion start plane.
    for index in (1, 5, 9, 2, 6, 10):
        transform[index] = -transform[index]
    return transform


def _extrusion_end_bracket_transform_from_extrusion(
    extrusion_instance: dict[str, object],
    *,
    length_mm: float,
) -> list[float]:
    transform = [float(value) for value in extrusion_instance["transform"]]
    # Match the extrusion frame at the downstream end plane so the bracket wraps
    # the far end without rotating the existing downstream chain.
    extrusion_z_world = _instance_local_axis_world_vector(extrusion_instance, axis="z")
    transform[3] += extrusion_z_world[0] * -length_mm
    transform[7] += extrusion_z_world[1] * -length_mm
    transform[11] += extrusion_z_world[2] * -length_mm
    return transform


ASSEMBLY_INSTANCES = [{'path': 'imports/sts3250.step',
  'name': 'sts3250_1',
  'transform': [0.0,
                1.0,
                0.0,
                -1.264258,
                -1.0,
                0.0,
                0.0,
                52.610399203721,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_horn_yoke.step',
  'name': 'servo_horn_yoke',
  'transform': [0.0,
                1.0,
                0.0,
                -1.264258,
                -1.0,
                0.0,
                0.0,
                52.610399203721,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3250.step',
  'name': 'sts3250_2',
  'transform': [1.0,
                0.0,
                0.0,
                15.135742000006,
                0.0,
                1.0,
                0.0,
                134.620798778311,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'extrusion_bracket_2020.step',
  'name': 'secondary_servo_2020_connector',
  'transform': [1.0,
                0.0,
                0.0,
                -10.364257999994,
                0.0,
                1.0,
                0.0,
                145.850798778311,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/hfs5_2020_150.step',
  'name': 'secondary_servo_hfs5_2020',
  'transform': [1.0,
                0.0,
                0.0,
                -10.364257999994,
                0.0,
                0.0,
                -1.0,
                147.450798778311,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_end_mount.step',
  'name': 'quaternary_servo_end_mount',
  'transform': [0.0,
                1.0,
                0.0,
                -0.764257999994,
                -1.0,
                0.0,
                0.0,
                261.060997778311,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3250.step',
  'name': 'sts3250_4',
  'transform': [0.0,
                1.0,
                0.0,
                -0.764257999994,
                -1.0,
                0.0,
                0.0,
                261.060997778311,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_horn_yoke.step',
  'name': 'quinary_horn_yoke',
  'transform': [-0.000376789973259,
                0.999999858029296,
                0.000376790000006,
                -0.777330838358056,
                -1.41970704e-07,
                0.000376789973259,
                -0.999999929014646,
                286.55752815855016,
                -0.999999929014646,
                -0.000376790000006,
                0.0,
                -25.496532190119495,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3215.step',
  'name': 'sts3215_5',
  'transform': [0.999999858029296,
                0.000376789973259,
                0.000376790000006,
                15.653567529745356,
                0.000376789973259,
                1.41970704e-07,
                -0.999999929014646,
                286.56371915718586,
                -0.000376790000006,
                0.999999929014646,
                0.0,
                56.5076826323431,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'extrusion_bracket_2020.step',
  'name': 'quinary_servo_2020_connector',
  'transform': [0.999999858029296,
                0.000376789973259,
                0.000376790000006,
                -9.838731499094065,
                0.000376789973259,
                1.41970704e-07,
                -0.999999929014646,
                286.55411391315283,
                -0.000376790000006,
                0.999999929014646,
                0.0,
                67.74728867422357,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/hfs5_2020_100.step',
  'name': 'quinary_servo_hfs5_2020',
  'transform': [0.999999858029296,
                0.000376790000006,
                -0.000376789973259,
                -9.83812863513685,
                0.000376789973259,
                -0.999999929014646,
                -1.41970704e-07,
                286.55411414030596,
                -0.000376790000006,
                0.0,
                -0.999999929014646,
                69.347288560647,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_end_mount.step',
  'name': 'senary_servo_end_mount',
  'transform': [-0.000376789973259,
                0.999999858029296,
                0.000376790000006,
                -0.198788813720378,
                -1.41970704e-07,
                0.000376789973259,
                -0.999999929014646,
                286.5577461474151,
                -0.999999929014646,
                -0.000376790000006,
                0.0,
                182.95386361794084,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3215.step',
  'name': 'sts3215_6',
  'transform': [-0.000376789973259,
                0.999999858029296,
                0.000376790000006,
                -0.198788813720378,
                -1.41970704e-07,
                0.000376789973259,
                -0.999999929014646,
                286.5577461474151,
                -0.999999929014646,
                -0.000376790000006,
                0.0,
                182.95386361794084,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_horn_yoke.step',
  'name': 'septenary_horn_yoke',
  'transform': [-0.000376789973259,
                0.999999858029296,
                0.000376790000006,
                -0.198788813720376,
                -1.41970704e-07,
                0.000376789973259,
                -0.999999929014646,
                286.5577461474151,
                -0.999999929014646,
                -0.000376790000006,
                0.0,
                182.95386361794084,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3215.step',
  'name': 'sts3215_7',
  'transform': [0.999999858029296,
                0.000376789973259,
                0.000376790000006,
                16.232109554383037,
                0.000376789973259,
                1.41970704e-07,
                -0.999999929014646,
                286.5639371460508,
                -0.000376790000006,
                0.999999929014646,
                0.0,
                264.9580784404034,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'servo_end_mount.step',
  'name': 'servo_end_mount',
  'transform': [0.0,
                1.0,
                0.0,
                -1.264258,
                -1.0,
                0.0,
                0.0,
                52.610399203721,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'imports/sts3250.step',
  'name': 'sts3250_3',
  'transform': [1.0,
                0.0,
                0.0,
                14.635742,
                0.0,
                1.0,
                0.0,
                27.7702,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'base_plate.step',
  'name': 'base_plate',
  'transform': [1.0,
                0.0,
                0.0,
                14.635742,
                0.0,
                1.0,
                0.0,
                27.7702,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0]},
 {'path': 'gripper/tom_gripper.step',
 'name': 'parallel_gripper',
 'transform': [0.999999929014645,
                0.0,
                0.00037679,
                -9.277696917667,
                0.0,
                1.0,
                0.0,
                286.552253,
                -0.00037679,
                0.0,
                0.999999929014645,
                326.167694693849,
                0.0,
                0.0,
                0.0,
                1.0]}]

REMOVED_ROBOT_ARM_INSTANCE_NAMES = frozenset()
SECONDARY_END_BRACKET_DOWNSTREAM_INSTANCE_NAMES = frozenset(
    {
        "quaternary_servo_end_mount",
        "sts3250_4",
        "quinary_horn_yoke",
        "sts3215_5",
        "quinary_servo_2020_connector",
        "quinary_servo_hfs5_2020",
        "quinary_servo_end_bracket",
        "senary_servo_end_mount",
        "sts3215_6",
        "septenary_horn_yoke",
        "sts3215_7",
        "parallel_gripper",
    }
)
QUINARY_END_BRACKET_DOWNSTREAM_INSTANCE_NAMES = frozenset(
    {
        "senary_servo_end_mount",
        "sts3215_6",
        "septenary_horn_yoke",
        "sts3215_7",
        "parallel_gripper",
    }
)

for connector_name, extrusion_name in (
    ("secondary_servo_2020_connector", "secondary_servo_hfs5_2020"),
    ("quinary_servo_2020_connector", "quinary_servo_hfs5_2020"),
):
    connector_instance = _find_named_instance(ASSEMBLY_INSTANCES, connector_name)
    extrusion_instance = _find_named_instance(ASSEMBLY_INSTANCES, extrusion_name)
    _replace_named_instance(
        ASSEMBLY_INSTANCES,
        name=connector_name,
        replacement={
            **connector_instance,
            "path": "extrusion_bracket_2020.step",
            "transform": _extrusion_bracket_transform_from_extrusion(extrusion_instance),
        },
    )

for bracket_name, extrusion_name, before_name in (
    ("secondary_servo_end_bracket", "secondary_servo_hfs5_2020", "quaternary_servo_end_mount"),
    ("quinary_servo_end_bracket", "quinary_servo_hfs5_2020", "senary_servo_end_mount"),
):
    extrusion_instance = _find_named_instance(ASSEMBLY_INSTANCES, extrusion_name)
    bracket_length_mm = (
        SECONDARY_EXTRUSION_2020_LENGTH_MM
        if extrusion_name == "secondary_servo_hfs5_2020"
        else EXTRUSION_2020_LENGTH_MM
    )
    _insert_named_instance_before(
        ASSEMBLY_INSTANCES,
        before_name=before_name,
        instance={
            "path": "extrusion_bracket_2020.step",
            "name": bracket_name,
            "transform": _extrusion_end_bracket_transform_from_extrusion(
                extrusion_instance,
                length_mm=bracket_length_mm,
            ),
        },
    )

_translate_named_instances_world_vector(
    ASSEMBLY_INSTANCES,
    SECONDARY_END_BRACKET_DOWNSTREAM_INSTANCE_NAMES,
    vector_xyz=tuple(
        -value
        for value in _instance_local_axis_world_vector(
            _find_named_instance(ASSEMBLY_INSTANCES, "secondary_servo_hfs5_2020"),
            axis="z",
        )
    ),
    distance_mm=SECONDARY_EXTRUSION_EXTENSION_MM,
)
_translate_named_instances_world_vector(
    ASSEMBLY_INSTANCES,
    SECONDARY_END_BRACKET_DOWNSTREAM_INSTANCE_NAMES,
    vector_xyz=tuple(
        -value
        for value in _instance_local_axis_world_vector(
            _find_named_instance(ASSEMBLY_INSTANCES, "secondary_servo_hfs5_2020"),
            axis="z",
        )
    ),
    distance_mm=EXTRUSION_BRACKET_INSERTION_THICKNESS_MM,
)
_translate_named_instances_world_vector(
    ASSEMBLY_INSTANCES,
    QUINARY_END_BRACKET_DOWNSTREAM_INSTANCE_NAMES,
    vector_xyz=tuple(
        -value
        for value in _instance_local_axis_world_vector(
            _find_named_instance(ASSEMBLY_INSTANCES, "quinary_servo_hfs5_2020"),
            axis="z",
        )
    ),
    distance_mm=EXTRUSION_BRACKET_INSERTION_THICKNESS_MM,
)

# Robonine gripper uses a module 0.5, 26-tooth pinion and a 76 mm full stroke.
GRIPPER_CLAW_TRAVEL_M = 0.038
GRIPPER_SERVO_CLOSE_DEG = 334.96
GRIPPER_SERVO_CLOSE_RAD = math.radians(GRIPPER_SERVO_CLOSE_DEG)
GRIPPER_RACK_TRAVEL_PER_RAD_M = GRIPPER_CLAW_TRAVEL_M / GRIPPER_SERVO_CLOSE_RAD
GRIPPER_SERVO_VELOCITY_RAD_PER_S = 0.03 / GRIPPER_RACK_TRAVEL_PER_RAD_M

# Mesh-derived gripper inertials. The Robonine gripper source gives a
# 250 g assembly mass, but not per-link mass properties. These values
# distribute that mass over the generated gripper mesh volume estimates.
GRIPPER_STATIC_MESH_VOLUME_MM3 = 69789.45759247476
GRIPPER_SERVO_GEAR_MESH_VOLUME_MM3 = 1118.1904419098348
GRIPPER_CLAW_MESH_VOLUME_MM3 = 19529.73092604228
GRIPPER_MESH_VOLUME_SUM_MM3 = (
    GRIPPER_STATIC_MESH_VOLUME_MM3
    + GRIPPER_SERVO_GEAR_MESH_VOLUME_MM3
    + (2.0 * GRIPPER_CLAW_MESH_VOLUME_MM3)
)
GRIPPER_MESH_DENSITY_KG_PER_MM3 = GRIPPER_ASSEMBLY_MASS_KG / GRIPPER_MESH_VOLUME_SUM_MM3


def _mesh_estimated_mass_kg(volume_mm3: float) -> float:
    return volume_mm3 * GRIPPER_MESH_DENSITY_KG_PER_MM3


def _mesh_center_m(center_xyz_mm: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(value * 0.001 for value in center_xyz_mm)


def _mesh_inertia_kg_m2(inertia_mm5: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(value * GRIPPER_MESH_DENSITY_KG_PER_MM3 * 1e-6 for value in inertia_mm5)


URDF_LINK_INERTIALS = {
    "base_link": {
        "mass": STS3250_MASS_KG + BASE_PLATE_MASS_KG,
        "origin_xyz": (-0.013065695, 0.018748416, -0.000001347),
        "inertia": (2.00286469315e-05, 3.27226966744e-05, 3.64056286856e-05),
    },
    "shoulder_yaw_link": {
        "mass": STS3250_MASS_KG + SERVO_END_MOUNT_MASS_KG,
        "origin_xyz": (0.001212643, 0.046188702, -0.000001520),
        "inertia": (2.19822684157e-05, 1.33477342495e-05, 2.72133948517e-05),
    },
    "shoulder_pitch_link": {
        "mass": STS3250_MASS_KG + SERVO_HORN_YOKE_MASS_KG,
        "origin_xyz": (-0.046864415, 0.009984643, -0.000001415),
        "inertia": (2.61354708556e-05, 5.11017950126e-05, 6.8521371663e-05),
    },
    "shoulder_roll_link": {
        "mass": (
            STS3250_MASS_KG
            + SERVO_END_MOUNT_MASS_KG
            + HFS5_2020_150_MASS_KG
            + 2 * EXTRUSION_BRACKET_2020_MASS_KG
        ),
        "origin_xyz": (0.000577873, 0.144167410, -0.000000724),
        "inertia": (0.000595051077045, 2.80096804783e-05, 0.0006060283843),
    },
    "elbow_pitch_link": {
        "mass": STS3215_MASS_KG + SERVO_HORN_YOKE_MASS_KG,
        "origin_xyz": (0.000001711, 0.009998836, 0.046867544),
        "inertia": (6.85659210126e-05, 5.11223026952e-05, 2.61742086504e-05),
    },
    "elbow_roll_link": {
        "mass": (
            STS3215_MASS_KG
            + SERVO_END_MOUNT_MASS_KG
            + HFS5_2020_100_MASS_KG
            + 2 * EXTRUSION_BRACKET_2020_MASS_KG
        ),
        "origin_xyz": (0.000680967, 0.113970513, -0.000000851),
        "inertia": (0.000292565038128, 2.38225119977e-05, 0.000301901347194),
    },
    "wrist_pitch_link": {
        "mass": STS3215_MASS_KG + SERVO_HORN_YOKE_MASS_KG,
        "origin_xyz": (-0.046864415, 0.009984643, -0.000001415),
        "inertia": (2.61354708556e-05, 5.11017950126e-05, 6.8521371663e-05),
    },
    "gripper_base_link": {
        "mass": _mesh_estimated_mass_kg(GRIPPER_STATIC_MESH_VOLUME_MM3),
        "origin_xyz": _mesh_center_m((-0.0126298648, 15.5220681, -11.3782697)),
        "inertia": _mesh_inertia_kg_m2((72377447.4, 94420670.5, 126870002.0)),
    },
    "gripper_servo_link": {
        "mass": _mesh_estimated_mass_kg(GRIPPER_SERVO_GEAR_MESH_VOLUME_MM3),
        "origin_xyz": _mesh_center_m((0.0000000329379318, -0.00000015359035, -0.668503477)),
        "inertia": _mesh_inertia_kg_m2((28356.08228658, 28356.0947249, 43883.87103322)),
    },
    "gripper_right_claw_link": {
        "mass": _mesh_estimated_mass_kg(GRIPPER_CLAW_MESH_VOLUME_MM3),
        "origin_xyz": _mesh_center_m((45.56599565, -1.48478733, 22.03617984)),
        "inertia": _mesh_inertia_kg_m2((10873354.67241446, 9338011.90258315, 5226795.70594811)),
    },
    "gripper_left_claw_link": {
        "mass": _mesh_estimated_mass_kg(GRIPPER_CLAW_MESH_VOLUME_MM3),
        "origin_xyz": _mesh_center_m((-45.56599565, 1.48478733, 22.03617984)),
        "inertia": _mesh_inertia_kg_m2((10873354.67241446, 9338011.90258318, 5226795.70594813)),
    },
}


def _urdf_numeric_text(value: float) -> str:
    numeric = float(value)
    if abs(numeric) < 0.5e-9:
        numeric = 0.0
    return f"{numeric:.9f}".rstrip("0").rstrip(".")


def _urdf_link_inertial(link_name: str) -> dict[str, object]:
    inertial = URDF_LINK_INERTIALS[link_name]
    ixx, iyy, izz = inertial["inertia"]
    return {
        "origin_xyz": " ".join(_urdf_numeric_text(value) for value in inertial["origin_xyz"]),
        "origin_rpy": "0 0 0",
        "mass": _urdf_numeric_text(float(inertial["mass"])),
        "inertia": {
            "ixx": _urdf_numeric_text(ixx),
            "ixy": "0",
            "ixz": "0",
            "iyy": _urdf_numeric_text(iyy),
            "iyz": "0",
            "izz": _urdf_numeric_text(izz),
        },
    }


URDF_LINKS = (
    {"name": "base_footprint"},
    {
        "name": "base_link",
        "inertial": _urdf_link_inertial("base_link"),
        "visuals": (
            {
                "instance_name": "sts3250_3",
                "origin_xyz": "0 0.030575 0",
                "origin_rpy": "0 0 0",
            },
            {
                "instance_name": "base_plate",
                "origin_xyz": "0 0.0329752 0",
                "origin_rpy": "0 0 0",
            },
        ),
    },
    {
        "name": "shoulder_yaw_link",
        "inertial": _urdf_link_inertial("shoulder_yaw_link"),
        "visuals": (
            {
                "instance_name": "sts3250_1",
                "origin_xyz": "0.0096 0.033940199 0",
                "origin_rpy": "0 0 -1.570796327",
            },
            {
                "instance_name": "servo_end_mount",
                "origin_xyz": "0.0096 0.033940199 0",
                "origin_rpy": "0 0 -1.570796327",
            },
        ),
    },
    {
        "name": "shoulder_pitch_link",
        "inertial": _urdf_link_inertial("shoulder_pitch_link"),
        "visuals": (
            {
                "instance_name": "servo_horn_yoke",
                "origin_xyz": "0.0255 0.0091 0",
                "origin_rpy": "0 0 0",
            },
            {
                "instance_name": "sts3250_2",
                "origin_xyz": "-0.0594 0.0255 0",
                "origin_rpy": "0 0 1.570796327",
            },
        ),
    },
    {
        "name": "shoulder_roll_link",
        "inertial": _urdf_link_inertial("shoulder_roll_link"),
        "visuals": (
            {
                "instance_name": "secondary_servo_2020_connector",
                "origin_xyz": "0 0.0190404 0",
                "origin_rpy": "-1.570796327 0 0",
            },
            {
                "instance_name": "secondary_servo_hfs5_2020",
                "origin_xyz": "0 0.0190404 0",
                "origin_rpy": "1.570796327 0 0",
            },
            {
                "instance_name": "secondary_servo_end_bracket",
                "origin_xyz": "0 0.1690404 0",
                "origin_rpy": "1.570796327 0 0",
            },
            {
                "instance_name": "quaternary_servo_end_mount",
                "origin_xyz": "0.0096 0.186981399 0",
                "origin_rpy": "0 0 -1.570796327",
            },
            {
                "instance_name": "sts3250_4",
                "origin_xyz": "0.0096 0.186981399 0",
                "origin_rpy": "0 0 -1.570796327",
            },
        ),
    },
    {
        "name": "elbow_pitch_link",
        "inertial": _urdf_link_inertial("elbow_pitch_link"),
        "visuals": (
            {
                "instance_name": "quinary_horn_yoke",
                "origin_xyz": "0.00000347 0.009086927 -0.025496532",
                "origin_rpy": "-1.570796327 1.570419537 -1.570419537",
            },
            {
                "instance_name": "sts3215_5",
                "origin_xyz": "-0.000002722 0.025518914 0.059397282",
                "origin_rpy": "1.570796327 0.00037679 1.571173117",
            },
        ),
    },
    {
        "name": "elbow_roll_link",
        "inertial": _urdf_link_inertial("elbow_roll_link"),
        "visuals": (
            {
                "instance_name": "quinary_servo_2020_connector",
                "origin_xyz": "0.000003466 0.0190404 0",
                "origin_rpy": "-1.570796327 0 0",
            },
            {
                "instance_name": "quinary_servo_hfs5_2020",
                "origin_xyz": "0.000003466 0.0190404 0",
                "origin_rpy": "1.570796327 0 0",
            },
            {
                "instance_name": "quinary_servo_end_bracket",
                "origin_xyz": "0.000003466 0.1190404 0",
                "origin_rpy": "1.570796327 0 0",
            },
            {
                "instance_name": "senary_servo_end_mount",
                "origin_xyz": "0.0096 0.136981399 0",
                "origin_rpy": "0 0 -1.570796327",
            },
            {
                "instance_name": "sts3215_6",
                "origin_xyz": "0.0096 0.136981399 0",
                "origin_rpy": "0 0 -1.570796327",
            },
        ),
    },
    {
        "name": "wrist_pitch_link",
        "inertial": _urdf_link_inertial("wrist_pitch_link"),
        "visuals": (
            {
                "instance_name": "septenary_horn_yoke",
                "origin_xyz": "0.0255 0.0091 0",
                "origin_rpy": "0 0 0",
            },
            {
                "instance_name": "sts3215_7",
                "origin_xyz": "-0.0594 0.0255 0",
                "origin_rpy": "0 0 1.570796327",
            },
        ),
    },
    {
        "name": "gripper_base_link",
        "inertial": _urdf_link_inertial("gripper_base_link"),
        "visuals": (
            {
                "mesh_filename": "3MF/gripper_static.3mf",
                "origin_xyz": "0 0 0",
                "origin_rpy": "0 0 0",
            },
        ),
    },
    {
        "name": "gripper_servo_link",
        "inertial": _urdf_link_inertial("gripper_servo_link"),
        "visuals": (
            {
                "mesh_filename": "3MF/gripper_servo_gear.3mf",
                "origin_xyz": "0 0 0",
                "origin_rpy": "0 0 0",
            },
        ),
    },
    {
        "name": "gripper_right_claw_link",
        "inertial": _urdf_link_inertial("gripper_right_claw_link"),
        "visuals": (
            {
                "mesh_filename": "3MF/gripper_right_claw.3mf",
                "origin_xyz": "0 0 0",
                "origin_rpy": "0 0 0",
            },
        ),
    },
    {
        "name": "gripper_left_claw_link",
        "inertial": _urdf_link_inertial("gripper_left_claw_link"),
        "visuals": (
            {
                "mesh_filename": "3MF/gripper_left_claw.3mf",
                "origin_xyz": "0 0 0",
                "origin_rpy": "0 0 0",
            },
        ),
    },
)

URDF_JOINTS = (
    {
        "name": "base_footprint_to_base_link",
        "joint_type": "fixed",
        "parent": "base_footprint",
        "child": "base_link",
        "origin_xyz": "0.014635742 0 0",
        "origin_rpy": "1.570796327 0 0",
    },
    {
        "name": "base_yaw",
        "joint_type": "continuous",
        "parent": "base_link",
        "child": "shoulder_yaw_link",
        "origin_xyz": "-0.0255 0.021475 0",
        "origin_rpy": "0 0 0",
        "axis_xyz": "0 1 0",
        "limit": {
            "effort": STS3250_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "shoulder_pitch",
        "joint_type": "revolute",
        "parent": "shoulder_yaw_link",
        "child": "shoulder_pitch_link",
        "origin_xyz": "0.0005 0.059440199 0",
        "origin_rpy": "0 0 -1.570796327",
        "axis_xyz": "0 1 0",
        "limit": {
            "lower": f"{-HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "upper": f"{HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "effort": STS3250_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "shoulder_roll",
        "joint_type": "continuous",
        "parent": "shoulder_pitch_link",
        "child": "shoulder_roll_link",
        "origin_xyz": "-0.0503 0 0",
        "origin_rpy": "0 0 1.570796327",
        "axis_xyz": "0 1 0",
        "limit": {
            "effort": STS3250_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "elbow_pitch",
        "joint_type": "revolute",
        "parent": "shoulder_roll_link",
        "child": "elbow_pitch_link",
        "origin_xyz": "0.0005 0.212481399 0",
        "origin_rpy": "0 0 -1.570796327",
        "axis_xyz": "0 1 0",
        "limit": {
            "lower": f"{-HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "upper": f"{HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "effort": STS3250_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "elbow_roll",
        "joint_type": "continuous",
        "parent": "elbow_pitch_link",
        "child": "elbow_roll_link",
        "origin_xyz": "0.000006888 0.000015489 0.050306891",
        "origin_rpy": "1.570796327 0.00037679 1.571173117",
        "axis_xyz": "0 1 0",
        "limit": {
            "effort": STS3215_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "wrist_pitch",
        "joint_type": "revolute",
        "parent": "elbow_roll_link",
        "child": "wrist_pitch_link",
        "origin_xyz": "0.0005 0.162481399 0",
        "origin_rpy": "0 0 -1.570796327",
        "axis_xyz": "0 1 0",
        "limit": {
            "lower": f"{-HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "upper": f"{HORN_YOKE_SWEEP_LIMIT_RAD:.9f}",
            "effort": STS3215_JOINT_EFFORT_TEXT,
            "velocity": "4.000000",
        },
    },
    {
        "name": "wrist_pitch_to_gripper_base",
        "joint_type": "fixed",
        "parent": "wrist_pitch_link",
        "child": "gripper_base_link",
        "origin_xyz": "-0.00003287 0.0674104 0.000002072",
        "origin_rpy": "-1.570796185 -0.00037679 0",
    },
    {
        "name": "gripper_servo",
        "joint_type": "revolute",
        "parent": "gripper_base_link",
        "child": "gripper_servo_link",
        "origin_xyz": "0 0 0",
        "origin_rpy": "0 0 0",
        "axis_xyz": "0 0 1",
        "attrs": {"default_deg": "0"},
        "limit": {
            "lower": "0",
            "upper": f"{GRIPPER_SERVO_CLOSE_RAD:.9f}",
            "effort": GRIPPER_SERVO_EFFORT_TEXT,
            "velocity": f"{GRIPPER_SERVO_VELOCITY_RAD_PER_S:.6f}",
        },
    },
    {
        "name": "gripper_right_claw_slide",
        "joint_type": "prismatic",
        "parent": "gripper_base_link",
        "child": "gripper_right_claw_link",
        "origin_xyz": "0 0 0",
        "origin_rpy": "0 0 0",
        "axis_xyz": "-1 0 0",
        "limit": {
            "lower": "0",
            "upper": f"{GRIPPER_CLAW_TRAVEL_M:.6f}",
            "effort": "150",
            "velocity": "0.03",
        },
            "mimic": {
                "joint": "gripper_servo",
                "multiplier": f"{GRIPPER_RACK_TRAVEL_PER_RAD_M:.12f}",
                "offset": "0",
            },
        },
    {
        "name": "gripper_left_claw_slide",
        "joint_type": "prismatic",
        "parent": "gripper_base_link",
        "child": "gripper_left_claw_link",
        "origin_xyz": "0 0 0",
        "origin_rpy": "0 0 0",
        "axis_xyz": "1 0 0",
        "limit": {
            "lower": "0",
            "upper": f"{GRIPPER_CLAW_TRAVEL_M:.6f}",
            "effort": "150",
            "velocity": "0.03",
        },
            "mimic": {
                "joint": "gripper_servo",
                "multiplier": f"{GRIPPER_RACK_TRAVEL_PER_RAD_M:.12f}",
                "offset": "0",
            },
        },
)

URDF_VISUAL_INSTANCE_NAMES = tuple(
    str(visual["instance_name"])
    for link in URDF_LINKS
    for visual in link.get("visuals", ())
    if "instance_name" in visual and str(visual["instance_name"]) not in REMOVED_ROBOT_ARM_INSTANCE_NAMES
)

URDF_MATERIALS = {
    "black_aluminum": BLACK_ALUMINUM_RGBA,
}

URDF_STEP_MATERIALS = {
    "imports/sts3250.step": "black_aluminum",
    "imports/sts3215.step": "black_aluminum",
}

PRESERVE_SOURCE_COLOR_STEP_PATHS = frozenset(
    {
        "imports/sts3250.step",
        "imports/sts3215.step",
        "gripper/tom_gripper.step",
    }
)
EXPLORER_POSES = (
    {
        "name": "home",
        "joint_values": {
            "base_yaw": 0,
            "shoulder_pitch": 0,
            "shoulder_roll": 0,
            "elbow_pitch": 0,
            "elbow_roll": 0,
            "wrist_pitch": 0,
            "wrist_roll": 0,
            "gripper_servo": 0,
        },
    },
    {
        "name": "reach",
        "joint_values": {
            "base_yaw": 0,
            "shoulder_pitch": 90,
            "shoulder_roll": 0,
            "elbow_pitch": -90,
            "elbow_roll": 0,
            "wrist_pitch": 0,
            "wrist_roll": 0,
            "gripper_servo": 90,
        },
    },
    {
        "name": "action",
        "joint_values": {
            "base_yaw": 95,
            "shoulder_pitch": 32,
            "shoulder_roll": 35,
            "elbow_pitch": -20,
            "elbow_roll": -103,
            "wrist_pitch": 65,
            "wrist_roll": -71,
            "gripper_servo": 185,
        },
    },
)
ROBOT_ARM_LINK_ASSEMBLIES = (
    {
        "path": "assemblies/base_link.step",
        "name": "base_link",
        "anchor_instance_name": "base_plate",
        "top_level_y_offset_mm": BASE_PLATE_BOTTOM_LOCAL_Y_MM,
        "instance_names": frozenset(
            {
                "sts3250_3",
                "base_plate",
            }
        ),
    },
    {
        "path": "assemblies/shoulder_yaw_link.step",
        "name": "shoulder_yaw_link",
        "anchor_instance_name": "sts3250_1",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "sts3250_1",
                "servo_end_mount",
            }
        ),
    },
    {
        "path": "assemblies/pitch_link_sts3250.step",
        "name": "shoulder_pitch_link",
        "anchor_instance_name": "servo_horn_yoke",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "servo_horn_yoke",
                "sts3250_2",
            }
        ),
    },
    {
        "path": "assemblies/shoulder_roll_link.step",
        "name": "shoulder_roll_link",
        "anchor_instance_name": "secondary_servo_2020_connector",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "secondary_servo_2020_connector",
                "secondary_servo_hfs5_2020",
                "secondary_servo_end_bracket",
                "quaternary_servo_end_mount",
                "sts3250_4",
            }
        ),
    },
    {
        "path": "assemblies/pitch_link_sts3215.step",
        "name": "elbow_pitch_link",
        "anchor_instance_name": "quinary_horn_yoke",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "quinary_horn_yoke",
                "sts3215_5",
            }
        ),
    },
    {
        "path": "assemblies/elbow_roll_link.step",
        "name": "elbow_roll_link",
        "anchor_instance_name": "quinary_servo_2020_connector",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "quinary_servo_2020_connector",
                "quinary_servo_hfs5_2020",
                "quinary_servo_end_bracket",
                "senary_servo_end_mount",
                "sts3215_6",
            }
        ),
    },
    {
        "path": "assemblies/pitch_link_sts3215.step",
        "name": "wrist_pitch_link",
        "anchor_instance_name": "septenary_horn_yoke",
        "top_level_y_offset_mm": BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        "instance_names": frozenset(
            {
                "septenary_horn_yoke",
                "sts3215_7",
            }
        ),
    },
)


def _xml(tag: str, attrs: dict[str, object] | None = None, children: tuple[ET.Element, ...] = ()) -> ET.Element:
    element = ET.Element(tag, {key: str(value) for key, value in (attrs or {}).items()})
    for child in children:
        element.append(child)
    return element


def _urdf_inertial_element(inertial: dict[str, object]) -> ET.Element:
    return _xml(
        "inertial",
        children=(
            _xml("origin", {"xyz": inertial["origin_xyz"], "rpy": inertial["origin_rpy"]}),
            _xml("mass", {"value": inertial["mass"]}),
            _xml("inertia", dict(inertial["inertia"])),
        ),
    )


def _urdf_mesh_filename_for_entry(entry: dict[str, object]) -> str:
    mesh_filename = entry.get("mesh_filename")
    if mesh_filename is None:
        mesh_filename = _urdf_mesh_filename(str(entry["instance_name"]))
    return str(mesh_filename)


def _urdf_mesh_geometry_element(entry: dict[str, object]) -> ET.Element:
    mesh_filename = _urdf_mesh_filename_for_entry(entry)
    return _xml(
        "geometry",
        children=(
            _xml(
                "mesh",
                {
                    "filename": mesh_filename,
                    "scale": "0.001 0.001 0.001",
                },
            ),
        ),
    )


def _urdf_visual_element(visual: dict[str, object]) -> ET.Element:
    children = [
        _xml("origin", {"xyz": visual["origin_xyz"], "rpy": visual["origin_rpy"]}),
        _urdf_mesh_geometry_element(visual),
    ]
    material_name = _urdf_visual_material_name(visual)
    if material_name:
        children.append(_xml("material", {"name": material_name}))
    return _xml(
        "visual",
        children=tuple(children),
    )


def _urdf_collision_element(collision: dict[str, object]) -> ET.Element:
    return _xml(
        "collision",
        children=(
            _xml("origin", {"xyz": collision["origin_xyz"], "rpy": collision["origin_rpy"]}),
            _urdf_mesh_geometry_element(collision),
        ),
    )


def _urdf_entry_is_removed(entry: dict[str, object]) -> bool:
    return "instance_name" in entry and str(entry["instance_name"]) in REMOVED_ROBOT_ARM_INSTANCE_NAMES


def _urdf_link_element(link: dict[str, object]) -> ET.Element:
    children: list[ET.Element] = []
    inertial = link.get("inertial")
    if inertial is not None:
        children.append(_urdf_inertial_element(dict(inertial)))
    for visual in link.get("visuals", ()):
        if _urdf_entry_is_removed(dict(visual)):
            continue
        children.append(_urdf_visual_element(dict(visual)))
    collision_specs = link.get("collisions")
    if collision_specs is None:
        collision_specs = link.get("visuals", ())
    for collision in collision_specs:
        if _urdf_entry_is_removed(dict(collision)):
            continue
        children.append(_urdf_collision_element(dict(collision)))
    return _xml("link", {"name": link["name"]}, tuple(children))


def _urdf_joint_element(joint: dict[str, object]) -> ET.Element:
    attrs = {"name": joint["name"], "type": joint["joint_type"]}
    attrs.update(dict(joint.get("urdf_attrs", {})))
    children = [
        _xml("parent", {"link": joint["parent"]}),
        _xml("child", {"link": joint["child"]}),
        _xml("origin", {"xyz": joint["origin_xyz"], "rpy": joint["origin_rpy"]}),
    ]
    axis_xyz = joint.get("axis_xyz")
    if axis_xyz is not None:
        children.append(_xml("axis", {"xyz": axis_xyz}))
    limit = joint.get("limit")
    if limit is not None:
        children.append(_xml("limit", dict(limit)))
    mimic = joint.get("mimic")
    if mimic is not None:
        children.append(_xml("mimic", dict(mimic)))
    return _xml("joint", attrs, tuple(children))


def _explorer_numeric_value(value: float) -> float | int:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _urdf_explorer_metadata(
    *,
    joints: tuple[dict[str, object], ...] = URDF_JOINTS,
    poses: tuple[dict[str, object], ...] = EXPLORER_POSES,
) -> dict[str, object]:
    joint_defaults_by_name = {}
    for joint in joints:
        attrs = dict(joint.get("attrs", {}))
        if "default_deg" in attrs:
            joint_defaults_by_name[str(joint["name"])] = _explorer_numeric_value(float(attrs["default_deg"]))
    return {
        "schemaVersion": 3,
        "kind": "texttocad-urdf-explorer",
        "jointDefaultsByName": joint_defaults_by_name,
        "poses": [
            {
                "name": str(pose["name"]),
                "jointValuesByName": {
                    str(joint_name): _explorer_numeric_value(float(joint_value))
                    for joint_name, joint_value in dict(pose["joint_values"]).items()
                },
            }
            for pose in poses
        ],
    }


def _urdf_root_element(
    *,
    links: tuple[dict[str, object], ...] = URDF_LINKS,
    joints: tuple[dict[str, object], ...] = URDF_JOINTS,
    robot_name: str = "tom",
    source_name: str = "tom.step.py",
) -> ET.Element:
    root = _xml("robot", {"name": robot_name})
    root.append(ET.Comment(f" Generated by {source_name} for CAD Explorer and external URDF consumers. "))
    root.append(
        ET.Comment(
            " Link inertials use STS3250 mass 74.5 g and STS3215 mass 55 g from Feetech, HFS5-2020 profile "
            "mass 0.5 kg/m from MISUMI, 5052-H32 density 0.097 lb/in^3 from "
            "SendCutSend, and Robonine gripper assembly mass 250 g distributed "
            "across generated gripper mesh volume estimates. Arm joint effort "
            "uses each servo family's rated torque: STS3250 16 kg-cm "
            "and STS3215 10 kg-cm at 12 V. "
        )
    )
    used_material_names = sorted(
        {
            material_name
            for link in links
            for visual in link.get("visuals", ())
            if (material_name := _urdf_visual_material_name(visual))
        }
    )
    for material_name in used_material_names:
        rgba = URDF_MATERIALS[material_name]
        root.append(
            _xml(
                "material",
                {"name": material_name},
                (_xml("color", {"rgba": _urdf_rgba_text(rgba)}),),
            )
        )
    for link in links:
        root.append(_urdf_link_element(link))
    root.append(
        ET.Comment(
            " Joint frames use the horn-center line resolved from "
            "@cad[STEP/imports/sts3250#o1.4.f2,o1.5.f3]. "
        )
    )
    for joint in joints:
        root.append(_urdf_joint_element(joint))
    return root


def _serialize_urdf(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode")


def _assembly_instances() -> list[dict[str, object]]:
    instances = []
    for instance in ASSEMBLY_INSTANCES:
        step_path = PurePosixPath(str(instance["path"])).as_posix()
        instances.append(
            {
                "path": step_path,
                "name": str(instance["name"]),
                "transform": [float(value) for value in instance["transform"]],
                "use_source_colors": step_path in PRESERVE_SOURCE_COLOR_STEP_PATHS,
            }
        )
    return instances


def _assembly_children() -> list[dict[str, object]]:
    source_instances = _assembly_instances()
    source_by_name = {str(instance["name"]): instance for instance in source_instances}
    missing_anchors = [
        str(spec["anchor_instance_name"])
        for spec in ROBOT_ARM_LINK_ASSEMBLIES
        if str(spec["anchor_instance_name"]) not in source_by_name
    ]
    if missing_anchors:
        raise RuntimeError(f"Missing robot arm link assembly anchors: {missing_anchors!r}")

    children = []
    consumed_instance_names = set(REMOVED_ROBOT_ARM_INSTANCE_NAMES)
    downstream_offset_xyz_mm = (0.0, 0.0, 0.0)
    for link_spec in ROBOT_ARM_LINK_ASSEMBLIES:
        anchor = source_by_name[str(link_spec["anchor_instance_name"])]
        child_transform = _translate_transform_world_offset(
            _standard_ground_top_level_transform(
                anchor["transform"],
                y_offset_mm=float(link_spec["top_level_y_offset_mm"]),
            ),
            downstream_offset_xyz_mm,
        )
        children.append(
            {
                "path": str(link_spec["path"]),
                "name": str(link_spec["name"]),
                "transform": child_transform,
                "use_source_colors": True,
            }
        )
        consumed_instance_names.update(link_spec["instance_names"])
        if str(link_spec["name"]) in {"shoulder_roll_link", "elbow_roll_link"}:
            local_z_world = _transform_local_axis_world_vector(child_transform, axis="z")
            downstream_offset_xyz_mm = (
                downstream_offset_xyz_mm[0] + (local_z_world[0] * ROLL_LINK_SERVO_END_MOUNT_FLUSH_Z_ADJUST_MM),
                downstream_offset_xyz_mm[1] + (local_z_world[1] * ROLL_LINK_SERVO_END_MOUNT_FLUSH_Z_ADJUST_MM),
                downstream_offset_xyz_mm[2] + (local_z_world[2] * ROLL_LINK_SERVO_END_MOUNT_FLUSH_Z_ADJUST_MM),
            )

    for instance in source_instances:
        instance_name = str(instance["name"])
        if instance_name in consumed_instance_names:
            continue
        child_transform = _standard_ground_top_level_transform(
            instance["transform"],
            y_offset_mm=BASE_LINK_STS3250_SOURCE_Y_OFFSET_MM,
        )
        if instance_name == "parallel_gripper":
            child_transform = _translate_transform_world_offset(child_transform, downstream_offset_xyz_mm)
        children.append(
            {
                **instance,
                "transform": child_transform,
            }
        )
    return children


def _assembly_instance_by_name() -> dict[str, dict[str, object]]:
    instances = _assembly_instances()
    by_name = {str(instance["name"]): instance for instance in instances}
    if len(by_name) != len(instances):
        raise RuntimeError("assembly instance names must be unique")
    return by_name


def _urdf_rgba_text(rgba: tuple[float, float, float, float]) -> str:
    return " ".join(f"{float(value):.6f}".rstrip("0").rstrip(".") for value in rgba)


def _urdf_visual_material_name(visual: dict[str, object]) -> str:
    if str(_urdf_mesh_filename_for_entry(visual)).lower().endswith(".3mf"):
        return ""
    material_name = visual.get("material")
    if material_name is not None:
        return str(material_name)
    if "instance_name" not in visual:
        return ""
    by_name = _assembly_instance_by_name()
    instance_name = str(visual["instance_name"])
    try:
        instance = by_name[instance_name]
    except KeyError as exc:
        raise RuntimeError(f"URDF visual references missing assembly instance {instance_name!r}") from exc
    step_path = PurePosixPath(str(instance["path"])).as_posix()
    return URDF_STEP_MATERIALS.get(step_path, "")


def _urdf_mesh_filename(instance_name: str) -> str:
    by_name = _assembly_instance_by_name()
    try:
        instance = by_name[instance_name]
    except KeyError as exc:
        raise RuntimeError(f"URDF visual references missing assembly instance {instance_name!r}") from exc
    step_path = PurePosixPath(str(instance["path"]))
    if step_path.suffix.lower() != ".step":
        raise RuntimeError(f"URDF visual instance {instance_name!r} does not reference a .step file")
    return f"3MF/{step_path.stem}.3mf"


ROBOT_ARM_MOTION_JOINT_NAMES = [
    "base_yaw",
    "shoulder_pitch",
    "shoulder_roll",
    "elbow_pitch",
    "elbow_roll",
    "wrist_pitch",
]

ROBOT_ARM_MOTION_DISABLED_COLLISION_PAIRS = (
    ("wrist_pitch_link", "gripper_base_link"),
    ("elbow_pitch_link", "shoulder_roll_link"),
)

ROBOT_ARM_SRDF_INSPECTION_ARM_GROUP_STATE_DEG = {
    "base_yaw": 45.0,
    "shoulder_pitch": -27.0,
    "shoulder_roll": -53.001,
    "elbow_pitch": 3.0,
    "elbow_roll": 29.969,
    "wrist_pitch": 58.004,
}

ROBOT_ARM_SRDF_INSPECTION_MIRRORED_ARM_GROUP_STATE_DEG = {
    "base_yaw": 45.0,
    "shoulder_pitch": -27.0,
    "shoulder_roll": 53.001,
    "elbow_pitch": 3.0,
    "elbow_roll": -29.969,
    "wrist_pitch": 58.004,
}

ROBOT_ARM_SRDF_ARM_GROUP_STATES_DEG = (
    (
        "home",
        {
            "base_yaw": 0.0,
            "shoulder_pitch": 0.0,
            "shoulder_roll": 0.0,
            "elbow_pitch": 0.0,
            "elbow_roll": 0.0,
            "wrist_pitch": 0.0,
        },
    ),
    (
        "reach_forward",
        {
            "base_yaw": 0.0,
            "shoulder_pitch": 60.0,
            "shoulder_roll": 0.0,
            "elbow_pitch": -90.0,
            "elbow_roll": 0.0,
            "wrist_pitch": 30.0,
        },
    ),
    (
        "inspection",
        ROBOT_ARM_SRDF_INSPECTION_ARM_GROUP_STATE_DEG,
    ),
    (
        "inspection_mirrored",
        ROBOT_ARM_SRDF_INSPECTION_MIRRORED_ARM_GROUP_STATE_DEG,
    ),
)

ROBOT_ARM_SRDF_ARM_WITH_GRIPPER_GROUP_STATES_DEG = ()

ROBOT_ARM_SRDF_GRIPPER_GROUP_STATES_RAD = (
    ("open", {"gripper_servo": 0.0}),
    ("half_closed", {"gripper_servo": GRIPPER_SERVO_CLOSE_RAD * 0.5}),
    ("closed", {"gripper_servo": GRIPPER_SERVO_CLOSE_RAD}),
)


def _joint_degrees_to_radians(joint_values_deg: dict[str, float]) -> dict[str, float]:
    return {
        joint_name: math.radians(float(value_deg))
        for joint_name, value_deg in joint_values_deg.items()
    }


def _srdf_group_state_element(
    *,
    name: str,
    group: str,
    joint_values_rad: dict[str, float],
) -> ET.Element:
    return _xml(
        "group_state",
        {"name": name, "group": group},
        tuple(
            _xml("joint", {"name": joint_name, "value": _urdf_numeric_text(value_rad)})
            for joint_name, value_rad in joint_values_rad.items()
        ),
    )


def _srdf_adjacent_collision_pairs() -> tuple[tuple[str, str], ...]:
    pairs = []
    seen: set[tuple[str, str]] = set()
    for joint in URDF_JOINTS:
        parent = str(joint["parent"])
        child = str(joint["child"])
        if "base_footprint" in {parent, child}:
            continue
        key = tuple(sorted((parent, child)))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((parent, child))
    return tuple(pairs)


def _srdf_root_element(*, robot_name: str = "tom") -> ET.Element:
    root = _xml("robot", {"name": robot_name})
    root.append(ET.Comment(" Generated by tom.py for MoveIt2 and CAD Viewer test poses. "))
    root.append(
        _xml(
            "virtual_joint",
            {
                "name": "fixed_base",
                "type": "fixed",
                "parent_frame": "world",
                "child_link": "base_footprint",
            },
        )
    )

    arm_group = _xml("group", {"name": "arm"})
    arm_group.append(_xml("chain", {"base_link": "base_link", "tip_link": "wrist_roll_link"}))
    root.append(arm_group)

    tcp_group = _xml("group", {"name": "tcp"})
    tcp_group.append(_xml("link", {"name": "gripper_base_link"}))
    root.append(tcp_group)

    gripper_group = _xml("group", {"name": "gripper"})
    gripper_group.append(_xml("joint", {"name": "gripper_servo"}))
    root.append(gripper_group)

    arm_with_gripper_group = _xml("group", {"name": "arm_with_gripper"})
    arm_with_gripper_group.append(_xml("group", {"name": "arm"}))
    arm_with_gripper_group.append(_xml("group", {"name": "gripper"}))
    root.append(arm_with_gripper_group)

    root.append(
        _xml(
            "end_effector",
            {
                "name": "gripper_tcp",
                "parent_link": "wrist_roll_link",
                "group": "tcp",
                "parent_group": "arm",
            },
        )
    )

    for name, joint_values_deg in ROBOT_ARM_SRDF_ARM_GROUP_STATES_DEG:
        root.append(
            _srdf_group_state_element(
                name=name,
                group="arm",
                joint_values_rad=_joint_degrees_to_radians(joint_values_deg),
            )
        )
    for name, joint_values_rad in ROBOT_ARM_SRDF_GRIPPER_GROUP_STATES_RAD:
        root.append(
            _srdf_group_state_element(
                name=name,
                group="gripper",
                joint_values_rad=joint_values_rad,
            )
        )
    for name, joint_values_deg in ROBOT_ARM_SRDF_ARM_WITH_GRIPPER_GROUP_STATES_DEG:
        root.append(
            _srdf_group_state_element(
                name=name,
                group="arm_with_gripper",
                joint_values_rad=_joint_degrees_to_radians(joint_values_deg),
            )
        )
    for link1, link2 in _srdf_adjacent_collision_pairs():
        root.append(_xml("disable_collisions", {"link1": link1, "link2": link2, "reason": "Adjacent"}))
    return root

ROBOT_ARM_2X_ARM_1_BASE_YAW_DEG = 90.0
ROBOT_ARM_2X_ARM_2_BASE_YAW_DEG = -90.0
ROBOT_ARM_2X_BASE_OFFSET_X_M = 0.395
ROBOT_ARM_2X_HOLDING_HANDS_POSE_JOINT_VALUES = {
    "arm_1_base_yaw": 90,
    "arm_1_shoulder_pitch": 0,
    "arm_1_shoulder_roll": 0,
    "arm_1_elbow_pitch": 90,
    "arm_1_elbow_roll": 0,
    "arm_1_wrist_pitch": 0,
    "arm_1_wrist_roll": -24,
    "arm_1_gripper_servo": 208,
    "arm_2_base_yaw": -90,
    "arm_2_shoulder_pitch": 0,
    "arm_2_shoulder_roll": 0,
    "arm_2_elbow_pitch": 90,
    "arm_2_elbow_roll": 0,
    "arm_2_wrist_pitch": 0,
    "arm_2_wrist_roll": -45,
    "arm_2_gripper_servo": 334.95,
}

ROBOT_ARM_2X_ARM_SPECS = (
    {
        "name": "arm_1",
        "prefix": "arm_1_",
        "base_origin_xyz": (-ROBOT_ARM_2X_BASE_OFFSET_X_M, 0.0, 0.0),
        "base_origin_rpy": (0.0, 0.0, 0.0),
        "default_joint_degrees": {"base_yaw": ROBOT_ARM_2X_ARM_1_BASE_YAW_DEG},
    },
    {
        "name": "arm_2",
        "prefix": "arm_2_",
        "base_origin_xyz": (ROBOT_ARM_2X_BASE_OFFSET_X_M, 0.0, 0.0),
        "base_origin_rpy": (0.0, 0.0, 0.0),
        "default_joint_degrees": {"base_yaw": ROBOT_ARM_2X_ARM_2_BASE_YAW_DEG},
    },
)

ROBOT_ARM_2X_MOTION_JOINT_NAMES = [
    f"{spec['prefix']}{joint_name}"
    for spec in ROBOT_ARM_2X_ARM_SPECS
    for joint_name in ROBOT_ARM_MOTION_JOINT_NAMES
]


def _urdf_xyz_values(text: str) -> tuple[float, float, float]:
    values = tuple(float(value) for value in text.split())
    if len(values) != 3:
        raise RuntimeError(f"URDF xyz value must have exactly 3 components: {text!r}")
    return values


def _urdf_xyz_text(values: tuple[float, float, float]) -> str:
    return " ".join(_urdf_numeric_text(value) for value in values)


def _prefixed_robot_arm_link(link: dict[str, object], *, prefix: str) -> dict[str, object]:
    prefixed = deepcopy(link)
    prefixed["name"] = f"{prefix}{link['name']}"
    return prefixed


def _prefixed_robot_arm_joint(
    joint: dict[str, object],
    *,
    prefix: str,
    base_origin_xyz: tuple[float, float, float],
    base_origin_rpy: tuple[float, float, float],
    default_joint_degrees: dict[str, float],
) -> dict[str, object]:
    prefixed = deepcopy(joint)
    parent_name = str(joint["parent"])
    child_name = str(joint["child"])
    joint_name = str(joint["name"])
    prefixed["name"] = f"{prefix}{joint['name']}"
    prefixed["parent"] = "base_footprint" if parent_name == "base_footprint" else f"{prefix}{parent_name}"
    prefixed["child"] = f"{prefix}{child_name}"
    if parent_name == "base_footprint":
        prefixed["origin_xyz"] = _urdf_xyz_text(base_origin_xyz)
        prefixed["origin_rpy"] = _urdf_xyz_text(base_origin_rpy)
    if joint_name in default_joint_degrees:
        attrs = dict(prefixed.get("attrs", {}))
        attrs["default_deg"] = _urdf_numeric_text(float(default_joint_degrees[joint_name]))
        prefixed["attrs"] = attrs
    if "mimic" in prefixed:
        mimic = dict(prefixed["mimic"])
        mimic["joint"] = f"{prefix}{mimic['joint']}"
        prefixed["mimic"] = mimic
    return prefixed


def _robot_arm_2x_links() -> tuple[dict[str, object], ...]:
    links = [{"name": "base_footprint"}]
    for spec in ROBOT_ARM_2X_ARM_SPECS:
        prefix = str(spec["prefix"])
        links.extend(
            _prefixed_robot_arm_link(link, prefix=prefix)
            for link in URDF_LINKS
            if str(link["name"]) != "base_footprint"
        )
    return tuple(links)


def _robot_arm_2x_joints() -> tuple[dict[str, object], ...]:
    joints = []
    for spec in ROBOT_ARM_2X_ARM_SPECS:
        prefix = str(spec["prefix"])
        base_origin_xyz = tuple(float(value) for value in spec["base_origin_xyz"])
        base_origin_rpy = tuple(float(value) for value in spec["base_origin_rpy"])
        default_joint_degrees = {
            str(name): float(value)
            for name, value in dict(spec.get("default_joint_degrees", {})).items()
        }
        joints.extend(
            _prefixed_robot_arm_joint(
                joint,
                prefix=prefix,
                base_origin_xyz=base_origin_xyz,
                base_origin_rpy=base_origin_rpy,
                default_joint_degrees=default_joint_degrees,
            )
            for joint in URDF_JOINTS
        )
    return tuple(joints)


def _explorer_pose_by_name(name: str) -> dict[str, object]:
    for pose in EXPLORER_POSES:
        if str(pose["name"]) == name:
            return pose
    raise RuntimeError(f"Missing explorer pose {name!r}")


def _robot_arm_2x_default_joint_values() -> dict[str, object]:
    joint_values = {}
    home_pose = _explorer_pose_by_name("home")
    for spec in ROBOT_ARM_2X_ARM_SPECS:
        prefix = str(spec["prefix"])
        base_yaw_degrees = float(dict(spec.get("default_joint_degrees", {})).get("base_yaw", 0.0))
        joint_values.update(
            {
                f"{prefix}{joint_name}": (
                    float(joint_value) + base_yaw_degrees
                    if str(joint_name) == "base_yaw"
                    else joint_value
                )
                for joint_name, joint_value in dict(home_pose["joint_values"]).items()
            }
        )
    return joint_values


def _robot_arm_2x_explorer_pose(
    pose: dict[str, object],
) -> dict[str, object]:
    joint_values = {}
    pose_joint_values = dict(pose["joint_values"])
    for spec in ROBOT_ARM_2X_ARM_SPECS:
        prefix = str(spec["prefix"])
        base_yaw_degrees = float(dict(spec.get("default_joint_degrees", {})).get("base_yaw", 0.0))
        joint_values.update(
            {
                f"{prefix}{joint_name}": (
                    float(joint_value) + base_yaw_degrees
                    if str(joint_name) == "base_yaw"
                    else joint_value
                )
                for joint_name, joint_value in pose_joint_values.items()
            }
        )
    return {
        "name": str(pose["name"]),
        "joint_values": joint_values,
    }


def _robot_arm_2x_explorer_poses() -> tuple[dict[str, object], ...]:
    return (
        *(_robot_arm_2x_explorer_pose(pose) for pose in EXPLORER_POSES),
        {
            "name": "holding_hands",
            "joint_values": ROBOT_ARM_2X_HOLDING_HANDS_POSE_JOINT_VALUES,
        },
    )


def _prefixed_disabled_collision_pairs(*, prefix: str) -> list[list[str]]:
    return [
        [f"{prefix}{left}", f"{prefix}{right}"]
        for left, right in ROBOT_ARM_MOTION_DISABLED_COLLISION_PAIRS
    ]


def _robot_arm_2x_disabled_collision_pairs() -> list[list[str]]:
    pairs = []
    for spec in ROBOT_ARM_2X_ARM_SPECS:
        pairs.extend(_prefixed_disabled_collision_pairs(prefix=str(spec["prefix"])))
    return pairs


def _robot_arm_2x_motion_joint_names(*, prefix: str) -> list[str]:
    return [f"{prefix}{joint_name}" for joint_name in ROBOT_ARM_MOTION_JOINT_NAMES]


def _robot_arm_2x_motion_planning_groups() -> list[dict[str, object]]:
    return [
        {
            "name": str(spec["name"]),
            "jointNames": _robot_arm_2x_motion_joint_names(prefix=str(spec["prefix"])),
        }
        for spec in ROBOT_ARM_2X_ARM_SPECS
    ]


def _robot_arm_2x_default_motion_joint_values_rad(*, prefix: str) -> dict[str, float]:
    default_joint_values = _robot_arm_2x_default_joint_values()
    return {
        name: math.radians(float(default_joint_values[name]))
        for name in _robot_arm_2x_motion_joint_names(prefix=prefix)
    }


def robot_arm_assembly_children() -> list[dict[str, object]]:
    return _assembly_children()


def robot_arm_step_envelope() -> dict[str, object]:
    return {
        "children": robot_arm_assembly_children(),
    }


def robot_arm_urdf_envelope(*, urdf_output: str = "tom.urdf") -> dict[str, object]:
    return {
        "xml": _serialize_urdf(_urdf_root_element()),
        "urdf_output": urdf_output,
        "explorer_metadata": _urdf_explorer_metadata(),
    }


def robot_arm_2x_urdf_envelope(*, urdf_output: str = "robot_arm_2x.urdf") -> dict[str, object]:
    links = _robot_arm_2x_links()
    joints = _robot_arm_2x_joints()
    return {
        "xml": _serialize_urdf(
            _urdf_root_element(
                links=links,
                joints=joints,
                robot_name="robot_arm_2x",
                source_name="robot_arm_2x_urdf.py",
            )
        ),
        "urdf_output": urdf_output,
        "explorer_metadata": _urdf_explorer_metadata(
            joints=joints,
            poses=_robot_arm_2x_explorer_poses(),
        ),
    }


def robot_arm_srdf_envelope(*, urdf: str = "tom.urdf") -> dict[str, object]:
    return {
        "xml": _serialize_urdf(_srdf_root_element()),
        "urdf": urdf,
    }


def robot_arm_motion_envelope(*, urdf: str = "tom.urdf") -> dict[str, object]:
    return {
        "urdf": urdf,
        "provider": "moveit_py",
        "commands": ["urdf.solvePose", "urdf.planToPose"],
        "planningGroup": "arm",
        "jointNames": ROBOT_ARM_MOTION_JOINT_NAMES,
        "endEffectors": [
            {
                "name": "gripper",
                "link": "gripper_base_link",
                "frame": "base_link",
                "parentLink": "wrist_roll_link",
                "positionTolerance": 0.002,
            }
        ],
        "planner": {
            "pipeline": "ompl",
            "plannerId": "RRTConnectkConfigDefault",
            "planningTime": 1.0,
        },
        "disabledCollisionPairs": [list(pair) for pair in ROBOT_ARM_MOTION_DISABLED_COLLISION_PAIRS],
        "groupStates": [
            {
                "name": name,
                "jointValuesByNameRad": {
                    joint_name: joint_values_rad[joint_name]
                    for joint_name in ROBOT_ARM_MOTION_JOINT_NAMES
                },
            }
            for name, joint_values_deg in ROBOT_ARM_SRDF_ARM_GROUP_STATES_DEG
            for joint_values_rad in (_joint_degrees_to_radians(joint_values_deg),)
        ],
    }


def robot_arm_2x_motion_envelope(*, urdf: str = "robot_arm_2x.urdf") -> dict[str, object]:
    default_group = str(ROBOT_ARM_2X_ARM_SPECS[0]["name"])
    default_prefix = str(ROBOT_ARM_2X_ARM_SPECS[0]["prefix"])
    return {
        "urdf": urdf,
        "provider": "moveit_py",
        "commands": ["urdf.solvePose", "urdf.planToPose"],
        "planningGroup": default_group,
        "jointNames": _robot_arm_2x_motion_joint_names(prefix=default_prefix),
        "planningGroups": _robot_arm_2x_motion_planning_groups(),
        "endEffectors": [
            {
                "name": f"{spec['name']}_gripper",
                "link": f"{spec['prefix']}gripper_base_link",
                "frame": f"{spec['prefix']}base_link",
                "parentLink": f"{spec['prefix']}wrist_roll_link",
                "planningGroup": str(spec["name"]),
                "jointNames": _robot_arm_2x_motion_joint_names(prefix=str(spec["prefix"])),
                "positionTolerance": 0.002,
            }
            for spec in ROBOT_ARM_2X_ARM_SPECS
        ],
        "planner": {
            "pipeline": "ompl",
            "plannerId": "RRTConnectkConfigDefault",
            "planningTime": 1.0,
        },
        "disabledCollisionPairs": _robot_arm_2x_disabled_collision_pairs(),
        "groupStates": [
            {
                "name": "home",
                "planningGroup": str(spec["name"]),
                "jointValuesByNameRad": _robot_arm_2x_default_motion_joint_values_rad(prefix=str(spec["prefix"])),
            }
            for spec in ROBOT_ARM_2X_ARM_SPECS
        ],
    }
