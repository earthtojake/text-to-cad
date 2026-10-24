"""Carry the jaw mechanism with the centered gripper-only case envelope."""
import build123d as bd
from common.gripper_frame import gripper_frame
from lib.restored_claw_refinement import fixed_claw, moving_claw
from lib.gripper_frame_layout import GRIPPER_CARRIED_SHIFT_MM
from lib.gripper_horn_phase import square_at_closed


def with_centered_frame(original):
    shift = bd.Pos(*GRIPPER_CARRIED_SHIFT_MM)
    frame = gripper_frame()
    frame.label = 'gripper_frame'
    return bd.Compound(children=[frame,
        square_at_closed(original.children[1]).moved(shift),
        fixed_claw(original.children[2]).moved(shift),
        moving_claw(original.children[3]).moved(shift)], label=original.label)
