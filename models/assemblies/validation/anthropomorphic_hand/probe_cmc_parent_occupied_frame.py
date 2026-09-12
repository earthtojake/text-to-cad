import sys
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step
from lib.palm_frame import make_palm_frame_bodies
from check_middle_hardware_paths import bbox_gap
p=[p for p in read_step('models/assemblies/STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step').children if p.label.startswith('thumb_cmc_parent_')]
h=[b for b in make_palm_frame_bodies() if 'palmar_clamp' in b.label]
for a in p:
 for b in h:
  if bbox_gap(a.bounding_box(),b.bounding_box())>.001:continue
  c=a&b;print(a.label,b.label,sum(s.volume for s in c.solids()) if c else 0.,flush=True)
