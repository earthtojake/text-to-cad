"""Optimize cup and radial support curves against all accepted route poses."""
import sys,json,gzip,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent;sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import transforms,FINGERS,finger_fan_matrix,THUMB_CMC
from lib.axis_transport import point_at
from lib.guide_mounts import guide_end_registry
from lib.palm_frame import make_palm_frame_bodies
f=next(f for f in FINGERS if f.name=='little');cupworld=finger_fan_matrix(f)@np.array([[1,0,0,f.x],[0,1,0,f.base_y],[0,0,1,0],[0,0,0,1]])
thumbworld=np.eye(4);a=np.pi/4;thumbworld[:3,:3]=[[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]];thumbworld[:3,3]=THUMB_CMC

def samples(cp,n):
 t=np.linspace(0,1,n);degree=len(cp)-1;return np.array([math.comb(degree,i)*t**i*(1-t)**(degree-i) for i in range(degree+1)]).T@cp
file=HERE/'remaining_support_route_cloud.npz'
if file.exists():clouds=dict(np.load(file))
else:
 clouds={k:[] for k in ('cup','palm','thumb')};manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text())
 for ri,e in enumerate(manifest['rows']):
  packet=json.load(gzip.open(e['file'],'rt'));fk=transforms(e['pose']);matrices={'cup':np.linalg.inv(fk['palm_cup']@cupworld),'palm':np.linalg.inv(fk['wrist_flexion']),'thumb':np.linalg.inv(fk['wrist_flexion']@thumbworld)}
  for fr,mat in matrices.items():
   lo,hi={'cup':([-22,-42,-25],[22,5,20]),'palm':([-40,10,-25],[45,80,25]),'thumb':([-25,-32,-25],[25,40,25])}[fr];lo=np.array(lo);hi=np.array(hi)
   for r in packet['routes']:
    for g in r['groups']:
     for s in g['path']:
      if s['kind'] in ('bezier','line'):
       cp=np.array(s['points'] if s['kind']=='bezier' else [s['start'],s['end']])@mat[:3,:3].T+mat[:3,3]
       if np.any(cp.max(0)<lo) or np.any(cp.min(0)>hi):continue
       pts=samples(cp,max(6,int(np.linalg.norm(np.diff(cp,axis=0),axis=1).sum()/.4)+1))
      else:pts=np.array([point_at(s,t) for t in np.linspace(0,1,100)])@mat[:3,:3].T+mat[:3,3]
      pts=pts[np.all((pts>=lo)&(pts<=hi),axis=1)]
      if len(pts):clouds[fr].append(pts)
  if ri%25==0:print('pose',ri,flush=True)
 clouds={fr:np.unique(np.round(np.concatenate(ps),3),axis=0) for fr,ps in clouds.items()};np.savez_compressed(file,**clouds)
trees={fr:cKDTree(p) for fr,p in clouds.items()};rng=np.random.default_rng(572);plans={}
def search(key,root,end,fr):
 root=np.array(root);end=np.array(end);delta=end-root;tree=trees[fr];best=None
 for k in range(1600):
  c1=root+delta/3+rng.uniform([-6,-8,-10],[6,8,10]);c2=root+2*delta/3+rng.uniform([-6,-8,-10],[6,8,10])
  p=samples(np.array([root,c1,c2,end]),95);clear=float(tree.query(p)[0].min());length=np.linalg.norm(np.diff(p,axis=0),axis=1).sum();score=min(clear,1.25)-length*.0006
  if best is None or score>best['score']:best={'root':root.tolist(),'end':end.tolist(),'controls':[c1.tolist(),c2.tolist()],'clearance':clear,'score':score}
 plans[key]=best;print(key,best,flush=True);(HERE/'remaining_support_path_candidates.json').write_text(json.dumps(plans,indent=2)+'\n')
ends=guide_end_registry();grouped={}
for e in ends:
 if e.frame!='palm_cup':continue
 p=np.linalg.inv(cupworld)@[*e.point,1];grouped.setdefault((round(p[1],7),round(p[2],7)),[]).append(round(p[0],7))
for i,((y,z),xs) in enumerate(sorted(grouped.items())):
 for sign,outer in ([(-1,min(xs)),(1,max(xs))] if len(xs)>1 else [(1 if xs[0]>=0 else -1,xs[0])]):
  search('child_'+str(i+1)+'_'+str(sign),(outer+sign*1.33,y,z-.4),(12,y,z-1.1),'cup')
palm=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss');feet={}
for sign in(-1,1):
 q=np.array(tuple(palm.closest_points((17.5,36.5,sign*14))[0]));feet[sign]=q+[4.08,0,-.85]
grouped={}
for e in ends:
 if e.frame=='wrist_flexion' and all(r.startswith('little_') for r in e.routes):grouped.setdefault((round(e.point[1],7),round(e.point[2],7)),[]).append(e.point)
for i,((y,z),points) in enumerate(sorted(grouped.items())):
 side=-1 if max(p[0] for p in points)>30 else 1;outer=(min if side<0 else max)(p[0] for p in points)
 search('parent_'+str(i+1),(outer+side*1.35,y,z-.36),feet[1 if z>0 else -1],'palm')
from lib.assembly import matrix_location
host=matrix_location(np.linalg.inv(thumbworld))*palm
points=[]
for e in ends:
 if e.frame=='wrist_flexion' and e.name.startswith('thumb_') and '_wrist_guide_outlet' in e.name and ('_mcp_' in e.name or '_ip_' in e.name):points.append((np.linalg.inv(thumbworld)@[*e.point,1])[:3])
y=np.mean(np.array(points)[:,1]);root=(min(p[0] for p in points)-1.37,y,-.36);q=np.array(tuple(host.closest_points((-5,-1,-18))[0]));search('thumb_splice',root,q+[-1.78,0,-.85],'thumb')
