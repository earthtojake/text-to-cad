from cadgen import build123d as bd,step
from lib.yaw_guide_mounts import make_yaw_reaction_mounts
from lib.universal_carrier import make_universal_carrier
from lib.pulley import make_pulley
@step(out='../../STEP/anthropomorphic_hand/yaw_guide_macro_review.step',mesh_tolerance=.0005,mesh_angular_tolerance=.01)
def yaw_guide_macro_review():
 parts=make_yaw_reaction_mounts(18,'index_mcp');parts.append(make_universal_carrier(phalanx_width=18,label='index_mcp_actual_carrier'))
 for sign in(-1,1):
  p=bd.Pos(sign*.9,0,0)*bd.Rot(0,90,0)*make_pulley(5.5);p.label='index_mcp_flexion_'+str(sign)+'_actual_pulley';parts.append(p)
 return bd.Compound(label='mounted_index_yaw_mouth_macro',children=parts)
if __name__=='__main__':yaw_guide_macro_review()
