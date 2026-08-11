from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
TOM_DIR = V2_DIR
ASSEMBLIES_DIR = V2_DIR / "assemblies"
PARTS_DIR = V2_DIR / "parts"
for path in (TOM_DIR, V2_DIR, PARTS_DIR, ASSEMBLIES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.step_entry import load_step_entry

link_bracket = load_step_entry("link_bracket")
pitch_link_sts3215 = load_step_entry("pitch_link_sts3215")
pitch_link_sts3250 = load_step_entry("pitch_link_sts3250")
from robot_common import robot_arm


MATE_TRANSFORM_TOLERANCE = 1e-6
RIGHT_BRACKET_PATH = "../parts/link_bracket_right.step"
LEFT_BRACKET_PATH = "../parts/link_bracket_left.step"
LINK_STANDOFF_PATH = "../parts/link_standoff_m3_35.step"
TOP_SERVO_FACE_TO_FLANGE_TRANSFORM = tuple(
    link_bracket.top_servo_case_transform(
        case_span_centering_offset_mm=link_bracket.TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM,
    )
)


@dataclass(frozen=True)
class RollLinkMateSpec:
    anchor: str
    upstream_anchor: str
    upstream_servo: str
    upstream_servo_transform: tuple[float, ...]
    downstream_servo: str
    downstream_servo_path: str


@dataclass(frozen=True)
class RollLinkMates:
    spec: RollLinkMateSpec
    bracket_local: list[float]
    downstream_shift_local: tuple[float, float, float]
    downstream_servo_local: list[float]


ROLL_LINK_SPECS = {
    "shoulder": RollLinkMateSpec(
        anchor="secondary_servo_2020_connector",
        upstream_anchor="servo_horn_yoke",
        upstream_servo="sts3250_2",
        upstream_servo_transform=tuple(pitch_link_sts3250.STS3250_DESIGN_TRANSFORM),
        downstream_servo="sts3250_4",
        downstream_servo_path="../parts/imports/sts3250.step",
    ),
    "elbow": RollLinkMateSpec(
        anchor="quinary_servo_2020_connector",
        upstream_anchor="quinary_horn_yoke",
        upstream_servo="sts3215_5",
        upstream_servo_transform=tuple(pitch_link_sts3215.STS3215_DESIGN_TRANSFORM),
        downstream_servo="sts3215_6",
        downstream_servo_path="../parts/imports/sts3215.step",
    ),
}


def _matrix(transform: list[float] | tuple[float, ...]) -> list[list[float]]:
    return [list(transform[index : index + 4]) for index in range(0, 16, 4)]


def _flatten(matrix: list[list[float]]) -> list[float]:
    return [value for row in matrix for value in row]


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(left[row][inner] * right[inner][col] for inner in range(4))
            for col in range(4)
        ]
        for row in range(4)
    ]


