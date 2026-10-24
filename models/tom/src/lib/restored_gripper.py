"""Approved mirrored case-flange pattern at the restored gripper's datums.

Reuses the reversible frame factory while keeping this assembly's original
case mounting height, horn arms and payload placements. Later flange lifts
in the shoulder experiments are not part of this configuration.
"""
from end_effector.gripper_frame_template import _make_end_for_end_case_mount
from lib.restored_frame_gauge import with_sheet_stock, CASE_SERVO_ORIGIN_MM
from lib.servo_case_flange import case_hole_centers, CASE_MIRROR_X_MM
from lib.shoulder_yaw_notches import notch_horn_arms

# Case holes and reversal derive from the same vendor interface as the
# link feet and static claw. Only the placement is specific to this frame.
CASE_MIRROR_Y_MM = CASE_SERVO_ORIGIN_MM[1] + CASE_MIRROR_X_MM
REVERSIBLE_HOLES = tuple(sorted(
    (CASE_SERVO_ORIGIN_MM[0]-z,CASE_SERVO_ORIGIN_MM[1]+x,sign)
    for side,sign in (('lower',1),('upper',-1))
    for x,_y,z in case_hole_centers(side,z_sign=-1,reversible=True)
))


def mirrored_frame(original_frame):
    """The unchanged reversible frame used by the shoulder yaw assembly."""
    frame = _make_end_for_end_case_mount(
        original_frame, mirror_y_mm=CASE_MIRROR_Y_MM,
        hole_centers=REVERSIBLE_HOLES,
    )
    frame = notch_horn_arms(with_sheet_stock(frame))
    frame.label = original_frame.label
    frame.color = original_frame.color
    return frame


