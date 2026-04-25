from mimo_case_geometry import mid_button_shape


def gen_step():
    shape = mid_button_shape()
    shape.label = "button-mid"
    return {
        "shape": shape,
        "step_output": "mimo_case_button_mid.step",
    }
