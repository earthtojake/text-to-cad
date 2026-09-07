import sys
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.palm_frame import make_palm_frame_bodies
from lib.layout import THUMB_CMC
s=read_step(HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_base_mounts_review.step')
def leaves(s):
 if s.children:
  for p in s.children:yield from leaves(p)
 else:yield s
p=next(p for p in leaves(s) if p.label=='thumb_cmc_yaw_drive_-1_host_M0p6_screw');host=make_palm_frame_bodies()[0];common=p&host;base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
for obj in(p,common):
 local=base.inverse()*obj;print('VOL',obj.volume,'BBOX',local.bounding_box(),flush=True)
