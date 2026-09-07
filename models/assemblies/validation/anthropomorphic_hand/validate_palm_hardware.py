"""Native hardware fits and all current neutral/wrist tendon packet clearances."""
import sys,json,itertools,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd,read_step
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.path_analysis import sample_path
from lib.finger_routing import transform_path
from lib.layout import transforms
from lib.transport_guide import path_wire
root=Path('models/assemblies');base=root/'STEP/anthropomorphic_hand';out=root/'validation/anthropomorphic_hand'
def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else[s]
parts=leaves(read_step(base/'palm_hardware_review.step'));rows=[];route_rows=[];near=0;screened=0;source_hashes={}
bbox_cache={}
def bounds_of(s):
 key=id(s)
 if key not in bbox_cache:
  b=s.bounding_box(optimal=False);bbox_cache[key]=(s,np.array(tuple(b.min)),np.array(tuple(b.max)))
 return bbox_cache[key][1:]
bounds=[bounds_of(p) for p in parts]
def bb_gap(a,b):
 lo,hi=bounds_of(a);blo,bhi=bounds_of(b);return np.linalg.norm(np.maximum(np.maximum(lo-bhi,blo-hi),0))
def fit(a,b):
 if bb_gap(a,b)>.001:return
 common=a&b;vol=sum(s.volume for s in common.solids()) if common else 0
 row={'a':a.label,'b':b.label,'intersection_mm3':vol};rows.append(row)
 if vol>1e-7:print('HIT',row,flush=True)
for a,b in itertools.combinations(parts,2):fit(a,b)
for filename in ('imported/palm_frame_integration','palm_cradle_clearance_review','palm_little_review','palm_guide_mounts_review','thumb_cmc_mounts_review','drive_terminal_placements','wrist_guide_mounts_review'):
 source_hashes[filename]=hashlib.sha256((base/(filename+'.step')).read_bytes()).hexdigest()
 for p in leaves(read_step(base/(filename+'.step'))):
  for a in parts:fit(a,p)
 print('BODY_DONE',filename,flush=True)
def route(path,label,pose,radius):
 global near,screened
 q=sample_path(path,.08);wire=None
 for p,(lo,hi) in zip(parts,bounds):
  screened+=1;d=np.linalg.norm(np.maximum(np.maximum(lo-q,q-hi),0),axis=1).min()-radius-.08
  if d>.02:continue
  if wire is None:wire=path_wire(path)
  gap=wire.distance_to(p)-radius;near+=1
  row={'body':p.label,'route':label,'pose':pose,'surface_gap_mm':gap};route_rows.append(row);print('ROUTE',row,flush=True)
for r in NEUTRAL_ROUTES:
 for g in r['groups']:
  radius=.45 if g.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30
  route(g['path'],g['label'],{},radius)
print('NEUTRAL_DONE',flush=True)
motion=json.loads((out/'wrist_motion_routes.json').read_text())
for packet in motion['samples']:
 inv=np.linalg.inv(transforms(packet['pose'])['wrist_flexion'])
 for r in packet['routes']:route(transform_path(r['path'],inv),r['name'],packet['pose'],.45)
 print('POSE_DONE',packet['pose'],flush=True)
result={'input_step_sha256':source_hashes,'body_count':len(parts),'body_native_near_checks':len(rows),'route_screened_pairs':screened,'route_native_near_checks':near,'body_rows':rows,'route_rows':route_rows,'failures':[r for r in rows if r['intersection_mm3']>1e-7]+[r for r in route_rows if r['surface_gap_mm']<0],'step_sha256':hashlib.sha256((base/'palm_hardware_review.step').read_bytes()).hexdigest(),'wrist_packets_sha256':hashlib.sha256((out/'wrist_motion_routes.json').read_bytes()).hexdigest()}
(out/'palm_hardware_fits.json').write_text(json.dumps(result,indent=2));print('DONE',len(result['failures']),flush=True)
