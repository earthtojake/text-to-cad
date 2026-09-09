import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand/lib';file=SRC/'wrist_support_paths.json';data=json.loads(file.read_text());q=np.array([-2.644829653,67.040070426,7.000320874]);end=q+[1.98,0,-.85];tree=cKDTree(np.load(HERE/'wrist_support_route_cloud.npz')['palm']);rng=np.random.default_rng(29);t=np.linspace(0,1,120);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T
for name in('cup_positive','cup_negative'):
 root=np.array(data[name]['root']);best=None
 for k in range(2200):
  c1=root+(end-root)/3+rng.uniform([-8,-8,-12],[8,8,12]);c2=root+2*(end-root)/3+rng.uniform([-8,-8,-12],[8,8,12]);pts=w@np.array([root,c1,c2,end]);clear=float(tree.query(pts)[0].min());score=min(clear,1.4)-np.linalg.norm(np.diff(pts,axis=0),axis=1).sum()*.0002
  if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist()],'arm_clearance_centerline_mm':clear,'score':score}
 data[name]={**data[name],**best,'query':q.tolist(),'host_point':q.tolist(),'end':end.tolist()};print(name,data[name],flush=True)
file.write_text(json.dumps(data,indent=2)+'\n')
