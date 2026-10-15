"""The few OCP names that moved between OpenCascade 7.9 and 8.0.

OCCT 8 replaced the ``TopTools_*``, ``TDF_*``, ``TColStd_*``, ``TColgp_*`` and
``BOPAlgo_*`` collection typedefs with ``NCollection`` templates, and OCP 8
binds each instantiation once, under ``OCP.collections``, by its template
arguments: ``TopTools_IndexedMapOfShape`` is
``IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher`` there. The static
downcasts lost their ``_s`` suffix at the same time (``TopoDS.Edge_s(shape)``
is ``TopoDS.Edge(shape)``), and ``Bnd_Box.Get()`` came to return a struct OCP 8
leaves unbound.

Everything in cadgen and its tests that needs one of these imports it from
here, under the 7.9 name it has always used, so the rest of the code reads the
same on either kernel and the build123d pin can move without touching it.
Nothing else is shimmed: of the 93 distinct OCP imports and 42 static calls
cadgen makes, these are the only ones that differ, checked by importing each
against the installed OCP. What OCP 8 binds on neither side, the one caller
works around in place (``BRepCheck_Result.Status()`` in ``cadgen.geometry``).
"""

from __future__ import annotations

from OCP.TopoDS import TopoDS

try:  # OpenCascade 7.9: the typedefs
    from OCP.BOPAlgo import BOPAlgo_ListOfCheckResult
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal, TColStd_Array2OfReal
    from OCP.TColgp import TColgp_Array1OfPnt, TColgp_Array1OfPnt2d, TColgp_Array2OfPnt
    from OCP.TDF import TDF_LabelSequence
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape
except ImportError:  # OpenCascade 8: the instantiations
    from OCP.collections import (
        Array1_double as TColStd_Array1OfReal,
        Array1_gp_Pnt as TColgp_Array1OfPnt,
        Array1_gp_Pnt2d as TColgp_Array1OfPnt2d,
        Array1_int as TColStd_Array1OfInteger,
        Array2_double as TColStd_Array2OfReal,
        Array2_gp_Pnt as TColgp_Array2OfPnt,
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape,
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
        List_BOPAlgo_CheckResult as BOPAlgo_ListOfCheckResult,
        Sequence_TDF_Label as TDF_LabelSequence,
    )

# The downcasts: ``_s`` on 7.9, bare on 8.
topods_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
topods_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
topods_shell = getattr(TopoDS, "Shell_s", None) or TopoDS.Shell
topods_solid = getattr(TopoDS, "Solid_s", None) or TopoDS.Solid
topods_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
topods_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire


def bnd_box_limits(box) -> tuple[float, float, float, float, float, float]:
    """``(xmin, ymin, zmin, xmax, ymax, zmax)`` of a non-void ``Bnd_Box``.

    ``Bnd_Box.Get()`` returned the six floats on 7.9 and returns a
    ``Bnd_Box::Limits`` struct OCP 8 does not bind; the corner points are the
    same numbers on both."""
    low, high = box.CornerMin(), box.CornerMax()
    return (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())


__all__ = [
    "BOPAlgo_ListOfCheckResult",
    "TColStd_Array1OfInteger",
    "TColStd_Array1OfReal",
    "TColStd_Array2OfReal",
    "TColgp_Array1OfPnt",
    "TColgp_Array1OfPnt2d",
    "TColgp_Array2OfPnt",
    "TDF_LabelSequence",
    "TopTools_IndexedDataMapOfShapeListOfShape",
    "TopTools_IndexedMapOfShape",
    "bnd_box_limits",
    "topods_edge",
    "topods_face",
    "topods_shell",
    "topods_solid",
    "topods_vertex",
    "topods_wire",
]
