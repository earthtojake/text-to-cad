import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;file=HERE/'thumb_fixed_anchor_candidates.json';data=json.loads(file.read_text());plan=data['-1'][0];tree=cKDTree(np.load(HERE/'remaining_support_route_cloud.npz')['thumb']);rng=np.random.default_rng(324);t=np.linspace(0,1,110);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T;end=np.array(plan['anchor'])+[plan['side']*1.78,0,-.85];arms=[]
for y in(-24,-23):
 root=np.array([2.27,y,6.64]);best=None
 for k in range(6500):
  c1=root+(end-root)/3+rng.uniform([-12,-12,-16],[12,12,16]);c2=root+2*(end-root)/3+rng.uniform([-12,-12,-16],[12,12,16]);pts=w@np.array([root,c1,c2,end]);clear=float(tree.query(pts)[0].min());length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score=min(clear,1.4)-length*.0001
  if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist()],'clearance':clear,'score':score}
 arms.append(best);print(y,best,flush=True)
plan={**plan,'arms':arms,'clearance':min(a['clearance'] for a in arms)};data['1']=[plan];file.write_text(json.dumps(data,indent=2)+'\n')
