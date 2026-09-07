import sys,json,gzip
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from check_remaining_guide_routes import frame,near_segments
from check_guide_mount_mutual import leaves
from cadgen import read_step
from lib.layout import transforms,THUMB_CMC,FINGERS,finger_fan_matrix
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());entries={e['label']:e for e in manifest['rows']}
f=next(f for f in FINGERS if f.name=='little');cupworld=finger_fan_matrix(f)@np.array([[1,0,0,f.x],[0,1,0,f.base_y],[0,0,1,0],[0,0,0,1]])
a=np.pi/4;thumbworld=np.eye(4);thumbworld[:3,:3]=[[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]];thumbworld[:3,3]=THUMB_CMC
for name,file in [('cup_guide','cup_guide_route_previous.step'),('thumb_base','thumb_base_mounts_review.step')]:
 if len(sys.argv)>1 and name!=sys.argv[1]:continue
 report=json.loads((HERE/(name+'_route_report.json')).read_text());parts={p.label:p for p in leaves(read_step(ROOT/'STEP/anthropomorphic_hand'/file))}
 for row in report['rows']:
  for c in row['collisions']:
   if name=='cup_guide' and row['label']!='palm_cup_25':continue
   packet=json.load(gzip.open(entries[row['label']]['file'],'rt'));r=next(r for r in packet['routes'] if r['name']==c['route']);g=next(g for g in r['groups'] if g['label']==c['group']);p=parts.get(c['body'])
   if p is None:p=max((p for n,p in parts.items() if n.startswith(c['body'].rsplit('_',1)[0])),key=lambda p:p.volume)
   path=transform_path(g['path'],np.linalg.inv(transforms(row['pose'])[frame(p.label)]));bb=p.bounding_box(optimal=False)
   for seg in near_segments(path,np.array(tuple(bb.min)),np.array(tuple(bb.max)),.475):
    wire=path_wire([seg]);d=p.distance_to(wire)
    if d<.45:
     aa,bb=p.closest_points(wire);mat=np.linalg.inv(cupworld if name=='cup_guide' else thumbworld);aa=(mat@[*aa,1])[:3];bb=(mat@[*bb,1])[:3];print(name,row['label'],p.label,c['group'],'bodypoint',aa.tolist(),'wirepoint',bb.tolist(),'distance',d,flush=True);break
