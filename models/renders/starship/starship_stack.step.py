"""SpaceX Starship / Super Heavy full stack — reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Full ~123 m stack (V1/Block 1 with hot-staging ring, as flown IFT-2..6):
Super Heavy booster + vented hot-stage ring + Starship ship, with 39 linked
Raptor engine instances (33 SL booster, 3 SL + 3 RVac ship). See RESEARCH.md,
PROVENANCE.md, VARIANTS.md, HIERARCHY.md, and INSTANCE_MAP.md.
"""

from build123d import Compound

import starship_common as sc

DISPLAY_NAME = "SpaceX Starship / Super Heavy stack (educational public-source reconstruction)"


def gen_step():
    groups = sc.build_stack()
    return Compound(
        obj=groups,
        children=groups,
        label="starship_super_heavy_stack__educational_public_source_reconstruction",
    )
