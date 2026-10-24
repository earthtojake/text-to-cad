"""Shared case/horn datums for the selected ST3215 engineering STEP, in mm.

Robotopian ST3215-20200328-to-customer, SHA-256
9622b2a7bc01af8fbb181de67c801ba9d02a584372a129f8423391233c63eebc.
See SERVO_ALTERNATIVES.md. Common ST3215/STS3250 fit envelope; case threads differ.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServoInterface:
    horn_lower_y_mm: float = -27.4
    horn_upper_y_mm: float = 9.2
    case_lower_y_mm: float = -25.6
    case_upper_y_mm: float = 6.4
    horn_axis_x_mm: float = -25.5
    horn_axis_z_mm: float = 0.0
    horn_diameter_mm: float = 19.95
    case_lower_hole_x_mm: tuple[float, ...] = (-17.2, 7.25)
    case_upper_hole_x_mm: tuple[float, ...] = (-17.2, 3.5)
    case_hole_z_mm: float = 10.25
    case_skin_protrusion_mm: float = 1.1  # conservative each side beyond mounting pad
    # Measured far-end envelope of the vendor middle-case shell, including draft.
    middle_case_end_x_mm: float = 9.6125767

    @property
    def horn_span_mm(self) -> float:
        return self.horn_upper_y_mm - self.horn_lower_y_mm

    @property
    def horn_mid_y_mm(self) -> float:
        return (self.horn_upper_y_mm + self.horn_lower_y_mm) / 2

    @property
    def case_span_mm(self) -> float:
        return self.case_upper_y_mm - self.case_lower_y_mm

    @property
    def case_mid_y_mm(self) -> float:
        return (self.case_upper_y_mm + self.case_lower_y_mm) / 2


SERVO = ServoInterface()
# Direct mounting, as requested: sheet mounting faces meet the measured servo
# mounting faces. Manufacturing variation must not be hidden in spacer stacks.
HORN_MOUNT_GAP_MM = 0.0
CASE_MOUNT_GAP_MM = 0.0
