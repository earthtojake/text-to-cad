import sys,json,gzip,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from collections import defaultdict
HERE=Path(__file__).parent;ROOT=HERE.parents[1];SRC=ROOT/'src/anthropomorphic_hand';sys.path.insert(0,str(SRC))
from lib.palm_guide_mounts import palm_ray_endpoints
from lib.palm_frame_paths import PALM_PATHS
from lib.layout import transforms,MCP_PALM_SUPPORT_PLANES
from lib.axis_transport import point_at

def samples(cp,n):
 t=np.linspace(0,1,n);d=len(cp)-1;return np.array([math.comb(d,i)*t**i*(1-t)**(d-i) for i in range(d+1)]).T@cp
file=HERE/'palm_bank_full_route_cloud.npz'
if file.exists():cloud=np.load(file)['points']
else:
 points=[];lo=np.array([-55,50,-25]);hi=np.array([40,115,16]);manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text())
 for e in manifest['rows']:
  packet=json.load(gzip.open(e['file'],'rt'));m=np.linalg.inv(transforms(e['pose'])['wrist_flexion'])
  for r in packet['routes']:
   for g in r['groups']:
    for s in g['path']:
     if s['kind'] in('bezier','line'):
      cp=np.array(s['points'] if s['kind']=='bezier' else [s['start'],s['end']])@m[:3,:3].T+m[:3,3]
      if np.any(cp.max(0)<lo) or np.any(cp.min(0)>hi):continue
      pts=samples(cp,max(6,int(np.linalg.norm(np.diff(cp,axis=0),axis=1).sum()/.35)+1))
     else:pts=np.array([point_at(s,t) for t in np.linspace(0,1,120)])@m[:3,:3].T+m[:3,3]
     pts=pts[np.all((pts>=lo)&(pts<=hi),axis=1)]
     if len(pts):points.append(pts)
 cloud=np.unique(np.round(np.concatenate(points),3),axis=0);np.savez_compressed(file,points=cloud)
print('cloud',len(cloud),flush=True);rng=np.random.default_rng(546);plans={};t=np.linspace(0,1,140);w=np.array([(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]).T;previous=[]
for name in('index','middle','ring'):
 entries,world=palm_ray_endpoints(name);inv=np.linalg.inv(world);tree=cKDTree(cloud@inv[:3,:3].T+inv[:3,3]);hostpts=defaultdict(list)
 for row in PALM_PATHS:
  for seg in row['segments']:
   pts=samples(np.array(seg),100)@inv[:3,:3].T+inv[:3,3]
   if np.any((pts[:,1]>-45)&(pts[:,1]<4)):hostpts[row['radius']].extend(pts)
 ht=[(cKDTree(np.array(v)),r) for r,v in hostpts.items()];prev=cKDTree(np.array(previous)@inv[:3,:3].T+inv[:3,3]) if previous else None;ymin=min(p[1] for e,p in entries)
 for sign in(-1,1):
  x=sign*(7.2 if(name,sign)in(('index',1),('middle',-1)) else 8.);root=np.array([x,ymin,6]);end=np.array([sign*2.85,-2.85,MCP_PALM_SUPPORT_PLANES[1]]);best=None
  for k in range(7500):
   c1=root+.32*(end-root)+rng.uniform([-4,-6,-10],[4,6,7]);c2=root+.72*(end-root)+rng.uniform([-4,-6,-8],[4,6,8]);cs=np.array([root,c1,c2,end]);pts=w@cs
   d=3*((1-t)[:,None]**2*(c1-root)+2*((1-t)*t)[:,None]*(c2-c1)+t[:,None]**2*(end-c2));dd=6*((1-t)[:,None]*(c2-2*c1+root)+t[:,None]*(end-2*c2+c1));rad=np.linalg.norm(d,axis=1)**3/(np.linalg.norm(np.cross(d,dd),axis=1)+1e-12)
   if rad.min()<1:continue
   clear=float(tree.query(pts)[0].min());hostgap=min(float(tr.query(pts[:-8])[0].min())-r for tr,r in ht);score=min(clear,hostgap+.45,1.1)
   if prev:score=min(score,float(prev.query(pts)[0].min())-.0)
   length=np.linalg.norm(np.diff(pts,axis=0),axis=1).sum();score-=length*.0002
   if best is None or score>best['score']:best={'controls':[c1.tolist(),c2.tolist()],'root':root.tolist(),'end':end.tolist(),'route_clearance':clear,'host_gap':hostgap,'score':score,'curvature_radius':float(rad.min())}
  plans[name+'_'+str(sign)]=best;previous.extend((w@np.array([root,*best['controls'],end]))@world[:3,:3].T+world[:3,3]);print(name,sign,best,flush=True)
 (SRC/'lib/palm_dorsal_bank_paths.json').write_text(json.dumps(plans,indent=2)+'\n')
