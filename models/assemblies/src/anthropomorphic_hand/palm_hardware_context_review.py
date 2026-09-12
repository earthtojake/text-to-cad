"""Accepted palm, cupping ray and wrist cradle with removable contact hardware."""
from pathlib import Path
from cadgen import build123d as bd,step,read_step
@step(out='../../STEP/anthropomorphic_hand/palm_hardware_context_review.step',mesh_tolerance=.006,mesh_angular_tolerance=.06)
def palm_hardware_context_review():
    base=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand'
    return bd.Compound(label='palm_with_removable_pads_and_mounts',children=[read_step(base/(p+'.step')) for p in ('imported/palm_frame_integration','palm_little_review','palm_cradle_clearance_review','palm_hardware_review')])
if __name__=='__main__':palm_hardware_context_review()
