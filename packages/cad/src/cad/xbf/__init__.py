"""``cad.xbf``: the older spelling of ``cad.model`` for the file a model is saved as, its ``.xbf``
(``cad.registry.SAVED``), kept for the scripts that say it and listed nowhere.

Each name is what ``cad.model`` runs for that file: ``@xbf("XBF/arm.xbf")`` is ``@model(xbf="XBF/arm.xbf")``,
``xbf.read`` is ``model.read`` (one function), and ``xbf.export("arm.xbf", ...)``, ``xbf.inspect``,
``xbf.snapshot``, ``xbf.dfm``, ``xbf.interference``, ``xbf.solve`` and ``xbf.ranges`` are ``model``'s given an
``.xbf`` path, each of a file alone. Nothing of the library's or the server's imports this module.
Everything loads on first use: ``import cad.xbf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
