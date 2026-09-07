"""Six thumb routes from CMC reaction outlets to MCP and IP terminations.

Geometry is expressed in the neutral CMC-flexion child frame, with MCP atY36.
CMC packet integration and whole-thumb validation remain separate.
"""
from math import radians,cos,sin
import numpy as np
from lib.finger_routing import connector,line,terminal_arc,transform_path,endpoint
from lib.yaw_transport import yaw_reaction_span
from lib.bowden_mcp import mcp_crossover


def rotation(axis,q):
    a=radians(q);c,s=cos(a),sin(a);m=np.eye(4)
    m[:3,:3]=[[1,0,0],[0,c,-s],[0,s,c]] if axis=='x' else [[c,-s,0],[s,c,0],[0,0,1]]
    return m


def about(m,point):
    out=m.copy();point=np.asarray(point);out[:3,3]=point-m[:3,:3]@point
    return out


def downstream_transforms(pose=None):
    pose=dict(pose or {});base=np.array([0.,36.,0.]);ip=base+[0,27,0]
    yaw=about(rotation('z',pose.get('thumb_mcp_abduction',0)),base)
    flex=yaw@about(rotation('x',pose.get('thumb_mcp_flexion',0)),base)
    distal=flex@about(rotation('x',pose.get('thumb_ip',0)),ip)
    return {'thumb_cmc_flexion':np.eye(4),'thumb_mcp_abduction':yaw,'thumb_mcp_flexion':flex,'thumb_ip':distal}


def thumb_downstream_routes(pose=None,short_mcp_yaw=False):
    pose=dict(pose or {});fk=downstream_transforms(pose);base=np.array([0.,36.,0.]);ip=base+[0,27,0]
    yaw=pose.get('thumb_mcp_abduction',0.);flex=pose.get('thumb_mcp_flexion',0.);ipq=pose.get('thumb_ip',0.)
    routes=[]
    for target in ('mcp_abduction','mcp_flexion','ip'):
        for sign,suffix in ((1,'positive'),(-1,'negative')):
            name=f'thumb_{target}_{suffix}';groups=[]
            def add(label,path,frame,guide=None,neutralizes=()):
                group={'label':f'{name}_{label}','path':path,'frame':frame,'guide':guide,'neutralizes':list(neutralizes)}
                if guide=='snug_reaction_liner':
                    first=np.asarray(path[0]['points']);group['working_length']=(20.5 if short_mcp_yaw else 24.5) if label=='mcp_yaw_reaction' else 30.
                    group['length_correction']={'variable':'first_handle_length','segment':0,'control':1,'anchor_control':0,'direction':'exact_inlet_tangent','initial_value':float(np.linalg.norm(first[1]-first[0]))}
                groups.append(group)
            if target=='mcp_abduction':
                plane=-9.5 if sign>0 else -12.
                start=np.array([sign*3.,12.25,0.]);end=np.array([-sign*5.5,33.,plane])
                a,b=(8.,6.5) if sign>0 else (6.5,8.)
                staggered={'kind':'bezier','points':[start.tolist(),(start+[0,a,0]).tolist(),(end-[0,b,0]).tolist(),end.tolist()]}
                add('metacarpal_guide',[staggered],'thumb_cmc_flexion','fixed_curved_guide')
                add('drive_approach',[line([-sign*5.5,33,plane],[-sign*5.5,36,plane])],'thumb_cmc_flexion')
                add('drive_wrap',transform_path([terminal_arc('yaw',5.5,sign,yaw)],np.eye(4),base),'thumb_cmc_flexion','drive_pulley')
            elif target=='mcp_flexion':
                if short_mcp_yaw:
                    from lib.thumb_mcp_yaw_transport import thumb_mcp_yaw_reaction_span
                    reaction=thumb_mcp_yaw_reaction_span(yaw,sign)
                else:reaction=yaw_reaction_span(yaw,sign)
                add('mcp_yaw_reaction',transform_path(reaction,np.eye(4),base),'variable','snug_reaction_liner',('thumb_mcp_abduction',))
                add('drive_approach',transform_path([line([sign*.9,-3,sign*5.5],[sign*.9,0,sign*5.5])],fk['thumb_mcp_abduction'],base),'thumb_mcp_abduction')
                add('drive_wrap',transform_path([terminal_arc('flex',5.5,sign,flex)],fk['thumb_mcp_abduction'],base),'thumb_mcp_abduction','drive_pulley')
            else:
                add('metacarpal_guide',[connector([sign*5.4,12.25,0],[sign*4.2,23.75,0])],'thumb_cmc_flexion','fixed_curved_guide')
                packet=mcp_crossover(flex,yaw,sign*4.2,cheek_inner=6.55)
                add('mcp_reaction',transform_path(packet['path'],np.eye(4),base),'variable','snug_reaction_liner',('thumb_mcp_abduction','thumb_mcp_flexion'))
                add('proximal_guide',transform_path([connector([sign*4.2,12.25,0],[sign*.9,24,sign*3.5])],fk['thumb_mcp_flexion'],base),'thumb_mcp_flexion','fixed_curved_guide')
                add('drive_approach',transform_path([line([sign*.9,-3,sign*3.5],[sign*.9,0,sign*3.5])],fk['thumb_mcp_flexion'],ip),'thumb_mcp_flexion')
                add('drive_wrap',transform_path([terminal_arc('flex',3.5,sign,ipq)],fk['thumb_mcp_flexion'],ip),'thumb_mcp_flexion','drive_pulley')
            path=[s for group in groups for s in group['path']]
            routes.append({'name':name,'joint':f'thumb_{target}','sign':sign,'groups':groups,'path':path,'termination':endpoint(path[-1],True),'termination_frame':f'thumb_{target}','moment_arm':sign*(3.5 if target=='ip' else 5.5)})
    return routes
