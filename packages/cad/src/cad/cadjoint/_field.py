"""A cadjoint field declared with its sampling (``field(scene, cell=)``), and sampled (``sample``).

``Field`` is what a model returns to the ``implicit`` document type (``@implicit``): the scene -- a
cadjoint SDF -- the cell it is sampled at, in millimetres, and the bounds, where the caller gives them in
place of cadjoint's own fit. ``sample`` is the one sampling: the grid over the bounds, cadjoint's dual
contouring (``extract_mesh``, sharp creases kept), its coincident slivers welded (``remove_slivers``), and
the checks that make the mesh a part's -- clipped, empty, open or in pieces refused by name (law 17) --
answering the triangles with the field's own normals and the thinnest wall, measured on the field
(``_wall``) and refused under two cells, where the mesh still closes but its thickness is the grid's.
``solid`` samples the same way before it simplifies and builds B-rep; an ``implicit`` document holds the
sample as it is.

``Field.digest`` names the field: its lowered node table and parameter values (``cadjoint.zeroset.lower``),
the cell and the bounds, so a build whose body ran to the same field samples nothing again.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["MAX_CELLS", "MIN_WALL_CELLS", "Field", "Sampled", "field", "sample"]

# The most cells along any one axis: a grid of 512 on every side samples 134 million points.
MAX_CELLS = 512
# The thinnest wall a sample takes, in cells: under two its thickness is the grid's -- closed, its faces
# scalloped, or fallen apart. A wall needs about four (``cell = wall / 4``).
MIN_WALL_CELLS = 2.0
# A wall's ray (``_wall``): at most this many steps of sphere tracing, then its crossing halved this many times.
_WALL_STEPS = 48
_WALL_HALVINGS = 8
# A ray is a wall's where it leaves through a face turned back at it: the field's gradient at its exit within
# 30 degrees of the opposite of its start's normal. One that leaves through a neighbouring face (a ray from just
# beside a convex edge sharper than a right angle: a shell's rim cut at a slant, a tube's end, a gusset's tip)
# measures how near the edge it started, not a wall.
_OPPOSITE = math.cos(math.radians(30.0))
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
    refusal said as the way out: a solid around the part."""
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


@dataclass(frozen=True)
class Field:
    """A cadjoint field with its sampling: the scene (a cadjoint SDF), the cell in millimetres and the bounds
    (``((x0, y0, z0), (x1, y1, z1))``, or None for cadjoint's fit). What ``@implicit``'s function returns."""

    scene: Any
    cell: float
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None

    @property
    def digest(self) -> str:
        """A digest of the field as declared: its lowered node table and parameter values -- the scene's
        structure and every number in it -- with the cell and the bounds. Two builds whose bodies return
        fields of one digest sample one mesh."""
        return hashlib.blake2b(json.dumps([_lowered(self.scene), self.cell, self.bounds], sort_keys=True,
                                          separators=(",", ":"), default=_plain).encode("utf-8"),
                               digest_size=16).hexdigest()


def _plain(value: Any) -> Any:
    """A value of cadjoint's as JSON: an array by its numbers, anything else by its words."""
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    return repr(value)


def _lowered(scene: Any) -> Any:
    """The scene lowered to cadjoint's flat node table and parameter vector (``zeroset.lower``), as plain
    data; where cadjoint cannot lower it, its functionalized parameters and the tree's words."""
    try:
        from cadjoint.zeroset import lower

        lowered = lower(scene)
    except Exception:  # noqa: BLE001 - a scene the lowering does not take is named by its words
        lowered = None
    if lowered is not None:
        for name in ("to_dict", "as_dict", "_asdict"):
            method = getattr(lowered, name, None)
            if callable(method):
                try:
                    return method()
                except Exception:  # noqa: BLE001
                    pass
        return _plain(getattr(lowered, "__dict__", None) or lowered)
    # A scene cadjoint cannot lower (a RoundBox, say): its parameters by path, which name each node's kind and
    # place in the tree (``roundbox_3.radius``), and their values. Never a repr: an object's address is no
    # part of the field, and two builds of one scene must digest alike.
    from cadjoint.extraction import extract_parameters

    free, fixed, _ = extract_parameters(scene)
    return {"root": type(scene).__qualname__, "free": {str(k): _plain(v) for k, v in sorted(free.items())},
            "fixed": {str(k): _plain(v) for k, v in sorted(fixed.items())}}


