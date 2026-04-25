from mimo_case_geometry import bottom_button_shape


def gen_step():
    shape = bottom_button_shape()
    shape.label = "button-bottom"
    return {
        "shape": shape,
        "step_output": "mimo_case_button_bottom.step",
    }
