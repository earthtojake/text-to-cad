"""Search support centerlines in the actual 225-pose route cloud; native gate follows."""
import sys,json,gzip,math,time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent;sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import transforms
from lib.axis_transport import point_at
from lib.wrist import make_wrist_fixed_fork
from lib.palm_frame import make_palm_frame_bodies

def bezier(cp,t):
 a=np.array(cp,float);out=[]
 for v in t:
  b=a.copy()
  while len(b)>1:b=(1-v)*b[:-1]+v*b[1:]
  out.append(b[0])
 return np.array(out)

cloudfile=HERE/'wrist_support_route_cloud.npz'
if cloudfile.exists():clouds=dict(np.load(cloudfile))
else:
 clouds={'palm':[],'forearm':[]};m=json.loads((HERE/'static_route_packet_manifest.json').read_text())
 for ri,e in enumerate(m['rows']):
  packet=json.load(gzip.open(e['file'],'rt'));fk=transforms(e['pose']);matrices={'palm':np.linalg.inv(fk['wrist_flexion']),'forearm':np.eye(4)}
  for fr,mat in matrices.items():
   lo=np.array([-32,25,-25]) if fr=='palm' else np.array([-22,-34,-16]);hi=np.array([32,72,25]) if fr=='palm' else np.array([22,-7,16])
   for r in packet['routes']:
    for g in r['groups']:
     for s in g['path']:
      if s['kind']=='bezier':
       cp=np.asarray(s['points'])@mat[:3,:3].T+mat[:3,3]
       if np.any(cp.max(axis=0)<lo) or np.any(cp.min(axis=0)>hi):continue
       n=max(10,int(np.linalg.norm(np.diff(cp,axis=0),axis=1).sum()/.65)+1);pts=bezier(cp,np.linspace(0,1,n))
      elif s['kind']=='line':
       cp=np.array([s['start'],s['end']])@mat[:3,:3].T+mat[:3,3]
       if np.any(cp.max(axis=0)<lo) or np.any(cp.min(axis=0)>hi):continue
       pts=bezier(cp,np.linspace(0,1,max(2,int(np.linalg.norm(cp[1]-cp[0])/.65)+1)))
      else:
       pts=np.array([point_at(s,t) for t in np.linspace(0,1,60)])@mat[:3,:3].T+mat[:3,3]
      pts=pts[np.all((pts>=lo)&(pts<=hi),axis=1)]
      if len(pts):clouds[fr].append(pts)
  if ri%25==0:print('cloud pose',ri,flush=True)
 clouds={fr:np.unique(np.round(np.concatenate(ps),2),axis=0) for fr,ps in clouds.items()};np.savez_compressed(cloudfile,**clouds)
print({k:len(v) for k,v in clouds.items()},flush=True)
palm=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss');fork=make_wrist_fixed_fork();rng=np.random.default_rng(43);results={};anchors={}
for target,root,host,fr,queries,side in [
 ('cup_positive',[2,43.63,6.64],palm,'palm',[(x,y,z) for x,y in [(-4,66),(15,53),(-24,55),(-13,44),(17.5,36.5)] for z in(-14,-11.5,11.5,14)],1),
 ('cup_negative',[2,45.63,-7.36],palm,'palm',[(x,y,z) for x,y in [(-4,66),(15,53),(-24,55),(-13,44),(17.5,36.5)] for z in(-14,-11.5,11.5,14)],1),
 ('yaw_positive',[-12.37,-15,5.14],fork,'forearm',[(-x,y,z) for x,y in [(7.5,-18),(8.5,-22),(10,-27),(3,-14)] for z in(9,10.5,11.5)],-1)]:
 tree=cKDTree(clouds[fr]);root=np.array(root);best=[]
 for query in queries:
  akey=(fr,query)
  if akey not in anchors:
   nearby=host & (bd.Pos(*query)*bd.Box(7,7,7))
   if not nearby or not len(nearby.solids()):continue
   anchors[akey]=np.array(tuple(nearby.closest_points(query)[0]))
  q=anchors[akey];end=q+[side*1.78,0,-.85]
  print('candidate anchor',target,query,q.tolist(),flush=True)
  # Coarse full clamp envelope: conservative enough to reject busy stations.
  grid=np.array([[q[0]+x,q[1]+y,q[2]+z] for x in(-1.9,0,1.9) for y in(-.5,0,.5) for z in(-2,0,2)])
  clampclear=tree.query(grid)[0].min()
  if clampclear<.55:continue
  for k in range(350):
   if k==0:c1=root+(end-root)/3;c2=root+2*(end-root)/3
   else:
    c1=root+(end-root)/3+rng.uniform([-7,-6,-10],[7,6,10]);c2=root+2*(end-root)/3+rng.uniform([-7,-6,-10],[7,6,10])
   path=bezier([root,c1,c2,end],np.linspace(0,1,65));clear=tree.query(path)[0].min();score=min(clear,clampclear+.2)
   if len(best)<4 or score>best[-1]['score']:
    best.append({'query':query,'host_point':q.tolist(),'root':root.tolist(),'end':end.tolist(),'controls':[c1.tolist(),c2.tolist()],'arm_clearance_centerline_mm':float(clear),'clamp_sample_clearance_mm':float(clampclear),'score':float(score)});best=sorted(best,key=lambda x:x['score'],reverse=True)[:4]
 results[target]=best;print(target,best,flush=True);(HERE/'wrist_support_path_candidates.json').write_text(json.dumps(results,indent=2)+'\n')
