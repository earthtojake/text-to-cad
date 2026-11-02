"""``cad.step``: the STEP document type, an ISO 10303 (AP242) exchange file (``cad.registry``).

``@step("arm.step")`` declares a model's STEP file;
``step.read(path)`` reads one into a model;
its operations (``step.export(source, *destinations)``, ...) are the ``cad step <operation>`` commands'.
Everything loads on first use: ``import cad.step`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
