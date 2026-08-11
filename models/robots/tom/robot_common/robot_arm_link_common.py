from __future__ import annotations

import sys
from pathlib import Path
from pathlib import PurePosixPath

TOM_DIR = Path(__file__).resolve().parents[1]
if str(TOM_DIR) not in sys.path:
    sys.path.insert(0, str(TOM_DIR))

from robot_common import robot_arm


def _matrix(transform: list[float]) -> list[list[float]]:
    return [transform[index : index + 4] for index in range(0, 16, 4)]


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


def _invert_rigid_transform(transform: list[float]) -> list[list[float]]:
    matrix = _matrix(transform)
    rotation = [row[:3] for row in matrix[:3]]
    translation = [matrix[row][3] for row in range(3)]
    inverse_rotation = [[rotation[col][row] for col in range(3)] for row in range(3)]
    inverse_translation = [
        -sum(inverse_rotation[row][col] * translation[col] for col in range(3))
        for row in range(3)
    ]
    return [
        [*inverse_rotation[0], inverse_translation[0]],
        [*inverse_rotation[1], inverse_translation[1]],
        [*inverse_rotation[2], inverse_translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _relative_step_path(path: str) -> str:
    step_path = PurePosixPath(path)
    if step_path.parts and step_path.parts[0] in {"imports", "gripper"}:
        return (PurePosixPath("..") / "parts" / step_path).as_posix()
    if step_path.parts and step_path.parts[0] == "assemblies":
        return (PurePosixPath("..") / step_path).as_posix()
    return (PurePosixPath("..") / "parts" / step_path.name).as_posix()


def translated_instances(
    instances: list[dict[str, object]],
    *,
    names: frozenset[str],
    vector_xyz: tuple[float, float, float],
    distance_mm: float,
) -> list[dict[str, object]]:
    translated: list[dict[str, object]] = []
    for instance in instances:
        transform = [float(value) for value in instance["transform"]]
        if str(instance["name"]) in names:
            transform[3] += vector_xyz[0] * distance_mm
            transform[7] += vector_xyz[1] * distance_mm
            transform[11] += vector_xyz[2] * distance_mm
        translated.append({**instance, "transform": transform})
    return translated


def rebased_robot_arm_instances(
    *,
    source_ref: str,
    anchor_instance_name: str,
    extracted_instance_names: tuple[str, ...],
) -> list[dict[str, object]]:
    source_instances = {
        str(instance["name"]): instance
        for instance in robot_arm._assembly_instances()
    }
    missing = [
        name for name in extracted_instance_names if name not in source_instances
    ]
    if missing:
        raise RuntimeError(f"{source_ref} references missing source instances: {missing!r}")

    anchor = source_instances[anchor_instance_name]
    anchor_inverse = _invert_rigid_transform(
        [float(value) for value in anchor["transform"]]
    )

    instances: list[dict[str, object]] = []
    for name in extracted_instance_names:
        source = source_instances[name]
        relative_transform = _matmul(
            anchor_inverse,
            _matrix([float(value) for value in source["transform"]]),
        )
        instances.append(
            {
                "path": _relative_step_path(str(source["path"])),
                "name": str(source["name"]),
                "transform": _flatten(relative_transform),
                "use_source_colors": bool(source.get("use_source_colors", True)),
            }
        )
    return instances
