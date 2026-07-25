"""Non-printable fit preview of the standalone ST3215 motor bay."""

from build123d import import_step
from cadpy.assembly import AssemblyHelper

from ST3215_rear_motor_bay import ST3215_SERVO_STEP
from ST3215_rear_motor_bay import gen_step as gen_motor_bay
from ST3215_rear_motor_bay import st3215_installed_location


def gen_step():
    """Return a labeled assembly containing the bay and exact catalog servo."""
    bay = gen_motor_bay()
    servo = import_step(ST3215_SERVO_STEP).moved(st3215_installed_location())

    assembly = AssemblyHelper("st3215_rear_motor_bay_fit_preview")
    assembly.add(bay, "st3215_rear_motor_bay")
    assembly.add(servo, "waveshare_feetech_st3215_servo")
    return assembly.build()
