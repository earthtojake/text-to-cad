"""SpaceX Raptor 2 — exploded educational view (public-source reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Exterior component groups separated along the thrust axis (Z) and radially,
with translucent guide rods marking the reassembly axes. Offsets are purely
presentational; part-local geometry is identical to raptor2.step.py.
"""

from build123d import Color, Compound, Cylinder, Location

import raptor2_common as rc

DISPLAY_NAME = "SpaceX Raptor 2 exploded view (educational public-source reconstruction)"

# presentational explode offsets per exterior group (mm)
OFFSETS = {
    "nozzle_bell_group": (0.0, 0.0, -650.0),
    "chamber_group": (0.0, 0.0, -280.0),
    "injector_head_group": (0.0, 0.0, 0.0),
    "thrust_structure_group": (0.0, 0.0, 260.0),
    "gimbal_mount_group": (0.0, 0.0, 520.0),
    "ox_turbopump_group": (380.0, 0.0, 120.0),
    "fuel_turbopump_group": (-380.0, 0.0, 120.0),
    "tvc_actuator_group": (0.0, 340.0, 260.0),
    "avionics_harness_group": (0.0, -340.0, 0.0),
}

COL_GUIDE = Color(0.55, 0.57, 0.62, 0.45)


def _guide(label: str, location: Location, length: float, rotation=(0, 0, 0)):
    rod = Cylinder(radius=6.0, height=length, rotation=rotation).locate(location)
    rod.label = label
    rod.color = COL_GUIDE
    return rod


def gen_step():
    groups = []
    for group in rc.build_exterior():
        offset = OFFSETS.get(group.label, (0.0, 0.0, 0.0))
        moved = group.moved(Location(offset))
        moved.label = group.label
        groups.append(moved)
    guides = Compound(
        obj=(rods := [
            _guide("explode_guide_axis_z__annotation", Location((0, 0, 1480)), 4300.0),
            _guide(
                "explode_guide_axis_x_pumps__annotation",
                Location((0, 0, 2195)), 1640.0, rotation=(0, 90, 0),
            ),
            _guide(
                "explode_guide_axis_y_tvc__annotation",
                Location((0, 100, 2790)), 1120.0, rotation=(90, 0, 0),
            ),
        ]),
        children=rods,
        label="explode_guides_group",
    )
    groups.append(guides)
    return Compound(
        obj=groups,
        children=groups,
        label="raptor2_exploded_view__educational_nonfunctional",
    )
