"""Exact solid tendon and translucent reaction liner for cubic Bowden paths."""
from cadgen import build123d as bd,srgb
from lib.bowden_transport import cubic_derivative


def bezier_wire(path):
    return bd.Wire([bd.Edge.make_bezier(*s['points']) for s in path])


def make_bowden_body(path,label,liner=False):
    first=path[0]['points']
    plane=bd.Plane(origin=first[0],z_dir=cubic_derivative(first,0))
    profile=(bd.Circle(.45)-bd.Circle(.30)) if liner else bd.Circle(.30)
    shape=bd.sweep(plane*profile,path=bezier_wire(path),is_frenet=False)
    shape.label=label
    shape.color=srgb('#D5E7E5',alpha=.28) if liner else srgb('#C59852')
    shape.cad_material={'metalness':.05,'roughness':.30} if liner else {'metalness':.12,'roughness':.40}
    if not shape.is_valid or len(shape.solids())!=1 or shape.volume<=0:
        raise ValueError(f'{label}: invalid cubic swept body')
    return shape
