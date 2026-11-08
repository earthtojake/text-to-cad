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

Nothing here imports cadjoint: the engine knows a sample's arrays, never the field.
"""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["EXTRAS", "FORMAT", "document_bytes", "facts_of", "is_glb", "read_extras", "source_of"]

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


def facts_of(positions: Any, triangles: Any) -> dict[str, Any]:
    """What the run line's delta says of a sampled mesh (``delta.FACTS``): one part, its bounds in millimetres,
    no joints or sequences, its triangles, and its volume (the signed volume of a closed mesh, mm³)."""
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
    return {"parts": 1, "bounds": bounds, "joints": 0, "sequences": 0, "warnings": [],
            "triangles": int(len(faces)), "volume": round(volume, 3)}


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
                   digest: str, cell: float) -> tuple[bytes, dict[str, Any]]:
    """The implicit document of a sample: its GLB bytes, the engine's words in ``asset.extras``
    (``read_extras``), and its facts (``facts_of``)."""
    from cad.engine.export import translate

    facts = facts_of(positions, triangles)
    source = _source(name, positions, normals, triangles)
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
    extras = (document.get("asset") or {}).get("extras") or {}
    found = extras.get(EXTRAS)
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
