import sys,json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib';sys.path.insert(0,str(SRC.parent))
from lib.palm_frame import make_palm_frame_bodies
from lib.thumb_remaining_mounts import _near_anchor
clouds=dict(np.load(HERE/'remaining_support_route_cloud.npz'));trees={k:cKDTree(v) for k,v in clouds.items()};rng=np.random.default_rng(917);t=np.linspace(0,1,140);degree=5;w=np.array([math.comb(degree,i)*t**i*(1-t)**(degree-i) for i in range(degree+1)]).T

def search(root,end,side,fr):
 root=np.array(root);end=np.array(end);first=root+[side*2.,-.3,-1.0];best=None
 for k in range(4200):
  controls=[first,*[root+f*(end-root)+rng.uniform([-8,-8,-10],[8,8,10]) for f in(.4,.65,.85)]];pts=w@np.array([root,*controls,end]);clear=float(trees[fr].query(pts)[0].min());length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score=min(clear,1.2)-length*.0003
  if best is None or score>best['score']:best={'controls':[p.tolist() for p in controls],'clearance':clear,'score':score}
 return best
file=SRC/'cup_child_direct_paths.json';child=json.loads(file.read_text());child['branches']['child_3_-1']=search([-2.23,-35,-5.9],child['node'],-1,'cup');file.write_text(json.dumps(child,indent=2)+'\n');print('child3',child['branches']['child_3_-1'],flush=True)
host=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss');q=np.array(tuple(_near_anchor(host,(17.5,36.5,-14))));node=q+[4.08,0,-.85];print('parent anchor',q,'node',node,flush=True)
old=json.loads((SRC/'remaining_support_paths.json').read_text());out={'anchor':q.tolist(),'node':node.tolist(),'branches':{}}
for key,row in old.items():
 if not key.startswith('parent_'):continue
 root=row['root'];side=-1 if key=='parent_5' else 1
 out['branches'][key]=search(root,node,side,'palm');print(key,out['branches'][key],flush=True);(SRC/'cup_fixed_direct_paths.json').write_text(json.dumps(out,indent=2)+'\n')
