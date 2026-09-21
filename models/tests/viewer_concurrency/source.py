from cadgen import build123d as bd
from cadgen import step

REVISION = 4

@step(out="assembly.step")
def assembly():
    parts = []
    for i in range(32):
        part = bd.Solid.make_box(10 + (i % 4), 12, 3 + REVISION * 0.25 + i * 0.015)
        part = part.cut(bd.Solid.make_cylinder(2 + i * 0.01, 20).moved(bd.Location((5, 6, -5))))
        part.label = f"revision_{REVISION}_plate_{i + 1}"
        part.color = bd.Color(0.25 + (i % 3) * 0.22, 0.45, 0.65)
        parts.append(part.moved(bd.Location(((i % 8) * 18, (i // 8) * 20, 0))))
    return bd.Compound(children=parts)

if __name__ == "__main__":
    assembly()
