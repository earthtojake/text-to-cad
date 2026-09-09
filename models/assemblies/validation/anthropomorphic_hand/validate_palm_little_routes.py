import sys,json,numpy as np
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from scipy.spatial import cKDTree
from cadgen import build123d as bd
from lib.palm_little_paths import LITTLE_PATHS
from lib.path_analysis import sample_path
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.layout import transforms
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
s=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step');rows=[];tested=0
branches=[(r,cKDTree(sample_path([{'kind':'bezier','points':p}],.05))) for _,_,p,r in LITTLE_PATHS]
eyes=[((22,y,0),4.1,2.4,1) for y in(38.2,71.8)]+[((36,89,z),3.75,2,2) for z in(12.5,-16.5)]
def check(path,label,pose,r):
 global tested
 q=sample_path(path,.07);q=q[(q[:,1]>32)&(q[:,1]<96)]
 if not len(q):return
 tested+=1;near=any(tree.query(q)[0].min()<rr+r+.12 for rr,tree in branches)
 for c,rr,h,axis in eyes:
  qq=q-np.array(c);a=np.linalg.norm(np.delete(qq,axis,axis=1),axis=1)-rr;b=abs(qq[:,axis])-h/2
  sd=np.linalg.norm(np.maximum(np.column_stack([a,b]),0),axis=1)+np.minimum(np.maximum(a,b),0)
  near=near or sd.min()<r+.12
 if near:
  d=path_wire(path).distance_to(s);row={'label':label,'pose':pose,'gap_mm':d-r};rows.append(row);print(row,flush=True)
for route in NEUTRAL_ROUTES:
 for g in route['groups']:check(g['path'],g['label'],{},.45 if g.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .3)
for pose in json.load(open('models/assemblies/validation/anthropomorphic_hand/wrist_motion_routes.json'))['samples']:
 inv=np.linalg.inv(transforms(pose['pose'])['wrist_flexion'])
 for r in pose['routes']:check(transform_path(r['path'],inv),r['name'],pose['pose'],.45)
result={'scope':'all neutral tendon groups and all 17 repaired wrist cases; conservative primitive envelope screens with exact native curve distance for every near pair','broad_tests':tested,'exact_rows':rows,'failures':[r for r in rows if r['gap_mm']<0]}
json.dump(result,open('models/assemblies/validation/anthropomorphic_hand/palm_little_all_routes.json','w'),indent=2)
print('DONE',len(result['failures']),flush=True)
