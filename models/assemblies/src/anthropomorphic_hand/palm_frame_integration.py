"""Publish the reviewed native palm as the assembly's declared STEP input.

Construction lives in palm_frame_candidate_review.py and lib/palm_frame_candidate.py.
The split keeps complete hand assembly builds from repeating route relief Booleans.
"""
from pathlib import Path
from cadgen import step,read_step
@step(out='../../STEP/anthropomorphic_hand/imported/palm_frame_integration.step')
def palm_frame_integration():
    return read_step(Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand/palm_frame_candidate_review.step')
if __name__=='__main__':palm_frame_integration()
