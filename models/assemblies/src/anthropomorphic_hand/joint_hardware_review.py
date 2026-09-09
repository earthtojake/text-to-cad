from cadgen import step,build123d as bd
from lib.joint_hardware import joint_hardware
from lib.layout import FINGERS,finger_fan_matrix
from lib.assembly import matrix_location

@step(out='../../STEP/anthropomorphic_hand/joint_hardware_review.step')
def joint_hardware_review():
    fans={f.name:matrix_location(finger_fan_matrix(f)) for f in FINGERS}
    return bd.Compound(label='assembled_driven_joint_hardware',children=[fans[system]*shape if system in fans else shape for shape,frame,system,kind in joint_hardware()])

if __name__=='__main__':joint_hardware_review()
