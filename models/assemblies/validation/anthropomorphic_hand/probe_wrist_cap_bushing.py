import sys
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step
from check_guide_mount_mutual import leaves
from lib.wrist import make_wrist_bushings
p=next(p for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/wrist_guide_mounts_review.step')) if p.label=='wrist_flexion_drive_mouth_-1_host_cap');b=next(p for f,p in make_wrist_bushings() if p.label=='wrist_flex_bushing_-1');q=p-b
common=p&b;volume=0. if common is None else common.volume
import json
r={'pass':volume<=1e-7,'cap':p.label,'bushing':b.label,'intersection_mm3':volume,'cap_body_count':len(p.solids())};(HERE/'wrist_bushing_cap_fit.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)
assert r['pass']
