"""A complete miniature motor and a separated, readable component set."""
from cadgen import build123d as bd, step
from lib.motor import make_motor_case,make_motor_endcap,make_motor_shaft

@step(out='../../STEP/anthropomorphic_hand/motor_review.step')
def motor_review():
    return bd.Compound(label='miniature_motor_family',children=[
        bd.Pos(-10,0,0)*make_motor_case('assembled_motor_case'),
        bd.Pos(-10,0,0)*make_motor_endcap('assembled_motor_endcap'),
        bd.Pos(-10,0,0)*make_motor_shaft('assembled_motor_shaft'),
        bd.Pos(10,0,0)*make_motor_case('separated_motor_case'),
        bd.Pos(10,0,6)*make_motor_endcap('separated_motor_endcap'),
        bd.Pos(10,0,15)*make_motor_shaft('separated_motor_shaft'),
    ])

if __name__=='__main__':
    motor_review()