def field(scene: Any, *, cell: float, bounds: Sequence[Sequence[float]] | None = None) -> Field:
    """The cadjoint field ``scene`` with its sampling: ``cell``, the sampling cell in millimetres (the thinnest
    wall needs about four cells across, and a wall or bridge thinner than about two falls apart), and
    ``bounds=((x0, y0, z0), (x1, y1, z1))``, a box of the caller's in place of cadjoint's ``fit_bounds`` -- one
    the caller knows holds the whole part; it never clips. What a function declared ``@implicit`` returns:
    the engine samples it (``sample``) and holds the mesh as the model's document, refusing a wall under two
    cells. Refused with a ``TypeError`` for a ``scene`` that is no cadjoint field, a ``ValueError`` for a cell
    that is no positive number or bounds that are no box."""
    return Field(_scene(scene, "cad.cadjoint.field"), _cell(cell), None if bounds is None else _box_corners(bounds))


def _box_corners(bounds: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    low, extent = _box(bounds)
    return ((low[0], low[1], low[2]), (low[0] + extent[0], low[1] + extent[1], low[2] + extent[2]))


@dataclass(frozen=True)
class Sampled:
    """A field sampled: its vertices in millimetres (``positions``, (V, 3)), the field's unit normals at them
    (``normals``, (V, 3)), its triangles (``triangles``, (T, 3), counterclockwise seen from outside), the
    cell it was sampled at, and its thinnest wall in millimetres (``wall_mm``, ``_wall``; None where no ray
    could measure one), ``cells`` of the cell across."""

    positions: Any
    normals: Any
    triangles: Any
    cell: float
    wall_mm: float | None = None

    @property
    def cells(self) -> float | None:
        """The thinnest wall in cells, or None with no wall measured."""
        return None if self.wall_mm is None else self.wall_mm / self.cell


def _wall(scene: Any, positions: Any, normals: Any, cell: float) -> float | None:
    """The sample's thinnest wall in millimetres, measured on the field; None where no vertex could be.

    From each vertex a ray runs into the material along the opposite of its normal (cadjoint's averaged
    normal: on a crease the bisector, so the ray enters the material rather than grazing the other face) until
    the field is positive again. It starts an eighth of a cell in -- a start already outside leaves the vertex
    unmeasured, never a wall of zero -- and sphere-traces: each step the field's magnitude there, a lower bound
    on the distance to the nearest surface, so no crossing is stepped over, and at least an eighth of a cell,
    at most ``_WALL_STEPS`` of them and never past the sample's diagonal. Its last inside and outside points
    are then halved ``_WALL_HALVINGS`` times. A ray counts where it leaves through a face turned back at it
    (``_OPPOSITE``, the field's gradient at its outside point by forward differences): on a flat or curved wall
    the faces are opposite, and a crease's bisector only lengthens its chord, so the least of them is the
    thinnest wall. Every ray at once: the field is called on all the vertices, float32, once a step -- one
    shape, so JAX compiles each of its operations once -- at most 60 calls in all."""
    import numpy as np

    points = np.asarray(positions, dtype=np.float64)
    inward = -np.asarray(normals, dtype=np.float64)
    if not len(points):
        return None

    def at(where: Any) -> Any:
        return np.asarray(scene(np.asarray(where, dtype=np.float32)), dtype=np.float64).reshape(-1)

    least = cell / 8.0
    reach = max(float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))), least)
    depth = np.full(len(points), least)
    value = at(points + inward * depth[:, None])
    low = depth.copy()  # the deepest depth known inside
    high = np.full(len(points), np.nan)  # the shallowest known outside
    beyond = np.zeros(len(points))  # the field there
    tracing = value < 0
    for _step in range(_WALL_STEPS):
        if not tracing.any():
            break
        ahead = np.where(tracing, np.minimum(depth + np.maximum(np.abs(value), least), reach), depth)
        found = at(points + inward * ahead[:, None])
        left = tracing & (found >= 0)
        low = np.where(tracing & ~left, ahead, low)
        high, beyond = np.where(left, ahead, high), np.where(left, found, beyond)
        depth, value = np.where(tracing, ahead, depth), np.where(tracing, found, value)
        tracing &= ~left & (ahead < reach)
    crossed = ~np.isnan(high)
    if not crossed.any():
        return None
    high = np.where(crossed, high, low)
    for _halving in range(_WALL_HALVINGS):
        middle = (low + high) / 2.0
        found = at(points + inward * middle[:, None])
        within = found < 0
        low, high = np.where(within, middle, low), np.where(within, high, middle)
        beyond = np.where(within, beyond, found)
    exits = points + inward * high[:, None]
    gradient = np.stack([at(exits + cell / 16.0 * axis) - beyond for axis in np.eye(3)], axis=1)
    length = np.linalg.norm(gradient, axis=1)
    facing = np.einsum("ij,ij->i", gradient, inward) >= _OPPOSITE * np.where(length > 0, length, np.inf)
    walls = ((low + high) / 2.0)[crossed & facing]
    return float(walls.min()) if len(walls) else None


