import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib';trees={k:cKDTree(v) for k,v in dict(np.load(HERE/'remaining_support_route_cloud.npz')).items()};rng=np.random.default_rng(3291);t=np.linspace(0,1,150);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T

def search(root,end,side,fr,n=9000):
 root=np.array(root);end=np.array(end);best=None
 for k in range(n):
  c1=root+[side*rng.uniform(1.5,6),rng.uniform(-1,8),rng.uniform(-5,-.4)]
  c2=end+rng.uniform([2,-7,-7],[9,1,-.3]);cs=np.array([root,c1,c2,end]);pts=w@cs
  d=3*((1-t)[:,None]**2*(c1-root)+2*((1-t)*t)[:,None]*(c2-c1)+t[:,None]**2*(end-c2));dd=6*((1-t)[:,None]*(c2-2*c1+root)+t[:,None]*(end-2*c2+c1));radius=np.linalg.norm(d,axis=1)**3/(np.linalg.norm(np.cross(d,dd),axis=1)+1e-12)
  if radius.min()<.85:continue
  clear=float(trees[fr].query(pts)[0].min());length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score=min(clear,1.25)-length*.0002
  if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist()],'clearance':clear,'curvature_radius':float(radius.min()),'score':score}
 assert best;return best
anchor=[-1.512673403,-9.118275723,-15.000175788];end=np.array(anchor)+[1.98,0,-.85];out={}
for sign in(-1,1):
 arms=[]
 for y in(-24,-23):
  arm=search([sign*2.27,y,sign*7-.36],end,sign,'thumb',7000);arms.append(arm);print('thumb',sign,y,arm,flush=True)
 out[str(sign)]={'anchor':anchor,'side':1,'width':4.2,'arms':arms,'clearance':min(a['clearance'] for a in arms)}
(SRC/'thumb_fixed_anchors.json').write_text(json.dumps(out,indent=2)+'\n')
