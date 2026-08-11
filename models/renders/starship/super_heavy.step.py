"""SpaceX Super Heavy booster — exterior reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

9 m x 71 m booster with 33 linked Raptor 2 sea-level engine instances
(3 gimbaling center + 10 middle + 20 outer), fixed grid fins, raceways,
catch hardpoints, and COPV placeholders. See RESEARCH.md, PROVENANCE.md,
and INSTANCE_MAP.md.
"""

from build123d import Compound

import starship_common as sc

DISPLAY_NAME = "SpaceX Super Heavy booster (educational public-source reconstruction)"


def gen_step():
    groups = sc.build_booster()
    return Compound(
        obj=groups,
        children=groups,
        label="super_heavy_booster__educational_public_source_reconstruction",
    )
