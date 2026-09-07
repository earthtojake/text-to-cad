"""Three skeletal wrist frames, in assembled world coordinates.

Yaw is Z through (0,-9,0); flexion is X through (0,0,0).
Drive flats are +X for yaw and +Y for flexion. All dimensions millimetres.
"""
from cadgen import build123d as bd, srgb

WRIST_FOREARM_MOUNTS=tuple((x,-30.,z) for x in (-10.,10.) for z in (-9.,9.))
WRIST_PALM_MOUNTS=((-24.,14.,-10.2),(24.,14.,-10.2))


def _rib(points,radius=1.35):
    edge=bd.Edge.make_bezier(*points)
    return bd.sweep(bd.Plane(origin=edge.position_at(0),z_dir=edge.tangent_at(0))*bd.Circle(radius*.60),path=edge)


def _disk(center,radius,length,axis,bore=None,keyed=False):
    shape=bd.fillet(bd.Cylinder(radius,length).edges(),.25)
    if bore is not None:
        shape=shape-_bore((0,0,0),bore,length+2,'z',keyed)
        rims=[e for e in shape.edges() if e.bounding_box().size.Z<1e-7
              and abs(abs(e.center().Z)-length/2)<1e-6]
        shape=shape.fillet(.06,rims)
    if axis=='x':shape=bd.Rot(0,90,0)*bd.Rot(0,0,90)*shape
    elif axis=='y':shape=bd.Rot(90,0,0)*shape
    return bd.Pos(*center)*shape


def _bore(center,radius,length,axis,keyed=False):
    shape=bd.Cylinder(radius,length)
    if keyed:shape=shape-(bd.Pos(radius+2.25,0,0)*bd.Box(2*radius,2*radius+2,length+2))
    if axis=='x':shape=bd.Rot(0,90,0)*bd.Rot(0,0,90)*shape
    elif axis=='y':shape=bd.Rot(90,0,0)*shape
    return bd.Pos(*center)*shape


def _finish(pieces,bores,label):
    shape=pieces[0].fuse(*pieces[1:])
    if len(shape.solids())!=1:raise ValueError(f'{label}: disconnected {len(shape.solids())}')
    # A swept surface has a seam edge with only one adjacent face; it is
    # already smooth and must not be mistaken for an unblended junction.
    faces=list(shape.faces())
    roots=[]
    for edge in shape.edges():
        if edge.geom_type!=bd.GeomType.BSPLINE:continue
        adjacent=[f for f in faces if any(edge.is_same(fe) for fe in f.edges())]
        if len(adjacent)!=2:continue
        normals=[f.normal_at(edge.position_at(.5)) for f in adjacent]
        if abs(normals[0].dot(normals[1]))<.99999:roots.append(edge)
    roots.sort(key=lambda e:tuple(round(v,5) for v in e.center()))
    for edge in roots:
        current=next((candidate for candidate in shape.edges() if edge.is_same(candidate)),None)
        if current is not None:shape=shape.fillet(.03,[current])
    for args in bores:shape=shape-_bore(*args)
    if len(shape.solids())!=1 or not shape.is_valid:raise ValueError(f'{label}: invalid result, solids={len(shape.solids())}, valid={shape.is_valid}, volumes={[s.volume for s in shape.solids()]}')
    shape.label=label;shape.color=srgb('#a9b7c1')
    shape.cad_material={'metalness':.86,'roughness':.34,'clearcoat':.12}
    return shape


def make_wrist_fixed_fork(label='wrist_fixed_bearing_fork'):
    pieces=[];bores=[]
    for z in (-9.,9.):
        pieces.append(_disk((0,-9,z),6.5,3.,'z',5.03))
        bores.append(((0,-9,z),5.03,5.,'z',False))
        for x in (-10.,10.):
            pieces.append(_rib([(x*.41,-13.1,z),(x*.8,-17,z),(x,-23,z+(2.2 if z>0 else -2.2)),(x,-30,z+(2.2 if z>0 else -2.2))],1.5))
            pieces.append(_disk((x,-30,z),3.1,3.,'y',1.65))
            bores.append(((x,-30,z),1.65,5.,'y',False))
    for x in (-10.,10.):
        pieces.append(_rib([(x,-30,-6.5),(x,-34,-4),(x,-34,4),(x,-30,6.5)],1.5))
    pieces.append(_rib([(-7.5,-30,-9),(-4,-32,-9),(4,-32,-9),(7.5,-30,-9)],1.3))
    return _finish(pieces,bores,label)


