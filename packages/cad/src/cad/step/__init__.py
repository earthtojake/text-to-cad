"""``cad.step``: the STEP document type, an ISO 10303 (AP242) exchange file (``cad.registry``).

``@step("arm.step")`` declares a model's STEP file;
``step.read(path)`` reads one into a model;
its operations (``step.export(source, *destinations)``, ...) are the ``cad step <operation>`` commands'.
``step.dfm(source, process="molding")`` (or ``"printing"``) measures it for manufacturing, with
the trimesh integration (``cad._internal.manufacturing``).
``step.plan(source, job=..., out="cam/")`` plans a CAM job on its part, FreeCAD's toolpaths and G-code checked
against it, writing its results into that folder (with no job, it lists the faces, holes and floors a job names),
read with the kernel and planned by the freecad integration (``cad._internal.cam.operation``).
Everything loads on first use: ``import cad.step`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
