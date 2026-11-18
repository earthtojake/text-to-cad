"""``cad.step``: the STEP document type, an ISO 10303 (AP242) exchange file (``cad.registry``).

``@step("arm.step")`` declares a model's STEP file;
``step.read(path)`` reads one into a model;
its operations (``step.export(source, *destinations)``, ...) are the ``cad step <operation>`` commands'.
``step.dfm(source, process="cnc")`` (or ``"sheet"``, ``"molding"``, ``"printing"``) checks it for manufacturing
on its exact geometry, with the build123d integration (``cad._internal.manufacturing``).
``step.solve(source, study=..., out="results/")`` runs a stress study on its part or bonded assembly, writing
its results into that folder (with no study, it lists the parts, pairs and faces a study names), with the
kernel, netgen and calculix integrations (``cad._internal.fea.operation``).
Everything loads on first use: ``import cad.step`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
