"""Small deterministic part used by Hardcore's CAD runtime smoke test."""

from cadgen import build123d as bd
from cadgen import step


WIDTH = 30
DEPTH = 20
HEIGHT = 6
HOLE_RADIUS = 3


@step()
def emdash_smoke():
    body = bd.Box(WIDTH, DEPTH, HEIGHT)
    mounting_hole = bd.Pos(0, 0, -1) * bd.Cylinder(HOLE_RADIUS, HEIGHT + 2)
    part = body - mounting_hole
    part.label = "emdash_smoke_plate"
    return part


if __name__ == "__main__":
    emdash_smoke()
