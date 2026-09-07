import sys,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.palm_frame import make_palm_frame_bodies
from lib.layout import THUMB_CMC
from lib.guide_mounts import _sweep
base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45);host=base.inverse()*make_palm_frame_bodies()[0];plans=json.loads((HERE.parents[1]/'src/anthropomorphic_hand/lib/thumb_fixed_anchors.json').read_text());other=[base.inverse()*p for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_base_mounts_review.step')) if p.label.startswith(('thumb_radial_shared','thumb_wrist_splice'))]
for sign in(-1,):
 plan=plans[str(sign)];end=np.array(plan['anchor'])+[1.88,0,-.85]
 for i,y in enumerate((-24,)):
  root=[sign*2.27,y,sign*7-.36];arm=_sweep([root,*plan['arms'][i]['controls'],end],.25);trim=arm-host;print(sign,y,'VALID',arm.is_valid,'ORIGINAL',arm.volume,'PARTS',[(s.volume,s.bounding_box()) for s in trim.solids()],flush=True)
  for p in other:
   common=arm&p
   if common is not None and common.volume>1e-7:print('OTHER',p.label,common.volume,flush=True)
