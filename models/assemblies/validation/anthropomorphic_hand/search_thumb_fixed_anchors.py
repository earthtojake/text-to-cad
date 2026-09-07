import sys,json,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import THUMB_CMC
from lib.palm_frame import make_palm_frame_bodies
from lib.thumb_cmc_mounts import _host_clamp
host=(bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)).inverse()*next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss')
tree=cKDTree(np.load(HERE/'remaining_support_route_cloud.npz')['thumb']);rng=np.random.default_rng(943);t=np.linspace(0,1,75);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T;results={}
for sign in(-1,1):
 best=[]
 for query in [(x,y,z) for x in(-10,-5,0,5,10) for y in(-26,-21,-16,-11) for z in(sign*12,sign*16)]:
  local=host & (bd.Pos(*query)*bd.Box(6,6,6))
  if local is None or not len(local.solids()):continue
  q=np.array(tuple(local.closest_points(query)[0]))
  for side in(-1,1):
   sx=q[0]+side*2.62
   grid=np.array([[q[0]+x,q[1]+y,q[2]+z] for x in(-1.9,-.9,0,.9,1.9) for y in(-.5,0,.5) for z in(-2,-1,0,1,2)]+[[sx+x,q[1]+y,q[2]+z] for x in(-.5,0,.5) for y in(-.5,0,.5) for z in(-.65,0,.65,1.05)])
   clearance=tree.query(grid)[0].min()
   if clearance<.7:continue
   hl,hu,hb,foot=_host_clamp(host,*q,side,'probe',width=3.8,height=4.)
   overlap=hb & host
   if overlap is not None and overlap.volume>1e-7:continue
   arms=[]
   for y in(-24,-23):
    root=np.array([sign*2.27,y,sign*7-.36]);end=np.array(foot);armbest=None
    for k in range(250):
     c1=root+(end-root)/3+rng.uniform([-5,-5,-5],[5,5,5]);c2=root+2*(end-root)/3+rng.uniform([-5,-5,-5],[5,5,5]);points=w@np.array([root,c1,c2,end]);clear=tree.query(points)[0].min()
     if armbest is None or clear>armbest['clearance']:armbest={'controls':[c1.tolist(),c2.tolist()],'clearance':float(clear)}
    arms.append(armbest)
   score=min(clearance,*(a['clearance'] for a in arms));row={'query':query,'anchor':q.tolist(),'side':side,'arms':arms,'clearance':float(score)}
   best=sorted([*best,row],key=lambda r:r['clearance'],reverse=True)[:3];print(sign,query,score,flush=True)
  results[str(sign)]=best;(HERE/'thumb_fixed_anchor_candidates.json').write_text(json.dumps(results,indent=2)+'\n')
