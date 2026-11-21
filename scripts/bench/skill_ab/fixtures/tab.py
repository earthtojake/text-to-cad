"""A bent mounting tab: 0.090 in sheet, one 90 degree bend."""
import build123d as bd
from cad import model

T = 2.286          # mm, 0.090 in
R = 2.0            # mm, inside bend radius as modelled
BASE = 60.0        # mm, base flange length (outside)
UP = 7.0           # mm, upright flange height (outside)
WIDTH = 40.0       # mm


@model
def tab():
    outline = bd.Polygon((0, 0), (BASE, 0), (BASE, T), (T, T), (T, UP), (0, UP), align=None)
    corners = outline.vertices()
    inside = [v for v in corners if abs(v.X - T) < 1e-6 and abs(v.Y - T) < 1e-6]
    outside = [v for v in corners if abs(v.X) < 1e-6 and abs(v.Y) < 1e-6]
    outline = bd.fillet(inside, R)
    outside = [v for v in outline.vertices() if abs(v.X) < 1e-6 and abs(v.Y) < 1e-6]
    outline = bd.fillet(outside, R + T)
    body = bd.extrude(bd.Plane.XZ * outline, -WIDTH)
    for y in (10, 30):
        body -= bd.Pos(40, y, 0) * bd.Cylinder(2.5, 3 * T)
    body.label = "tab"
    return body


if __name__ == "__main__":
    tab()
