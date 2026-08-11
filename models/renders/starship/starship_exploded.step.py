"""SpaceX Starship / Super Heavy — exploded educational view.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Stage separation exploded view: ship lifted above the hot-stage ring and
booster, engine clusters dropped below their stages, flaps and TPS field
offset from the ship hull, grid fins offset from the booster, with schematic
interiors exposed in place. Offsets are purely presentational.
"""

from build123d import Color, Compound, Cylinder, Location

import starship_common as sc

DISPLAY_NAME = "Starship / Super Heavy exploded view (educational reconstruction)"

COL_GUIDE = Color(0.55, 0.57, 0.62, 0.45)

SHIP_DZ = sc.BOOSTER_HEIGHT + sc.HOT_STAGE_H

OFFSETS = {
    "booster_hull_group": (0, 0, 0),
    "booster_fittings_group": (0, 0, 0),
    "booster_engine_cluster__33_raptor_sl_instances": (0, 0, -14000.0),
    "booster_interior_group__schematic_nonfunctional": (0, 0, 0),
    "hot_stage_ring_group": (0, 0, 9000.0),
    "ship_hull_group": (0, 0, 26000.0),
    "ship_tps_field_group": (-11000.0, -8000.0, 26000.0),
    "ship_flaps_group": (0, 9000.0, 26000.0),
    "ship_engine_bay__3_sl_3_rvac_instances": (0, 0, 6000.0),
    "ship_interior_group__schematic_nonfunctional": (0, 0, 26000.0),
}


def _guide(label, location, length, rotation=(0, 0, 0)):
    rod = Cylinder(radius=60.0, height=length, rotation=rotation).locate(location)
    rod.label = label
    rod.color = COL_GUIDE
    return rod


def gen_step():
    groups = []
    booster_groups = sc.build_booster(interior=True)
    ring = sc.make_hot_stage_ring(z_base=sc.BOOSTER_HEIGHT)
    ship_groups = [sc._moved_group(g, SHIP_DZ) for g in sc.build_ship(interior=True)]
    for group in booster_groups + [ring] + ship_groups:
        offset = OFFSETS.get(group.label, (0, 0, 0))
        moved = group.moved(Location(offset))
        moved.label = group.label
        groups.append(moved)
    guides = [
        _guide("explode_guide_axis_z__annotation", Location((0, 0, 82000.0)), 128000.0),
        _guide("explode_guide_ship_engines__annotation",
               Location((0, 0, SHIP_DZ + 2000.0)), 16000.0),
    ]
    guide_group = Compound(obj=guides, children=guides, label="explode_guides_group")
    groups.append(guide_group)
    return Compound(
        obj=groups,
        children=groups,
        label="starship_stack_exploded_view__educational_nonfunctional",
    )
