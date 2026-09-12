import sys,json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import FINGERS,finger_fan_matrix
from lib.cup_guide_mounts import _cup_host
from lib.assembly import matrix_location
from lib.thumb_cmc_mounts import _host_clamp
f=next(f for f in FINGERS if f.name=='little');world=finger_fan_matrix(f)@np.array([[1,0,0,f.x],[0,1,0,f.base_y],[0,0,1,0],[0,0,0,1]])
host=matrix_location(np.linalg.inv(world))*_cup_host();tree=cKDTree(np.load(HERE/'remaining_support_route_cloud.npz')['cup']);rng=np.random.default_rng(1943);t=np.linspace(0,1,95);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T;best=[];root=np.array([12,-35,6])
for query in [(x,y,z) for x in(-8,-3,3,8) for y in(-30,-20,-10) for z in(11.5,-14)]:
 local=host & (bd.Pos(*query)*bd.Box(7,7,7))
 if local is None or not len(local.solids()):continue
 q=np.array(tuple(local.closest_points(query)[0]))
 for side in(-1,1):
  sx=q[0]+side*2.62
  grid=np.array([[q[0]+x,q[1]+y,q[2]+z] for x in(-1.9,0,1.9) for y in(-.5,0,.5) for z in(-2,0,2)]+[[sx+x,q[1]+y,q[2]+z] for x in(-.5,0,.5) for y in(-.5,0,.5) for z in(-.65,0,.65,1.05)])
  clearance=tree.query(grid)[0].min()
  if clearance<.85:continue
  hl,hu,hb,foot=_host_clamp(host,*q,side,'probe',width=3.8,height=4.)
  overlap=hb & host
  if overlap is not None and overlap.volume>1e-7:continue
  end=np.array(foot);armbest=None
  for k in range(500):
   c1=root+(end-root)/3+rng.uniform([-6,-6,-8],[6,6,8]);c2=root+2*(end-root)/3+rng.uniform([-6,-6,-8],[6,6,8]);points=w@np.array([root,c1,c2,end]);clear=tree.query(points)[0].min()
   if armbest is None or clear>armbest['clearance']:armbest={'controls':[c1.tolist(),c2.tolist()],'clearance':float(clear)}
  score=min(clearance,armbest['clearance']);row={'query':query,'anchor':q.tolist(),'side':side,'arm':armbest,'clearance':float(score)}
  best=sorted([*best,row],key=lambda r:r['clearance'],reverse=True)[:3];print(query,score,flush=True);(HERE/'cup_host_anchor_candidates.json').write_text(json.dumps(best,indent=2)+'\n')
