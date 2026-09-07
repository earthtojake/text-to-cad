import sys,json,gzip
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'src/anthropomorphic_hand'))
from lib.layout import JOINTS,assembled_transforms
from lib.finger_routing import transform_path
from lib.path_analysis import sample_path
from check_hand_route_pairs import group_radius
manifest=json.loads((ROOT/'static_route_packet_manifest.json').read_text())
joints=[j for j in JOINTS if j.name=='thumb_cmc_abduction'];bands=[(float(z),float(z+1)) for z in range(0,25)]
rows={str(b):{'minimum_safe_outer_radius':1e6} for b in bands};cache={}
for si,s in enumerate(manifest['rows']):
 packet=json.loads(gzip.decompress(Path(s['file']).read_bytes()));fk=assembled_transforms(s['pose'])
 for j in joints:
  origin=np.asarray(j.origin);inv=np.linalg.inv(fk[j.parent]);zlo,zhi=0.,25.
  for route in packet['routes']:
   for group in route['groups']:
    path=transform_path(group['path'],inv); points=[]
    for seg in path:
     
     if seg['kind']=='bezier':points.extend(seg['points'])
     elif seg['kind']=='line':points.extend([seg['start'],seg['end']])
     else:
      c=np.asarray(seg['center']);rr=np.linalg.norm(np.asarray(seg['start'])-c);points.extend([c-rr,c+rr])
    a=np.asarray(points)-origin;rad=group_radius(group)
    if a[:,2].max()<zlo-rad or a[:,2].min()>zhi+rad or a[:,0].min()>5 or a[:,0].max()<-5 or a[:,1].min()>5 or a[:,1].max()<-5:continue
    key=json.dumps(path,sort_keys=True)
    if key not in cache:cache[key]=sample_path(path,.1)
    cloud=cache[key]-origin
    for band in bands:
     near=cloud[(cloud[:,2]>=band[0]-rad-.05)&(cloud[:,2]<=band[1]+rad+.05)]
     if not len(near):continue
     r=np.linalg.norm(near[:,:2],axis=1);mi=int(np.argmin(r));safe=float(r[mi]-rad-.050001)
     if safe<rows[str(band)]['minimum_safe_outer_radius']:
      rows[str(band)]={'minimum_safe_outer_radius':safe,'sample':s['label'],'tendon':route['name'],'group':group['label'],'point':near[mi].tolist(),'tube_radius':rad,'axial_band':band}
 if si%10==0:print(si,rows,flush=True)
(ROOT/'cmc_axial_radial_envelopes.json').write_text(json.dumps({'sample_count':225,'method':'0.1 mm conservative curve sampling; expanded axial band and 0.050001 mm radial reserve','rows':rows},indent=2))
print('FINAL',json.dumps(rows),flush=True)