def make_wrist_yaw_carrier(label='wrist_yaw_carrier'):
    pieces=[_disk((0,-9,0),4.5,3.,'z',3.03,True)]
    bores=[((0,-9,0),3.03,5.,'z',True)]
    for sign in (-1,1):
        x=sign*17.
        pieces.append(_disk((x,0,0),6.5,3.,'x',5.03))
        bores.append(((x,0,0),5.03,5.,'x',False))
        pieces.append(_rib([(sign*1.3,-12.3,0),(sign*8,-21,0),(x,-21,0),(x,-5.3,0)],1.4))
    return _finish(pieces,bores,label)


def make_wrist_palm_cradle(label='wrist_palm_cradle'):
    pieces=[];bores=[]
    for sign in (-1,1):
        x=sign*20.
        pieces.append(_disk((x,0,0),4.6,2.4,'x'))
        bores.append(((x,0,0),3.03,5.,'x',True))
        # Paired branches open a window at each ankle; both merge smoothly
        # into the palmar-side mounting shoe below the existing palm boss.
        pieces.append(_rib([(x,3.6,0),(sign*23,9,0),(sign*24,9,-7),(sign*24,14,-13.4)],1.35))
        pieces.append(_rib([(x,0,-3.6),(sign*23,2,-9),(sign*24,8,-14),(sign*24,14,-13.4)],1.35))
        pieces.append(_disk((sign*24,14,-13.4),3.3,2.4,'z'))
        bores.append(((sign*24,14,-13.4),1.65,6.,'z',False))
    # A shallow bowed dorsal bridge ties the ankle pair below the flex disk.
    pieces.append(_rib([(-24,14,-13.4),(-12,19,-16.5),(12,19,-16.5),(24,14,-13.4)],1.4))
    shape=_finish(pieces,bores,label)
    rims=[e for e in shape.edges() if e.geom_type==bd.GeomType.CIRCLE
          and any(abs(e.radius-r)<1e-6 for r in (3.03,))]
    shape=shape.fillet(.06,rims)
    # The negative keyed shaft head withdraws along -X outside the eye face.
    # Preserve the full D seat through X=-21.2 while clearing the lateral ribs.
    head_withdrawal=bd.Pos(-23.7,0,0)*bd.Rot(0,90,0)*bd.Cylinder(4.85,5.)
    shape=shape-head_withdrawal
    # Keep the ribs below each mounting shoe's planar top face. This leaves
    # the palm's complete M3 bore wall intact and a 0.4 mm spacer interface.
    for x in (-24.,24.):
        shape=shape-(bd.Pos(x,14,-10.2)*bd.Cylinder(3.5,4.0))
    shape.label=label;shape.color=srgb('#a9b7c1')
    shape.cad_material={'metalness':.86,'roughness':.34,'clearcoat':.12}
    return shape


def wrist_datums():
    return {'yaw_axis':((0.,-9.,0.),(0.,0.,1.)), 'flex_axis':((0.,0.,0.),(1.,0.,0.)),
            'forearm_mounts':WRIST_FOREARM_MOUNTS,'palm_mounts':WRIST_PALM_MOUNTS,
            'yaw_bearings':((0,-9,-9),(0,-9,9)),
            'flex_bearings':((-17,0,0),(17,0,0)), 'flex_keyed_eyes':((-20,0,0),(20,0,0))}


def make_wrist_bushings():
    """Four actual outward-flanged steel bushings, paired with their frames."""
    from .bushing import make_bushing
    result=[]
    for sign in (-1,1):
        b=make_bushing(5.,3.03,3.,5.45,.28,label=f'wrist_yaw_bushing_{sign}')
        result.append(('fixed',bd.Pos(0,-9,7.5)*b if sign>0 else bd.Pos(0,-9,-7.5)*bd.Rot(180,0,0)*b))
        b=make_bushing(5.,3.03,3.,5.45,.28,label=f'wrist_flex_bushing_{sign}')
        result.append(('yaw',bd.Pos(sign*15.5,0,0)*bd.Rot(0,sign*90,0)*b))
    return result