_COMPILED: list[bool] = []


def _compilation_cache() -> None:
    """JAX's persistent compilation cache, under the engine's cache folder (``places.cache_dir()/jax``): a
    fresh worker reuses the programs cadjoint's meshing compiled before, instead of compiling them again
    (cadjoint's ``cache.enable_compilation_cache``, where cadjoint has it). Once per process; nothing when the
    folder cannot be made or cadjoint has no such cache."""
    if _COMPILED:
        return
    _COMPILED.append(True)
    try:
        from cadjoint.cache import enable_compilation_cache

        from cad.engine.places import cache_dir

        folder = cache_dir() / "jax"
        folder.mkdir(parents=True, exist_ok=True)
        enable_compilation_cache(folder)
    except Exception:  # noqa: BLE001 - a cache is a saving, never a reason to fail a build
        pass


def sample(declared: Field, *, where: str = "cad.cadjoint.solid") -> Sampled:
    """The field sampled on a grid of its cell over its bounds (fitted, or the caller's), meshed by cadjoint's
    dual contouring and welded (``remove_slivers``), its thinnest wall measured (``_wall``); refused by name
    where the mesh is no part's: more than ``MAX_CELLS`` cells along an axis, bounds that cut the part
    (clipped) or hold no surface, a mesh that is not watertight, one of several bodies, or a wall thinner
    than ``MIN_WALL_CELLS`` cells."""
    import warnings

    import numpy as np
    from cadjoint.meshing import GridSpec, extract_mesh, remove_slivers
    from cadjoint.meshing.bounds import boundary_inside

    _compilation_cache()
    scene, size = declared.scene, declared.cell
    if declared.bounds is None:
        origin, extent = _fitted(scene, where)
    else:
        low, high = declared.bounds
        origin, extent = tuple(low), tuple(b - a for a, b in zip(low, high))
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
        mesh = extract_mesh(scene, grid)
    high = tuple(a + b for a, b in zip(origin, extent))
    box = f"(({', '.join(f'{v:.6g}' for v in origin)}), ({', '.join(f'{v:.6g}' for v in high)}))"
    # Bounds fitted by cadjoint hold the part with a margin of more than half a cell of their scan (its
    # near-surface rule): only the caller's can cut it. The check evaluates the field on the grid's six
    # faces, seconds for a large scene.
    clipped = declared.bounds is not None and boundary_inside(scene, grid)
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
    positions = np.asarray(mesh.vertices, dtype=np.float64)
    normals = np.asarray(mesh.normals, dtype=np.float64) if mesh.normals is not None else None
    # The vertices the triangles use, in order: a welded mesh leaves rows no triangle names.
    used, faces = np.unique(faces, return_inverse=True)
    positions = positions[used]
    if normals is not None:
        normals = normals[used]
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.where(length > 1e-12, normals / np.where(length > 1e-12, length, 1.0), (0.0, 0.0, 1.0))
    wall = None if normals is None else _wall(scene, positions, normals, size)
    if wall is not None and wall / size < MIN_WALL_CELLS:
        # Its cells to the tenth below, so a wall refused never reads as two.
        raise ValueError(f"the thinnest wall is {math.floor(wall / size * 10) / 10:g} cells ({wall:.3g} mm at a {size:g} mm "
                         f"cell), and a wall needs about four: use a cell of {wall / 4:.3g} mm or less, or thicken it")
    return Sampled(positions, normals, faces.reshape(-1, 3), size, wall)
