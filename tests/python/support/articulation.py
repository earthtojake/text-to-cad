"""The articulation played in closed form: the reference a page's player is compared against.

``cadgen.robot_payload`` resolves a robot description's kinematics into the articulation a page
plays; this plays it as the page must: joint values from the controls by dot products (plus a curve's
interpolated term), and each joint's world delta from its parent's and its own displacement.
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Mapping


def _curve_value(curve: Mapping[str, Any], values: Mapping[str, float]) -> float:
    """A curve's term at a control vector: its driver row's value, folded into one period when
    the curve has one, interpolated linearly between its keys and held beyond them."""
    inputs = [float(v) for v in curve.get("input") or []]
    outputs = [float(v) for v in curve.get("output") or []]
    count = min(len(inputs), len(outputs))
    if not count:
        return 0.0
    x = row_value(curve.get("driver"), values)
    period = float(curve.get("period") or 0.0)
    if period > 0:
        x = inputs[0] + (x - inputs[0]) % period
    if x <= inputs[0]:
        return outputs[0]
    if x >= inputs[count - 1]:
        return outputs[count - 1]
    after = bisect.bisect_right(inputs, x, 0, count)
    before = after - 1
    span = inputs[after] - inputs[before]
    t = (x - inputs[before]) / span if span > 0 else 0.0
    return outputs[before] + t * (outputs[after] - outputs[before])


def row_value(row: Mapping[str, Any] | None, values: Mapping[str, float]) -> float:
    """``bias + sum(weight * control)``, plus the row's curve at the vector when it has one."""
    if not row:
        return 0.0
    total = float(row.get("bias") or 0.0) + sum(
        float(weight) * float(values.get(str(control), 0.0)) for control, weight in row.get("terms") or [])
    curve = row.get("curve")
    if isinstance(curve, Mapping):
        total += _curve_value(curve, values)
    return total


def joint_values(articulation: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """Every joint's ``{"turn": degrees, "travel": units}`` at a control vector: the rows'
    dot products (and a curve's interpolated term), nothing else."""
    return {
        str(joint["id"]): {"turn": row_value(joint.get("turn"), values), "travel": row_value(joint.get("travel"), values)}
        for joint in articulation.get("joints") or []
    }


def _multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _motion(origin: list[float], axis: list[float], turn_deg: float, travel: float) -> list[list[float]]:
    """D(axis, q) in rest space: the turn about the axis line, then the travel along it
    (the two commute, both being about one axis)."""
    x, y, z = axis
    c = math.cos(math.radians(turn_deg))
    s = math.sin(math.radians(turn_deg))
    t = 1.0 - c
    r = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
         [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
         [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    ox, oy, oz = origin
    # T(o) R T(-o) T(axis * travel): translation column = o - R o + axis * travel.
    translation = [ox - (r[0][0] * ox + r[0][1] * oy + r[0][2] * oz) + x * travel,
                   oy - (r[1][0] * ox + r[1][1] * oy + r[1][2] * oz) + y * travel,
                   oz - (r[2][0] * ox + r[2][1] * oy + r[2][2] * oz) + z * travel]
    return [[*r[0], translation[0]], [*r[1], translation[1]], [*r[2], translation[2]], [0.0, 0.0, 0.0, 1.0]]


def joint_matrices(articulation: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, list[list[float]]]:
    """Every joint's world delta (row-major 4x4) at a control vector: its parent's delta
    times its own displacement. Applied as ``delta @ rest_placement`` to each occurrence
    the joint carries, this is the pose."""
    rows = joint_values(articulation, values)
    identity = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    deltas: dict[str, list[list[float]]] = {}
    for joint in articulation.get("joints") or []:
        joint_id = str(joint["id"])
        parent = deltas.get(str(joint.get("parent") or ""), identity)
        if joint.get("kind") == "fixed" or "axis" not in joint:
            deltas[joint_id] = parent
            continue
        own = rows[joint_id]
        deltas[joint_id] = _multiply(parent, _motion(joint["origin"], joint["axis"], own["turn"], own["travel"]))
    return deltas
