"""Upstream-only open reaction-mouth clamps clear of the flexion drive drums.

The C mouths expose the drum-facing120degrees. Their plane is the accepted
liner outlet; all metal extends upstream, preserving the3mm drive approach.
"""
from math import cos,sin,radians
import numpy as np
from cadgen import build123d as bd
from lib.guide_mounts import _finish,_sweep
from lib.universal_carrier import make_universal_carrier
from lib.layout import FINGERS,finger_fan_matrix
from lib.finish import finish


def _cross_screw(center,diameter,length,label):
    r=diameter/2;headr=diameter*.80;headh=diameter*.75
    sh=bd.Cylinder(r,length)
    head=bd.Pos(0,0,length/2+headh/2)*bd.Cylinder(headr,headh)
    socket=bd.Pos(0,0,length/2+headh)*bd.extrude(bd.RegularPolygon(diameter*.34,6),amount=-headh*.65)
    result=sh.fuse(head)-socket
    return finish(_finish(bd.Pos(*center)*bd.Rot(0,90,0)*result,label),'steel',label)


def _mouth(sign,label):
    if sign<0:
        lower,cap,screw=_mouth(1,label)
        return (bd.Rot(0,180,0)*cap,
                _finish(bd.Rot(0,180,0)*lower,label+'_outer_jaw'),
                bd.Rot(0,180,0)*screw)
    x=sign*.9;y=-3;z=sign*5.5
    def p(r,a):return (r*cos(radians(a)),r*sin(radians(a)),0)
    edges=[bd.Edge.make_three_point_arc(p(.57,-30),p(.57,90),p(.57,210)),
           bd.Edge.make_line(p(.57,210),p(.49,210)),
           bd.Edge.make_three_point_arc(p(.49,210),p(.49,90),p(.49,-30)),
           bd.Edge.make_line(p(.49,-30),p(.57,-30))]
    with bd.BuildSketch() as section:
        bd.add(bd.Face(bd.Wire(edges)))
        for side in (-1,1):
            with bd.Locations((side*.2825,.84)):
                bd.RectangleRounded(.485,.88,.07)
        bd.Circle(.49,mode=bd.Mode.SUBTRACT)
    face=bd.Plane(origin=(x,y,z),x_dir=(1,0,0),z_dir=(0,-1,0))*section.sketch
    raw=bd.extrude(face,amount=.55,dir=(0,-1,0))
    parts=[]
    for side in (-1,1):
        half=raw & (bd.Pos(x+side*2.04,y,z)*bd.Box(4,3,4))
        hole=bd.Pos(x,y-.275,z+.95)*bd.Cylinder(.22,3,rotation=(0,90,0))
        parts.append(half-hole)
    screw=_cross_screw((x,y-.275,z+sign*.95),.4,1.05,label+'_M0p4_pinch_screw')
    return parts[0],_finish(parts[1],label+'_outer_jaw'),screw


def _hub_clamp(host,sign,label,delta=0):
    z=(9.5 if sign>0 else -13.7)+sign*delta
    if sign>0:
        outer=bd.SlotOverall(5.70,4.90,rotation=90)
        inner=bd.SlotOverall(5.44,4.64,rotation=90)
    else:outer=bd.Circle(2.95);inner=bd.Circle(2.72)
    raw=bd.Pos(0,0,z-.35)*bd.extrude(outer-inner,amount=.7)
    halves=[]
    for side in (-1,1):
        h=raw & (bd.Pos(side*5.04,0,z)*bd.Box(10,10,3))
        for y in (-3.5,3.5):
            lug=bd.Pos(side*.40,y,z)*bd.Cylinder(.50,.50,rotation=(0,90,0))
            neck=bd.Pos(side*.43,np.sign(y)*2.98,z)*bd.Box(.7,1.04,.7)
            h=h.fuse(lug,neck)
            h=h-(bd.Pos(0,y,z)*bd.Cylinder(.32,3,rotation=(0,90,0)))
        halves.append(h-host)
    screws=[_cross_screw((0,y,z),.6,1.30,label+('_posterior' if y<0 else '_anterior')+'_M0p6_screw') for y in (-3.5,3.5)]
    return halves[0],halves[1],screws


