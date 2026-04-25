from mimo_case_geometry import top_button_shape


def gen_step():
    shape = top_button_shape()
    shape.label = "button-top"
    return {
        "shape": shape,
        "step_output": "mimo_case_button_top.step",
    }
