import sys,json
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
import numpy as np
from scipy.spatial import cKDTree
from cadgen import build123d as bd
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
from lib.finger_routing import transform_path
from lib.layout import transforms
from lib.transport_guide import path_wire
shape=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step')
branches=[(p['name'],p['radius'],cKDTree(sample_path([{'kind':'bezier','points':x} for x in p['segments']],.06))) for p in PALM_PATHS]
branches.append(('cmc_patch',1.3,cKDTree(sample_path([{'kind':'bezier','points':[(-35,36,-18),(-31,34.5,-18),(-26,35,-18),(-21.75,36.625,-18)]}],.06))))
eyes=[]
for x,y in ((-36,101),(-12,105),(12,100)):
 for z in (12.5,-16.5):eyes.append((f'mcp_{x}_{z}',(x,y,z),3.75,2,2))
for z in (14,-18):eyes.append((f'cmc_{z}',(-35,36,z),4.15,2,2))
for x in (-24,24):eyes.append((f'foot_{x}',(x,14,-10.2),3.3,3.2,2))
for y in (35,75):eyes.append((f'cup_{y}',(22,y,0),4.1,2.4,1))
for i,c in enumerate(((-24,55,11.5),(15,53,11.5),(-4,66,11.5))):eyes.append((f'pad_{i}',c,2.5,2.2,2))
centers=np.array([[-28,48,-22],[-10,74,-22],[16,56,-22]])
rows=[]
def check(path,name,pose,radius):
 q=sample_path(path,.06);q=q[(q[:,1]>8)&(q[:,1]<110)]
 if not len(q):return
 risks=[]
 for label,r,tree in branches:
  d=tree.query(q)[0].min()-r-radius-.06
  if d<.02:risks.append((label,float(d)))
 for label,c,r,h,axis in eyes:
  local=q-np.array(c);a=np.linalg.norm(np.delete(local,axis,axis=1),axis=1)-r;b=np.abs(local[:,axis])-h/2
  sd=np.sqrt(np.maximum(a,0)**2+np.maximum(b,0)**2)+np.minimum(np.maximum(a,b),0)
  d=sd.min()-radius-.03
  if d<.02:risks.append((label,float(d)))
 if cKDTree(centers).query(q)[0].min()-1.65-radius-.03<.02:risks.append(('branch_node',-1))
 if risks:
  wire=path_wire(path);d=wire.distance_to(shape);row={'name':name,'pose':pose,'radius':radius,'distance':d,'gap':d-radius,'risks':risks};rows.append(row);print(row,flush=True)
for r in NEUTRAL_ROUTES:
 for g in r['groups']:
  radius=.45 if g.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30
  check(g['path'],g['label'],{},radius)
print('NEUTRAL_DONE',flush=True)
motion=json.load(open('models/assemblies/validation/anthropomorphic_hand/wrist_motion_routes.json'))
for pose in motion['samples']:
 inv=np.linalg.inv(transforms(pose['pose'])['wrist_flexion'])
 for r in pose['routes']:check(transform_path(r['path'],inv),r['name']+'_wrist_guide',pose['pose'],.45)
 print('POSE_DONE',pose['pose'],flush=True)
report={'scope':'all neutral groups and 17 wrist span cases versus raw branch/cylinder envelope; exact STEP checks for every near pair','rows':rows,'failures':[r for r in rows if r['gap']<0]}
Path('models/assemblies/validation/anthropomorphic_hand/palm_rebuilt_route_audit.json').write_text(json.dumps(report,indent=2))
print('FAILURES',len(report['failures']),flush=True)
