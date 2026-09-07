"""Three removable palm pads and two complete palm-to-wrist fastener sets."""
from cadgen import build123d as bd,step
from lib.palm_hardware import make_palm_hardware
@step(out='../../STEP/anthropomorphic_hand/palm_hardware_review.step',mesh_tolerance=.006,mesh_angular_tolerance=.06)
def palm_hardware_review():return bd.Compound(label='palm_contact_and_wrist_mount_hardware',children=make_palm_hardware())
if __name__=='__main__':palm_hardware_review()
