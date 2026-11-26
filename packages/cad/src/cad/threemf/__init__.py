"""``cad.threemf``: the 3MF document type, a 3D Manufacturing Format package (``cad.registry``).

``@threemf("arm.3mf")`` declares a model's 3MF file;
the verbs take one as the ``cad`` command's do (``cad.export("arm.3mf", "arm.stl")``, a mesh to the other
mesh kinds; ``cad.snapshot``).
``cad.dfm("arm.3mf")`` measures it for 3D printing (molding, CNC and sheet are judged on exact geometry), with
the trimesh integration (``cad._internal.manufacturing``).
Everything loads on first use: ``import cad.threemf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
