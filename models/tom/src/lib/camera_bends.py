"""Bend primitives and locked reference datums for the production camera mount."""
import math
import build123d as bd
from lib import camera_mount_interface as base
from lib.materials import ALUMINUM_5052_COLOR

T = base.T
RI = base.RI
RO = RI + T
WIDTH = base.FOOT_WIDTH
PANEL_SIZE = 35.0
PANEL_CENTER_S = PANEL_SIZE/2
PITCH_DEG = 25.0
ROOT_HEADING = math.pi/2
RISER_HEADING = math.radians(135)
PANEL_HEADING = math.radians(65)
# Measured on the downloaded official SO101 STL, in its native Y-up frame.
SO101_FRAME_CENTER = (2.50007659395,71.8603022749,-3.19070832468)
SO101_WRIST_TOP = 27.7817856
SO101_ROOT_FRONT = 11.95
CENTER_HEIGHT = SO101_FRAME_CENTER[1]-SO101_WRIST_TOP
CENTER_BACKSET = SO101_ROOT_FRONT-SO101_FRAME_CENTER[2]
U = math.sqrt(.5)
RISER_LENGTH = (-RI-RO*(1-U)+RI*(U-math.cos(math.radians(25)))
                +PANEL_CENTER_S*math.sin(math.radians(25))+CENTER_BACKSET)/U
ROOT_LENGTH = CENTER_HEIGHT-(T+RI+RO*U+RISER_LENGTH*U
                +RI*(U+math.sin(math.radians(25)))
                +PANEL_CENTER_S*math.cos(math.radians(25)))

def add(a,b,k=1):return tuple(x+k*y for x,y in zip(a,b))
def direction(a):return (0,math.cos(a),math.sin(a))
def normal(a):return (0,math.sin(a),-math.cos(a))

def bend_end(start,a,b,*,thickness=T,radius=RI):
    RI=radius;RO=radius+thickness
    sign=-1 if b<a else 1
    radius=RI if sign<0 else RO
    center=add(start,normal(a),-sign*radius)
    return add(center,normal(b),sign*radius)

def datums(lift=0.0):
    foot_end=(0,base.REAR_TANGENT_Y,T)
    root_start=bend_end(foot_end,math.pi,ROOT_HEADING)
    root_end=add(root_start,direction(ROOT_HEADING),ROOT_LENGTH+lift)
    riser_start=bend_end(root_end,ROOT_HEADING,RISER_HEADING)
    riser_end=add(riser_start,direction(RISER_HEADING),RISER_LENGTH)
    panel_start=bend_end(riser_end,RISER_HEADING,PANEL_HEADING)
    center=add(panel_start,direction(PANEL_HEADING),PANEL_CENTER_S)
    assert abs(center[2]-CENTER_HEIGHT-lift)<1e-8
    assert abs(center[1]-(base.REAR_TANGENT_Y-CENTER_BACKSET))<1e-8
    return foot_end,root_start,root_end,riser_start,riser_end,panel_start,center

def front_plane(point,a):
    return bd.Plane(origin=point,x_dir=(1,0,0),z_dir=tuple(-x for x in normal(a)))

def bend(start,a,b,width=WIDTH,*,thickness=T,radius=RI):
    RI=radius;RO=radius+thickness
    sign=-1 if b<a else 1
    front,back=(RI,RO) if sign<0 else (RO,RI)
    center=add(start,normal(a),-sign*front)
    def p(r,h):
        v=add(center,normal(h),sign*r)
        return (v[0]-width/2,v[1],v[2])
    mid=(a+b)/2
    wire=bd.Wire([
        bd.Edge.make_line(p(front,a),p(back,a)),
        bd.Edge.make_three_point_arc(p(back,a),p(back,mid),p(back,b)),
        bd.Edge.make_line(p(back,b),p(front,b)),
        bd.Edge.make_three_point_arc(p(front,b),p(front,mid),p(front,a))])
    return bd.extrude(bd.Face(wire),amount=width,dir=(1,0,0))

def straight(start,length,a,width=WIDTH,*,thickness=T):
    f=bd.Rectangle(width,length,align=(bd.Align.CENTER,bd.Align.MIN))
    return bd.extrude(f,amount=thickness).moved(front_plane(start,a).location)
