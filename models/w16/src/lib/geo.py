"""Frame/placement helpers shared by every builder (plain module)."""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import spec as S


def _unit(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def plane(origin, z_dir, x_dir=None) -> bd.Plane:
    """A Plane from explicit vectors. x_dir defaults to a stable perpendicular."""
    z = _unit(z_dir)
    if x_dir is None:
        ref = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
        x = _cross(ref, z)
        x = _cross(z, _cross(x, z))
    else:
        x = x_dir
    # orthogonalise x against z
    d = x[0] * z[0] + x[1] * z[1] + x[2] * z[2]
    x = _unit((x[0] - d * z[0], x[1] - d * z[1], x[2] - d * z[2]))
    return bd.Plane(origin=bd.Vector(*origin), x_dir=bd.Vector(*x), z_dir=bd.Vector(*z))


def locate(shape, origin, z_dir, x_dir=None):
    """Copy of `shape` (authored at the origin, +Z up) placed with local +Z
    along z_dir and local +X along x_dir (default: engine +X when possible)."""
    if x_dir is None and abs(_unit(z_dir)[0]) < 0.99:
        x_dir = (1.0, 0.0, 0.0)
    return plane(origin, z_dir, x_dir).location * shape


def yz_plane(x: float) -> bd.Plane:
    """Sketch plane perpendicular to the crank axis at station x, with local
    x = engine Y and local y = engine Z (so 2D (y, z) maps straight in)."""
    return bd.Plane(origin=(x, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))


def prism_yz(points, x0: float, x1: float):
    """Extrude a closed (y, z) polygon between stations x0 < x1."""
    face = bd.make_face(bd.Polyline(*[(y, z) for y, z in points], close=True).edges())
    face = yz_plane(x0).location * face if False else face
    solid = bd.extrude(yz_plane(x0) * face, amount=x1 - x0)
    return solid


def cyl_along(p0, p1, d: float):
    """Cylinder of diameter d from point p0 to point p1."""
    v = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    L = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    c = bd.Cylinder(d / 2.0, L, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return locate(c, p0, v)


def cyl_x(x0: float, x1: float, d: float, yc: float = 0.0, zc: float = 0.0):
    """Cylinder along +X between stations x0 and x1, centred at (yc, zc)."""
    return cyl_along((x0, yc, zc), (x1, yc, zc), d)


def section_cutter(bank: int = S.SECTION_BANK):
    """The museum-section cutter for bank-1 static parts (x > SECTION_X)."""
    assert bank == 1, "only bank 1 is sectioned"
    return bd.Box(1000.0, 1000.0, 1000.0, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)).moved(
        bd.Location((S.SECTION_X, S.SECTION_Y_MIN, S.SECTION_Z_MIN)))


def sectioned(shape, bank: int, enabled: bool):
    if enabled and bank == S.SECTION_BANK:
        return shape - section_cutter(bank)
    return shape


def in_section_void(point, bank: int, enabled: bool) -> bool:
    """True when a point of a bank-1 static lies in the removed region (so a
    fastener seated there is simply omitted)."""
    return (enabled and bank == S.SECTION_BANK and point[0] > S.SECTION_X
            and point[1] > S.SECTION_Y_MIN and point[2] > S.SECTION_Z_MIN)


def cut_fuzzy(shape, tools, fuzzy: float = 1e-3):
    """Boolean cut with an OCCT fuzzy value: absorbs near-tangent/coincident
    surface noise that makes an exact cut BOP-invalid. `tools` is a list."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.TopTools import TopTools_ListOfShape

    args = TopTools_ListOfShape()
    args.Append(shape.wrapped)
    tl = TopTools_ListOfShape()
    for t in tools:
        tl.Append(t.wrapped)
    op = BRepAlgoAPI_Cut()
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("fuzzy cut failed")
    return _wrap(op.Shape())


def fuse_fuzzy(shapes, fuzzy: float = 1e-3):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.TopTools import TopTools_ListOfShape

    args = TopTools_ListOfShape()
    args.Append(shapes[0].wrapped)
    tl = TopTools_ListOfShape()
    for t in shapes[1:]:
        tl.Append(t.wrapped)
    op = BRepAlgoAPI_Fuse()
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("fuzzy fuse failed")
    op.SimplifyResult()
    return _wrap(op.Shape())


def _wrap(topods):
    """Wrap a TopoDS result as a build123d Solid when it is one solid, else a Compound."""
    comp = bd.Compound(topods)
    solids = comp.solids()
    if len(solids) == 1:
        return solids[0]
    return comp


def sound(shape) -> bool:
    """Geometry gate for the big castings: OCCT-valid, BOP-valid, one or more
    positive-volume solids, closed shells per OCCT (the tool `cadgen step inspect
    validate` runs the authoritative version of this after export)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
    from OCP.BRep import BRep_Tool

    try:
        if shape is None or shape.wrapped is None or not shape.is_valid:
            return False
        solids = shape.solids()
        if not solids:
            return False
        for s in solids:
            if s.volume <= 1e-6:
                return False
            for sh in s.shells():
                if not BRep_Tool.IsClosed_s(sh.wrapped):
                    return False
        return BRepAlgoAPI_Check(shape.wrapped).IsValid()
    except Exception:
        return False
