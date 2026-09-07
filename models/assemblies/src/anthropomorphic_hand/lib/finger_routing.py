"""Full eight-tendon finger-family path planner from the palm input datum.

The output is analytic swept-path data, all expressed in assembled world mm.
Every hand-joint crossing before the target uses an explicit reaction liner.
Fixed curved connectors are separate guide paths; they must have real bodies.
"""
from math import sin,cos,radians
import numpy as np
from scipy.optimize import brentq,minimize
from lib.layout import FINGERS,transforms,JOINT_BY_NAME
from lib.bowden_universal import bowden_universal,_length,_curvatures
from lib.bowden_mcp import mcp_crossover,OUTLET_DISTANCE
from lib.pip_transport import pip_transport
from lib.bowden_transport import cubic_point,cubic_derivative
from lib.axis_transport import point_at,tangent_at,segment_length

PALM_INPUT_Y=70.0
WRAP_DEG=150.0
def yaw_drive_plane(sign):
    return -9.5 if sign > 0 else -12.0
MIDDLE=next(f for f in FINGERS if f.name=='middle')
LANES={'pip_positive':3.,'pip_negative':-3.,'dip_positive':4.2,'dip_negative':-4.2}


def _point(m,p):return (m@np.array([*p,1.]))[:3].tolist()
def _vector(m,p):return (m[:3,:3]@np.array(p)).tolist()
def _shift(p,o):return [p[i]+o[i] for i in range(3)]


def transform_path(path,m,offset=(0,0,0)):
    result=[]
    for s in path:
        if s['kind']=='bezier':result.append({'kind':'bezier','points':[_point(m,_shift(p,offset)) for p in s['points']]})
        elif s['kind']=='line':result.append({'kind':'line','start':_point(m,_shift(s['start'],offset)),'end':_point(m,_shift(s['end'],offset))})
        else:result.append({'kind':'arc','center':_point(m,_shift(s['center'],offset)),
                            'axis':_vector(m,s['axis']),'start':_point(m,_shift(s['start'],offset)),'sweepDeg':s['sweepDeg']})
    return result


def endpoint(s,end=False):
    if s['kind']=='bezier':return s['points'][-1 if end else 0]
    return point_at(s,1 if end else 0)


def tangent(s,end=False):
    if s['kind']=='bezier':
        v=np.array(cubic_derivative(s['points'],1 if end else 0));return (v/np.linalg.norm(v)).tolist()
    return tangent_at(s,1 if end else 0)


def line(p0,p1):return {'kind':'line','start':list(p0),'end':list(p1)}


def connector(p0,p1):
    """Fixed connector with +Y end tangents; actual curved guide is mandatory."""
    p0=np.asarray(p0,dtype=float);p1=np.asarray(p1,dtype=float)
    handle=(p1[1]-p0[1])/3
    if handle<=0:raise ValueError('fixed finger connector must advance distally')
    return {'kind':'bezier','points':[p0.tolist(),(p0+[0,handle,0]).tolist(),(p1-[0,handle,0]).tolist(),p1.tolist()]}


from lib.yaw_transport import yaw_reaction_span


def terminal_arc(axis,radius,sign,angle_deg):
    if axis=='flex':
        center=[sign*.9,0,0];start=[sign*.9,0,sign*radius];ax=[1,0,0]
    elif axis=='yaw':
        center=[0,0,yaw_drive_plane(sign)];start=[-sign*radius,0,yaw_drive_plane(sign)];ax=[0,0,1]
    else:raise ValueError('unknown drive axis')
    return {'kind':'arc','center':center,'axis':ax,'start':start,
            'sweepDeg':-sign*WRAP_DEG+angle_deg}


