"""A bending tube as a glTF skin: the one place a tube's motion is worked out.

A tube track (``animation_bake``) keys its centerline: one path and one twist per
key. Every renderer and every export draws that motion the same way, as a standard
glTF skin, so nothing downstream ever evaluates a path:

- JOINTS stand along the rest centerline at equal arc-length fractions, at most
  ``maxSegmentLength`` mm apart (:func:`joint_fractions`). Each is a frame: its
  origin on the centerline, its x axis the tangent, y and z the transported normal
  and binormal turned by the key's twist.
- A key POSES the joints: the same fractions of the key's own centerline, so a
  tube that lengthens stretches evenly (:func:`key_joints`). A key that is None is
  the rest.
- Each VERTEX is bound to the two joints either side of its rest arc length,
  weighted by where it falls between them (:func:`bind`). Blending two neighbouring
  joints reproduces the centerline's stretch exactly, so the joints need no scale,
  and a tube's end caps stay round.
- Between keys a player interpolates joints the way glTF's LINEAR sampler does:
  translations lerp, rotations slerp. The bake chooses keys under exactly that
  rule (``animation_bake``).

The mesh a skin binds is cadgen's own mesh of the component, placed in the space
the paths are authored in, and refined into bands of at most ``maxSegmentLength``
in rest arc length first (``tube_deformation.refine_rest_mesh``): a straight STEP
surface may have rings only at its ends, and a bend would otherwise draw a chord.
Each vertex also carries its rest material coordinates -- arc length in mm and the
two transverse offsets -- for a braided finish, which follows the twist because the
coordinates ride with the vertex.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from cadgen._internal import tube_deformation as td

# Joints per tube, at most: a 600 mm spring at 2 mm needs 301. Past this the joints
# spread out evenly instead of failing, and the bands stay as fine as asked.
MAX_JOINTS = 2048


@dataclass(frozen=True)
class Joints:
    """Joint frames at the skin's fractions: origins (n, 3) and unit quaternions
    (n, 4, xyzw) whose x axis is the tangent."""

    translations: np.ndarray
    rotations: np.ndarray


@dataclass(frozen=True)
class SkinnedTube:
    """A tube's mesh, refined and bound to its joints."""

    positions: np.ndarray  # (v, 3) float32, the space the paths are authored in
    normals: np.ndarray  # (v, 3) float32
    indices: np.ndarray  # (t * 3,) uint32
    source_triangles: np.ndarray | None  # (t,) the source triangle each came from
    joints: np.ndarray  # (v, 4) uint16, JOINTS_0
    weights: np.ndarray  # (v, 4) float32, WEIGHTS_0
    material: np.ndarray  # (v, 3) float32: rest arc length (mm), transverse u, v


def joint_fractions(rest: td.Path, spacing: float) -> np.ndarray:
    """The joints' arc-length fractions along the rest centerline: both ends, and
    none more than ``spacing`` mm from the next."""
    count = min(MAX_JOINTS, max(2, math.ceil(rest.length / spacing) + 1))
    return np.linspace(0.0, 1.0, count)


def _quaternions(tangent: np.ndarray, normal: np.ndarray, binormal: np.ndarray) -> np.ndarray:
    """Unit quaternions (n, 4, xyzw) of the rotations whose columns are the frames."""
    m = np.stack([tangent, normal, binormal], axis=2)  # (n, 3, 3), columns
    trace = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    q = np.empty((len(m), 4))
    rows = trace > 0
    if np.any(rows):
        s = np.sqrt(trace[rows] + 1.0) * 2.0
        q[rows] = np.column_stack([
            (m[rows, 2, 1] - m[rows, 1, 2]) / s, (m[rows, 0, 2] - m[rows, 2, 0]) / s,
            (m[rows, 1, 0] - m[rows, 0, 1]) / s, s / 4.0,
        ])
    for axis in range(3):
        rows = (trace <= 0) & (np.argmax(np.stack([m[:, 0, 0], m[:, 1, 1], m[:, 2, 2]], axis=1), axis=1) == axis)
        if not np.any(rows):
            continue
        i, j, k = axis, (axis + 1) % 3, (axis + 2) % 3
        s = np.sqrt(1.0 + m[rows, i, i] - m[rows, j, j] - m[rows, k, k]) * 2.0
        part = np.empty((int(rows.sum()), 4))
        part[:, i] = s / 4.0
        part[:, j] = (m[rows, j, i] + m[rows, i, j]) / s
        part[:, k] = (m[rows, k, i] + m[rows, i, k]) / s
        part[:, 3] = (m[rows, k, j] - m[rows, j, k]) / s
        q[rows] = part
    return q / np.linalg.norm(q, axis=1)[:, None]


