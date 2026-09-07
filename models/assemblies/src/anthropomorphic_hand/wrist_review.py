from cadgen import build123d as bd,step
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings
from lib.pulley import make_pulley
@step(out='../../STEP/anthropomorphic_hand/wrist_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.01)
def wrist_review():
    p=[make_wrist_fixed_fork(),make_wrist_yaw_carrier(),make_wrist_palm_cradle()]
    for sign in (-1,1):
        p.append(bd.Pos(0,-9,sign*5.5)*make_pulley(11,bore_radius=3.03,label=f'wrist_yaw_drive_{sign}'))
        p.append(bd.Pos(sign*14,0,0)*bd.Rot(0,90,0)*bd.Rot(0,0,90)*make_pulley(11,bore_radius=3.03,label=f'wrist_flex_drive_{sign}'))
    p += [b for frame,b in make_wrist_bushings()]
    return bd.Compound(label='skeletal_wrist',children=p)
if __name__=='__main__':wrist_review()
