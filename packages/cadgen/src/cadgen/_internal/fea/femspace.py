"""The finite element space of one meshed study: built once, shared by every solve on that mesh.

:class:`FemSpace` turns netgen's arrays (:class:`~cadgen._internal.fea.mesh.VolumeMesh`)
into scikit-fem's: the element mesh, the vector (displacement) and scalar
(temperature, projection) bases, and the bookkeeping that ties them to the
mesher's nodes and faces -- each DOF's location and component, the boundary
triangles in scalar DOF ids, and the skfem facets of the faces a study names.
An upstream analysis (the thermal solve under a thermal stress, the static
prestress under buckling) and its downstream one read the same space.

Quadratic (10-node) tetrahedra by default; ``order=1`` builds linear (4-node)
ones from a first-order mesh. Numeric imports live inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.mesh import VolumeMesh

__all__ = ["FacetLookup", "FemSpace", "NETGEN_TET10_TO_SKFEM", "element_mesh"]

# netgen's 10-node tetrahedron lists the four corners, then the mid-edge nodes of
# edges (0,1) (0,2) (0,3) (1,2) (1,3) (2,3); skfem's quadratic tet wants them on
# edges (0,1) (1,2) (0,2) (0,3) (1,3) (2,3). One fixed permutation maps the
# former to the latter -- the mesher does not vary its order.
NETGEN_TET10_TO_SKFEM = (0, 1, 2, 3, 4, 7, 5, 6, 8, 9)


def element_mesh(volume: "VolumeMesh", order: int = 2):
    """scikit-fem's tet mesh from netgen's arrays, and node -> scalar DOF.

    skfem renumbers a quadratic mesh on construction (corner vertices first,
    then edge nodes); the map back to the mesher's node ids falls out of its
    element DOF table. A linear mesh keeps the mesher's numbering.
    """
    import numpy as np

    if order == 1:
        from skfem import MeshTet

        connectivity = np.ascontiguousarray(volume.tets[:, :4].T)
        mesh = MeshTet(np.ascontiguousarray(volume.nodes.T), connectivity)
        node_to_dof = np.full(len(volume.nodes), -1, dtype=np.int64)
        node_to_dof[connectivity] = connectivity
    elif order == 2:
        from skfem import MeshTet2

        connectivity = np.ascontiguousarray(volume.tets[:, NETGEN_TET10_TO_SKFEM].T)
        mesh = MeshTet2(np.ascontiguousarray(volume.nodes.T), connectivity)
        node_to_dof = np.full(len(volume.nodes), -1, dtype=np.int64)
        node_to_dof[connectivity] = mesh.dofs.element_dofs
    else:
        raise ValueError(f"element order {order!r} is not 1 or 2")
    if (node_to_dof < 0).any():
        raise RuntimeError("the mesher produced nodes that no element uses")
    return mesh, node_to_dof


class FacetLookup:
    """skfem facet ids for boundary triangles given as vertex triples; the
    facet table is keyed once and reused for every fixture and load."""

    def __init__(self, mesh, vertices: int):
        import numpy as np

        self._vertices = vertices
        facets = np.sort(mesh.facets.astype(np.int64), axis=0)
        keys = (facets[0] * vertices + facets[1]) * vertices + facets[2]
        self._order = np.argsort(keys)
        self._keys = keys[self._order]

    def __call__(self, triangles: "np.ndarray") -> "np.ndarray":
        import numpy as np

        tri = np.sort(triangles.astype(np.int64), axis=1)
        wanted = (tri[:, 0] * self._vertices + tri[:, 1]) * self._vertices + tri[:, 2]
        where = np.clip(np.searchsorted(self._keys, wanted), 0, len(self._keys) - 1)
        if not np.array_equal(self._keys[where], wanted):
            raise RuntimeError("a boundary triangle of the mesher is not a facet of the element mesh")
        return self._order[where]


@dataclass
class FemSpace:
    """One mesh's element space: what every operator and every analysis on that mesh reads."""

    volume: "VolumeMesh | None"
    order: int
    #: skfem's element mesh (``MeshTet2`` or ``MeshTet``).
    mesh: Any
    #: Vector (displacement) basis, three components per scalar DOF.
    basis: Any
    #: Scalar basis on the same nodes (temperature, projections).
    scalar: Any
    #: Corner-vertex count; scalar DOF ``[:vertices]`` are the linear mesh's points.
    vertices: int
    #: Scalar DOF count: vertices, then (quadratic) edge midpoints.
    scalar_count: int
    #: (N, 3) location and (N,) component (0, 1, 2) of every vector DOF.
    locations: "np.ndarray"
    component: "np.ndarray"
    #: (B, 6) -- (B, 3) for linear elements -- the mesher's boundary triangles in scalar DOF ids.
    boundary_quadratic: "np.ndarray | None" = None
    #: (E,) the part each element belongs to, for an assembly; ``None`` for one part.
    domain: "np.ndarray | None" = None
    #: Facet lookup for the boundary triangles.
    _facets: Any = field(default=None, repr=False)

    @property
    def dofs(self) -> int:
        return int(self.basis.N)

    @classmethod
    def build(cls, volume: "VolumeMesh", order: int = 2) -> "FemSpace":
        """The space of a meshed study: its element mesh, bases, DOF maps and boundary."""
        mesh, node_to_dof = element_mesh(volume, order)
        space = cls.from_mesh(mesh, order=order, domain=volume.domain)
        boundary = node_to_dof[volume.boundary[:, :3 if order == 1 else 6]]
        if (boundary[:, :3] >= space.vertices).any():
            raise RuntimeError("a boundary triangle's corner is not a corner vertex of the element mesh")
        space.volume = volume
        space.boundary_quadratic = boundary
        return space

    @classmethod
    def from_mesh(cls, mesh, *, order: int = 2, domain: "np.ndarray | None" = None) -> "FemSpace":
        """The space of an skfem mesh alone (no mesher faces): what :meth:`build` wraps, and what tests build on."""
        import numpy as np
        from skfem import Basis, ElementTetP1, ElementTetP2, ElementVector

        element = ElementTetP2() if order == 2 else ElementTetP1()
        basis = Basis(mesh, ElementVector(element))
        scalar = basis.with_element(element)
        vertices = int(mesh.t.max()) + 1
        # DOF bookkeeping: skfem numbers scalar DOF vertices first, then (quadratic) edges.
        edges = mesh.edges.shape[1] if order == 2 else 0
        if not np.array_equal(scalar.nodal_dofs[0], np.arange(vertices)) or (
            order == 2 and not np.array_equal(scalar.edge_dofs[0], vertices + np.arange(edges))
        ):
            raise RuntimeError("unexpected degree-of-freedom numbering in the element basis")
        locations = np.zeros((basis.N, 3))
        component = np.zeros(basis.N, dtype=np.int64)
        for c in range(3):
            pairs = [(basis.nodal_dofs[c], scalar.nodal_dofs[0])]
            if order == 2:
                pairs.append((basis.edge_dofs[c], scalar.edge_dofs[0]))
            for dofs, where in pairs:
                locations[dofs] = mesh.doflocs[:, where].T
                component[dofs] = c
        return cls(
            volume=None, order=order, mesh=mesh, basis=basis, scalar=scalar, vertices=vertices,
            scalar_count=vertices + edges, locations=locations, component=component,
            domain=None if domain is None else np.asarray(domain),
        )

    def facets_of_ordinals(self, ordinals, what: str) -> "np.ndarray":
        """The skfem facets of the boundary triangles on face ``ordinals``; ``what`` names them in the error."""
        import numpy as np

        mask = np.isin(self.volume.boundary_ordinal, list(ordinals))
        if not mask.any():
            raise RuntimeError(f"no boundary triangles lie on {what}")
        return self.facets_of_rows(mask)

    def facets_of_rows(self, rows) -> "np.ndarray":
        """The skfem facets of boundary triangles ``rows`` (a mask or indices into ``boundary_quadratic``)."""
        if self._facets is None:
            self._facets = FacetLookup(self.mesh, self.vertices)
        return self._facets(self.boundary_quadratic[rows][:, :3])

    def facets_of(self, refs, ordinal_of: dict[str, int]) -> "np.ndarray":
        """The skfem facets of the faces ``refs`` (study refs, through ``ordinal_of``)."""
        return self.facets_of_ordinals([ordinal_of[ref] for ref in refs], ", ".join(refs))

    def nodal(self, u: "np.ndarray") -> "np.ndarray":
        """A vector DOF array as (scalar_count, 3) per node: vertices, then edge midpoints."""
        import numpy as np

        out = np.zeros((self.scalar_count, 3))
        for c in range(3):
            out[self.scalar.nodal_dofs[0], c] = u[self.basis.nodal_dofs[c]]
            if self.order == 2:
                out[self.scalar.edge_dofs[0], c] = u[self.basis.edge_dofs[c]]
        return out

    @property
    def dof_locations(self) -> "np.ndarray":
        """(scalar_count, 3) coordinates of every scalar DOF."""
        import numpy as np

        return np.ascontiguousarray(self.mesh.doflocs.T)

    @property
    def tets(self) -> "np.ndarray":
        import numpy as np

        return np.ascontiguousarray(self.mesh.t.T)

    @property
    def element_dofs(self) -> "np.ndarray":
        """(E, 10) -- (E, 4) linear -- the scalar DOF ids of each element's nodes."""
        import numpy as np

        return np.ascontiguousarray(self.scalar.element_dofs.T)
