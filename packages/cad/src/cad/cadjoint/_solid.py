"""A cadjoint field as a build123d solid: ``solid(scene, cell=)``.

The field is sampled on a grid of ``cell``-millimetre cells over its bounds (cadjoint's ``fit_bounds``,
or the caller's), meshed by cadjoint's dual contouring (``extract_mesh``, sharp creases kept), its
coincident slivers welded (``remove_slivers``), checked to be one closed body, simplified by cadjoint's
error-bounded, feature-preserving collapse (``simplify_mesh``) and built into a solid of planar faces
(``cad.build123d.faceted_solid``). Every refusal says, in one line, what to change (law 17): a mesh
that is clipped, open or in pieces is no part's, and a solid of it would be a plausible wrong one.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence
from typing import Any

__all__ = ["solid"]

# The most cells along any one axis: a grid of 512 on every side samples 134 million points.
MAX_CELLS = 512
# The half-width of the largest cube cadjoint's fit_bounds scans (``SCAN_HALF_WIDTHS[-1]``).
_SCAN_HALF_WIDTH = 4096


def _scene(scene: Any, where: str) -> Any:
    """``scene`` itself when it is a cadjoint field; else a ``TypeError`` naming what ``where`` takes."""
    from cadjoint.sdf.base import SDF

    if not isinstance(scene, SDF):
        raise TypeError(f"{where} takes a cadjoint field (a cadjoint.sdf.SDF: Solid.box(...), Union(...), "
                        f"extrude(...)), not {type(scene).__module__}.{type(scene).__qualname__}")
    return scene


def _fitted(scene: Any, where: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The lower corner and the extent of a box around the field's part, cadjoint's ``fit_bounds``; its
    refusal said as the way out, ``bounds=``."""
    from cadjoint.meshing.bounds import fit_bounds

    try:
        origin, extent = fit_bounds(scene)
    except ValueError:
        raise ValueError(f"{where}: no closed part found inside a cube of half-width {_SCAN_HALF_WIDTH} mm: the field is "
                         "empty or unbounded (a Plane, a missing Intersection): intersect it with a solid around the part") from None
    return tuple(float(value) for value in origin), tuple(float(value) for value in extent)


def _cell(cell: Any) -> float:
    if isinstance(cell, bool) or not isinstance(cell, numbers.Real) or not math.isfinite(cell) or cell <= 0:
        raise ValueError(f"cell is the sampling cell in millimetres, a finite number above zero, not {cell!r}")
    return float(cell)


def _box(bounds: Any) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """``bounds=((x0, y0, z0), (x1, y1, z1))`` as a lower corner and an extent."""
    try:
        low, high = (tuple(float(value) for value in corner) for corner in bounds)
    except (TypeError, ValueError):
        raise ValueError(f"bounds is ((x0, y0, z0), (x1, y1, z1)) in millimetres, not {bounds!r}") from None
    if len(low) != 3 or len(high) != 3 or not all(map(math.isfinite, (*low, *high))):
        raise ValueError(f"bounds is ((x0, y0, z0), (x1, y1, z1)), six finite numbers, not {bounds!r}")
    if not all(a < b for a, b in zip(low, high)):
        raise ValueError(f"bounds needs x0 < x1, y0 < y1 and z0 < z1, not {bounds!r}")
    return low, tuple(b - a for a, b in zip(low, high))


def _edges_off(faces: Any) -> int:
    """How many of the mesh's edges are not shared by exactly two triangles."""
    import numpy as np

    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, uses = np.unique(edges, axis=0, return_counts=True)
    return int((uses != 2).sum())


