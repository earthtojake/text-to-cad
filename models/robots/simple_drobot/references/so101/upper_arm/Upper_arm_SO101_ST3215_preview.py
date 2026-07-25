"""Installed-fit preview of the editable SO-101 upper arm and ST3215 servo."""

from pathlib import Path

from build123d import import_step
from cadpy.assembly import AssemblyHelper

from Upper_arm_SO101_editable import gen_step as gen_upper_arm
from Upper_arm_SO101_editable import st3215_preview_location


SERVO_STEP = (
    Path(__file__).parents[4]
    / "lekiwi_quadruped"
    / "components"
    / "waveshare_feetech_st3215_servo.step"
)


def gen_step():
    """Return a labeled, non-printable fit preview assembly."""
    arm = gen_upper_arm()
    servo = import_step(SERVO_STEP).moved(st3215_preview_location())

    asm = AssemblyHelper("upper_arm_st3215_fit_preview")
    asm.add(arm, "upper_arm_with_rear_socket")
    asm.add(servo, "waveshare_feetech_st3215_servo")
    return asm.build()
