"""Supports: the faces a study holds, as the displacement DOF they hold.

A study's ``fixtures`` are ``fixed`` (every component of every node on the
faces held at zero) or ``roller`` (a frictionless support: the face slides in
its own plane but never moves along its normal). A roller holds each of its
nodes along the face's normal there, per facet: each roller face's facet
normals around the node, weighted by area, give the node a direction (on a
curved face, the local normal), and where two roller faces meet at an edge
or a corner the node is held along each of theirs (the principal directions
of ``Σ n nᵀ`` over the faces, one per face that is not tangent to another).

Where every held direction is a global axis (a roller on a face square to X,
Y or Z) the hold is that component's DOF, exactly as a symmetry plane's: the
system is solved in the global axes, unchanged. Anywhere else (a sloped or
curved roller face) the node's three DOF are turned into its own frame
(``frame``, an orthogonal block-diagonal matrix with ``u_global = frame @
u_local``) and the held directions are DOF of that frame: an analysis solves
``frameᵀ K frame`` on the free DOF and turns the answer back. :class:`Turned`
does that for a nonlinear problem the driver follows.

A study with only fixed faces gives exactly the DOF it always did, in the same
order. Numeric imports live inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.study import Fixture

__all__ = [
    "AXIS_TOLERANCE", "EDGE_SHARE", "Supports", "Turned", "check_held", "driven", "has_rollers", "held_bodies", "not_held_sentence", "path_to_global",
    "supports_of", "unheld_motions",
]

#: A held direction within this of a global axis (each component) is that axis: the plain DOF is held.
AXIS_TOLERANCE = 1e-6
#: At a node on several roller faces, a second (third) direction counts when its weight in Σ n nᵀ is at least this
#: share of the first: faces meeting at an edge; under it the faces are nearly tangent and the node is held along
#: their mean normal alone.
EDGE_SHARE = 0.2


@dataclass
class Supports:
    """The DOF a study holds, and the frame they are held in."""

    #: Sorted DOF held at zero: in ``frame``'s axes where a node is turned, else the global ones.
    fixed: "np.ndarray"
    #: Every DOF of each fixture's faces, in the study's order (global), for its reaction.
    per_fixture: "list[np.ndarray]"
    #: (N, N) orthogonal, ``u_global = frame @ u_local``; ``None`` when every node keeps the global axes.
    frame: Any = None
    #: Whether any fixture is a roller.
    rollers: bool = False
    #: Scalar DOF of the turned nodes, for tests and the log.
    turned_nodes: "np.ndarray | None" = field(default=None, repr=False)

    @property
    def turned(self) -> bool:
        return self.frame is not None

    def free(self, size: int) -> "np.ndarray":
        import numpy as np

        return np.setdiff1d(np.arange(size), self.fixed)

    def local(self, matrix):
        """A global matrix in the supports' frame: ``frameᵀ A frame`` (CSR); the matrix itself when nothing is turned."""
        if self.frame is None:
            return matrix
        return (self.frame.T @ matrix @ self.frame).tocsr()

    def local_vector(self, vector: "np.ndarray") -> "np.ndarray":
        """A global vector (or columns) in the supports' frame: ``frameᵀ v``."""
        return vector if self.frame is None else self.frame.T @ vector

    def global_vector(self, vector: "np.ndarray") -> "np.ndarray":
        """A vector (or columns) of the supports' frame back in global axes: ``frame v``."""
        return vector if self.frame is None else self.frame @ vector


def has_rollers(fixtures) -> bool:
    """Whether any fixture is a roller (stdlib: what a ladder rung reads before meshing)."""
    return any(getattr(fixture, "type", "fixed") == "roller" for fixture in fixtures or ())


def _roller_directions(space: "FemSpace", roller_ordinals: "list[set[int]]") -> "dict[int, np.ndarray]":
    """Each roller node (scalar DOF) -> its held directions, (r, 3) orthonormal rows, r in 1..3."""
    import numpy as np

    boundary = space.boundary_quadratic
    ordinal = np.asarray(space.volume.boundary_ordinal)
    points = space.dof_locations
    per_node: dict[int, np.ndarray] = {}
    for ordinals in roller_ordinals:
        rows = np.flatnonzero(np.isin(ordinal, list(ordinals)))
        if not len(rows):
            continue
        corners = points[boundary[rows, :3]]
        normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])  # 2 × area along the normal
        area = np.linalg.norm(normal, axis=1)
        unit = normal / np.where(area > 0, area, 1.0)[:, None]
        outer = area[:, None, None] * unit[:, :, None] * unit[:, None, :]
        # Per face: each node's area-weighted Σ n nᵀ over its facets, normalised, so every face weighs one.
        for face in sorted({int(o) for o in ordinal[rows]}):
            mine = ordinal[rows] == face
            nodes = boundary[rows[mine]]
            flat_nodes = nodes.ravel()
            weights = np.repeat(outer[mine], nodes.shape[1], axis=0)
            totals = np.repeat(area[mine], nodes.shape[1])
            unique, inverse = np.unique(flat_nodes, return_inverse=True)
            summed = np.zeros((len(unique), 3, 3))
            np.add.at(summed, inverse, weights)
            norm = np.zeros(len(unique))
            np.add.at(norm, inverse, totals)
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


