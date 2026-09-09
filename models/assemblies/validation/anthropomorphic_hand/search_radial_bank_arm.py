"""Construction-only rib search; sampled clearance is not an acceptance gate."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib'
source=SRC/'remaining_support_paths.json';old=json.loads(source.read_text())['thumb_splice']
cloud_path=HERE/'remaining_support_route_cloud.npz';tree=cKDTree(np.load(cloud_path)['thumb'])
root=np.asarray(old['root']);end=np.asarray(old['end']);t=np.linspace(0,1,180);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T
rng=np.random.default_rng(7031);candidates=[]
for i in range(2500):
 c1=np.array([-9.,-12.,-5.5]) if i==0 else rng.uniform([-13,-16,-8],[-7,-9,-3])
 c2=np.array([-9.,-7.,-15.5]) if i==0 else rng.uniform([-14,-12,-19],[-7,-4,-13])
 cp=np.array([root,c1,c2,end]);p=w@cp;r=np.linalg.norm(p[:,:2],axis=1)
 in_drums=((p[:,2]>=-14.7)&(p[:,2]<=-12.3))|((p[:,2]>=-12.2)&(p[:,2]<=-9.8))
 if np.any(r[in_drums]<8.4):continue
 gap=float(tree.query(p)[0].min());length=float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum())
 candidates.append(dict(root=root.tolist(),end=end.tolist(),controls=[c1.tolist(),c2.tolist()],sampled_route_distance_mm=gap,sampled_drum_radial_distance_mm=float(r[in_drums].min()),length_mm=length,score=min(gap,1.4)-.01*length))
candidates.sort(key=lambda x:x['score'],reverse=True);assert candidates
r={'scope':__doc__,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,cloud_path,Path(__file__))},'candidate':candidates[0],'top_candidates':candidates[:10]}
(HERE/'radial_bank_arm_search.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r['candidate']),flush=True)
