"""Short solid-metal jaws, preserving the existing case/horn mounting ends.

50 mm contact faces, centered 7 mm blunt noses, existing stock and bend radii.
The fixed face root determines the inward angle; the moving face mirrors it.
The complete channel is shortened; outer cheek edges are straightened without
adding bends or disturbing mounting holes.
"""
from __future__ import annotations
import math
import build123d as b
from lib.booleans import as_single_shape as one

FACE_LENGTH = 50.0
THICKNESS = 2.032

def convex_outline(points):
    pts=sorted(set(points))
    def cross(o,a,c):return (a[0]-o[0])*(c[1]-o[1])-(a[1]-o[1])*(c[0]-o[0])
    chains=[]
    for sequence in (pts,list(reversed(pts))):
        chain=[]
        for v in sequence:
            while len(chain)>=2 and cross(chain[-2],chain[-1],v)<=1e-10:chain.pop()
            chain.append(v)
        chains.append(chain[:-1])
    return chains[0]+chains[1]

def box(lo,hi):
    return b.Solid.make_box(*(v-u for u,v in zip(lo,hi)),b.Plane(origin=lo))

def contact_face(part,moving):
    return max((f for f in part.faces() if f.geom_type==b.GeomType.PLANE
                and abs(f.normal_at().Z)<1e-6
                and f.normal_at().Y*(-1 if moving else 1)>.95),key=lambda f:f.area)

def datums(part,moving):
    f=contact_face(part,moving);vs=[v.center() for v in f.vertices()]
    x0=min(p.X for p in vs);x1=max(p.X for p in vs)
    tip=sum((p for p in vs if abs(p.X-x0)<1e-6),b.Vector())/sum(abs(p.X-x0)<1e-6 for p in vs)
    root=sum((p for p in vs if abs(p.X-x1)<1e-6),b.Vector())/sum(abs(p.X-x1)<1e-6 for p in vs)
    # The wider moving web has unequal historic Z lands. Use its pinch Z datum.
    root=b.Vector(root.X,root.Y,tip.Z)
    direction=(root-tip).normalized();length=(root-tip).length
    return f,tip,root,direction,length

def shorten(part,moving):
    label,color=part.label,part.color
    assert len(part.solids())==1
    part=part.solids()[0]
    part.label,part.color=label,color
    face,tip,root,direction,old_length=datums(part,moving)
    assert abs(old_length-60)<1e-5,(part.label,old_length)
    removed=old_length-FACE_LENGTH
    new_tip=b.Vector(root.X-math.sqrt(FACE_LENGTH**2-root.Y**2),0,tip.Z)
    new_direction=(root-new_tip).normalized()
    turn=math.degrees(math.atan2(new_direction.Y,new_direction.X)-math.atan2(direction.Y,direction.X))
    axis=b.Axis(root,(0,0,1))
    local=b.Plane(origin=tip,x_dir=direction,z_dir=(0,0,1)).location
    # Splice the complete constant channel section so web, bends and cheeks
    # remain connected; retain a 1 mm coplanar overlap at the mounting lands.
    split=25.0
    front=one(part.intersect(box((-600,-300,-100),(root.X+3,300,400))))
    back=one(part.intersect(box((root.X+2,-300,-100),(400,300,400))))
    q=front.moved(local.inverse())
    nose=one(q.intersect(box((-200,-200,-200),(split,200,200)))).moved(b.Pos(removed,0,0))
    base=one(q.intersect(box((split+removed,-200,-200),(300,200,200))))
    front=one(nose.fuse(base)).clean().moved(local).rotate(axis,turn)
    # The original cheeks taper slightly. Fill the tiny steps left by removing
    # a longitudinal band, keeping uninterrupted straight outer edges.
    bb=front.bounding_box();fills=[]
    for z,dz in [(bb.min.Z,THICKNESS),(bb.max.Z,-THICKNESS)]:
        faces=[f for f in front.faces() if f.geom_type==b.GeomType.PLANE
               and abs(f.normal_at().Z)>.999 and abs(f.center().Z-z)<1e-5]
        xy=[(v.center().X,v.center().Y) for f in faces for v in f.vertices()]
        assert xy
        wire=b.Wire.make_polygon([(x,y,z) for x,y in convex_outline(xy)],close=True)
        fills.append(b.Solid.extrude(b.Face(wire),(0,0,dz)))
    front=one(front.fuse(*fills)).clean()
    result=one(front.fuse(back)).clean()
    assert result.is_valid and len(result.solids())==1,(label,result.is_valid,len(result.solids()))
    result.label=label;result.color=color
    return result
