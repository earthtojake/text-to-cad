"""Named native diagnostics when OCP cannot return a BRepCheck status list.

OCP 8.0.1 leaves NCollection_List<BRepCheck_Status> unbound. The scalar
checks below retain the faults they can name; callers must still distinguish
an invalid shape with no accessible diagnostic from a valid shape.
"""


def probed_statuses(entity, face=None) -> list:
    """The ``BRepCheck_Status`` values the per-type checkers report for one entity.

    Each checker answers one question with one status -- is the shell closed, are
    the face's wires oriented, do they intersect -- so the faults it can name are
    fewer than a result's status list, but every one of them is named exactly.
    Edges and vertices have no such question: the analyzer still says they are
    invalid, and the shell or face they belong to reports the fault."""
    from OCP.BRepCheck import (
        BRepCheck_Face,
        BRepCheck_NoError,
        BRepCheck_Shell,
        BRepCheck_UnorientableShape,
        BRepCheck_Wire,
    )
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_WIRE
    from OCP.TopoDS import TopoDS, TopoDS_Edge

    kind = entity.ShapeType()
    statuses = []
    if kind == TopAbs_SHELL:
        checker = BRepCheck_Shell(TopoDS.Shell(entity))
        statuses += [checker.Closed(False), checker.Orientation(False)]
        if checker.IsUnorientable():
            statuses.append(BRepCheck_UnorientableShape)
    elif kind == TopAbs_FACE:
        checker = BRepCheck_Face(TopoDS.Face(entity))
        statuses += [checker.IntersectWires(False), checker.ClassifyWires(False), checker.OrientationOfWires(False)]
        if checker.IsUnorientable():
            statuses.append(BRepCheck_UnorientableShape)
    elif kind == TopAbs_WIRE:
        checker = BRepCheck_Wire(TopoDS.Wire(entity))
        if face is not None:
            statuses.append(checker.SelfIntersect(TopoDS.Face(face), TopoDS_Edge(), TopoDS_Edge(), False))
        statuses.append(checker.Closed(False))
    return [status for status in statuses if status != BRepCheck_NoError]
