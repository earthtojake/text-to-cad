"""``cad.glb``: the GLB document type, a binary glTF scene (``cad.registry``).

``@glb("arm.glb")`` declares a model's GLB file;
the verbs take one as the ``cad`` command's do (``cad.export("arm.glb", "arm.stl")``, a mesh to the other
mesh kinds; ``cad.snapshot``, ``cad.inspect``).
``cad.dfm("arm.glb")`` measures it for 3D printing (molding, CNC and sheet are judged on exact geometry), with
the trimesh integration (``cad._internal.manufacturing``).
Everything loads on first use: ``import cad.glb`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
