"""Solving half (or a quarter) of a symmetric part: the ladder's ``symmetry`` rung.

A part that is its own mirror image about an axis plane through its centre of
mass, under fixtures, loads and checks that are mirror images too, deforms
symmetrically: the half on one side of the plane, held on the plane so it
cannot cross it (each node there keeps its normal displacement at zero), is
the whole answer, exactly. :func:`planes_of` finds such planes, :func:`cut`
makes the half or quarter to mesh (its faces traced to the part's own
ordinals, the cut faces given :data:`PLANE_ORDINAL` + the plane's index), and
:func:`unfold_volume` / :func:`unfold_fields` mirror the solved half back into
the whole part for the GLB, the checks and the findings.

The mirror check compares every face's area, kind and centre with a face at
its mirror image (a part is symmetric when every face has its image). OCP
imports live inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.defeature import Prepared
    from cadgen._internal.fea.fit import Geometry

__all__ = ["PLANE_ORDINAL", "Plane", "cut", "planes_of", "unfold_fields", "unfold_volume"]

#: The ordinal of a cut face on symmetry plane i is PLANE_ORDINAL + i: no part has that many faces.
PLANE_ORDINAL = 1_000_000
_AXES = "xyz"


@dataclass
class Plane:
    """The plane ``axis = offset``; ``mirror`` maps each face ordinal of the part to its mirror image's."""

    axis: str
    offset: float
    index: int = 0
    mirror: dict[int, int] = field(default_factory=dict)

    @property
    def component(self) -> int:
        return _AXES.index(self.axis)

    @property
    def ordinal(self) -> int:
        return PLANE_ORDINAL + self.index

    def as_dict(self) -> dict:
        return {"axis": self.axis, "offset_mm": round(self.offset, 6)}

    def reflect(self, points: "np.ndarray") -> "np.ndarray":
        out = points.copy()
        out[:, self.component] = 2.0 * self.offset - out[:, self.component]
        return out

    def reflect_vectors(self, vectors: "np.ndarray") -> "np.ndarray":
        out = vectors.copy()
        out[:, self.component] = -out[:, self.component]
        return out


def _centre_of_mass(shape) -> tuple[float, float, float]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    c = props.CentreOfMass()
    return (c.X(), c.Y(), c.Z())


def _mirror_map(geometry: "Geometry", component: int, offset: float) -> dict[int, int] | None:
    """Each face's mirror image by area, kind and centre; ``None`` when some face has none."""
    tolerance = 1e-5 * max(geometry.bbox_diagonal_mm, 1.0)
    mirror: dict[int, int] = {}
    for face in geometry.faces:
        image = list(face.center)
        image[component] = 2.0 * offset - image[component]
        match = [
            other.ordinal for other in geometry.faces
            if other.kind == face.kind and abs(other.area_mm2 - face.area_mm2) <= 1e-5 * max(face.area_mm2, 1.0)
            and sum((a - b) ** 2 for a, b in zip(other.center, image)) ** 0.5 <= tolerance
        ]
        if len(match) != 1:
            return None
        mirror[face.ordinal] = match[0]
    return mirror


def planes_of(geometry: "Geometry", prepared: "Prepared | None" = None) -> list[Plane]:
    """The axis planes through the centre of mass the part (and the shape to mesh, if prepared) mirrors onto itself."""
    from cadgen._internal.fea.fit import geometry_of

    centre = _centre_of_mass(geometry.shape)
    simplified = None
    if prepared is not None:
        if prepared.planes:
            return []
        simplified = geometry_of(prepared.shape, keep_shape=False)
    planes = []
    for component, axis in enumerate(_AXES):
        mirror = _mirror_map(geometry, component, centre[component])
        if mirror is None:
            continue
        if simplified is not None and _mirror_map(simplified, component, centre[component]) is None:
            continue
        offset = round(centre[component], 6) + 0.0  # 1e-17 is the plane through 0
        planes.append(Plane(axis, offset, len(planes), mirror))
    return planes


