from cadgen import build123d as bd
from cadgen import step, glb

LENGTH, WIDTH, HEIGHT, WALL = 60.0, 40.0, 25.0, 2.0
BOSS_OD, BOSS_HOLE = 5.5, 2.5
BOSS_HEIGHT = HEIGHT - WALL
HOLE_DEPTH = BOSS_HEIGHT - 3.0
BOSS_X = LENGTH / 2 - WALL - BOSS_OD / 2 + 0.25
BOSS_Y = WIDTH / 2 - WALL - BOSS_OD / 2 + 0.25
NOTCH_WIDTH, NOTCH_DEPTH = 12.0, 10.0


@step(out="../out/enclosure_brep.step")
@glb(out="../out/enclosure_brep.glb")
def enclosure_brep():
    outer = bd.Pos(0, 0, HEIGHT / 2) * bd.Box(LENGTH, WIDTH, HEIGHT)
    cavity = bd.Pos(0, 0, (HEIGHT - WALL) / 2) * bd.Box(LENGTH - 2 * WALL, WIDTH - 2 * WALL, HEIGHT - WALL)
    shell = outer - cavity
    for sx in (-1, 1):
        for sy in (-1, 1):
            shell = shell + bd.Pos(sx * BOSS_X, sy * BOSS_Y, BOSS_HEIGHT / 2) * bd.Cylinder(BOSS_OD / 2, BOSS_HEIGHT)
            shell = shell - bd.Pos(sx * BOSS_X, sy * BOSS_Y, HOLE_DEPTH / 2) * bd.Cylinder(BOSS_HOLE / 2, HOLE_DEPTH)
    profile = bd.Plane.XZ * bd.fillet(bd.Rectangle(NOTCH_WIDTH, 2 * NOTCH_DEPTH).vertices(), NOTCH_WIDTH / 2 - 0.01)
    notch = bd.Pos(0, -WIDTH / 2, 0) * bd.extrude(profile, amount=1.5 * WALL, both=True)
    shape = shell - notch
    shape.label = "enclosure"
    return shape


if __name__ == "__main__":
    enclosure_brep()
