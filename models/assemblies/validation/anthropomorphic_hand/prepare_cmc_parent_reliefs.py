import sys,json,gzip,re
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step
from check_remaining_guide_routes import frame,near_segments
from check_guide_mount_mutual import leaves
from lib.layout import transforms
from lib.finger_routing import transform_path
manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text());entries={r['label']:r for r in manifest['rows']};out={}
for name,file,targets in [('thumb_cmc','thumb_cmc_mounts_review.step',{'thumb_cmc_parent_inlet_comb_structural_jaw','thumb_cmc_parent_inlet_comb_palm_rib_lower_cap'})]:
 parts={p.label:p for p in leaves(read_step(ROOT/'STEP/anthropomorphic_hand'/file))};report=json.loads((HERE/(name+'_route_report.json')).read_text())
 for row in report['rows']:
  hits=[c for c in row['collisions'] if c['body'] in targets]
  if not hits:continue
  packet=json.load(gzip.open(entries[row['label']]['file'],'rt'))
  for c in hits:
   p=parts[c['body']];bb=p.bounding_box(optimal=False);g=next(g for r in packet['routes'] if r['name']==c['route'] for g in r['groups'] if g['label']==c['group']);path=transform_path(g['path'],np.linalg.inv(transforms(row['pose'])[frame(p.label)]));rad=.475
   for s in near_segments(path,np.array(tuple(bb.min)),np.array(tuple(bb.max)),rad):
    key=json.dumps({'segment':s,'radius':rad},sort_keys=True);out.setdefault(p.label,{})[key]={'segment':s,'radius':rad}
file=ROOT/'src/anthropomorphic_hand/lib/cmc_parent_reliefs.json';prior=json.loads(file.read_text()) if file.exists() else {}
for name,items in out.items():prior[name]=list(items.values())
file.write_text(json.dumps(prior,indent=2)+'\n');print({name:len(ps) for name,ps in prior.items()})
