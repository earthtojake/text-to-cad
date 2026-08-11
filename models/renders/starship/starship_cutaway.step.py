"""SpaceX Starship / Super Heavy stack — schematic cutaway (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Hull shells revolved through 270 degrees (opening faces +Y, the leeward side)
exposing dense schematic internals: translucent LOX (blue) and methane (green)
tank volumes, downcomers, header-tank placeholders, payload bay volume,
avionics modules, skirt stringers, engine-bay manifolds and mount blocks —
all simplified, translucent, labeled schematic/non-functional. Engine
instances remain whole.
"""

from build123d import Compound

import starship_common as sc

DISPLAY_NAME = "Starship / Super Heavy schematic cutaway (educational reconstruction)"


def gen_step():
    groups = sc.build_stack(
        arc=sc.CUT_ARC_DEG, start=sc.CUT_START_DEG, interior=True
    )
    return Compound(
        obj=groups,
        children=groups,
        label="starship_stack_schematic_cutaway__educational_nonfunctional",
    )
