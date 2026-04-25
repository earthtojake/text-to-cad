from build123d import Compound

from mimo_case_geometry import (
    back_puck,
    back_anchor,
    BACK_PUCK_BACK_U,
    BACK_PUCK_BACK_V,
    BACK_PUCK_BACK_Z_OFFSET,
    front_back_shell_halves_raw,
    side_button,
    BUTTON_TOP_RIGHT_V,
    BUTTON_MID_RIGHT_V,
    BUTTON_BOTTOM_RIGHT_V,
    viewer_aligned,
)
from mimo_pcb_geometry import pcb_in_case_raw, validate_pcb_mount_holes, validate_usb_alignment


def gen_step():
    validate_pcb_mount_holes()
    validate_usb_alignment()

    back_half, front_half = front_back_shell_halves_raw()
    shape = Compound(
        [
            back_half,
            front_half.translate((0.0, 0.0, 10.0)),
            pcb_in_case_raw(),
            back_puck().translate(back_anchor(BACK_PUCK_BACK_U, BACK_PUCK_BACK_V, z_offset=BACK_PUCK_BACK_Z_OFFSET)),
            side_button(BUTTON_TOP_RIGHT_V),
            side_button(BUTTON_MID_RIGHT_V),
            side_button(BUTTON_BOTTOM_RIGHT_V),
        ]
    )

    return {
        "shape": viewer_aligned(shape),
        "step_output": "mimo_case_pcb_integration.step",
    }
