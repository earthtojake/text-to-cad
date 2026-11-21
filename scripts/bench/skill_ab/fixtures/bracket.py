"""An L-bracket: a base flange and an upright."""
import build123d as bd
from cad import model

MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


@model
def bracket():
    base = bd.Box(60, 40, 6, align=MIN)
    upright = bd.Pos(-27, 0, 6) * bd.Box(6, 40, 60, align=MIN)
    body = base + upright
    inside = body.edges().filter_by(bd.Axis.Y).filter_by_position(bd.Axis.Z, 5.9, 6.1).filter_by_position(bd.Axis.X, -24.1, -23.9)
    body = bd.fillet(inside, 4)
    body.label = "bracket"
    return body


if __name__ == "__main__":
    bracket()
