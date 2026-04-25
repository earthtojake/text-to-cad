from build123d import Compound

from mimo_case_print_ready_geometry import (
    PrintReadyParams,
    front_anchor,
    front_back_halves_raw,
    pcb_in_case_raw,
    validate_print_ready_alignment,
    viewer_aligned,
)


def _screen_center_xy(params: PrintReadyParams) -> tuple[float, float]:
    center_x, center_y, _ = front_anchor(params.screen_u, params.screen_v)
    return (center_x, center_y)


def gen_step():
    params = PrintReadyParams()
    screen_center_xy = _screen_center_xy(params)
    validate_print_ready_alignment(params=params, screen_center_xy=screen_center_xy)

    back_half, front_half = front_back_halves_raw(params=params, screen_center_xy=screen_center_xy)
    pcb = pcb_in_case_raw()

    shape = viewer_aligned(Compound([back_half, front_half, pcb]))
    shape.label = "mimo-case-print-ready-assembled"
    return {
        "shape": shape,
        "step_output": "mimo_case_print_ready_assembled.step",
    }
