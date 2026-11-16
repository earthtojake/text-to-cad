"""``cad.stl``: the STL document type, a binary STL mesh (``cad.registry``).

``@stl("arm.stl")`` declares a model's STL file;
``stl.read(path)`` reads one into a model;
its operations (``stl.export(source, *destinations)``, ...) are the ``cad stl <operation>`` commands'.
``stl.dfm(source)`` measures it for 3D printing (molding, CNC and sheet are judged on exact geometry), with
the trimesh integration (``cad._internal.manufacturing``).
Everything loads on first use: ``import cad.stl`` imports no CAD kernel (``cad._internal.document_type``).
"""

from cad._internal.document_type import bind as _bind

_bind(__name__)
