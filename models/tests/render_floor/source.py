from cadgen import model

import build123d as bd


@model
def floor_positions():
    parts = []
    for label, x, z, color in [
        ("below_origin", -42, -30, "#61a6e1"),
        ("crosses_origin", 0, -10, "#61c899"),
        ("above_origin", 42, 30, "#f38950"),
    ]:
        part = bd.Solid.make_box(24, 24, 20).moved(bd.Location((x, 0, z)))
        part.label = label
        part.color = bd.Color(color)
        parts.append(part)
    return bd.Compound(children=parts)


if __name__ == "__main__":
    floor_positions()
