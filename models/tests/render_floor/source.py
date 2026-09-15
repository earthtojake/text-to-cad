from cadgen import build123d as bd
from cadgen import step

@step(out="floor_positions.step")
def floor_positions():
    parts = []
    for label, x, z, color in [
        ("below_origin", -42, -30, (0.12, 0.38, 0.75)),
        ("crosses_origin", 0, -10, (0.12, 0.58, 0.32)),
        ("above_origin", 42, 30, (0.9, 0.25, 0.08)),
    ]:
        part = bd.Solid.make_box(24, 24, 20).moved(bd.Location((x, 0, z)))
        part.label = label
        part.color = bd.Color(*color)
        parts.append(part)
    return bd.Compound(children=parts)

if __name__ == "__main__":
    floor_positions()
