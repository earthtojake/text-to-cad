import sys,json,gzip
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import assembled_transforms,JOINT_BY_NAME
from lib.assembly import joint_location,matrix_location
from lib.retaining_ring import make_retaining_ring
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
from lib.path_analysis import sample_path
manifest=json.loads((ROOT/'static_route_packet_manifest.json').read_text());j=JOINT_BY_NAME['thumb_cmc_abduction'];base=joint_location(j)*bd.Pos(0,0,-9.99)
ring=make_retaining_ring();candidates=[(angle,base*bd.Rot(0,0,angle)*ring) for angle in range(0,360,5)]
mins={a:1e6 for a,_ in candidates};worst={};checks=0;cache={}
for sample in manifest['rows']:
 packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()));inv=np.linalg.inv(assembled_transforms(sample['pose'])[j.name])
 for route in packet['routes']:
  for group in route['groups']:
   if 'cmc_reaction' not in group['label']:continue
   local=transform_path(group['path'],inv);key=json.dumps(local,sort_keys=True)
   if key in cache:continue
   cache[key]=True;cloud=sample_path(local,.2);delta=cloud-np.array(j.origin)-[0,0,-9.99]
   if np.linalg.norm(delta,axis=1).min()-.1>1.9:continue
   wire=path_wire(local)
   for angle,r in candidates:
    d=wire.distance_to(r)-.450001;checks+=1
    if d<mins[angle]:mins[angle]=d;worst[angle]=dict(sample=sample['label'],tendon=route['name'],group=group['label'])
 print(sample['label'],'best',max(mins,key=mins.get),max(mins.values()),flush=True)
report={'sample_count':225,'checks':checks,'rows':[dict(angle=a,minimum_gap=mins[a],worst=worst.get(a)) for a,_ in candidates]};(ROOT/'cmc_dorsal_ring_rotation_probe.json').write_text(json.dumps(report,indent=2))
print('BEST',max(mins,key=mins.get),max(mins.values()),flush=True)
