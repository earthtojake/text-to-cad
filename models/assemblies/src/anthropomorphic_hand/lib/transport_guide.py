"""Swept open guide shoes and full solid tendons for the axis crossover family."""
from math import cos, radians, sin
from cadgen import build123d as bd, srgb
from lib.axis_transport import (point_at, tangent_at, GUIDE_OUTER_RADIUS,
    GUIDE_INNER_RADIUS, TENDON_RADIUS)


def path_wire(path):
    edges=[]
    for segment in path:
        if segment['kind']=='bezier':
            edges.append(bd.Edge.make_bezier(*segment['points']))
        elif segment['kind']=='line':
            edges.append(bd.Edge.make_line(segment['start'],segment['end']))
        else:
            edges.append(bd.Edge.make_three_point_arc(segment['start'],point_at(segment,.5),point_at(segment,1)))
    return bd.Wire(edges)


def make_tendon(path,label='transport_tendon'):
    first=path[0]
    if first['kind']=='bezier':
        start=first['points'][0]
        direction=[first['points'][1][i]-start[i] for i in range(3)]
    else:
        start=first['start'];direction=tangent_at(first,0)
    profile=bd.Plane(origin=start,z_dir=direction)*bd.Circle(TENDON_RADIUS)
    result=bd.sweep(profile,path=path_wire(path),is_frenet=False)
    result.label=label
    result.color=srgb('#C99850')
    result.cad_material={'metalness':.15,'roughness':.42}
    if len(result.solids())!=1 or not result.is_valid:
        raise ValueError(f'{label}: invalid swept tendon')
    return result


def make_guide(segment,label='open_transport_guide'):
    """An open 240-degree annular channel, 0.2 wall and 0.05 rope gap.

    The C opening exposes the rope continuously. The circular profile envelope
    exactly matches the conservative all-pose transport clearance audit.
    Supports must be supplied by the final parent frame and separately checked.
    """
    def p(r,a):
        return (r*cos(radians(a)),r*sin(radians(a)),0)
    a,b=60,300
    ro,ri=GUIDE_OUTER_RADIUS,GUIDE_INNER_RADIUS
    edges=[bd.Edge.make_three_point_arc(p(ro,a),p(ro,180),p(ro,b)),
           bd.Edge.make_line(p(ro,b),p(ri,b)),
           bd.Edge.make_three_point_arc(p(ri,b),p(ri,180),p(ri,a)),
           bd.Edge.make_line(p(ri,a),p(ro,a))]
    profile=bd.Plane(origin=segment['start'],z_dir=tangent_at(segment,0))*bd.Face(bd.Wire(edges))
    result=bd.sweep(profile,path=path_wire([segment]),is_frenet=False)
    result.label=label
    result.color=srgb('#BAC8CE')
    result.cad_material={'metalness':.82,'roughness':.28}
    if len(result.solids())!=1 or not result.is_valid:
        raise ValueError(f'{label}: invalid swept open guide')
    return result
