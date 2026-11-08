"""A cadjoint field as a build123d solid: ``solid(scene, cell=)``.

The field is sampled as an implicit document is (``_field.sample``: the grid of ``cell``-millimetre cells
over its bounds, cadjoint's dual contouring with sharp creases kept, slivers welded, and a mesh that is
clipped, open or in pieces refused by name), then simplified by cadjoint's error-bounded, feature-preserving
collapse (``simplify_mesh``) and built into a solid of planar faces (``cad.build123d.faceted_solid``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cad.cadjoint._field import MAX_CELLS, Field, _box_corners, _cell, _scene, sample

__all__ = ["MAX_CELLS", "solid"]


def solid(scene: Any, *, cell: float, bounds: Sequence[Sequence[float]] | None = None) -> Any:
    """The cadjoint field ``scene`` as one build123d ``Solid`` of planar triangles, the part a model returns.

    ``cell`` is the sampling cell in millimetres: the thinnest wall needs about four cells across, and a
    wall or bridge thinner than about two falls apart. ``bounds=((x0, y0, z0), (x1, y1, z1))`` replaces
    cadjoint's ``fit_bounds`` with a box the caller knows holds the whole part (one made with a loose
    fit, or to skip the scan); it never clips: a part that reaches the box's faces is refused. No axis
    takes more than 512 cells.

    The surface is cadjoint's dual contour of the field (creases and corners land on the field's own
    edges), simplified by cadjoint's feature-preserving collapse, whose every changed triangle stays
    within ``cell / 20`` of the field. The solid is faceted (``cad.build123d.faceted_solid``): no face is
    a cylinder or a plane a pick can select as one, and a hole's radius reads as its chords; it measures,
    exports and draws as any solid does. It costs tens of seconds for a part of 100 mm at a 1 mm cell
    (the field is compiled by JAX on its first evaluation, the mesh simplified, then built face by face),
    and more as the cell shrinks, roughly with the surface's area in cells. A model that needs no B-rep
    -- no assembly to compose it into -- declares ``@implicit`` and returns ``field(scene, cell=)`` instead:
    the sample itself is its document, with nothing simplified or built.

    Refused with a ``ValueError`` naming the fix: a field with no closed part in reach; a grid of more
    than 512 cells along an axis; a part that reaches the bounds (clipped); bounds that hold no surface;
    a mesh that is not watertight (a concave corner sharper than the cell resolves) or that is several
    bodies (a wall thinner than about two cells); a thinnest wall, measured on the field, under two cells
    (naming the cell that gives it four). A ``TypeError`` for a ``scene`` that is no cadjoint field.
    """
    import numpy as np
    from cadjoint.meshing import simplify_mesh
    from cadjoint.meshing.dual_contouring import Mesh

    from cad.build123d import faceted_solid

    field = _scene(scene, "cad.cadjoint.solid")
    declared = Field(field, _cell(cell), None if bounds is None else _box_corners(bounds))
    found = sample(declared, where="cad.cadjoint.solid")
    mesh = Mesh(vertices=np.asarray(found.positions, dtype=np.float32), faces=np.asarray(found.triangles, dtype=np.int64),
                quads=np.zeros((0, 4), dtype=np.int32), normals=np.asarray(found.normals, dtype=np.float32),
                cells=np.zeros((len(found.positions), 3), dtype=np.int64))
    simplified = simplify_mesh(mesh, lambda point: field(point), error=found.cell / 20)
    return faceted_solid(np.asarray(simplified.vertices, dtype=np.float64), np.asarray(simplified.faces, dtype=np.int64))
