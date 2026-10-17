"""A real continuous STEP swept tube for flexible-animation integration checks."""
import math

import cadgen
from cadgen import build123d as bd
from cadgen import step

_REST = {"normal": [0, 0, 1], "segments": [{"kind": "line", "start": [0, 0, 8], "end": [60, 0, 8]}]}


def _bend(t, m):
    # The 60 mm tube curls into a quarter circle, keeping its length, its braid
    # twisting half a turn along the way.
    angle = t * math.pi / 2
    path = _REST if angle < 1e-8 else {"normal": [0, 0, 1], "segments": [{
        "kind": "arc", "center": [0, 60 / angle, 8], "axis": [0, 0, 1], "start": [0, 0, 8],
        "sweepDeg": math.degrees(angle),
    }]}
    m.get("#continuous_swept_tube").deform_tube(
        rest=_REST, path=path, twist_deg=180 * t, max_segment_length=0.5,
        braid={"pitch": 5, "depth": 0.06, "strands": 8},
    )


ANIMATION = {"bend": cadgen.clip(_bend, duration=1, loop=False, label="Continuous swept tube — length 60 mm")}


@step(out="../STEP/runtime_fixture.step", animation=ANIMATION)
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
