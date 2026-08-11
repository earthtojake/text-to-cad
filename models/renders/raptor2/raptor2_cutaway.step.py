"""SpaceX Raptor 2 — quarter-section schematic cutaway (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

The axisymmetric shells are revolved through 270 degrees (opening faces +Y)
so the schematic interior is visible: hot-gas chamber/nozzle volumes, a
simplified annular regen-cooling band, a plain disk labeled "schematic
injector region — no element detail", translucent turbopump/preburner
placeholder volumes, and color-coded FFSC flow tubes (LOX/oxygen-rich = blue,
methane/fuel-rich = green, hot combustion gas = orange). All internals are
simplified, translucent, and labeled schematic/inferred/non-functional.
"""

from build123d import Compound

import raptor2_common as rc

DISPLAY_NAME = "SpaceX Raptor 2 schematic cutaway (educational public-source reconstruction)"


def gen_step():
    groups = rc.build_exterior(
        arc_deg=rc.CUT_ARC_DEG, start_deg=rc.CUT_START_DEG, section_pumps=True
    )
    groups += rc.build_schematic_interior()
    return Compound(
        obj=groups,
        children=groups,
        label="raptor2_schematic_cutaway__educational_nonfunctional",
    )
