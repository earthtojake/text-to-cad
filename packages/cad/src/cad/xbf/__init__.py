"""``cad.xbf``: the XBF document type, the engine's own document, saved as a file, its ``.xbf``
(``cad.registry``).

A model is addressed by its ``.xbf``'s path or the handle its call returns. ``@xbf`` declares one
(``@xbf(name=...)``), and ``@xbf("XBF/arm.xbf")`` has each run save it as that ``.xbf``, relative to the script
(bare: ``<name>.xbf`` beside it); its other files are the other types' decorators (``@step("arm.step")``), and a
shape a program holds is saved as one by ``cad.save(shape, "plate.xbf")``. ``xbf.read("vendor/motor.xbf")``
reads a saved model into a body as a build123d shape, keyed by the file's bytes; any other file is refused with
the reader that takes it (``step.read``, ``stl.read``). The verbs take a model as the ``cad`` command's do, by
its handle or its ``.xbf``: ``cad.export(source, "arm.glb", tolerance=None, angle=None)``, ``cad.snapshot``,
``cad.inspect`` (with ``interference=True`` or ``ranges=True`` too), ``cad.dfm(source, process="cnc")`` (or
``"sheet"``, ``"molding"``, ``"printing"``), which checks it for manufacturing on its exact geometry, measured
by the engine with the build123d integration (``cad._internal.manufacturing``), and ``cad.fea(source,
study=..., out="results/")``, a stress study of it (``cad._internal.fea.operation``), which reads an ``.xbf``:
the file given, or one the engine writes of a held model in a temporary folder. A file is read as the file it
is, never as the model the engine holds: its inspection says the file's state and closure, lists its
parameters read-only and names no ``made_by``. Any other file is refused by name (``arm.step`` is
``cad.step``'s). Its script declares its parameters with it at a module's top level, ``WALL =
xbf.param("wall", 2.0, min=1, max=5)`` (``cad.engine.parameters.param``, the standard library alone); a value
changes in the script, by an edit and a run or the CAD Viewer's Save.
Everything loads on first use: ``import cad.xbf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
