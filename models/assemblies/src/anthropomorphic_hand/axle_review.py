"""Resolved axle family: two finger stubs, a wrist journal, a locating dowel."""
from cadgen import build123d as bd, step
from lib.axle import make_axle,make_dowel

@step(out="../../STEP/anthropomorphic_hand/axle_review.step",mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def axle_review():
    return bd.Compound(label="polished_axle_and_dowel_family",children=[
        bd.Pos(-9,0,0)*make_axle(3.5,label="finger_3_5mm_stub_axle"),
        bd.Pos(-4,0,0)*make_axle(6,label="finger_6mm_stub_axle"),
        bd.Pos(6,0,0)*make_axle(12,3,label="wrist_12mm_axle"),
        bd.Pos(-6,-5,0)*make_dowel(4,label="finger_4mm_location_dowel"),
    ])

if __name__=="__main__":axle_review()
