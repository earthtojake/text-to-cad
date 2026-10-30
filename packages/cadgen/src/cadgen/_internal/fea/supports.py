"""Supports: the faces a study holds, as the nodes and directions CalculiX holds.

A study's ``fixtures`` are ``fixed`` (every component of every node on the faces held at zero) or ``roller`` (a
frictionless support: the face slides in its own plane but never moves along its normal). A roller holds each of its
nodes along the face's normal there, per facet: each roller face's facet normals around the node, weighted by area, give
the node a direction (on a curved face, the local normal), and where two roller faces meet at an edge or a corner the
node is held along each of theirs (the principal directions of ``Σ n nᵀ`` over the faces, one per face that is not
tangent to another).

Where every held direction is a global axis (a roller on a face square to X, Y or Z) the hold is that axis. Anywhere
else (a sloped or curved roller face) the node gets its own frame, its held directions first, and is held along those
axes of it (CalculiX's ``*TRANSFORM``).

A DOF is ``3 * node + axis``. One on the edge two fixtures share is held once, so its reaction is counted once
(``per_fixture`` is disjoint): it goes to the fixture that holds its component most, a fixed face fully and a roller by
its normal's share of that component there, the first such fixture on a tie. Numeric imports live inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.mesh import VolumeMesh
    from cadgen._internal.fea.study import Fixture

__all__ = ["AXIS_TOLERANCE", "EDGE_SHARE", "Supports", "check_held", "not_held_sentence", "supports_of", "unheld_motions"]

#: A held direction within this of a global axis (each component) is that axis.
AXIS_TOLERANCE = 1e-6
#: At a node on several roller faces, a second (third) direction counts when its weight in Σ n nᵀ is at least this
#: share of the first: faces meeting at an edge; under it the faces are nearly tangent and the node is held along
#: their mean normal alone.
EDGE_SHARE = 0.2


@dataclass
class Supports:
    #: The held DOF: ``3 * node + axis``, the axis global, or the node's own where ``frames`` has one.
    fixed: "np.ndarray"
    #: Per fixture (by index), the global DOF its reaction sums: disjoint.
    per_fixture: "list[np.ndarray]"
    #: node -> (3, 3) its frame, columns its axes (global = frame @ local).
    frames: "dict[int, np.ndarray]" = field(default_factory=dict)
    rollers: bool = False

    def held(self) -> list[tuple[int, int]]:
        """``(node, axis)`` of every held DOF, as CalculiX's boundary conditions name them."""
        return [(int(dof) // 3, int(dof) % 3) for dof in self.fixed.tolist()]

    def local_vector(self, rows: "np.ndarray") -> "np.ndarray":
        """``rows`` (3N, ...) given in the global axes, each framed node's three in its own frame."""
        out = rows.copy()
        for node, frame in self.frames.items():
            out[3 * node:3 * node + 3] = frame.T @ rows[3 * node:3 * node + 3]
        return out


def _facet_normals(points: "np.ndarray", triangles: "np.ndarray") -> "np.ndarray":
    """Each boundary triangle's normal, 2 × its area long."""
    import numpy as np

    corners = points[triangles[:, :3]]
    return np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])


def _rows_on(volume: "VolumeMesh", ordinals: "set[int]") -> "np.ndarray":
    import numpy as np

    return np.flatnonzero(np.isin(np.asarray(volume.boundary_ordinal), list(ordinals)))


