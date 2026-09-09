"""Replan only spans violating immutable mounting and foreign-CMC envelopes."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.wrist_transport import plan_span,hardware_clearances
from lib.layout import TENDONS,THUMB_CMC,transforms
from lib.path_analysis import sample_path,path_min_radius,path_length

root=Path(__file__).parent
source=json.loads((root/'wrist_motion_routes.json').read_text())
neutral=json.loads((root/'wrist_transport_neutral.json').read_text())
packets=[{'pose':{},'routes':neutral['routes']}]+source['samples']
tendons={t['name']:t for t in TENDONS}
output=[]
for packet in packets:
    pose=packet['pose'];routes=packet['routes'];changes=[]
    for index,route in enumerate(routes):
        points=sample_path(route['path'],.025)
        minimum=float(hardware_clearances(points,pose).min())-.45
        if route['name']=='index_mcp_abduction_positive':
            center=(transforms(pose)['wrist_flexion']@np.r_[THUMB_CMC,1.])[:3]
            minimum=min(minimum,float(np.linalg.norm(points-center,axis=1).min())-22.45)
        if minimum>=.005:continue
        cloud=np.concatenate([sample_path(r['path'],.025) for j,r in enumerate(routes) if j!=index])
        print('REPAIR',pose,route['name'],'old envelope clearance',minimum,flush=True)
        result=plan_span(tendons[route['name']],pose,previous_cloud=cloud,seed=route['parameters'])
        points=sample_path(result['path'],.025)
        gap=float(cKDTree(cloud).query(points)[0].min())-.925
        radius=float(path_min_radius(result['path']))
        hardware=float(hardware_clearances(points,pose).min())-.45
        assert gap>0 and radius>=3.5 and hardware>0,(pose,result['name'],gap,radius,hardware)
        result.update(minimum_bend_radius_mm=radius,length_mm=float(path_length(result['path'])),
                      certified_other_surface_gap_mm=gap,hardware_envelope_clearance_mm=hardware)
        routes[index]=result;changes.append(result['name'])
        print('PASS',result['name'],gap,radius,hardware,flush=True)
    output.append({'pose':pose,'routes':routes,'repaired':changes,'clear':True})
    (root/'wrist_mount_repaired_packets.json').write_text(json.dumps({'samples':output},indent=2)+'\n')
    print('PACKET',pose,'repaired',len(changes),flush=True)
print('ALL PACKETS COMPLETE',len(output),flush=True)
