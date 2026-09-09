"""Compose all48 tendon paths without hiding interface discontinuities."""
import copy
import numpy as np
from lib.layout import FINGERS,TENDONS,transforms
from lib.assembled_routing import assembled_finger_routes
from lib.thumb_routing import thumb_routes
from lib.cup_transport import cup_packet
from lib.proximal_drive_routing import proximal_drive_route
from lib.forearm_routing import forearm_route
from lib.finger_routing import transform_path,endpoint


def _assert_joins(name,path):
    for index,(a,b) in enumerate(zip(path,path[1:])):
        gap=float(np.linalg.norm(np.asarray(endpoint(a,True))-endpoint(b)))
        if gap>1e-7:raise ValueError(f'{name}: discontinuity of{gap:.9g}mm between segments{index}/{index+1}')


def hand_side_routes(pose=None,cup=None,thumb_cmc=None):
    """All48 terminal-side routes; excludes compensated wrist and forearm runs."""
    pose=dict(pose or {});fk=transforms(pose);cup_rows={r['tendon']:r for r in(cup_packet(pose.get('palm_cup',0.)) if cup is None else cup)}
    routes=[]
    for finger in FINGERS:
        for route in assembled_finger_routes(finger.name,pose):
            if finger.name=='little':
                packet=cup_rows[route['name']]
                prefix={'label':route['name']+'_cup_reaction','path':transform_path(packet['path'],fk['wrist_flexion']),
                    'frame':'variable','guide':'snug_reaction_liner','neutralizes':['palm_cup'],
                    'working_length':packet['length'],'parameters':packet['parameters'],
                    'length_correction':packet['length_correction']}
                route['groups']=[prefix]+route['groups'];route['path']=[s for g in route['groups'] for s in g['path']]
            routes.append(route)
    routes.extend(thumb_routes(pose,cmc_packet=thumb_cmc))
    routes.extend(proximal_drive_route(tendon['name'],pose) for tendon in TENDONS if tendon['name'].startswith(('palm_cup_','wrist_')))
    mapping={r['name']:r for r in routes}
    if len(routes)!=48 or set(mapping)!={t['name'] for t in TENDONS}:raise ValueError('48-tendon assembly manifest mismatch')
    for route in routes:_assert_joins(route['name'],route['path'])
    return [mapping[t['name']] for t in TENDONS]


def full_tendon_routes(wrist_packet,pose=None,capstan_rotations=None):
    """Spool termination to driven termination, using actual evaluated wrist paths.

    The caller supplies a complete wrist packet for exactly this pose. Payout
    compensation is explicit in capstan_rotations; it is not inferred here.
    """
    pose=dict(pose or {});rotations=capstan_rotations or {};wrists={r['name']:r for r in wrist_packet};routes=hand_side_routes(pose)
    if set(wrists)!={t['name'] for t in TENDONS}:raise ValueError('wrist packet must contain all48 tendons')
    for route,tendon in zip(routes,TENDONS):
        name=route['name'];forearm=forearm_route(tendon,rotations.get(name,0.));wrist=wrists[name]
        group={'label':name+'_wrist_guide','path':copy.deepcopy(wrist['path']),'frame':'variable','guide':'compliant_wrist_guide',
               'neutralizes':[],'compensation':'full measured wrist-span length change'}
        route['groups']=forearm['groups']+[group]+route['groups'];route['path']=[s for g in route['groups'] for s in g['path']]
        route['spool_termination']=forearm['inlet'];route['capstan_rotation']=rotations.get(name,0.)
        _assert_joins(name,route['path'])
    return routes
