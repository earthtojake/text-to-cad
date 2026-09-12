"""Middle MCP carrier with its actual adjacent phalanx and crossed drums."""
from cadgen import build123d as bd, step
from lib.universal_carrier import make_universal_carrier
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.layout import MCP_YAW_DRIVE_PLANES

@step(out='../../STEP/anthropomorphic_hand/universal_carrier_review.step',
      mesh_tolerance=.001,mesh_angular_tolerance=.008)
def universal_carrier_review():
    children=[make_universal_carrier(),make_phalanx(45,18)]
    for sign in (-1,1):
        children.append(bd.Pos(sign*.9,0,0)*bd.Rot(0,90,0)*make_pulley(5.5,label=f'flex_drive_{sign}'))
        children.append(bd.Pos(0,0,MCP_YAW_DRIVE_PLANES[0 if sign==1 else 1])*make_pulley(5.5,label=f'yaw_drive_{sign}'))
    return bd.Compound(label='universal_carrier_in_joint_context',children=children)

if __name__=='__main__':universal_carrier_review()
