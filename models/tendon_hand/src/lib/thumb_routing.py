"""Complete ten-tendon thumb paths from wrist splice to driven termination."""
import numpy as np
from lib.layout import THUMB_CMC,THUMB_CROSS_AXIS,THUMB_DIRECTION,transforms
from lib.thumb_downstream import thumb_downstream_routes,rotation
from lib.thumb_cmc_transport import thumb_cmc_packet,cmc_inlet_contract
from lib.thumb_yaw_transport import thumb_yaw_reaction_span
from lib.finger_routing import line,transform_path,endpoint


def thumb_terminal_arc(axis,radius,sign,q):
    plane=-11. if sign>0 else -13.5
    return {'kind':'arc','center':[sign*.9,0,0] if axis=='flex' else [0,0,plane],
        'start':[sign*.9,0,sign*radius] if axis=='flex' else [-sign*radius,0,plane],
        'axis':[1,0,0] if axis=='flex' else [0,0,1],'sweepDeg':-sign*150+q}


def thumb_routes(pose=None,cmc_packet=None):
    pose=dict(pose or {});fk=transforms(pose)
    basis=np.eye(4);basis[:3,0]=THUMB_CROSS_AXIS;basis[:3,1]=THUMB_DIRECTION;basis[:3,3]=THUMB_CMC
    parent=fk['wrist_flexion']@basis
    yaw=pose.get('thumb_cmc_abduction',0.);flex=pose.get('thumb_cmc_flexion',0.)
    yaw_local=rotation('z',yaw);child_local=yaw_local@rotation('x',flex)
    routes=[]
    for target in ('cmc_abduction','cmc_flexion'):
        for sign,suffix in ((1,'positive'),(-1,'negative')):
            name=f'thumb_{target}_{suffix}';groups=[]
            def add(label,path,frame,guide=None,neutralizes=()):
                group={'label':f'{name}_{label}','path':transform_path(path,parent),'frame':frame,'guide':guide,'neutralizes':list(neutralizes)}
                if guide=='snug_reaction_liner':
                    first=np.asarray(path[0]['points']);group['working_length']=24.5
                    group['length_correction']={'variable':'first_handle_length','segment':0,'control':1,'anchor_control':0,'direction':'exact_inlet_tangent','initial_value':float(np.linalg.norm(first[1]-first[0]))}
                groups.append(group)
            if target=='cmc_abduction':
                plane=-11 if sign>0 else -13.5
                add('palm_run',[line([-sign*7,-3,plane],[-sign*7,0,plane])],'wrist_flexion')
                add('drive_wrap',[thumb_terminal_arc('yaw',7,sign,yaw)],'wrist_flexion','drive_pulley')
            else:
                add('palm_run',[line([sign*.9,-24,sign*7],[sign*.9,-23,sign*7])],'wrist_flexion')
                add('cmc_yaw_reaction',thumb_yaw_reaction_span(yaw,sign),'variable','snug_reaction_liner',('thumb_cmc_abduction',))
                add('drive_approach',transform_path([line([sign*.9,-3,sign*7],[sign*.9,0,sign*7])],yaw_local),'thumb_cmc_abduction')
                add('drive_wrap',transform_path([thumb_terminal_arc('flex',7,sign,flex)],yaw_local),'thumb_cmc_abduction','drive_pulley')
            path=[s for g in groups for s in g['path']]
            routes.append({'name':name,'joint':f'thumb_{target}','sign':sign,'groups':groups,'path':path,'termination':endpoint(path[-1],True),'termination_frame':f'thumb_{target}','moment_arm':sign*7})
    contract={r['tendon']:r for r in cmc_inlet_contract()}
    packet={r['tendon']:r for r in (thumb_cmc_packet(flex,yaw) if cmc_packet is None else cmc_packet)}
    short_mcp_yaw=abs(contract['thumb_mcp_flexion_positive']['outlet'][1]-16.)<1e-9
    for route in thumb_downstream_routes(pose,short_mcp_yaw=short_mcp_yaw):
        name=route['name'];datum=contract[name];reaction=packet[name]
        prefix=[{'label':f'{name}_palm_run','path':transform_path([line(datum['splice_point'],datum['anchor'])],parent),'frame':'wrist_flexion','guide':None,'neutralizes':[]},
                {'label':f'{name}_cmc_reaction','path':transform_path(reaction['path'],parent),'frame':'variable','guide':'snug_reaction_liner','neutralizes':['thumb_cmc_abduction','thumb_cmc_flexion'],'working_length':reaction['working_length'],'parameters':reaction['parameters'],'length_correction':reaction['length_correction']}]
        for group in route['groups']:group['path']=transform_path(group['path'],parent@child_local)
        route['groups']=prefix+route['groups'];route['path']=[s for g in route['groups'] for s in g['path']]
        route['termination']=endpoint(route['path'][-1],True);routes.append(route)
    assert len(routes)==10
    return routes