def _axes_of(directions: "np.ndarray") -> "list[int] | None":
    """The global axes spanning the held directions exactly, or None when they are not axes."""
    import numpy as np

    reach = np.linalg.norm(directions @ np.eye(3), axis=0)  # each axis's length inside the span
    on = np.abs(reach - 1.0) <= AXIS_TOLERANCE
    off = reach <= AXIS_TOLERANCE
    if not np.all(on | off) or int(on.sum()) != len(directions):
        return None
    return [int(k) for k in np.flatnonzero(on)]


def supports_of(space: "FemSpace", fixtures: "tuple[Fixture, ...]", ordinal_of: dict[str, int],
                *, held: "list[np.ndarray] | tuple" = ()) -> Supports:
    """The study's supports on ``space``: fixed faces, rollers, and ``held`` (more DOF held, global: a symmetry
    plane's component, fit's ``symmetry`` rung). Only fixed faces: the DOF exactly as before."""
    import numpy as np
    import scipy.sparse as sparse

    basis = space.basis
    per_fixture = [basis.get_dofs(space.facets_of(fixture.faces, ordinal_of)).all() for fixture in fixtures]
    rollers = [fixture for fixture in fixtures if getattr(fixture, "type", "fixed") == "roller"]
    if not rollers:
        held_all = [*per_fixture, *held]
        fixed = np.unique(np.concatenate(held_all)) if held_all else np.zeros(0, dtype=np.int64)
        return Supports(fixed=fixed, per_fixture=per_fixture)

    clamped = [dofs for dofs, fixture in zip(per_fixture, fixtures) if getattr(fixture, "type", "fixed") != "roller"]
    pieces = [*clamped, *held]
    fixed = np.unique(np.concatenate(pieces)) if pieces else np.zeros(0, dtype=np.int64)
    vdofs = np.zeros((space.scalar_count, 3), dtype=np.int64)
    for c in range(3):
        vdofs[space.scalar.nodal_dofs[0], c] = basis.nodal_dofs[c]
        if space.order == 2:
            vdofs[space.scalar.edge_dofs[0], c] = basis.edge_dofs[c]
    clamped_nodes = np.zeros(space.scalar_count, dtype=bool)
    if len(fixed):
        is_fixed = np.zeros(basis.N, dtype=bool)
        is_fixed[fixed] = True
        clamped_nodes = is_fixed[vdofs].all(axis=1)  # a node every component of which is held already
    directions = _roller_directions(space, [{ordinal_of[ref] for ref in fixture.faces} for fixture in rollers])
    more: list[int] = []
    turned: dict[int, np.ndarray] = {}
    for node, held_dirs in directions.items():
        if clamped_nodes[node]:
            continue
        axes = _axes_of(held_dirs)
        if axes is not None:
            more.extend(int(vdofs[node, k]) for k in axes)
            continue
        # The node's own frame: its held directions first, then the rest of an orthonormal basis.
        q, _ = np.linalg.qr(np.vstack([held_dirs, np.eye(3)]).T, mode="complete")
        frame = q[:, :3]
        frame[:, :len(held_dirs)] = held_dirs.T  # exactly the held directions (QR may flip a sign)
        frame, _ = np.linalg.qr(frame)
        turned[node] = frame
        more.extend(int(vdofs[node, k]) for k in range(len(held_dirs)))
    fixed = np.unique(np.concatenate([fixed, np.asarray(more, dtype=np.int64)]))
    frame = None
    turned_nodes = None
    if turned:
        nodes = np.array(sorted(turned), dtype=np.int64)
        blocks = np.stack([turned[int(n)] for n in nodes])  # (n, 3 global, 3 local)
        rows = vdofs[nodes][:, :, None].repeat(3, axis=2)    # global component i
        cols = vdofs[nodes][:, None, :].repeat(3, axis=1)    # local slot j
        keep = np.ones(basis.N, dtype=bool)
        keep[vdofs[nodes].ravel()] = False
        identity = np.flatnonzero(keep)
        frame = sparse.coo_matrix(
            (np.concatenate([blocks.ravel(), np.ones(len(identity))]),
             (np.concatenate([rows.ravel(), identity]), np.concatenate([cols.ravel(), identity]))),
            shape=(basis.N, basis.N)).tocsr()
        turned_nodes = nodes
    return Supports(fixed=fixed, per_fixture=per_fixture, frame=frame, rollers=True, turned_nodes=turned_nodes)


