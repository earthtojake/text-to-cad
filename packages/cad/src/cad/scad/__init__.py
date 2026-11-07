"""``cad.scad``: the OpenSCAD document type (``cad.registry``), a program OpenSCAD renders to a mesh.

A ``.scad`` is an AUTHORED file, edited as text, never a document a model makes: the type has no decorator and
no edit. What a person reviews is the triangle mesh OpenSCAD renders of it -- OpenSCAD's kernel makes meshes,
no B-rep -- so every function here renders the program first, headless, into a temporary folder that is gone
when the call returns (the ``openscad`` integration's ``cad.openscad._render``; nothing is written beside the
program), then hands the engine's mesh code the STL, as an ``.stl``'s own functions would take it:

* :func:`read` is the program as mesh data (``cad.engine.reader.Mesh``: its vertices, triangles and name, and
  ``bounding_box()``), what ``stl.read`` gives of an STL: a model measures it and builds B-rep from its numbers.
  It reads the program's bytes and every file OpenSCAD read beside it, so a build that calls it has them in its
  closure; the render itself is not memoized, and runs at every build that reaches it.
* :func:`export` writes the mesh to ``.stl`` (the rendered file, byte for byte), ``.3mf`` and ``.glb``
  destinations (the engine's mesh translations); a ``.step``, an ``.xbf`` or a ``.dxf`` is refused by name:
  there is no B-rep to write.
* :func:`snapshot` draws the mesh as the CAD Viewer does, into a PNG, with the snapshot's own options.
* :func:`inspect` is the program in one look as plain data: the OpenSCAD that rendered it, the files it
  includes, its triangles and its bounds.
* ``dfm`` measures it for manufacturing with the trimesh integration (``cad._internal.manufacturing``), the
  mesh rendered first; an OpenSCAD program's numbers are millimetres.

No function sets a variable of the program (``-D``) or gives it a parameter file: a verb's option is about the
picture or the path, never the model (law 22), and a variant of a program is a program. Each is the ``cad scad
<operation>`` command, one to one. Everything loads on first use: ``import cad.scad`` imports no CAD kernel and
runs no OpenSCAD.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = ["export", "inspect", "read", "snapshot"]

# What a mesh has no translation to: an export names one of these and is refused before OpenSCAD runs.
_NO_BREP = {".step": "STEP", ".stp": "STEP", ".xbf": "xbf", ".dxf": "DXF"}


def _program(source: Any) -> Path:
    """``source`` as the program's path: a file of another type is refused by name (``refuse_other``), and one
    that is not there (``FileNotFoundError``) before OpenSCAD runs."""
    from cad._internal.document_type import refuse_other

    refuse_other("scad", source)
    path = Path(os.fspath(source)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    return path


@contextmanager
def _rendered(source: Any) -> Iterator[Any]:
    """The program rendered into a temporary folder of this call's (``cad.openscad._render.Rendered``), gone
    when the block ends."""
    from cad.openscad._render import render

    program = _program(source)
    with tempfile.TemporaryDirectory(prefix="cad-scad-") as folder:
        yield render(program, Path(folder) / f"{program.stem}.stl")


def read(path: Path | str) -> Any:
    """The program at ``path`` rendered by OpenSCAD, as mesh data (``cad.engine.reader.Mesh``: ``vertices``,
    ``triangles``, ``name`` and ``bounding_box()``), its numbers millimetres as OpenSCAD's are: what a model
    sizes or places B-rep by, as ``stl.read`` gives of an STL. The program's bytes and its includes' are read
    here too, so a build's closure holds them; the render is not memoized."""
    from cad.engine.reader import _read_mesh
    from cad.openscad._render import key

    with _rendered(path) as found:
        key(found.source, found.includes, found.version)  # the program and its libraries, read: a build's inputs
        mesh = _read_mesh(str(found.mesh))
    return mesh


