import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib';plan=json.loads((SRC/'cup_host_anchor.json').read_text());q=np.array(plan['anchor']);foot=q+[plan['side']*1.78,0,-.85];end=foot+[0,-1.5,-.5];old=json.loads((SRC/'remaining_support_paths.json').read_text());tree=cKDTree(np.load(HERE/'remaining_support_route_cloud.npz')['cup']);rng=np.random.default_rng(219);t=np.linspace(0,1,130);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T;out={'node':end.tolist(),'foot':foot.tolist(),'branches':{}}
for key,entry in old.items():
 if not key.startswith('child_'):continue
 root=np.array(entry['root']);best=None
 for k in range(3600):
  c1=root+(end-root)/3+rng.uniform([-10,-12,-14],[10,12,14]);c2=root+2*(end-root)/3+rng.uniform([-10,-12,-14],[10,12,14]);pts=w@np.array([root,c1,c2,end]);clear=float(tree.query(pts)[0].min());length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score=min(clear,1.2)-length*.0004
  if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist()],'clearance':clear,'score':score}
 out['branches'][key]=best;print(key,best,flush=True);(SRC/'cup_child_direct_paths.json').write_text(json.dumps(out,indent=2)+'\n')
