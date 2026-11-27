"""The demo model: a plate whose thickness and hole count are parameters, with a knob on it."""
import build123d as bd
from bd_materials import metals, plastics

from cad import xbf
from cad.build123d import paint

WALL = xbf.param("wall", 2.0, min=1, max=5)
HOLES = xbf.param("holes", 4, min=2, max=8)


@xbf
def plate():
    base = bd.Box(60, 40, WALL)
    for i in range(HOLES):
        base -= bd.Pos(-20 + 40 * i / max(1, HOLES - 1), 0, 0) * bd.Cylinder(3, 10)
    base.label = "base"
    base.material = metals.aluminum()
    polished = metals.aluminum()
    polished.pbr = polished.pbr.override(roughness=0.1)
    paint(base, base.faces().filter_by(bd.Axis.Z)[-1:], polished)
    knob = bd.Pos(0, 0, 10) * bd.Cylinder(5, 8)
    knob.label = "knob"
    knob.material = plastics.abs_()
    knob.color = "#c2410c"
    return bd.Compound(children=[base, knob], label="plate")


if __name__ == "__main__":
    plate()
