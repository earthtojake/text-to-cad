"""``cad.dxf``: the DXF document type, a 2D drawing of a planar document (``cad.registry``).

``@dxf("plate.dxf")`` declares a model's DXF file;
the verbs take one as the ``cad`` command's do: ``cad.snapshot("plate.dxf", "plate.png")`` draws it, and
``cad.dfm("plate.dxf")`` checks it as a sheet's cut file.
Everything loads on first use: ``import cad.dxf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