def make_yaw_reaction_mounts(width=18,label='mcp',radius=5.5,yaw_plane=8.,negative_bow_y=-7.3):
    host=make_universal_carrier(phalanx_width=width,yaw_plane=yaw_plane)
    delta=radius-5.5
    from copy import deepcopy
    prototype=_mouth(1,label+'_positive_yaw_outlet')
    parts=[]
    for sign in (-1,1):
        name=label+('_positive' if sign>0 else '_negative')+'_yaw_outlet'
        if sign>0:mouth,cap,screw=map(deepcopy,prototype)
        else:
            a,b,s=map(deepcopy,prototype)
            mouth=bd.Rot(0,180,0)*a
            cap=_finish(bd.Rot(0,180,0)*b,name+'_outer_jaw')
            screw=bd.Rot(0,180,0)*s;screw.label=name+'_M0p4_pinch_screw'
        mouth=bd.Pos(0,0,sign*delta)*mouth
        cap=bd.Pos(0,0,sign*delta)*cap
        screw=bd.Pos(0,0,sign*delta)*screw
        hub,hubcap,bolts=_hub_clamp(host,sign,name+'_hub_clamp',delta)
        if sign<0:hub,hubcap=hubcap,hub
        if sign>0:
            paths=[[(.62,-3.275,6.40),(.62,-3.4,7.3),(-.4,-3.5,8.7),(-.4,-3.5,9.5)]]
        else:
            paths=[[(-.62,-3.275,-6.40),(1.8,-3.275,-6.40),(1.8,negative_bow_y,-7.2),
                    (1.8,negative_bow_y,-8.2),(1.8,negative_bow_y,-12.0),(1.8,negative_bow_y,-15.4),
                    (1.8,-3.5,-15.4),(.4,-3.5,-13.7)]]
        paths=[[(x,y,z+sign*delta) for x,y,z in points] for points in paths]
        wire=bd.Wire([bd.Edge.make_bezier(*points) for points in paths])
        arm=bd.sweep(bd.Plane(origin=paths[0][0],z_dir=wire.tangent_at(0))*bd.Circle(.24),path=wire)
        body=mouth.fuse(hub,arm)-host
        # The narrow open mouths have a dedicated cross screw bore.
        body=body-(bd.Pos(sign*.9,-3.275,sign*(6.45+delta))*bd.Cylinder(.22,3,rotation=(0,90,0)))
        for y in (-3.5,3.5):body=body-(bd.Pos(0,y,(9.5 if sign>0 else -13.7)+sign*delta)*bd.Cylinder(.32,3,rotation=(0,90,0)))
        # A pre-existing carrier branch divides the negative hub clamp.
        # Preserve each fitted segment as a real body; the opposing jaw and
        # the two cross bolts capture the segments without crossing the host.
        if label.startswith('index_') and sign>0:
            import json
            from pathlib import Path
            relief=json.loads(Path(__file__).with_name('yaw_guide_relief.json').read_text())
            for seg in relief['path']:
                edge=bd.Edge.make_bezier(*seg['points'])
                tool=bd.sweep(bd.Plane(origin=edge.position_at(0),z_dir=edge.tangent_at(0))*bd.Circle(relief['cut_radius']),path=edge)
                hubcap=hubcap-tool
        for mate in [screw,*bolts]:body=body-mate;hubcap=hubcap-mate
        for role,shape in (('structural_jaw',body),('hub_right_jaw',hubcap)):
            solids=list(shape.solids())
            for i,solid in enumerate(solids):
                suffix='_'+str(i+1) if len(solids)>1 else ''
                parts.append(_finish(solid,name+'_'+role+suffix))
        parts.extend([cap,screw,*bolts])
    return parts


def yaw_reaction_mounts(finger_names=None):
    from lib.assembly import matrix_location
    out=[]
    for f in FINGERS:
        if finger_names and f.name not in finger_names:continue
        placement=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)
        for part in make_yaw_reaction_mounts(f.widths[0],f.name+'_mcp'):
            out.append((placement*part,f.name+'_mcp_abduction',f.name,'guide_mount'))
    return out
