from pathlib import Path
from cadgen import build123d as bd,step,read_step
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location
from lib.finish import finish
BASE=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand'
def leaves(s):return [x for c in s.children for x in leaves(c)] if s.children else [s]
def candidate_bodies():
    f=FINGERS[1];place=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)
    host=finish(place*read_step(BASE/'phalanx_continuous_r5.step'),'aluminum','middle_proximal_frame')
    return [host,*leaves(read_step(BASE/'phalanx_continuous_supports_r5.step'))]
@step(out='../../STEP/anthropomorphic_hand/phalanx_continuous_representative_r5.step',mesh_tolerance=.001,mesh_angular_tolerance=.018)
def phalanx_continuous_representative_r5():return bd.Compound(label='continuous_rail_and_actual_guide_supports',children=candidate_bodies())
if __name__=='__main__':phalanx_continuous_representative_r5()
