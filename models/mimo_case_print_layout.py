from build123d import Axis, Compound

from mimo_case_geometry import (
    BACK_PUCK_BACK_U,
    BACK_PUCK_BACK_V,
    BACK_PUCK_BACK_Z_OFFSET,
    BUTTON_BOTTOM_RIGHT_V,
    BUTTON_MID_RIGHT_V,
    BUTTON_TOP_RIGHT_V,
    back_anchor,
    back_puck,
    front_back_shell_halves_raw,
    side_button,
)
from mimo_pcb_geometry import pcb_shape_raw, validate_pcb_mount_holes, validate_usb_alignment


def place_on_bed(shape, x: float, z: float):
    flat_shape = shape.rotate(Axis.X, 90)
    bounds = flat_shape.bounding_box()
    center_x = (bounds.min.X + bounds.max.X) / 2.0
    center_z = (bounds.min.Z + bounds.max.Z) / 2.0
    return flat_shape.translate((x - center_x, -bounds.min.Y, z - center_z))


def gen_step():
    validate_pcb_mount_holes()
    validate_usb_alignment()

    back_half, front_half = front_back_shell_halves_raw()
    puck = back_puck().translate(back_anchor(BACK_PUCK_BACK_U, BACK_PUCK_BACK_V, z_offset=BACK_PUCK_BACK_Z_OFFSET))

    shape = Compound(
        [
            place_on_bed(front_half, -62.0, 28.0),
            place_on_bed(back_half, 62.0, 28.0),
            place_on_bed(pcb_shape_raw(), 0.0, -66.0),
            place_on_bed(puck, -58.0, -66.0),
            place_on_bed(side_button(BUTTON_TOP_RIGHT_V), 42.0, -62.0),
            place_on_bed(side_button(BUTTON_MID_RIGHT_V), 54.0, -62.0),
            place_on_bed(side_button(BUTTON_BOTTOM_RIGHT_V), 66.0, -62.0),
        ]
    )

    return {
        "shape": shape,
        "step_output": "mimo_case_print_layout.step",
    }
