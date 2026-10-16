#!/usr/bin/env python3
"""Mesh one SDF object of a cadjoint scene file and write STL, OBJ or STEP.

Requires: Python 3.11+, cadjoint, jax (install requirements.txt)

Usage:
    python cadjoint_export.py SCENE.py OUT.stl [--object scene] [--resolution 160]
        [--bounds X0 Y0 Z0 X1 Y1 Z1] [--ascii]

The output format follows OUT's suffix: `.stl` (binary unless `--ascii`),
`.obj`, or `.step`/`.stp`. STEP is faceted: one planar face per triangle,
exact in position but without analytic surfaces, so downstream tools can
view and measure it but not select a cylinder as a cylinder.

SCENE.py is plain Python run top to bottom. It must bind the object to
export -- an SDF from `cadjoint` -- to a module-level name, `scene` by
default. Code under `if __name__ == "__main__":` does not run.

The meshing grid is fitted to the object. A coarse scan at growing scales
(cubes of half-width 1, 4, 16, ... 4096 model units) finds the smallest one
that contains the whole part, and the samples inside or next to the
surface, padded by one and a half scan cells, become the grid. `--bounds`
replaces the scan, for an object that is unbounded on purpose or to mesh
only part of one.

`--resolution` counts cells along the longest axis; the other axes take
proportionally fewer, so cells stay cubic. The smallest feature the mesh
resolves is about two cells.

Prints one JSON object. `size` is the mesh's extent per axis, `bodies` its
count of separate pieces and `watertight` whether every edge is shared by
exactly two triangles; `warnings` names the facts that usually mean a
mistake: a part under one unit across (a scene in metres), more than one
body (a wall thinner than the cells, or parts that do not touch), and a mesh
that is not watertight (a sharp concave corner the cells cannot resolve).
`clipped: true` means part of the solid lies on or
beyond the grid boundary and the mesh is cut open there: widen `--bounds`.
Exits 1 with `{"ok": false, "error": ...}` when the scene fails to run, the
object is missing, the scan finds no closed part, or the grid holds no
surface at all.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
import time
import warnings
from pathlib import Path

FORMATS = {".stl": "stl", ".obj": "obj", ".step": "step", ".stp": "step"}
SCAN_HALF_WIDTHS = (1.0, 4.0, 16.0, 64.0, 256.0, 1024.0, 4096.0)
SCAN_CELLS = 48


def load_object(scene: Path, name: str):
    """Run SCENE and return the SDF it binds to NAME."""
    from cadjoint.sdf.base import SDF

    sys.path.insert(0, str(scene.parent))
    namespace = runpy.run_path(str(scene), run_name="__cadjoint_scene__")
    value = namespace.get(name)
    if isinstance(value, SDF):
        return value
    exportable = sorted(
        key for key, item in namespace.items() if not key.startswith("_") and isinstance(item, SDF)
    )
    found = "nothing" if value is None else f"a {type(value).__name__}"
    raise ValueError(
        f"{scene.name} binds {found} to {name!r}; SDF objects it binds: "
        f"{', '.join(exportable) or 'none'}."
    )


def scan_bounds(sdf) -> tuple[list[float], list[float]]:
    """The padded box around the part, from the smallest scan cube that holds it.

    A sample counts when it is inside or within half a cell diagonal of the
    surface. The field never overestimates the distance to the surface, so
    every surface point has a counted sample within that half diagonal: a
    plate thinner than the scan spacing is found even when no sample lands
    inside it.
    """
    import numpy as np

    axis = (np.arange(SCAN_CELLS + 1) / SCAN_CELLS) * 2.0 - 1.0
    unit = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    for half in SCAN_HALF_WIDTHS:
        spacing = 2.0 * half / SCAN_CELLS
        points = unit * half
        near = np.asarray(sdf(points.astype(np.float32))) < 0.5 * np.sqrt(3.0) * spacing
        if not near.any():
            continue
        low = points[near].min(axis=0)
        high = points[near].max(axis=0)
        if (low <= -half + 0.5 * spacing).any() or (high >= half - 0.5 * spacing).any():
            continue  # the part reaches the scan boundary: look wider
        pad = 1.5 * spacing
        return refine_bounds(sdf, low - pad, high + pad)
    raise ValueError(
        "no closed part found inside a cube of half-width "
        f"{SCAN_HALF_WIDTHS[-1]:g}: the object is empty or unbounded (an infinite "
        "plane, a missing Intersection). Pass --bounds."
    )


def refine_bounds(sdf, low, high) -> tuple[list[float], list[float]]:
    """Tighten a coarse box with one finer scan inside it.

    The coarse cube can be four times the part's size with a pad of a
    sixteenth of the cube, which would spend a quarter of the export's cells
    on empty space. The same near-surface rule on 48 cells across the box
    itself bounds the part to within a few percent of its size.
    """
    import numpy as np

    axes = [np.linspace(a, b, SCAN_CELLS + 1) for a, b in zip(low, high)]
    points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    spacing = (np.asarray(high) - np.asarray(low)) / SCAN_CELLS
    near = np.asarray(sdf(points.astype(np.float32))) < 0.5 * np.linalg.norm(spacing)
    if not near.any():
        return list(low), list(high)
    pad = 1.5 * spacing
    return (points[near].min(axis=0) - pad).tolist(), (points[near].max(axis=0) + pad).tolist()


def boundary_inside(sdf, grid) -> bool:
    """Whether any lattice vertex on the grid's six faces lies inside the part."""
    import numpy as np

    axes = [
        origin + spacing * np.arange(count + 1)
        for origin, spacing, count in zip(grid.origin, grid.spacing, grid.cells)
    ]
    for fixed in range(3):
        for end in (axes[fixed][0], axes[fixed][-1]):
            free = [axes[i] for i in range(3) if i != fixed]
            a, b = np.meshgrid(*free, indexing="ij")
            columns = [a.ravel(), b.ravel()]
            columns.insert(fixed, np.full(a.size, end))
            face = np.stack(columns, axis=-1).astype(np.float32)
            if (np.asarray(sdf(face)) < 0.0).any():
                return True
    return False


