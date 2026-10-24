"""Horn-concentric cap and parallel neck, shared by frame and roll collars."""
import math
import build123d as bd


def circle_neck_outline(*, center, radius_mm, neck_width_mm, neck_start_mm,
                        along=(1, 0, 0), across=(0, 1, 0)):
    """A circular cap joins a constant-width inboard neck in the given plane.

    The circle follows the horn circumference to the exact neck intersection.
    Mounting bores, fork openings, sheet bends and root transitions belong to
    the caller and keep their existing datums.
    """
    half = neck_width_mm / 2
    if not 0 < half <= radius_mm:
        raise ValueError('Neck must fit within the circular horn cap')
    join = -math.sqrt(radius_mm**2 - half**2)
    if neck_start_mm >= join:
        raise ValueError('Neck must start inboard of its circle intersection')
    c, u, v = (bd.Vector(x) for x in (center, along, across))
    if abs(u.length-1) > 1e-8 or abs(v.length-1) > 1e-8 or abs(u.dot(v)) > 1e-8:
        raise ValueError('Horn profile axes must be orthonormal')
    def p(x, y):
        return c + u*x + v*y
    a, b = p(neck_start_mm, -half), p(join, -half)
    d, e = p(join, half), p(neck_start_mm, half)
    return bd.Wire([
        bd.Edge.make_line(a, b),
        bd.Edge.make_three_point_arc(b, p(radius_mm, 0), d),
        bd.Edge.make_line(d, e), bd.Edge.make_line(e, a),
    ])
