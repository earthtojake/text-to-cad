import sys,json,itertools
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd,read_step
from lib.layout import FINGERS,finger_fan_matrix,assembled_transforms
from lib.assembly import matrix_location
from lib.universal_carrier import make_universal_carrier
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.wrist import make_wrist_palm_cradle
main=read_step('models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step');mb=main.bounding_box();rows=[]
import numpy as np
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
branches=[(sample_path([{'kind':'bezier','points':p} for p in row['segments']],.05),row['radius']) for row in PALM_PATHS]
branches.append((sample_path([{'kind':'bezier','points':[(-35,36,-18),(-31,34.5,-18),(-26,35,-18),(-21.75,36.625,-18)]}],.05),1.3))
balls=[(np.array((x,y,z)),4.2) for x,y in ((-36,101),(-12,105),(12,100)) for z in (12.5,-16.5)]
balls += [(np.array((-35,36,z)),4.5) for z in (14,-18)]
balls += [(np.array((x,14,-10.2)),3.8) for x in (-24,24)]
balls += [(np.array((22,y,0)),4.5) for y in (35,75)]
balls += [(np.array(c),2.9) for c in ((-24,55,11.5),(15,53,11.5),(-4,66,11.5))]
balls += [(np.array(c),1.65) for c in ((-28,48,-22),(-10,74,-22),(16,56,-22))]
def check(shape,name,pose={}):
 bb=shape.bounding_box();low=np.array(tuple(bb.min));high=np.array(tuple(bb.max))
 def boxgap(q):return np.linalg.norm(np.maximum(np.maximum(low-q,q-high),0),axis=-1)
 near=any(boxgap(q).min()<r+.06 for q,r in branches) or any(boxgap(c)<r+.06 for c,r in balls)
 if not near:
  rows.append({'name':name,'pose':pose,'intersection_mm3':0.,'method':'conservative swept-branch/eye envelope'});return
 hit=main&shape;v=sum(s.volume for s in hit.solids()) if hit else 0
 row={'name':name,'pose':pose,'intersection_mm3':v,'method':'exact native Boolean'};rows.append(row)
 if v>1e-7:
  row['intersection_bounds']=[tuple(hit.bounding_box().min),tuple(hit.bounding_box().max)]
  print('HIT',row,flush=True)
 else:print('CLEAR',name,pose,flush=True)

import numpy as np
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
curves=[(sample_path([{'kind':'bezier','points':p} for p in row['segments']],.05),row['radius']) for row in PALM_PATHS]
# Every fixed eye and branching node is covered by a conservative sphere.
centers=[(np.array(c),r) for c,r in [*(((-35,36,z),4.4) for z in(14,-18)),*(((-24,14,-10.2),3.6),((24,14,-10.2),3.6)),*(((-28,48,-22),1.65),((-10,74,-22),1.65),((16,56,-22),1.65))]]
centers += [(np.array((x,y,z)),4.2) for x,y in ((-36,101),(-12,105),(12,100)) for z in (12.5,-16.5)]
centers += [(np.array(c),2.9) for c in ((-24,55,11.5),(15,53,11.5),(-4,66,11.5))]
centers += [(np.array((22,y,0)),4.5) for y in (35,75)]
curves.append((sample_path([{'kind':'bezier','points':[(-35,36,-18),(-31,34.5,-18),(-26,35,-18),(-21.75,36.625,-18)]}],.05),1.3))
parts=read_step('models/assemblies/STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')
def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else [s]
parts=[p for p in leaves(parts) if 'child' in p.label]
for yaw,flex in itertools.product((-25,0,45),(-15,0,65)):
 pose={'thumb_cmc_abduction':yaw,'thumb_cmc_flexion':flex};loc=matrix_location(assembled_transforms(pose)['thumb_cmc_flexion'])
 for part in parts:
  posed=loc*part;bb=posed.bounding_box();low=np.array(tuple(bb.min));high=np.array(tuple(bb.max))
  def d(q):return np.linalg.norm(np.maximum(np.maximum(low-q,q-high),0),axis=-1)
  near=any(np.min(d(q))-r<.06 for q,r in curves) or any(d(c)<r+.06 for c,r in centers)
  if near:check(posed,part.label,pose)
 print('POSE_DONE',pose,flush=True)
json.dump({'scope':'all18 moving CMC mount bodies,9yaw/flex corners; conservative branch/eye-envelope screen and exact native Boolean for near pairs','rows':rows,'failures':[r for r in rows if r['intersection_mm3']>1e-7]},open('models/assemblies/validation/anthropomorphic_hand/palm_cmc_mount_motion.json','w'),indent=2)
