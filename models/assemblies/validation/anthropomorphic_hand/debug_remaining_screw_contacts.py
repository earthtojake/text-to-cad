import sys,json,gzip
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from check_remaining_guide_routes import frame
from check_guide_mount_mutual import leaves
from cadgen import read_step
from lib.layout import transforms,THUMB_CMC
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());entries={e['label']:e for e in manifest['rows']}
for name in('thumb_base','cup_guide'):
 report=json.loads((HERE/(name+'_route_report.json')).read_text());parts={p.label:p for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand'/(name.replace('cup_guide','cup_guide')+'_mounts_review.step' if name=='thumb_base' else 'cup_guide_mounts_review.step')))}
 for row in report['rows']:
  for c in row['collisions']:
   if 'screw' not in c['body']:continue
   packet=json.load(gzip.open(entries[row['label']]['file'],'rt'));r=next(r for r in packet['routes'] if r['name']==c['route']);g=next(g for g in r['groups'] if g['label']==c['group']);p=parts[c['body']]
   path=transform_path(g['path'],np.linalg.inv(transforms(row['pose'])[frame(p.label)]));wire=path_wire(path)
   a,b=p.closest_points(wire);print(name,row['label'],p.label,'screwpoint',tuple(a),'wirepoint',tuple(b),'bbox',p.bounding_box(optimal=False),flush=True)
