"""cadgen's engine: ``@xbf`` models built in a warm worker, kept as XCAF documents.

A model is a parameterless function returning a build123d shape::

    from cadgen.engine import xbf, step

    @xbf("XBF/arm.xbf")
    @step("arm.step")
    def arm():
        ...

An explicit ``arm()`` call builds it, and the child models its body calls, in a warm worker whose
kernel memo makes an edit cost what it changed; the document is written to
``XBF/arm.xbf`` beside the script, and the derived files it declares after it, each a
translation of that document (``cadgen export``). ``cadgen serve XBF/arm.xbf``
shows it. Nothing but those files is written: every cache lives in a process's memory.
The verbs as functions are ``cadgen.engine.api`` (``cadgen.export``, ``cadgen.snapshot``, ...).

A function worth replaying on a later build -- an assembly's part, a derivation's stage --
is marked ``@memo``: it writes no file, and a build whose edit does not reach it replays it
instead of running it. A part's material is a value set on the shape: ``part.material = materials.aluminium``
(``Material`` for any other). An assembly's mechanism is build123d's joints, placed with
``connect_to``, as built where the joints place the parts. The functions that say more are
``cadgen.ap242``'s and ``cadgen.gltf``'s, defined here (``model``, ``mechanism``, ``animations``)
and exported there: ``mechanism_state(assembly, name, **values)`` names a state of it, ``gear_pair``, ``rack_and_pinion_pair`` and ``screw_pair(assembly,
name, **joints)`` a constraint moving joints by ratio (their only way to move, its range their
limits'), and ``configuration_sequence(assembly, name, ...)`` a sequence of states over time, which a
GLB export bakes into a clip; ``animation(assembly, name, duration=)``
a GLB's own choreography, never in the document, baked into the GLBs the model declares. ``read_step(path)`` and ``read_xbf(path)`` copy a file's geometry into
the model, named, coloured and given its materials as the file has them; ``read_mesh(path)`` reads
an STL as data -- vertices, triangles, ``bounding_box()`` -- never a shape. A build says where it
is without a word from the model: each body it runs, by name (``progress``).
Importing this package imports no kernel: the names below load on first use. Decoration only declares: imports and definitions never build or exit the caller.
Imported by a
script run by its path from inside a package (``python proj/parts/model.py``), it gives the
script the package ``python -m proj.parts.model`` would (``model.as_package_module``).
"""

from __future__ import annotations

from typing import Any

__all__ = ["Material", "dxf", "glb", "materials", "memo", "model", "paint", "read_mesh", "read_step", "read_xbf", "step",
           "stl", "threemf", "xbf"]


def _main_in_a_package() -> None:
    """A ``__main__`` run by its path (no spec, no package) from a folder holding an
    ``__init__.py`` takes its package now, before its own relative imports run."""
    import os
    import sys

    main = sys.modules.get("__main__")
    file = getattr(main, "__file__", None)
    if getattr(main, "__spec__", True) is not None or getattr(main, "__package__", None) or \
            not isinstance(file, str) or not file.endswith(".py") or \
            not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(file)), "__init__.py")):
        return
    from cadgen.engine.model import as_package_module

    as_package_module(main)


_main_in_a_package()


def __getattr__(name: str) -> Any:
    if name == "materials":
        import importlib

        return importlib.import_module("cadgen.engine.materials")
    if name == "Material":
        from cadgen.engine.materials import Material

        return Material
    if name == "read_mesh":
        from cadgen.engine.reader import read_mesh

        return read_mesh
    if name in __all__:
        import importlib

        declarations = importlib.import_module("cadgen.engine.model")
        return declarations if name == "model" else getattr(declarations, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
