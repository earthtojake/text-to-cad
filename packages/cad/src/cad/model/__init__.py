"""``cad.model``: the model document type, a model built from code: held in the engine's memory, or saved
as a file, its ``.xbf`` (``cad.registry``).

A model the engine holds is addressed by its document id (``cad run SCRIPT.py`` prints it) or the handle its
call returns; a saved one by its file's path. ``@model`` declares one (``@model(name=...)``;
``model(shape, name=...)`` hands a shape over), with no file; ``@model(xbf="XBF/arm.xbf")`` has each run save it
as that ``.xbf`` too, relative to the script, and its other files are the other types' decorators
(``@step("arm.step")``). ``model.read("vendor/motor.xbf")`` reads a saved model into a body as a build123d shape,
keyed by the file's bytes; any other file is refused with the reader that takes it (``step.read``, ``stl.read``).
Its operations are the ``cad model <operation>`` commands', each of a handle, an id or an ``.xbf`` path:
``model.export(source, *destinations, tolerance=None, angle=None)``, ``model.snapshot(...)``,
``model.inspect(...)``, ``model.interference(...)``, ``model.ranges(...)`` and ``model.dfm(source,
process="cnc")`` (or ``"sheet"``, ``"molding"``, ``"printing"``), which checks it for manufacturing on its exact
geometry, measured by the engine with the build123d integration (``cad._internal.manufacturing``), and
``model.solve(source, study=..., out="results/")``, a stress study of it (``cad._internal.fea.operation``),
which reads an ``.xbf``: the file given, or one the engine writes of a held model in a temporary folder. A file
is read as the file it is, never as the model the engine holds: its ``inspect`` says the file's state and
closure, lists its parameters read-only and names no ``made_by``. Any other file is refused by name
(``arm.step`` is ``cad.step``'s). Its script declares its parameters with
it at a module's top level, ``WALL = model.param("wall", 2.0, min=1, max=5)`` (``cad.engine.parameters.param``,
the standard library alone); a value changes in the script, by an edit and a run or the CAD Viewer's Save.
Everything loads on first use: ``import cad.model`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
