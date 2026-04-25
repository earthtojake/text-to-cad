from mimo_case_geometry import (
    EXPLODED_BACK_PUCK_OFFSET_Z,
    EXPLODED_BUTTON_OFFSET_X,
    translation_matrix,
)


def gen_step():
    return {
        "instances": [
            {
                "path": "mimo_case_shell.step",
                "name": "shell",
                "transform": translation_matrix(0.0, 0.0, 0.0),
            },
            {
                "path": "mimo_case_back_puck.step",
                "name": "back-puck",
                "transform": translation_matrix(0.0, 0.0, EXPLODED_BACK_PUCK_OFFSET_Z),
            },
            {
                "path": "mimo_case_button_top.step",
                "name": "button-top",
                "transform": translation_matrix(EXPLODED_BUTTON_OFFSET_X, 0.0, 0.0),
            },
            {
                "path": "mimo_case_button_mid.step",
                "name": "button-mid",
                "transform": translation_matrix(EXPLODED_BUTTON_OFFSET_X, 0.0, 0.0),
            },
            {
                "path": "mimo_case_button_bottom.step",
                "name": "button-bottom",
                "transform": translation_matrix(EXPLODED_BUTTON_OFFSET_X, 0.0, 0.0),
            },
        ],
        "step_output": "mimo_case_exploded.step",
    }
