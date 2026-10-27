"""Numeric bounds of OCCT boxes, without tessellating geometry."""


def box_limits(box) -> tuple[float, float, float, float, float, float]:
    """Return (xmin, ymin, zmin, xmax, ymax, zmax) of a non-void Bnd_Box.

    OCP 8 does not bind the Limits structure returned by Bnd_Box.Get().
    The two corner points expose the same bounds, including the box's gap.
    """
    low, high = box.CornerMin(), box.CornerMax()
    return low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z()
