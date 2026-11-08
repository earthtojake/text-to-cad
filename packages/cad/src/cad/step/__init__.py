"""``cad.step``: the STEP document type, an ISO 10303 (AP242) exchange file (``cad.registry``).

``@step("arm.step")`` declares a model's STEP file;
``step.read(path)`` reads one into a model; its AP242 semantic PMI is read and checked in
``_ap242`` with the standard library alone;
its operations (``step.export(source, *destinations)``, ...) are the ``cad step <operation>`` commands'.
``step.dfm(source, process="molding")`` (or ``"printing"``) measures it for manufacturing, with
the trimesh integration (``cad._internal.manufacturing``).
Everything loads on first use: ``import cad.step`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
