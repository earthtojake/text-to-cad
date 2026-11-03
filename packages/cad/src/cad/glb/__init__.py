"""``cad.glb``: the GLB document type, a binary glTF scene (``cad.registry``).

``@glb("arm.glb")`` declares a model's GLB file;
its operations (``glb.export(source, *destinations)``, ...) are the ``cad glb <operation>`` commands'.
``glb.check(source, process="molding")`` (or ``"printing"``) measures it for manufacturing, with
the trimesh integration (``cad._internal.manufacturing``).
Everything loads on first use: ``import cad.glb`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
