"""What the engine keeps of an OpenSCAD program: its mesh, rendered by OpenSCAD and kept by the program's bytes.

The engine renders no program itself: OpenSCAD does, headless, in its own process (the openscad integration,
``cad.openscad._render``), and what it rendered is kept beside the program's document in the engine's
document cache, ``<cache>/documents/<the program's document id>/openscad/<key>/mesh.stl`` (``folder``), so a
changed file is a new key and nothing stale is ever read, and deleting the document (``cad delete``, the
home's Delete) deletes it with it (``Registry.delete`` removes ``documents/<id>`` whole). The key
(``cad.openscad._render.key``) is the program's bytes, the bytes of every file OpenSCAD read beside it, its
version and the render code's. Which files those are is known from the last render (``INCLUDES``, kept beside
the keys): a lookup reads the program and those, so an edited library file is a new key as an edited program
is; a program not rendered yet is keyed by its own bytes, rendered, and its includes recorded, so the next
lookup finds what the render kept.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from cad._internal.atomic_replace import replace_atomic, write_bytes_atomic

__all__ = ["INCLUDES", "MESH", "folder", "includes", "key", "rendered"]

#: The includes the last render read, beside the keys; the mesh under its key.
INCLUDES = "includes.json"
MESH = "mesh.stl"


def folder(source: str | os.PathLike) -> Path:
    """Where what is made of the program at ``source`` is kept: under its document in the engine's document
    cache, ``<cache>/documents/<the file's document id>/openscad``."""
    from cad.engine.ids import file_id
    from cad.engine.places import cache_dir

    return cache_dir() / "documents" / file_id(source) / "openscad"


def includes(source: str | os.PathLike) -> list[Path]:
    """The files OpenSCAD read beside the program at its last render, as recorded; none before one."""
    try:
        found = json.loads((folder(source) / INCLUDES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Path(item) for item in found if isinstance(item, str)] if isinstance(found, list) else []


def key(source: str | os.PathLike, version: str) -> str:
    """The program's key as it is now, with the includes its last render read (``_render.key``)."""
    from cad.openscad._render import key as keyed

    return keyed(source, includes(source), version)


def rendered(source: str | os.PathLike, version: str) -> tuple[Path, str]:
    """The program's mesh as the file is now: the kept one for its key, else rendered by OpenSCAD now, kept
    under the key of what the render read, and its includes recorded. ``(the STL, its key)``. ``RenderError``
    (``TwoDimensional`` for a 2D program) in OpenSCAD's words, ``OpenscadMissing`` with no OpenSCAD."""
    from cad.openscad._render import key as keyed, render

    program = Path(os.fspath(source))
    known = key(program, version)
    kept = folder(program) / known / MESH
    if kept.is_file():
        return kept, known
    home = folder(program)
    home.mkdir(parents=True, exist_ok=True)
    # Rendered into a folder of this render's own (two renders of one program, an edit's mid-render, never
    # share one), then moved under the key the render found; the folder removed either way.
    staging = Path(tempfile.mkdtemp(prefix="rendering-", dir=home))
    try:
        found = render(program, staging / MESH)
        actual = keyed(found.source, found.includes, found.version)
        target = home / actual / MESH
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_atomic(found.mesh, target)
        write_bytes_atomic(home / INCLUDES, json.dumps([str(path) for path in found.includes]).encode("utf-8"))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target, actual
