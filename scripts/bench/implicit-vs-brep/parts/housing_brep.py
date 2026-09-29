from cadgen import build123d as bd
from cadgen import step, glb


@step(out="../out/housing_brep.step")
@glb(out="../out/housing_brep.glb")
def housing_brep():
    body = bd.Box(30, 30, 20)
    body = body.fillet(2, body.edges())
    bore = bd.Cylinder(8, 40)
    boss = bd.Pos(0, 0, 14) * bd.Cylinder(5, 8)
    shape = body - bore + boss
    for sx in (-1, 1):
        for sy in (-1, 1):
            shape = shape - bd.Pos(11 * sx, 11 * sy, 0) * bd.Cylinder(1.6, 30)
    shape.label = "housing"
    return shape


if __name__ == "__main__":
    housing_brep()
