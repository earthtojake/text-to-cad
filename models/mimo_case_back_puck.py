from mimo_case_geometry import back_puck_shape


def gen_step():
    shape = back_puck_shape()
    shape.label = "back-puck"
    return {
        "shape": shape,
        "step_output": "mimo_case_back_puck.step",
    }
