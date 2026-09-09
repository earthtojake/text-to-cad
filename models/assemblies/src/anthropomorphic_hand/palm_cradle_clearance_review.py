"""Strict inspection target for the headed-shaft withdrawal relief."""
from cadgen import step
from lib.wrist import make_wrist_palm_cradle
@step(out='../../STEP/anthropomorphic_hand/palm_cradle_clearance_review.step')
def palm_cradle_clearance_review():return make_wrist_palm_cradle()
if __name__=='__main__':palm_cradle_clearance_review()
