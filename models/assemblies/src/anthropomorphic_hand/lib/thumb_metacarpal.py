"""Thumb metacarpal: 36 mm keyed CMC-to-MCP transition, local +Y.

Four slender curved machined load paths surround a broad uninterrupted window.
The distal fixed bearing eyes run along Z rather than the X pin eyes used by
ordinary phalanges. No member crosses the central six-liner corridor.
"""
from cadgen import build123d as bd, srgb
from .phalanx import _drive_bore

LENGTH=36.
WIDTH=19.
PALMAR_SUPPORT_Z=12.5
DORSAL_SUPPORT_Z=-16.5


def metacarpal_datums():
    return {'cmc_flex': {'origin':(0.,0.,0.),'axis':(1.,0.,0.)},
            'mcp_yaw': {'origin':(0.,LENGTH,0.),'axis':(0.,0.,1.)},
            'palmar_bearing': {'origin':(0.,LENGTH,PALMAR_SUPPORT_Z),'axis':(0.,0.,1.)},
            'dorsal_bearing': {'origin':(0.,LENGTH,DORSAL_SUPPORT_Z),'axis':(0.,0.,1.)},
            'length':LENGTH,'proximal_width':WIDTH}


def make_thumb_metacarpal(label='thumb_metacarpal'):
    x=WIDTH/2-.725
    pieces=[]
    for sign in (-1,1):
        eye=bd.Cylinder(3.55,1.45)
        eye=bd.fillet(eye.edges(),.20)
        placement=bd.Pos(sign*x-.725,0,0)*bd.Rot(0,0,90)*bd.Rot(90,0,0)
        # _drive_bore is native sketch-X flat at +0.75; placement maps it to +Y.
        eye=bd.Pos(sign*x,0,0)*bd.Rot(0,90,0)*eye
        eye=eye-(placement*_drive_bore(1.03,.75))
        rims=[e for e in eye.edges() if e.bounding_box().size.X<1e-6
              and abs(e.center().Y)<1.04 and abs(e.center().Z)<1.04]
        eye=bd.fillet(rims,.10)
        pieces.append(eye)
    for z in (PALMAR_SUPPORT_Z,DORSAL_SUPPORT_Z):
        ring=bd.Cylinder(3.75,2.)-bd.Cylinder(2.53,4.)
        pieces.append(bd.Pos(0,LENGTH,z)*bd.fillet(ring.edges(),.18))
        sign=1 if z>0 else -1
        for side in (-1,1):
            points=[(side*x,1.1,sign*2.2),
                    (side*(x-1.5),1.1,sign*2.2),
                    (side*(x-1.5),7.5,sign*9.5),
                    (side*x,20.,z+sign*4.5),
                    (side*7.5,31.,z+sign*4.),
                    (side*3.14,36.,z+sign*3.),
                    (side*3.14,36.,z)]
            path=bd.Edge.make_bezier(*points)
            section=bd.Plane(origin=points[0],z_dir=path.tangent_at(0))*bd.Ellipse(.65,.48)
            pieces.append(bd.sweep(section,path=path))
    shape=pieces[0].fuse(*pieces[1:])
    if len(shape.solids())!=1:
        raise ValueError(f'{label}: expected one solid, got {len(shape.solids())}')
    roots=[e for e in shape.edges() if e.geom_type==bd.GeomType.BSPLINE
           and .8<e.length<6.5 and (e.center().Y<4 or e.center().Y>32)]
    if not roots:raise ValueError(f'{label}: root edges absent')
    shape=bd.fillet(roots,.10)
    # Reopen the two distal seats after the ribs blend into their bosses.
    for z in (PALMAR_SUPPORT_Z,DORSAL_SUPPORT_Z):
        shape=shape-(bd.Pos(0,LENGTH,z)*bd.Cylinder(2.53,4.5))
    shape.label=label
    shape.color=srgb('#a9b7c1')
    shape.cad_material={'roughness':.34,'metalness':.86,'clearcoat':.12}
    if not shape.is_valid or shape.volume<=0:raise ValueError(f'{label}: invalid solid')
    return shape
