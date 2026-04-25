from build123d import Axis, Compound

from mimo_case_print_ready_geometry import (
    PrintReadyParams,
    front_back_halves_raw,
    sensor_window_geometry,
    validate_print_ready_alignment,
)


def _place_on_bed(shape, x: float, z: float, *, rotate_degrees: float):
    flat_shape = shape.rotate(Axis.X, rotate_degrees)
    bounds = flat_shape.bounding_box()
    center_x = (bounds.min.X + bounds.max.X) / 2.0
    center_z = (bounds.min.Z + bounds.max.Z) / 2.0
    return flat_shape.translate((x - center_x, -bounds.min.Y, z - center_z))


def _validate_print_layout(parts):
    bounds = []
    for label, part in parts:
        box = part.bounding_box()
        bounds.append((label, box.min.X, box.max.X, box.min.Z, box.max.Z, box.min.Y))

    for i, (label_a, min_x_a, max_x_a, min_z_a, max_z_a, _) in enumerate(bounds):
        for label_b, min_x_b, max_x_b, min_z_b, max_z_b, _ in bounds[i + 1 :]:
            separated = max_x_a < min_x_b or max_x_b < min_x_a or max_z_a < min_z_b or max_z_b < min_z_a
            if not separated:
                raise ValueError(f"Print layout parts overlap: {label_a} and {label_b}")

    layout = Compound([part for _, part in parts])
    size = layout.bounding_box().size
    if size.X > 200.0 or size.Z > 170.0:
        raise ValueError(f"Print layout exceeds target bed bounds: {(round(size.X, 3), round(size.Z, 3))}")

    for label, _, _, _, _, min_y in bounds:
        if abs(min_y) > 0.01:
            raise ValueError(f"{label} is not on the print bed: minY={min_y:.3f}")


def gen_step():
    params = PrintReadyParams()
    window_xy, window_w, window_h, _ = sensor_window_geometry(params)
    validate_print_ready_alignment(
        params=params,
        screen_center_xy=window_xy,
        window_size=(window_w, window_h),
    )
    back_half, front_half = front_back_halves_raw(params=params)

    # Layout: open faces up, splayed for a single print plate.
    parts = [
        ("front-shell", _place_on_bed(front_half, -50.0, 0.0, rotate_degrees=-90)),
        ("back-shell", _place_on_bed(back_half, 50.0, 0.0, rotate_degrees=90)),
    ]
    _validate_print_layout(parts)

    shape = Compound([part for _, part in parts])
    shape.label = "mimo-case-print-ready-layout"
    return {
        "shape": shape,
        "step_output": "mimo_case_print_ready_print_layout.step",
    }
