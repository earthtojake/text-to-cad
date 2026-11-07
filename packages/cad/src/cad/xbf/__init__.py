"""``cad.xbf``: the XBF document type, the engine's own document saved as a file (``cad.registry``).

``@xbf("XBF/arm.xbf")`` declares a model's XBF file;
``xbf.read(path)`` reads one into a model;
its operations (``xbf.export("arm.xbf", *destinations)``, ...) are the ``cad xbf <operation>`` commands',
each of an ``.xbf`` file: a model the engine holds, by its handle or id, is ``cad.model``'s.
``xbf.dfm(source, process="molding")`` (or ``"printing"``) measures it for manufacturing, with
the trimesh integration (``cad._internal.manufacturing``).
``xbf.fea(source, study=..., out="result.glb")`` runs a stress study on its part or bonded assembly
(with no study, lists the parts, pairs and faces a study names), with the netgen and calculix integrations
(``cad._internal.fea.operation``).
Everything loads on first use: ``import cad.xbf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
