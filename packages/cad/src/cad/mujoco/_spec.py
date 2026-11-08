"""``spec``: a document as a MuJoCo ``MjSpec``, for a scene to attach.

A robot made in build123d goes into a simulation as MuJoCo's own object: ``spec(thing)`` describes
the document (``cad.engine.describe``), writes it as the engine's MJCF export does
(``cad.engine.export.mjcf``) and reads that back with ``mujoco.MjSpec.from_file``, so the spec holds
the same bodies, joints, classes, equalities and keys the ``.xml`` export holds, and a scene attaches it
(``scene.attach(spec(arm()), prefix="arm/", frame=...)``) as it attaches a Menagerie robot.

``thing`` is what a program holds of a document: a ``.xml`` or ``.mjcf`` path (read as it is, its meshes
where it names them), a ``.step``/``.stp`` or an ``.xbf`` path (the document it holds), a model call's
handle (``api.Document``: the document the engine holds, transferred into this process), or a build123d
shape, in a build or outside one (made a document here as ``model(shape, name=...)`` makes one, and
never handed to the engine). An undecorated function, a ``Model`` not called, a mesh file and anything
else is refused by name.

MuJoCo reads a mesh's file when the spec is compiled, not when it is made, so the files must outlive
the call. Where they go:

- ``assets`` None: a folder of the engine's cache (``places.cache_dir()/mjcf/<digest>``), named by the
  digest of what is written (the MJCF and every mesh), so the same document lands in the same folder and
  a changed one in a new folder. The spec names each mesh by its absolute path: a scene saved from it
  (``to_file``) finds them anywhere on this computer, and nowhere else. It is a cache: wiping it loses a
  saved scene's meshes, never a document.
- ``assets`` a folder: the meshes and the fragment's MJCF (``<assets>/<model>.xml``) are written there,
  relative to the working directory, and the spec names each mesh as ``<assets>/<file>``, the folder as
  given: a scene written to the working directory (``scene.to_file("scene.xml")``), with no ``meshdir``
  of its own, finds them, and moves with them.

Either way the spec's own mesh folder is cleared (``meshdir``, ``modelfiledir``), because MuJoCo resolves
an attached spec's mesh files by the child's folder when it compiles but writes them bare when it saves
the scene, so a saved scene finds nothing the child's folder held. ``tolerance`` meshes the visual and
collision meshes to within it (millimetres, as an export's): the engine's own otherwise.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["spec"]

EXTRA = "cad[mujoco]"
SUFFIXES = (".xml", ".mjcf")


def spec(thing: Any, *, assets: str | Path | None = None, tolerance: float | None = None) -> Any:
    """``thing`` as a ``mujoco.MjSpec`` (see the module docstring)."""
    try:
        import mujoco
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(f"mujoco comes with cad's mujoco integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name=error.name) from None
    from cad.engine.export import tolerance_of

    if isinstance(thing, (str, os.PathLike)) and Path(thing).suffix.lower() in SUFFIXES:
        path = Path(thing)
        if tolerance is not None:
            raise ValueError(f"{path.name} is an MJCF: its meshes are its files, and no tolerance meshes them again")
        if not path.is_file():
            raise FileNotFoundError(f"no MJCF {path}")
        return mujoco.MjSpec.from_file(str(path))
    tolerance = tolerance_of(tolerance)
    with _source(thing) as source:
        from cad.engine.describe import describe

        view = source.view()
        view.tolerance = tolerance
        description = describe(view)
    return _written(mujoco, description, assets)


def _written(mujoco: Any, description: Any, assets: str | Path | None) -> Any:
    """``description`` written where ``assets`` says and read back as a spec naming its meshes so a saved
    scene finds them."""
    from cad.engine.export.mjcf import digest, place, rendered

    stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in description.name).strip(".") or "model"
    if assets is None:
        from cad.engine.places import cache_dir

        text, files = rendered(description, "assets")
        folder = cache_dir() / "mjcf" / digest(text, files)[:32]
        fragment = folder / f"{stem}.xml"
        place(fragment, text, files, "assets")
        named = {name: str((folder / "assets" / name).resolve()) for name in files}
    else:
        given = Path(assets)
        text, files = rendered(description, ".")
        fragment = given / f"{stem}.xml"
        place(fragment, text, files, ".")
        named = {name: (given / name).as_posix() for name in files}
    made = mujoco.MjSpec.from_file(str(fragment))
    made.meshdir = ""
    made.modelfiledir = ""
    for mesh in made.meshes:
        mesh.file = named.get(mesh.file, mesh.file)
    return made


class _source:
    """The document ``thing`` names, as an ``export.Source``, for the length of a ``with``."""

    def __init__(self, thing: Any) -> None:
        self.thing = thing
        self.folder: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> Any:
        from cad.engine import api
        from cad.engine.export import MESHES, SOURCES, Source
        from cad.engine.model import Model

        thing = self.thing
        if isinstance(thing, (str, os.PathLike)):
            path = Path(thing)
            if path.suffix.lower() in MESHES:
                raise ValueError(f"{path.name} is a mesh: it has no solids to weigh or joints to move, and no MJCF is "
                                 "made from one")
            if path.suffix.lower() not in SOURCES:
                raise ValueError(f"{path.name}: spec reads an MJCF ({', '.join(SUFFIXES)}), a STEP or an .xbf")
            if not path.is_file():
                raise FileNotFoundError(f"no document {path}")
            return Source.read(path)
        if isinstance(thing, Model):
            raise TypeError(f"{thing.name} is a model, not its document: call it, spec({thing.name}()), and pass "
                            "the handle the call returns")
        if isinstance(thing, api.Document):
            if not thing._inside:
                return thing._transferred()
            return self._shape(thing.shape, thing.name)
        # A build123d shape, known by its type's module and its wrapped TopoDS, never by importing build123d
        # here: this module imports its own extra alone (law 26), and the shape brings its library with it.
        if type(thing).__module__.split(".")[0] == "build123d" and hasattr(thing, "wrapped"):
            return self._shape(thing, thing.__dict__.get("label") or "model")
        raise TypeError(f"spec takes an MJCF, a STEP or an .xbf path, a model call's handle or a build123d shape; "
                        f"not {type(thing).__name__}")

    def _shape(self, shape: Any, name: str) -> Any:
        """A shape made a document in this process, as ``model(shape, name=...)`` makes one (``api._handed_bytes``),
        and read back from those bytes: the engine is not asked."""
        from cad.engine import api
        from cad.engine.export import Source

        self.folder = tempfile.TemporaryDirectory(prefix="cad-mujoco-spec-")
        path = Path(self.folder.name) / "shape.xbf"
        path.write_bytes(api._handed_bytes(shape, name, None))
        return Source.read(path)

    def __exit__(self, *_exc: object) -> None:
        if self.folder is not None:
            self.folder.cleanup()
