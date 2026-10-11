"""What a CAD view does with cadgen's tube skins, in numpy: the reference the tube
skin tests pose a payload with (``cadgen._internal.tube_skin_payload``)."""

from __future__ import annotations

import numpy as np


def joint_matrices(translations: np.ndarray, rotations: np.ndarray) -> np.ndarray:
    """Each joint's 4x4 from its origin and unit quaternion (x, y, z, w)."""
    x, y, z, w = rotations.T
    m = np.zeros((len(rotations), 4, 4))
    m[:, 0, :3] = np.column_stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)])
    m[:, 1, :3] = np.column_stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)])
    m[:, 2, :3] = np.column_stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)])
    m[:, :3, 3] = translations
    m[:, 3, 3] = 1.0
    return m


def view_skin(local: np.ndarray, along: np.ndarray, rest: np.ndarray, key: np.ndarray,
              placement: np.ndarray) -> np.ndarray:
    """What a CAD view draws, in the document: each component-local point blended
    between the two joints either side of it, joint j moving it by
    placement^-1 . key_j . rest_j^-1 . placement, then placed."""
    count = len(rest)
    matrices = np.linalg.inv(placement) @ joint_matrices(key[:, :3], key[:, 3:]) @ np.linalg.inv(
        joint_matrices(rest[:, :3], rest[:, 3:])) @ placement
    lower = np.minimum(np.floor(along).astype(int), count - 2)
    weight = (along - lower)[:, None]
    points = np.column_stack([local, np.ones(len(local))])
    blended = ((1 - weight) * np.einsum("vij,vj->vi", matrices[lower], points)
               + weight * np.einsum("vij,vj->vi", matrices[lower + 1], points))
    return (blended @ placement.T)[:, :3]
