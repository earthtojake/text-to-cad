"""An implicit document: the mesh sampled from a field, as the engine holds and writes it.

A model declared ``@implicit`` returns a field with its sampling (the cadjoint integration's
``cad.cadjoint.field``), and its producer samples it (``cad.cadjoint._document``) into vertices, the field's
normals at them and triangles. The engine makes those the document: a GLB written by the engine's own
GLB writer (``export/glb.py``: one part, one placement, the engine's frame), with what a model's xbf carries
on its main label in the glTF's ``asset.extras`` under ``cad`` -- the writer, the build closure
(``previous``), the field's digest and the sample's facts -- so a cache file of it is taken by its key as an
xbf is (``build._previous``), a rebuild to the same field keeps its bytes, and the run line's delta reads
its facts. The daemon holds it as a document with no file of the author's: ``documents/<id>/document.glb``
in its cache, served to the page's mesh view, and every verb of it the mesh file's (``cad glb ...``).
Its normals are split at folds (``split_folds``): a sample's vertex on a crease carries one normal, the
mean of both sides', which shading would blend across the crease, so a vertex there is written once per
smooth side, each with its side's normal.

Nothing here imports cadjoint: the engine knows a sample's arrays, never the field.
"""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["EXTRAS", "FORMAT", "document_bytes", "extras_of", "facts_of", "is_glb", "read_extras", "source_of",
           "split_folds"]

#: The document's format, as the daemon's records, the cache and the worker's frames name it.
FORMAT = "glb"
#: Where the engine's own words are in the glTF: ``asset.extras.cad``.
EXTRAS = "cad"


def _container() -> tuple[int, int]:
    """The GLB container's magic and JSON chunk type: the GLB writer's constants, declared there alone
    (``export/glb.py``), imported when first needed (the writer imports numpy, which the daemon does not until
    a document's bytes are looked at)."""
    from cad.engine.export.glb import JSON_CHUNK, MAGIC

    return MAGIC, JSON_CHUNK


def is_glb(data: bytes) -> bool:
    """Whether ``data`` begins as a GLB does (the container's magic)."""
    return len(data) >= 12 and struct.unpack_from("<I", data)[0] == _container()[0]


def facts_of(positions: Any, triangles: Any, *, wall: float | None = None, cell: float | None = None) -> dict[str, Any]:
    """What the run line's delta says of a sampled mesh (``delta.FACTS``): one part, its bounds in millimetres,
    no joints or sequences, its triangles, its volume (the signed volume of a closed mesh, mm³), and its
    thinnest wall (the sampling's, ``cad.cadjoint._field._wall``) in millimetres and in cells of ``cell``:
    ``wall_mm`` and ``wall_cells``, None where none was measured."""
    import numpy as np

    points = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if len(points) and len(faces):
        low, high = points.min(axis=0), points.max(axis=0)
        bounds = [round(float(value), 4) for value in (high - low)]
        a, b, c = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]
        volume = float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    else:
        bounds, volume = None, 0.0
    measured = wall is not None and cell is not None and cell > 0
    return {"parts": 1, "bounds": bounds, "joints": 0, "sequences": 0, "warnings": [],
            "triangles": int(len(faces)), "volume": round(volume, 3),
            "wall_mm": round(float(wall), 4) if measured else None,
            "wall_cells": round(float(wall) / float(cell), 2) if measured else None}


def _roots(parent: Any, start: Any, end: Any) -> Any:
    """Each item's root under the joins ``start[i]``--``end[i]``: a union-find of numpy's alone (as the
    sampling's ``_bodies``), each round hooking every root onto the lowest root a join reaches."""
    import numpy as np

    while True:
        a, b = parent[start], parent[end]
        apart = a != b
        if not apart.any():
            return parent
        low, high = np.minimum(a[apart], b[apart]), np.maximum(a[apart], b[apart])
        np.minimum.at(parent, high, low)
        while True:
            jumped = parent[parent]
            if (jumped == parent).all():
                break
            parent = jumped


