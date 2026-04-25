from mimo_pcb_geometry import pcb_shape, validate_pcb_mount_holes, validate_usb_alignment


def gen_step():
    validate_pcb_mount_holes()
    validate_usb_alignment()

    return {
        "shape": pcb_shape(),
        "step_output": "mimo_pcb.step",
    }