def cut(geometry: "Geometry", prepared: "Prepared | None", planes: list[Plane]) -> "Prepared | None":
    """The part (or its defeatured shape) on the positive side of each plane, faces traced; ``None`` on failure."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    from cadgen._internal.fea.defeature import Prepared, face_map, trace

    shape = geometry.shape if prepared is None else prepared.shape
    origin = list(range(1, face_map(shape).Extent() + 1)) if prepared is None else list(prepared.origin)
    margin = max(geometry.bbox_diagonal_mm, 1.0)
    for index, plane in enumerate(planes):
        plane.index = index
        low = [-1e3 * margin] * 3
        high = [1e3 * margin] * 3
        low[plane.component] = plane.offset
        try:
            box = BRepPrimAPI_MakeBox(gp_Pnt(*low), gp_Pnt(*high)).Shape()
            common = BRepAlgoAPI_Common(shape, box)
            if not common.IsDone() or getattr(common, "HasErrors", lambda: False)():
                return None
            half = common.Shape()
        except Exception:  # noqa: BLE001 - a kernel failure means the rung does not apply
            return None
        traced = trace(common, shape, half, origin)
        faces = face_map(half)
        for k in range(1, faces.Extent() + 1):
            if traced[k - 1] == 0 and _on_plane(faces.FindKey(k), plane, margin):
                traced[k - 1] = plane.ordinal
        shape, origin = half, traced
    return Prepared(shape, origin, list(planes))


def _on_plane(face, plane: Plane, scale: float) -> bool:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(face, box)
    values = box.Get()
    low, high = values[plane.component], values[3 + plane.component]
    return abs(low - plane.offset) <= 1e-6 * scale and abs(high - plane.offset) <= 1e-6 * scale


# -- mirroring the solved part back into the whole one ----------------------------------------------


def _flip_rows(rows: "np.ndarray") -> "np.ndarray":
    """Triangles with their winding reversed: corners 1 and 2 swap, and with them the mid-edge nodes of edges (0,2) and (0,1)."""
    import numpy as np

    if rows.shape[1] == 6:
        return np.ascontiguousarray(rows[:, [0, 2, 1, 3, 5, 4]])
    return np.ascontiguousarray(rows[:, [0, 2, 1]])


def unfold_volume(volume, plane: Plane):
    """The mesh and its mirror image about ``plane`` as one mesh: the cut face's triangles dropped, the
    mirrored triangles on each face's mirror image (other planes' cut faces stay theirs)."""
    import dataclasses

    import numpy as np

    keep = volume.boundary_ordinal != plane.ordinal
    boundary = volume.boundary[keep]
    ordinal = volume.boundary_ordinal[keep]
    count = len(volume.nodes)
    mirrored = np.array([plane.mirror.get(int(o), int(o)) for o in ordinal], dtype=np.int64)
    return dataclasses.replace(
        volume,
        nodes=np.concatenate([volume.nodes, plane.reflect(volume.nodes)]),
        tets=np.concatenate([volume.tets, volume.tets + count]),
        boundary=np.concatenate([boundary, _flip_rows(boundary + count)]),
        boundary_ordinal=np.concatenate([ordinal, mirrored]),
    ), keep


def dof_maps(vertices: int, count: int):
    """Where a scalar DOF of the half goes in the whole, for each copy: vertices of both copies first, then edges."""
    import numpy as np

    index = np.arange(count)
    first = np.where(index < vertices, index, index + vertices)
    second = np.where(index < vertices, index + vertices, index + count)
    return first, second


def unfold_fields(plane: Plane, vertices: int, locations: "np.ndarray", keep: "np.ndarray", *,
                  scalars: dict[str, "np.ndarray"], vectors: dict[str, "np.ndarray"], boundary: "np.ndarray",
                  tets: "np.ndarray", element_dofs: "np.ndarray"):
    """The half's DOF-indexed arrays mirrored into the whole: (locations, scalars, vectors, boundary, tets, element_dofs, vertices)."""
    import numpy as np

    count = len(locations)
    first, second = dof_maps(vertices, count)

    def spread(values, mirrored):
        out = np.zeros((2 * count, *values.shape[1:]), dtype=values.dtype)
        out[first] = values
        out[second] = mirrored
        return out

    whole_locations = spread(locations, plane.reflect(locations))
    whole_scalars = {name: spread(values, values) for name, values in scalars.items()}
    whole_vectors = {name: spread(values, plane.reflect_vectors(values)) for name, values in vectors.items()}
    rows = boundary[keep]
    whole_boundary = np.concatenate([first[rows], _flip_rows(second[rows])])
    whole_tets = np.concatenate([first[tets], second[tets]])
    whole_elements = np.concatenate([first[element_dofs], second[element_dofs]])
    return whole_locations, whole_scalars, whole_vectors, whole_boundary, whole_tets, whole_elements, 2 * vertices


def unfold_force(plane: Plane, force) -> tuple[float, float, float]:
    """A force on the half plus its mirror image: the whole part's."""
    out = [float(c) for c in force]
    out[plane.component] = 0.0
    return tuple(2.0 * c if k != plane.component else 0.0 for k, c in enumerate(out))
