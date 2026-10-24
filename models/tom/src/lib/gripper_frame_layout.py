"""Case-band centering datums shared by the gripper and shoulder yaw frame."""
from lib.restored_frame_gauge import CASE_BAND_Y_MM, HORN_SEATS_Y_MM

GRIPPER_FRAME_CENTER_Y_MM = sum(HORN_SEATS_Y_MM)/2
GRIPPER_ENVELOPE_SHIFT_Y_MM = GRIPPER_FRAME_CENTER_Y_MM-sum(CASE_BAND_Y_MM)/2
GRIPPER_CARRIED_SHIFT_MM = (0.0,GRIPPER_ENVELOPE_SHIFT_Y_MM,0.0)
# Native placement in the frozen recovered gripper STEP. Both jaw parts and
# the jaw servo already include this band offset before the centering move.
RECOVERED_JAW_BAND_SHIFT_Y_MM = -0.0428
GRIPPER_PINCH_CENTER_IN_CLAW_Y_MM = (GRIPPER_FRAME_CENTER_Y_MM
    -GRIPPER_ENVELOPE_SHIFT_Y_MM-RECOVERED_JAW_BAND_SHIFT_Y_MM)
