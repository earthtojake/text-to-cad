import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand';sys.path.insert(0,str(SRC))
from lib.layout import JOINT_BY_NAME,transforms
from lib.assembly import joint_location,matrix_location
from cadgen import build123d as bd
root=np.array([-12.37,-15,5.96]);end=np.array([-10.28,-22,9.65]);tree=cKDTree(np.load(HERE/'wrist_support_route_cloud.npz')['forearm']);rng=np.random.default_rng(754);t=np.linspace(0,1,110);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T
# Signed exact point distance to conservative circular flex-drive envelopes.
from OCP.gp import gp_Pnt
def matrix(loc):
 tr=loc.wrapped.Transformation();return np.array([[tr.Value(i,j) for j in range(1,5)] for i in range(1,4)]+[[0,0,0,1]])
inv=[]
for angle in(-20,-10,0,10,20):
 for side in(-1,1):
  loc=matrix_location(transforms({'wrist_abduction':angle})['wrist_flexion'])*joint_location(JOINT_BY_NAME['wrist_flexion'])*bd.Pos(0,0,side*14);inv.append(np.linalg.inv(matrix(loc)))
def hardware_clear(path):
 best=1e9
 for m in inv:
  p=path@m[:3,:3].T+m[:3,3];d=np.c_[np.linalg.norm(p[:,:2],axis=1)-11.7,np.abs(p[:,2])-.85];signed=np.linalg.norm(np.maximum(d,0),axis=1)+np.minimum(np.max(d,axis=1),0);best=min(best,signed.min())
 return best
best=None
for i in range(12000):
 c1=root+(end-root)/3+(rng.uniform([-4,-5,-2],[4,5,7]) if i else 0);c2=root+2*(end-root)/3+(rng.uniform([-4,-5,-2],[4,5,7]) if i else 0);path=w@np.array([root,c1,c2,end]);route=tree.query(path)[0].min();hw=hardware_clear(path);score=min(route-.45,hw)-.002*np.linalg.norm(np.diff(path,axis=0),axis=1).sum()
 if best is None or score>best['score']:
  best={'root':root.tolist(),'end':end.tolist(),'controls':[c1.tolist(),c2.tolist()],'route_clear':float(route),'hardware_clear':float(hw),'score':float(score)};print(i,best,flush=True)
file=SRC/'lib/wrist_support_paths.json';data=json.loads(file.read_text());data['yaw_positive'].update(best);file.write_text(json.dumps(data,indent=2)+'\n')
