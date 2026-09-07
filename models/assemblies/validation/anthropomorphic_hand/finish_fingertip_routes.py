"""Resume remaining route checks from source-matched production route packets."""
import copy,hashlib,json
from pathlib import Path
import numpy as np
import check_fingertip_pads as audit
from check_global_phalanges import named_poses
from lib.fingertip_pad import fingertip_pad_bodies
from lib.layout import FINGERS,JOINTS,transforms,finger_fan_matrix
from lib.finger_routing import finger_routes,transform_path

root=Path(__file__).parent;source=Path('models/assemblies/src/anthropomorphic_hand/lib')
digest=hashlib.sha256(b''.join((source/n).read_bytes() for n in ['finger_routing.py','bowden_mcp.py','yaw_transport.py','pip_transport.py','layout.py'])).hexdigest()
cache={}
for f in FINGERS:
    d=json.loads((root/(f.name+'_mount_audit_route_packets.json')).read_text())
    if d['source_sha256']!=digest:raise ValueError('Cached routes have changed sources')
    cache[f.name]=d['packets']

def cached_assembled_routes(name,pose):
    local={k:v for k,v in pose.items() if k.startswith(name+'_')}
    key=json.dumps(local,sort_keys=True)
    routes=copy.deepcopy(cache[name][key]) if key in cache[name] else finger_routes(name,local)
    f=next(f for f in FINGERS if f.name==name);fk=transforms(pose)
    placement=fk['palm_cup' if name=='little' else 'wrist_flexion']@finger_fan_matrix(f)
    for route in routes:
        for group in route['groups']:group['path']=transform_path(group['path'],placement)
    return routes

audit.assembled_finger_routes=cached_assembled_routes
report=json.loads((root/'fingertip_pad_report.json').read_text())
repair=json.loads((root/'fingertip_pad_little_repair.json').read_text())
assert repair['pass']
assert repair['source_sha256']==hashlib.sha256((source/'fingertip_pad.py').read_bytes()).hexdigest()
pads=fingertip_pad_bodies()
samples=named_poses()
for j in JOINTS:
    lo,hi=j.limits
    samples.extend((f'{j.name}_{q:g}',{j.name:float(q)}) for q in sorted(set([lo,hi,0.]+list(np.arange(lo,hi+1e-8,10.)))))
for label,pose in samples:
    if any(r['label']==label for r in report['route_rows']):continue
    if len(pose)>1 or not pose:systems=[f.name for f in FINGERS]+['thumb']
    else:
        system=next(j.system for j in JOINTS if j.name==next(iter(pose)))
        if system not in [f.name for f in FINGERS]+['thumb']:continue
        systems=[system]
    row=audit.route_check(pads,label,pose,systems);row['geometry']='final_contained_little_repair'
    report['route_rows'].append(row)
    (root/'fingertip_pad_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(label,row['pass'],row['collisions'],flush=True)
report['route_packet_source_sha256']=digest
report['scope']='Thirty pad-system bodies against all15 native production phalanges over225 poses. Completed route rows use the larger reference little pad until its repair; remaining rows use the final exact subset. Source-matched cached finger routes are transformed with the identical production fan/FK contract. The sole reference full-fist conflict is intentionally retained and superseded by the exact subset/clearance repair certificate. Use fingertip_pad_acceptance.json for final pass status.'
report['pass']=all(r['pass'] for k in ('mounts','body_rows','route_rows') for r in report[k])
(root/'fingertip_pad_report.json').write_text(json.dumps(report,indent=2)+'\n')
print('complete',len(report['route_rows']),'route poses; reference conflict retained for acceptance join',flush=True)
