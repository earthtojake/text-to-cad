"""``cad.dxf``: the DXF document type, a 2D drawing of a planar document (``cad.registry``).

``@dxf("plate.dxf")`` declares a model's DXF file;
its operations (``dxf.snapshot(source, out)``, ...) are the ``cad dxf <operation>`` commands'.
Everything loads on first use: ``import cad.dxf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
