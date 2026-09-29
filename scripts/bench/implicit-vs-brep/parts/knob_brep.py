from cadgen import build123d as bd
from cadgen import step, glb

GRIP_COUNT = 8


@step(out="../out/knob_brep.step")
@glb(out="../out/knob_brep.glb")
def knob_brep():
    outline = bd.Plane.XZ * bd.Polygon((0, 0), (14, 0), (16, 4), (13, 18), (8, 22), (0, 22), align=None)
    body = bd.revolve(outline, axis=bd.Axis.Z)
    for i in range(GRIP_COUNT):
        a, b = bd.Vector(15, 0, 6), bd.Vector(11.5, 0, 20)
        seg = b - a
        grip = bd.Plane(origin=(a + b) * 0.5, z_dir=seg.normalized()) * bd.Cylinder(2.2, seg.length)
        grip = grip + bd.Pos(*a) * bd.Sphere(2.2) + bd.Pos(*b) * bd.Sphere(2.2)
        body = body - grip.rotate(bd.Axis.Z, 360 / GRIP_COUNT * i)
    socket = bd.Pos(0, 0, 4) * bd.extrude(bd.RegularPolygon(3.2, 6), amount=6, both=True)
    boss = bd.Pos(0, 0, 8) * bd.Cylinder(5.5, 12)
    try:
        hollow = bd.offset(body, amount=-1.6, openings=body.faces().sort_by(bd.Axis.Z)[0])
    except Exception as error:  # OCC refuses; report and fall back to the solid body
        import sys
        print(f"[knob_brep] shell failed: {error}", file=sys.stderr)
        hollow = body
    shape = hollow + boss - socket
    shape.label = "knob"
    return shape


if __name__ == "__main__":
    knob_brep()
