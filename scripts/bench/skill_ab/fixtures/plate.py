"""A mounting plate with four holes."""
import build123d as bd
from cad import model

L, W, T = 80, 60, 6                                    # mm
HOLES = [(-30, -20), (30, -20), (30, 20), (-30, 20)]   # mm, hole centres
HOLE_D = 5                                             # mm


@model
def plate():
    body = bd.Box(L, W, T)
    for x, y in HOLES:
        body -= bd.Pos(x, y, 0) * bd.Cylinder(HOLE_D / 2, T)
    body.label = "plate"
    body.color = "#8a8f98"
    return body


if __name__ == "__main__":
    plate()
