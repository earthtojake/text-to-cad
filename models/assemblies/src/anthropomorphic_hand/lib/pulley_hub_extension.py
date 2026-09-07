"""Turned captive PIP hub spacers. No groove or tendon datum is altered.

Two independent stainless collars occupy the exposed keyed shaft outside the
paired drums. Their round 2.06 mm running bores clear the 2 mm D shaft; the
existing drum and child eye capture them axially. The outboard face stops at
3.65 mm, before the independent DIP reaction liners at axial ±4.2 mm. External rounds are drawn
in the lathe section, with no coincident union cleanup.
"""
from cadgen import build123d as bd
from lib.finish import finish
from lib.layout import JOINT_BY_NAME,FINGERS,finger_fan_matrix
from lib.assembly import joint_location,matrix_location,Body


def collar():
    edges=[]
    def p(q):return (q[0],0,1.75+(q[1]-1.75)*.5)
    def line(a,b):edges.append(bd.Edge.make_line(p(a),p(b)))
    def bez(*pts):edges.append(bd.Edge.make_bezier(*[p(q) for q in pts]))
    line((1.03,1.83),(1.03,5.47))
    bez((1.03,5.47),(1.03,5.55),(1.11,5.55),(1.19,5.55))
    line((1.19,5.55),(2.06,5.55))
    bez((2.06,5.55),(2.20,5.55),(2.24,5.49),(2.24,5.35))
    line((2.24,5.35),(2.24,4.90))
    bez((2.24,4.90),(2.24,4.58),(2.82,4.32),(2.82,3.96))
    line((2.82,3.96),(2.82,2.86))
    bez((2.82,2.86),(2.82,2.52),(1.70,2.32),(1.70,1.98))
    bez((1.70,1.98),(1.70,1.82),(1.62,1.75),(1.46,1.75))
    line((1.46,1.75),(1.19,1.75))
    bez((1.19,1.75),(1.11,1.75),(1.03,1.75),(1.03,1.83))
    s=bd.revolve(bd.Face(bd.Wire(edges)),axis=bd.Axis.Z)
    assert s.is_valid and len(s.solids())==1
    return finish(s,'steel','turned_captive_hub_collar')


def representative_bodies():
    j=JOINT_BY_NAME['middle_pip'];f=next(f for f in FINGERS if f.name=='middle')
    placement=matrix_location(finger_fan_matrix(f))*joint_location(j)
    proto=collar();out=[]
    for sign in (-1,1):
        shape=placement*(bd.Rot(180,0,0) if sign<0 else bd.Pos())*proto
        shape.label=f'middle_pip_{"negative" if sign<0 else "positive"}_turned_hub_collar'
        out.append(Body(shape,j.name,j.system,'hub_spacer'))
    return out
