import sys
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
for q in(-20,-10,0,10,20):
 h=matrix_location(transforms({'wrist_abduction':q,'wrist_flexion':-45})['wrist_flexion'])*p;c=s&h
 if c is not None:print('ORIGINAL',q,c.volume,c.bounding_box(),flush=True)
 for r in(.44,.40,.36):
  v=common_volume(s & (bd.Pos(12.05,-15,-5.5)*bd.Cylinder(r,4)),h);print(q,r,v,flush=True)
