import sys,json,gzip
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.native_integration import frozen_bodies
from lib.assembly import posed_bodies,joint_location
from lib.layout import JOINT_BY_NAME,assembled_transforms
from lib.transport_guide import path_wire
from lib.finger_routing import transform_path
bodies=frozen_bodies(False);manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());rows=[]
for label,route_name,group_name,body_names in [
 ('index_mcp_flexion_-15','index_pip_positive','index_pip_positive_mcp_reaction',[
  'index_mcp_abduction_dorsal_drive_stub_keyed_shaft','index_mcp_abduction_dorsal_drive_stub_retaining_ring']),
 ('wrist_flexion_35','thumb_cmc_abduction_positive','thumb_cmc_abduction_positive_wrist_guide',['thumb_cmc_carrier'])]:
 sample=next(r for r in manifest['rows'] if r['label']==label)
 packet=json.load(gzip.open(sample['file'],'rt'));route=next(r for r in packet['routes'] if r['name']==route_name);group=next(g for g in route['groups'] if g['label']==group_name)
 for b in posed_bodies([b for b in bodies if b.name in body_names],sample['pose']):
  d,a,z=path_wire(group['path']).distance_to_with_closest_points(b.shape)
  fk=assembled_transforms(sample['pose']);inv=np.linalg.inv(fk[b.frame]);pt=inv@np.array([*tuple(a),1.])
  row={'sample':label,'body':b.name,'distance':d,'curve_point_world':tuple(a),'body_point_world':tuple(z),'curve_point_neutral':pt[:3].tolist(),'path_neutral':transform_path(group['path'],inv)}
  rows.append(row);print({k:v for k,v in row.items() if k!='path_neutral'},flush=True)
(HERE/'secondary_hardware_diagnostic.json').write_text(json.dumps(rows,indent=2)+'\n')