def finger_routes(finger_name,pose=None):
    pose=dict(pose or {});fk=transforms(pose)
    f=next(f for f in FINGERS if f.name==finger_name);base=np.array([f.x,f.base_y,0.]);pip=base+np.array([0,f.lengths[0],0]);dip=pip+np.array([0,f.lengths[1],0])
    parent_name='palm_cup' if finger_name=='little' else 'wrist_flexion'
    input_y=f.base_y-35.
    pip_child_anchor=10. if finger_name=='little' else 12.25
    parent=fk[parent_name];yaw_frame=fk[f'{finger_name}_mcp_abduction'];prox=fk[f'{finger_name}_mcp_flexion'];mid=fk[f'{finger_name}_pip']
    yaw=pose.get(f'{finger_name}_mcp_abduction',0.);flex=pose.get(f'{finger_name}_mcp_flexion',0.);pipq=pose.get(f'{finger_name}_pip',0.)
    tendons=[]
    for target in ('mcp_abduction','mcp_flexion','pip','dip'):
        for sign,suffix in ((1,'positive'),(-1,'negative')):
            input_y=f.base_y-(12.25 if finger_name=='little' and target in('pip','dip') else 35.)
            name=f'{finger_name}_{target}_{suffix}';joint=f'{finger_name}_{target}';q=pose.get(joint,0.);groups=[]
            def append(label,path,frame,guide=None,neutralizes=()):
                group={'label':f'{name}_{label}','path':path,'frame':frame,'guide':guide,'neutralizes':list(neutralizes)}
                if guide=='snug_reaction_liner':
                    first=np.asarray(path[0]['points'])
                    group['working_length']=24.5 if label=='yaw_reaction' else 30.
                    group['length_correction']={'variable':'first_handle_length','segment':0,'control':1,
                        'anchor_control':0,'direction':'exact_inlet_tangent',
                        'initial_value':float(np.linalg.norm(first[1]-first[0])),
                        'preserves':'C1 joins, both anchored endpoint positions and tangents'}
                groups.append(group)
            if target=='mcp_abduction':
                arc=terminal_arc('yaw',5.5,sign,q)
                entry=np.array(arc['start'])+base
                source=entry.copy();source[1]=input_y
                append('palm_run',transform_path([line(source,entry)],parent),parent_name)
                append('drive_wrap',transform_path([arc],parent,base),parent_name,'drive_pulley')
            elif target=='mcp_flexion':
                neutral=yaw_reaction_span(yaw,sign)
                inlet=np.array(endpoint(neutral[0]))+base;source=inlet.copy();source[1]=input_y
                if np.linalg.norm(source-inlet)>1e-9:append('palm_run',transform_path([line(source,inlet)],parent),parent_name)
                append('yaw_reaction',transform_path(neutral,parent,base),'variable','snug_reaction_liner',(f'{finger_name}_mcp_abduction',))
                append('drive_approach',transform_path([line([sign*.9,-3.,sign*5.5],[sign*.9,0,sign*5.5])],yaw_frame,base),f'{finger_name}_mcp_abduction')
                append('drive_wrap',transform_path([terminal_arc('flex',5.5,sign,q)],yaw_frame,base),f'{finger_name}_mcp_abduction','drive_pulley')
            else:
                lane=LANES[f'{target}_{suffix}']
                neutral=mcp_crossover(flex,yaw,lane,cheek_inner=f.widths[0]/2-1.45)['path']
                inlet=np.array(endpoint(neutral[0]))+base;source=inlet.copy();source[1]=input_y
                if np.linalg.norm(source-inlet)>1e-9:append('palm_run',transform_path([line(source,inlet)],parent),parent_name)
                append('mcp_reaction',transform_path(neutral,parent,base),'variable','snug_reaction_liner',(f'{finger_name}_mcp_abduction',f'{finger_name}_mcp_flexion'))
                if target=='pip':
                    c=connector([lane,OUTLET_DISTANCE,0],[sign*.9,f.lengths[0]-3,sign*4.5])
                    append('proximal_guide',transform_path([c],prox,base),f'{finger_name}_mcp_flexion','fixed_curved_guide')
                    append('drive_approach',transform_path([line([sign*.9,-3,sign*4.5],[sign*.9,0,sign*4.5])],prox,pip),f'{finger_name}_mcp_flexion')
                    append('drive_wrap',transform_path([terminal_arc('flex',4.5,sign,q)],prox,pip),f'{finger_name}_mcp_flexion','drive_pulley')
                else:
                    append('proximal_run',transform_path([line([lane,OUTLET_DISTANCE,0],[lane,f.lengths[0]-12.25,0])],prox,base),f'{finger_name}_mcp_flexion')
                    pipneutral=pip_transport(pipq,lane,child_anchor=pip_child_anchor)['path']
                    append('pip_reaction',transform_path(pipneutral,prox,pip),'variable','snug_reaction_liner',(f'{finger_name}_pip',))
                    c=connector([lane,pip_child_anchor,0],[sign*.9,f.lengths[1]-3,sign*3.5])
                    if finger_name=='little':
                        c={'kind':'bezier','points':[[lane,10.,0.],[lane,14.,0.],[sign*.9,14.,sign*3.5],[sign*.9,18.,sign*3.5]]}
                    append('middle_guide',transform_path([c],mid,pip),f'{finger_name}_pip','fixed_curved_guide')
                    append('drive_approach',transform_path([line([sign*.9,-3,sign*3.5],[sign*.9,0,sign*3.5])],mid,dip),f'{finger_name}_pip')
                    append('drive_wrap',transform_path([terminal_arc('flex',3.5,sign,q)],mid,dip),f'{finger_name}_pip','drive_pulley')
            path=[s for group in groups for s in group['path']]
            tendons.append({'name':name,'joint':joint,'sign':sign,'groups':groups,'path':path,
                            'termination':endpoint(path[-1],True),'termination_frame':joint,
                            'moment_arm':sign*JOINT_BY_NAME[joint].drive_radius})
    return tendons


def middle_finger_routes(pose=None):
    return finger_routes('middle',pose)