def _bodies(faces: Any) -> int:
    """How many connected bodies the triangles make, joined through shared vertices: a union-find of
    numpy's alone, each round hooking every root onto the lowest root an edge reaches, then jumping
    every vertex to its root."""
    import numpy as np

    count = int(faces.max()) + 1
    start = np.concatenate([faces[:, 0], faces[:, 1]])
    end = np.concatenate([faces[:, 1], faces[:, 2]])
    parent = np.arange(count)
    while True:
        a, b = parent[start], parent[end]
        apart = a != b
        if not apart.any():
            break
        low, high = np.minimum(a[apart], b[apart]), np.maximum(a[apart], b[apart])
        np.minimum.at(parent, high, low)
        while True:
            jumped = parent[parent]
            if (jumped == parent).all():
                break
            parent = jumped
    return int(np.unique(parent[faces.ravel()]).size)


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
    and more as the cell shrinks, roughly with the surface's area in cells.

    Refused with a ``ValueError`` naming the fix: a field with no closed part in reach; a grid of more
    than 512 cells along an axis; a part that reaches the bounds (clipped); bounds that hold no surface;
    a mesh that is not watertight (a concave corner sharper than the cell resolves) or that is several
    bodies (a wall thinner than about two cells). A ``TypeError`` for a ``scene`` that is no cadjoint field.
    """
    import warnings

    import numpy as np
    from cadjoint.meshing import GridSpec, extract_mesh, remove_slivers, simplify_mesh
    from cadjoint.meshing.bounds import boundary_inside

    from cad.build123d import faceted_solid

    field = _scene(scene, "cad.cadjoint.solid")
    size = _cell(cell)
    origin, extent = _fitted(field, "cad.cadjoint.solid") if bounds is None else _box(bounds)
    cells = tuple(max(1, math.ceil(value / size)) for value in extent)
    for axis, count, length in zip("xyz", cells, extent):
        if count > MAX_CELLS:
            raise ValueError(f"the part is {length:.6g} mm along {axis}, {count} cells of {size:g} mm, and an axis takes at "
                             f"most {MAX_CELLS}: use a cell of {length / MAX_CELLS:.3g} mm or more, or intersect the field with a "
                             "box around the region that matters and make that region its own model")
    grid = GridSpec.from_bounds(origin, extent, cells)
    with warnings.catch_warnings():
        # Clipping is asked of the field below (boundary_inside), which also sees a box wholly inside it.
        warnings.filterwarnings("ignore", message=".*extraction boundary")
        mesh = extract_mesh(field, grid)
    high = tuple(a + b for a, b in zip(origin, extent))
    box = f"(({', '.join(f'{v:.6g}' for v in origin)}), ({', '.join(f'{v:.6g}' for v in high)}))"
    # Bounds fitted by cadjoint hold the part with a margin of more than half a cell of their scan (its
    # near-surface rule): only the caller's can cut it. The check evaluates the field on the grid's six
    # faces, seconds for a large scene.
    clipped = bounds is not None and boundary_inside(field, grid)
    if np.asarray(mesh.faces).shape[0] == 0:
        raise ValueError(f"the bounds {box} hold no surface: the box lies wholly {'inside' if clipped else 'outside'} the "
                         "part: bounds= is a box that holds the whole part: widen it, or drop it to fit the part")
    if clipped:
        raise ValueError(f"part of the field lies on or beyond the bounds {box}, so its mesh is cut open there: bounds= "
                         "is a box that holds the whole part: widen it, or drop it to fit the part")
    mesh, _slivers = remove_slivers(mesh)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    off = _edges_off(faces)
    if off:
        raise ValueError(f"the mesh at a {size:g} mm cell is not watertight: {off} edges are not shared by exactly two "
                         "triangles, usually a concave corner sharper than the cell resolves: round it, or use a finer cell")
    bodies = _bodies(faces)
    if bodies != 1:
        raise ValueError(f"the mesh at a {size:g} mm cell is {bodies} separate bodies: a wall or bridge is thinner than "
                         f"about two cells ({2 * size:g} mm): use a finer cell, or model each piece as its own model")
    simplified = simplify_mesh(mesh, lambda point: field(point), error=size / 20)
    return faceted_solid(np.asarray(simplified.vertices, dtype=np.float64), np.asarray(simplified.faces, dtype=np.int64))
