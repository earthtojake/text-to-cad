from cadgen import build123d as bd,step
from lib.guide_mounts_continuous_r5 import make_phalanx_comb
from lib.fixed_guide_mounts_continuous_r5 import make_fixed_outlet_pair
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location
@step(out="../../STEP/anthropomorphic_hand/phalanx_continuous_supports_r5.step",mesh_tolerance=.001,mesh_angular_tolerance=.018)
def phalanx_continuous_supports_r5():
    from lib.phalanx_r5_host import warm_host
    warm_host()
    # Avoid OCCT same-domain unification runaway; all strict checks remain required.
    with bd.SkipClean():
        parts=make_phalanx_comb(45,18,12.25,[-4.2,-3,3,4.2],'middle_mcp_outlet_comb')
        parts+=make_phalanx_comb(45,18,32.75,[-4.2,4.2],'middle_pip_inlet_comb')
        parts+=make_fixed_outlet_pair(45,18,4.5,'middle_pip_drive_guide')
        f=FINGERS[1];place=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)
        return bd.Compound(label='continuous_rail_matched_guide_supports',children=[place*s for s in parts])

if __name__=='__main__':phalanx_continuous_supports_r5()
