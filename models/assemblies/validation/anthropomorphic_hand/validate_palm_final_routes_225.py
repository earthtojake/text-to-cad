import sys,json,gzip,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step
from lib.layout import assembled_transforms
from lib.finger_routing import transform_path
from lib.path_analysis import sample_path
from lib.transport_guide import path_wire
from lib.palm_frame_paths import PALM_PATHS
from lib.palm_little_paths import LITTLE_PATHS
V=Path('models/assemblies/validation/anthropomorphic_hand');M=json.loads((V/'static_route_packet_manifest.json').read_text());B=Path('models/assemblies/STEP/anthropomorphic_hand')
which=sys.argv[1] if len(sys.argv)>1 else 'main'
shapes={which:read_step(B/('palm_main_final_rom_review.step' if which=='main' else 'palm_little_comb_rom_review.step'))}
branches={'main':np.vstack([sample_path([{'kind':'bezier','points':s} for s in r['segments']],.08) for r in PALM_PATHS]+[sample_path([{'kind':'bezier','points':[(-35,36,-18),(-32.12,34.92,-18),(-28.7216,34.8768,-18),(-25.457984,35.543808,-18)]}],.08)]),'little':np.vstack([sample_path([{'kind':'bezier','points':s}],.08) for side,i,s,r in LITTLE_PATHS])};trees={k:cKDTree(q) for k,q in branches.items()}
eyes={'main':[(x,y,z,3.75,1.,2) for x,y in[(-36,101),(-12,105),(12,100)] for z in(12.5,-16.5)]+[(-35,36,z,4.15,1.,2) for z in(14.,-18.)]+[(x,14,-10.2,3.3,1.6,2) for x in(-24,24)]+[(22,y,0,4.1,1.2,1) for y in(35,75)]+[(x,y,11.5,2.5,1.1,2) for x,y in[(-24,55),(15,53),(-4,66)]], 'little':[(36,89,z,3.75,1.,2) for z in(12.5,-16.5)]+[(22,y,0,4.1,1.2,1) for y in(38.2,71.8)]}
new_cmc=json.loads(Path('models/assemblies/src/anthropomorphic_hand/lib/palm_cmc_connection_path.json').read_text())
branches['main']=np.vstack([branches['main'],sample_path([{'kind':'bezier','points':p} for p in new_cmc['segments']],.08)])
trees['main']=cKDTree(branches['main']);eyes['main'].append((-35,36,9.3,1.85,.7,2))
node=cKDTree([[-28,48,-22],[-10,74,-22],[16,56,-22]])
def lower_gap(k,q,radius):
 d=trees[k].query(q)[0].min()-(1.35 if k=='main' else 1.45)
 if k=='main':d=min(d,node.query(q)[0].min()-1.65)
 for x,y,z,r,h,axis in eyes[k]:
  local=q-[x,y,z];a=np.linalg.norm(np.delete(local,axis,axis=1),axis=1)-r;b=np.abs(local[:,axis])-h;dd=np.hypot(np.maximum(a,0),np.maximum(b,0))+np.minimum(np.maximum(a,b),0);d=min(d,dd.min())
 return d-radius-.24
cache={};near=[];native=0
for j,sample in enumerate(M['rows']):
 packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()));fk=assembled_transforms(sample['pose']);inverses={'main':np.linalg.inv(fk['wrist_flexion']),'little':np.linalg.inv(fk['palm_cup'])}
 for route in packet['routes']:
  for group in route['groups']:
   radius=.45 if group.get('guide') in('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30
   for k in shapes:
    path=transform_path(group['path'],inverses[k]);key=(k,radius,json.dumps(path,sort_keys=True));
    if key in cache:continue
    q=sample_path(path,.3);q=q[(q[:,1]>7)&(q[:,1]<111)&(q[:,2]>-29)&(q[:,2]<24)]
    if not len(q) or lower_gap(k,q,radius)>.06:cache[key]=None;continue
    d=path_wire(path).distance_to(shapes[k])-radius;native+=1;cache[key]=d
    if d<.13:
     row={'sample':sample['label'],'pose':sample['pose'],'body':k,'tendon':route['name'],'group':group['label'],'radius':radius,'gap':d,'path':path};near.append(row);print('NEAR',k,route['name'],group['label'],sample['label'],d,flush=True)
 report={'scope':'All48 tendon full path groups in every225 static packet versus final main/little, conservative primitive screen then exact native distances. Immutable PIP/CMC bearing contacts are separately owned by root.','completed_poses':j+1,'native_checks':native,'near':near,'unique_path_body_pairs':len(cache),'complete':j==224,'pass':j==224 and not any(r['gap']<.02 for r in near),'failures':[r for r in near if r['gap']<.02]}
 (V/f'palm_{which}_accepted_routes_225_gate.json').write_text(json.dumps(report,indent=2))
 if j%10==0:print('POSE',j,'NATIVE',native,'UNIQUE',len(cache),flush=True)
print('DONE',native,len(near),flush=True)
