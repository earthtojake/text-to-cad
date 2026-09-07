import sys
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.layout import THUMB_CMC
base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
for fn,prefix in [('thumb_base_mounts_review.step','thumb_cmc_fixed_flex'),('cup_guide_mounts_review.step','little_cup_fixed_bank_-1')]:
 for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand'/fn)):
  if p.label.startswith(prefix):
   local=base.inverse()*p if fn.startswith('thumb') else p
   print(p.label,'V',p.volume,'BB',local.bounding_box(),flush=True)