def export(source: Path | str, *destinations: Path | str, log: Callable[[str], None] | None = None,
           daemon: bool = True) -> list[Any]:
    """Render the program at ``source`` and write its mesh to each destination, its kind from its suffix: an
    ``.stl`` the rendered file itself, a ``.3mf`` or a ``.glb`` the engine's translation of it (``cad.engine.api
    .export``). A ``.step``, an ``.xbf`` or a ``.dxf`` is refused by name before OpenSCAD runs: a mesh has no
    B-rep. Answers one ``cad.engine.api.Written`` per destination, in their order (``cad scad export``)."""
    import shutil
    import time

    from cad.engine.api import Written, export as translate
    from cad.engine.export import ExportRefused, kind_of

    program = _program(source)
    if not destinations:
        raise ExportRefused("export names at least one destination")
    resolved = [Path(os.fspath(destination)).expanduser() for destination in destinations]
    for destination in resolved:
        if destination.suffix.lower() in _NO_BREP:
            raise ExportRefused(f"{destination.name}: {program.name} renders to a mesh, which has no B-rep, and no "
                                f"{_NO_BREP[destination.suffix.lower()]} is made from one; export .stl, .3mf or .glb")
        kind_of(destination)  # any other suffix the engine does not write, refused by name
    with _rendered(program) as found:
        rows: dict[int, Any] = {}
        copies = [(at, destination) for at, destination in enumerate(resolved) if destination.suffix.lower() == ".stl"]
        others = [(at, destination) for at, destination in enumerate(resolved) if destination.suffix.lower() != ".stl"]
        for at, destination in copies:
            started = time.perf_counter()
            destination.parent.mkdir(parents=True, exist_ok=True)
            changed = not (destination.is_file() and destination.read_bytes() == found.mesh.read_bytes())
            if changed:
                from cad._internal.atomic_replace import replace_atomic, temp_suffix

                staged = destination.with_name(destination.name + temp_suffix())
                shutil.copyfile(found.mesh, staged)
                replace_atomic(staged, destination)
            rows[at] = Written(destination.resolve(), "stl", destination.stat().st_size, time.perf_counter() - started,
                               written=changed)
        if others:
            written = translate(found.mesh, *(destination for _at, destination in others), log=log, daemon=daemon,
                                progress=False)
            for (at, _destination), row in zip(others, written, strict=True):
                rows[at] = row
    return [rows[at] for at in range(len(resolved))]


def snapshot(source: Path | str, out: Path | str, **options: Any) -> Any:
    """Render the program at ``source`` and draw its mesh into ``out`` (a ``.png``) as the CAD Viewer draws an
    STL (``cad.engine.api.snapshot``): every option is the snapshot's, about the picture -- ``display``,
    ``camera``, ``grid``, ``width``, ``height``, ``size_profile``, ``annotation``, ``measurements``
    (``cad scad snapshot``)."""
    from cad.engine.api import snapshot as draw

    with _rendered(source) as found:
        return draw(found.mesh, out, **options)


def inspect(source: Path | str) -> dict[str, Any]:
    """What the program at ``source`` renders to, as plain data (``cad scad inspect``): ``file``, ``openscad``
    (the version that rendered it), ``includes`` (every file OpenSCAD read beside it), ``triangles``, ``bounds``
    (``min``, ``max`` and ``size``, millimetres) and ``said`` (what OpenSCAD printed: its ``echo`` lines)."""
    from cad.engine.formats.stl import read_stl

    with _rendered(source) as found:
        corners = read_stl(found.mesh)
    points = corners.reshape(-1, 3)
    bounds = None
    if len(points):
        low, high = points.min(axis=0).tolist(), points.max(axis=0).tolist()
        bounds = {"min": low, "max": high, "size": [top - bottom for bottom, top in zip(low, high, strict=True)]}
    return {"file": str(found.source), "openscad": found.version, "includes": [str(path) for path in found.includes],
            "triangles": int(len(corners)), "bounds": bounds,
            "said": [line for line in found.said.splitlines() if line.startswith("ECHO")]}


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