def _roller_directions(volume: "VolumeMesh", roller_ordinals: "list[set[int]]") -> "dict[int, np.ndarray]":
    """Each roller node -> its held directions, (r, 3) orthonormal rows, r in 1..3."""
    import numpy as np

    boundary = np.asarray(volume.boundary)
    ordinal = np.asarray(volume.boundary_ordinal)
    per_node: dict[int, np.ndarray] = {}
    for ordinals in roller_ordinals:
        rows = _rows_on(volume, ordinals)
        if not len(rows):
            continue
        normal = _facet_normals(volume.nodes, boundary[rows])
        area = np.linalg.norm(normal, axis=1)
        unit = normal / np.where(area > 0, area, 1.0)[:, None]
        outer = area[:, None, None] * unit[:, :, None] * unit[:, None, :]
        # Per face: each node's area-weighted Σ n nᵀ over its facets, normalised, so every face weighs one.
        for face in sorted({int(o) for o in ordinal[rows]}):
            mine = ordinal[rows] == face
            nodes = boundary[rows[mine]]
            unique, inverse = np.unique(nodes.ravel(), return_inverse=True)
            summed = np.zeros((len(unique), 3, 3))
            np.add.at(summed, inverse, np.repeat(outer[mine], nodes.shape[1], axis=0))
            norm = np.zeros(len(unique))
            np.add.at(norm, inverse, np.repeat(area[mine], nodes.shape[1]))
            summed /= np.where(norm > 0, norm, 1.0)[:, None, None]
            for node, matrix in zip(unique.tolist(), summed):
                per_node[node] = per_node.get(node, 0.0) + matrix
    directions: dict[int, np.ndarray] = {}
    for node, matrix in per_node.items():
        values, vectors = np.linalg.eigh(matrix)
        order = np.argsort(values)[::-1]
        values, vectors = values[order], vectors[:, order]
        rank = int((values >= EDGE_SHARE * values[0]).sum()) if values[0] > 0 else 0
        if rank:
            directions[node] = vectors[:, :rank].T
    return directions


def _fixture_normals(volume: "VolumeMesh", ordinals: "set[int]") -> "tuple[np.ndarray, np.ndarray]":
    """The roller fixture's nodes and their unit normals: the area-weighted sum of its facets' normals."""
    import numpy as np

    rows = _rows_on(volume, ordinals)
    if not len(rows):
        return np.zeros(0, dtype=np.int64), np.zeros((0, 3))
    nodes = np.asarray(volume.boundary)[rows]
    normal = _facet_normals(volume.nodes, nodes)
    unique, inverse = np.unique(nodes.ravel(), return_inverse=True)
    summed = np.zeros((len(unique), 3))
    np.add.at(summed, inverse, np.repeat(normal, nodes.shape[1], axis=0))
    length = np.linalg.norm(summed, axis=1)
    return unique, summed / np.where(length > 0, length, 1.0)[:, None]


