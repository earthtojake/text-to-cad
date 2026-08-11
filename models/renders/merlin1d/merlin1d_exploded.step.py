"""SpaceX Merlin 1D — exploded educational view (public-source reconstruction).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Exterior assemblies separated along the thrust axis (Z) and radially, with
translucent guide rods marking reassembly axes. Offsets are presentational;
part-local geometry is identical to merlin1d.step.py.
"""

from build123d import Color, Compound, Cylinder, Location

import merlin_common as mc

DISPLAY_NAME = "SpaceX Merlin 1D exploded view (educational public-source reconstruction)"

OFFSETS = {
    "nozzle_assembly": (0.0, 0.0, -560.0),
    "chamber_assembly": (0.0, 0.0, 0.0),
    "thrust_structure_assembly": (0.0, 0.0, 420.0),
    "turbopump_assembly": (420.0, 0.0, 120.0),
    "gas_generator_assembly": (420.0, 0.0, 380.0),
    "turbine_exhaust_assembly": (330.0, 0.0, -300.0),
    "propellant_feed_assembly": (160.0, 0.0, 640.0),
    "harness_ignition_assembly": (0.0, -360.0, 0.0),
}

COL_GUIDE = Color(0.55, 0.57, 0.62, 0.45)


def _guide(label, location, length, rotation=(0, 0, 0)):
    rod = Cylinder(radius=5.0, height=length, rotation=rotation).locate(location)
    rod.label = label
    rod.color = COL_GUIDE
    return rod


def gen_step():
    groups = []
    for group in mc.build_exterior():
        moved = group.moved(Location(OFFSETS.get(group.label, (0.0, 0.0, 0.0))))
        moved.label = group.label
        groups.append(moved)
    rods = [
        _guide("explode_guide_axis_z__annotation", Location((0, 0, 1500)), 4100.0),
        _guide("explode_guide_axis_x_pump__annotation",
               Location((640, 0, 1650)), 1500.0, rotation=(0, 90, 0)),
        _guide("explode_guide_axis_y_harness__annotation",
               Location((0, -180, 1900)), 900.0, rotation=(90, 0, 0)),
    ]
    groups.append(Compound(obj=rods, children=rods, label="explode_guides_assembly"))
    return Compound(
        obj=groups,
        children=groups,
        label="merlin1d_exploded_view__educational_nonfunctional",
    )