def joints_on(path: td.Path, fractions: np.ndarray, twist_deg: float = 0.0) -> Joints:
    """The joints a centerline carries: its frames at ``fractions`` of its length,
    turned by ``twist_deg`` about their tangents."""
    frames = td.sample_frames(path, fractions * path.length)
    c, s = math.cos(math.radians(twist_deg)), math.sin(math.radians(twist_deg))
    normal = frames.normal * c + frames.binormal * s
    binormal = -frames.normal * s + frames.binormal * c
    return Joints(frames.point.copy(), _quaternions(frames.tangent, normal, binormal))


def compile_rest(rest_spec: Mapping[str, Any]) -> td.Path:
    """A track's rest centerline, compiled once for every key of it."""
    return td.compile_tube_path(td.canonical_path_spec(rest_spec), canonical=True)


def key_joints(key: Mapping[str, Any] | None, rest_spec: Mapping[str, Any], rest: td.Path,
               fractions: np.ndarray) -> Joints:
    """One key's joints, as written in a sidecar: its centerline's frames, or the
    rest's for a None key. The key compiles as every reader of a sidecar compiles
    it (``tube_deformation.compile_deformation``): a key that maps the rest on the
    rest's own tables."""
    from cadgen._internal.animation_bake import key_path

    if key is None:
        return joints_on(rest, fractions)
    deformation = td.normalize_tube_deformation({
        "rest": rest_spec, "path": key_path(rest_spec, key["path"]),
        "twistDeg": key.get("twistDeg") or 0.0, "mapsRest": "map" in key["path"],
    })
    compiled = td.compile_deformation(deformation)
    return joints_on(compiled.path, fractions, compiled.twist_deg)


def slerp(a: np.ndarray, b: np.ndarray, u: float) -> np.ndarray:
    """glTF's LINEAR rotation: spherical interpolation, row by row, the near way."""
    dot = np.sum(a * b, axis=1)
    b = np.where(dot[:, None] < 0, -b, b)
    dot = np.abs(dot)
    out = np.empty_like(a)
    close = dot > 0.9995
    out[close] = a[close] + (b[close] - a[close]) * u
    far = ~close
    if np.any(far):
        theta = np.arccos(np.clip(dot[far], -1.0, 1.0))
        sin = np.sin(theta)
        out[far] = (np.sin((1 - u) * theta) / sin)[:, None] * a[far] + (np.sin(u * theta) / sin)[:, None] * b[far]
    return out / np.linalg.norm(out, axis=1)[:, None]


def between(a: Joints, b: Joints, u: float) -> Joints:
    """The joints a glTF player draws a fraction ``u`` of the way from key a to key b."""
    return Joints(a.translations + (b.translations - a.translations) * u, slerp(a.rotations, b.rotations, u))


def joint_error(estimate: Joints, truth: Joints) -> tuple[float, float]:
    """How far ``estimate`` sits from ``truth``: the largest origin distance (mm) and
    the largest turn between frames (degrees)."""
    moved = float(np.max(np.linalg.norm(estimate.translations - truth.translations, axis=1)))
    dot = np.clip(np.abs(np.sum(estimate.rotations * truth.rotations, axis=1)), 0.0, 1.0)
    turned = float(np.degrees(2.0 * np.arccos(np.min(dot))))
    return moved, turned


def continuous(keys: list[Joints]) -> list[Joints]:
    """The keys with each joint's quaternion kept on the side of its previous key's,
    so a player slerps the short way between every pair."""
    out: list[Joints] = []
    for joints in keys:
        if out:
            flip = np.sum(out[-1].rotations * joints.rotations, axis=1) < 0
            joints = Joints(joints.translations, np.where(flip[:, None], -joints.rotations, joints.rotations))
        out.append(joints)
    return out


