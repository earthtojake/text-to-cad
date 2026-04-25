from mimo_case_geometry import shell_shape


def gen_step():
    shape = shell_shape()
    shape.label = "shell"
    return {
        "shape": shape,
        "step_output": "mimo_case_shell.step",
    }
