"""Miniature pierced external retaining rings; axis Z, thickness centered at Z0.

The opening points along +X. For a shaft radius r the ring spans r-.17 to
r+.30 radially and +/-.12 axially. It seats at an axle's length-.6 datum,
leaving .01 radial and .04 axial clearance to the existing groove.
"""
from math import cos, sin, radians
from cadgen import build123d as bd
from .finish import finish


def make_retaining_ring(shaft_radius=1., label="polished_pierced_retaining_ring", opening_half_angle=20.):
    """A single spring-steel C ring with two real removal holes and soft edges."""
    r = float(shaft_radius)
    if r < 1:
        raise ValueError("retaining ring family requires shaft radius >=1 mm")
    outer, inner, thickness = r+.30, r-.17, .24
    ring = bd.Cylinder(outer, thickness)-bd.Cylinder(inner, thickness+1)
    # Wide clear opening; curved ears stay inside the strict outer envelope.
    a = radians(opening_half_angle)
    reach = 2*outer
    wedge = bd.Polygon((0, 0), (reach*cos(a), -reach*sin(a)),
                       (reach*cos(a), reach*sin(a)), align=None)
    ring -= bd.Pos(0,0,-1)*bd.extrude(wedge, amount=2)
    ring = bd.fillet(ring.edges().filter_by(bd.Axis.Z), radius=.13)
    # Two pierced removal ears. Angle scales to preserve identical local web
    # around each bore for the finger and wrist radii.
    mid = (outer+inner)/2
    hole_angle = a + .245/mid
    for sign in (-1,1):
        x,y = mid*cos(hole_angle), sign*mid*sin(hole_angle)
        ring -= bd.Pos(x,y,0)*bd.Cylinder(.105, thickness+1)
    ring = bd.fillet(ring.edges(), radius=.025)
    if len(ring.solids()) != 1 or not ring.is_valid or ring.volume <= 0:
        raise ValueError(f"{label}: retaining ring is not one valid positive solid")
    return finish(ring,"steel",label)
