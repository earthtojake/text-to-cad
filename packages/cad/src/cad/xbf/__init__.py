"""``cad.xbf``: the XBF document type, the engine's own document (``cad.registry``).

``@xbf("XBF/arm.xbf")`` declares a model's XBF file;
``xbf.read(path)`` reads one into a model;
its operations (``xbf.export(source, *destinations)``, ...) are the ``cad xbf <operation>`` commands'.
Everything loads on first use: ``import cad.xbf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
