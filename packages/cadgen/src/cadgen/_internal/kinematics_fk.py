"""The Python half of the mates FK evaluator (design/pose-animation-split.md).

Mirrors ``packages/cadgen-js/src/common/kinematicsRuntime.js`` operation for
operation: effective DOF values (defaults, then additive coupling gears), one
motion matrix per mate about its world-at-rest axis, deltas composed down the
mate tree. Pure 4x4 arithmetic on plain floats — deterministic to the bit, no
OCP import — so a viewer slider position and an exported bake agree.

Matrices are row-major 4x4 nested lists; assembly.json occurrence transforms are
the 12-float row-major [R|t] form (rotation rows + translation column), and
deltas PREMULTIPLY absolute transforms exactly like the viewer's effectMatrix
premultiplies baseTransform.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

_CYLINDRICAL_DOFS = ("turn", "travel")


def identity4() -> list[list[float]]:
    return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def matmul4(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]


def transform_point(matrix: list[list[float]], point: tuple[float, float, float]) -> list[float]:
    x, y, z = point
    return [
        matrix[i][0] * x + matrix[i][1] * y + matrix[i][2] * z + matrix[i][3]
        for i in range(3)
    ]


def transform_vector(matrix: list[list[float]], vector: tuple[float, float, float]) -> list[float]:
    x, y, z = vector
    return [matrix[i][0] * x + matrix[i][1] * y + matrix[i][2] * z for i in range(3)]


def matrix_from_rows12(rows: list[float]) -> list[list[float]]:
    """assembly.json occurrence transform (12 floats, row-major [R|t]) -> 4x4."""
    return [
        [rows[0], rows[1], rows[2], rows[3]],
        [rows[4], rows[5], rows[6], rows[7]],
        [rows[8], rows[9], rows[10], rows[11]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def rows12_from_matrix(matrix: list[list[float]]) -> list[float]:
    return [matrix[i][j] for i in range(3) for j in range(4)]


def _rotation_about_axis(origin: list[float], direction: list[float], angle_deg: float) -> list[list[float]]:
    angle = math.radians(angle_deg)
    x, y, z = direction
    c, s, t = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    rot = [
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ]
    # Conjugate by the origin so the axis line is fixed: T(o) R T(-o).
    translation = [
        origin[i] - sum(rot[i][j] * origin[j] for j in range(3))
        for i in range(3)
    ]
    return [
        [*rot[0], translation[0]],
        [*rot[1], translation[1]],
        [*rot[2], translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _translation_along(direction: list[float], distance: float) -> list[list[float]]:
    matrix = identity4()
    for i in range(3):
        matrix[i][3] = direction[i] * distance
    return matrix


def _axis_numbers(mate: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    axis = mate.get("axis") or {}
    origin = axis.get("origin")
    direction = axis.get("dir")
    if not (isinstance(origin, list) and isinstance(direction, list) and len(origin) == 3 and len(direction) == 3):
        raise ValueError(f"kinematics mate {mate.get('name')}: axis is not resolved to numbers")
    length = math.hypot(*direction) or 1.0
    return [float(v) for v in origin], [float(v) / length for v in direction]


def mate_dof_ids(block: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for mate in block.get("mates", ()):
        if mate.get("kind") == "fastened":
            continue
        if mate.get("kind") == "cylindrical":
            ids.extend(f"{mate['name']}.{sub}" for sub in _CYLINDRICAL_DOFS)
        else:
            ids.append(str(mate["name"]))
    return ids


def effective_dof_values(block: Mapping[str, Any], values: Mapping[str, Any] | None) -> dict[str, float]:
    """Explicit value else 0 (ZERO IS THE ARTIFACT AS WRITTEN), plus additive
    coupling gearing — the identical rule the viewer runtime applies."""
    raw = dict(values or {})
    effective = {dof: 0.0 for dof in mate_dof_ids(block)}
    for dof in effective:
        if dof in raw:
            effective[dof] = float(raw[dof])
    for coupling in block.get("couplings", ()):
        amount = float(raw.get(str(coupling.get("name")), 0.0) or 0.0)
        if not amount:
            continue
        for dof, ratio in (coupling.get("gears") or {}).items():
            effective[dof] = effective.get(dof, 0.0) + float(ratio) * amount
    return effective


def _mate_motion(mate: Mapping[str, Any], effective: Mapping[str, float]) -> list[list[float]]:
    kind = mate.get("kind")
    if kind == "fastened":
        return identity4()
    origin, direction = _axis_numbers(mate)
    name = str(mate.get("name"))
    motion = identity4()
    if kind == "revolute":
        angle = effective.get(name, 0.0)
        if angle:
            motion = _rotation_about_axis(origin, direction, angle)
    elif kind == "slider":
        distance = effective.get(name, 0.0)
        if distance:
            motion = _translation_along(direction, distance)
    elif kind == "cylindrical":
        turn = effective.get(f"{name}.turn", 0.0)
        travel = effective.get(f"{name}.travel", 0.0)
        if turn:
            motion = _rotation_about_axis(origin, direction, turn)
        if travel:
            motion = matmul4(_translation_along(direction, travel), motion)
    else:
        raise ValueError(f"kinematics mate {name}: unknown kind {kind!r}")
    return motion


def mates_in_tree_order(mates: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    by_child = {mate["child"]: mate for mate in mates}
    ordered: list[Mapping[str, Any]] = []
    placed: set[str] = set()

    def place(mate: Mapping[str, Any]) -> None:
        if mate["child"] in placed:
            return
        parent_mate = by_child.get(mate["parent"])
        if parent_mate is not None and parent_mate["child"] not in placed:
            place(parent_mate)
        placed.add(mate["child"])
        ordered.append(mate)

    for mate in mates:
        place(mate)
    return ordered


def kinematics_deltas(
    block: Mapping[str, Any], values: Mapping[str, Any] | None
) -> dict[str, list[list[float]]]:
    """DOF values -> one world-space delta per mated child ref ('#label').

    Apply a delta by PREMULTIPLYING the absolute transforms of every
    occurrence in that child's instance subtree; a deeper mate's children get
    their own (already composed) delta.
    """
    effective = effective_dof_values(block, values)
    deltas: dict[str, list[list[float]]] = {}
    for mate in mates_in_tree_order(list(block.get("mates", ()))):
        motion = _mate_motion(mate, effective)
        parent_delta = deltas.get(str(mate["parent"]))
        deltas[str(mate["child"])] = matmul4(parent_delta, motion) if parent_delta else motion
    return deltas


def parent_chain_deltas(
    block: Mapping[str, Any], values: Mapping[str, Any] | None
) -> dict[str, list[list[float]]]:
    """Per mate NAME: the delta of everything above it (its parent chain,
    excluding its own motion). This is what carries a mate's AXIS when the
    artifact is baked at a pose — a hinge axis rides with the parent link, and
    its own rotation leaves it invariant."""
    effective = effective_dof_values(block, values)
    child_delta: dict[str, list[list[float]]] = {}
    chain: dict[str, list[list[float]]] = {}
    for mate in mates_in_tree_order(list(block.get("mates", ()))):
        parent_delta = child_delta.get(str(mate["parent"]))
        chain[str(mate["name"])] = parent_delta if parent_delta is not None else identity4()
        motion = _mate_motion(mate, effective)
        child_delta[str(mate["child"])] = (
            matmul4(parent_delta, motion) if parent_delta is not None else motion
        )
    return chain
