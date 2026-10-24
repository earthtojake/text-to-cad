"""Shared tapered-link aperture geometry for the arm and pattern review."""
import math
import build123d as b
from lib.tapered_solid_links import side_faces
RAIL=6.

def clip(poly,a,c,d):
    """Clip convex 2D polygon to a*x+c*z <= d."""
    out=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        u=a*p[0]+c*p[1]-d;v=a*q[0]+c*q[1]-d
        if u<=1e-9:out.append(p)
        if (v>1e-9 and u<-1e-9) or (u>1e-9 and v<-1e-9):
            t=u/(u-v);out.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
    return out


def offset(poly,margin):
    out=list(poly)
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dx,dz=q[0]-p[0],q[1]-p[1]
        out=clip(out,dz,-dx,dz*p[0]-dx*p[1]-margin*math.hypot(dx,dz))
    return out


def geometry(p,upper):
    """Extract the usable wall and web from this saved plate, not old datums."""
    flats=[f for f in p.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999]
    web=max(flats,key=lambda f:f.area).bounding_box()
    wall=side_faces(p)[0]
    diag=max((e for e in wall.edges() if e.geom_type==b.GeomType.LINE
              and e.bounding_box().size.X>60 and e.bounding_box().size.Z>5),key=lambda e:e.length)
    ends=sorted((v.center() for v in diag.vertices()),key=lambda q:q.X)
    a,c=ends;slope=(c.Z-a.Z)/(c.X-a.X)
    levels=[e.center().Z for e in wall.edges() if e.geom_type==b.GeomType.LINE
            and e.bounding_box().size.X>60 and e.bounding_box().size.Z<1e-5]
    tangent=min(levels) if upper else max(levels)
    x0,x1=web.min.X,web.max.X
    points=[x0]+[q.X for q in ends if x0+1e-5<q.X<x1-1e-5]+[x1]
    z=lambda x:min(c.Z,a.Z+slope*(x-a.X)) if upper else max(a.Z,a.Z+slope*(x-a.X))
    poly=([(x0,tangent),(x1,tangent)]+[(x,z(x)) for x in reversed(points)]) if upper else ([(x,z(x)) for x in points]+[(x1,tangent),(x0,tangent)])
    # Drop redundant collinear points before offset/fillet operations.
    changed=True
    while changed:
        changed=False
        for i in range(len(poly)):
            prev,q,nxt=poly[i-1],poly[i],poly[(i+1)%len(poly)]
            cross=(q[0]-prev[0])*(nxt[1]-q[1])-(q[1]-prev[1])*(nxt[0]-q[0])
            if abs(cross)<1e-7:
                poly.pop(i);changed=True;break
    roof=[(x0,web.min.Y),(x1,web.min.Y),(x1,web.max.Y),(x0,web.max.Y)]
    # Either horizontal web face is an acceptable envelope; cut through both.
    web_z=web.min.Z
    return poly,roof,slope,tangent,web_z


def face(poly,r):
    f=b.Face(b.Wire.make_polygon([(x,z,0) for x,z in poly],close=True))
    return f.fillet_2d(r,f.vertices())


def section(poly,x):
    zs=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        if abs(q[0]-p[0])<1e-8:
            if abs(x-p[0])<1e-7:zs.extend((p[1],q[1]))
        elif min(p[0],q[0])-1e-7<=x<=max(p[0],q[0])+1e-7:
            t=(x-p[0])/(q[0]-p[0]);zs.append(p[1]+t*(q[1]-p[1]))
    assert zs,(poly,x)
    return min(zs),max(zs)