def _disjoint(volume: "VolumeMesh", fixtures, per_fixture: "list[np.ndarray]", ordinal_of: dict[str, int]) -> "list[np.ndarray]":
    """``per_fixture`` with each DOF shared by several fixtures kept in one: the one holding its component most."""
    import numpy as np

    if len(per_fixture) < 2:
        return per_fixture
    size = 3 * len(volume.nodes)
    counts = np.zeros(size, dtype=np.int64)
    for dofs in per_fixture:
        counts[np.unique(dofs)] += 1
    if not (counts > 1).any():
        return per_fixture
    owner = np.full(size, -1, dtype=np.int64)
    best = np.full(size, -1.0)
    for index, (dofs, fixture) in enumerate(zip(per_fixture, fixtures)):
        dofs = np.unique(dofs)
        if fixture.type == "roller":
            nodes, normals = _fixture_normals(volume, {ordinal_of[ref] for ref in fixture.faces})
            share = np.zeros((len(volume.nodes), 3))
            share[nodes] = np.abs(normals)
            hold = share[dofs // 3, dofs % 3]
        else:
            hold = np.ones(len(dofs))
        better = hold > best[dofs] + 1e-9
        owner[dofs[better]] = index
        best[dofs[better]] = hold[better]
    return [dofs[owner[dofs] == index] for index, dofs in enumerate(per_fixture)]


def _axes_of(directions: "np.ndarray") -> "list[int] | None":
    """The global axes spanning the held directions exactly, or None when they are not axes."""
    import numpy as np

    reach = np.linalg.norm(directions @ np.eye(3), axis=0)  # each axis's length inside the span
    on = np.abs(reach - 1.0) <= AXIS_TOLERANCE
    off = reach <= AXIS_TOLERANCE
    if not np.all(on | off) or int(on.sum()) != len(directions):
        return None
    return [int(k) for k in np.flatnonzero(on)]


def _node_dofs(nodes: "np.ndarray") -> "np.ndarray":
    import numpy as np

    return (3 * np.asarray(nodes, dtype=np.int64)[:, None] + np.arange(3)).ravel()


def supports_of(volume: "VolumeMesh", fixtures: "tuple[Fixture, ...]", ordinal_of: dict[str, int]) -> Supports:
    """The study's supports on ``volume``: fixed faces and rollers."""
    import numpy as np

    boundary = np.asarray(volume.boundary)
    on_faces = [_node_dofs(np.unique(boundary[_rows_on(volume, {ordinal_of[ref] for ref in fixture.faces})]))
                for fixture in fixtures]
    per_fixture = _disjoint(volume, fixtures, on_faces, ordinal_of)
    clamped = [dofs for dofs, fixture in zip(on_faces, fixtures) if fixture.type != "roller"]
    fixed = np.unique(np.concatenate(clamped)) if clamped else np.zeros(0, dtype=np.int64)
    rollers = [fixture for fixture in fixtures if fixture.type == "roller"]
    if not rollers:
        return Supports(fixed=fixed, per_fixture=per_fixture)

    clamped_nodes = set((fixed // 3).tolist())             # a fixed face's node: every component held already
    directions = _roller_directions(volume, [{ordinal_of[ref] for ref in fixture.faces} for fixture in rollers])
    more: list[int] = []
    frames: dict[int, np.ndarray] = {}
    for node, held_dirs in directions.items():
        if node in clamped_nodes:
            continue
        axes = _axes_of(held_dirs)
        if axes is not None:
            more.extend(3 * node + k for k in axes)
            continue
        # The node's own frame: its held directions first, then the rest of a right-handed orthonormal basis.
        q, _ = np.linalg.qr(np.vstack([held_dirs, np.eye(3)]).T, mode="complete")
        frame = q[:, :3]
        frame[:, :len(held_dirs)] = held_dirs.T  # exactly the held directions (QR may flip a sign)
        frame, _ = np.linalg.qr(frame)
        if np.linalg.det(frame) < 0:
            frame[:, 2] = -frame[:, 2]            # CalculiX's local z is x × y
        frames[node] = frame
        more.extend(3 * node + k for k in range(len(held_dirs)))
    fixed = np.unique(np.concatenate([fixed, np.asarray(more, dtype=np.int64)]))
    return Supports(fixed=fixed, per_fixture=per_fixture, frames=frames, rollers=True)


def _unit_modes(points: "np.ndarray") -> "np.ndarray":
    """(3N, 6) the six rigid motions of the points (three translations, three rotations), about their centre and
    scaled by their size."""
    import numpy as np

    centre, size = points.mean(axis=0), float(np.ptp(points, axis=0).max()) or 1.0
    x = (points - centre) / size
    modes = np.zeros((len(points), 3, 6))
    for k in range(3):
        modes[:, k, k] = 1.0
    # Rotations about x, y and z: ω × x.
    modes[:, 1, 3], modes[:, 2, 3] = -x[:, 2], x[:, 1]
    modes[:, 0, 4], modes[:, 2, 4] = x[:, 2], -x[:, 0]
    modes[:, 0, 5], modes[:, 1, 5] = -x[:, 1], x[:, 0]
    return modes.reshape(3 * len(points), 6)


def _held_motions(rows: "np.ndarray") -> int:
    """How many of the six rigid motions the held rows (held DOF x 6) stop."""
    import numpy as np

    if not len(rows):
        return 0
    values = np.linalg.svd(rows, compute_uv=False)
    return int((values > 1e-8 * max(float(values.max()), 1e-300)).sum())


def unheld_motions(volume: "VolumeMesh", supports: Supports) -> int:
    """How many rigid motions (of 6) the supports leave the whole mesh free to make: 0 when it is held."""
    return 6 - _held_motions(supports.local_vector(_unit_modes(volume.nodes))[supports.fixed])


def not_held_sentence(loose: int) -> str:
    """The plain error for supports that leave the part free to move."""
    return (f"the fixtures leave the part free to slide or turn ({loose} of its 6 rigid motions): a roller face holds "
            "it only along its normal, so rollers alone need faces facing at least three ways (like a block's corner); "
            "add a roller on another face, or fix a face")


def check_held(volume: "VolumeMesh", supports: Supports) -> None:
    """Refuse, in a sentence, supports that leave the part free to move."""
    if loose := unheld_motions(volume, supports):
        raise ValueError(not_held_sentence(loose))
