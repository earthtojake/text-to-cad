"""Placements a STEP reader rebuilds as the result places them.

An occurrence's token hashes its placement rounded to fixed quanta (``tree_tokens``). A STEP
file states a placement as OCCT writes it -- an origin and two directions
(``GeomToStep_MakeAxis2Placement3d``), each coordinate a real as the writer prints it
(``step_reals``) -- from which a reader rebuilds the transformation. A translation is read
exactly as stated, and a token rounds a translation as stated, so no translation is read as
another token. A rotation entry is rebuilt from the two stated directions, and about
one placement in five hundred turned at a general angle has an entry that rounds otherwise
once rebuilt.

:func:`as_read` computes what a reader rebuilds, with the reader's own classes in the
reader's own order, so it is exact. :func:`readable_placement` gives the placement a named
file writes: the one given, unless a rotation entry would be read rounding otherwise; then
the first turn of the given placement about its own origin, by at most a picoradian -- one
stated digit of a unit direction -- that is read rounding as given. Nothing else moves.
"""

from __future__ import annotations

from typing import Any

# The turns tried, in radians, smallest first, each about each of these axes both ways: none
# more than one stated digit (1e-12) of a unit direction. Of 120,000 placements turned at
# random, the 232 whose rotation was read as another token were each kept by one of them.
_TURNS = (1e-13, 3e-13, 5e-13, 1e-12)
_AXES = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, -1, 0), (1, 0, 1), (1, 0, -1), (0, 1, 1), (0, 1, -1),
         (1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1))


def as_read(trsf: Any) -> tuple[float, ...]:
    """The twelve placement numbers (row-major, translation last in each row) a reader
    rebuilds from the placement OCCT writes for ``trsf``, a ``gp_Trsf``: the axis placement
    the writer states, each real as printed, rebuilt as ``StepToGeom`` rebuilds it (each
    direction a ``Geom_Direction``, the axes a ``Geom_Axis2Placement``) and placed as
    ``STEPControl_ActorRead`` places it (``SetTransformation`` from the identity frame)."""
    from OCP.Geom import Geom_Axis2Placement, Geom_Direction
    from OCP.GeomToStep import GeomToStep_MakeAxis2Placement3d
    from OCP.gp import gp_Ax2, gp_Ax3, gp_Pnt, gp_Trsf

    from cadgen._internal.step_reals import stated_real

    written = GeomToStep_MakeAxis2Placement3d(trsf).Value()
    point = written.Location().Coordinates()
    axis = written.Axis().DirectionRatios()
    reference = written.RefDirection().DirectionRatios()
    origin = gp_Pnt(*(stated_real(point.Value(i)) for i in range(1, 4)))
    stated_axis = Geom_Direction(*(stated_real(axis.Value(i)) for i in range(1, 4))).Dir()
    stated_reference = Geom_Direction(*(stated_real(reference.Value(i)) for i in range(1, 4))).Dir()
    target = gp_Ax3(Geom_Axis2Placement(gp_Ax2(origin, stated_axis, stated_reference)).Ax2())
    rebuilt = gp_Trsf()
    rebuilt.SetTransformation(target, gp_Ax3())
    return tuple(rebuilt.Value(row, column) for row in range(1, 4) for column in range(1, 5))


def readable_placement(trsf: Any) -> Any:
    """The ``gp_Trsf`` a named file writes for an occurrence placed by ``trsf``: ``trsf``
    itself when every entry a reader rebuilds rounds as ``trsf``'s does
    (``tree_tokens.rounded_placement``), as every translation does; else the first turn of
    ``trsf`` about its own origin, by at most a picoradian, that does; else ``trsf`` (a
    reader's token then differs, which verifying the file reports)."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf

    from cadgen._internal.tree_tokens import rounded_placement

    try:
        target = rounded_placement([trsf.Value(row, column) for row in range(1, 4) for column in range(1, 5)])
        if rounded_placement(list(as_read(trsf))) == target:
            return trsf
        for turn in _TURNS:
            for axis in _AXES:
                for sign in (1, -1):
                    twist = gp_Trsf()
                    twist.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), sign * turn)
                    candidate = trsf.Multiplied(twist)
                    if rounded_placement(list(as_read(candidate))) == target:
                        return candidate
    except Exception:  # noqa: BLE001 - a placement OCCT cannot state as an axis placement is written as given
        return trsf
    return trsf
