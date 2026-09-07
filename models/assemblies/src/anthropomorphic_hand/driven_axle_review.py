"""Keyed through shafts and separate universal-joint yaw stub, native +Z."""
from cadgen import build123d as bd, step
from lib.axle import make_driven_axle

@step(out='../../STEP/anthropomorphic_hand/driven_axle_review.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def driven_axle_review():
    return bd.Compound(label='D_keyed_drive_axle_family',children=[
        bd.Pos(-6,0,0)*make_driven_axle(26,label='finger_26mm_through_drive_shaft'),
        make_driven_axle(20,label='finger_20mm_through_drive_shaft'),
        bd.Pos(6,0,0)*make_driven_axle(6,label='yaw_6mm_independent_keyed_stub'),
    ])

if __name__=='__main__':driven_axle_review()
