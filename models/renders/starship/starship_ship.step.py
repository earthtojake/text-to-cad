"""SpaceX Starship (upper stage) — exterior reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

9 m x 50.3 m ship (V1/Block 1) with 3 sea-level + 3 Raptor Vacuum linked
engine instances, forward and aft flaps, windward TPS field with featured
hex-tile array, and leeward raceway. See RESEARCH.md, PROVENANCE.md, and
INSTANCE_MAP.md.
"""

from build123d import Compound

import starship_common as sc

DISPLAY_NAME = "SpaceX Starship ship (educational public-source reconstruction)"


def gen_step():
    groups = sc.build_ship()
    return Compound(
        obj=groups,
        children=groups,
        label="starship_ship__educational_public_source_reconstruction",
    )