def inverse_binds(rest: Joints) -> np.ndarray:
    """Each joint's inverse bind matrix (n, 4, 4), column-major as glTF stores them:
    the inverse of its rest frame."""
    q = rest.rotations
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    r = np.empty((len(q), 3, 3))
    r[:, 0, 0] = 1 - 2 * (y * y + z * z)
    r[:, 0, 1] = 2 * (x * y - z * w)
    r[:, 0, 2] = 2 * (x * z + y * w)
    r[:, 1, 0] = 2 * (x * y + z * w)
    r[:, 1, 1] = 1 - 2 * (x * x + z * z)
    r[:, 1, 2] = 2 * (y * z - x * w)
    r[:, 2, 0] = 2 * (x * z - y * w)
    r[:, 2, 1] = 2 * (y * z + x * w)
    r[:, 2, 2] = 1 - 2 * (x * x + y * y)
    inverse = np.zeros((len(q), 4, 4))
    rt = np.transpose(r, (0, 2, 1))
    inverse[:, :3, :3] = rt
    inverse[:, :3, 3] = -np.einsum("nij,nj->ni", rt, rest.translations)
    inverse[:, 3, 3] = 1.0
    return np.transpose(inverse, (0, 2, 1))  # column-major


def bind(mesh: td.RestMesh, rest: td.Path, spacing: float, fractions: np.ndarray) -> SkinnedTube:
    """``mesh`` (in the space the paths are authored in), refined into bands of at
    most ``spacing`` mm and bound to the joints at ``fractions``."""
    refined = td.refine_rest_mesh(mesh, rest, spacing)
    mapping = td.mapping_for(refined, rest)
    values = mapping.values[mapping.slots]
    along = np.clip(values[:, 0], 0.0, 1.0) * (len(fractions) - 1)
    lower = np.minimum(np.floor(along).astype(np.int64), len(fractions) - 2)
    upper_weight = (along - lower).astype(np.float32)
    count = len(refined.positions)
    joints = np.zeros((count, 4), dtype=np.uint16)
    joints[:, 0] = lower
    joints[:, 1] = lower + 1
    weights = np.zeros((count, 4), dtype=np.float32)
    weights[:, 0] = 1.0 - upper_weight
    weights[:, 1] = upper_weight
    material = np.column_stack([values[:, 0] * rest.length, values[:, 1], values[:, 2]]).astype(np.float32)
    return SkinnedTube(
        positions=refined.positions.astype(np.float32), normals=refined.normals.astype(np.float32),
        indices=refined.indices.astype(np.uint32), source_triangles=refined.source_triangles,
        joints=joints, weights=weights, material=material,
    )


def skin(joints: Joints, rest: Joints, tube: SkinnedTube) -> np.ndarray:
    """``tube``'s vertices posed by ``joints``, as a glTF player skins them: the
    weighted sum of each joint's pose times its inverse bind. A reference for tests
    and checks; no renderer calls it."""
    binds = np.transpose(inverse_binds(rest), (0, 2, 1))  # row-major again
    q = joints.rotations
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    pose = np.zeros((len(q), 4, 4))
    pose[:, 0, 0] = 1 - 2 * (y * y + z * z)
    pose[:, 0, 1] = 2 * (x * y - z * w)
    pose[:, 0, 2] = 2 * (x * z + y * w)
    pose[:, 1, 0] = 2 * (x * y + z * w)
    pose[:, 1, 1] = 1 - 2 * (x * x + z * z)
    pose[:, 1, 2] = 2 * (y * z - x * w)
    pose[:, 2, 0] = 2 * (x * z - y * w)
    pose[:, 2, 1] = 2 * (y * z + x * w)
    pose[:, 2, 2] = 1 - 2 * (x * x + y * y)
    pose[:, :3, 3] = joints.translations
    pose[:, 3, 3] = 1.0
    matrices = pose @ binds
    p = np.column_stack([tube.positions.astype(np.float64), np.ones(len(tube.positions))])
    out = np.zeros((len(p), 4))
    for slot in range(2):
        index = tube.joints[:, slot].astype(np.int64)
        out += tube.weights[:, slot, None] * np.einsum("vij,vj->vi", matrices[index], p)
    return out[:, :3]
