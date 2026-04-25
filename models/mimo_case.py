from mimo_case_geometry import assembled_shape, validate_assembled_bounds


def gen_step():
    shape = assembled_shape()
    validate_assembled_bounds(shape)

    return {
        "shape": shape,
        "step_output": "mimo_case.step",
    }
