import sys,json
from pathlib import Path
HERE=Path(__file__).parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand';sys.path.insert(0,str(SRC))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.transport_guide import path_wire
from check_remaining_guide_routes import ExactBodyDistance
DATA=json.loads((SRC/'lib/cmc_parent_reliefs.json').read_text())
for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step')):
 if p.label not in DATA:continue
 ts=[];dist=ExactBodyDistance(p);kept=[]
 for e in DATA[p.label]:
  w=path_wire([e['segment']])
  if dist.distance(w,e['radius'])>e['radius']+.001:continue
  kept.append(e);ts.append(bd.sweep(bd.Plane(origin=w.position_at(0),z_dir=w.tangent_at(0))*bd.Circle(e['radius']),path=w))
 DATA[p.label]=kept
 q=p.cut(*ts);print(p.label,'TOOLS',len(ts),'ORIGINAL',p.volume,'RESULT',[(s.volume,s.is_valid,s.bounding_box()) for s in q.solids()],flush=True)

(SRC/'lib/cmc_parent_reliefs.json').write_text(json.dumps(DATA,indent=2)+'\n')
