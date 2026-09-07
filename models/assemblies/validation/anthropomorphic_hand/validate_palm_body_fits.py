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
check(make_wrist_palm_cradle(),'wrist_palm_cradle')
little=read_step('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step')
for q in range(0,26,5):check(little.rotate(bd.Axis((22,40,0),(0,-1,0)),q),'fifth_metacarpal',{'palm_cup':q})
for f in FINGERS[:3]:
 s=matrix_location(finger_fan_matrix(f))*(bd.Pos(f.x,f.base_y,0)*make_universal_carrier(phalanx_width=f.widths[0],yaw_plane=8.))
 for q in (f.abduction[0],0,f.abduction[1]):
  pose={f.name+'_mcp_abduction':q};check(matrix_location(assembled_transforms(pose)[f.name+'_mcp_abduction'])*s,f.name+'_carrier',pose)
s=bd.Pos(-35,36,0)*bd.Rot(0,0,45)*make_universal_carrier(phalanx_width=19,yaw_plane=9.5)
for q in(-25,0,45):
 pose={'thumb_cmc_abduction':q};check(matrix_location(assembled_transforms(pose)['thumb_cmc_abduction'])*s,'CMC_carrier',pose)
s=bd.Pos(-35,36,0)*bd.Rot(0,0,45)*make_thumb_metacarpal()
for yaw,flex in itertools.product((-25,0,45),(-15,0,65)):
 pose={'thumb_cmc_abduction':yaw,'thumb_cmc_flexion':flex};check(matrix_location(assembled_transforms(pose)['thumb_cmc_flexion'])*s,'thumb_metacarpal',pose)
def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else [s]
for filename in ('palm_guide_mounts_review','thumb_cmc_mounts_review','drive_terminal_placements'):
 parts=leaves(read_step('models/assemblies/STEP/anthropomorphic_hand/'+filename+'.step'))
 for p in parts:check(p,p.label)
json.dump({'rows':rows,'failures':[r for r in rows if r['intersection_mm3']>1e-7]},open('models/assemblies/validation/anthropomorphic_hand/palm_rebuilt_local_motion_fits.json','w'),indent=2)
print('DONE',len(rows),flush=True)
