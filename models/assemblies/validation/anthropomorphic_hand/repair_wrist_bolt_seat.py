"""Preserve the complete palm mounting annulus at wrist flexion55 degrees."""
import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.wrist_transport import plan_span,hardware_clearances
from lib.layout import TENDONS
from lib.path_analysis import sample_path,path_length,path_min_radius
root=Path(__file__).parent
file=root/'wrist_mount_repaired_packets.json';data=json.loads(file.read_text())
packet=next(p for p in data['samples'] if p['pose']=={'wrist_flexion':55.0})
name='index_mcp_flexion_negative';index=next(i for i,r in enumerate(packet['routes']) if r['name']==name)
old=packet['routes'][index];cloud=np.concatenate([sample_path(r['path'],.025) for i,r in enumerate(packet['routes']) if i!=index])
result=plan_span(next(t for t in TENDONS if t['name']==name),packet['pose'],previous_cloud=cloud,seed=old['parameters'])
points=sample_path(result['path'],.025)
gap=float(cKDTree(cloud).query(points)[0].min())-.925
radius=float(path_min_radius(result['path']));hardware=float(hardware_clearances(points,packet['pose']).min())-.45-.0125
assert gap>0 and radius>=3.5 and hardware>0,(gap,radius,hardware)
result.update(minimum_bend_radius_mm=radius,length_mm=float(path_length(result['path'])),certified_other_surface_gap_mm=gap,hardware_envelope_clearance_mm=hardware)
packet['routes'][index]=result
(root/'wrist_bolt_seat_repair.json').write_text(json.dumps({'old':old,'replacement':result,'pose':packet['pose'],'gap':gap,'minimum_radius':radius,'hardware_gap':hardware},indent=2)+'\n')
file.write_text(json.dumps(data,indent=2)+'\n')
file=root/'wrist_motion_routes.json';motion=json.loads(file.read_text());target=next(p for p in motion['samples'] if p['pose']==packet['pose']);target['routes'][index]=result;file.write_text(json.dumps(motion,indent=2)+'\n')
print('REPAIRED',gap,radius,hardware,flush=True)
