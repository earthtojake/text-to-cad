import sys
import numpy as np
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
from lib.drive_terminal import terminal_placements,make_terminal_pulley_parts
from lib.layout import transforms
from lib.assembly import matrix_location
from check_guide_combs import common_volume
row=next(r for r in terminal_placements() if r['name']=='wrist_flexion_positive');p=row['placement']*make_terminal_pulley_parts(row['radius'],row['bore_radius'],row['angle'],row['direction'])[0]
parts=leaves(read_step(ROOT/'STEP/anthropomorphic_hand/wrist_guide_mounts_review.step'));s=next(p for p in parts if p.label=='wrist_abduction_drive_mouth_-1_liner_+1_M0p6_screw')
for offset in(-.3,):
 axis=(12.05+offset,-15,-5.5);shank=bd.Pos(*axis)*bd.Cylinder(.20,1.08);head=bd.Pos(axis[0],axis[1],axis[2]+.74)*bd.fillet(bd.Cylinder(.40,.4).edges(),.045);socket=bd.Pos(axis[0],axis[1],axis[2]+.94)*bd.extrude(bd.RegularPolygon(.17,6),amount=-.23);bolt=shank.fuse(head)-socket;bolt=bd.Pos(*axis)*bd.Rot(180,0,0)*bd.Pos(*(-np.array(axis)))*bolt
 for flex in(-45,):
  h=matrix_location(transforms({'wrist_abduction':-20,'wrist_flexion':flex})['wrist_flexion'])*(row['placement']*bd.Cylinder(11.7,1.7));print(offset,flex,common_volume(bolt,h),(bolt&h).bounding_box(),flush=True)
  for rr in(.35,.32):print('HEAD',rr,common_volume(bolt & (bd.Pos(*axis)*bd.Cylinder(rr,4)),h),flush=True)
