"""Reaction mouths attached to the universal carrier beside both drive drums."""
from cadgen import build123d as bd,step
from lib.yaw_guide_mounts import make_yaw_reaction_mounts
from lib.universal_carrier import make_universal_carrier
from lib.pulley import make_pulley

@step(out='../../STEP/anthropomorphic_hand/yaw_outlet_mount_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def yaw_outlet_mount_review():
    p=[make_universal_carrier(),*make_yaw_reaction_mounts(18,'middle_mcp')]
    for sign in (-1,1):p.append(bd.Pos(sign*.9,0,0)*bd.Rot(0,90,0)*make_pulley(5.5,label=f'flexion_{sign}_pulley'))
    return bd.Compound(label='yaw_reaction_open_mouth_clamps',children=p)

if __name__=='__main__':yaw_outlet_mount_review()
