"""Place proven local finger routes into the articulated, fanned hand."""
import numpy as np
from lib.layout import FINGERS,transforms,finger_fan_matrix
from lib.finger_routing import finger_routes,transform_path


def assembled_finger_routes(name,pose=None):
    pose=dict(pose or {});finger=next(f for f in FINGERS if f.name==name)
    fk=transforms(pose)
    parent=fk['palm_cup' if name=='little' else 'wrist_flexion']
    placement=parent@finger_fan_matrix(finger)
    local_pose={k:v for k,v in pose.items() if k.startswith(name+'_')}
    routes=finger_routes(name,local_pose)
    for route in routes:
        for group in route['groups']:group['path']=transform_path(group['path'],placement)
        route['path']=[s for group in route['groups'] for s in group['path']]
        route['termination']=(placement@np.array([*route['termination'],1.]))[:3].tolist()
    return routes
