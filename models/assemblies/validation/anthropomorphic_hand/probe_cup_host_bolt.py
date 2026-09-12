import sys
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.palm_frame import make_palm_frame_bodies
host=make_palm_frame_bodies()[0]
for p in leaves(read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/cup_guide_mounts_review.step')):
 if p.label=='little_cup_fixed_bank_-1_host_M0p6_screw':
  common=p&host;print('V',common.volume,'BB',common.bounding_box(),flush=True)
