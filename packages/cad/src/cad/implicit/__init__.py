"""``cad.implicit``: the implicit document type, a model built from a signed-distance field and held in the
engine's memory as the mesh sampled from it, with no file behind it (``cad.registry``).

``@implicit`` declares one: its function returns ``cad.cadjoint.field(scene, cell=...)``, a cadjoint SDF with
the cell it is sampled at. A call builds it and returns its document's handle, as ``@model``'s does. Its
operations (``implicit.export(source, *destinations)``, ``.snapshot``, ``.inspect``, ``.dfm``) are the
``cad implicit <operation>`` commands', each taking the document's id or its handle, never a file.
Everything loads on first use: ``import cad.implicit`` imports no cadjoint and no CAD kernel
(``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
