"""SpaceX Merlin 1D — quarter-section schematic cutaway (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Axisymmetric shells revolved through 270 degrees (opening faces +Y), the
turbopump housing sectioned about its own axis, exposing schematic interior
volumes: hot-gas chamber/nozzle volumes, a simplified annular regen-cooling
band, a plain disk labeled "schematic injector region — no element detail",
translucent pump/turbine/gas-generator placeholder volumes, and color-coded
gas-generator-cycle flow tubes (LOX = blue, RP-1 = amber, hot gas = orange).
All internals are simplified, translucent, labeled schematic/inferred/
non-functional.
"""

from build123d import Compound

import merlin_common as mc

DISPLAY_NAME = "SpaceX Merlin 1D schematic cutaway (educational public-source reconstruction)"


def gen_step():
    groups = mc.build_exterior(
        arc_deg=mc.CUT_ARC_DEG, start_deg=mc.CUT_START_DEG, section_pumps=True
    )
    groups += mc.build_schematic_interior()
    return Compound(
        obj=groups,
        children=groups,
        label="merlin1d_schematic_cutaway__educational_nonfunctional",
    )
