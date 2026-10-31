"""Numeric bounds of OCCT boxes, without tessellating geometry."""

import math


def box_limits(box) -> tuple[float, float, float, float, float, float]:
    """Return (xmin, ymin, zmin, xmax, ymax, zmax) of a non-void Bnd_Box.

    OCP 8 does not bind the Limits structure returned by Bnd_Box.Get().
    The two corner points expose the same bounds, including the box's gap.
    """
    low, high = box.CornerMin(), box.CornerMax()
    return low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z()


def optimal_box(shape):
    """Measure the shape without the OCP 8 spline-grid extrema heuristic.

    OCCT #1604 can miss a spline's extremum when its grid refinement test ties.
    For a free-form surface, distances to six exterior support planes give the
    extrema directly, including trimmed faces. Nothing meshes or changes the
    input shape. Analytic surfaces and edges retain the native fast path.
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.GeomAbs import (GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane,
                             GeomAbs_Sphere, GeomAbs_Torus)
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    analytic = (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus)
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        if BRepAdaptor_Surface(TopoDS.Face(faces.Current()), False).GetType() not in analytic:
            return _support_box(shape)
        faces.Next()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return box


def _support_box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeFace
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.Precision import Precision
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return box
    limits = box_limits(box)
    if not all(math.isfinite(value) for value in limits):
        raise ValueError("cannot measure a non-finite shape's bounds")
    # Measure the boundary, not the solid's interior. DistShapeShape's solid
    # classifier can report exterior planes as contained by a spline solid;
    # a reversed shell's interior is unbounded too, but its box is unchanged.
    # Copy topology before adding faces so the builder changes no input flags.
    copied = BRepBuilderAPI_Copy(shape, False, False).Shape()
    boundary = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(boundary)
    for kind, avoid in ((TopAbs_FACE, TopAbs_SHAPE), (TopAbs_EDGE, TopAbs_FACE), (TopAbs_VERTEX, TopAbs_EDGE)):
        elements = TopExp_Explorer(copied, kind, avoid)
        while elements.More():
            builder.Add(boundary, elements.Current())
            elements.Next()
    center = [(limits[axis] + limits[axis + 3]) / 2 for axis in range(3)]
    reach = max(max(limits[axis + 3] - limits[axis] for axis in range(3)), 1.0) * 2
    measured = [0.0] * 6
    for axis in range(3):
        direction = [0.0] * 3
        direction[axis] = 1.0
        for side, offset in ((-1, 0), (1, 3)):
            origin = center.copy()
            origin[axis] += side * reach
            plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*direction))
            face = BRepBuilderAPI_MakeFace(plane, -reach, reach, -reach, reach).Face()
            distance = BRepExtrema_DistShapeShape(boundary, face, Precision.Confusion_s())
            if not distance.IsDone() or distance.InnerSolution() or not math.isfinite(distance.Value()):
                raise ValueError("the kernel could not measure a shape's support plane distance")
            measured[axis + offset] = origin[axis] - side * distance.Value()
    result = Bnd_Box()
    result.Update(*measured)
    return result
