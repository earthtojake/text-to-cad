"""``cad.glb``: the GLB document type, a binary glTF scene (``cad.registry``).

``@glb("arm.glb")`` declares a model's GLB file;
its operations (``glb.export(source, *destinations)``, ...) are the ``cad glb <operation>`` commands'.
Everything loads on first use: ``import cad.glb`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
