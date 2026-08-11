"""SpaceX Raptor 2 sea-level engine — exterior reconstruction (educational).

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Exterior-only assembly: nozzle bell, chamber envelope, injector head dome,
thrust/gimbal structure, turbopump exterior placeholders, visible plumbing,
TVC brackets, avionics/harness. See RESEARCH.md and PROVENANCE.md for the
per-component source and confidence metadata.
"""

from build123d import Compound

import raptor2_common as rc

DISPLAY_NAME = rc.DISPLAY_NAME


def gen_step():
    groups = rc.build_exterior()
    return Compound(
        obj=groups,
        children=groups,
        label="raptor2_sea_level_exterior__educational_public_source_reconstruction",
    )