def count_bodies(faces) -> int:
    """Connected pieces of the mesh, joined through shared vertices."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    faces = np.asarray(faces)
    count = int(faces.max()) + 1
    rows = np.concatenate([faces[:, 0], faces[:, 1]])
    cols = np.concatenate([faces[:, 1], faces[:, 2]])
    graph = coo_matrix((np.ones(rows.size, dtype=np.int8), (rows, cols)), shape=(count, count))
    used = np.zeros(count, dtype=bool)
    used[faces.ravel()] = True
    _, labels = connected_components(graph, directed=False)
    return int(np.unique(labels[used]).size)


def merged_faces(vertices, faces):
    """Faces re-indexed onto vertices merged by position, zero-area slivers dropped.

    An STL has no vertex indices, so every reader merges coincident points.
    At a sharp concave corner the mesher can emit triangles whose corners are
    distinct rows but the same point (1e-15 apart); after the merge they have
    no area and use their edges a third and fourth time, which is what makes
    a reader call the file non-manifold. Returns (merged faces, kept mask).
    """
    import numpy as np

    vertices = np.asarray(vertices, dtype=np.float64)
    tolerance = 1e-9 * max(float(np.ptp(vertices, axis=0).max()), 1e-12)
    _, merged = np.unique(np.round(vertices / tolerance), axis=0, return_inverse=True)
    faces = merged.reshape(-1)[np.asarray(faces)]
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return faces[keep], keep


def bad_edges(faces) -> int:
    """Edges not shared by exactly two triangles: holes or non-manifold seams."""
    import numpy as np

    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts != 2).sum())


def review_warnings(size: list[float], bodies: int, spacing: float, open_edges: int) -> list[str]:
    """Facts about the mesh that usually mean the scene or the resolution is wrong."""
    notes = []
    if open_edges:
        notes.append(
            f"{open_edges} edges are not shared by exactly two triangles, so the mesh is not "
            "watertight: usually a sharp concave corner sharper than the cells resolve (round "
            "it, or raise --resolution)"
        )
    if max(size) < 1.0:
        notes.append(
            f"the part is {max(size):.3g} units across: the export reads model units as "
            "millimetres, so a scene written in metres must be scaled by 1000"
        )
    if bodies > 1:
        notes.append(
            f"{bodies} separate bodies: if the part should be one piece, a wall or bridge is "
            f"thinner than about two cells ({2 * spacing:.3g} units); raise --resolution"
        )
    return notes


def export(scene: Path, out: Path, name: str, resolution: int, bounds, binary: bool) -> dict:
    import jax.numpy as jnp
    import numpy as np

    from cadjoint.meshing import GridSpec, extract_mesh, save_obj, save_step, save_stl

    fmt = FORMATS.get(out.suffix.lower())
    if fmt is None:
        raise ValueError(f"unsupported output suffix {out.suffix!r}; use .stl, .obj or .step")
    started = time.perf_counter()
    obj = load_object(scene, name)
    sdf = lambda points: jnp.asarray(obj(jnp.asarray(points)))  # noqa: E731

    if bounds is None:
        low, high = scan_bounds(sdf)
    else:
        low, high = list(bounds[:3]), list(bounds[3:])
    extent = np.asarray(high) - np.asarray(low)
    if (extent <= 0).any():
        raise ValueError("--bounds needs X0 < X1, Y0 < Y1 and Z0 < Z1")
    cells = tuple(max(1, round(resolution * float(e) / float(extent.max()))) for e in extent)
    grid = GridSpec.from_bounds(tuple(low), tuple(extent.tolist()), cells)

    with warnings.catch_warnings():
        # Clipping is measured below, on the field itself: the kernel's own
        # warning only fires when the surface crosses the boundary, not when
        # the whole box sits inside the part.
        warnings.filterwarnings("ignore", message=".*extraction boundary")
        mesh = extract_mesh(sdf, grid)
    clipped = boundary_inside(sdf, grid)
    if mesh.faces.shape[0] == 0:
        raise ValueError(
            "the grid holds no surface: the box lies wholly "
            + ("inside" if clipped else "outside")
            + " the part. Widen or move --bounds."
        )

    welded, keep = merged_faces(mesh.vertices, mesh.faces)
    slivers = int((~keep).sum())
    if slivers:
        mesh = mesh._replace(faces=np.asarray(mesh.faces)[keep])

    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "stl":
        save_stl(mesh, out, binary=binary)
    elif fmt == "obj":
        save_obj(mesh, out)
    else:
        save_step(mesh, out)
    vertices = np.asarray(mesh.vertices)
    size = (vertices.max(axis=0) - vertices.min(axis=0)).tolist()
    spacing = float(extent.max()) / resolution
    bodies = count_bodies(mesh.faces)
    open_edges = bad_edges(welded)
    return {
        "ok": True,
        "path": str(out.resolve()),
        "format": fmt,
        "object": name,
        "bounds": [low, high],
        "cells": list(cells),
        "spacing": spacing,
        "size": size,
        "bodies": bodies,
        "watertight": open_edges == 0,
        "slivers_removed": slivers,
        "vertices": int(mesh.vertices.shape[0]),
        "triangles": int(mesh.faces.shape[0]),
        "clipped": clipped,
        "warnings": review_warnings(size, bodies, spacing, open_edges),
        "seconds": round(time.perf_counter() - started, 2),
    }


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print(json.dumps({
            "ok": False,
            "error": f"Python {sys.version.split()[0]} is too old; cadjoint needs 3.11 or newer "
            "(create the environment with `uv venv --managed-python --python 3.12`).",
        }))
        return 1
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scene", type=Path, help="cadjoint scene file (.py)")
    parser.add_argument("out", type=Path, help="output file: .stl, .obj, .step or .stp")
    parser.add_argument("--object", default="scene", help="name the scene binds the SDF to")
    parser.add_argument("--resolution", type=int, default=160, help="cells along the longest axis")
    parser.add_argument(
        "--bounds", type=float, nargs=6, metavar=("X0", "Y0", "Z0", "X1", "Y1", "Z1"),
        help="mesh this box instead of scanning for the part",
    )
    parser.add_argument("--ascii", action="store_true", help="ASCII STL instead of binary")
    args = parser.parse_args(argv)
    if not 8 <= args.resolution <= 512:
        parser.error("--resolution must be between 8 and 512")
    try:
        report = export(
            args.scene, args.out, args.object, args.resolution, args.bounds, not args.ascii
        )
    except Exception as error:  # noqa: BLE001 - every failure is reported as JSON
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
