from build123d import Compound

from mimo_case_print_ready_geometry import (
    PrintReadyParams,
    front_back_halves_raw,
    pcb_in_case_raw,
    sensor_window_geometry,
    validate_print_ready_alignment,
    viewer_aligned,
)


def gen_step():
    params = PrintReadyParams()
    window_xy, window_w, window_h, _ = sensor_window_geometry(params)
    validate_print_ready_alignment(
        params=params,
        screen_center_xy=window_xy,
        window_size=(window_w, window_h),
    )

    back_half, front_half = front_back_halves_raw(params=params)
    pcb = pcb_in_case_raw()

    shape = viewer_aligned(Compound([back_half, front_half, pcb]))
    shape.label = "mimo-case-print-ready-assembled"
    return {
        "shape": shape,
        "step_output": "mimo_case_print_ready_assembled.step",
    }
