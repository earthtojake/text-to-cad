"""SpaceX Falcon Heavy — exploded educational view.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Boosters translated outboard, second stage and fairing lifted, with
translucent guide rods. Offsets presentational only.
"""
from __future__ import annotations
from cadgen import step
from cadgen import build123d as bd
from lib import falcon_common as fc


OFFSETS = {
    "port_booster_group": (-5500.0, 0.0, 0.0),
    "starboard_booster_group": (5500.0, 0.0, 0.0),
    "second_stage_group": (0.0, 0.0, 9000.0),
    "payload_fairing_group": (0.0, 0.0, 18000.0),
}


@step(out="../STEP/falcon_heavy_exploded.step")
def falcon_heavy_exploded():
    groups = []
    for g in fc.build_vehicle():
        moved = g.moved(bd.Location(OFFSETS.get(g.label, (0.0, 0.0, 0.0))))
        moved.label = g.label
        groups.append(moved)
    rods = []
    for label, loc, ln, rot in (
        ("explode_guide_axis_z__annotation", (0, 0, 46000), 92000.0, (0, 0, 0)),
        ("explode_guide_axis_x__annotation", (0, 0, 21000), 18500.0, (0, 90, 0)),
    ):
        rod = bd.Cylinder(radius=60.0, height=ln, rotation=rot).locate(bd.Location(loc))
        rod.label = label
        rod.color = bd.Color(0.55, 0.57, 0.62, 0.45)
        rods.append(rod)
    groups.append(bd.Compound(obj=rods, children=rods, label="explode_guides_group"))
    return bd.Compound(obj=groups, children=groups,
                    label="falcon_heavy_exploded__educational_nonfunctional")


if __name__ == "__main__":
    falcon_heavy_exploded()
