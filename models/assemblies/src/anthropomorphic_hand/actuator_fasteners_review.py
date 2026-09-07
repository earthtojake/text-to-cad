"""All assembled actuator and reaction-frame fastener occurrences."""
from cadgen import step,build123d as bd
from lib.actuator_fasteners import actuator_fasteners

@step(out='../../STEP/anthropomorphic_hand/actuator_fasteners_review.step')
def actuator_fasteners_review():
    return bd.Compound(label='all_actuator_and_frame_fasteners',children=[p for p,frame,system,kind in actuator_fasteners()])

if __name__=='__main__':actuator_fasteners_review()