def unheld_motions(space: "FemSpace", supports: Supports) -> int:
    """How many rigid motions (of 6) the supports leave the whole mesh free to make: 0 when it is held."""
    import numpy as np

    from cadgen._internal.fea.operators import rigid_body_modes

    locations = space.locations
    centre = locations.mean(axis=0)
    size = float(np.ptp(locations, axis=0).max()) or 1.0
    modes = rigid_body_modes((locations - centre) / size, space.component)
    held = supports.local_vector(modes)[supports.fixed]
    if not len(held):
        return 6
    values = np.linalg.svd(held, compute_uv=False)
    return 6 - int((values > 1e-8 * max(float(values.max()), 1e-300)).sum())


def held_bodies(space: "FemSpace", supports: Supports, body_of_dof: "np.ndarray") -> set[int]:
    """The bodies (``body_of_dof``: each vector DOF's body) the supports hold still: every one any held DOF touches,
    and, with rollers, only those whose six rigid motions are all held (a body on rollers on one face may still
    slide along it, and rests on what else it touches)."""
    import numpy as np

    from cadgen._internal.fea.operators import rigid_body_modes

    touched = set(np.unique(body_of_dof[supports.fixed]).tolist()) if len(supports.fixed) else set()
    if not supports.rollers:
        return touched
    held = set()
    is_fixed = np.zeros(len(body_of_dof), dtype=bool)
    is_fixed[supports.fixed] = True
    for body in touched:
        mine = body_of_dof == body
        locations = space.locations[mine]
        centre, size = locations.mean(axis=0), float(np.ptp(locations, axis=0).max()) or 1.0
        modes = np.zeros((len(body_of_dof), 6))
        modes[mine] = rigid_body_modes((locations - centre) / size, space.component[mine])
        rows = supports.local_vector(modes)[is_fixed & mine]
        values = np.linalg.svd(rows, compute_uv=False) if len(rows) else np.zeros(0)
        if int((values > 1e-8 * max(float(values.max()) if len(values) else 0.0, 1e-300)).sum()) == 6:
            held.add(body)
    return held


def not_held_sentence(loose: int) -> str:
    """The plain error for supports that leave the part free to move."""
    return (f"the fixtures leave the part free to slide or turn ({loose} of its 6 rigid motions): a roller face holds "
            "it only along its normal, so rollers alone need faces facing at least three ways (like a block's corner); "
            "add a roller on another face, or fix a face")


def check_held(space: "FemSpace", supports: Supports) -> None:
    """Refuse, in a sentence, supports with rollers that leave the part free to move (a part with no roller is
    the analysis's own business, as before)."""
    if supports.rollers and (loose := unheld_motions(space, supports)):
        raise ValueError(not_held_sentence(loose))


def driven(problem, supports: Supports, free: "np.ndarray"):
    """What the nonlinear driver follows: the problem itself, or :class:`Turned` when a roller's nodes are turned."""
    return Turned(problem, supports, free) if supports.turned else problem


def path_to_global(path, supports: Supports):
    """A driver path's displacements back in global axes (in place); the path itself."""
    if supports.turned:
        for record in path.records:
            record.u = supports.global_vector(record.u)
    return path


class Turned:
    """A nonlinear problem (:class:`~.nonlinear_driver.NonlinearProblem`) seen in the supports' frame: the driver
    solves for ``u_local`` on the frame's free DOF, the problem itself still sees global displacements.
    Every other attribute is the problem's own. Its path's displacements are local: :meth:`to_global` turns them."""

    def __init__(self, problem, supports: Supports, free: "np.ndarray"):
        self.problem = problem
        self.supports = supports
        self.free = free
        if hasattr(problem, "settle"):  # only a problem that settles has the driver settle it (contact's Uzawa)
            self.settle = self._settle

    def __getattr__(self, name):
        return getattr(self.problem, name)

    @property
    def external(self):
        return self.supports.local_vector(self.problem.external)  # a bolt's lock changes its problem's load

    def to_global(self, u):
        return self.supports.global_vector(u)

    def evaluate(self, u, *, tangent):
        internal, K = self.problem.evaluate(self.to_global(u), tangent=tangent)
        return self.supports.local_vector(internal), (self.supports.local(K) if tangent else None)

    def update(self, u, tangent):
        return self.problem.update(self.to_global(u), tangent)

    def commit(self, u, *rest):
        if rest:
            return self.problem.commit(self.to_global(u), *rest)
        return self.problem.commit(u)  # creep commits an update, not a displacement

    def _settle(self, u, factor):
        from cadgen._internal.fea.nonlinear_driver import Settled

        settled = self.problem.settle(self.to_global(u), factor)
        return Settled(self.supports.local_vector(settled.u), settled.settled)
