"""Symmetric horn-arm outline shared by every recovered frame occurrence."""
import math
import build123d as bd
from lib.booleans import as_single_shape

HORN_ARM_TAPER_DEG = 0.0
HORN_CENTER_X_MM = -25.5
HORN_ENVELOPE_RADIUS_MM = 10.0


def taper_horn_arms(shape, angle_deg=HORN_ARM_TAPER_DEG):
    """Tangent straight sides blend into the existing circular horn envelope.

    Carry the trim through each horn bend and its wall land. The case-seat
    band, mounting bores, and all mating faces retain their datums.
    """
    if angle_deg == 0:
        return shape
    angle = math.radians(angle_deg)
    radius, xc = HORN_ENVELOPE_RADIUS_MM, HORN_CENTER_X_MM
    tangent_x = xc-radius*math.sin(angle)
    tangent_z = radius*math.cos(angle)
    xmin = -43.1598
    start_z = tangent_z+(xmin-tangent_x)*math.tan(angle)
    for ymin,ymax in ((0.,12.5496),(41.9152,60.)):
        for side in (-1,1):
            def p(x,z): return (x,ymin,side*z)
            arc_mid=p(xc-radius*math.sin(angle/2),radius*math.cos(angle/2))
            a,b,c,d,e=(p(xmin,60),p(xc,60),p(xc,radius),
                       p(tangent_x,tangent_z),p(xmin,start_z))
            wire=bd.Wire([bd.Edge.make_line(a,b),bd.Edge.make_line(b,c),
                          bd.Edge.make_three_point_arc(c,arc_mid,d),
                          bd.Edge.make_line(d,e),bd.Edge.make_line(e,a)])
            tool=bd.Solid.extrude(bd.Face(wire),(0,ymax-ymin,0))
            shape=as_single_shape(shape.cut(tool)).clean()
    if not shape.is_valid or len(shape.solids())!=1:
        raise ValueError('Tapered frame must be one valid solid')
    return shape