def split_folds(positions: Any, normals: Any, triangles: Any, *, crease: float | None = None) -> tuple[Any, Any, Any]:
    """The sample with a vertex for each smooth side of a fold: what the document's shading takes.

    The triangles at a vertex fall into sides: two that share an edge through it are on one side when their
    normals part by no more than ``crease`` degrees (the viewer's, ``formats.buffer.CREASE``), and a side
    reaches as far round the vertex as such edges join it. A vertex of one side keeps its index and the
    field's normal, closer than any average of facets on a smooth surface. A vertex where a fold divides its
    triangles (two sides or more) is one vertex per side: the first keeps its index, the rest follow the
    sample's vertices in order, each side's triangles name its own, and its normal is the mean of the side's
    triangles' normals weighted by their areas: the field's one normal there is a mean of both sides (a
    cadjoint vertex's is the mean of the Hermite normals its cell saw), true of neither. With no ``normals``,
    every vertex takes its side's mean. A triangle of no area folds nowhere. Returns ``(positions, normals,
    triangles)``: as many triangles, the same corners at the same points; only a fold's vertices split, so
    the mesh is welded everywhere else."""
    import math

    import numpy as np

    from cad.engine.formats.buffer import CREASE

    positions = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    count = len(positions)
    if not len(faces):
        return positions, normals, faces
    limit = math.cos(math.radians(CREASE if crease is None else crease))
    a, b, c = (positions[faces[:, at]] for at in range(3))
    weighted = np.cross(b - a, c - a)  # twice each triangle's area along its normal
    length = np.linalg.norm(weighted, axis=1, keepdims=True)
    flat = length[:, 0] <= 1e-12 * max(1.0, float(np.abs(positions).max()) ** 2)
    unit = np.where(flat[:, None], 0.0, weighted / np.where(flat[:, None], 1.0, length))
    # Corner ``3 t + k`` is triangle t's k-th; the half-edge it starts runs to the next corner's vertex.
    vertex = faces.reshape(-1)
    corners = np.arange(len(vertex))
    following = corners - corners % 3 + (corners + 1) % 3
    end = vertex[following]
    low, high = np.minimum(vertex, end), np.maximum(vertex, end)
    order = np.lexsort((high, low))
    first = np.flatnonzero(np.r_[True, (low[order][1:] != low[order][:-1]) | (high[order][1:] != high[order][:-1])])
    sizes = np.diff(np.r_[first, len(order)])
    one, two = order[first[sizes == 2]], order[first[sizes == 2] + 1]
    owner_one, owner_two = one // 3, two // 3
    smooth = (np.einsum("ij,ij->i", unit[owner_one], unit[owner_two]) >= limit) | flat[owner_one] | flat[owner_two]
    one, two = one[smooth], two[smooth]
    # An edge the two triangles run opposite ways (a welded mesh's): one's start is two's end.
    opposite = vertex[one] == end[two]
    near = np.where(opposite, following[two], two)
    far = np.where(opposite, two, following[two])
    root = _roots(corners.copy(), np.r_[one, following[one]], np.r_[near, far])
    sides, side_of = np.unique(root, return_inverse=True)
    side_vertex = vertex[sides]
    per_vertex = np.bincount(side_vertex, minlength=count)
    if not (per_vertex > 1).any():
        return positions, normals, faces
    summed = np.zeros((len(sides), 3))
    np.add.at(summed, side_of, weighted[corners // 3])
    size = np.linalg.norm(summed, axis=1, keepdims=True)
    mean = np.where(size > 0, summed / np.where(size > 0, size, 1.0), 0.0)
    # Each vertex's side of its lowest corner keeps the vertex's index; every other side of a divided
    # vertex is a new vertex after the sample's.
    by_vertex = np.lexsort((sides, side_vertex))
    leading = np.zeros(len(sides), dtype=bool)
    leading[by_vertex[np.r_[True, side_vertex[by_vertex][1:] != side_vertex[by_vertex][:-1]]]] = True
    index = side_vertex.copy()
    extra = np.flatnonzero(~leading)
    index[extra] = count + np.arange(len(extra))
    split_positions = np.concatenate([positions, positions[side_vertex[extra]]])
    given = None if normals is None else np.asarray(normals, dtype=np.float64).reshape(-1, 3)
    kept = mean if given is None else np.where((per_vertex[side_vertex] > 1)[:, None], mean, given[side_vertex])
    split_normals = np.zeros_like(split_positions)
    split_normals[:count] = 0.0 if given is None else given
    split_normals[index] = kept
    return split_positions, split_normals, index[side_of].reshape(-1, 3)


def _source(name: str, positions: Any, normals: Any, triangles: Any) -> Any:
    """The sample as an ``export.Source`` of one part, placed at the origin: what the engine's mesh writers take."""
    import numpy as np

    from cad.engine.export import Source
    from cad.engine.export.mesh_file import _column_major, _prototype, mesh_of

    mesh = mesh_of(positions, triangles, None, normals)
    prototype = _prototype(0, name, mesh, None, {}, None, {})
    structure = {"name": name, "path": "", "version": "", "units": "mm", "kind": FORMAT, "prototypes": [prototype],
                 "instances": [{"prototype": 0, "path": f"{name}/{name}", "matrix": _column_major(np.eye(4)),
                                "color": None}],
                 "tree": {"name": name, "prototype": 0, "instance": 0}}
    return Source(structure, {}, live=False, path=None, meshes={prototype["key"]: mesh}, mesh=FORMAT)


def document_bytes(name: str, positions: Any, normals: Any, triangles: Any, *, closure: str | None,
                   digest: str, cell: float, wall: float | None = None) -> tuple[bytes, dict[str, Any]]:
    """The implicit document of a sample: its GLB bytes, the engine's words in ``asset.extras``
    (``read_extras``), and its facts (``facts_of``, its thinnest wall ``wall`` in millimetres among them)."""
    from cad.engine.export import translate

    facts = facts_of(positions, triangles, wall=wall, cell=cell)
    source = _source(name, *split_folds(positions, normals, triangles))
    with tempfile.TemporaryDirectory(prefix="cad-implicit-") as folder:
        path = Path(folder) / "document.glb"
        translate(source, FORMAT, path)
        data = path.read_bytes()
    extras = {"writer": _writer(), "closure": closure, "digest": digest, "cell": cell, "facts": facts,
              "format": FORMAT}
    return with_extras(data, extras), facts


def _writer() -> str:
    from cad.engine import previous

    return f"cad.engine {FORMAT} ({previous.version()})"


def with_extras(data: bytes, extras: dict[str, Any]) -> bytes:
    """``data`` (a GLB) with ``extras`` under ``asset.extras.cad``: its JSON chunk rewritten, its binary
    chunk as it is."""
    document, rest = _split(data)
    asset = document.setdefault("asset", {"version": "2.0"})
    asset.setdefault("extras", {})[EXTRAS] = extras
    body = json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    body += b" " * (-len(body) % 4)
    magic, json_chunk = _container()
    chunks = struct.pack("<II", len(body), json_chunk) + body + rest
    return struct.pack("<III", magic, 2, 12 + len(chunks)) + chunks


def _split(data: bytes) -> tuple[dict[str, Any], bytes]:
    """A GLB's JSON (its first chunk) and the chunks after it, as bytes."""
    if not is_glb(data):
        raise ValueError("not a GLB: it does not begin with glTF")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != _container()[1]:
        raise ValueError("not a GLB: its first chunk is not its JSON")
    document = json.loads(data[20:20 + length])
    at = 20 + length + (-length % 4)
    return document, data[at:]


def read_extras(data: bytes) -> dict[str, Any] | None:
    """The engine's words an implicit document carries (``asset.extras.cad``), or None for a GLB that is no
    document of the engine's."""
    try:
        document, _rest = _split(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return extras_of(document)


def extras_of(document: Any) -> dict[str, Any] | None:
    """``read_extras`` of a GLB's JSON already parsed (its first chunk): the marker a reader keys on, as the
    stills' GLB reader does to draw an implicit document with no feature edges (``formats/glb.py``)."""
    asset = document.get("asset") if isinstance(document, dict) else None
    extras = asset.get("extras") if isinstance(asset, dict) else None
    found = extras.get(EXTRAS) if isinstance(extras, dict) else None
    return found if isinstance(found, dict) and found.get("format") == FORMAT else None


def source_of(data: bytes, name: str) -> Any:
    """An implicit document's bytes as an ``export.Source``, read as a GLB on disk is (``mesh_file.read``): what
    an export, a snapshot or a check of a held document reads. The file it is read through is temporary;
    the source keeps no path."""
    from cad.engine.export.mesh_file import read

    with tempfile.TemporaryDirectory(prefix="cad-implicit-") as folder:
        path = Path(folder) / f"{_stem(name)}.glb"
        path.write_bytes(data)
        source = read(path)
    source.path = None
    source.structure["path"] = ""
    return source


def _stem(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name).strip(".") or "document"
