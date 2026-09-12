"""Three finished bushing sizes, each a separate closed polished body."""
from cadgen import build123d as bd, step
from lib.bushing import make_bushing

@step(out="../../STEP/anthropomorphic_hand/bushing_review.step",
      mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def bushing_review():
    return bd.Compound(label="polished_flanged_bushing_family",children=[
        bd.Pos(-10,0,0)*make_bushing(label="finger_eye_5mm_OD_2mm_shaft"),
        make_bushing(3.25,1.53,2.0,3.55,.20,label="palm_eye_6_5mm_OD_3mm_shaft"),
        bd.Pos(12,0,0)*make_bushing(5.0,3.03,3.0,5.45,.28,label="wrist_eye_10mm_OD_6mm_shaft"),
    ])

if __name__=="__main__":
    bushing_review()
