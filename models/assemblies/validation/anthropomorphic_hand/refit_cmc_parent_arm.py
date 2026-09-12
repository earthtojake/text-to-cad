import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib';trees={k:cKDTree(v) for k,v in dict(np.load(HERE/'remaining_support_route_cloud.npz')).items()};rng=np.random.default_rng(3291);t=np.linspace(0,1,150);w=np.array([math.comb(5,i)*t**i*(1-t)**(5-i) for i in range(6)]).T

import sys
sys.path.insert(0,str(SRC.parent))
from lib.palm_frame_paths import PALM_PATHS
from lib.layout import THUMB_CMC
from collections import defaultdict
hostpts=defaultdict(list);R=np.array([[2**-.5,2**-.5,0],[-2**-.5,2**-.5,0],[0,0,1]])
u=np.linspace(0,1,100);ww=np.array([(1-u)**3,3*u*(1-u)**2,3*u*u*(1-u),u**3]).T
for row in PALM_PATHS:
 for seg in row['segments']:
  pts=(ww@np.array(seg)-np.array(THUMB_CMC))@R.T
  if np.any((pts[:,1]>-29)&(pts[:,1]<-5)):hostpts[row['radius']].extend(pts)
hosttrees=[(cKDTree(np.array(v)),r) for r,v in hostpts.items()]

def search(root,end,side,fr,n=9000):
 root=np.array(root);end=np.array(end);best=None
 for k in range(n):
  c1=root+[rng.uniform(.8,4),rng.uniform(-4,1),rng.uniform(-8,-1)]
  c2=root+.40*(end-root)+rng.uniform([-9,-9,-9],[9,9,9]);c3=root+.70*(end-root)+rng.uniform([-9,-9,-9],[9,9,9]);c4=end+[rng.uniform(-1,3),rng.uniform(-3,1),rng.uniform(1,4)];cs=np.array([root,c1,c2,c3,c4,end]);pts=w@cs
  d=np.gradient(pts,t,axis=0);dd=np.gradient(d,t,axis=0);radius=np.linalg.norm(d,axis=1)**3/(np.linalg.norm(np.cross(d,dd),axis=1)+1e-12)
  if radius.min()<.85:continue
  clear=float(trees[fr].query(pts)[0].min());hostgap=min(float(tr.query(pts[:-8])[0].min())-r for tr,r in hosttrees);clear=min(clear,hostgap+.4);length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score=min(clear,1.25)-length*.0002
  if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist(),c3.tolist(),c4.tolist()],'clearance':clear,'curvature_radius':float(radius.min()),'score':score}
 assert best;return best
best=search([6.81,-12.25,-.36],[2.98,-8,-15.81],1,'thumb',12000);(SRC/'cmc_parent_arm.json').write_text(json.dumps(best,indent=2)+'\n');print(best,flush=True)
