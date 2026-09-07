"""Removable open side frames, split rail clamps and wiring provisions.

The two 1.8 mm side frames stay outside X±42.5 mm. Existing actuator, guide,
chassis and tendon geometry is immutable. All screws are nominal envelopes.
"""
from cadgen import build123d as bd, srgb
from .finish import finish
from .actuator_fasteners import socket_screw
from .forearm_frame import SIDE_RAIL_WIDTH,SIDE_RAIL_LENGTH,SIDE_RAIL_HEIGHT,SIDE_RAIL_CENTER_Y,SIDE_RAIL_FILLET

CLAMP_Y=(-264.,-69.)
ANCHOR_Y=(-215.,-135.)
EDGE_Z=(-44.5,44.5)


def _done(shape,kind,label):
    if len(shape.solids())!=1 or not shape.is_valid or shape.volume<=0:
        raise ValueError(f'{label}: expected one connected valid solid')
    return finish(shape,kind,label)


def _xcylinder(r,length,x,y,z):
    return bd.Pos(x,y,z)*bd.Cylinder(r,length,rotation=(0,90,0))


def _rail():
    s=bd.Box(SIDE_RAIL_WIDTH,SIDE_RAIL_LENGTH,SIDE_RAIL_HEIGHT)
    return bd.Pos(38,SIDE_RAIL_CENTER_Y,0)*bd.fillet(s.edges(),SIDE_RAIL_FILLET)


def _clamp(y):
    s=bd.Pos(39.4,y,0)*bd.Box(9.8,7,17)
    s=bd.fillet(s.edges(),.35)-_rail()
    for z in (-7.,7.):s=s-_xcylinder(.82,9.0,38.0,y,z)
    cap=s & (bd.Pos(31.225,y,0)*bd.Box(13.45,9,20))
    # The distal cap crosses the existing inter-row transverse brace. An
    # inward-open constant-section relief preserves straight-X withdrawal.
    cap=cap-bd.Pos(0,-67.5,0)*bd.Box(100,2.35,3.50)
    outer=s & (bd.Pos(43.525,y,0)*bd.Box(10.95,9,20))
    return outer,_done(cap,'dark','removable_split_rail_clamp_cap')


def make_side_frame():
    profile=bd.RectangleRounded(234,94,12)-bd.RectangleRounded(224,84,8)
    body=bd.Pos(42.5,-153.5,0)*bd.extrude(bd.Plane.YZ*profile,amount=1.8)
    body=bd.fillet(body.edges(),.30)
    caps=[]
    for y in CLAMP_Y:
        outer,cap=_clamp(y);caps.append(cap)
        bar=bd.Pos(43.4,y,0)*bd.Box(1.8,2.8,88)
        bar=bd.fillet(bar.edges(),.30)
        body=body.fuse(outer,bar)
    for z in EDGE_Z:
        body=body-_xcylinder(2.2,5,43.4,-253,z)
        for y in ANCHOR_Y:
            for dy in (-5.,5.):body=body-_xcylinder(.6,5,43.4,y+dy,z)
    return _done(body,'dark','open_anodized_forearm_side_frame'),caps


def make_cable_grommet():
    # Elastic double-lip insert, kept with the side panel in an exploded group.
    stem=bd.Cylinder(2.2,1.8)
    lips=[bd.Pos(0,0,z)*bd.Cylinder(2.8,.40) for z in (-1.1,1.1)]
    s=stem.fuse(*lips)-bd.Cylinder(1.3,4)
    s=bd.fillet(s.edges(),.10)
    # Ream the panel seat after rounding: a concave lip fillet otherwise adds
    # material outside the Ø4.4 stem inside the 1.8 mm panel thickness.
    seat=bd.Cylinder(4,1.8)-bd.Cylinder(2.2,2.0)
    s=s-seat
    s=_done(s,'dark','silicone_two_lip_cable_exit_grommet')
    s.color=srgb('#242a2b');s.cad_material={'roughness':.72,'metalness':0.0}
    return s


def make_tie_anchor():
    # Tangential 3 mm wide cable-tie passage, open along Z between two feet.
    outline=bd.RectangleRounded(5,13,1.2)-bd.Pos(.3,0)*bd.RectangleRounded(2.4,7,.6)
    s=bd.Pos(46.8,0,0)*bd.extrude(outline,amount=1.,both=True)
    s=bd.fillet(s.edges(),.15)
    for y in (-5.,5.):s=s-_xcylinder(.65,7,46.8,y,0)
    return _done(s,'dark','raised_open_cable_tie_anchor')


def forearm_housing_bodies():
    """Return 42 named (shape,'forearm','forearm',kind) occurrences."""
    side,caps=make_side_frame();grommet=make_cable_grommet();anchor=make_tie_anchor()
    clamp_screw=socket_screw(.8,7.8,1.3,1.1)
    anchor_screw=socket_screw(.6,6.2,1.05,.7)
    bodies=[]
    for sign in (-1,1):
        transform=bd.Rot(0,180 if sign<0 else 0,0)
        prefix='left' if sign<0 else 'right'
        def add(s,name,kind):
            s=transform*s;s.label=prefix+'_forearm_'+name
            bodies.append((s,'forearm','forearm',kind))
        add(side,'open_side_frame','housing')
        for i,(y,cap) in enumerate(zip(CLAMP_Y,caps),1):
            add(cap,f'rail_clamp_{i}_removable_cap','housing_clamp')
            for n,z in enumerate((-7.,7.),1):
                add(bd.Pos(34.5,y,z)*bd.Rot(0,-90,0)*clamp_screw,f'rail_clamp_{i}_M1p6_socket_screw_{n}','housing_fastener')
        for i,z in enumerate(EDGE_Z,1):
            add(bd.Pos(43.4,-253,z)*bd.Rot(0,90,0)*grommet,f'cable_exit_{i}_silicone_grommet','cable_grommet')
            for j,y in enumerate(ANCHOR_Y,1):
                add(bd.Pos(0,y,z)*anchor,f'edge_{i}_tie_anchor_{j}','cable_tie_anchor')
                for n,dy in enumerate((-5.,5.),1):
                    add(bd.Pos(49.3,y+dy,z)*bd.Rot(0,90,0)*anchor_screw,f'edge_{i}_tie_anchor_{j}_M1p2_socket_screw_{n}','housing_fastener')
    if len(bodies)!=42:raise ValueError('Expected42 open forearm housing bodies')
    return bodies


def forearm_housing_release_directions():
    """Neutral-world directions; elastic grommets stay grouped with panels."""
    result={}
    for body,_,_,kind in forearm_housing_bodies():
        side=-1. if body.label.startswith('left_') else 1.
        inward=kind=='housing_clamp' or ('rail_clamp_' in body.label and kind=='housing_fastener')
        result[body.label]=(side*(-1. if inward else 1.),0.,0.)
    return result
