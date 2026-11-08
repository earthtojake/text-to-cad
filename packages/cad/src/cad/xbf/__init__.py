"""``cad.xbf``: the XBF document type, the engine's own document saved as a file (``cad.registry``).

``@xbf("XBF/arm.xbf")`` declares a model's XBF file;
``xbf.read(path)`` reads one into a model;
its operations (``xbf.export("arm.xbf", *destinations)``, ...) are the ``cad xbf <operation>`` commands',
each of an ``.xbf`` file: a model the engine holds, by its handle or id, is ``cad.model``'s.
``xbf.dfm(source, process="molding")`` (or ``"printing"``) measures it for manufacturing, with
the trimesh integration (``cad._internal.manufacturing``).
``xbf.plan(source, job=..., out="cam/")`` plans a CAM job on its part, FreeCAD's toolpaths and G-code checked
against it, writing its results into that folder (with no job, it lists the faces, holes and floors a job names),
read with the kernel and planned by the freecad integration (``cad._internal.cam.operation``).
Everything loads on first use: ``import cad.xbf`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
