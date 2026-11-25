"""``cad.model``: the model document type, a model built from code and held in the engine's memory
(``cad.registry``).

A model has no file behind it: it is addressed by its document id (``cad run SCRIPT.py`` prints it) or
the handle its call returns. ``@model`` declares one (``@model(name=...)``; ``model(shape, name=...)`` hands
a shape over), with no file of its own; the files it declares are the other types' decorators
(``@xbf("XBF/arm.xbf")``, ``@step("arm.step")``). Its operations are the ``cad model <operation>`` commands':
``model.export(handle_or_id, *destinations, tolerance=None, angle=None)``, ``model.snapshot(...)``,
``model.inspect(...)`` and ``model.dfm(handle_or_id, process="cnc")`` (or ``"sheet"``, ``"molding"``,
``"printing"``), which checks it for manufacturing on its exact geometry, measured by the engine with the build123d
integration (``cad._internal.manufacturing``), and
``model.solve(handle_or_id, study=..., out="results/")``, a stress study of it (``cad._internal.fea.operation``),
which reads an ``.xbf`` the engine writes of it in a temporary folder. Its script declares its parameters with
it at a module's top level, ``WALL = model.param("wall", 2.0, min=1, max=5)`` (``cad.engine.parameters.param``,
the standard library alone); a value changes in the script, by an edit and a run or the CAD Viewer's Save. A
file is refused by name: ``arm.xbf`` is an xbf's (``cad.xbf``). Everything loads on first use: ``import cad.model``
imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
