import sys,json,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step
from lib.layout import transforms
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
base=Path('models/assemblies');p=base/'STEP/anthropomorphic_hand/palm_hardware_review.step';parts=read_step(p).children
s=next(s for s in parts if s.label=='palm_wrist_ulnar_M3_flanged_thread_insert');rows=[]
packets=json.loads((base/'validation/anthropomorphic_hand/wrist_motion_routes.json').read_text())
for packet in packets['samples']:
 if packet['pose'].get('wrist_flexion') not in (35.,45.,55.,60.):continue
 r=next(r for r in packet['routes'] if r['name']=='little_mcp_abduction_negative');path=transform_path(r['path'],np.linalg.inv(transforms(packet['pose'])['wrist_flexion']));gap=path_wire(path).distance_to(s)-.45
 row={'pose':packet['pose'],'route':r['name'],'native_liner_gap_mm':gap};rows.append(row);print(row,flush=True)
out={'step_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':rows,'failures':[r for r in rows if r['native_liner_gap_mm']<0]};(base/'validation/anthropomorphic_hand/palm_final_insert_clearance.json').write_text(json.dumps(out,indent=2));assert not out['failures']