def invert_rigid_transform(transform: list[float] | tuple[float, ...]) -> list[float]:
    matrix = _matrix(transform)
    rotation = [row[:3] for row in matrix[:3]]
    translation = [matrix[row][3] for row in range(3)]
    inverse_rotation = [[rotation[col][row] for col in range(3)] for row in range(3)]
    inverse_translation = [
        -sum(inverse_rotation[row][col] * translation[col] for col in range(3))
        for row in range(3)
    ]
    return _flatten(
        [
            [*inverse_rotation[0], inverse_translation[0]],
            [*inverse_rotation[1], inverse_translation[1]],
            [*inverse_rotation[2], inverse_translation[2]],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def relative_transform(
    *,
    anchor_transform: list[float] | tuple[float, ...],
    transform: list[float] | tuple[float, ...],
) -> list[float]:
    return multiply_transforms(invert_rigid_transform(anchor_transform), transform)


def multiply_transforms(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> list[float]:
    return _flatten(_matmul(_matrix(left), _matrix(right)))


def translate_transform(
    transform: list[float] | tuple[float, ...],
    delta_xyz: tuple[float, float, float],
) -> list[float]:
    translated = [float(value) for value in transform]
    translated[3] += delta_xyz[0]
    translated[7] += delta_xyz[1]
    translated[11] += delta_xyz[2]
    return translated


def translation_transform(x: float, y: float, z: float) -> list[float]:
    return [
        1.0, 0.0, 0.0, x,
        0.0, 1.0, 0.0, y,
        0.0, 0.0, 1.0, z,
        0.0, 0.0, 0.0, 1.0,
    ]


def transform_local_vector_world(
    transform: list[float] | tuple[float, ...],
    vector_xyz_mm: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        transform[0] * vector_xyz_mm[0]
        + transform[1] * vector_xyz_mm[1]
        + transform[2] * vector_xyz_mm[2],
        transform[4] * vector_xyz_mm[0]
        + transform[5] * vector_xyz_mm[1]
        + transform[6] * vector_xyz_mm[2],
        transform[8] * vector_xyz_mm[0]
        + transform[9] * vector_xyz_mm[1]
        + transform[10] * vector_xyz_mm[2],
    )


def _max_transform_delta(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> float:
    return max(abs(float(left[index]) - float(right[index])) for index in range(16))


def _validate_roll_link_mates(kind: str, mates: RollLinkMates, upstream_servo_local: list[float]) -> None:
    bottom_servo_relative = multiply_transforms(
        invert_rigid_transform(mates.bracket_local),
        upstream_servo_local,
    )
    bottom_delta = _max_transform_delta(bottom_servo_relative, lc.BOTTOM_SERVO_TRANSFORM)
    if bottom_delta > MATE_TRANSFORM_TOLERANCE:
        raise RuntimeError(
            f"{kind} roll-link bottom servo mate drifted by {bottom_delta:.9f}; "
            "the bracket is no longer seated on the authored bottom-servo frame"
        )

    cable_face_normal = transform_local_vector_world(bottom_servo_relative, (0.0, -1.0, 0.0))
    cable_delta = max(
        abs(cable_face_normal[index] - expected)
        for index, expected in enumerate((0.0, 0.0, 1.0))
    )
    if cable_delta > MATE_TRANSFORM_TOLERANCE:
        raise RuntimeError(
            f"{kind} roll-link bottom servo cable face is not pointing up: "
            f"{tuple(round(value, 6) for value in cable_face_normal)}"
        )

    top_servo_relative = multiply_transforms(
        invert_rigid_transform(mates.bracket_local),
        mates.downstream_servo_local,
    )
    top_delta = _max_transform_delta(top_servo_relative, TOP_SERVO_FACE_TO_FLANGE_TRANSFORM)
    if top_delta > MATE_TRANSFORM_TOLERANCE:
        raise RuntimeError(
            f"{kind} roll-link top servo mate drifted by {top_delta:.9f}; "
            "the downstream servo is no longer seated on the authored top-servo frame"
        )


def _source_instances_by_name() -> dict[str, dict[str, object]]:
    return {
        str(instance["name"]): instance
        for instance in robot_arm._assembly_instances()
    }


def roll_link_mates(kind: str) -> RollLinkMates:
    spec = ROLL_LINK_SPECS[kind]
    source_instances = _source_instances_by_name()
    anchor = [float(value) for value in source_instances[spec.anchor]["transform"]]
    upstream_anchor_transform = [
        float(value) for value in source_instances[spec.upstream_anchor]["transform"]
    ]
    upstream_servo_transform = multiply_transforms(
        upstream_anchor_transform,
        spec.upstream_servo_transform,
    )
    upstream_servo_local = relative_transform(
        anchor_transform=anchor,
        transform=upstream_servo_transform,
    )
    old_downstream_servo_local = relative_transform(
        anchor_transform=anchor,
        transform=[
            float(value) for value in source_instances[spec.downstream_servo]["transform"]
        ],
    )
    bracket_local = multiply_transforms(
        upstream_servo_local,
        invert_rigid_transform(lc.BOTTOM_SERVO_TRANSFORM),
    )
    downstream_servo_local = multiply_transforms(
        bracket_local,
        TOP_SERVO_FACE_TO_FLANGE_TRANSFORM,
    )
    downstream_shift_local = tuple(
        downstream_servo_local[index] - old_downstream_servo_local[index]
        for index in (3, 7, 11)
    )

    mates = RollLinkMates(
        spec=spec,
        bracket_local=bracket_local,
        downstream_shift_local=downstream_shift_local,
        downstream_servo_local=downstream_servo_local,
    )
    _validate_roll_link_mates(kind, mates, upstream_servo_local)
    return mates


def downstream_mate_shift_local(kind: str) -> tuple[float, float, float]:
    return roll_link_mates(kind).downstream_shift_local


def roll_link_instances(kind: str) -> list[dict[str, object]]:
    mates = roll_link_mates(kind)
    spec = mates.spec

    return [
        {
            "path": RIGHT_BRACKET_PATH,
            "name": f"{kind}_link_bracket_right",
            "transform": mates.bracket_local,
        },
        {
            "path": LEFT_BRACKET_PATH,
            "name": f"{kind}_link_bracket_left",
            "transform": mates.bracket_local,
        },
        # Items 2 & 3: all 35 mm link-bracket standoffs (link_standoff_m3_35) removed.
        {
            "path": spec.downstream_servo_path,
            "name": spec.downstream_servo,
            "transform": mates.downstream_servo_local,
            "use_source_colors": True,
        },
    ]
