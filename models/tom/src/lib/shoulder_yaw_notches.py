"""Horn-concentric outline, shared by the shoulder and gripper frames."""
import build123d as bd
from lib.booleans import as_single_shape
from lib.servo_fit import SERVO
from lib.horn_neck import circle_neck_outline
from lib.horn_cap import FRAME_HORN_CAP_DIAMETER_MM
from lib.yoke_design_rules import COLLAR_NECK_WIDTH_MM
from lib import sheet_rule_scs as scs
from lib.restored_frame_gauge import WALL_FACE_X_MM

HORN_CENTER_NATIVE_X_MM = SERVO.horn_axis_x_mm
HORN_OUTLINE_RADIUS_MM = FRAME_HORN_CAP_DIAMETER_MM/2
WALL_OUTSIDE_X_MM = WALL_FACE_X_MM-scs.THICKNESS_MM
HORN_ARM_CUT_BANDS_Y_MM = ((0.0,12.5496),(41.9152,60.0))


def notch_horn_arms(shape):
    """Trim the inboard cap and neck, retaining the finished fork tips."""
    for y0,y1 in HORN_ARM_CUT_BANDS_Y_MM:
        window = bd.Solid.make_box(HORN_CENTER_NATIVE_X_MM-WALL_OUTSIDE_X_MM,y1-y0,80,
            bd.Plane(origin=(WALL_OUTSIDE_X_MM,y0,-40)))
        outline = circle_neck_outline(
            center=(HORN_CENTER_NATIVE_X_MM,y0,0),
            radius_mm=HORN_OUTLINE_RADIUS_MM, neck_width_mm=COLLAR_NECK_WIDTH_MM,
            neck_start_mm=WALL_OUTSIDE_X_MM-HORN_CENTER_NATIVE_X_MM,
            along=(1,0,0), across=(0,0,1))
        envelope = bd.Solid.extrude(bd.Face(outline),(0,y1-y0,0))
        tool = window.cut(envelope)
        shape = as_single_shape(shape.cut(tool)).clean()
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError('Horn-concentric frame must remain one valid solid')
    return shape
