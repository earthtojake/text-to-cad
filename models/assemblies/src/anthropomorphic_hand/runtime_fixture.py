"""A real continuous STEP swept tube for flexible-animation integration checks."""
from cadgen import build123d as bd
from cadgen import step


@step(out="../../STEP/anthropomorphic_hand/runtime_fixture.step")
def runtime_fixture():
    centerline = bd.Edge.make_line((0, 0, 8), (60, 0, 8))
    profile = bd.Plane(origin=(0, 0, 8), z_dir=(1, 0, 0)) * bd.Circle(0.8)
    tube = bd.sweep(profile, path=centerline)
    tube.label = "continuous_swept_tube"
    tube.color = bd.Color(0.86, 0.32, 0.11)
    start = bd.Pos(0, 0, 8) * bd.Sphere(1.2)
    start.label = "fixed_start_marker"
    start.color = bd.Color(0.18, 0.2, 0.23)
    return bd.Compound(children=[tube, start])


if __name__ == "__main__":
    runtime_fixture()
