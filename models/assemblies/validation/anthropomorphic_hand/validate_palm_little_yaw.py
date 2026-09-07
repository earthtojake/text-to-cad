import sys,json
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd
from lib.layout import FINGERS,finger_fan_matrix
from lib.finger_routing import transform_path
from lib.yaw_transport import yaw_reaction_span
from lib.transport_guide import path_wire
s=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step');f=next(f for f in FINGERS if f.name=='little');fan=finger_fan_matrix(f);rows=[]
for q in range(-25,26):
 for sign in (-1,1):
  path=transform_path(yaw_reaction_span(q,sign),fan,(36,89,0));d=path_wire(path).distance_to(s);rows.append({'yaw_deg':q,'sign':sign,'gap_mm':d-.45})
  if d<.45:print('HIT',rows[-1],flush=True)
 print('YAW',q,'min',min(r['gap_mm'] for r in rows[-2:]),flush=True)
p={'scope':'actual liner-to-fifth-frame gap at 1 degree MCP yaw intervals; MCP flexion 0..90 does not alter these reaction paths; rigid cup transform cancels','rows':rows,'pass':all(r['gap_mm']>=0 for r in rows)}
json.dump(p,open('models/assemblies/validation/anthropomorphic_hand/palm_little_smooth_yaw_proof.json','w'),indent=2)
